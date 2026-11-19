#!/usr/bin/env python3
"""Build the Jarvis website for GitHub Pages.

Usage::

    python scripts/build_site.py [--out _site] [--base-url https://example.org/jarvis/]

The page is generated from the live skill registry, so it never drifts from
what the assistant can do: every skill gets a card, the demo terminal shows
real replies and the searchable topics come from the data shipped with the
package. Only the standard library is used.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from jarvis import __version__  # noqa: E402
from jarvis import (  # noqa: E402
    atlas,
    bible,
    emergency,
    encyclopedia,
    finance,
    maritime,
    poetry,
    signlanguage,
    sketch,
    traffic,
    units,
)
from jarvis.assistant import Assistant  # noqa: E402
from jarvis.cloud import DEFAULT_MODEL  # noqa: E402
from jarvis.memory import Memory  # noqa: E402
from jarvis.skills import Skill, build_default_registry  # noqa: E402
from jarvis.style import _QUOTED  # noqa: E402

SITE_DIR = ROOT / "site"
DEFAULT_BASE_URL = "https://charles2ke.github.io/jarvis/"
REPO_URL = "https://github.com/charles2ke/jarvis"
TITLE = "Jarvis · Private, offline-first AI companion for your terminal"
DESCRIPTION = (
    "Jarvis is a free, open-source AI companion for your terminal that works "
    "offline: {skills} skills for wellbeing, maths, science, world facts and "
    "accessibility."
)

#: (id, label, blurb, skills) for every theme, in display order. Every
#: registered skill must appear exactly once; ``tests/test_site.py`` checks it.
CATEGORIES: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    (
        "wellbeing",
        "Wellbeing",
        "Supportive conversations, coaching and crisis help lines.",
        (
            "crisis-support",
            "mental-health",
            "console",
            "psychiatrist",
            "mood-history",
            "clear-mood-history",
            "emotional-support",
            "love-support",
            "couples-counseling",
            "midlife-counseling",
            "career-counselling",
            "role-model",
            "coach",
            "self-care",
            "uplift",
        ),
    ),
    (
        "creativity",
        "Creativity",
        "Conversation, small talk, poems, stories, jokes and ASCII sketches.",
        (
            "greeting",
            "small-talk",
            "thanks",
            "about-jarvis",
            "repeat",
            "farewell",
            "help",
            "joke",
            "story",
            "poetry",
            "poetry-forms",
            "sketch",
            "sketch-topics",
        ),
    ),
    (
        "maths",
        "Maths & science",
        "Arithmetic, percentages, equations, physics, chemistry and conversions.",
        (
            "calculator",
            "percentages",
            "science-solver",
            "unit-conversion",
            "unit-list",
            "number-words",
            "money-math",
        ),
    ),
    (
        "reference",
        "Reference",
        "Countries, time zones, history, road signs, the sea and more.",
        (
            "atlas",
            "cities",
            "time-zone",
            "wonders",
            "history",
            "traffic-signs",
            "encyclopedia",
            "encyclopedia-topics",
            "bible",
            "bible-topics",
            "bible-books",
            "gmdss",
            "gmdss-topics",
            "economics",
            "economics-topics",
            "financial-advisor",
        ),
    ),
    (
        "accessibility",
        "Accessibility",
        "Braille, American Sign Language and text to speech.",
        (
            "braille",
            "braille-alphabet",
            "sign-language",
            "sign-language-alphabet",
            "sign-language-topics",
            "fingerspell",
            "speak",
        ),
    ),
    (
        "memory",
        "Memory",
        "Notes, your name and knowledge sources you own.",
        (
            "remember-name",
            "recall-name",
            "forget-name",
            "add-note",
            "list-notes",
            "search-notes",
            "edit-note",
            "delete-note",
            "clear-notes",
            "add-knowledge-website",
            "add-knowledge-file",
            "list-knowledge-sources",
            "clear-knowledge-sources",
        ),
    ),
    (
        "everyday",
        "Everyday",
        "Time, dates, world clocks, emergency numbers, cloud answers and computer use.",
        (
            "time",
            "date",
            "date-calculator",
            "world-clock",
            "answer",
            "computer-use",
            "cua-actions",
            "emergency-numbers",
            "emergency-call",
            "emergency-text",
            "emergency-share",
        ),
    ),
)

#: Skills shown before a visitor searches or asks for the full list.
FEATURED: Tuple[str, ...] = (
    "emotional-support",
    "poetry",
    "sketch",
    "calculator",
    "unit-conversion",
    "atlas",
    "time-zone",
    "gmdss",
    "braille",
    "sign-language",
    "add-note",
    "emergency-numbers",
)

#: Prompts replayed through the real assistant for the demo terminal. They are
#: deterministic, so repeated builds produce the same page.
DEMO_PROMPTS: Tuple[str, ...] = (
    "calculate 21 * 2",
    "convert 10 km to miles",
    "what time zone is Japan in?",
    "write hello in braille",
    "solve 2x + 3 = 11",
    "draw a cat",
    "what is an EPIRB?",
    "monthly payment on a 250000 mortgage at 5% over 30 years",
    "fingerspell Jarvis",
)

#: Hero suggestions that show off the search.
SUGGESTIONS: Tuple[str, ...] = (
    "braille",
    "time zone",
    "mortgage",
    "Kenya",
    "haiku",
    "GMDSS",
    "anxious",
)


def category_of() -> Dict[str, Tuple[str, str]]:
    """Map each skill name to its ``(category id, label)``."""

    mapping: Dict[str, Tuple[str, str]] = {}
    for cat_id, label, _, names in CATEGORIES:
        for name in names:
            if name in mapping:
                raise ValueError(f"skill {name!r} is listed in two categories")
            mapping[name] = (cat_id, label)
    return mapping


def _singular_units(names: Iterable[str]) -> List[str]:
    known = set(names)
    keep = []
    for name in names:
        if len(name) <= 3 or (name.endswith("s") and name[:-1] in known):
            continue
        keep.append(name)
    return sorted(keep)


def topic_index() -> Dict[str, List[str]]:
    """Topics each data-backed skill knows about, for search and SEO."""

    return {
        "atlas": [c.name for c in atlas.COUNTRIES],
        "cities": sorted(c.name for c in atlas.CITIES),
        "time-zone": sorted(set(atlas.TIMEZONES) | {c.name for c in atlas.CITIES}),
        "wonders": [w.name for w in atlas.WONDERS],
        "history": [e.name for e in atlas.EVENTS],
        "encyclopedia": [a.title for a in encyclopedia.ARTICLES],
        "economics": [e.title for e in finance.ENTRIES],
        "financial-advisor": [g.topic for g in finance.GUIDANCE],
        "gmdss": [e.title for e in maritime.ENTRIES],
        "bible": [t.title for t in bible.TOPICS],
        "bible-books": [b.name for b in bible.BOOKS],
        "traffic-signs": [s.name for s in traffic.SIGNS],
        "sketch": [s.subject for s in sketch.SKETCHES],
        "sign-language": [s.term for s in signlanguage.SIGNS],
        "poetry": list(poetry.FORMS),
        "unit-conversion": _singular_units(units.UNIT_NAMES),
        "emergency-numbers": [n.country for n in emergency.NUMBERS],
    }


def demo_transcripts() -> List[Dict[str, str]]:
    """Run the demo prompts through a throwaway, RAM-only assistant."""

    assistant = Assistant(memory=Memory(None), now=lambda: datetime(2026, 1, 1, 9, 0))
    return [{"prompt": prompt, "reply": assistant.respond(prompt)} for prompt in DEMO_PROMPTS]


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def shell_command(example: str) -> str:
    """The one-shot shell command that asks Jarvis ``example``."""

    return 'jarvis "' + example.replace("\\", "\\\\").replace('"', '\\"') + '"'


#: Words that need special casing in human-readable skill titles.
TITLE_WORDS: Dict[str, str] = {"cua": "CUA", "gmdss": "GMDSS"}
TITLE_OVERRIDES: Dict[str, str] = {"self-care": "Self-care"}


def display_name(name: str) -> str:
    """Turn a skill id such as ``unit-conversion`` into ``Unit conversion``."""

    if name in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[name]
    words = [TITLE_WORDS.get(word, word) for word in name.split("-")]
    if not words[0].isupper():
        words[0] = words[0].capitalize()
    return " ".join(words)


def render_card(
    skill: Skill, cat_id: str, cat_label: str, topics: Sequence[str], featured: bool
) -> str:
    """Render one skill card; all text is HTML-escaped."""

    anchor = f"skill-{skill.name}"
    title = display_name(skill.name)
    examples = "".join(
        '<li><code class="example">{ex}</code>'
        '<button type="button" class="copy" data-copy="{cmd}" '
        'aria-label="Copy command: {cmd}">Copy</button></li>'.format(
            ex=_e(example), cmd=_e(shell_command(example))
        )
        for example in skill.examples
    )
    topic_html = ""
    if topics:
        items = "".join(f"<li>{_e(topic)}</li>" for topic in topics)
        topic_html = (
            f'<details class="topics"><summary>Covers {len(topics)} topics</summary>'
            f'<ul class="topic-list">{items}</ul></details>'
        )
    flag = ' data-featured="true"' if featured else ""
    return (
        f'<article class="card" id="{_e(anchor)}" data-category="{_e(cat_id)}"{flag}>'
        f'<div class="card-top"><span class="badge">{_e(cat_label)}</span>'
        f'<a class="anchor" href="#{_e(anchor)}" aria-label="Link to the {_e(title)} skill">#</a></div>'
        f'<h3 class="card-title">{_e(title)}</h3>'
        f'<p class="card-desc">{_e(skill.description)}</p>'
        f'<ul class="examples" aria-label="Examples">{examples}</ul>'
        f"{topic_html}"
        '<p class="matches" hidden></p>'
        "</article>"
    )


def _chips(counts: Dict[str, int]) -> str:
    total = sum(counts.values())
    chips = [
        '<button type="button" class="chip" data-category="all" aria-pressed="true">'
        f'All <span class="chip-count">{total}</span></button>'
    ]
    for cat_id, label, blurb, _ in CATEGORIES:
        chips.append(
            f'<button type="button" class="chip" data-category="{_e(cat_id)}" '
            f'aria-pressed="false" title="{_e(blurb)}">'
            f'<span class="chip-dot" aria-hidden="true"></span>{_e(label)} '
            f'<span class="chip-count">{counts.get(cat_id, 0)}</span></button>'
        )
    return "".join(chips)


def demo_intro() -> str:
    """The start of an interactive session, mirroring :class:`jarvis.style.Style`."""

    text = Assistant(memory=Memory(None)).greet()
    parts, last = [], 0
    for match in _QUOTED.finditer(text):
        parts.append(_e(text[last:match.start()]))
        parts.append(f"'<span class=\"term-key\">{_e(match.group(1))}</span>'")
        last = match.end()
    greeting = "".join(parts) + _e(text[last:])
    return (
        '<div class="term-intro">'
        '<p class="term-line term-dim"><span class="term-shell">$</span> jarvis</p>'
        '<p class="term-line"><span class="term-brand">\u25c6 Jarvis</span> '
        f'<span class="term-dim">v{_e(__version__)} \u00b7 your personal AI companion</span></p>'
        f'<p class="term-line">{greeting}</p>'
        "</div>"
    )


def _terminal_lines(transcript: Dict[str, str]) -> str:
    """The no-JavaScript rendering of one exchange, laid out like the CLI."""

    return (
        '<p class="term-line"><span class="term-you">you&gt;</span> '
        f'<span class="term-prompt">{_e(transcript["prompt"])}</span></p>'
        '<pre class="term-reply"><span class="term-jarvis">jarvis&gt;</span> '
        f'<span class="term-text">{_e(transcript["reply"])}</span></pre>'
    )


def _json_for_script(data: object) -> str:
    """JSON that is safe inside a ``<script>`` data block."""

    text = json.dumps(data, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def structured_data(base_url: str, skills: Sequence[Skill], description: str) -> Dict[str, object]:
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "SoftwareApplication",
                "@id": base_url + "#app",
                "name": "Jarvis",
                "alternateName": "Jarvis personal AI companion",
                "description": description,
                "url": base_url,
                "applicationCategory": "UtilitiesApplication",
                "operatingSystem": "Windows, macOS, Linux",
                "softwareVersion": __version__,
                "softwareRequirements": "Python 3.10 or newer",
                "downloadUrl": REPO_URL + "/releases/latest",
                "installUrl": REPO_URL + "#quick-start",
                "softwareHelp": {"@type": "CreativeWork", "url": REPO_URL + "#readme"},
                "license": "https://www.gnu.org/licenses/agpl-3.0.html",
                "isAccessibleForFree": True,
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
                "image": base_url + "assets/social-card.png",
                "screenshot": base_url + "assets/social-card.png",
                "featureList": [f"{s.name}: {s.description}" for s in skills],
                "author": {"@type": "Person", "name": "charles2ke", "url": "https://github.com/charles2ke"},
            },
            {
                "@type": "SoftwareSourceCode",
                "@id": base_url + "#source",
                "name": "jarvis",
                "codeRepository": REPO_URL,
                "programmingLanguage": "Python",
                "runtimePlatform": "Python 3.10+",
                "license": "https://www.gnu.org/licenses/agpl-3.0.html",
                "targetProduct": {"@id": base_url + "#app"},
            },
            {
                "@type": "WebSite",
                "@id": base_url + "#website",
                "name": "Jarvis",
                "url": base_url,
                "inLanguage": "en",
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": {"@type": "EntryPoint", "urlTemplate": base_url + "?q={search_term_string}"},
                    "query-input": "required name=search_term_string",
                },
            },
        ],
    }


def _ordered(skills: Sequence[Skill]) -> List[Skill]:
    categories = category_of()
    missing = [s.name for s in skills if s.name not in categories]
    if missing:
        raise ValueError(
            "add these skills to CATEGORIES in scripts/build_site.py: " + ", ".join(missing)
        )
    names = {s.name for s in skills}
    unknown = sorted((set(categories) | set(FEATURED)) - names)
    if unknown:
        raise ValueError("CATEGORIES or FEATURED name unknown skills: " + ", ".join(unknown))
    position = {name: i for i, (_, _, _, group) in enumerate(CATEGORIES) for name in group}
    return sorted(skills, key=lambda s: (position[s.name], CATEGORIES[position[s.name]][3].index(s.name)))


def render_index(base_url: str, skills: Sequence[Skill], built: date) -> str:
    categories = category_of()
    topics = topic_index()
    ordered = _ordered(skills)
    counts: Dict[str, int] = {}
    cards = []
    for skill in ordered:
        cat_id, label = categories[skill.name]
        counts[cat_id] = counts.get(cat_id, 0) + 1
        cards.append(
            render_card(skill, cat_id, label, topics.get(skill.name, ()), skill.name in FEATURED)
        )
    description = DESCRIPTION.format(skills=len(skills))
    transcripts = demo_transcripts()
    suggestions = "".join(
        f'<button type="button" class="suggestion" data-query="{_e(s)}">{_e(s)}</button>'
        for s in SUGGESTIONS
    )
    demo_tabs = "".join(
        f'<li><button type="button" class="demo-tab" data-index="{i}" aria-controls="terminal-body" '
        f'aria-pressed="{"true" if i == 0 else "false"}">{_e(t["prompt"])}</button></li>'
        for i, t in enumerate(transcripts)
    )
    replacements = {
        "title": _e(TITLE),
        "description": _e(description),
        "base_url": _e(base_url),
        "og_image": _e(base_url + "assets/social-card.png"),
        "version": _e(__version__),
        "skill_count": str(len(skills)),
        "featured_count": str(len(FEATURED)),
        "topic_count": f"{sum(len(v) for v in topics.values()):,}",
        "country_count": str(len(emergency.NUMBERS)),
        "chips": _chips(counts),
        "cards": "\n".join(cards),
        "suggestions": suggestions,
        "demo_tabs": demo_tabs,
        "demo_intro": demo_intro(),
        "demo_first": _terminal_lines(transcripts[0]),
        "demo_json": _json_for_script(transcripts),
        "structured_data": _json_for_script(structured_data(base_url, ordered, description)),
        "repo_url": _e(REPO_URL),
        "built": built.isoformat(),
        "built_human": f"{built.day} {built:%B %Y}",
        "cloud_model": _e(DEFAULT_MODEL),
    }
    return fill((SITE_DIR / "index.html").read_text(encoding="utf-8"), replacements)


def fill(template: str, values: Dict[str, str]) -> str:
    """Replace ``{{name}}`` placeholders, refusing to leave any behind."""

    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    if "{{" in out:
        start = out.index("{{")
        raise ValueError(f"unfilled placeholder near: {out[start:start + 40]!r}")
    return out


def skills_json(skills: Sequence[Skill]) -> str:
    categories = category_of()
    topics = topic_index()
    data = {
        "name": "Jarvis",
        "version": __version__,
        "skills": [
            {
                "name": s.name,
                "category": categories[s.name][1],
                "description": s.description,
                "examples": list(s.examples),
                "topics": topics.get(s.name, []),
            }
            for s in _ordered(skills)
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def sitemap(base_url: str, built: date) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{_e(base_url)}</loc><lastmod>{built.isoformat()}</lastmod></url>\n"
        "</urlset>\n"
    )


def robots(base_url: str) -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {base_url}sitemap.xml\n"


def _clear_out_dir(out_dir: Path) -> None:
    """Remove a previous build, refusing anything that does not look like one."""

    out = out_dir.resolve()
    for keep in (ROOT, SITE_DIR, Path.home()):
        keep = keep.resolve()
        if out == keep or out in keep.parents:
            raise ValueError(f"refusing to replace {out_dir}: it holds {keep}")
    if not out.exists():
        return
    if not out.is_dir() or (any(out.iterdir()) and not (out / ".nojekyll").exists()):
        raise ValueError(f"refusing to replace {out_dir}: it is not empty and not a previous site build")
    shutil.rmtree(out)


def build(out_dir: Path, base_url: str = DEFAULT_BASE_URL, built: Optional[date] = None) -> Path:
    """Write the whole site into ``out_dir`` and return it."""

    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"the base URL must be an absolute http(s) URL, not {base_url!r}")
    if not base_url.endswith("/"):
        base_url += "/"
    built = built or build_date()
    skills = list(build_default_registry())
    index = render_index(base_url, skills, built)
    not_found = fill(
        (SITE_DIR / "404.html").read_text(encoding="utf-8"),
        {"base_path": _e(urlsplit(base_url).path or "/"), "version": _e(__version__)},
    )
    _clear_out_dir(out_dir)
    shutil.copytree(SITE_DIR / "assets", out_dir / "assets")
    (out_dir / "index.html").write_text(index, encoding="utf-8")
    (out_dir / "404.html").write_text(not_found, encoding="utf-8")
    (out_dir / "skills.json").write_text(skills_json(skills), encoding="utf-8")
    (out_dir / "sitemap.xml").write_text(sitemap(base_url, built), encoding="utf-8")
    (out_dir / "robots.txt").write_text(robots(base_url), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return out_dir


def build_date() -> date:
    """Today, or ``SOURCE_DATE_EPOCH`` for reproducible builds."""

    epoch = os.environ.get("SOURCE_DATE_EPOCH", "")
    if epoch.isdigit():
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).date()
    return date.today()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Jarvis website.")
    parser.add_argument("--out", default=str(ROOT / "_site"), help="output directory (default: _site)")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("JARVIS_SITE_URL") or DEFAULT_BASE_URL,
        help=f"public URL of the site, ending in / (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args(argv)
    try:
        out = build(Path(args.out), args.base_url)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Built {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
