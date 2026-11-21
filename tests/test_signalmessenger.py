import http.server
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from jarvis import emergency, signalmessenger
from jarvis.assistant import Assistant
from jarvis.memory import Memory
from jarvis.signalmessenger import Recipient, SignalError
from jarvis.skills import SkillContext, _signal_message

ENABLE = signalmessenger.ENABLE_ENV_VAR
ACCOUNT = signalmessenger.ACCOUNT_ENV_VAR
COMMAND = signalmessenger.COMMAND_ENV_VAR
URL = signalmessenger.URL_ENV_VAR
NUMBER = Recipient("number", "+15551234567")
SENT = "Sent your Signal message to +15551234567."


def completed(returncode=0, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess(["signal-cli"], returncode, stdout, stderr)


def results(kind, **extra):
    item = {"recipientAddress": {"number": "+15551234567"}, "type": kind, **extra}
    return {"timestamp": 1, "results": [item]}


class FakeResponse:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class SignalSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in (ENABLE, ACCOUNT, COMMAND, URL, emergency.ENABLE_ENV_VAR):
            os.environ.pop(name, None)
        self.assistant = Assistant(memory=Memory(None))

    def test_phrasings_preview_the_message_exactly_as_typed(self):
        cases = {
            "signal +15551234567: running late, see you at 7": (
                "+15551234567", "running late, see you at 7"
            ),
            "send a signal message to u:alice.42 saying the train is delayed": (
                "alice.42", "the train is delayed"
            ),
            "message +254 712 345 678 on signal that I'm on my way": (
                "+254712345678", "I'm on my way"
            ),
            "send a message via signal to +254712345678: hi": ("+254712345678", "hi"),
            "send 'happy birthday!' to +15551234567 on signal": (
                "+15551234567", "happy birthday!"
            ),
            "send \u201cgo to bob\u201d to +15551234567 via signal.": ("+15551234567", "go to bob"),
            "ping @alice.42 via the Signal app: hi": ("alice.42", "hi"),
            "signal +1 555\u2013123\u20134567: hi": ("+15551234567", "hi"),
            "note to self on signal: buy milk": ("your Note to Self", "buy milk"),
            "send me a signal message: line one\nline two": (
                "your Note to Self", "line one\n  line two"
            ),
            # Polite prefixes match as typed, so number and operator words are kept.
            "hey jarvis, could you please signal +1 (555) 123-4567: I'll be over in one minute": (
                "+15551234567", "I'll be over in one minute"
            ),
            "Jarvis, please, could you signal plus 1 555 123 4567 saying 2 times 3": (
                "+15551234567", "2 times 3"
            ),
            "send 'the party is over, home by ten' to +15551234567 on signal, please.": (
                "+15551234567", "the party is over, home by ten"
            ),
            "signal +15551234567: 10:30 works for me": ("+15551234567", "10:30 works for me"),
            "send a signal message to +15551234567 that says: running late": (
                "+15551234567", "running late"
            ),
            "signal +15551234567 saying that: running late": ("+15551234567", "running late"),
            "text +15551234567 on signal, please: running late": ("+15551234567", "running late"),
            "signal +15551234567 please: please call me": ("+15551234567", "please call me"),
        }
        for text, (who, message) in cases.items():
            with self.subTest(text=text):
                reply = self.assistant.respond(text)
                self.assertTrue(
                    reply.startswith(f"Signal message for {who}:\n  {message}\nI have not sent it."),
                    reply,
                )
                self.assertIn(f"Set {ENABLE}=1 to let me send it through 'signal-cli'.", reply)

    def test_other_skills_keep_their_phrases(self):
        cases = {
            "what does a flashing red signal mean": "traffic-signs",
            "tell me about traffic signals": "traffic-signs",
            "tell me about the problems with signal": "traffic-signs",
            "text the emergency numbers for Kenya to +15551234567 on signal": "emergency-share",
            "signal +15551234567: I want to die": "crisis-support",
        }
        for text, skill in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.assistant.registry.resolve(text)[0].name, skill)
        for text in (
            "signal processing: what is it",
            "tell me how to block someone on signal",
            "tell me how to verify a safety number on signal",
        ):
            with self.subTest(text=text):
                self.assertIsNone(self.assistant.registry.resolve(text))

    def test_asks_instead_of_sending_when_the_request_is_incomplete(self):
        os.environ[ENABLE] = "1"
        run_on = "Put a colon and a space after the recipient"
        cases = {
            "signal +15551234567": (
                "What should the Signal message to +15551234567 say? "
                "Say 'signal +15551234567: your message'."
            ),
            "text +15551234567 on signal, please?": "What should the Signal message to +15551234567",
            "send a signal message": "Who should I send it to?",
            "signal +15551234567 hello there": run_on,
            # The hour of a time must not be read as the end of the number.
            "signal +15551234567 10:30 works for me": run_on,
            "signal +254 712 345 678 3:15 pm at the gate": run_on,
            "send a signal message to +15551234567 2:30 is fine": run_on,
            "signal +15551234567:7pm works": run_on,
            "text bob on signal: hi": "I do not keep a contact list, so I cannot look up 'bob'.",
            "signal @alice: hello": "I do not keep a contact list, so I cannot look up '@alice'.",
            "send a signal message to 0712345678: hi": "international format",
            "signal 911 help": "Signal cannot reach short numbers such as 911.",
        }
        with mock.patch("subprocess.run") as run:
            for text, expected in cases.items():
                with self.subTest(text=text):
                    self.assertIn(expected, self.assistant.respond(text))
        run.assert_not_called()

    def test_emergency_services_get_an_emergency_text_instead(self):
        os.environ[ENABLE] = "1"
        cases = {
            "text the police in France on signal: there is a break-in": (
                "Texting 114 for police in France. "
                "Open sms:114?body=there%20is%20a%20break-in"
            ),
            "send a signal message to the police: help": "Which country are you in? On a mobile phone 112",
            "message my local police on signal: help": "On a mobile phone 112 reaches emergency services",
        }
        with mock.patch("subprocess.run") as run:
            for text, expected in cases.items():
                with self.subTest(text=text):
                    reply = self.assistant.respond(text)
                    self.assertTrue(
                        reply.startswith("Signal cannot reach emergency services. "), reply
                    )
                    self.assertIn(expected, reply)
        run.assert_not_called()

    def test_enabled_skill_sends_and_reports_failures(self):
        match = self.assistant.registry.resolve("signal +15551234567: on my way")[1]
        env = {ENABLE: "1"}
        runner = mock.Mock(return_value=completed(stdout=json.dumps(results("SUCCESS")).encode()))
        self.assertEqual(_signal_message(match, None, environ=env, runner=runner), SENT)
        self.assertEqual(runner.call_args.kwargs["input"], b"on my way")

        runner = mock.Mock(side_effect=FileNotFoundError(2, "No such file"))
        reply = _signal_message(match, None, environ=env, runner=runner)
        self.assertTrue(
            reply.startswith("I could not send the Signal message: I could not find 'signal-cli'."),
            reply,
        )

    def test_never_sends_a_message_that_only_matched_after_normalizing(self):
        registry = self.assistant.registry
        match = registry.resolve("send 'home by 10' to +15551234567 on signal")[1]
        context = SkillContext(
            memory=Memory(None),
            registry=registry,
            text="send 'home by ten' to +15551234567 on signal",
        )
        runner = mock.Mock()
        reply = _signal_message(match, context, environ={ENABLE: "1"}, runner=runner)
        self.assertIn("so I have not sent it", reply)
        runner.assert_not_called()

    def test_look_it_up_never_searches_a_signal_message(self):
        assistant = Assistant(memory=Memory(None), web_search="manual")
        assistant.respond("who invented the telephone")
        assistant.respond("signal +15551234567: meet me at the clinic")
        assistant.respond("signal +one billion: meet me at the clinic")
        with mock.patch("jarvis.skills._web_answer", return_value=("(searched)", True)) as web:
            assistant.respond("look it up")
        self.assertEqual(web.call_args.args[1], "who invented the telephone")


class RecipientTests(unittest.TestCase):
    def test_parses_numbers_usernames_and_note_to_self(self):
        cases = {
            "+1 (555) 123-4567": NUMBER,
            "plus 254 712 345 678.": Recipient("number", "+254712345678"),
            "'+44 20 7946 0958', please": Recipient("number", "+442079460958"),
            "u:alice.42": Recipient("username", "alice.42"),
            "@alice.42": Recipient("username", "alice.42"),
            "username alice.42": Recipient("username", "alice.42"),
            "me": Recipient("self"),
            "My Note to Self": Recipient("self"),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(signalmessenger.parse_recipient(text), expected)

    def test_rejects_what_signal_cannot_reach(self):
        cases = {
            "": "Who should I send it to?",
            "0712345678": "international format",
            "112": "short numbers such as 112",
            "+12 34": "+12 34 is not a full international phone number.",
            "+0123456789": "is not a full international phone number.",
            "the police in Kenya": "Signal cannot reach emergency services. On a mobile phone 112",
            "Mom": "I do not keep a contact list, so I cannot look up 'Mom'.",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                with self.assertRaises(SignalError) as caught:
                    signalmessenger.parse_recipient(text)
                self.assertIn(expected, str(caught.exception))

    def test_clean_message_removes_one_pair_of_outer_double_quotes(self):
        cases = {
            '  "on my way"  ': "on my way",
            "\u201con my way\u201d": "on my way",
            '"a" and "b"': '"a" and "b"',
            "'single quotes stay'": "'single quotes stay'",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(signalmessenger.clean_message(text), expected)


class SettingsTests(unittest.TestCase):
    def test_daemon_url(self):
        cases = {
            "": "",
            "localhost:8080": "http://localhost:8080/api/v1/rpc",
            "http://127.0.0.1:8080/": "http://127.0.0.1:8080/api/v1/rpc",
            "HTTPS://signal.example/rpc": "https://signal.example/rpc",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(signalmessenger.rpc_url({URL: value}), expected)
        for value in (
            "ftp://localhost:8080",
            "http://:8080",
            "http://localhost:99999",
            "http://local host:8080",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(SignalError, "must be an http:// or https:// address"):
                    signalmessenger.rpc_url({URL: value})
        with self.assertRaises(SignalError) as caught:
            signalmessenger.rpc_url({URL: "http://user:secret@localhost:8080"})
        self.assertNotIn("secret", str(caught.exception))

    def test_account_and_command(self):
        self.assertEqual(signalmessenger.account({}), "")
        self.assertEqual(signalmessenger.account({ACCOUNT: " +1 555-123-4567 "}), "+15551234567")
        aci = "0F0F0F0F-1234-4ABC-8DEF-0123456789AB"
        self.assertEqual(signalmessenger.account({ACCOUNT: aci}), aci.lower())
        with self.assertRaisesRegex(SignalError, "country code"):
            signalmessenger.account({ACCOUNT: "0712345678"})

        self.assertEqual(signalmessenger.command({}), ["signal-cli"])
        self.assertEqual(
            signalmessenger.command({COMMAND: "docker exec -i 'signal cli' signal-cli"}),
            ["docker", "exec", "-i", "signal cli", "signal-cli"],
        )
        for value in ("'unterminated", "''"):
            with self.subTest(value=value):
                with self.assertRaises(SignalError):
                    signalmessenger.command({COMMAND: value})

    def test_preview_sends_nothing_but_still_checks_settings(self):
        runner, opener = mock.Mock(), mock.Mock()
        reply = signalmessenger.send(
            NUMBER, "on my way\nsee you", environ={}, runner=runner, opener=opener
        )
        self.assertEqual(
            reply,
            "Signal message for +15551234567:\n  on my way\n  see you\n"
            "I have not sent it. Set JARVIS_SIGNAL_ENABLED=1 to let me send it through "
            "'signal-cli'. See 'Signal messages' in the README to set up signal-cli.",
        )
        reply = signalmessenger.send(
            NUMBER,
            "hi",
            environ={ENABLE: "0", ACCOUNT: "+15550000000", URL: "localhost:8080"},
            runner=runner,
            opener=opener,
        )
        self.assertIn(
            "send it from +15550000000 through the signal-cli daemon at "
            "http://localhost:8080/api/v1/rpc.",
            reply,
        )
        runner.assert_not_called()
        opener.assert_not_called()
        with self.assertRaisesRegex(SignalError, "JARVIS_SIGNAL_URL must be"):
            signalmessenger.send(NUMBER, "hi", environ={URL: "ftp://localhost"})


class CommandLineTests(unittest.TestCase):
    def send(self, runner, recipient=NUMBER, message="h\u00e9llo \U0001f44b", **env):
        return signalmessenger.send(recipient, message, environ={ENABLE: "1", **env}, runner=runner)

    def test_passes_the_message_on_standard_input(self):
        stdout = b"INFO starting\n" + json.dumps(results("SUCCESS")).encode()
        runner = mock.Mock(return_value=completed(stdout=stdout, stderr=b"WARN slow\n"))
        self.assertEqual(self.send(runner, **{ACCOUNT: "+15550000000"}), SENT)
        runner.assert_called_once_with(
            ["signal-cli", "-a", "+15550000000", "-o", "json", "send", "--message-from-stdin",
             "+15551234567"],
            input="h\u00e9llo \U0001f44b".encode("utf-8"),
            capture_output=True,
            timeout=60.0,
            check=False,
        )

    def test_recipients_and_custom_commands(self):
        self.assertEqual(
            signalmessenger.build_command(Recipient("self"), {}),
            ["signal-cli", "-o", "json", "send", "--message-from-stdin", "--note-to-self"],
        )
        self.assertEqual(
            signalmessenger.build_command(
                Recipient("username", "alice.42"), {COMMAND: "docker exec -i sig signal-cli"}
            ),
            ["docker", "exec", "-i", "sig", "signal-cli", "-o", "json", "send",
             "--message-from-stdin", "u:alice.42"],
        )

    def test_failed_results_say_what_to_do(self):
        cases = [
            (1, results("UNREGISTERED_FAILURE"), "+15551234567 is not registered with Signal."),
            (4, results("IDENTITY_FAILURE"), "trust it with 'signal-cli trust'"),
            (5, results("RATE_LIMIT_FAILURE", retryAfterSeconds=30), "Try again in 30 seconds."),
            (
                5,
                results("RATE_LIMIT_FAILURE", token="abc-123"),
                "'signal-cli submitRateLimitChallenge --challenge abc-123 --captcha <link>'",
            ),
            (1, results("NETWORK_FAILURE"), "Check your internet connection."),
        ]
        for code, result, expected in cases:
            with self.subTest(expected=expected):
                runner = mock.Mock(
                    return_value=completed(code, json.dumps(result).encode(), b"Failed to send message\n")
                )
                with self.assertRaises(SignalError) as caught:
                    self.send(runner)
                self.assertIn(expected, str(caught.exception))

    def test_errors_quote_signal_cli_with_a_hint(self):
        cases = [
            (
                1,
                b"No local users found, you first need to register or link an account\n",
                "signal-cli failed (exit status 1): No local users found, you first need to "
                "register or link an account Link signal-cli to your Signal account first.",
            ),
            (
                1,
                b"Multiple users found, you need to specify an account (phone number or ACI) with -a\n",
                f"Set {ACCOUNT} to the Signal number you send from.",
            ),
            (1, b"The user +15551234567 is not registered.\n", "They may not use Signal"),
            (3, b"WARN noise\nConnection \x1b]0;owned\x07failed\n", "(exit status 3, server or storage error): Connection ]0;ownedfailed"),
            (2, b"", "signal-cli failed (exit status 2, unexpected error)."),
        ]
        for code, stderr, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(SignalError) as caught:
                    self.send(mock.Mock(return_value=completed(code, b"", stderr)))
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn("\x1b", str(caught.exception))

    def test_missing_command_and_timeout(self):
        with self.assertRaisesRegex(SignalError, "I could not find 'signal-cli'. Install signal-cli"):
            self.send(mock.Mock(side_effect=FileNotFoundError(2, "No such file")))
        with self.assertRaisesRegex(
            SignalError, "did not finish within 60 seconds, so I do not know whether"
        ):
            self.send(mock.Mock(side_effect=subprocess.TimeoutExpired("signal-cli", 60)))

    def test_runs_a_real_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "call.json"
            script = Path(tmp) / "fake_signal_cli.py"
            script.write_text(
                "import json, sys\n"
                "message = sys.stdin.buffer.read().decode('utf-8')\n"
                f"with open({str(log)!r}, 'w', encoding='utf-8') as log:\n"
                "    json.dump({'argv': sys.argv[1:], 'message': message}, log)\n"
                "print(json.dumps({'timestamp': 1, 'results': [{'type': 'SUCCESS'}]}))\n",
                encoding="utf-8",
            )
            command = " ".join(shlex.quote(part) for part in (sys.executable, str(script)))
            reply = signalmessenger.send(
                Recipient("self"), "h\u00e9llo \U0001f44b\nline two", environ={ENABLE: "1", COMMAND: command}
            )
            call = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(reply, "Sent your Signal message to your Note to Self.")
        self.assertEqual(
            call,
            {
                "argv": ["-o", "json", "send", "--message-from-stdin", "--note-to-self"],
                "message": "h\u00e9llo \U0001f44b\nline two",
            },
        )


class DaemonTests(unittest.TestCase):
    def send(self, opener, recipient=NUMBER, **env):
        environ = {ENABLE: "1", URL: "http://localhost:8080", **env}
        runner = mock.Mock(side_effect=AssertionError("signal-cli should not run"))
        return signalmessenger.send(recipient, "h\u00e9llo", environ=environ, opener=opener, runner=runner)

    def test_posts_a_json_rpc_send_request(self):
        opener = mock.Mock(
            return_value=FakeResponse({"jsonrpc": "2.0", "result": results("SUCCESS"), "id": "1"})
        )
        self.assertEqual(self.send(opener, **{ACCOUNT: "+15550000000"}), SENT)
        request = opener.call_args.args[0]
        self.assertEqual(opener.call_args.kwargs, {"timeout": 60.0})
        self.assertEqual(request.full_url, "http://localhost:8080/api/v1/rpc")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        body = json.loads(request.data)
        self.assertTrue(body.pop("id"))
        self.assertEqual(
            body,
            {
                "jsonrpc": "2.0",
                "method": "send",
                "params": {"recipient": ["+15551234567"], "message": "h\u00e9llo", "account": "+15550000000"},
            },
        )
        self.assertEqual(
            signalmessenger.build_rpc_request(Recipient("self"), "hi", {}, request_id="7"),
            {"jsonrpc": "2.0", "method": "send", "params": {"noteToSelf": True, "message": "hi"}, "id": "7"},
        )

    def test_daemon_errors_say_what_to_do(self):
        url = "http://localhost:8080/api/v1/rpc"
        unregistered = {
            "error": {
                "code": -1,
                "message": "Failed to send message",
                "data": {"response": results("UNREGISTERED_FAILURE")},
            }
        }
        missing_account = {"error": {"code": -32602, "message": "Method requires valid account parameter"}}
        cases = [
            (FakeResponse(unregistered), "+15551234567 is not registered with Signal."),
            (
                FakeResponse(missing_account),
                "(error -32602, invalid parameters): Method requires valid account parameter "
                f"Set {ACCOUNT}",
            ),
            (FakeResponse(b"<html>it works</html>"), "did not answer like a signal-cli daemon"),
            (
                urllib.error.HTTPError(url, 421, "Misdirected Request", {}, None),
                "(HTTP 421). The daemon only accepts the host name it listens on",
            ),
            (
                urllib.error.URLError(ConnectionRefusedError(111, "Connection refused")),
                f"I could not reach the signal-cli daemon at {url} ([Errno 111] Connection refused)",
            ),
            (TimeoutError("timed out"), "did not answer within 60 seconds, so I do not know whether"),
        ]
        for outcome, expected in cases:
            with self.subTest(expected=expected):
                if isinstance(outcome, BaseException):
                    opener = mock.Mock(side_effect=outcome)
                else:
                    opener = mock.Mock(return_value=outcome)
                with self.assertRaises(SignalError) as caught:
                    self.send(opener)
                self.assertIn(expected, str(caught.exception))

    def test_reaches_a_local_daemon_directly_even_with_a_proxy_set(self):
        requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                requests.append((self.path, self.headers["Content-Type"], json.loads(body)["params"]))
                reply = json.dumps({"jsonrpc": "2.0", "result": results("SUCCESS"), "id": "1"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        proxy = "http://127.0.0.1:9"
        with mock.patch.dict(os.environ, {"http_proxy": proxy, "HTTP_PROXY": proxy}):
            os.environ.pop("no_proxy", None)
            os.environ.pop("NO_PROXY", None)
            reply = signalmessenger.send(
                NUMBER, "h\u00e9llo", environ={ENABLE: "1", URL: f"127.0.0.1:{port}"}
            )
        self.assertEqual(reply, SENT)
        self.assertEqual(
            requests,
            [("/api/v1/rpc", "application/json", {"recipient": ["+15551234567"], "message": "h\u00e9llo"})],
        )


if __name__ == "__main__":
    unittest.main()
