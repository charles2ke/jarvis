"""Knowledge sources Jarvis can learn from: local files and websites.

A knowledge source is a plain text excerpt taken from a file on disk or from a
web page, stored in memory so later questions can be answered from it. Only the
standard library is used, so Jarvis stays dependency free.
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

MEMORY_KEY = "knowledge_sources"
MAX_TEXT_CHARS = 20_000
MAX_FILE_BYTES = 2_000_000
MAX_WEBSITE_BYTES = MAX_TEXT_CHARS * 20
DEFAULT_TIMEOUT = 15.0
USER_AGENT = "jarvis-knowledge/1.0"

TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".htm",
    ".xml",
    ".py",
    ".cfg",
    ".ini",
    ".toml",
    ".log",
    "",
}

_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "say",
    "tell",
    "that",
    "the",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}


class KnowledgeError(RuntimeError):
    """Raised when a knowledge source cannot be added."""


@dataclass(frozen=True)
class Source:
    """A file or website Jarvis has read."""

    kind: str
    title: str
    location: str
    text: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "kind": self.kind,
            "title": self.title,
            "location": self.location,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> Optional["Source"]:
        if not isinstance(data, dict):
            return None
        kind = str(data.get("kind") or "")
        location = str(data.get("location") or "")
        text = str(data.get("text") or "")
        if kind not in {"file", "website"} or not location:
            return None
        return cls(
            kind=kind,
            title=str(data.get("title") or location),
            location=location,
            text=text,
        )

    def describe(self) -> str:
        words = len(self.text.split())
        what = "file" if self.kind == "file" else "website"
        return f"{self.title} ({what}, {self.location}, {words} words)"


class _TextExtractor(HTMLParser):
    """Collect the visible text and the ``<title>`` of an HTML document."""

    _SKIP = {"script", "style", "noscript", "head", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._parts: List[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._skip_depth:
            return
        self._parts.append(data)

    @property
    def text(self) -> str:
        return "".join(self._parts)


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


def extract_html_text(markup: str) -> tuple[str, str]:
    """Return ``(title, text)`` for an HTML document."""

    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:  # pragma: no cover - malformed markup is still usable
        pass
    return html.unescape(parser.title).strip(), _tidy(parser.text)


def add_file(path: str | Path) -> Source:
    """Read ``path`` and return it as a knowledge source."""

    raw = str(path or "").strip().strip("'\"")
    if not raw:
        raise KnowledgeError("Tell me which file to read.")
    resolved = Path(raw).expanduser()
    if not resolved.exists():
        raise KnowledgeError(f"I could not find the file '{raw}'.")
    if resolved.is_dir():
        raise KnowledgeError(f"'{raw}' is a folder, not a file.")
    if resolved.suffix.lower() not in TEXT_SUFFIXES:
        raise KnowledgeError(
            f"I can only read text files, and '{resolved.suffix}' is not one of them."
        )
    try:
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise KnowledgeError(f"'{raw}' is too large for me to read.")
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise KnowledgeError(f"I could not read '{raw}': {exc}") from exc
    if resolved.suffix.lower() in {".html", ".htm"}:
        title, text = extract_html_text(content)
        title = title or resolved.name
    else:
        title, text = resolved.name, _tidy(content)
    if not text:
        raise KnowledgeError(f"'{raw}' looks empty, so there is nothing to learn.")
    return Source(kind="file", title=title, location=str(resolved), text=text)


def add_website(url: str, *, opener=None, timeout: float = DEFAULT_TIMEOUT) -> Source:
    """Fetch ``url`` and return the page as a knowledge source."""

    address = str(url or "").strip().strip("'\"").rstrip(".,")
    if not address:
        raise KnowledgeError("Tell me which website to read.")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", address, re.IGNORECASE):
        address = "https://" + address
    scheme = address.split("://", 1)[0].lower()
    if scheme not in {"http", "https"}:
        raise KnowledgeError("I can only read http and https addresses.")
    request = urllib.request.Request(
        address, headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain"}
    )
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(request, timeout=timeout) as response:
            charset = "utf-8"
            content_type = ""
            headers = getattr(response, "headers", None)
            if headers is not None:
                charset = headers.get_content_charset() or "utf-8"
                content_type = (headers.get_content_type() or "").lower()
                try:
                    content_length = int(headers.get("Content-Length", 0))
                except (TypeError, ValueError):
                    content_length = 0
                if content_length > MAX_WEBSITE_BYTES:
                    raise KnowledgeError(f"{address} is too large for me to read.")
            payload = response.read(MAX_WEBSITE_BYTES + 1)
            if len(payload) > MAX_WEBSITE_BYTES:
                raise KnowledgeError(f"{address} is too large for me to read.")
    except urllib.error.HTTPError as exc:
        raise KnowledgeError(f"{address} refused to answer (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as exc:
        raise KnowledgeError(f"I could not reach {address}: {exc}") from exc

    if isinstance(payload, bytes):
        markup = payload.decode(charset, errors="replace")
    else:  # pragma: no cover - defensive
        markup = str(payload)
    markup = markup[:MAX_WEBSITE_BYTES]
    if content_type and not content_type.startswith("text/"):
        raise KnowledgeError(f"{address} is not a text or HTML page.")
    if content_type == "text/plain":
        title, text = "", _tidy(markup)
    else:
        title, text = extract_html_text(markup)
    if not text:
        raise KnowledgeError(f"I could not find any readable text at {address}.")
    return Source(kind="website", title=title or address, location=address, text=text)


def load(stored: object) -> List[Source]:
    """Rebuild the stored sources, ignoring anything unreadable."""

    if not isinstance(stored, list):
        return []
    sources: List[Source] = []
    for item in stored:
        source = Source.from_dict(item)
        if source is not None:
            sources.append(source)
    return sources


def dump(sources: Iterable[Source]) -> List[Dict[str, str]]:
    return [source.as_dict() for source in sources]


def _keywords(query: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", (query or "").lower())
    keywords = [word for word in words if word not in _STOPWORDS and len(word) > 1]
    return keywords or words


def _passages(text: str) -> List[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def search(
    sources: Sequence[Source], query: str, *, limit: int = 2
) -> Optional[tuple[Source, List[str]]]:
    """Return the best matching source and passages for ``query``."""

    keywords = _keywords(query)
    if not keywords or not sources:
        return None
    best: Optional[tuple[float, Source, List[str]]] = None
    for source in sources:
        scored: List[tuple[int, int, str]] = []
        for index, passage in enumerate(_passages(source.text)):
            lowered = passage.lower()
            hits = sum(1 for word in keywords if word in lowered)
            if hits:
                scored.append((hits, -index, passage))
        if not scored:
            continue
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        top = scored[:limit]
        total = sum(hits for hits, _, _ in top) / len(keywords)
        if best is None or total > best[0]:
            best = (total, source, [passage for _, _, passage in top])
    if best is None:
        return None
    return best[1], best[2]
