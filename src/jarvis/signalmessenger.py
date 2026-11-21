"""Send Signal messages with signal-cli.

Signal has no official interface for other programs to send messages, so
Jarvis uses signal-cli (https://github.com/AsamK/signal-cli), the unofficial,
open source command line client for Signal built on Signal's own libsignal
library. signal-cli has to be installed and linked to a Signal account (or
registered with a number of its own) before Jarvis can send anything.

Jarvis reaches signal-cli in one of two ways:

* By default it runs ``signal-cli send`` once per message and passes the text
  on standard input. ``JARVIS_SIGNAL_COMMAND`` changes the command, for
  example to run signal-cli inside Docker.
* When ``JARVIS_SIGNAL_URL`` is set, it posts a JSON-RPC ``send`` request to a
  signal-cli daemon started with ``signal-cli daemon --http``, which answers
  faster than starting signal-cli for every message.

Messages reach other people, so sending is opt-in: until
``JARVIS_SIGNAL_ENABLED`` is set, Jarvis only shows the message it would send.
Only the standard library is used.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional

from jarvis.emergency import UNIVERSAL_HINT
from jarvis.websearch import clean_text

ENABLE_ENV_VAR = "JARVIS_SIGNAL_ENABLED"
ACCOUNT_ENV_VAR = "JARVIS_SIGNAL_ACCOUNT"
COMMAND_ENV_VAR = "JARVIS_SIGNAL_COMMAND"
URL_ENV_VAR = "JARVIS_SIGNAL_URL"

DEFAULT_COMMAND = "signal-cli"
RPC_PATH = "/api/v1/rpc"
DEFAULT_TIMEOUT = 60.0
MAX_RESPONSE_BYTES = 1_000_000
CAPTCHA_URL = "https://signalcaptchas.org/challenge/generate.html"
SETUP_HINT = "See 'Signal messages' in the README to set up signal-cli."

_TRUTHY = {"1", "true", "yes", "on", "enable", "enabled"}

_SELF = re.compile(
    r"^(?:me|myself|self|(?:my\s+)?note[\s-]+to[\s-]+(?:self|myself))$", re.IGNORECASE
)
_USERNAME = re.compile(
    r"^(?:u:|@|username\s+)?(?P<name>[a-z_][a-z0-9_]{2,31}\.\d{2,9})$", re.IGNORECASE
)
# Digits with the spaces, brackets, dots and dashes people write between them.
_SEPARATORS = r"\s().\-\u2010-\u2015\u2212"
_PHONE = re.compile(rf"^\+?[\d{_SEPARATORS}]*\d[\d{_SEPARATORS}]*$")
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_EMERGENCY = re.compile(
    r"^(?:the\s+|an?\s+|my\s+local\s+|local\s+)?"
    r"(?:police|cops?|ambulance|paramedics?|fire(?:\s*fighters?|\s+(?:brigade|department|services?))?"
    r"|emergency(?:\s+(?:services?|numbers?|lines?))?)(?:\s+(?:in|for|of|at)\s+.+)?$",
    re.IGNORECASE,
)

#: Hints for signal-cli errors that have a well known fix.
_HINTS = (
    (
        re.compile(r"No local users found|^User \S+ is not registered", re.IGNORECASE),
        "Link signal-cli to your Signal account first. " + SETUP_HINT,
    ),
    (
        re.compile(r"^The user \S+ is not registered", re.IGNORECASE),
        "They may not use Signal, or the number may be wrong.",
    ),
    (
        re.compile(r"Multiple users found|requires valid account", re.IGNORECASE),
        f"Set {ACCOUNT_ENV_VAR} to the Signal number you send from.",
    ),
    (
        re.compile(r"Specified account does not exist", re.IGNORECASE),
        f"Check {ACCOUNT_ENV_VAR}: the daemon has no account with that number.",
    ),
    (
        re.compile(r"JAVA_HOME|'java' command|UnsupportedClassVersionError", re.IGNORECASE),
        "signal-cli needs Java 25 or newer; its native Linux build needs no Java.",
    ),
)

_EXIT_LABELS = {
    2: "unexpected error",
    3: "server or storage error",
    4: "untrusted safety number",
    5: "rate limited",
    6: "CAPTCHA rejected",
}

_RPC_LABELS = {
    -3: "server or storage error",
    -4: "untrusted safety number",
    -5: "rate limited",
    -6: "CAPTCHA rejected",
    -32600: "invalid request",
    -32601: "unknown method",
    -32602: "invalid parameters",
    -32603: "internal error",
    -32700: "unreadable request",
}

_HTTP_HINTS = {
    404: f"signal-cli's daemon answers JSON-RPC at {RPC_PATH}.",
    405: "Is it a signal-cli daemon?",
    415: "Is it a signal-cli daemon?",
    421: (
        "The daemon only accepts the host name it listens on: use localhost, "
        "127.0.0.1 or the address you passed to --http."
    ),
}

Runner = Callable[..., object]
Opener = Callable[..., object]


class SignalError(RuntimeError):
    """Raised when a Signal message cannot be prepared or sent."""


class EmergencyServiceError(SignalError):
    """Raised when the recipient is an emergency service, which Signal cannot reach."""


@dataclass(frozen=True)
class Recipient:
    """Who a Signal message goes to: a phone number, a username or yourself."""

    kind: str
    value: str = ""

    def describe(self) -> str:
        """Return the recipient as it reads in a sentence."""

        return "your Note to Self" if self.kind == "self" else self.value

    def address(self) -> str:
        """Return the recipient the way it is typed in a Jarvis command."""

        if self.kind == "self":
            return "me"
        if self.kind == "username":
            return f"u:{self.value}"
        return self.value

    def cli_arguments(self) -> List[str]:
        """Return the ``signal-cli send`` arguments that name the recipient."""

        return ["--note-to-self"] if self.kind == "self" else [self.address()]

    def rpc_params(self) -> Dict[str, object]:
        """Return the JSON-RPC ``send`` parameters that name the recipient."""

        if self.kind == "self":
            return {"noteToSelf": True}
        return {"recipient": [self.address()]}


def parse_recipient(text: str) -> Recipient:
    """Return the :class:`Recipient` named by ``text``.

    Phone numbers need ``+`` and the country code (``+254 712 345 678``);
    usernames look like ``u:alice.42`` or ``@alice.42``; ``me`` and
    ``note to self`` send to your own Note to Self.
    """

    raw = re.sub(r"\s+", " ", text or "").strip()
    raw = re.sub(r"[,\s]+please$", "", raw, flags=re.IGNORECASE)
    raw = raw.strip(" .!?,;\"'\u201c\u201d\u2018\u2019")
    if not raw:
        raise SignalError(
            "Who should I send it to? Give a phone number with its country code, "
            "such as +254712345678."
        )
    if _SELF.match(raw):
        return Recipient("self")
    username = _USERNAME.match(raw)
    if username:
        return Recipient("username", username.group("name"))
    number = re.sub(r"^plus\s*", "+", raw, flags=re.IGNORECASE)
    if _PHONE.match(number):
        digits = re.sub(r"\D", "", number)
        if not number.startswith("+"):
            if len(digits) <= 6:
                raise SignalError(
                    f"Signal cannot reach short numbers such as {digits}. If this is an "
                    "emergency, say 'call the police in <your country>' and I will find "
                    "the number to dial."
                )
            raise SignalError(
                "Signal needs the number in international format: + and the country "
                "code, such as +254712345678 rather than 0712345678."
            )
        if not 7 <= len(digits) <= 15 or digits.startswith("0"):
            raise SignalError(f"{clean_text(raw)[:40]} is not a full international phone number.")
        return Recipient("number", "+" + digits)
    if _EMERGENCY.match(raw):
        raise EmergencyServiceError(
            f"Signal cannot reach emergency services. {UNIVERSAL_HINT} Say 'call the "
            "police in <your country>' and I will find the number to dial."
        )
    raise SignalError(
        f"I do not keep a contact list, so I cannot look up '{clean_text(raw)[:60]}'. "
        "Give their Signal phone number with its country code (such as "
        "+254712345678) or their Signal username (such as u:alice.42)."
    )


def clean_message(text: str) -> str:
    """Return ``text`` trimmed, without one pair of surrounding double quotes."""

    message = (text or "").strip()
    if (
        len(message) >= 2
        and message[0] in "\"\u201c"
        and message[-1] in "\"\u201d"
        and not any(quote in message[1:-1] for quote in "\"\u201c\u201d")
    ):
        message = message[1:-1].strip()
    return message


def _env(environ: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def is_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """Return ``True`` when sending Signal messages has been opted into."""

    return str(_env(environ).get(ENABLE_ENV_VAR, "")).strip().lower() in _TRUTHY


def account(environ: Optional[Mapping[str, str]] = None) -> str:
    """Return the configured sending account, or ``""`` to let signal-cli choose."""

    configured = (_env(environ).get(ACCOUNT_ENV_VAR) or "").strip()
    if not configured:
        return ""
    if _UUID.match(configured):
        return configured.lower()
    number = re.sub(rf"[{_SEPARATORS}]", "", configured)
    if re.fullmatch(r"\+[1-9]\d{6,14}", number):
        return number
    raise SignalError(
        f"{ACCOUNT_ENV_VAR} must be your Signal number with its country code, "
        "such as +254712345678."
    )


def command(environ: Optional[Mapping[str, str]] = None) -> List[str]:
    """Return the signal-cli command, split like a shell would split it."""

    configured = (_env(environ).get(COMMAND_ENV_VAR) or "").strip()
    if not configured:
        return [DEFAULT_COMMAND]
    try:
        parts = shlex.split(configured)
    except ValueError as exc:
        raise SignalError(f"I could not read {COMMAND_ENV_VAR}: {exc}") from exc
    if not parts or not parts[0]:
        raise SignalError(f"{COMMAND_ENV_VAR} is empty.")
    return parts


def rpc_url(environ: Optional[Mapping[str, str]] = None) -> str:
    """Return the daemon's JSON-RPC address, or ``""`` to run signal-cli instead."""

    configured = (_env(environ).get(URL_ENV_VAR) or "").strip()
    if not configured:
        return ""
    if "://" not in configured:
        configured = "http://" + configured
    try:
        parts = urllib.parse.urlsplit(configured)
        # ``port`` raises ValueError when the port is not a number from 0 to 65535.
        valid = (
            parts.scheme.lower() in {"http", "https"}
            and bool(parts.hostname)
            and parts.port != 0
            and not re.search(r"[\s\x00-\x1f\x7f]", configured)
        )
    except ValueError:
        valid = False
    if not valid:
        raise SignalError(
            f"{URL_ENV_VAR} must be an http:// or https:// address, such as http://localhost:8080."
        )
    if parts.username is not None or parts.password is not None:
        raise SignalError(f"{URL_ENV_VAR} must not contain a user name or password.")
    path = parts.path if parts.path not in {"", "/"} else RPC_PATH
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc, path, parts.query, ""))


def build_command(
    recipient: Recipient, environ: Optional[Mapping[str, str]] = None
) -> List[str]:
    """Return the ``signal-cli send`` command line; the message goes on stdin."""

    argv = command(environ)
    sender = account(environ)
    if sender:
        argv += ["-a", sender]
    return [*argv, "-o", "json", "send", "--message-from-stdin", *recipient.cli_arguments()]


def build_rpc_request(
    recipient: Recipient,
    message: str,
    environ: Optional[Mapping[str, str]] = None,
    *,
    request_id: Optional[str] = None,
) -> Dict[str, object]:
    """Return the JSON-RPC ``send`` request for the signal-cli daemon."""

    params: Dict[str, object] = {**recipient.rpc_params(), "message": message}
    sender = account(environ)
    if sender:
        params["account"] = sender
    return {
        "jsonrpc": "2.0",
        "method": "send",
        "params": params,
        "id": request_id or f"jarvis-{uuid.uuid4().hex}",
    }


def _decode(data: object) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data or "")


def _json_object(text: str) -> Optional[Dict[str, object]]:
    for candidate in [text.strip(), *reversed(text.strip().splitlines())]:
        try:
            value = json.loads(candidate)
        except (ValueError, RecursionError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _last_line(text: str) -> str:
    lines = [line.strip() for line in clean_text(text).splitlines() if line.strip()]
    return lines[-1][:300] if lines else ""


def _with_hint(detail: str) -> str:
    for pattern, hint in _HINTS:
        if pattern.search(detail):
            return f"{detail} {hint}"
    return detail


def _failure(item: Mapping[str, object], recipient: Recipient) -> str:
    kind = str(item.get("type") or "").upper()
    who = recipient.describe()
    token = clean_text(item.get("token") or "").strip()
    if token:
        return (
            "Signal wants a CAPTCHA solved before this account sends more messages. "
            f"Solve it at {CAPTCHA_URL}, copy the 'Open Signal' link and run "
            f"'signal-cli submitRateLimitChallenge --challenge {token} --captcha <link>'."
        )
    if kind == "RATE_LIMIT_FAILURE":
        wait = item.get("retryAfterSeconds")
        later = f"in {wait} seconds" if isinstance(wait, int) and wait > 0 else "later"
        return f"Signal is rate limiting this account. Try again {later}."
    if kind == "UNREGISTERED_FAILURE":
        return f"{who} is not registered with Signal."
    if kind == "IDENTITY_FAILURE":
        return (
            f"The safety number for {who} has changed, so signal-cli held the message "
            "back. Verify the new safety number (for example with 'signal-cli "
            "listIdentities'), trust it with 'signal-cli trust', then try again."
        )
    if kind == "NETWORK_FAILURE":
        return "signal-cli could not reach the Signal servers. Check your internet connection."
    if kind == "INVALID_PRE_KEY_FAILURE":
        return (
            f"Signal could not set up encryption with one of {who}'s devices, which may "
            "not have been online for a while. Try again later."
        )
    return f"Signal reported {clean_text(kind)[:40] or 'a failure'} for {who}."


def _raise_for_failures(result: Mapping[str, object], recipient: Recipient) -> None:
    for item in result.get("results") or []:
        if isinstance(item, dict) and str(item.get("type") or "").upper() != "SUCCESS":
            raise SignalError(_failure(item, recipient))


def run_cli(
    recipient: Recipient,
    message: str,
    *,
    environ: Optional[Mapping[str, str]] = None,
    runner: Optional[Runner] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, object]:
    """Send ``message`` by running signal-cli and return its JSON result."""

    argv = build_command(recipient, environ)
    run = runner or subprocess.run
    try:
        completed = run(
            argv,
            input=message.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SignalError(
            f"I could not find '{argv[0]}'. Install signal-cli or set {COMMAND_ENV_VAR} "
            f"to its full path. {SETUP_HINT}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SignalError(
            f"signal-cli did not finish within {timeout:g} seconds, so I do not know "
            "whether the message was sent. Check Signal before you try again."
        ) from exc
    except OSError as exc:
        raise SignalError(f"I could not run '{argv[0]}': {exc}") from exc
    stdout = _decode(getattr(completed, "stdout", b""))
    result = _json_object(stdout) or {}
    code = getattr(completed, "returncode", 0)
    if code != 0:
        _raise_for_failures(result, recipient)
        detail = _last_line(_decode(getattr(completed, "stderr", b""))) or _last_line(stdout)
        label = _EXIT_LABELS.get(code, "")
        status = f"exit status {code}" + (f", {label}" if label else "")
        raise SignalError(
            f"signal-cli failed ({status}): {_with_hint(detail)}"
            if detail
            else f"signal-cli failed ({status})."
        )
    return result


def _open_direct(request: urllib.request.Request, timeout: float):
    # The daemon is local, so never route messages through a configured proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(request, timeout=timeout)


def post_rpc(
    recipient: Recipient,
    message: str,
    *,
    environ: Optional[Mapping[str, str]] = None,
    opener: Optional[Opener] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, object]:
    """Send ``message`` through the signal-cli daemon and return its result."""

    url = rpc_url(environ)
    if not url:
        raise SignalError(f"Set {URL_ENV_VAR} to the address of your signal-cli daemon.")
    body = json.dumps(build_rpc_request(recipient, message, environ)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    unknown = "so I do not know whether the message was sent. Check Signal before you try again."
    try:
        with (opener or _open_direct)(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        hint = _HTTP_HINTS.get(exc.code, "")
        raise SignalError(
            f"The signal-cli daemon at {url} refused the message (HTTP {exc.code})."
            + (f" {hint}" if hint else "")
        ) from exc
    except urllib.error.URLError as exc:
        reason = clean_text(getattr(exc, "reason", None) or exc).strip()[:200]
        raise SignalError(
            f"I could not reach the signal-cli daemon at {url} ({reason}). Start it with "
            "'signal-cli -a +YOUR_NUMBER daemon --http localhost:8080', or unset "
            f"{URL_ENV_VAR} to run signal-cli directly."
        ) from exc
    except TimeoutError as exc:
        raise SignalError(
            f"The signal-cli daemon did not answer within {timeout:g} seconds, {unknown}"
        ) from exc
    except (http.client.HTTPException, OSError) as exc:
        reason = clean_text(exc).strip()[:200] or exc.__class__.__name__
        raise SignalError(f"The signal-cli daemon stopped answering ({reason}), {unknown}") from exc
    except ValueError as exc:
        raise SignalError(f"{URL_ENV_VAR} is not an address I can use: {exc}") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise SignalError(f"The server at {url} sent more data than I can read, {unknown}")
    data = _json_object(_decode(payload))
    if data is None or ("result" not in data and "error" not in data):
        raise SignalError(f"The server at {url} did not answer like a signal-cli daemon.")
    error = data.get("error")
    if error:
        error = error if isinstance(error, dict) else {}
        details = error.get("data")
        response = details.get("response") if isinstance(details, dict) else None
        if isinstance(response, dict):
            _raise_for_failures(response, recipient)
        code = error.get("code")
        detail = clean_text(error.get("message") or "").strip()[:300]
        status = f"error {code}" if isinstance(code, int) else "error"
        label = _RPC_LABELS.get(code, "") if isinstance(code, int) else ""
        status += f", {label}" if label else ""
        raise SignalError(
            f"The signal-cli daemon could not send it ({status}): {_with_hint(detail)}"
            if detail
            else f"The signal-cli daemon could not send it ({status})."
        )
    result = data.get("result")
    if not isinstance(result, dict):
        raise SignalError(f"The server at {url} did not answer like a signal-cli daemon.")
    return result


def _preview(recipient: Recipient, message: str, env: Mapping[str, str]) -> str:
    url = rpc_url(env)
    sender = account(env)
    backend = f"the signal-cli daemon at {url}" if url else f"'{' '.join(command(env))}'"
    indented = "\n".join(f"  {line}" for line in message.splitlines() or [message])
    return (
        f"Signal message for {recipient.describe()}:\n{indented}\n"
        f"I have not sent it. Set {ENABLE_ENV_VAR}=1 to let me send it"
        f"{f' from {sender}' if sender else ''} through {backend}. {SETUP_HINT}"
    )


def send(
    recipient: Recipient,
    message: str,
    *,
    environ: Optional[Mapping[str, str]] = None,
    runner: Optional[Runner] = None,
    opener: Optional[Opener] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Send ``message`` to ``recipient`` when enabled and say what happened."""

    text = (message or "").strip()
    if not text:
        raise SignalError("The message is empty.")
    env = _env(environ)
    if not is_enabled(env):
        return _preview(recipient, text, env)
    if rpc_url(env):
        result = post_rpc(recipient, text, environ=env, opener=opener, timeout=timeout)
    else:
        result = run_cli(recipient, text, environ=env, runner=runner, timeout=timeout)
    _raise_for_failures(result, recipient)
    return f"Sent your Signal message to {recipient.describe()}."
