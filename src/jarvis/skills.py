"""Skill definitions and the default Jarvis skill set."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable, List, Match, Optional, Pattern, Sequence

from jarvis.calculator import CalculationError, calculate
from jarvis.memory import Memory


@dataclass
class SkillContext:
    """Runtime state handed to a skill when it is invoked."""

    memory: Memory
    registry: "SkillRegistry"
    now: Callable[[], datetime] = datetime.now


SkillHandler = Callable[[Match[str], SkillContext], str]


@dataclass
class Skill:
    """A named capability triggered by one or more regular expressions."""

    name: str
    description: str
    patterns: Sequence[str]
    handler: SkillHandler
    examples: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self._compiled: List[Pattern[str]] = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.patterns
        ]

    def match(self, text: str) -> Optional[Match[str]]:
        for pattern in self._compiled:
            found = pattern.search(text)
            if found is not None:
                return found
        return None


class SkillRegistry:
    """Ordered collection of skills with first-match resolution."""

    def __init__(self, skills: Iterable[Skill] = ()) -> None:
        self._skills: List[Skill] = []
        for skill in skills:
            self.register(skill)

    def register(self, skill: Skill) -> Skill:
        if any(existing.name == skill.name for existing in self._skills):
            raise ValueError(f"A skill named '{skill.name}' is already registered.")
        self._skills.append(skill)
        return skill

    def resolve(self, text: str) -> Optional[tuple[Skill, Match[str]]]:
        for skill in self._skills:
            found = skill.match(text)
            if found is not None:
                return skill, found
        return None

    @property
    def skills(self) -> tuple[Skill, ...]:
        return tuple(self._skills)

    def __len__(self) -> int:
        return len(self._skills)

    def __iter__(self):
        return iter(self._skills)


def _greeting(match: Match[str], context: SkillContext) -> str:
    name = context.memory.get("user_name")
    if name:
        return f"Hello {name}. How can I help you today?"
    return "Hello. I am Jarvis, your personal AI companion. How can I help?"


def _remember_name(match: Match[str], context: SkillContext) -> str:
    name = match.group("name").strip().rstrip(".!")
    context.memory.set("user_name", name)
    return f"Pleased to meet you, {name}. I will remember that."

def _recall_name(match: Match[str], context: SkillContext) -> str:
    name = context.memory.get("user_name")
    if name:
        return f"You are {name}."
    return "I do not know your name yet. Tell me: 'my name is ...'."


def _current_time(match: Match[str], context: SkillContext) -> str:
    return f"It is {context.now().strftime('%H:%M')}."


def _current_date(match: Match[str], context: SkillContext) -> str:
    return f"Today is {context.now().strftime('%A, %d %B %Y')}."


def _calculate(match: Match[str], context: SkillContext) -> str:
    expression = match.group("expression").strip().rstrip("?")
    try:
        result = calculate(expression)
    except CalculationError as exc:
        return str(exc)
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return f"{expression} = {result}"


def _add_note(match: Match[str], context: SkillContext) -> str:
    note = match.group("note").strip()
    if not note:
        return "What would you like me to note down?"
    notes = context.memory.append("notes", note)
    return f"Noted. You now have {len(notes)} note(s)."


def _list_notes(match: Match[str], context: SkillContext) -> str:
    notes = context.memory.get("notes", [])
    if not notes:
        return "You have no notes yet."
    lines = [f"{index}. {note}" for index, note in enumerate(notes, start=1)]
    return "Your notes:\n" + "\n".join(lines)


def _clear_notes(match: Match[str], context: SkillContext) -> str:
    context.memory.clear("notes")
    return "All notes cleared."


def _help(match: Match[str], context: SkillContext) -> str:
    lines = ["Here is what I can do:"]
    for skill in context.registry:
        lines.append(f"- {skill.name}: {skill.description}")
        if skill.examples:
            lines.append(f"    e.g. {skill.examples[0]}")
    return "\n".join(lines)


def _farewell(match: Match[str], context: SkillContext) -> str:
    return "Goodbye. Call on me whenever you need."


def build_default_registry(memory: Optional[Memory] = None) -> SkillRegistry:
    """Return a registry populated with the built-in Jarvis skills."""

    del memory  # Reserved for skills that need memory at construction time.
    return SkillRegistry(
        [
            Skill(
                name="greeting",
                description="Greet Jarvis and start a conversation.",
                patterns=[r"^\s*(hello|hi|hey|good (morning|afternoon|evening))\b"],
                handler=_greeting,
                examples=["hello"],
            ),
            Skill(
                name="remember-name",
                description="Remember how you would like to be addressed.",
                patterns=[r"\bmy name is (?P<name>[\w .'-]+)"],
                handler=_remember_name,
                examples=["my name is Charles"],
            ),
            Skill(
                name="recall-name",
                description="Recall the name you shared with me.",
                patterns=[r"\b(what('s| is) my name|who am i)\b"],
                handler=_recall_name,
                examples=["what is my name?"],
            ),
            Skill(
                name="time",
                description="Report the current time.",
                patterns=[r"\bwhat('s| is)? ?the time\b", r"\bcurrent time\b"],
                handler=_current_time,
                examples=["what is the time?"],
            ),
            Skill(
                name="date",
                description="Report today's date.",
                patterns=[
                    r"\bwhat('s| is)? ?(today'?s )?date\b",
                    r"\bwhat day is it\b",
                ],
                handler=_current_date,
                examples=["what is today's date?"],
            ),
            Skill(
                name="calculator",
                description="Evaluate basic arithmetic expressions.",
                patterns=[
                    r"^\s*(calculate|compute|what is|what's)\s+(?P<expression>[-+*/%(). \d]+)\s*\??\s*$",
                    r"^\s*(?P<expression>[-+*/%(). \d]*\d[-+*/%(). \d]*[-+*/%][-+*/%(). \d]*)\s*$",
                ],
                handler=_calculate,
                examples=["calculate 21 * 2"],
            ),
            Skill(
                name="add-note",
                description="Store a note for later.",
                patterns=[
                    r"^\s*(remember|note|take a note)(?: that)?[:,]?\s+(?P<note>.+)$"
                ],
                handler=_add_note,
                examples=["remember buy milk"],
            ),
            Skill(
                name="list-notes",
                description="List the notes you asked me to keep.",
                patterns=[r"\b(list|show|read)( me)?( my)? notes\b"],
                handler=_list_notes,
                examples=["list my notes"],
            ),
            Skill(
                name="clear-notes",
                description="Forget every stored note.",
                patterns=[r"\b(clear|delete|forget)( all)?( my)? notes\b"],
                handler=_clear_notes,
                examples=["clear my notes"],
            ),
            Skill(
                name="help",
                description="List everything I can do.",
                patterns=[r"^\s*(help|what can you do)\b"],
                handler=_help,
                examples=["help"],
            ),
            Skill(
                name="farewell",
                description="Say goodbye.",
                patterns=[r"^\s*(bye|goodbye|see you)\b"],
                handler=_farewell,
                examples=["goodbye"],
            ),
        ]
    )
