#!/usr/bin/env python3
"""Generate ``src/jarvis/cancer_data.py`` from a local beat-it checkout.

Usage::

    python3 scripts/import_beat_it.py /path/to/beat-it \
        [--commit SHA] [--date YYYY-MM-DD] [--output PATH]

beat-it (https://github.com/charles2ke/beat-it, AGPL-3.0) keeps its
hand-reviewed content in ``site/data``. This script copies ``cancers.json``,
``faq.json`` and ``facts.json`` into plain Python literals, because Jarvis
ships no package data. ``updates.json`` (refreshed daily from live feeds) and
each entry's ``query`` search term are left out.

The commit and its date come from ``git`` when the checkout is a repository;
pass ``--commit`` and ``--date`` otherwise. The output depends only on the
data files, the commit and its date, so regenerating from the same commit
gives the same file. Only the standard library is used.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "src" / "jarvis" / "cancer_data.py"
REPO_URL = "https://github.com/charles2ke/beat-it"
LICENCE = "AGPL-3.0"
DATA_FILES = ("site/data/cancers.json", "site/data/faq.json", "site/data/facts.json")
WIDTH = 79


def _git(checkout: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _field(record: Dict[str, Any], key: str, where: str, optional: bool = False) -> Any:
    value = record.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: '{key}' must be a non-empty string")
    return value


def _strings(record: Dict[str, Any], key: str, where: str) -> Tuple[str, ...]:
    values = record.get(key) or []
    if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
        raise ValueError(f"{where}: '{key}' must be a list of strings")
    return tuple(values)


def convert_cancer(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Return the fields Jarvis uses from one ``cancers.json`` entry."""

    where = f"cancers.json entry {raw.get('id', '?')!r}"
    source = raw.get("screeningSource") or None
    return {
        "id": _field(raw, "id", where),
        "name": _field(raw, "name", where),
        "group": _field(raw, "group", where),
        "aliases": _strings(raw, "aliases", where),
        "nci": _field(raw, "nci", where),
        "summary": _field(raw, "summary", where),
        "symptoms": _strings(raw, "symptoms", where),
        "risk_factors": _strings(raw, "riskFactors", where),
        "screening": _field(raw, "screening", where),
        "screening_source": (
            {
                "name": _field(source, "name", where + " screeningSource"),
                "url": _field(source, "url", where + " screeningSource"),
            }
            if source
            else None
        ),
        "treatments": _strings(raw, "treatments", where),
        "medicines": tuple(
            {
                "name": _field(medicine, "name", where + " medicine"),
                "use": _field(medicine, "use", where + " medicine"),
                "since": _field(medicine, "since", where + " medicine", optional=True),
            }
            for medicine in raw.get("medicines") or []
        ),
        "approvals": tuple(
            {
                "date": _field(approval, "date", where + " approval"),
                "drug": _field(approval, "drug", where + " approval"),
                "text": _field(approval, "text", where + " approval"),
                "url": _field(approval, "url", where + " approval"),
            }
            for approval in raw.get("approvals") or []
        ),
        "reviewed": _field(raw, "reviewed", where, optional=True),
    }


def convert_faq(raw: Dict[str, Any]) -> Dict[str, str]:
    where = f"faq.json entry {raw.get('q', '?')!r}"
    return {
        "q": _field(raw, "q", where),
        "a": _field(raw, "a", where),
        "link": _field(raw, "link", where),
    }


def convert_facts(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": _field(raw, "title", "facts.json"),
        "intro": _field(raw, "intro", "facts.json"),
        "facts": tuple(
            {
                "value": _field(fact, "value", "facts.json fact"),
                "label": _field(fact, "label", "facts.json fact"),
                "source": _field(fact, "source", "facts.json fact"),
                "url": _field(fact, "url", "facts.json fact"),
            }
            for fact in raw.get("facts") or []
        ),
    }


def _string(text: str, indent: int, column: int) -> str:
    """Return ``text`` as a literal, split into adjacent pieces when long.

    ``column`` is where the literal starts and ``indent`` is the indentation
    of that line; split pieces go one level deeper.
    """

    single = repr(text)
    if column + len(single) + 1 <= WIDTH:
        return single
    room = WIDTH - indent - 4
    chunks: List[str] = []
    current = ""
    for piece in re.findall(r"\S*\s*", text):
        if current and len(repr(current + piece)) > room:
            chunks.append(current)
            current = piece
        else:
            current += piece
    if current:
        chunks.append(current)
    if len(chunks) == 1:
        return single
    pad = " " * indent
    inner = "".join(f"{pad}    {chunk!r}\n" for chunk in chunks)
    return f"(\n{inner}{pad})"


def literal(value: Any, indent: int = 0, column: Optional[int] = None) -> str:
    """Return ``value`` as deterministic, readable Python source."""

    pad = " " * indent
    if isinstance(value, str):
        return _string(value, indent, indent if column is None else column)
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = "".join(
            f"{pad}    {key!r}: {literal(item, indent + 4, indent + 6 + len(repr(key)))},\n"
            for key, item in value.items()
        )
        return f"{{\n{inner}{pad}}}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "()"
        inner = "".join(f"{pad}    {literal(item, indent + 4)},\n" for item in value)
        return f"(\n{inner}{pad})"
    if value is None or isinstance(value, (bool, int, float)):
        return repr(value)
    raise TypeError(f"cannot write {type(value).__name__} values")


def render(
    cancers: Sequence[Dict[str, Any]],
    faqs: Sequence[Dict[str, str]],
    facts: Dict[str, Any],
    *,
    commit: str,
    date: str,
) -> str:
    """Return the source of ``cancer_data.py`` for already converted data."""

    reviewed = max((c["reviewed"] for c in cancers if c.get("reviewed")), default="unknown")
    source = {
        "repo": REPO_URL,
        "commit": commit,
        "date": date,
        "licence": LICENCE,
        "files": DATA_FILES,
    }
    lines = [
        "# Generated by scripts/import_beat_it.py - do not edit by hand.",
        f"# Source: {REPO_URL} ({LICENCE})",
        f"# Commit: {commit} ({date})",
        "# Files: " + ", ".join(DATA_FILES),
        "# Not ported: site/data/updates.json (live feeds) and each entry's 'query'.",
        f"# Entries last reviewed by beat-it: {reviewed}",
        "# Regenerate from a beat-it checkout with:",
        "#     python3 scripts/import_beat_it.py /path/to/beat-it",
        '"""Curated cancer reference data from beat-it, as plain Python literals.',
        "",
        "Generated - see the header above. :mod:`jarvis.cancer` builds the lookups.",
        '"""',
        "",
        f"SOURCE = {literal(source)}",
        "",
        f"CANCERS = {literal(tuple(cancers))}",
        "",
        f"FAQS = {literal(tuple(faqs))}",
        "",
        f"FACTS = {literal(facts)}",
        "",
    ]
    return "\n".join(lines)


def build(checkout: Path, commit: Optional[str] = None, date: Optional[str] = None) -> str:
    """Read the beat-it data under ``checkout`` and return the module source."""

    commit = commit or _git(checkout, "rev-parse", "HEAD")
    date = date or _git(checkout, "log", "-1", "--format=%cs")
    if not commit:
        raise SystemExit("Could not read the commit with git; pass --commit SHA.")
    if not date:
        raise SystemExit("Could not read the commit date with git; pass --date YYYY-MM-DD.")
    cancers_path, faq_path, facts_path = (checkout / name for name in DATA_FILES)
    cancers = [convert_cancer(raw) for raw in json.loads(cancers_path.read_text(encoding="utf-8"))]
    faqs = [convert_faq(raw) for raw in json.loads(faq_path.read_text(encoding="utf-8"))]
    facts = convert_facts(json.loads(facts_path.read_text(encoding="utf-8")))
    ids = [cancer["id"] for cancer in cancers]
    if len(set(ids)) != len(ids):
        raise SystemExit("cancers.json has duplicate ids.")
    return render(cancers, faqs, facts, commit=commit, date=date)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("checkout", type=Path, help="path to a local beat-it checkout")
    parser.add_argument("--commit", help="commit SHA, if the checkout is not a git repository")
    parser.add_argument("--date", help="commit date (YYYY-MM-DD), if git is unavailable")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="file to write")
    args = parser.parse_args(argv)
    source = build(args.checkout, commit=args.commit, date=args.date)
    args.output.write_text(source, encoding="utf-8")
    print(f"Wrote {args.output} ({len(source.encode('utf-8'))} bytes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
