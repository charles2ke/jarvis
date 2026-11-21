"""Test helpers for skills built on the connected projects (see jarvis.projects).

``ProjectTestCase`` runs a class's tests against the real project in
``projects/`` and skips them when its submodule or Node.js is missing, unless
``JARVIS_REQUIRE_PROJECTS=1`` is set (CI sets it), which makes them fail
instead. ``fake_project`` stands in for a project's bridge, so the parsing and
replies around it can be tested without Node.js.
"""

import os
import tempfile
import unittest
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Tuple
from unittest import mock

from jarvis import projects

REQUIRED = os.environ.get("JARVIS_REQUIRE_PROJECTS") == "1"


class ProjectTestCase(unittest.TestCase):
    #: The project the tests need, or a tuple of several.
    project: "str | Tuple[str, ...]" = ""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        names = (cls.project,) if isinstance(cls.project, str) else cls.project
        try:
            for name in names:
                projects.check(name)
        except projects.ProjectUnavailable as exc:
            if REQUIRED:
                raise
            raise unittest.SkipTest(str(exc))


@contextmanager
def fake_project(name: str, actions: Dict[str, Any]) -> Iterator[List[Tuple[str, Any]]]:
    """Answer ``projects.call(name, action, payload)`` from ``actions``.

    A value in ``actions`` is returned as is, or called with the payload when
    it is callable. Yields the list of ``(action, payload)`` calls made.
    """

    calls: List[Tuple[str, Any]] = []

    def call(project: str, action: str, payload: Any = None, **_: Any) -> Any:
        if project != name:
            raise AssertionError(f"unexpected call to project {project!r}")
        calls.append((action, payload))
        answer = actions[action]
        return answer(payload) if callable(answer) else answer

    with mock.patch.object(projects, "call", side_effect=call):
        yield calls


@contextmanager
def missing_projects() -> Iterator[None]:
    """Point Jarvis at an empty projects folder."""

    with tempfile.TemporaryDirectory() as empty:
        with mock.patch.dict(os.environ, {"JARVIS_PROJECTS_DIR": empty}):
            yield
