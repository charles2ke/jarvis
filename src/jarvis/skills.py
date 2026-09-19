"""Skill definitions and the default Jarvis skill set."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
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


STORIES: Sequence[str] = (
    "Once upon a time a lighthouse keeper grew tired of the dark, so every night "
    "he wrote one sentence of a story on a slip of paper and sent it out with the "
    "tide. Years later a ship arrived carrying a book: the sailors had collected "
    "every slip and bound them together. He had been telling a story to the whole "
    "ocean without ever knowing it.",
    "A young inventor built a clock that ran backwards, hoping to recover a wasted "
    "year. It ticked politely for a week, then stopped. Pinned to its pendulum was "
    "a note in her own handwriting: 'Nothing spent on learning is wasted.' She "
    "never worked out when she had written it, so she chose to believe her future "
    "self had.",
    "In a village where everyone whispered, a girl spoke at a normal volume and was "
    "thought terribly rude. One winter the river froze and cracked, and only her "
    "voice carried far enough to warn the houses below. After that the village "
    "learned that the right volume depends entirely on who needs to hear you.",
)


JOKES: Sequence[str] = (
    "Why did the developer go broke? Because he used up all his cache.",
    "I told my computer I needed a break, and it said: 'No problem, I will go to sleep.'",
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "I would tell you a UDP joke, but you might not get it.",
)


UPLIFTS: Sequence[str] = (
    "You have already survived every difficult day so far. That is a perfect record.",
    "Progress is rarely loud. Small, dull, repeated effort is what actually moves things.",
    "You are allowed to be both a work in progress and someone worth being proud of.",
    "Courage is not the absence of doubt; it is doing the next small thing anyway.",
)


COPING_IDEAS: Sequence[str] = (
    "Try box breathing: inhale for four counts, hold for four, exhale for four, hold for four. Repeat four times.",
    "Ground yourself with the 5-4-3-2-1 exercise: name five things you can see, four you can touch, three you can hear, two you can smell and one you can taste.",
    "Step outside for a few minutes, or open a window and let your eyes rest on something far away.",
    "Write down the thought that is looping, then write one kinder sentence you would say to a friend who had it.",
)


def _rotator(options: Sequence[str]) -> Callable[[], str]:
    """Return a callable that walks ``options`` in order, then repeats."""

    state = {"index": 0}

    def next_option() -> str:
        value = options[state["index"] % len(options)]
        state["index"] += 1
        return value

    return next_option


def _addressed(context: SkillContext) -> str:
    name = context.memory.get("user_name")
    return f" {name}" if name else ""


CRISIS_RESPONSE = (
    "I am really glad you told me, and I want you to stay safe. I am a small program, "
    "not a counsellor, so please reach out to someone who can help right now: call or "
    "text 988 in the US and Canada, call 116 123 (Samaritans) in the UK and Ireland, or "
    "find your local line at https://findahelpline.com. If you are in immediate danger, "
    "please contact your local emergency number. Would you like to tell me what has been "
    "happening while you reach out?"
)


def _crisis_support(match: Match[str], context: SkillContext) -> str:
    return CRISIS_RESPONSE


def _mental_health(match: Match[str], context: SkillContext, *, idea: Callable[[], str]) -> str:
    return (
        f"Thank you for telling me{_addressed(context)}. Difficult feelings are real, and "
        "they usually pass more easily when they are shared. "
        f"{idea()} "
        "If this has been going on for a while, talking to a doctor or therapist is a "
        "strong, sensible move — I can keep you company in the meantime."
    )


def _console(match: Match[str], context: SkillContext, *, idea: Callable[[], str]) -> str:
    return (
        f"I am sorry{_addressed(context)}. That sounds genuinely hard, and you are not "
        "overreacting. You do not have to fix it this minute. "
        f"{idea()} "
        "I am here if you want to talk it through, or I can simply keep you company."
    )


def _uplift(match: Match[str], context: SkillContext, *, line: Callable[[], str]) -> str:
    return f"{line()} Ask me again whenever you need another nudge{_addressed(context)}."


def _story(match: Match[str], context: SkillContext, *, tale: Callable[[], str]) -> str:
    return tale()


def _joke(match: Match[str], context: SkillContext, *, gag: Callable[[], str]) -> str:
    return gag()


def build_default_registry(memory: Optional[Memory] = None) -> SkillRegistry:
    """Return a registry populated with the built-in Jarvis skills."""

    del memory  # Reserved for skills that need memory at construction time.
    next_story = _rotator(STORIES)
    next_joke = _rotator(JOKES)
    next_uplift = _rotator(UPLIFTS)
    next_idea = _rotator(COPING_IDEAS)
    return SkillRegistry(
        [
            Skill(
                name="crisis-support",
                description="Share urgent help lines when you mention harming yourself.",
                patterns=[
                    r"\b(kill myself|end my life|take my own life|suicidal|suicide)\b",
                    r"\b(hurt|harm)(ing)? myself\b",
                    r"\bself[- ]harm\b",
                    r"\bwant to die\b",
                    r"\bdon'?t want to (live|be here|go on|wake up)\b",
                ],
                handler=_crisis_support,
                examples=["I have been thinking about hurting myself"],
            ),
            Skill(
                name="mental-health",
                description="Talk through anxiety, low mood or burnout and suggest a coping step.",
                patterns=[
                    r"\bmental health\b",
                    r"\b(anxious|anxiety|panic attack|panicking|depressed|depression|burn(ed|t) out|burnout|overwhelmed)\b",
                    r"\bcan'?t stop (worrying|overthinking)\b",
                ],
                handler=partial(_mental_health, idea=next_idea),
                examples=["I feel anxious"],
            ),
            Skill(
                name="console",
                description="Offer comfort when you are having a hard time.",
                patterns=[
                    r"\b(console|comfort) me\b",
                    r"\bi('m| am) (so |really |very )?(sad|lonely|upset|heartbroken|miserable|crying)\b",
                    r"\bi feel (sad|low|awful|terrible|lonely|empty|hopeless)\b",
                    r"\bi (failed|messed up|screwed up)\b",
                    r"\b(bad|rough|tough|terrible) day\b",
                    r"\bhard time\b",
                ],
                handler=partial(_console, idea=next_idea),
                examples=["I am having a rough day"],
            ),
            Skill(
                name="story",
                description="Tell you a short original story.",
                patterns=[
                    r"\b(tell|read)( me)? (a|an ?other|another) (story|tale)\b",
                    r"\bstory ?time\b",
                ],
                handler=partial(_story, tale=next_story),
                examples=["tell me a story"],
            ),
            Skill(
                name="joke",
                description="Tell you a joke.",
                patterns=[
                    r"\b(tell|say)( me)? (a|an ?other|another) joke\b",
                    r"\bmake me laugh\b",
                    r"\bsay something funny\b",
                ],
                handler=partial(_joke, gag=next_joke),
                examples=["tell me a joke"],
            ),
            Skill(
                name="uplift",
                description="Give you an encouraging nudge.",
                patterns=[
                    r"\b(cheer me up|uplift me|motivate me|inspire me|encourage me|lift my spirits)\b",
                    r"\bneed (some )?(encouragement|motivation|a pick[- ]?me[- ]?up)\b",
                ],
                handler=partial(_uplift, line=next_uplift),
                examples=["cheer me up"],
            ),
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
                patterns=[r"^\s*(clear|delete|forget)( all)?( my)? notes\s*[.!]?\s*$"],
                handler=_clear_notes,
                examples=["clear my notes"],
            ),
            Skill(
                name="help",
                description="List everything I can do.",
                patterns=[
                    r"^\s*(help|what can you do|what are your skills)\b",
                    r"\b(list|show)( me)? your skills\b",
                ],
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
