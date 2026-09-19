"""Skill definitions and the default Jarvis skill set."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from typing import Callable, Iterable, List, Match, Optional, Pattern, Sequence

from jarvis import encyclopedia
from jarvis.atlas import (
    Country,
    countries_in,
    describe,
    display_name,
    find_by_capital,
    find_continent,
    find_country,
    format_population,
    sentence,
)
from jarvis.calculator import CalculationError, calculate
from jarvis.cloud import CloudSessionError, ask_cloud
from jarvis.memory import Memory
from jarvis.science import solve_problem


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
                name="answer",
                description=(
                    "Answer any query by spawning a GitHub cloud session on this "
                    "repository with the Opus 5 max model."
                ),
                patterns=[
                    r"^\s*answer(?: me)?(?: this)?[:,]?\s+(?P<query>.+)$",
                    r"^\s*ask (?:the )?(?:cloud|copilot|github)(?: session)?[:,]?\s+(?P<query>.+)$",
                    r"^\s*(?:spawn|start|open) (?:a )?(?:git(?:hub)? )?cloud session(?: on this repo(?:sitory)?)?(?: to answer)?[:,]?\s+(?P<query>.+)$",
                ],
                handler=_answer,
                examples=["answer how does the skill registry resolve matches?"],
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
                    r"^\s*(?:look\s?up|search\s+for)\s+(?P<subject>.+?)\s*[.?!]*\s*$",
                ],
                handler=_encyclopedia,
                examples=["what is gravity?"],
            ),
        ]
    )
