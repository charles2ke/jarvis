"""The Jarvis assistant engine."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Optional

from jarvis.memory import Memory
from jarvis.nl import normalize
from jarvis.skills import SkillContext, SkillRegistry, build_default_registry

FALLBACK_RESPONSE = (
    "I am not sure how to help with that yet. Ask me for 'help' to see my skills."
)


class Assistant:
    """Routes user requests to the first skill that understands them."""

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        memory: Optional[Memory] = None,
        now: Callable[[], datetime] = datetime.now,
        name: str = "Jarvis",
    ) -> None:
        self.name = name
        self.memory = memory if memory is not None else Memory()
        self.registry = registry if registry is not None else build_default_registry()
        self.history: List[tuple[str, str]] = []
        self._context = SkillContext(memory=self.memory, registry=self.registry, now=now)

    def greet(self) -> str:
        user = self.memory.get("user_name")
        who = f" {user}" if user else ""
        return (
            f"{self.name} online.{who and ' Welcome back' + who + '.'}"
            " Type 'help' to see what I can do, 'help <topic>' to narrow it down,"
            " or 'exit' to leave."
        )

    def respond(self, message: str) -> str:
        """Return the assistant reply for ``message``."""

        text = (message or "").strip()
        if not text:
            return "I am listening."
        resolved = self._resolve(text)
        if resolved is None:
            reply = FALLBACK_RESPONSE
        else:
            skill, match = resolved
            reply = skill.handler(match, self._context)
        self.history.append((text, reply))
        return reply

    def _resolve(self, text: str):
        """Resolve ``text``, falling back to its normalized form.

        The normalized form only wins when it reaches a skill that was
        registered earlier — that is, a more specific one — so plain text
        keeps its usual routing.
        """

        direct = self.registry.resolve(text)
        normalized = normalize(text)
        if not normalized or normalized == text:
            return direct
        rewritten = self.registry.resolve(normalized)
        if rewritten is None:
            return direct
        if direct is None:
            return rewritten
        order = {skill.name: index for index, skill in enumerate(self.registry)}
        if order[rewritten[0].name] < order[direct[0].name]:
            return rewritten
        return direct
