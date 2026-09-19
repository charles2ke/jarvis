"""A small offline encyclopedia used by the ``encyclopedia`` skill.

The knowledge base is intentionally tiny and dependency free: entries are
plain data, looked up by title or alias with a forgiving fallback that
tolerates minor typos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Article:
    """A single encyclopedia entry."""

    title: str
    summary: str
    aliases: Sequence[str] = field(default_factory=tuple)

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.title, *self.aliases)


ARTICLES: Tuple[Article, ...] = (
    Article(
        title="Python",
        summary=(
            "Python is a high-level, general-purpose programming language created "
            "by Guido van Rossum and first released in 1991. It emphasises "
            "readable syntax and significant indentation, and is widely used for "
            "web development, automation, data analysis and machine learning."
        ),
        aliases=("python language", "python programming language"),
    ),
    Article(
        title="Artificial intelligence",
        summary=(
            "Artificial intelligence is the field of building systems that perform "
            "tasks normally associated with human intelligence, such as perception, "
            "reasoning, planning and language use. Modern AI is dominated by "
            "machine learning, where behaviour is learned from data rather than "
            "written by hand."
        ),
        aliases=("ai", "a.i."),
    ),
    Article(
        title="Machine learning",
        summary=(
            "Machine learning is the branch of artificial intelligence in which "
            "programs improve at a task by finding patterns in data. Common "
            "approaches include supervised learning from labelled examples, "
            "unsupervised learning that discovers structure, and reinforcement "
            "learning driven by rewards."
        ),
        aliases=("ml",),
    ),
    Article(
        title="The internet",
        summary=(
            "The internet is a global network of interconnected computer networks "
            "that communicate using the TCP/IP protocol suite. It grew out of "
            "ARPANET in the late 1960s and now carries services such as the World "
            "Wide Web, email and streaming media."
        ),
        aliases=("internet",),
    ),
    Article(
        title="The World Wide Web",
        summary=(
            "The World Wide Web is a system of linked documents and applications "
            "accessed over the internet. Tim Berners-Lee invented it at CERN in "
            "1989, combining HTML, URLs and HTTP so that any page could link to "
            "any other."
        ),
        aliases=("world wide web", "the web", "web", "www"),
    ),
    Article(
        title="Alan Turing",
        summary=(
            "Alan Turing (1912-1954) was a British mathematician and logician who "
            "formalised computation with the Turing machine, helped break the "
            "Enigma cipher at Bletchley Park during the Second World War, and "
            "proposed the imitation game now known as the Turing test."
        ),
        aliases=("turing",),
    ),
    Article(
        title="Ada Lovelace",
        summary=(
            "Ada Lovelace (1815-1852) was an English mathematician who worked with "
            "Charles Babbage on the Analytical Engine. Her notes contain what is "
            "widely considered the first published algorithm intended for a "
            "machine, along with early speculation that such machines could do "
            "more than arithmetic."
        ),
        aliases=("lovelace",),
    ),
    Article(
        title="Marie Curie",
        summary=(
            "Marie Curie (1867-1934) was a Polish-French physicist and chemist who "
            "pioneered research on radioactivity, discovered polonium and radium, "
            "and became the first person to win Nobel Prizes in two different "
            "sciences."
        ),
        aliases=("curie",),
    ),
    Article(
        title="Albert Einstein",
        summary=(
            "Albert Einstein (1879-1955) was a theoretical physicist best known "
            "for the special and general theories of relativity and the "
            "mass-energy equivalence E = mc^2. He received the 1921 Nobel Prize in "
            "Physics for explaining the photoelectric effect."
        ),
        aliases=("einstein",),
    ),
    Article(
        title="The Solar System",
        summary=(
            "The Solar System is the Sun and everything gravitationally bound to "
            "it: eight planets, their moons, dwarf planets such as Pluto, and "
            "countless asteroids and comets. It formed roughly 4.6 billion years "
            "ago from a collapsing cloud of gas and dust."
        ),
        aliases=("solar system",),
    ),
    Article(
        title="The Sun",
        summary=(
            "The Sun is the star at the centre of the Solar System, a ball of hot "
            "plasma about 1.39 million kilometres across. Nuclear fusion in its "
            "core converts hydrogen into helium and supplies nearly all the energy "
            "that drives life and weather on Earth."
        ),
        aliases=("sun",),
    ),
    Article(
        title="Earth",
        summary=(
            "Earth is the third planet from the Sun and the only place life is "
            "known to exist. It is about 4.54 billion years old, roughly 71 per "
            "cent of its surface is water, and its atmosphere of nitrogen and "
            "oxygen shields the surface and moderates temperature."
        ),
        aliases=("the earth", "planet earth"),
    ),
    Article(
        title="The Moon",
        summary=(
            "The Moon is Earth's only natural satellite, about 384,400 kilometres "
            "away. Its gravity drives the ocean tides, it always keeps the same "
            "face turned towards us, and it was first visited by humans during "
            "NASA's Apollo 11 mission in 1969."
        ),
        aliases=("moon",),
    ),
    Article(
        title="Photosynthesis",
        summary=(
            "Photosynthesis is the process by which plants, algae and some "
            "bacteria use light energy to convert carbon dioxide and water into "
            "sugars, releasing oxygen as a by-product. It underpins almost every "
            "food chain on Earth."
        ),
    ),
    Article(
        title="DNA",
        summary=(
            "DNA, or deoxyribonucleic acid, is the molecule that carries genetic "
            "instructions in nearly all living organisms. Its double helix, "
            "described by Watson, Crick, Franklin and Wilkins in 1953, pairs the "
            "bases adenine with thymine and cytosine with guanine."
        ),
        aliases=("deoxyribonucleic acid",),
    ),
    Article(
        title="Gravity",
        summary=(
            "Gravity is the attraction between objects that have mass. Newton "
            "described it as a force falling off with the square of distance; "
            "Einstein's general relativity recast it as the curvature of spacetime "
            "produced by mass and energy."
        ),
    ),
    Article(
        title="Climate change",
        summary=(
            "Climate change refers to long-term shifts in temperature and weather "
            "patterns. Since the industrial revolution the dominant cause has been "
            "human emission of greenhouse gases, chiefly carbon dioxide from "
            "burning fossil fuels, which warms the lower atmosphere and oceans."
        ),
        aliases=("global warming",),
    ),
    Article(
        title="Mount Everest",
        summary=(
            "Mount Everest, on the border of Nepal and Tibet, is the highest "
            "mountain above sea level at about 8,849 metres. Tenzing Norgay and "
            "Edmund Hillary made the first confirmed summit in 1953."
        ),
        aliases=("everest",),
    ),
    Article(
        title="The Great Wall of China",
        summary=(
            "The Great Wall of China is a series of fortifications built and "
            "rebuilt across northern China over roughly two thousand years, most "
            "famously during the Ming dynasty. Together its branches stretch more "
            "than 21,000 kilometres."
        ),
        aliases=("great wall of china", "great wall"),
    ),
    Article(
        title="The Renaissance",
        summary=(
            "The Renaissance was a European cultural movement spanning roughly the "
            "14th to 17th centuries. Beginning in Italy, it revived classical "
            "learning and produced figures such as Leonardo da Vinci, "
            "Michelangelo and Galileo."
        ),
        aliases=("renaissance",),
    ),
    Article(
        title="Leonardo da Vinci",
        summary=(
            "Leonardo da Vinci (1452-1519) was an Italian painter, engineer and "
            "anatomist of the High Renaissance. He painted the Mona Lisa and The "
            "Last Supper and filled notebooks with designs and observations "
            "centuries ahead of their time."
        ),
        aliases=("da vinci", "leonardo"),
    ),
    Article(
        title="William Shakespeare",
        summary=(
            "William Shakespeare (1564-1616) was an English playwright and poet "
            "whose roughly 39 plays and 154 sonnets, including Hamlet, Macbeth and "
            "Romeo and Juliet, remain the most performed works in the English "
            "language."
        ),
        aliases=("shakespeare",),
    ),
    Article(
        title="Democracy",
        summary=(
            "Democracy is a system of government in which political power rests "
            "with the people, exercised directly or through elected "
            "representatives. Its usual hallmarks are free elections, the rule of "
            "law and protection of minority rights."
        ),
    ),
    Article(
        title="The human brain",
        summary=(
            "The human brain is the organ that coordinates thought, emotion, "
            "memory and movement. It contains on the order of 86 billion neurons "
            "communicating through electrical and chemical signals, and consumes "
            "about a fifth of the body's energy."
        ),
        aliases=("human brain", "brain"),
    ),
    Article(
        title="Open source software",
        summary=(
            "Open source software is software released with a licence that lets "
            "anyone read, modify and redistribute the source code. The model is "
            "behind projects such as Linux, Git and Python, and relies on public "
            "collaboration and peer review."
        ),
        aliases=("open source", "free software"),
    ),
)


_STOPWORD_PREFIX = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)


def _normalise(text: str) -> str:
    """Return a comparable form of ``text`` for lookups."""

    cleaned = text.strip().lower()
    cleaned = re.sub(r"[^\w\s'-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _STOPWORD_PREFIX.sub("", cleaned)
    return cleaned


def _build_index(articles: Sequence[Article]) -> Dict[str, Article]:
    index: Dict[str, Article] = {}
    for article in articles:
        for key in article.keys:
            index.setdefault(_normalise(key), article)
    return index


_INDEX: Dict[str, Article] = _build_index(ARTICLES)


def topics() -> List[str]:
    """Return the article titles, alphabetically."""

    return sorted(article.title for article in ARTICLES)


def lookup(query: str) -> Optional[Article]:
    """Return the article matching ``query``, or ``None``.

    Matching is case and punctuation insensitive, understands aliases, and
    falls back to close matches so small typos still resolve.
    """

    key = _normalise(query or "")
    if not key:
        return None
    article = _INDEX.get(key)
    if article is not None:
        return article
    if key.endswith("s") and len(key) > 3:
        article = _INDEX.get(key[:-1])
        if article is not None:
            return article
    close = get_close_matches(key, list(_INDEX), n=1, cutoff=0.82)
    if close:
        return _INDEX[close[0]]
    return None


def suggestions(query: str, limit: int = 3) -> List[str]:
    """Return titles that look similar to ``query``."""

    key = _normalise(query or "")
    if not key:
        return []
    matches = get_close_matches(key, list(_INDEX), n=limit * 2, cutoff=0.5)
    titles: List[str] = []
    for match in matches:
        title = _INDEX[match].title
        if title not in titles:
            titles.append(title)
        if len(titles) == limit:
            break
    return titles
