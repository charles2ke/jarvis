"""Spawn GitHub Copilot cloud sessions to answer open-ended questions.

The :func:`ask_cloud` helper starts a Copilot coding agent session on this
repository and returns a short summary of the session that was created. It uses
only the standard library, so Jarvis stays dependency free.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_REASONING_EFFORT = "max"
DEFAULT_API_BASE = "https://api.githubcopilot.com"
DEFAULT_TIMEOUT = 30.0

TOKEN_ENV_VARS = ("JARVIS_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")

_REMOTE_PATTERN = re.compile(
    r"(?:github\.com[:/]|/)(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


class CloudSessionError(RuntimeError):
    """Raised when a cloud session cannot be started."""


@dataclass(frozen=True)
class CloudSession:
    """Details of a cloud session that was created."""

    repository: str
    model: str
    query: str
    session_id: Optional[str] = None
    url: Optional[str] = None

    def summary(self) -> str:
        where = self.url or self.session_id or "(id unavailable)"
        return (
            f"I spawned a GitHub cloud session on {self.repository} using "
            f"{self.model} (reasoning effort: {DEFAULT_REASONING_EFFORT}) to answer: "
            f"{self.query}\nFollow it here: {where}"
        )


def detect_repository(cwd: Optional[str] = None) -> str:
    """Return the ``owner/repo`` slug for the current checkout."""

    configured = os.environ.get("JARVIS_GITHUB_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if configured:
        return configured.strip()
    try:
        remote = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CloudSessionError(
            "I could not work out which GitHub repository to use. "
            "Set JARVIS_GITHUB_REPO to 'owner/repo'."
        ) from exc
    found = _REMOTE_PATTERN.search(remote)
    if found is None:
        raise CloudSessionError(
            f"I could not parse the git remote '{remote}'. "
            "Set JARVIS_GITHUB_REPO to 'owner/repo'."
        )
    return f"{found.group('owner')}/{found.group('repo')}"


def _token() -> str:
    for name in TOKEN_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    raise CloudSessionError(
        "I need a GitHub token to start a cloud session. "
        f"Set one of: {', '.join(TOKEN_ENV_VARS)}."
    )


def spawn_session(
    query: str,
    *,
    repository: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> CloudSession:
    """Start a Copilot cloud session for ``query`` and return its details."""

    question = (query or "").strip()
    if not question:
        raise CloudSessionError("Tell me what you would like the cloud session to answer.")

    slug = repository or detect_repository()
    chosen_model = model or os.environ.get("JARVIS_CLOUD_MODEL") or DEFAULT_MODEL
    api_base = os.environ.get("JARVIS_COPILOT_API", DEFAULT_API_BASE).rstrip("/")
    payload = json.dumps(
        {
            "problem_statement": question,
            "model": chosen_model,
            "reasoning_effort": DEFAULT_REASONING_EFFORT,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{api_base}/agents/swe/v0/jobs/{slug}",
        data=payload,
        method="POST",
        headers={
            "Authorization": "Bearer " + _token(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:  # pragma: no cover - network failure paths
        raise CloudSessionError(
            f"GitHub refused to start the cloud session (HTTP {exc.code})."
        ) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:  # pragma: no cover
        raise CloudSessionError(f"I could not reach GitHub: {exc}") from exc
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise CloudSessionError("GitHub returned a response I could not read.") from exc

    session_id = body.get("session_id") or body.get("id")
    return CloudSession(
        repository=slug,
        model=chosen_model,
        query=question,
        session_id=str(session_id) if session_id is not None else None,
        url=body.get("pull_request", {}).get("html_url")
        if isinstance(body.get("pull_request"), dict)
        else body.get("html_url"),
    )


def ask_cloud(query: str) -> str:
    """Spawn a cloud session for ``query`` and return a human readable summary."""

    return spawn_session(query).summary()
