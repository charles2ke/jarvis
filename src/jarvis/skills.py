"""Skill definitions and the default Jarvis skill set."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from typing import Callable, Iterable, List, Match, Optional, Pattern, Sequence

from jarvis import encyclopedia, knowledge, signlanguage, sketch, traffic
from jarvis.atlas import (
    City,
    Country,
    EVENTS,
    cities_in,
    countries_in,
    describe,
    describe_event,
    describe_wonder,
    display_name,
    events_in_year,
    find_by_capital,
    find_city,
    find_continent,
    find_country,
    find_event,
    find_wonder,
    find_wonder_category,
    format_population,
    sentence,
    timezone_for_country,
    wonders_in,
)
from jarvis.braille import (
    BrailleError,
    alphabet_chart,
    is_braille,
    read_braille,
    write_braille,
)
from jarvis.calculator import CalculationError, calculate
from jarvis.cloud import CloudSessionError, ask_cloud
from jarvis.cua import CuaError, actions_chart as cua_actions_chart, execute as cua_execute
from jarvis import maritime
from jarvis.memory import Memory
from jarvis.nl import number_to_words, words_to_number
from jarvis.science import solve_problem
from jarvis.speech import SpeechError, speak


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


def _number_words(match: Match[str], context: SkillContext) -> str:
    groups = {
        name: value for name, value in match.groupdict().items() if value is not None
    }
    digits = next(
        (value for name, value in groups.items() if name.startswith("to_words")), None
    )
    if digits is not None:
        try:
            return f"{int(digits)} in words is {number_to_words(int(digits))}."
        except ValueError as exc:
            return str(exc)
    words = next(
        (value for name, value in groups.items() if name.startswith("to_digits")), ""
    ).strip()
    value = words_to_number(words)
    if value is None:
        return (
            "I could not read that as a number. Try 'forty-two in digits' or "
            "'spell out 42'."
        )
    return f"{words} in digits is {value}."


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


_KNOWLEDGE_TAIL = re.compile(
    r"\s+(?:as|to|into|in)\s+(?:a|an|my|your|the)?\s*(?:new\s+)?"
    r"(?:knowledge|reference)\s+(?:source|sources|base)\b.*$",
    re.IGNORECASE,
)


def _clean_location(raw: str) -> str:
    location = _KNOWLEDGE_TAIL.sub("", (raw or "").strip())
    return location.strip().strip("'\"").rstrip(".,;:")


def _stored_sources(context: SkillContext) -> List[knowledge.Source]:
    return knowledge.load(context.memory.get(knowledge.MEMORY_KEY, []))


def _remember_source(context: SkillContext, source: knowledge.Source) -> int:
    sources = [
        existing
        for existing in _stored_sources(context)
        if existing.location != source.location
    ]
    sources.append(source)
    context.memory.set(knowledge.MEMORY_KEY, knowledge.dump(sources))
    return len(sources)


def _added_reply(source: knowledge.Source, total: int) -> str:
    words = len(source.text.split())
    what = "file" if source.kind == "file" else "website"
    return (
        f"Added the {what} '{source.title}' as a knowledge source "
        f"({words} words from {source.location}). You now have {total} "
        f"knowledge source(s); ask me about anything in it."
    )


def _add_knowledge_file(
    match: Match[str],
    context: SkillContext,
    *,
    reader: Optional[Callable[[str], knowledge.Source]] = None,
) -> str:
    path = _clean_location(match.groupdict().get("path") or "")
    if not path:
        return (
            "Which file should I read? Try 'add the file ~/notes.md as a "
            "knowledge source'."
        )
    try:
        source = (reader or knowledge.add_file)(path)
    except knowledge.KnowledgeError as exc:
        return str(exc)
    return _added_reply(source, _remember_source(context, source))


def _add_knowledge_website(
    match: Match[str],
    context: SkillContext,
    *,
    fetcher: Optional[Callable[[str], knowledge.Source]] = None,
) -> str:
    url = _clean_location(match.groupdict().get("url") or "")
    if not url:
        return (
            "Which website should I read? Try 'add https://example.com as a "
            "knowledge source'."
        )
    try:
        source = (fetcher or knowledge.add_website)(url)
    except knowledge.KnowledgeError as exc:
        return str(exc)
    return _added_reply(source, _remember_source(context, source))


def _list_knowledge_sources(match: Match[str], context: SkillContext) -> str:
    sources = _stored_sources(context)
    if not sources:
        return (
            "I have no knowledge sources yet. Add one with 'add the file "
            "notes.md as a knowledge source' or 'add https://example.com as a "
            "knowledge source'."
        )
    lines = [f"I have {len(sources)} knowledge source(s):"]
    lines.extend(
        f"{index}. {source.describe()}"
        for index, source in enumerate(sources, start=1)
    )
    return "\n".join(lines)


def _clear_knowledge_sources(match: Match[str], context: SkillContext) -> str:
    sources = _stored_sources(context)
    context.memory.clear(knowledge.MEMORY_KEY)
    if not sources:
        return "There were no knowledge sources to forget."
    return f"Forgot {len(sources)} knowledge source(s)."


def _answer_from_knowledge(context: SkillContext, subject: str) -> Optional[str]:
    found = knowledge.search(_stored_sources(context), subject)
    if found is None:
        return None
    source, passages = found
    body = " ".join(passages)
    return f"From {source.title} ({source.location}): {body}"


_MOOD_REFLECTIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("anxious", "anxiety", "nervous", "worried", "panicked", "panic", "scared", "afraid"),
        "Anxiety can make everything feel urgent at once. Let's slow it down: "
        "what is the worry that feels loudest right now?",
    ),
    (
        ("sad", "depressed", "down", "unhappy", "miserable", "hopeless", "empty"),
        "I am sorry you are carrying that heaviness. How long has it been "
        "sitting with you, and is there anything that briefly lifts it?",
    ),
    (
        ("angry", "furious", "mad", "irritated", "frustrated", "annoyed"),
        "Anger usually points at something that matters to you. What feels "
        "unfair or out of your control right now?",
    ),
    (
        ("stressed", "overwhelmed", "burned out", "burnt out", "exhausted", "tired", "drained"),
        "That sounds like a lot to hold at once. If you could set down one of "
        "those demands today, which would it be?",
    ),
    (
        ("lonely", "alone", "isolated", "ignored", "abandoned"),
        "Feeling unseen is genuinely painful. Who in your life feels even a "
        "little safe to reach out to this week?",
    ),
    (
        ("guilty", "ashamed", "shame", "embarrassed", "worthless", "failure"),
        "You are being hard on yourself. What would you say to a friend who "
        "told you the same thing about themselves?",
    ),
    (
        ("happy", "great", "good", "better", "grateful", "relieved", "excited", "calm"),
        "That is good to hear. What contributed to it, so we can notice what "
        "helps you feel this way?",
    ),
)

_PSYCHIATRIST_DISCLAIMER = (
    "I am not a therapist, but I am here to listen."
)


def _reflection_for(feeling: str) -> str:
    lowered = feeling.lower()
    for keywords, reflection in _MOOD_REFLECTIONS:
        if any(re.search(rf"\b{re.escape(keyword)}\b", lowered) for keyword in keywords):
            return reflection
    return (
        "Thank you for telling me. What has been feeding that feeling lately?"
    )


def _psychiatrist(match: Match[str], context: SkillContext) -> str:
    groups = match.groupdict()
    feeling = (groups.get("feeling") or "").strip().rstrip(".!?")
    entries = context.memory.get_session("mood_log", [])
    if feeling:
        entries = context.memory.append_session(
            "mood_log",
            {"feeling": feeling, "at": context.now().isoformat(timespec="minutes")},
        )
        opening = f"It sounds like you are feeling {feeling}."
    else:
        opening = "I am listening, and this is a safe place to think out loud."
    lines = [opening, _reflection_for(feeling)]
    if len(entries) > 1:
        lines.append(
            f"We have talked about your mood {len(entries)} times now; say "
            "'how have I been feeling' to review it."
        )
    lines.append(_PSYCHIATRIST_DISCLAIMER)
    return " ".join(lines)


def _mood_history(match: Match[str], context: SkillContext) -> str:
    entries = context.memory.get_session("mood_log", [])
    if not entries:
        return "You have not shared how you are feeling yet. Try: 'I feel anxious'."
    lines = [
        f"{index}. {entry.get('at', 'unknown time')} — {entry.get('feeling', 'unspecified')}"
        for index, entry in enumerate(entries, start=1)
    ]
    return "Here is what you have shared with me:\n" + "\n".join(lines)


def _clear_mood_history(match: Match[str], context: SkillContext) -> str:
    context.memory.clear_session("mood_log")
    return "I have cleared your mood history."


_COPING_SUGGESTIONS: tuple[str, ...] = (
    "Try a slow breath in for four counts and out for six; it tells your body "
    "the danger has passed.",
    "Name one small thing you can do in the next ten minutes — a glass of "
    "water, a short walk, opening a window.",
    "Write down the thought that keeps circling. On paper it is usually "
    "smaller than it feels.",
    "Reach out to one person today, even with a single message. Connection "
    "does a lot of the heavy lifting.",
    "Give yourself permission to do less today. Rest is not a reward you have "
    "to earn.",
)


def _next_suggestion(context: SkillContext) -> str:
    index = context.memory.get("support_tip_index", 0)
    if not isinstance(index, int) or index < 0:
        index = 0
    context.memory.set("support_tip_index", (index + 1) % len(_COPING_SUGGESTIONS))
    return _COPING_SUGGESTIONS[index % len(_COPING_SUGGESTIONS)]


def _emotional_support(match: Match[str], context: SkillContext) -> str:
    name = context.memory.get("user_name")
    address = f" {name}" if name else ""
    return (
        f"I am here with you{address}, and what you are going through sounds "
        "genuinely hard. You do not have to hold it together on your own right "
        f"now. {_next_suggestion(context)} "
        "Tell me more whenever you are ready — I am listening."
    )


_LOVE_REFLECTIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "broke up",
            "break up",
            "breakup",
            "broken up",
            "heartbroken",
            "heartbreak",
            "dumped",
            "left me",
            "divorce",
            "ex",
        ),
        "Losing a relationship is real grief, and it rarely heals in a straight "
        "line. What do you miss most — the person, or the future you had "
        "pictured with them?",
    ),
    (
        (
            "fight",
            "fighting",
            "argue",
            "argued",
            "arguing",
            "argument",
            "conflict",
            "not talking",
            "jealous",
            "cheated",
            "betrayed",
            "trust",
        ),
        "Conflict with someone you love hurts because the relationship matters. "
        "What is the need underneath the argument that you have not been able "
        "to say out loud yet?",
    ),
    (
        (
            "crush",
            "in love",
            "falling for",
            "ask out",
            "asking out",
            "confess",
            "tell them how i feel",
            "date",
            "dating",
            "rejected",
            "rejection",
            "unrequited",
        ),
        "New feelings are exciting and exposing at the same time. What would "
        "you want them to know about you if fear of rejection were not in the "
        "room?",
    ),
    (
        (
            "lonely",
            "alone",
            "single",
            "unloved",
            "nobody loves me",
            "no one loves me",
        ),
        "Wanting to be loved is one of the most human things there is, not a "
        "weakness. Where in your life do you already feel even a little "
        "cared for?",
    ),
)

_LOVE_DEFAULT_REFLECTION = (
    "Love asks a lot of us. What matters most to you about this relationship "
    "right now?"
)

_LOVE_CLOSING = (
    "Whatever you decide, you deserve to be treated with respect — including "
    "by yourself."
)


def _love_support(match: Match[str], context: SkillContext) -> str:
    text = match.string.lower()
    reflection = _LOVE_DEFAULT_REFLECTION
    for keywords, candidate in _LOVE_REFLECTIONS:
        if any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords):
            reflection = candidate
            break
    return " ".join(
        [
            "Thank you for trusting me with something this personal.",
            reflection,
            _LOVE_CLOSING,
        ]
    )


ROLE_MODEL_LINES: Sequence[str] = (
    "A role model is not someone flawless; it is someone whose habits you would "
    "be glad to copy. Name one person you admire and the single habit of theirs "
    "you could borrow this week.",
    "The version of you that other people look up to is built out of ordinary "
    "choices: showing up, telling the truth, finishing what you start. Which of "
    "those three needs your attention right now?",
    "Character is what you do when it costs you something. What is one value you "
    "want to hold on to even when it is inconvenient?",
    "If someone followed you around for a week, what would they conclude you "
    "care about? If that answer is not the one you want, we can change one habit "
    "at a time.",
)


COACH_PROMPTS: Sequence[str] = (
    "What does 'done' look like? Describe the finish line in one sentence.",
    "What is the smallest next step you could take in the next 24 hours?",
    "What has got in the way before, and how will you handle it this time?",
    "When exactly will you do it, and who will you tell about it?",
)


SELF_CARE_IDEAS: Sequence[str] = (
    "Start with the basics: water, food, and somewhere comfortable to sit. Care "
    "is usually physical before it is profound.",
    "Protect one small block of time today that belongs to nobody else — even "
    "fifteen minutes counts.",
    "Sleep is the cheapest repair tool you own. What would make tonight's rest "
    "a little easier?",
    "Move your body gently: a short walk, a stretch, stepping outside for fresh "
    "air. It resets more than it should be able to.",
    "Say no to one thing this week. Boundaries are a form of looking after "
    "yourself, not a failure of generosity.",
)


def _role_model(match: Match[str], context: SkillContext, *, line: Callable[[], str]) -> str:
    return (
        f"I will hold the bar high with you{_addressed(context)}. "
        f"{line()} "
        "Answer it for yourself now — naming it plainly is what turns it into a choice."
    )


def _coach(match: Match[str], context: SkillContext, *, prompt: Callable[[], str]) -> str:
    groups = match.groupdict()
    goal = (groups.get("goal") or "").strip().rstrip(".!?")
    if goal:
        opening = f"Good — let's make '{goal}' concrete."
    else:
        opening = "I am in your corner. Let's turn this into something you can act on."
    return (
        f"{opening} "
        f"{prompt()} "
        "Answer that and we will build the next step from it."
    )


def _self_care(match: Match[str], context: SkillContext, *, idea: Callable[[], str]) -> str:
    return (
        f"Looking after yourself counts as useful work{_addressed(context)}, not "
        "an indulgence. "
        f"{idea()} "
        "Pick one thing and let it be enough for today."
    )


SCIENCE_HELP = (
    "I can work through maths, physics, chemistry and biology problems. Try:\n"
    "- solve 2x + 3 = 11\n"
    "- solve x^2 - 5x + 6 = 0\n"
    "- calculate the force with mass 5 kg and acceleration 2 m/s^2\n"
    "- what is the molar mass of Ca(OH)2\n"
    "- how many moles are in 36 g of H2O\n"
    "- what is the pH of 0.001 M solution\n"
    "- what is the complement of ATGC\n"
    "- transcribe ATGC\n"
    "- translate the RNA AUGGCC\n"
    "- punnett square for Aa x Aa"
)


def _science(match: Match[str], context: SkillContext) -> str:
    answer = solve_problem(match.string)
    if answer:
        return answer
    return SCIENCE_HELP


BRAILLE_HELP = (
    "I read and write Grade 1 braille. Try:\n"
    "- read braille ⠓⠑⠇⠇⠕\n"
    "- write hello in braille\n"
    "- braille alphabet"
)


def _braille_alphabet(match: Match[str], context: SkillContext) -> str:
    return f"The Grade 1 braille alphabet:\n{alphabet_chart()}"


def _braille(match: Match[str], context: SkillContext) -> str:
    payload = (match.group("braille_text") or "").strip().strip('"“”')
    if not payload:
        return BRAILLE_HELP
    try:
        if is_braille(payload):
            return f"That braille reads: {read_braille(payload)}"
        return f"In braille that is: {write_braille(payload)}"
    except BrailleError as error:
        return str(error)


_MIDLIFE_REFLECTIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("career", "job", "work", "promotion", "retire", "retirement", "quit"),
        "Work often carries more of our identity than we admit. If the job "
        "title disappeared tomorrow, what would you still want to be known "
        "for?",
    ),
    (
        ("regret", "wasted", "too late", "missed", "should have", "behind"),
        "Regret usually marks something you still care about. What would "
        "honouring that value look like from where you actually stand today?",
    ),
    (
        ("meaning", "purpose", "point", "pointless", "empty", "stuck", "rut"),
        "A life can be full and still feel hollow. What did you used to do "
        "that made time disappear, and what stopped it?",
    ),
    (
        (
            "old",
            "older",
            "aging",
            "ageing",
            "age",
            "body",
            "health",
            "mortality",
            "dying",
            "grey",
            "gray",
        ),
        "Noticing time passing is unsettling, and it is also honest. What "
        "would you like the next ten years to be about, rather than away from?",
    ),
    (
        ("kids", "children", "son", "daughter", "empty nest", "parents", "mother", "father"),
        "Midlife often means holding other people's needs at both ends. "
        "Where in all of that is there any space left for you?",
    ),
)

_MIDLIFE_DEFAULT_REFLECTION = (
    "This stage asks hard questions: what you have built, what you still want, "
    "and what you are willing to change. Which of those is loudest for you "
    "right now?"
)

_MIDLIFE_CLOSING = (
    "A midlife reckoning is not a breakdown; it is usually a signal worth "
    "listening to. I am not a counsellor, so if it keeps weighing on you, a "
    "therapist can help you work through it properly."
)


def _midlife_counseling(match: Match[str], context: SkillContext) -> str:
    text = match.string.lower()
    reflection = _MIDLIFE_DEFAULT_REFLECTION
    for keywords, candidate in _MIDLIFE_REFLECTIONS:
        if any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords):
            reflection = candidate
            break
    return " ".join(
        [
            f"Thank you for saying that out loud{_addressed(context)}.",
            reflection,
            _MIDLIFE_CLOSING,
        ]
    )


_CAREER_REFLECTIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "fired",
            "laid off",
            "layoff",
            "layoffs",
            "redundant",
            "redundancy",
            "lost my job",
            "let go",
            "unemployed",
            "out of work",
        ),
        "Losing a job shakes far more than income — it touches identity and "
        "routine too. What kind of work would feel worth rebuilding towards, "
        "rather than just the fastest way back in?",
    ),
    (
        (
            "quit",
            "resign",
            "resigning",
            "leave my job",
            "leaving my job",
            "new job",
            "job offer",
            "offer",
            "change careers",
            "changing careers",
            "career change",
            "switch careers",
            "career switch",
            "change jobs",
            "changing jobs",
            "switch jobs",
        ),
        "Big career moves are easier to judge when the trade-offs are explicit. "
        "What would you gain in the first year, and what would you be giving up "
        "that actually matters to you?",
    ),
    (
        (
            "burned out",
            "burnt out",
            "burnout",
            "overworked",
            "hate my job",
            "hate my boss",
            "my boss",
            "manager",
            "toxic",
            "workload",
            "overtime",
        ),
        "Work that drains you is information, not a personal failing. Which part "
        "is the job itself, and which part is the environment or the people "
        "around it?",
    ),
    (
        (
            "promotion",
            "promoted",
            "raise",
            "salary",
            "pay",
            "negotiate",
            "negotiating",
            "performance review",
            "review",
            "stuck",
            "growth",
        ),
        "Progression usually rewards evidence more than effort. What have you "
        "delivered recently that the people deciding would recognise, and who "
        "needs to hear about it?",
    ),
    (
        (
            "interview",
            "interviewing",
            "resume",
            "cv",
            "cover letter",
            "applying",
            "application",
            "applications",
            "job search",
            "job hunting",
            "rejected",
            "rejection",
        ),
        "Job hunting is a numbers game with a bruising feedback loop. Which "
        "single step — the CV, the outreach or the interview itself — is losing "
        "you the most opportunities right now?",
    ),
    (
        (
            "what should i do with my life",
            "career path",
            "direction",
            "purpose",
            "passion",
            "study",
            "degree",
            "major",
            "internship",
            "graduate",
            "first job",
        ),
        "Direction rarely arrives as a single revelation; it usually shows up as "
        "a pattern. Which tasks have left you energised rather than depleted, "
        "whatever the job title was?",
    ),
)

_CAREER_DEFAULT_REFLECTION = (
    "Work takes up a lot of a life, so it is worth thinking about carefully. "
    "What would a good outcome here look like six months from now?"
)

_CAREER_CLOSING = (
    "I can help you think it through, though a mentor or someone in the field "
    "will know the specifics better than I do."
)


def _career_counselling(match: Match[str], context: SkillContext) -> str:
    text = match.string.lower()
    reflection = _CAREER_DEFAULT_REFLECTION
    for keywords, candidate in _CAREER_REFLECTIONS:
        if any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords):
            reflection = candidate
            break
    return " ".join(
        [
            f"Thanks for talking this through with me{_addressed(context)}.",
            reflection,
            _CAREER_CLOSING,
        ]
    )


_COUPLES_REFLECTIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("affair", "cheated", "cheating", "unfaithful", "betrayed", "betrayal", "trust"),
        "Broken trust needs more than an apology; it needs consistent, "
        "visible repair over time. Are you both willing to do that work, and "
        "what would honesty have to look like day to day?",
    ),
    (
        (
            "communicate",
            "communication",
            "talk",
            "talking",
            "listen",
            "listening",
            "shouting",
            "fight",
            "fighting",
            "argue",
            "arguing",
            "argument",
            "silent treatment",
        ),
        "Most couples argue about the argument, not the issue. Try each "
        "taking a turn to say what you need without naming what the other "
        "did wrong — what would your sentence be?",
    ),
    (
        ("money", "finances", "chores", "housework", "in-laws", "parenting", "kids", "children"),
        "Recurring practical fights are usually about fairness and feeling "
        "carried. Where do you each feel the load is uneven, and what is one "
        "concrete swap you could try this week?",
    ),
    (
        ("intimacy", "sex", "distant", "roommates", "disconnected", "drifted", "apart", "lonely"),
        "Drifting apart rarely happens in one moment; it happens in a hundred "
        "small missed turns. When did you last feel close, and what was "
        "different then?",
    ),
    (
        ("divorce", "separate", "separating", "separation", "leave", "leaving", "end it", "break up"),
        "Deciding whether to stay is one of the heaviest choices there is. "
        "What would need to change for staying to feel right, and is that "
        "change something you both want?",
    ),
)

_COUPLES_DEFAULT_REFLECTION = (
    "Counselling usually starts with each partner naming what they need "
    "rather than what the other is doing wrong. If you each had one sentence, "
    "what would yours be?"
)

_COUPLES_CLOSING = (
    "I can help you think it through, but a trained couples therapist is the "
    "right place for this. Whatever you decide, both of you deserve to feel "
    "safe and respected."
)

_RELATIONSHIP_SAFETY_PATTERN = re.compile(
    r"\b(abuse[ds]?|abusive|coerc(?:e[ds]?|ion|ive)|hit(?:s|ting)?|"
    r"threaten(?:s|ed|ing)?|unsafe|violen(?:ce|t))\b"
)

_RELATIONSHIP_SAFETY_RESPONSE = (
    "Your immediate safety comes first. If you are in immediate danger, move "
    "to a safe place and contact local emergency services. Please seek "
    "individual support from a trusted person or domestic-abuse service; "
    "couples therapy may not be safe while abuse or coercion is present."
)


def _couples_counseling(match: Match[str], context: SkillContext) -> str:
    text = match.string.lower()
    if _RELATIONSHIP_SAFETY_PATTERN.search(text):
        return _RELATIONSHIP_SAFETY_RESPONSE
    reflection = _COUPLES_DEFAULT_REFLECTION
    for keywords, candidate in _COUPLES_REFLECTIONS:
        if any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords):
            reflection = candidate
            break
    return " ".join(
        [
            "Thank you for bringing this here — wanting to work on it together "
            "already says something.",
            reflection,
            _COUPLES_CLOSING,
        ]
    )


_ENCYCLOPEDIA_FILLERS = re.compile(
    r"^(?:the meaning of|the definition of|the term|the word|me about|us about|about)\s+",
    re.IGNORECASE,
)


def _clean_subject(subject: str) -> str:
    cleaned = subject.strip()
    cleaned = re.sub(r"^(?:please|hey|ok|okay)[,\s]+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s,]+please$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip().strip("\"'")
    cleaned = _ENCYCLOPEDIA_FILLERS.sub("", cleaned)
    return cleaned.strip().rstrip("?!.").strip()


def _world_knowledge(subject: str) -> Optional[str]:
    """Return an atlas or traffic answer for ``subject``, if there is one."""

    wonder = find_wonder(subject)
    if wonder is not None:
        return describe_wonder(wonder)
    event = find_event(subject)
    if event is not None:
        return describe_event(event)
    city = find_city(subject)
    if city is not None:
        return _describe_city(city)
    sign = traffic.find_sign(subject)
    if sign is not None:
        return traffic.describe_sign(sign)
    return None


def _encyclopedia(match: Match[str], context: SkillContext) -> str:
    subject = _clean_subject(match.group("subject") or "")
    if not subject:
        return (
            "What would you like to look up? Try 'tell me about gravity', or ask "
            "for 'encyclopedia topics'."
        )
    article = encyclopedia.lookup(subject)
    if article is not None:
        return f"{article.title}: {article.summary}"
    from_world = _world_knowledge(subject)
    if from_world is not None:
        return from_world
    from_sources = _answer_from_knowledge(context, subject)
    if from_sources is not None:
        return from_sources
    lines = [f"I do not have an encyclopedia entry for '{subject}' yet."]
    close = encyclopedia.suggestions(subject)
    if close:
        lines.append("Did you mean: " + ", ".join(close) + "?")
    else:
        lines.append("Say 'encyclopedia topics' to see what I do know.")
    return " ".join(lines)


def _encyclopedia_topics(match: Match[str], context: SkillContext) -> str:
    titles = encyclopedia.topics()
    lines = [f"I have {len(titles)} encyclopedia entries:"]
    lines.extend(f"- {title}" for title in titles)
    lines.append("Ask me 'what is gravity?' or 'tell me about Ada Lovelace'.")
    return "\n".join(lines)


def _gmdss(match: Match[str], context: SkillContext) -> str:
    groups = match.groupdict()
    subject = _clean_subject(groups.get("subject") or "")
    if not subject or _normalised_gmdss(subject) in {"", "gmdss"}:
        entry = maritime.lookup("GMDSS")
        assert entry is not None  # The overview entry is always present.
        return f"{entry.title}: {entry.summary}"
    entry = maritime.lookup(subject)
    if entry is not None:
        return f"{entry.title}: {entry.summary}"
    lines = [f"I do not have a GMDSS entry for '{subject}' yet."]
    close = maritime.suggestions(subject)
    if close:
        lines.append("Did you mean: " + ", ".join(close) + "?")
    else:
        lines.append("Say 'gmdss topics' to see what I do know.")
    return " ".join(lines)


def _normalised_gmdss(subject: str) -> str:
    return re.sub(r"[^a-z]+", "", subject.lower())


def _gmdss_topics(match: Match[str], context: SkillContext) -> str:
    titles = maritime.topics()
    lines = [f"I have {len(titles)} GMDSS entries:"]
    lines.extend(f"- {title}" for title in titles)
    lines.append("Ask me 'what is an EPIRB?' or 'gmdss sea areas'.")
    return "\n".join(lines)


def _answer(
    match: Match[str],
    context: SkillContext,
    *,
    spawn: Optional[Callable[[str], str]] = None,
) -> str:
    query = match.group("query").strip()
    if not query:
        return "Tell me what you would like the cloud session to answer."
    try:
        return (spawn or ask_cloud)(query)
    except CloudSessionError as exc:
        return f"I could not start a cloud session: {exc}"


def _computer_use(
    match: Match[str],
    context: SkillContext,
    *,
    runner: Optional[Callable[[str], str]] = None,
) -> str:
    instruction = (match.group("instruction") or "").strip()
    if not instruction:
        return "Tell me what you would like me to do on the computer."
    try:
        return (runner or cua_execute)(instruction)
    except CuaError as exc:
        return f"I could not use the computer: {exc}"


def _computer_use_actions(match: Match[str], context: SkillContext) -> str:
    return cua_actions_chart()


def _speak(
    match: Match[str],
    context: SkillContext,
    *,
    voice: Optional[Callable[[str], object]] = None,
) -> str:
    text = (match.group("text") or "").strip().strip('"').strip("'")
    if not text:
        return "Tell me what you would like me to say out loud."
    try:
        (voice or speak)(text)
    except SpeechError as exc:
        return f"I could not speak that out loud: {exc}"
    return f"I said out loud: {text}"


_SIGN_TERM_GROUPS = ("term", "term2", "term3", "term4")


_SIGN_OVERVIEW = (
    "Sign languages are full natural languages made with the hands, face and "
    "body; American Sign Language (ASL) has its own grammar and is not signed "
    "English. I know the ASL manual alphabet and a set of everyday signs, all "
    "described in words. Ask me 'how do I sign thank you?', 'fingerspell "
    "Charles' or 'sign language alphabet', and say 'what signs do you know' for "
    "the full list. Descriptions are a starting point — learning from Deaf "
    "teachers and native signers is what makes signing fluent."
)


def _sign_term(match: Match[str]) -> str:
    groups = match.groupdict()
    for name in _SIGN_TERM_GROUPS:
        value = groups.get(name)
        if value:
            return _clean_subject(value)
    return ""


def _sign_language(match: Match[str], context: SkillContext) -> str:
    term = _sign_term(match)
    if not term:
        return _SIGN_OVERVIEW
    sign = signlanguage.lookup(term)
    if sign is not None:
        return f"{sign.term.capitalize()} in {signlanguage.LANGUAGE}: {sign.description}"
    shape = signlanguage.letter(term)
    if shape is not None:
        return (
            f"The letter {term.upper()} is fingerspelled as {shape}."
        )
    lines = [f"I do not have a sign for '{term}' yet."]
    close = signlanguage.suggestions(term)
    if close:
        lines.append("Did you mean: " + ", ".join(close) + "?")
    lines.append(
        f"Names and unknown words are fingerspelled — try 'fingerspell {term}'."
    )
    return " ".join(lines)


def _sign_alphabet(match: Match[str], context: SkillContext) -> str:
    lines = [f"The {signlanguage.LANGUAGE} manual alphabet:"]
    lines.extend(f"- {line}" for line in signlanguage.alphabet_lines())
    lines.append("Ask me to 'fingerspell' a word to see it letter by letter.")
    return "\n".join(lines)


def _sign_topics(match: Match[str], context: SkillContext) -> str:
    names = signlanguage.terms()
    lines = [f"I can describe {len(names)} signs:"]
    lines.extend(f"- {name}" for name in names)
    lines.append("Ask me 'how do I sign thank you?' for any of them.")
    return "\n".join(lines)


def _fingerspell(match: Match[str], context: SkillContext) -> str:
    text = _clean_subject(match.group("text") or "")
    if not text:
        return "What would you like me to fingerspell? Try 'fingerspell Charles'."
    spelled, skipped = signlanguage.fingerspell(text)
    if not spelled:
        return (
            f"I can only fingerspell letters and digits, so I cannot spell "
            f"'{text}'."
        )
    lines = [f"Fingerspelling '{text}' in {signlanguage.LANGUAGE}:"]
    for character, shape in spelled:
        if character == "␣":
            lines.append("- (space) pause briefly to mark a word break")
        else:
            lines.append(f"- {character}: {shape}")
    if skipped:
        lines.append("I skipped: " + " ".join(skipped) + ".")
    return "\n".join(lines)


def _sketch_topics(match: Match[str], context: SkillContext) -> str:
    names = sketch.subjects()
    lines = [f"I can sketch {len(names)} things:"]
    lines.extend(f"- {name}" for name in names)
    lines.append("Ask me to 'draw a cat' for any of them.")
    return "\n".join(lines)


def _sketch(match: Match[str], context: SkillContext) -> str:
    groups = match.groupdict()
    subject = ""
    for key in ("subject", "subject2"):
        subject = _clean_subject(groups.get(key) or "")
        if subject:
            break
    if not subject:
        return (
            "What would you like me to sketch? Try 'draw a cat', or ask "
            "'what can you sketch?'."
        )
    drawing = sketch.lookup(subject)
    if drawing is not None:
        return f"Here is my {drawing.subject} sketch:\n{sketch.render(drawing)}"
    close = sketch.suggestions(subject)
    if close:
        return (
            f"I cannot sketch '{subject}' yet. I could draw "
            + " or ".join(close)
            + " instead."
        )
    return (
        f"I cannot sketch '{subject}' yet. Ask me 'what can you sketch?' to "
        "see the gallery."
    )


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


_ATLAS_UNKNOWN = (
    "I do not have {subject} in my atlas yet. Ask me about a country such as "
    "Japan, Brazil or Kenya."
)


def _capitalised(text: str) -> str:
    """Return ``text`` with its first character upper-cased."""

    return text[:1].upper() + text[1:] if text else text


def _atlas_group(match: Match[str], *names: str) -> Optional[str]:
    """Return the first non-empty named group among ``names``."""

    groups = match.groupdict()
    for name in names:
        value = groups.get(name)
        if value:
            stripped = value.strip().strip(".,!?;:")
            if stripped:
                return stripped
    return None


def _atlas_country(subject: str) -> Optional[Country]:
    return find_country(subject)


def _atlas(match: Match[str], context: SkillContext) -> str:
    subject = _atlas_group(match, "capital_city", "capital_city2")
    if subject is not None:
        country = find_by_capital(subject)
        if country is not None:
            return sentence(
                f"{country.capital} is the capital of {display_name(country)}, "
                f"in {country.continent}"
            )
        return _ATLAS_UNKNOWN.format(subject=f"a capital called '{subject}'")

    subject = _atlas_group(match, "continent_list")
    if subject is not None:
        continent = find_continent(subject)
        if continent is None:
            return _ATLAS_UNKNOWN.format(subject=f"a continent called '{subject}'")
        countries = countries_in(continent)
        if not countries:
            return f"My atlas has no countries listed for {continent}."
        names = ", ".join(country.name for country in countries)
        return f"Countries I know in {continent}: {names}."

    for keys, describe_country in (
        (
            ("capital_of", "capital_of2"),
            lambda c: sentence(f"The capital of {display_name(c)} is {c.capital}"),
        ),
        (
            ("continent_of", "continent_of2"),
            lambda c: sentence(_capitalised(f"{display_name(c)} is in {c.continent}")),
        ),
        (
            ("currency_of", "currency_of2"),
            lambda c: sentence(_capitalised(f"{display_name(c)} uses the {c.currency}")),
        ),
        (
            ("population_of",),
            lambda c: sentence(
                _capitalised(
                    f"{display_name(c)} has {format_population(c)} (rounded estimate)"
                )
            ),
        ),
        (("about",), lambda c: _capitalised(describe(c))),
    ):
        subject = _atlas_group(match, *keys)
        if subject is None:
            continue
        country = _atlas_country(subject)
        if country is None:
            return _ATLAS_UNKNOWN.format(subject=f"'{subject}'")
        return describe_country(country)

    return (
        "Ask me for a capital, continent, currency or population, for example "
        "'what is the capital of Japan?'."
    )


def _country_name(name: str) -> str:
    """Return ``name`` with the definite article English expects."""

    country = find_country(name)
    return display_name(country) if country is not None else name


def _describe_city(city: City) -> str:
    """Return a one line profile of ``city``."""

    country = find_country(city.country)
    country_name = _country_name(city.country)
    detail = f" {city.note}" if city.note else ""
    return sentence(
        f"{city.name} is in {country_name}"
        f"{f', {country.continent}' if country is not None else ''}. "
        f"It keeps {city.utc_offset} ({city.timezone}).{detail}".rstrip()
    )


_TIMEZONE_HELP = (
    "Ask me for the time zone of a country or a major city, for example "
    "'what time zone is Japan in?' or 'time zone of New York'."
)


def _timezone(match: Match[str], context: SkillContext) -> str:
    subject = _atlas_group(match, "zone_place", "zone_place2")
    if subject is None:
        return _TIMEZONE_HELP

    city = find_city(subject)
    if city is not None:
        return sentence(
            f"{city.name} keeps {city.utc_offset} ({city.timezone}), the time "
            f"zone of {_country_name(city.country)}"
        )

    country = find_country(subject) or find_by_capital(subject)
    if country is not None:
        zone = timezone_for_country(country)
        if zone is not None:
            reply = sentence(
                f"{display_name(country)} keeps {zone.utc_offset} "
                f"({zone.zone}), the time zone of its capital {country.capital}"
            )
            return f"{reply} {zone.note}".strip() if zone.note else reply

    return (
        f"I do not have a time zone for '{subject}' yet. {_TIMEZONE_HELP}"
    )


def _cities(match: Match[str], context: SkillContext) -> str:
    subject = _atlas_group(match, "cities_in")
    if subject is None:
        return "Ask me for the major cities of a country I know, such as Japan."
    country = find_country(subject)
    if country is None:
        return _ATLAS_UNKNOWN.format(subject=f"'{subject}'")
    cities = cities_in(country.name)
    names = [country.capital] + [
        city.name for city in cities if city.name != country.capital
    ]
    return (
        f"Cities I know in {display_name(country)}: "
        f"{', '.join(names)} (capital first)."
    )


_WONDERS_HELP = (
    "I know the Seven Wonders of the Ancient World, the New Seven Wonders of "
    "the World and the Seven Natural Wonders of the World. Ask for one of "
    "those lists, or about a single wonder such as Petra."
)


def _wonders(match: Match[str], context: SkillContext) -> str:
    subject = _atlas_group(match, "wonder")
    if subject is not None:
        wonder = find_wonder(subject)
        if wonder is not None:
            return describe_wonder(wonder)

    listing = _atlas_group(match, "wonder_list")
    category = find_wonder_category(listing or match.group(0))
    if category is None:
        if subject is not None:
            return f"'{subject}' is not on my lists of wonders. {_WONDERS_HELP}"
        category = "New Seven Wonders of the World"
    entries = wonders_in(category)
    lines = [f"The {category}:"]
    lines.extend(f"- {wonder.name} ({wonder.location})" for wonder in entries)
    return "\n".join(lines)


_HISTORY_HELP = (
    "Ask me about a major event such as the fall of the Berlin Wall, or say "
    "'what happened in 1969?' or 'list major historical events'."
)


def _history(match: Match[str], context: SkillContext) -> str:
    year_text = _atlas_group(match, "year")
    if year_text is not None:
        try:
            year = int(year_text)
        except ValueError:
            return _HISTORY_HELP
        if _atlas_group(match, "era") in {"BC", "BCE", "bc", "bce"}:
            year = -year
        events = events_in_year(year)
        if not events:
            return f"I have no major event recorded around {year}. {_HISTORY_HELP}"
        lines = [f"Around {year} my history covers:"]
        lines.extend(f"- {describe_event(event)}" for event in events)
        return "\n".join(lines)

    subject = _atlas_group(match, "event")
    if subject is not None:
        event = find_event(subject)
        if event is not None:
            return describe_event(event)
        return f"I do not have '{subject}' in my history yet. {_HISTORY_HELP}"

    lines = ["Major events in world history that I know:"]
    lines.extend(
        f"- {event.name} ({event.period})"
        for event in sorted(
            EVENTS,
            key=lambda event: event.year if event.year is not None else float("inf"),
        )
    )
    lines.append("Ask me about any of them for more detail.")
    return "\n".join(lines)


_TRAFFIC_HELP = (
    "Ask me what a sign means — 'what does a give way sign mean?' — or for a "
    "family of signs such as warning signs, or say 'list traffic signs'."
)


_TRAFFIC_GENERIC = frozenset({"traffic", "road", "street", "the", ""})


def _traffic_overview() -> str:
    lines = [
        "Road signs worldwide come from two families. "
        + traffic.CONVENTIONS["Vienna Convention"],
        traffic.CONVENTIONS["MUTCD"],
        "The families I can explain:",
    ]
    lines.extend(
        f"- {traffic.describe_category(category)}" for category in traffic.CATEGORIES
    )
    lines.append(_TRAFFIC_HELP)
    return "\n".join(lines)


def _traffic(match: Match[str], context: SkillContext) -> str:
    if re.search(r"\btraffic (?:light|lights|signal lights)\b", match.string, re.I):
        return traffic.TRAFFIC_LIGHTS

    subject = _atlas_group(match, "sign", "sign2", "sign3")
    if subject is not None and subject.strip().lower() in _TRAFFIC_GENERIC:
        subject = None
    if subject is not None:
        sign = traffic.find_sign(subject)
        if sign is not None:
            return traffic.describe_sign(sign)
        category = traffic.find_category(subject)
        if category is not None:
            signs = traffic.signs_in(category.name)
            lines = [traffic.describe_category(category)]
            lines.extend(f"- {sign.name}: {sign.meaning}" for sign in signs)
            return "\n".join(lines)
        convention = traffic.find_convention(subject)
        if convention is not None:
            return convention
        close = traffic.suggestions(subject)
        if close:
            return (
                f"I do not know a '{subject}' sign. Did you mean: "
                + ", ".join(close)
                + "?"
            )
        return f"I do not know a '{subject}' sign yet. {_TRAFFIC_HELP}"

    if re.search(r"\b(?:list|show|which|what)\b", match.string, re.I) and re.search(
        r"\bsigns\b", match.string, re.I
    ):
        names = traffic.sign_names()
        lines = [f"I know {len(names)} road signs used around the world:"]
        lines.extend(f"- {name}" for name in names)
        lines.append(_TRAFFIC_HELP)
        return "\n".join(lines)

    return _traffic_overview()


def build_default_registry(memory: Optional[Memory] = None) -> SkillRegistry:
    """Return a registry populated with the built-in Jarvis skills."""

    del memory  # Reserved for skills that need memory at construction time.
    next_story = _rotator(STORIES)
    next_joke = _rotator(JOKES)
    next_uplift = _rotator(UPLIFTS)
    next_idea = _rotator(COPING_IDEAS)
    next_role_model = _rotator(ROLE_MODEL_LINES)
    next_coach_prompt = _rotator(COACH_PROMPTS)
    next_self_care = _rotator(SELF_CARE_IDEAS)
    return SkillRegistry(
        [
            Skill(
                name="crisis-support",
                description=(
                    "Share urgent help lines when you mention self-harm or suicidal thoughts."
                ),
                patterns=[
                    r"\b(?:kill(?:ing)?|harm(?:ing)?|hurt(?:ing)?|cut(?:ting)?) (myself|my self)\b",
                    r"\bkill myself\b",
                    r"\btake my own life\b",
                    r"\bsuicid(e|al)\b",
                    r"\bend(?:ing)? (my life|it all)\b",
                    r"\b(want|going) to die\b",
                    r"\b((no reason|nothing) to live|(?:do not|don't|don’t|dont) want to (live|be here|go on|wake up))\b",
                    r"\bself[- ]harm\b",
                ],
                handler=_crisis_support,
                examples=["I have been thinking about hurting myself"],
            ),
            Skill(
                name="couples-counseling",
                description=(
                    "Work through relationship problems as a couple, the way "
                    "couples counselling would."
                ),
                patterns=[
                    r"\b(couples?|marriage|marital|relationship) (counsel(?:l)?ing|counsel(?:l)?or|therapy|therapist)\b",
                    r"\b(save|fix|work on|repair|rebuild) (our|my|the) (marriage|relationship)\b",
                    r"\b(we|my (husband|wife|partner|spouse|girlfriend|boyfriend) and i) (need|should get|are in) .{0,20}(counsel(?:l)?ing|therapy|(couples?|marriage|marital|relationship) help)\b",
                    r"\bour (marriage|relationship) is (in trouble|failing|falling apart|struggling|broken)\b",
                ],
                handler=_couples_counseling,
                examples=["we need couples counseling"],
            ),
            Skill(
                name="midlife-counseling",
                description=(
                    "Talk through a midlife crisis: ageing, regret, purpose and "
                    "what comes next."
                ),
                patterns=[
                    r"\bmid[- ]?life\b",
                    r"\b(middle[- ]aged?|midlife) (crisis|slump)\b",
                    r"\bhalf (my|his|her|their) life (is )?(over|gone)\b",
                    r"\b(second half|rest) of my life\b",
                    r"\bturning (4\d|5\d|6\d)\b",
                    r"\bis this (all there is|it)\b",
                    r"\bwasted (the best|my best) years\b",
                ],
                handler=_midlife_counseling,
                examples=["I think I am having a midlife crisis"],
            ),
            Skill(
                name="speak",
                description="Read text aloud with the system text to speech voice.",
                patterns=[
                    r"^\s*(?:say|speak|read)\s+(?:this\s+)?(?:out loud|aloud)[:,]?\s+(?P<text>.+)$",
                    r"^\s*(?:say|speak|read)[:,]?\s+(?P<text>.+?)\s+(?:out loud|aloud)\s*[.!]?\s*$",
                    r"^\s*(?:text[- ]to[- ]speech|tts)[:,]?\s+(?P<text>.+)$",
                ],
                handler=_speak,
                examples=["say out loud hello Charles"],
            ),
            Skill(
                name="answer",
                description=(
                    "Answer any query by spawning a GitHub cloud session on this "
                    "repository with the Opus 5 max model."
                ),
                patterns=[
                    r"^\s*answer (?:in (?:plain )?text|as text)[:,]?\s+(?P<query>.+)$",
                    r"^\s*answer(?: me)?(?: this)?[:,]?\s+(?P<query>.+)$",
                    r"^\s*ask (?:the )?(?:cloud|copilot|github)(?: session)?[:,]?\s+(?P<query>.+)$",
                    r"^\s*(?:spawn|start|open) (?:a )?(?:git(?:hub)? )?cloud session(?: on this repo(?:sitory)?)?(?: to answer)?[:,]?\s+(?P<query>.+)$",
                    r"^\s*(?:give|get) me (?:a |the )?(?:plain[- ]?text |text |written )?answer (?:to|for|about)[:,]?\s+(?P<query>.+)$",
                    r"^\s*(?:put|turn) (?:this|the following|it) into text[:,]?\s+(?P<query>.+)$",
                ],
                handler=_answer,
                examples=["answer how does the skill registry resolve matches?"],
            ),
            Skill(
                name="cua-actions",
                description="List the computer use actions Jarvis can plan.",
                patterns=[
                    r"^\s*(?:cua|computer[- ]use)(?: agent)? actions\b",
                    r"^\s*what (?:computer|cua)(?: use)? actions (?:do you know|can you (?:do|plan|take))\b",
                    r"^\s*what can you do on (?:my|the) computer\b",
                ],
                handler=_computer_use_actions,
                examples=["computer use actions"],
            ),
            Skill(
                name="computer-use",
                description=(
                    "Plan, and with your opt-in run, computer use agent actions "
                    "such as opening apps, clicking, typing and pressing keys."
                ),
                patterns=[
                    r"^\s*(?:cua|computer[- ]use(?: agent)?)[:,]?\s+(?P<instruction>.+)$",
                    r"^\s*use (?:my|the) computer (?:to|and)\s+(?P<instruction>.+)$",
                    r"^\s*(?:on|with) (?:my|the) computer[:,]?\s+(?P<instruction>.+)$",
                    r"^\s*(?:control|drive|operate) (?:my|the) computer (?:to|and)\s+(?P<instruction>.+)$",
                    r"^\s*(?:plan|show me) (?:the )?computer use (?:steps |plan )?(?:for|to)[:,]?\s+(?P<instruction>.+)$",
                ],
                handler=_computer_use,
                examples=["use the computer to open Safari then click on Sign in"],
            ),
            Skill(
                name="love-support",
                description=(
                    "Talk through relationships, heartbreak and matters of the heart."
                ),
                patterns=[
                    r"\b(broke up|break ?up|broken up|heartbroken|heartbreak|dumped me|divorc(e|ed|ing))\b",
                    r"\b(my|our) (girlfriend|boyfriend|partner|husband|wife|spouse|fianc(e|ée|é)|ex|marriage|relationship|crush)\b",
                    r"\b(i('m| am)? ?(in love|falling (in love|for))|i have a crush|unrequited)\b",
                    r"\b(love life|dating|romantic|relationship advice|ask (him|her|them) out)\b",
                    r"\b(nobody|no one) loves me\b",
                ],
                handler=_love_support,
                examples=["my girlfriend and I keep fighting"],
            ),
            Skill(
                name="career-counselling",
                description=(
                    "Think through work, job searches and career decisions."
                ),
                patterns=[
                    r"\b(career|vocational) (advice|counsel?ling|coach(ing)?|change|path|move|goals?)\b",
                    r"\b(change|switch(ing)?|changing) careers\b",
                    r"\b(change|switch(ing)?|changing) (jobs?|roles?|positions?)\b",
                    r"\b(i (got|was|am being) (fired|laid off|made redundant|let go))\b",
                    r"\b(lost my job|out of (a )?work|unemployed)\b",
                    r"\b(quit|leave|leaving|resign(ing)?( from)?)( my)? (job|role|position)\b",
                    r"\b(hate|love|stuck in) my (job|work|career|role|boss|manager)\b",
                    r"\b(burned|burnt) out (at|from) (work|my job)\b",
                    r"\bmy (boss|manager) is toxic\b",
                    r"\b(job (search|hunt(ing)?|offer|interview|application))\b",
                    r"\b(rejected for|rejection from) (a |the )?(job|role|position)\b",
                    r"\b(my )?(resume|cv|cover letter)\b",
                    r"\b(ask(ing)? for a (raise|promotion)|get(ting)? promoted|performance review)\b",
                    r"\bnegotiate my (pay|salary|compensation)\b",
                    r"\bwhat should i do with my (life|career)\b",
                ],
                handler=_career_counselling,
                examples=["I am thinking about changing careers"],
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
                name="role-model",
                description="Talk about character, values and the person you want to become.",
                patterns=[
                    r"\brole[- ]?model\b",
                    r"\b(look up to|someone to admire|who should i admire)\b",
                    r"\b(be|become) a better (person|man|woman|human|version of myself)\b",
                    r"\b(what|which) values? (should i|do i want to)\b",
                ],
                handler=partial(_role_model, line=next_role_model),
                examples=["be my role model"],
            ),
            Skill(
                name="coach",
                description="Coach you through goals, habits and staying accountable.",
                patterns=[
                    r"\b(coach me|be my coach|i need a coach)\b",
                    r"\bhold me accountable\b",
                    r"\bhelp me (?:to )?(?:reach|achieve|set|stick to|follow through on) (?P<goal>.+)$",
                    r"\bi want to (?:get better at|learn|achieve|build a habit of) (?P<goal>.+)$",
                    r"\b(my goal is|set a goal|goal setting|stay disciplined|build (a|the) habit)\b",
                ],
                handler=partial(_coach, prompt=next_coach_prompt),
                examples=["coach me"],
            ),
            Skill(
                name="self-care",
                description="Suggest a practical way to take care of yourself.",
                patterns=[
                    r"\bself[- ]?care\b",
                    r"\b(take|taking) care of (myself|me)\b",
                    r"\blook after myself\b",
                    r"\bi (?:keep )?(?:forget|neglect|ignore)(?:ting)? (?:to look after |about )?myself\b",
                ],
                handler=partial(_self_care, idea=next_self_care),
                examples=["how do I take care of myself"],
            ),
            Skill(
                name="mental-health",
                description="Talk through anxiety, low mood or burnout and suggest a coping step.",
                patterns=[
                    r"^\s*i feel (anxious|depressed|overwhelmed)\.?\s*$",
                    r"^\s*i('m| am) (anxious|panicking|depressed|burned out|burnt out|overwhelmed)\.?\s*$",
                    r"\bmental health\b",
                    r"\bpanic attack\b",
                    r"\bcan'?t stop (worrying|overthinking)\b",
                ],
                handler=partial(_mental_health, idea=next_idea),
                examples=["I feel anxious"],
            ),
            Skill(
                name="psychiatrist",
                description=(
                    "Listen with empathy and ask reflective questions about how you feel."
                ),
                patterns=[
                    r"^\s*i(?:'m| am)? ?feel(?:ing)? (?:like |so |really |very )?(?P<feeling>.+)$",
                    r"^\s*i(?:'m| am) (?P<feeling>anxious|nervous|worried|scared|afraid|sad|depressed|down|unhappy|miserable|hopeless|empty|angry|furious|mad|irritated|frustrated|annoyed|stressed|overwhelmed|burned out|burnt out|exhausted|tired|drained|lonely|alone|isolated|guilty|ashamed|embarrassed|worthless)\b.*$",
                    r"\b(i need (someone )?to talk|can we talk about (my )?(feelings|mental health)|talk to a (therapist|psychiatrist))\b",
                ],
                handler=_psychiatrist,
                examples=["I feel anxious about work"],
            ),
            Skill(
                name="clear-mood-history",
                description="Forget everything you told me about your mood.",
                patterns=[
                    r"^\s*(clear|delete|forget)( all)?( my)? (mood|feelings?) (history|log|journal)\s*[.!]?\s*$"
                ],
                handler=_clear_mood_history,
                examples=["clear my mood history"],
            ),
            Skill(
                name="mood-history",
                description="Review the feelings you have shared with me.",
                patterns=[
                    r"\bhow have i been feeling\b",
                    r"\b(mood|feelings?) (history|log|journal)\b",
                ],
                handler=_mood_history,
                examples=["how have I been feeling"],
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
                name="emotional-support",
                description="Offer comfort, encouragement and a coping suggestion.",
                patterns=[
                    r"\b(i need (some )?(emotional )?support|support me|comfort me|cheer me up|encourage me)\b",
                    r"\b(i can'?t (cope|take|handle) (it|this|any ?more)|i('m| am) (not okay|not ok)|falling apart)\b",
                    r"\b(having a (really )?(hard|rough|tough|bad) (time|day|week)|going through a lot)\b",
                ],
                handler=_emotional_support,
                examples=["I need some emotional support"],
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
                name="traffic-signs",
                description=(
                    "Explain road signs, signals and the sign conventions used "
                    "around the world."
                ),
                patterns=[
                    r"\bwhat does (?:the |a |an )?(?P<sign>[^?!]+?)\s+(?:road |traffic )?(?:sign|signal)s?\s+mean\b",
                    r"\bmeaning of (?:the |a |an )?(?P<sign2>[^?!]+?)\s+(?:road |traffic )?(?:sign|signal)s?\b",
                    r"\b(?:tell me about|explain|describe)\s+(?:the |a |an )?(?!(?:asl|american sign language|sign language)\b)(?P<sign3>[^?!]+?)\s+(?:road |traffic )?(?:sign|signal)s?\b",
                    r"\btraffic (?:light|lights)\b",
                    r"\b(?:traffic|road|street) (?:sign|signal|symbol)s?\b",
                    r"\b(?:vienna convention|mutcd)\b",
                ],
                handler=_traffic,
                examples=["what does a give way sign mean?"],
            ),
            Skill(
                name="time-zone",
                description="Give the time zone and UTC offset of a country or city.",
                patterns=[
                    r"\b(?:time ?zone|timezone|utc offset)\s+(?:in|of|for)\s+(?P<zone_place>[^?!]+)",
                    r"\bwhat (?:time ?zone|timezone)\s+(?:is|does)\s+(?P<zone_place2>[^?!]+?)\s+(?:in|on|use|keep|observe)\b",
                    r"\b(?:time ?zone|timezone|utc offset)\b",
                ],
                handler=_timezone,
                examples=["what time zone is Japan in?"],
            ),
            Skill(
                name="wonders",
                description=(
                    "List the ancient, new and natural wonders of the world, or "
                    "describe one of them."
                ),
                patterns=[
                    r"\b(?:what|which) (?:are|were) the (?P<wonder_list>[^?!]*wonders[^?!]*)",
                    r"\bis\s+(?P<wonder>[^?!]+?)\s+(?:a|one of the)\s+wonders?\b",
                    r"\b(?:seven|7|new|ancient|natural) wonders\b",
                    r"\bwonders of (?:the )?(?:world|nature|the ancient world)\b",
                ],
                handler=_wonders,
                examples=["what are the seven wonders of the world?"],
            ),
            Skill(
                name="history",
                description=(
                    "Recall major events in world history, by name or by year."
                ),
                patterns=[
                    r"\bwhat happened in (?:the year )?(?P<year>\d{3,5})(?:\s*(?P<era>bc|bce)\b)?",
                    r"\bwhen (?:did|was|were)\s+(?P<event>[^?!]+?)\s+(?:happen(?:ed)?|start(?:ed)?|begin|began|end(?:ed)?|take place|took place|fall|fell|collapse|occur(?:red)?|founded|signed|invented|discovered|abolished)\b",
                    r"\b(?:major|important|key|big|list) (?:historical events|events in history|world events)\b",
                    r"\b(?:historical events|events in history|world history|history timeline)\b",
                ],
                handler=_history,
                examples=["what happened in 1969?"],
            ),
            Skill(
                name="cities",
                description="List the major cities I know in a country.",
                patterns=[
                    r"\b(?:what|which)\s+(?:major\s+)?cities\s+(?:are\s+)?(?:in|of)\s+(?P<cities_in>[^?!]+)",
                    r"\b(?:list|name|show)(?: me)?(?: the)?\s+(?:major\s+)?cities\s+(?:in|of)\s+(?P<cities_in>[^?!]+)",
                ],
                handler=_cities,
                examples=["what cities are in Japan?"],
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
                name="braille-alphabet",
                description="Show the Grade 1 braille alphabet.",
                patterns=[
                    r"\bbrail(?:le)?\s+(alphabet|chart|letters)\b",
                    r"\b(alphabet|chart)\s+(in|of|for)\s+brail(?:le)?\b",
                ],
                handler=_braille_alphabet,
                examples=["braille alphabet"],
            ),
            Skill(
                name="braille",
                description="Read braille cells aloud or write text in braille.",
                patterns=[
                    r"\b(?:read|decode|interpret|translate)\s+(?:this\s+|the\s+|some\s+)?brail(?:le)?\b[:,]?\s*(?P<braille_text>.*?)\s*[.?!]*$",
                    r"^\s*(?:write|translate|convert|put|spell|say)\s+(?P<braille_text>.+?)\s+(?:in|into|to)\s+brail(?:le)?\s*[.?!]*$",
                    r"^\s*brail(?:le)?\b[:,]?\s*(?P<braille_text>.*)$",
                    r"^\s*(?P<braille_text>[\u2800-\u28ff][\u2800-\u28ff\s]*)[.?!]*\s*$",
                    r"\b(?:what\s+does|what(?:'s| is))\s+(?P<braille_text>[\u2800-\u28ff][\u2800-\u28ff\s]*?)\s*(?:say|mean|read)\b",
                ],
                handler=_braille,
                examples=["read braille ⠓⠑⠇⠇⠕"],
            ),
            Skill(
                name="science-solver",
                description=(
                    "Solve maths, physics, chemistry and biology problems step by step."
                ),
                patterns=[
                    r"^\s*solve\b[^=]*=",
                    r"\bsolve\b.*\b(equation|for [a-z]\b)",
                    r"\b(?:help me with|solve|do)\b.*\b(maths?|mathematics|physics|chemistry|biology)\b.*\bproblem",
                    r"\b(molar|molecular|formula|relative molecular) (mass|weight)\b",
                    r"\bhow many moles\b",
                    r"\bideal gas\b",
                    r"\bpv\s*=\s*nrt\b",
                    r"\bph\b[^\n]*\d",
                    r"\b(reverse )?complement\b",
                    r"\btranscrib(e|ing|ed)\b",
                    r"\bgc content\b",
                    r"\btranslate\b[^\n]*\b(dna|rna|codon|sequence|protein)\b",
                    r"\b(punnett|monohybrid)\b",
                    r"\b(genotype|phenotype|offspring)\b[^\n]*\bcross\b",
                    r"\b(?:find|calculate|compute|work out|what(?:'s| is)|how (?:fast|far|long|much))\b[^\n]*\b(force|weight|kinetic energy|potential energy|momentum|density|voltage|current|resistance|pressure|acceleration|velocity|speed|work done|power)\b[^\n]*\d",
                    r"\bhow (?:fast|far|long)\b[^\n]*\d",
                ],
                handler=_science,
                examples=["solve 2x + 3 = 11"],
            ),
            Skill(
                name="atlas",
                description=(
                    "Answer geography questions about countries, capitals, "
                    "continents, currencies and populations."
                ),
                patterns=[
                    r"\b(?:which|what) country(?:'s|s'| is)?\s*(?:capital is|has the capital)\s+(?P<capital_city>[^?!]+)",
                    r"\b(?P<capital_city2>[^?!]+?)\s+is the capital of (?:which|what) country\b",
                    r"\b(?:which|what)\s+countries\s+(?:are\s+)?(?:in|of|on)\s+(?P<continent_list>[^?!]+)",
                    r"\b(?:list|name|show)(?: me)?(?: the)?\s+countries\s+(?:in|of|on)\s+(?P<continent_list>[^?!]+)",
                    r"\bcapital (?:city )?of\s+(?P<capital_of>[^?!]+)",
                    r"\bwhat(?:'s| is)\s+(?P<capital_of2>[^?!]+?)(?:'s|s')\s+capital\b",
                    r"\b(?:what|which) continent is\s+(?P<continent_of>[^?!]+?)\s+(?:in|on|part of)\b",
                    r"\bcontinent (?:of|for)\s+(?P<continent_of2>[^?!]+)",
                    r"\bcurrency\s+(?:of|in|used in|used by)\s+(?P<currency_of>[^?!]+)",
                    r"\bwhat(?:'s| is)\s+(?P<currency_of2>[^?!]+?)(?:'s|s')\s+currency\b",
                    r"\bpopulation\s+(?:of|in)\s+(?P<population_of>[^?!]+)",
                    r"\btell me about the country\s+(?P<about>[^?!]+)",
                ],
                handler=_atlas,
                examples=["what is the capital of Japan?"],
            ),
            Skill(
                name="number-words",
                description="Spell numbers out in words or turn spelled numbers back into digits.",
                patterns=[
                    r"^\s*(?:spell|write|say)(?:\s+out)?\s+(?:the\s+number\s+)?(?P<to_words>-?\d+)(?:\s+(?:out\s+)?(?:in|as)\s+(?:words|english|text))?\s*[.?!]*\s*$",
                    r"^\s*how\s+do\s+(?:you|i)\s+(?:spell|write|say)\s+(?:the\s+number\s+)?(?P<to_words2>-?\d+)\s*[.?!]*\s*$",
                    r"^\s*(?P<to_words3>-?\d+)\s+(?:in|as)\s+(?:words|english|text)\s*[.?!]*\s*$",
                    r"^\s*(?:convert|write|put|turn|translate)\s+(?P<to_digits>[a-z][a-z\s-]*?)\s+(?:in|into|to)\s+(?:a\s+)?(?:digits?|numbers?|numerals?|figures)\s*[.?!]*\s*$",
                    r"^\s*(?P<to_digits2>[a-z][a-z\s-]*?)\s+(?:in|as)\s+(?:digits|numerals|figures|numbers)\s*[.?!]*\s*$",
                ],
                handler=_number_words,
                examples=["spell out 42", "forty-two in digits"],
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
                name="add-knowledge-website",
                description="Read a website and keep it as a knowledge source.",
                patterns=[
                    r"^\s*(?:add|use|load|index|import|learn\s+from|read|fetch)\s+"
                    r"(?:the\s+|this\s+|a\s+|an\s+|that\s+)?"
                    r"(?:web\s?site|web\s?page|url|link|site|page)\s*"
                    r"(?P<url>[^\s]*)(?:\s+(?:as|to|into)\s+.*)?\s*[.?!]*\s*$",
                    r"^\s*(?:add|use|load|index|import|learn\s+from|read|fetch)\s+"
                    r"(?P<url>(?:[a-z][a-z0-9+.-]*://|www\.)\S+"
                    r"|[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|gov|edu|dev|ai|co|uk)(?:/\S*)?)"
                    r"(?:\s+(?:as|to|into)\s+.*)?\s*[.?!]*\s*$",
                ],
                handler=_add_knowledge_website,
                examples=["add https://example.com as a knowledge source"],
            ),
            Skill(
                name="add-knowledge-file",
                description="Read a local file and keep it as a knowledge source.",
                patterns=[
                    r"^\s*(?:add|use|load|index|import|learn\s+from|read|study)\s+"
                    r"(?:the\s+|this\s+|a\s+|an\s+|my\s+|that\s+)?"
                    r"(?:text\s+|local\s+|markdown\s+)?(?:file|document)\s*"
                    r"(?P<path>[^\s]*)(?:\s+(?:as|to|into)\s+.*)?\s*[.?!]*\s*$",
                    r"^\s*(?:add|use|load|index|import|learn\s+from|read)\s+"
                    r"(?P<path>(?:[~./]|[A-Za-z]:\\)\S*"
                    r"|[\w.-]+(?:/[\w.-]+)+"
                    r"|[\w.-]+\.(?:txt|md|markdown|rst|csv|json|ya?ml|html?|xml|py|log|ini|toml|cfg))"
                    r"(?:\s+(?:as|to|into)\s+.*)?\s*[.?!]*\s*$",
                ],
                handler=_add_knowledge_file,
                examples=["add the file notes.md as a knowledge source"],
            ),
            Skill(
                name="list-knowledge-sources",
                description="List the files and websites I have learned from.",
                patterns=[
                    r"\b(?:list|show)(?:\s+me)?(?:\s+my|\s+your)?\s+knowledge\s+(?:sources|base)\b",
                    r"\bwhat\s+(?:knowledge\s+)?sources\s+do\s+you\s+(?:have|know|use)\b",
                ],
                handler=_list_knowledge_sources,
                examples=["list my knowledge sources"],
            ),
            Skill(
                name="clear-knowledge-sources",
                description="Forget every file and website I have learned from.",
                patterns=[
                    r"^\s*(?:clear|delete|forget|remove)(?:\s+all)?(?:\s+my|\s+your)?\s+"
                    r"knowledge\s+(?:sources|base)\s*[.!?]*\s*$",
                ],
                handler=_clear_knowledge_sources,
                examples=["clear my knowledge sources"],
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
                name="sign-language-alphabet",
                description="Describe the ASL manual alphabet, letter by letter.",
                patterns=[
                    r"\b(?:asl|american sign language|sign language|manual|fingerspelling|finger ?spelling)\s+alphabet\b",
                    r"\balphabet\s+in\s+(?:asl|american sign language|sign language)\b",
                ],
                handler=_sign_alphabet,
                examples=["sign language alphabet"],
            ),
            Skill(
                name="fingerspell",
                description="Fingerspell a word letter by letter in ASL.",
                patterns=[
                    r"\bfinger ?spell(?:ing)?\b[:,]?\s*(?P<text>[^?!]*)",
                    r"\b(?:how (?:do|would) (?:i|you|we) )?spell\s+(?P<text>[^?!]+?)\s+in\s+(?:asl|american sign language|sign language)\b",
                ],
                handler=_fingerspell,
                examples=["fingerspell Charles"],
            ),
            Skill(
                name="sign-language-topics",
                description="List the signs I can describe.",
                patterns=[
                    r"\b(?:what|which)\s+signs\s+do\s+you\s+know\b",
                    r"\b(?:list|show)(?: me)?(?: the| your)?\s+signs\b",
                    r"\b(?:sign language|asl)\s+(?:signs|vocabulary|index|list)\b",
                ],
                handler=_sign_topics,
                examples=["what signs do you know"],
            ),
            Skill(
                name="sign-language",
                description=(
                    "Describe how to make a sign in American Sign Language and "
                    "explain sign language itself."
                ),
                patterns=[
                    r"\bhow (?:do|would|can) (?:i|you|we|someone)\s+sign\b[:,]?\s+(?P<term>[^?!]+)",
                    r"\bhow (?:do|would|can) (?:i|you|we|someone)\s+say\s+(?P<term2>[^?!]+?)\s+in\s+(?:asl|american sign language|sign language)\b",
                    r"\b(?:what(?:'s| is)\s+)?(?:the\s+)?(?:asl\s+)?sign\s+for\s+(?P<term3>[^?!]+)",
                    r"\b(?:sign|signing)\s+(?P<term4>[^?!]+?)\s+in\s+(?:asl|american sign language|sign language)\b",
                    r"\b(?:what(?:'s| is)|explain|tell me about|teach me|learn|understand)\b[^?!]*\b(?:asl|american sign language|sign language)\b",
                ],
                handler=_sign_language,
                examples=["how do I sign thank you?"],
            ),
            Skill(
                name="sketch-topics",
                description="List the things I can sketch.",
                patterns=[
                    r"\b(?:what|which)\s+(?:things\s+)?can\s+you\s+(?:sketch|draw)\b",
                    r"\b(?:sketch|drawing)\s+(?:topics|gallery|list|index|subjects)\b",
                    r"\b(?:list|show)(?: me)?(?: your| the)?\s+(?:sketches|drawings)\b",
                ],
                handler=_sketch_topics,
                examples=["what can you sketch?"],
            ),
            Skill(
                name="sketch",
                description="Draw a small ASCII sketch of something I know.",
                patterns=[
                    r"\b(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:draw|sketch)\s+(?:me\s+)?(?P<subject>[^?!]*)",
                    r"\b(?:draw|sketch)\s+(?:me\s+)?(?:a picture of|an? image of|a sketch of)\s+(?P<subject>[^?!]*)",
                    r"^\s*(?:please\s+)?(?:draw|sketch)\b[:,]?\s*(?P<subject>[^?!]*)",
                    r"\b(?:i want|i'd like|id like|show me)\s+a\s+(?:sketch|drawing)\s+of\s+(?P<subject2>[^?!]*)",
                ],
                handler=_sketch,
                examples=["draw a cat"],
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
            Skill(
                name="gmdss-topics",
                description="List the GMDSS reference entries I can explain.",
                patterns=[
                    r"\bgmdss\s+(topics|entries|index|glossary)\b",
                    r"\b(list|show)( me)?( your)? gmdss\b",
                ],
                handler=_gmdss_topics,
                examples=["gmdss topics"],
            ),
            Skill(
                name="gmdss",
                description=(
                    "Explain the Global Maritime Distress and Safety System: "
                    "sea areas, DSC, EPIRBs, SARTs, NAVTEX and distress calls."
                ),
                patterns=[
                    r"^\s*gmdss\b[:,]?\s*(?P<subject>.*?)\s*[.?!]*\s*$",
                    r"\b(?P<subject>epirbs?|ais[- ]sarts?|sarts?|"
                    r"digital selective calling|dsc|navtex|mmsi|"
                    r"maritime mobile service identity|inmarsat|safetynet|"
                    r"cospas[- ]sarsat|pan[- ]pan|securit[eé]|mayday|cqd|"
                    r"s\.?o\.?s\.?|sea areas?|area a[1-4]|distress alerts?|"
                    r"false alerts?|solas chapter iv|gmdss)\b",
                ],
                handler=_gmdss,
                examples=["what is an EPIRB?"],
            ),
            Skill(
                name="encyclopedia-topics",
                description="List the encyclopedia entries I can explain.",
                patterns=[
                    r"\b(encyclopedi(a|as)|encyclopaedia)\s+(topics|entries|index|articles)\b",
                    r"\b(list|show)( me)?( your)? (encyclopedi(a|as)|encyclopaedia)\b",
                    r"\bwhat (topics|subjects) do you know\b",
                ],
                handler=_encyclopedia_topics,
                examples=["encyclopedia topics"],
            ),
            Skill(
                name="encyclopedia",
                description="Look up a short factual article on a topic I know.",
                patterns=[
                    r"^\s*(?:encyclopedia|encyclopaedia)[:,]?\s+(?P<subject>.+?)\s*[.?!]*\s*$",
                    r"^\s*(?:tell|teach)\s+(?:me|us)\s+(?:more\s+)?about\s+(?P<subject>(?!(?:my|our)\b).+?)\s*[.?!]*\s*$",
                    r"^\s*(?:what|who)(?:'s|’s|'re|s|\s+is|\s+are|\s+was|\s+were)\s+(?P<subject>.+?)\s*[.?!]*\s*$",
                    r"^\s*(?:define|explain|describe)\s+(?P<subject>.+?)\s*[.?!]*\s*$",
                    r"^\s*what does\s+(?P<subject>.+?)\s+mean\s*[.?!]*\s*$",
                    r"^\s*(?:look\s?up|search\s+for)\s+(?P<subject>.+?)\s*[.?!]*\s*$",
                ],
                handler=_encyclopedia,
                examples=["what is gravity?"],
            ),
        ]
    )
