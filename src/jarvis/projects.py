"""Use charles2ke's connected projects straight from their own repositories.

tax-break, Portfolio-Watcher, OpenTrading, beat-it, 5-Mins and workout are git
submodules under ``projects/``. Jarvis keeps no copy of their code or data:
the skills built on them run each project's own JavaScript or TypeScript with
Node.js through the small adapters in ``bridges/``, and beat-it's JSON files
are read where they are. Updating a project is a submodule bump.

Fetch the projects once with ``git submodule update --init``. Node.js 22.18 or
newer is needed for every project except beat-it, because the TypeScript ones
rely on Node's built-in type stripping. ``JARVIS_PROJECTS_DIR`` points Jarvis
at checkouts somewhere else (for example when Jarvis is installed with pip),
and ``JARVIS_NODE`` picks the Node.js binary.

A missing checkout or Node.js raises :class:`ProjectUnavailable`, whose message
says how to set it up; a failure inside a project raises :class:`ProjectError`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

MIN_NODE = "22.18"
BRIDGES = Path(__file__).resolve().with_name("bridges")
_RUNNER = BRIDGES / "run.mjs"
_TIMEOUT = 30.0


@dataclass(frozen=True)
class Project:
    name: str
    repo: str
    site: str
    # A file every usable checkout has, so an empty submodule folder is caught.
    marker: str
    needs_node: bool = True


PROJECTS: Dict[str, Project] = {
    project.name: project
    for project in (
        Project(
            "tax-break",
            "https://github.com/charles2ke/tax-break",
            "https://charles2ke.github.io/tax-break/",
            "packages/tax-engine/src/index.ts",
        ),
        Project(
            "Portfolio-Watcher",
            "https://github.com/charles2ke/Portfolio-Watcher",
            "https://charles2ke.github.io/Portfolio-Watcher/",
            "src/research/dcf.ts",
        ),
        Project(
            "OpenTrading",
            "https://github.com/charles2ke/OpenTrading",
            "https://charles2ke.github.io/OpenTrading/",
            "src/core/trading.js",
        ),
        Project(
            "beat-it",
            "https://github.com/charles2ke/beat-it",
            "https://charles2ke.github.io/beat-it/",
            "site/data/cancers.json",
            needs_node=False,
        ),
        Project(
            "5-Mins",
            "https://github.com/charles2ke/5-Mins",
            "https://charles2ke.github.io/5-Mins/",
            "assets/js/alerts.js",
        ),
        Project(
            "workout",
            "https://github.com/charles2ke/workout",
            "https://charles2ke.github.io/workout/",
            "workout.js",
        ),
    )
}


class ProjectUnavailable(RuntimeError):
    """A project's checkout or Node.js is missing; the message says how to fix it."""


class ProjectError(RuntimeError):
    """A project's code failed or gave an answer Jarvis could not use."""


def projects_dir() -> Path:
    """The folder holding the project checkouts."""

    configured = os.environ.get("JARVIS_PROJECTS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "projects"


def _setup_hint(project: Project) -> str:
    step = f"From the Jarvis folder, run 'git submodule update --init projects/{project.name}'"
    if project.needs_node:
        step += f" and install Node.js {MIN_NODE} or newer"
    return step + f". Meanwhile, the app is at {project.site}"


def project_dir(name: str) -> Path:
    """Return the checkout of project ``name``, or raise :class:`ProjectUnavailable`."""

    project = PROJECTS[name]
    root = projects_dir() / name
    if not (root / project.marker).is_file():
        raise ProjectUnavailable(f"{name} isn't checked out here, so I can't use it. {_setup_hint(project)}.")
    return root


def read_json(name: str, relative: str) -> Any:
    """Load a JSON file from project ``name``'s checkout."""

    root = project_dir(name).resolve()
    path = (root / relative).resolve()
    if root not in path.parents:
        raise ValueError(f"{relative!r} is outside {name}")
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise ProjectError(f"{name} has no {relative}; the checkout may be out of date") from None
    except (OSError, ValueError) as exc:
        raise ProjectError(f"could not read {relative} from {name}: {exc}") from None


def _node(project: Project) -> str:
    configured = os.environ.get("JARVIS_NODE", "").strip()
    found = configured or shutil.which("node")
    if not found:
        raise ProjectUnavailable(
            f"{project.name} runs on Node.js, which isn't installed here, so I can't use it. "
            f"Install Node.js {MIN_NODE} or newer (or set JARVIS_NODE to its path). "
            f"Meanwhile, the app is at {project.site}."
        )
    return found


def call(name: str, action: str, payload: Any = None, *, timeout: float = _TIMEOUT) -> Any:
    """Run ``action`` of project ``name``'s bridge with a JSON ``payload``; return its result."""

    project = PROJECTS[name]
    root = project_dir(name)
    request = json.dumps(
        {"project": name, "root": str(root.resolve()), "action": action, "payload": payload},
        allow_nan=False,
    )
    command = [_node(project), "--no-warnings", str(_RUNNER)]
    try:
        done = subprocess.run(
            command,
            input=request,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ProjectError(f"{name} took longer than {timeout:g} seconds to answer") from None
    except OSError as exc:
        raise ProjectUnavailable(
            f"Node.js could not be started for {name} ({exc.strerror or exc}). "
            f"Install Node.js {MIN_NODE} or newer, or set JARVIS_NODE to its path."
        ) from None
    lines = done.stdout.strip().splitlines()
    try:
        reply = json.loads(lines[-1]) if lines else None
    except ValueError:
        reply = None
    if not isinstance(reply, dict):
        detail = (done.stderr.strip().splitlines() or [f"exit status {done.returncode}"])[-1]
        raise ProjectError(f"{name} failed: {detail[:300]}")
    if reply.get("ok") is True:
        return reply.get("result")
    error = reply.get("error") if isinstance(reply.get("error"), dict) else {}
    message = str(error.get("message") or "unknown error")[:300]
    if error.get("kind") == "node-too-old":
        raise ProjectUnavailable(
            f"{name} needs Node.js {MIN_NODE} or newer, but {message}. "
            f"Upgrade Node.js (or set JARVIS_NODE to a newer one). Meanwhile, the app is at {project.site}."
        )
    raise ProjectError(f"{name} failed: {message}")


def check(name: str) -> None:
    """Raise :class:`ProjectUnavailable` unless project ``name`` can be used here."""

    project = PROJECTS[name]
    project_dir(name)
    if project.needs_node:
        call(name, "ping")
