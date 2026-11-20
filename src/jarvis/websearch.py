"""Search the web and summarise what it says, using only the standard library.

Jarvis answers most questions offline. For a question outside its built-in
knowledge this module looks the question up online and writes a short
*extractive* summary: every sentence is quoted from a page that was found,
never invented, and carries a numbered citation so it can be checked.

Providers:

``wikipedia`` (the default, no key needed)
    Wikipedia's search API, in the language set by ``JARVIS_WIKIPEDIA_LANG``
    (default ``en``). One request returns the best matching articles together
    with their introductions.
``searxng``
    A SearXNG instance at ``JARVIS_SEARXNG_URL`` with its JSON format enabled.
``brave``
    The Brave Search API, with the key in ``JARVIS_BRAVE_API_KEY``.

``JARVIS_SEARCH_PROVIDER`` picks one explicitly. Otherwise Brave is used when a
key is set, then SearXNG when a URL is set, and Wikipedia when neither is. For
SearXNG and Brave the top result pages are read so the summary can quote them;
a page that cannot be read, or that lives on a private network, falls back to
its search snippet.
"""

from __future__ import annotations

import html
import http.client
import ipaddress
import json
import math
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from jarvis import knowledge

#: When Jarvis may search: ``auto`` also looks up questions no skill can
#: answer, ``manual`` only when asked to, and ``off`` never.
MODES = ("auto", "manual", "off")
PROVIDERS = ("wikipedia", "searxng", "brave")
PROVIDER_NAMES = {"wikipedia": "Wikipedia", "searxng": "SearXNG", "brave": "Brave Search"}
DEFAULT_TIMEOUT = 10.0
PAGE_TIMEOUT = 8.0
MAX_RESULTS = 3
MAX_RESPONSE_BYTES = 2_000_000
MAX_QUERY_CHARS = 250
MAX_LOOKUP_CHARS = 300
USER_AGENT = "jarvis-websearch/1.0 (+https://github.com/charles2ke/jarvis)"
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class WebSearchError(RuntimeError):
    """Raised when the web cannot be searched; the message is a full sentence."""


@dataclass(frozen=True)
class Document:
    """A page found on the web, reduced to plain text."""

    title: str
    url: str
    text: str

    def as_dict(self) -> Dict[str, str]:
        return {"title": self.title, "url": self.url, "text": self.text}

    @classmethod
    def from_dict(cls, data: object) -> Optional["Document"]:
        if not isinstance(data, dict):
            return None
        return _document(data.get("title"), data.get("url"), data.get("text"))


@dataclass(frozen=True)
class SearchResults:
    """What a provider returned for ``query``, best match first."""

    query: str
    provider: str
    documents: Tuple[Document, ...]


@dataclass(frozen=True)
class Sentence:
    """A sentence quoted from ``documents[source]`` for a summary."""

    text: str
    source: int
    position: int


# --- Text hygiene -----------------------------------------------------------

# C0 controls (except tab and newline), DEL, C1 controls and the bidirectional
# overrides: web text containing them could restyle or reorder the terminal.
_UNSAFE_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
_TAG = re.compile(r"<[^>]+>")


def clean_text(text: object) -> str:
    """Return ``text`` without characters that could rewrite the terminal."""

    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return _UNSAFE_CHARS.sub("", value)


def _one_line(text: object) -> str:
    return re.sub(r"\s+", " ", clean_text(text)).strip()


def _strip_markup(text: object) -> str:
    return html.unescape(_TAG.sub("", str(text or "")))


def _display_url(url: object) -> Optional[str]:
    value = _one_line(url)
    if " " in value or not re.match(r"^https?://[^/?#\s]+", value, re.IGNORECASE):
        return None
    return value


def _document(title: object, url: object, text: object) -> Optional[Document]:
    address = _display_url(url)
    body = clean_text(text).strip()[: knowledge.MAX_TEXT_CHARS]
    if address is None or not body:
        return None
    name = _one_line(title)[:200] or address
    return Document(title=name, url=address, text=body)


# --- Which questions to look up ---------------------------------------------

_STOPWORDS = frozenset(
    """a about above after again against all also am an and any are as at be
    because been before being below between both but by can could did do does
    doing down during each few find for from further give google had has have
    having he her here hers herself him himself his how i if in internet into is
    it its itself just know let look me more most my myself no nor not of off on
    once online only or other our ours ourselves out over own please same search
    she should show so some such tell than that the their theirs them themselves
    then there these they this those through to too under until up very was we
    web were what when where which while who whom whose why will with would you
    your yours yourself yourselves""".split()
)

# Words that do not say what a question is about, so "is that true?" or "what
# happened?" are not worth sending to a search engine.
_VAGUE = frozenset(
    """again another anything bad bye come cool did does done else everything
    false fine get gets going goes good got great happen happened happening help
    hello hey hi hmm huh like lol made make mean means meant need new next nice
    nothing now ok okay one ones really right said same say something stuff sure
    thank thanks thing things think time today tomorrow true want way went wow
    wrong yes yesterday""".split()
)

_LEAD_INS = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay|so|and|well|um|uh|jarvis|please|thanks|thank\s+you"
    r"|cheers)\b[\s,!.]*)*"
    r"(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"(?:tell\s+me|find\s+out|look\s+up|search(?:\s+for)?|explain)\s+"
    r"|(?:do|did)\s+you\s+(?:happen\s+to\s+)?know\s+"
    r"|i\s+(?:want|would\s+like|['’]d\s+like)\s+to\s+know\s+"
    r"|i\s+wonder\s+|i(?:['’]m|\s+am)\s+(?:curious|wondering)\s+(?:about\s+)?"
    r"|tell\s+me\s+|find\s+out\s+)?",
    re.IGNORECASE,
)
_QUESTION_START = re.compile(
    r"^(?:who|whom|whose|what|which|when|where|why|how|is|are|was|were|do|does"
    r"|did|can|could|should|would|will|has|have|had|about|define|explain|describe"
    r"|look\s*up|search\s+for)\b",
    re.IGNORECASE,
)
_QUESTION_WORDS = re.compile(
    r"^(?:(?:who|whom|whose|what|which|when|where|why|how)(?:['’](?:s|re|d))?"
    r"(?:\s+(?:is|are|was|were|do|does|did|has|have|had|can|could|should|would"
    r"|will))?|about|define|explain|describe|look\s*up|search\s+for)\s+",
    re.IGNORECASE,
)
# "How do I tie a tie?" is a how-to question, not a personal one; "where do I
# live?" or "when can I stop taking my pills?" are personal.
_GENERIC_PERSON = re.compile(
    r"\bhow\s+(?:do|can|could|should|would|might|will)\s+i\b", re.IGNORECASE
)
_GENERIC_LEAD = re.compile(
    r"^(how|where|when)\s+(?:do|can|could|should|would|might|will)\s+(?:i|we|you)\s+",
    re.IGNORECASE,
)
_PERSONAL = re.compile(
    r"\b(?:me|my|mine|myself|we|we['’](?:re|ve|d|ll)|our|ours|ourselves|you"
    r"|you['’](?:re|ve|d|ll)|your|yours|yourself|yourselves"
    # Lower case only, so that "US" and "U.S." are still countries.
    r"|(?-i:us|ur|u(?!\.\w)))\b",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"(?<![\w'’])(i|i['’](?:m|ve|d|ll)|im|ive)(?![\w'’])", re.IGNORECASE)
# Nouns that take a Roman numeral, as in "Type I diabetes" or "Act I".
_NUMBERED = frozenset(
    """act article book category chapter class grade level part phase schedule
    season section series stage tier type volume""".split()
)
_TIMELY = re.compile(
    r"\b(?:today|tonight|tomorrow|yesterday|now|current(?:ly)?|latest|this\s+"
    r"(?:week|month|year)|weather|forecast|news|prices?|scores?|stocks?|exchange\s+rate)\b",
    re.IGNORECASE,
)


def _words(text: str) -> List[str]:
    return re.findall(r"[^\W_]+", text.lower())


def _stem(word: str) -> str:
    """Reduce ``word`` to a rough stem so "invented" matches "inventor"."""

    stem = word.lower()
    if len(stem) <= 3:
        return stem
    if stem.endswith("ies") and len(stem) > 4:
        stem = stem[:-3] + "y"
    elif stem.endswith("sses"):
        stem = stem[:-2]
    elif stem.endswith("s") and not stem.endswith(("ss", "us", "is")):
        stem = stem[:-1]
    for suffix in ("ations", "ation", "ingly", "ings", "ing", "edly", "ed", "ions",
                   "ion", "ors", "or", "ers", "er", "ments", "ment", "ness", "ly"):
        if stem.endswith(suffix) and len(stem) - len(suffix) >= 4:
            stem = stem[: -len(suffix)]
            # "running" -> "run" and "stopped" -> "stop", but "installed" -> "install".
            if stem[-1] == stem[-2] and stem[-1] not in "aeioulsz":
                stem = stem[:-1]
            return stem
    return stem


def content_words(text: str) -> List[str]:
    """The words of ``text`` that say what it is about."""

    return [
        word
        for word in _words(text)
        if word not in _STOPWORDS and word not in _VAGUE and (len(word) > 1 or word.isdigit())
    ]


def keywords(text: str) -> List[str]:
    """Stemmed content words of ``text``, without repeats."""

    seen: List[str] = []
    for word in content_words(text):
        stem = _stem(word)
        if stem not in seen:
            seen.append(stem)
    return seen


def coverage(question: str, text: str) -> float:
    """The share of the question's keywords that ``text`` mentions."""

    wanted = keywords(question)
    if not wanted:
        return 0.0
    present = {_stem(word) for word in _words(text)}
    return sum(1 for stem in wanted if stem in present) / len(wanted)


def strip_lead_ins(text: str) -> str:
    """Drop greetings and wrappers such as "do you know" from ``text``."""

    return _LEAD_INS.sub("", _one_line(text), count=1).strip()


def _is_numeral(text: str, found: "re.Match[str]") -> bool:
    """True for the "I" in "Elizabeth I" or "World War I", which is not a person.

    A capitalised word before it is not enough, since "In January I moved" is
    the pronoun: the "I" must follow a numbered noun ("Type I") or end the name
    ("Who was Elizabeth I?", "Elizabeth I of England").
    """

    if found.group(0) != "I":
        return False
    before = text[: found.start()].split()
    if [word.lower() for word in before[-2:]] == ["world", "war"]:
        return True
    if not before:
        return False
    previous = before[-1]
    if not (previous[:1].isupper() and previous[-1:].isalpha()):
        return False
    if previous.lower() in _STOPWORDS | _VAGUE:
        return False
    if previous.lower() in _NUMBERED:
        # "Stage I cancer", but not "under the Affordable Care Act I pay".
        named = before[-2] if len(before) > 1 else ""
        if not named[:1].isupper() or named.lower() in _STOPWORDS | _VAGUE:
            return True
    return bool(re.match(r"\s*(?:$|[?!.;:)]|of\b)", text[found.end() :]))


def _is_personal(text: str) -> bool:
    if _PERSONAL.search(text):
        return True
    return any(not _is_numeral(text, found) for found in _FIRST_PERSON.finditer(text))


def is_lookup(text: str, *, require_question: bool = True) -> bool:
    """Return True when ``text`` reads like a factual question to look up.

    Personal messages ("my", "I am", "you") are never treated as lookups, so
    they are not sent to a search engine without being asked.
    """

    cleaned = strip_lead_ins(text)
    if not cleaned or len(cleaned) > MAX_LOOKUP_CHARS:
        return False
    generic = _GENERIC_PERSON.sub("how to", cleaned)
    if _is_personal(generic):
        return False
    if require_question and not (
        _QUESTION_START.match(generic) or generic.rstrip().endswith("?")
    ):
        return False
    return bool(content_words(generic))


def search_terms(text: str) -> str:
    """Turn a question into the words worth sending to a search engine."""

    asked = strip_lead_ins(text)
    generic = _GENERIC_LEAD.match(asked)
    if generic:
        # "How do I tie a tie?" is searched as "how to tie a tie".
        terms = f"{generic.group(1).lower()} to {asked[generic.end():]}"
    else:
        terms = _QUESTION_WORDS.sub("", asked, count=1)
    terms = terms.strip().strip("\"'“”‘’").rstrip("?!.").strip()
    if len(terms) > MAX_QUERY_CHARS:
        terms = terms[:MAX_QUERY_CHARS].rsplit(" ", 1)[0]
    return terms


def is_timely(text: str) -> bool:
    """True when ``text`` asks about something that changes, like the news."""

    return bool(_TIMELY.search(text or ""))


# --- Providers ---------------------------------------------------------------

Opener = Callable[..., object]


def choose_provider(environ: Optional[Mapping[str, str]] = None) -> str:
    """Return the provider to use, following ``JARVIS_SEARCH_PROVIDER``."""

    env = os.environ if environ is None else environ
    name = (env.get("JARVIS_SEARCH_PROVIDER") or "").strip().lower()
    if name:
        if name not in PROVIDERS:
            raise WebSearchError(
                f"JARVIS_SEARCH_PROVIDER is '{_one_line(name)[:20]}', but it must be "
                "wikipedia, searxng or brave."
            )
        return name
    if (env.get("JARVIS_BRAVE_API_KEY") or "").strip():
        return "brave"
    if (env.get("JARVIS_SEARXNG_URL") or "").strip():
        return "searxng"
    return "wikipedia"


def _get_json(
    url: str,
    *,
    service: str,
    opener: Optional[Opener],
    timeout: float,
    headers: Optional[Mapping[str, str]] = None,
    hints: Optional[Mapping[int, str]] = None,
) -> object:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})},
    )
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        hint = (hints or {}).get(exc.code, "")
        raise WebSearchError(
            f"{service} refused the search (HTTP {exc.code}).{' ' + hint if hint else ''}"
        ) from exc
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        # The reason can quote the server's own bytes, such as a bad status line.
        reason = _one_line(getattr(exc, "reason", None) or exc)[:200] or exc.__class__.__name__
        raise WebSearchError(f"{service} could not be reached ({reason}).") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise WebSearchError(f"{service} sent more data than I can read.")
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    try:
        return json.loads(payload)
    except ValueError as exc:
        raise WebSearchError(f"{service} sent a reply I could not read.") from exc


def _wikipedia_language(env: Mapping[str, str]) -> str:
    language = (env.get("JARVIS_WIKIPEDIA_LANG") or "en").strip().lower()
    if not re.fullmatch(r"[a-z]{2,12}(?:-[a-z0-9]{1,12}){0,2}", language):
        raise WebSearchError(
            f"JARVIS_WIKIPEDIA_LANG is '{_one_line(language)[:20]}', but it must be a "
            "Wikipedia language code such as 'en' or 'de'."
        )
    return language


def _is_disambiguation(extract: str) -> bool:
    return bool(re.search(r"\b(?:may|might|can)\s+(?:also\s+)?refer\s+to:?\s*$", extract.strip()))


def _search_wikipedia(
    query: str, *, limit: int, opener: Optional[Opener], timeout: float, env: Mapping[str, str]
) -> List[Document]:
    language = _wikipedia_language(env)
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": str(limit),
        "gsrnamespace": "0",
        "gsrenablerewrites": "1",
        "prop": "extracts|info",
        "exintro": "1",
        "explaintext": "1",
        "exlimit": str(limit),
        "inprop": "url",
        "redirects": "1",
    }
    url = f"https://{language}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    data = _get_json(url, service="Wikipedia", opener=opener, timeout=timeout)
    if not isinstance(data, dict):
        raise WebSearchError("Wikipedia sent a reply I could not read.")
    error = data.get("error")
    if isinstance(error, dict):
        detail = _one_line(error.get("info") or error.get("code") or "unknown error")[:200]
        raise WebSearchError(f"Wikipedia could not search: {detail}.")
    pages = (data.get("query") or {}).get("pages") or []
    if isinstance(pages, dict):
        pages = list(pages.values())
    ranked = sorted(
        (page for page in pages if isinstance(page, dict)),
        key=lambda page: page.get("index") if isinstance(page.get("index"), int) else 10**9,
    )
    documents: List[Document] = []
    for page in ranked:
        title = page.get("title") or ""
        extract = page.get("extract") or ""
        if not isinstance(extract, str) or _is_disambiguation(extract):
            continue
        address = page.get("fullurl") or page.get("canonicalurl")
        if not address and title:
            slug = urllib.parse.quote(str(title).replace(" ", "_"))
            address = f"https://{language}.wikipedia.org/wiki/{slug}"
        document = _document(title, address, extract)
        if document is not None:
            documents.append(document)
    return documents[:limit]


def _searxng_base(env: Mapping[str, str]) -> str:
    base = (env.get("JARVIS_SEARXNG_URL") or "").strip().rstrip("/")
    if not base:
        raise WebSearchError("Set JARVIS_SEARXNG_URL to the address of your SearXNG instance.")
    if not re.match(r"^https?://[^/?#\s]+", base, re.IGNORECASE):
        raise WebSearchError("JARVIS_SEARXNG_URL must start with http:// or https://.")
    if base.lower().endswith("/search"):
        base = base[: -len("/search")]
    return base


def _search_searxng(
    query: str, *, limit: int, opener: Optional[Opener], timeout: float, env: Mapping[str, str]
) -> List[Document]:
    url = f"{_searxng_base(env)}/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
    data = _get_json(
        url,
        service="SearXNG",
        opener=opener,
        timeout=timeout,
        hints={403: "Enable the json format under search.formats in its settings.yml."},
    )
    results = data.get("results") if isinstance(data, dict) else None
    hits = [
        (item.get("title"), item.get("url"), item.get("content"))
        for item in (results or [])
        if isinstance(item, dict)
    ]
    return _read_pages(hits, limit=limit, opener=opener)


def _search_brave(
    query: str, *, limit: int, opener: Optional[Opener], timeout: float, env: Mapping[str, str]
) -> List[Document]:
    key = (env.get("JARVIS_BRAVE_API_KEY") or "").strip()
    if not key:
        raise WebSearchError("Set JARVIS_BRAVE_API_KEY to use Brave Search.")
    params = {"q": query, "count": "5", "text_decorations": "false"}
    data = _get_json(
        f"{BRAVE_ENDPOINT}?" + urllib.parse.urlencode(params),
        service="Brave Search",
        opener=opener,
        timeout=timeout,
        headers={"X-Subscription-Token": key},
        hints={
            401: "Check JARVIS_BRAVE_API_KEY.",
            403: "Check JARVIS_BRAVE_API_KEY.",
            429: "The API rate limit was reached; try again shortly.",
        },
    )
    web = data.get("web") if isinstance(data, dict) else None
    results = web.get("results") if isinstance(web, dict) else None
    hits = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        extra = item.get("extra_snippets")
        snippets = [item.get("description") or ""]
        if isinstance(extra, list):
            snippets.extend(str(snippet) for snippet in extra)
        hits.append((item.get("title"), item.get("url"), "\n".join(snippets)))
    return _read_pages(hits, limit=limit, opener=opener)


# --- Reading result pages safely ---------------------------------------------

# A plain host name or bracketed IPv6 address with an optional port. User names,
# percent escapes and backslashes are refused: urllib decodes "127.0.0.1%3a80"
# to a different host than urlsplit reports.
_NETLOC = re.compile(r"(?:[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.?|\[[0-9A-Fa-f:.]+\])(?::\d{1,5})?")


def _is_public_address(address: object) -> bool:
    try:
        return ipaddress.ip_address(str(address).split("%", 1)[0]).is_global
    except ValueError:
        return False


def is_public_url(url: str) -> bool:
    """Return False for http(s) addresses on this machine or a private network."""

    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").rstrip(".").lower()
        valid_port = parts.port is None or parts.port > 0
    except ValueError:
        return False
    if parts.scheme.lower() not in {"http", "https"} or not host or not valid_port:
        return False
    if not _NETLOC.fullmatch(parts.netloc):
        return False
    if host == "localhost" or host.endswith(
        (".localhost", ".local", ".internal", ".lan", ".home.arpa")
    ):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    # Hosts such as "2130706433" or "127.1" are still read as IP addresses by
    # the resolver, and single-label names only resolve on a local network.
    last = host.rsplit(".", 1)[-1]
    return "." in host and bool(re.search(r"[a-z]", last)) and not last.startswith("0x")


def _resolves_publicly(host: str, resolver: Callable[..., Iterable] = socket.getaddrinfo) -> bool:
    """True when ``host`` resolves, and only to public addresses."""

    try:
        infos = list(resolver(host, None))
    except (OSError, UnicodeError, ValueError):
        return False
    addresses = []
    for info in infos:
        try:
            addresses.append(info[4][0])
        except (IndexError, TypeError):
            return False
    return bool(addresses) and all(_is_public_address(address) for address in addresses)


def _connect_publicly(address, *args, **kwargs):
    """Connect like ``socket.create_connection``, but hang up on private peers.

    A name can resolve to a public address for the check in
    ``_open_public_page`` and to a private one moments later, so the address
    actually connected to is checked too.
    """

    sock = socket.create_connection(address, *args, **kwargs)
    try:
        peer = sock.getpeername()[0]
    except OSError:
        peer = None
    if not _is_public_address(peer):
        sock.close()
        raise OSError(f"refusing to read {address[0]}, a private network address")
    return sock


class _PublicPeers:
    """Check where each connection really goes, unless a proxy makes it."""

    def do_open(self, http_class, req, **kwargs):
        if req.has_proxy() or getattr(req, "_tunnel_host", None):
            return super().do_open(http_class, req, **kwargs)

        def connection(*args, **options):
            conn = http_class(*args, **options)
            conn._create_connection = _connect_publicly
            return conn

        return super().do_open(connection, req, **kwargs)


class _PublicHTTPHandler(_PublicPeers, urllib.request.HTTPHandler):
    pass


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to public addresses."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        host = urllib.parse.urlsplit(newurl).hostname or ""
        if not is_public_url(newurl) or not _resolves_publicly(host):
            raise urllib.error.URLError(f"refusing to follow a redirect to {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_PAGE_HANDLERS: List[type] = [_PublicRedirects, _PublicHTTPHandler]
if hasattr(urllib.request, "HTTPSHandler"):  # Python can be built without ssl.

    class _PublicHTTPSHandler(_PublicPeers, urllib.request.HTTPSHandler):
        pass

    _PAGE_HANDLERS.append(_PublicHTTPSHandler)


def _open_public_page(request, timeout: float = PAGE_TIMEOUT):
    """Open ``request`` only if it leads to a public address."""

    host = urllib.parse.urlsplit(request.full_url).hostname or ""
    if not _resolves_publicly(host):
        raise urllib.error.URLError(f"refusing to read {host}, a private network address")
    # Built for each page so that proxy settings are read from the environment.
    return urllib.request.build_opener(*_PAGE_HANDLERS).open(request, timeout=timeout)


def _read_pages(
    hits: Sequence[Tuple[object, object, object]], *, limit: int, opener: Optional[Opener]
) -> List[Document]:
    chosen: List[Tuple[str, str, str]] = []
    for title, url, snippet in hits:
        address = _display_url(url)
        if address is None or any(address == seen for _, seen, _ in chosen):
            continue
        chosen.append((_one_line(_strip_markup(title)), address, _strip_markup(snippet)))
        if len(chosen) == limit:
            break
    if not chosen:
        return []

    def read(hit: Tuple[str, str, str]) -> Optional[Document]:
        title, address, snippet = hit
        page = ""
        if is_public_url(address):
            try:
                source = knowledge.add_website(
                    address, opener=opener or _open_public_page, timeout=PAGE_TIMEOUT
                )
            except (knowledge.KnowledgeError, http.client.HTTPException, OSError, ValueError):
                pass
            else:
                page = source.text
                title = title or source.title
        # The snippet leads: it is the search engine's own summary of the match.
        return _document(title, address, "\n".join(part for part in (snippet, page) if part.strip()))

    with ThreadPoolExecutor(max_workers=len(chosen)) as pool:
        documents = list(pool.map(read, chosen))
    return [document for document in documents if document is not None]


_SEARCHERS = {
    "wikipedia": _search_wikipedia,
    "searxng": _search_searxng,
    "brave": _search_brave,
}


def search(
    query: str,
    *,
    limit: int = MAX_RESULTS,
    opener: Optional[Opener] = None,
    timeout: float = DEFAULT_TIMEOUT,
    environ: Optional[Mapping[str, str]] = None,
) -> SearchResults:
    """Search the web for ``query`` and return the best pages as plain text."""

    env = os.environ if environ is None else environ
    terms = _one_line(query)[:MAX_QUERY_CHARS]
    if not terms:
        raise WebSearchError("There was nothing to search for.")
    provider = choose_provider(env)
    searcher = _SEARCHERS[provider]
    documents = searcher(terms, limit=limit, opener=opener, timeout=timeout, env=env)
    if not documents and provider == "wikipedia":
        # Wikipedia needs every word to match, so try again with any of them.
        words = content_words(terms)
        if len(words) > 1:
            documents = searcher(
                " OR ".join(words), limit=limit, opener=opener, timeout=timeout, env=env
            )
    return SearchResults(
        query=terms, provider=PROVIDER_NAMES[provider], documents=tuple(documents)
    )


# --- Summarising -------------------------------------------------------------

_ABBREVIATIONS = frozenset(
    """a.d a.m al approx apr aug b.a b.c b.sc c ca capt cf co col corp d.c dec dept
    dr e.g est etc feb fig ft gen gov hon i.e inc jan jr jul jun lt ltd m.a m.sc mar
    mr mrs ms mt no nos nov oct op p.m ph.d pp pres prof rev sep sept sgt sr st u.k
    u.n u.s univ vol vs""".split()
)
_BOUNDARY = re.compile(r"[.!?]+[\"'”’)\]]*\s+")
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
# (question pattern, what a sentence that answers it tends to contain).
_ANSWER_TYPES = (
    (
        re.compile(r"^(?:who|whom|whose)\b", re.IGNORECASE),
        re.compile(r"\b[A-Z][\w'’-]+(?:\s+(?:[A-Z]\.\s*)*[A-Z][\w'’-]+)+"),
    ),
    (
        re.compile(r"^(?:when|(?:in\s+)?(?:what|which)\s+(?:year|date|century))\b", re.IGNORECASE),
        re.compile(rf"\b(?:1\d{{3}}|20\d{{2}}|{_MONTHS})\b|\b\d{{1,2}}(?:st|nd|rd|th) century\b"),
    ),
    (
        re.compile(r"^how\s+(?:many|much|tall|long|old|far|big|large|high|deep|fast|heavy|wide)\b", re.IGNORECASE),
        re.compile(
            r"\d|\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen"
            r"|hundred|thousand|million|billion|trillion)\b",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(r"^where\b", re.IGNORECASE),
        re.compile(r"\b(?:in|at|near|from|on)\s+(?:the\s+)?[A-Z]|\blocated\b|\bborder"),
    ),
)


_WH_WORD = re.compile(r"^(who|whom|whose|what|which|when|where|why|how)\b", re.IGNORECASE)


def _echo_pattern(asked: str) -> Optional["re.Pattern[str]"]:
    """Match sentences that restate the question instead of answering it.

    "Disputes over who invented the telephone..." repeats "who invented the
    telephone?", while "Bell, who invented the telephone, ..." answers it, so
    only a wh-word that opens the sentence or follows a preposition counts.
    """

    wh = _WH_WORD.match(asked)
    words = search_terms(asked).split()
    if wh is None or not words:
        return None
    body = r"\s+".join(re.escape(word) for word in words)
    return re.compile(
        r"(?:^|\b(?:over|about|of|as\s+to|on|regarding|concerning|whether)\s+)"
        rf"{wh.group(1)}\s+(?:\w+\s+)?{body}",
        re.IGNORECASE,
    )


def split_sentences(text: str) -> List[str]:
    """Split ``text`` into sentences, keeping "Dr. Smith" and "U.S. law" whole."""

    sentences: List[str] = []
    for block in re.split(r"\n+", text or ""):
        block = re.sub(r"\s+", " ", block).strip()
        start = 0
        for boundary in _BOUNDARY.finditer(block):
            following = block[boundary.end() : boundary.end() + 1]
            if following and not (following.isupper() or following.isdigit() or following in "\"'“‘(["):
                continue
            if block[boundary.start()] == ".":
                before = re.search(r"([^\s(\"'“‘\[]+)$", block[start : boundary.start()])
                word = before.group(1).lower() if before else ""
                if word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha()):
                    continue
            sentences.append(block[start : boundary.end()].strip())
            start = boundary.end()
        if block[start:].strip():
            sentences.append(block[start:].strip())
    return sentences


def _tidy_sentence(sentence: str) -> str:
    tidy = re.sub(r"\[\s*(?:\d+|[a-z]|citation needed|note\s*\d+)\s*\]", "", sentence, flags=re.IGNORECASE)
    tidy = re.sub(r"\(\s*[;,]\s*", "(", tidy)
    tidy = re.sub(r"\s*[;,]\s*\)", ")", tidy)
    tidy = re.sub(r"\(\s*\)", "", tidy)
    tidy = re.sub(r"^[\-–—•*·]\s+", "", tidy.strip())
    tidy = re.sub(r"\s+([,.;:!?])", r"\1", tidy)
    return re.sub(r"\s{2,}", " ", tidy).strip()


def summarize(
    question: str,
    documents: Sequence[Document],
    *,
    limit: int = 3,
    exclude: Iterable[Tuple[int, int]] = (),
) -> List[Sentence]:
    """Pick up to ``limit`` sentences from ``documents`` that answer ``question``.

    Sentences are scored by how many of the question's keywords they mention,
    weighted so rare words count for more, with a bonus for opening sentences
    (which usually define the topic), for higher ranked pages and for the kind
    of fact the question wants (a name for "who", a date for "when", a number
    for "how many"), and a penalty for sentences that merely restate the
    question. Near duplicates are dropped, and the picks are returned in
    reading order.
    """

    wanted = keywords(question)
    asked = strip_lead_ins(question)
    shape = next((answer for kind, answer in _ANSWER_TYPES if kind.match(asked)), None)
    echo = _echo_pattern(asked)
    pool = []
    for source, document in enumerate(documents):
        for position, raw in enumerate(split_sentences(document.text)):
            text = _tidy_sentence(raw)
            words = _words(text)
            if not 4 <= len(words) <= 80 or not re.search(r"[^\W\d_]", text):
                continue
            pool.append((source, position, text, {_stem(word) for word in words}, len(words)))
    if not pool:
        return []
    weights = {
        stem: math.log(1 + len(pool) / (1 + sum(1 for item in pool if stem in item[3])))
        for stem in wanted
    }
    total = sum(weights.values())
    skip = {tuple(item) for item in exclude}
    scored = []
    for source, position, text, stems, length in pool:
        if (source, position) in skip:
            continue
        score = sum(weights[stem] for stem in wanted if stem in stems) / total if total else 0.0
        score += 0.35 if position == 0 else 0.1 if position < 3 else 0.0
        score += 0.15 / (1 + source)
        if shape is not None and shape.search(text):
            score += 0.25
        if echo is not None and echo.search(text):
            score *= 0.5
        if length < 6 or length > 50:
            score *= 0.75
        scored.append((score, source, position, text, stems))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    chosen: List[Tuple[float, int, int, str, set]] = []
    for item in scored:
        stems = item[4]
        if any(len(stems & other[4]) / max(1, len(stems | other[4])) > 0.6 for other in chosen):
            continue
        chosen.append(item)
        if len(chosen) == limit:
            break
    chosen.sort(key=lambda item: (item[1], item[2]))
    return [Sentence(text=text, source=source, position=position) for _, source, position, text, _ in chosen]


def cite(sentences: Sequence[Sentence]) -> str:
    """Join ``sentences`` with a ``[n]`` marker after each run from one source."""

    parts = []
    for index, sentence in enumerate(sentences):
        following = sentences[index + 1] if index + 1 < len(sentences) else None
        marker = "" if following and following.source == sentence.source else f" [{sentence.source + 1}]"
        parts.append(sentence.text + marker)
    return " ".join(parts)


def source_lines(documents: Sequence[Document], indexes: Optional[Iterable[int]] = None) -> List[str]:
    """``[n] Title - URL`` lines for the given documents (all of them by default)."""

    chosen = sorted(set(indexes)) if indexes is not None else range(len(documents))
    return [f"[{index + 1}] {documents[index].title} - {documents[index].url}" for index in chosen]


def format_answer(
    question: str,
    results: SearchResults,
    sentences: Sequence[Sentence],
) -> str:
    """Write the reply: what was searched, the cited summary and its sources."""

    lines = [
        f"I searched {results.provider} for '{results.query}'. Here is a summary:",
        cite(sentences),
        "",
        "Sources:",
        *source_lines(results.documents, (sentence.source for sentence in sentences)),
    ]
    if results.provider == PROVIDER_NAMES["wikipedia"] and is_timely(question):
        lines += [
            "",
            "Note: Wikipedia is an encyclopedia, not a live feed, so this may be out of "
            "date. Set JARVIS_BRAVE_API_KEY or JARVIS_SEARXNG_URL to search the live web.",
        ]
    lines += [
        "",
        "(Automatic summary: check the sources. Say 'tell me more', 'sources' or "
        "'learn that'.)",
    ]
    return "\n".join(lines)
