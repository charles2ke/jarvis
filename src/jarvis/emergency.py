"""Emergency telephone numbers for every country, and ways to reach them.

The data set is offline and hand-curated from public listings. Emergency
numbers do change, and some countries route calls differently by region, so
Jarvis always reminds people to confirm the number locally. On a mobile phone
``112`` (and ``911`` in many places) is accepted across most of the world.

Jarvis cannot place a call or send a message itself. It builds the standard
``tel:``, ``sms:`` and ``mailto:`` links and, only when the user has opted in
with ``JARVIS_DIAL_ENABLED``, hands them to the operating system so the phone,
messaging or email app opens with the number or message filled in. Nothing is
sent without the user pressing call or send in that app.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

ENABLE_ENV_VAR = "JARVIS_DIAL_ENABLED"
COMMAND_ENV_VAR = "JARVIS_DIAL_COMMAND"
DEFAULT_TIMEOUT = 15.0

_TRUTHY = {"1", "true", "yes", "on", "enable", "enabled"}

SERVICES: Tuple[str, ...] = ("police", "ambulance", "fire")

_SERVICE_ALIASES: Dict[str, str] = {
    "police": "police",
    "cops": "police",
    "cop": "police",
    "ambulance": "ambulance",
    "paramedics": "ambulance",
    "paramedic": "ambulance",
    "medical": "ambulance",
    "doctor": "ambulance",
    "fire": "fire",
    "fire brigade": "fire",
    "fire department": "fire",
    "fire service": "fire",
    "firefighters": "fire",
    "fire fighters": "fire",
}

DISCLAIMER = (
    "Numbers can change and may differ by region, so confirm them locally when "
    "you can."
)

UNIVERSAL_HINT = (
    "On a mobile phone 112 reaches emergency services across Europe and in many "
    "other countries, and 911 does across North America and in many others."
)


class EmergencyError(RuntimeError):
    """Raised when a number, link or message cannot be prepared or opened."""


@dataclass(frozen=True)
class EmergencySMS:
    """A verified emergency SMS destination, separate from voice numbers."""

    number: str
    requirements: str
    source: str


SMS_DESTINATIONS: Dict[str, EmergencySMS] = {
    "France": EmergencySMS(
        "114",
        "114 is for people with difficulty hearing or speaking, even temporarily, including "
        "when it is unsafe to speak aloud.",
        "https://www.service-public.gouv.fr/particuliers/vosdroits/F33954",
    ),
    "United Kingdom": EmergencySMS(
        "999",
        "999 emergencySMS is for people who are deaf, hard of hearing or have "
        "speech difficulties. You must register your mobile first: text 'register' "
        "to 999, follow the instructions and wait for registration confirmation "
        "before relying on this service.",
        "https://www.relayuk.bt.com/how-to-use-relay-uk/contact-999-using-relay-uk.html",
    ),
}


@dataclass(frozen=True)
class EmergencyNumbers:
    """The emergency numbers of one country."""

    country: str
    police: str
    ambulance: str
    fire: str
    general: str = ""
    aliases: Tuple[str, ...] = field(default_factory=tuple)
    note: str = ""

    def number_for(self, service: str = "") -> str:
        """Return the number for ``service`` (or the main number)."""

        key = service_key(service) if service else ""
        if key:
            value = getattr(self, key)
            if value:
                return value
        return self.main_number()

    def main_number(self) -> str:
        """Return the number to dial when the service is not specified."""

        if self.police and self.police == self.ambulance == self.fire:
            return self.police
        return self.general or self.police or self.ambulance or self.fire

    def describe(self) -> str:
        """Return a one paragraph summary of the numbers."""

        name = display_name(self.country)
        if self.police and self.police == self.ambulance == self.fire:
            text = f"In {name}, dial {self.police} for police, ambulance and fire"
        else:
            parts = []
            for service in SERVICES:
                value = getattr(self, service)
                parts.append(
                    f"{service} {value}" if value else f"{service}: no single national number"
                )
            text = f"Emergency numbers in {name}: " + ", ".join(parts)
        extra = []
        main = self.police if self.police == self.ambulance == self.fire else ""
        if self.general and self.general != main:
            extra.append(f"{self.general} also works as a general emergency number")
        if self.note:
            extra.append(self.note)
        if extra:
            text += " (" + "; ".join(extra) + ")"
        return text + "."


def _n(
    country: str,
    police: str,
    ambulance: str,
    fire: str,
    general: str = "",
    aliases: Sequence[str] = (),
    note: str = "",
) -> EmergencyNumbers:
    return EmergencyNumbers(country, police, ambulance, fire, general, tuple(aliases), note)


def _all(country: str, number: str, general: str = "", aliases: Sequence[str] = (), note: str = ""):
    return _n(country, number, number, number, general, aliases, note)


NUMBERS: Tuple[EmergencyNumbers, ...] = (
    # Africa
    _n("Algeria", "17", "14", "14", aliases=("algérie",), note="1548 reaches the gendarmerie"),
    _n("Angola", "113", "112", "115"),
    _n("Benin", "117", "112", "118"),
    _n("Botswana", "999", "997", "998"),
    _n("Burkina Faso", "17", "112", "18"),
    _n("Burundi", "117", "112", "118"),
    _n("Cabo Verde", "132", "130", "131", aliases=("cape verde",)),
    _n("Cameroon", "117", "119", "118"),
    _n("Central African Republic", "117", "1220", "118", aliases=("car",)),
    _n("Chad", "17", "2251-4242", "18"),
    _n("Comoros", "17", "772-03-73", "18"),
    _n(
        "Republic of the Congo",
        "117",
        "",
        "118",
        aliases=("congo", "congo-brazzaville", "congo brazzaville"),
    ),
    _n(
        "Democratic Republic of the Congo",
        "112",
        "",
        "118",
        aliases=("drc", "dr congo", "congo-kinshasa", "congo kinshasa"),
    ),
    _n("Djibouti", "17", "19", "18"),
    _n("Egypt", "122", "123", "180", general="112"),
    _n("Equatorial Guinea", "114", "115", "112"),
    _n("Eritrea", "113", "114", "116"),
    _n("Eswatini", "999", "977", "933", aliases=("swaziland",)),
    _n("Ethiopia", "991", "907", "939"),
    _n("Gabon", "1730", "1300", "18"),
    _n("Gambia", "117", "116", "118", aliases=("the gambia",)),
    _n("Ghana", "191", "193", "192", general="112"),
    _n("Guinea", "117", "18", "442-020"),
    _n("Guinea-Bissau", "117", "119", "118", aliases=("guinea bissau",)),
    _n(
        "Côte d'Ivoire",
        "110",
        "185",
        "180",
        aliases=("cote d'ivoire", "cote divoire", "ivory coast"),
        note="111 and 170 also reach the police",
    ),
    _all("Kenya", "999", general="112", note="911 also works from mobiles"),
    _n("Lesotho", "123", "121", "122"),
    _all("Liberia", "911"),
    _n("Libya", "1515", "193", "", aliases=("libyan arab jamahiriya",)),
    _n("Madagascar", "117", "124", "118"),
    _n("Malawi", "997", "998", "999"),
    _n("Mali", "17", "15", "18"),
    _n("Mauritania", "117", "101", "118"),
    _n("Mauritius", "999", "114", "995", general="112"),
    _n("Morocco", "19", "15", "15", general="112", note="177 reaches the gendarmerie"),
    _n("Mozambique", "119", "117", "198"),
    _n(
        "Namibia",
        "10111",
        "",
        "",
        general="112",
        note="ambulance and fire numbers depend on the town",
    ),
    _n("Niger", "17", "15", "18"),
    _all("Nigeria", "112", note="199 also works"),
    _n("Rwanda", "112", "912", "112"),
    _all("São Tomé and Príncipe", "112", aliases=("sao tome and principe", "sao tome")),
    _n("Senegal", "17", "15", "18"),
    _all("Seychelles", "999"),
    _n("Sierra Leone", "019", "999", "999", note="numbers vary by area"),
    _n("Somalia", "888", "999", "555"),
    _n("South Africa", "10111", "10177", "10177", general="112"),
    _all("South Sudan", "999"),
    _all("Sudan", "999"),
    _all("Tanzania", "112", aliases=("united republic of tanzania",)),
    _n("Togo", "117", "8200", "118"),
    _n("Tunisia", "197", "190", "198"),
    _all("Uganda", "999", general="112"),
    _n("Zambia", "999", "992", "993", general="112"),
    _n("Zimbabwe", "995", "994", "993", general="999"),
    # Americas
    _all("Antigua and Barbuda", "911", note="999 also works"),
    _n("Argentina", "101", "107", "100", general="911"),
    _all("Bahamas", "919", general="911", aliases=("the bahamas",)),
    _n("Barbados", "211", "511", "311"),
    _all("Belize", "911"),
    _n("Bolivia", "110", "118", "119"),
    _n("Brazil", "190", "192", "193", aliases=("brasil",)),
    _all("Canada", "911"),
    _n("Chile", "133", "131", "132"),
    _all("Colombia", "123"),
    _all("Costa Rica", "911"),
    _n("Cuba", "106", "104", "105"),
    _all("Dominica", "999"),
    _all("Dominican Republic", "911"),
    _all("Ecuador", "911"),
    _all("El Salvador", "911"),
    _all("Grenada", "911"),
    _n("Guatemala", "110", "128", "122"),
    _n("Guyana", "911", "913", "912"),
    _n("Haiti", "114", "116", "115"),
    _all("Honduras", "911"),
    _n("Jamaica", "119", "110", "110"),
    _all("Mexico", "911", aliases=("méxico",)),
    _n("Nicaragua", "118", "128", "115"),
    _all("Panama", "911"),
    _all("Paraguay", "911"),
    _n("Peru", "105", "106", "116"),
    _all("Saint Kitts and Nevis", "911", aliases=("st kitts and nevis", "st kitts")),
    _all("Saint Lucia", "999", general="911", aliases=("st lucia",)),
    _all(
        "Saint Vincent and the Grenadines",
        "999",
        general="911",
        aliases=("st vincent and the grenadines", "st vincent"),
    ),
    _all("Suriname", "115"),
    _n("Trinidad and Tobago", "999", "811", "990", aliases=("trinidad",)),
    _all(
        "United States",
        "911",
        aliases=("usa", "us", "u.s.", "u.s.a.", "america", "united states of america"),
        note="you can text 911 in many, but not all, areas",
    ),
    _all("Uruguay", "911"),
    _all("Venezuela", "911"),
    # Asia and the Middle East
    _n("Afghanistan", "119", "102", "119"),
    _n("Armenia", "102", "103", "101", general="112"),
    _n("Azerbaijan", "102", "103", "101", general="112"),
    _all("Bahrain", "999"),
    _all("Bangladesh", "999"),
    _n("Bhutan", "113", "112", "110"),
    _n("Brunei", "993", "991", "995", aliases=("brunei darussalam",)),
    _n("Cambodia", "117", "119", "118"),
    _n("China", "110", "120", "119", aliases=("prc", "people's republic of china")),
    _all("Georgia", "112"),
    _n("India", "100", "108", "101", general="112"),
    _n("Indonesia", "110", "118", "113", general="112", note="119 also reaches an ambulance"),
    _n("Iran", "110", "115", "125"),
    _n("Iraq", "104", "122", "115"),
    _n("Israel", "100", "101", "102"),
    _n("Japan", "110", "119", "119"),
    _all("Jordan", "911"),
    _n("Kazakhstan", "102", "103", "101", general="112"),
    _all("Kuwait", "112"),
    _n("Kyrgyzstan", "102", "103", "101", general="112"),
    _n("Laos", "191", "195", "190", aliases=("lao pdr",)),
    _n("Lebanon", "112", "140", "175"),
    _n("Malaysia", "999", "999", "994", general="112"),
    _n("Maldives", "119", "102", "118"),
    _n("Mongolia", "102", "103", "101"),
    _n("Myanmar", "199", "192", "191", aliases=("burma",)),
    _n("Nepal", "100", "102", "101"),
    _n(
        "North Korea",
        "112",
        "119",
        "119",
        aliases=("dprk", "democratic people's republic of korea"),
        note="information about this country is limited",
    ),
    _all("Oman", "9999"),
    _n("Pakistan", "15", "115", "16", note="1122 reaches Rescue 1122 in most provinces"),
    _n("Palestine", "100", "101", "102", aliases=("state of palestine",)),
    _all("Philippines", "911", aliases=("the philippines",)),
    _all("Qatar", "999"),
    _n("Saudi Arabia", "999", "997", "998", general="911"),
    _n("Singapore", "999", "995", "995"),
    _n("South Korea", "112", "119", "119", aliases=("korea", "republic of korea")),
    _n("Sri Lanka", "119", "1990", "110"),
    _n("Syria", "112", "110", "113"),
    _n("Taiwan", "110", "119", "119"),
    _n("Tajikistan", "102", "103", "101", general="112"),
    _n("Thailand", "191", "1669", "199"),
    _n("Timor-Leste", "112", "110", "115", aliases=("east timor", "timor leste")),
    _all("Turkey", "112", aliases=("türkiye", "turkiye")),
    _n("Turkmenistan", "02", "03", "01"),
    _n("United Arab Emirates", "999", "998", "997", aliases=("uae", "emirates")),
    _n("Uzbekistan", "102", "103", "101", general="112"),
    _n("Vietnam", "113", "115", "114", aliases=("viet nam",)),
    _n("Yemen", "194", "191", "191"),
    _all("Hong Kong", "999"),
    _all("Macau", "999", aliases=("macao",)),
    # Europe
    _n("Albania", "129", "127", "128", general="112"),
    _n("Andorra", "110", "118", "118", general="112"),
    _n("Austria", "133", "144", "122", general="112"),
    _n("Belarus", "102", "103", "101", general="112"),
    _n("Belgium", "101", "112", "112", general="112"),
    _n("Bosnia and Herzegovina", "122", "124", "123", general="112", aliases=("bosnia",)),
    _n("Bulgaria", "166", "150", "160", general="112"),
    _n("Croatia", "192", "194", "193", general="112"),
    _all("Cyprus", "112", note="199 also works"),
    _n("Czechia", "158", "155", "150", general="112", aliases=("czech republic",)),
    _all("Denmark", "112"),
    _n("Estonia", "112", "112", "112", general="112"),
    _all("Finland", "112"),
    _n("France", "17", "15", "18", general="112", note="114 accepts text messages for deaf callers"),
    _n("Germany", "110", "112", "112", general="112"),
    _n("Greece", "100", "166", "199", general="112"),
    _n("Hungary", "107", "104", "105", general="112"),
    _all("Iceland", "112"),
    _all("Ireland", "999", general="112"),
    _n("Italy", "113", "118", "115", general="112"),
    _n("Kosovo", "192", "194", "193", general="112"),
    _n("Latvia", "110", "113", "112", general="112"),
    _n("Liechtenstein", "117", "144", "118", general="112"),
    _all("Lithuania", "112"),
    _n("Luxembourg", "113", "112", "112", general="112"),
    _all("Malta", "112"),
    _all("Moldova", "112"),
    _n("Monaco", "17", "18", "18", general="112"),
    _n("Montenegro", "122", "124", "123", general="112"),
    _all("Netherlands", "112", aliases=("holland", "the netherlands")),
    _n("North Macedonia", "192", "194", "193", general="112", aliases=("macedonia",)),
    _n("Norway", "112", "113", "110"),
    _n("Poland", "997", "999", "998", general="112"),
    _all("Portugal", "112"),
    _all("Romania", "112"),
    _n("Russia", "102", "103", "101", general="112", aliases=("russian federation",)),
    _n("San Marino", "113", "118", "115", general="112"),
    _n("Serbia", "192", "194", "193", general="112"),
    _n("Slovakia", "158", "155", "150", general="112"),
    _n("Slovenia", "113", "112", "112", general="112"),
    _n("Spain", "091", "061", "080", general="112", note="local numbers vary by region"),
    _all("Sweden", "112"),
    _n("Switzerland", "117", "144", "118", general="112"),
    _n("Ukraine", "102", "103", "101", general="112"),
    _all(
        "United Kingdom",
        "999",
        general="112",
        aliases=("uk", "britain", "great britain", "england", "scotland", "wales", "northern ireland"),
        note="deaf and speech-impaired people can register for emergencySMS by texting 'register' to 999",
    ),
    _n("Vatican City", "113", "118", "115", general="112", aliases=("vatican", "holy see")),
    # Oceania
    _all("Australia", "000", general="112", note="106 is the text relay service"),
    _n("Fiji", "917", "911", "910"),
    _n("Kiribati", "192", "194", "193"),
    _all("Marshall Islands", "911", note="services are limited outside Majuro and Ebeye"),
    _all("Micronesia", "911", aliases=("federated states of micronesia",)),
    _n("Nauru", "110", "111", "112"),
    _all("New Zealand", "111", aliases=("aotearoa",)),
    _all("Palau", "911"),
    _n(
        "Papua New Guinea",
        "000",
        "111",
        "110",
        general="112",
        aliases=("png",),
    ),
    _n("Samoa", "995", "996", "994", general="911"),
    _n("Solomon Islands", "999", "911", "988"),
    _n("Tonga", "922", "933", "999"),
    _all("Tuvalu", "911"),
    _n("Vanuatu", "111", "112", "113"),
)


_DEFINITE_ARTICLE_NAMES = frozenset(
    {
        "Bahamas",
        "Central African Republic",
        "Comoros",
        "Democratic Republic of the Congo",
        "Dominican Republic",
        "Gambia",
        "Maldives",
        "Marshall Islands",
        "Netherlands",
        "Philippines",
        "Republic of the Congo",
        "Seychelles",
        "Solomon Islands",
        "United Arab Emirates",
        "United Kingdom",
        "United States",
    }
)


def display_name(country: str) -> str:
    """Return ``country`` with the definite article English expects."""

    return f"the {country}" if country in _DEFINITE_ARTICLE_NAMES else country


def _normalise(value: str) -> str:
    lowered = (value or "").strip().lower()
    lowered = lowered.strip(" \t.,!?;:'\"")
    lowered = lowered.replace("’", "'")
    lowered = re.sub(r"^(?:the)\s+", "", lowered)
    return re.sub(r"\s+", " ", lowered)


def _build_index() -> Dict[str, EmergencyNumbers]:
    index: Dict[str, EmergencyNumbers] = {}
    for entry in NUMBERS:
        for key in (entry.country, *entry.aliases):
            index[_normalise(key)] = entry
    return index


_BY_NAME: Dict[str, EmergencyNumbers] = _build_index()


def find(country: str) -> Optional[EmergencyNumbers]:
    """Return the emergency numbers for ``country`` or one of its aliases."""

    key = _normalise(country)
    if not key:
        return None
    return _BY_NAME.get(key)


def countries() -> List[str]:
    """Return every country Jarvis knows emergency numbers for, sorted."""

    return sorted(entry.country for entry in NUMBERS)


def service_key(service: str) -> str:
    """Return ``police``, ``ambulance`` or ``fire`` for ``service``, or ``""``."""

    key = re.sub(r"\s+", " ", (service or "").strip().lower())
    key = re.sub(r"^(?:the|an?)\s+", "", key)
    return _SERVICE_ALIASES.get(key, "")


def dial_digits(number: str) -> str:
    """Return ``number`` reduced to what a phone dials (digits and a leading +)."""

    raw = (number or "").strip()
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        raise EmergencyError("That is not a phone number I can dial.")
    if len(digits) > 15:
        raise EmergencyError("That phone number is too long.")
    return f"+{digits}" if raw.startswith("+") else digits


def tel_link(number: str) -> str:
    """Return a ``tel:`` link that opens the phone app with ``number``."""

    return f"tel:{dial_digits(number)}"


def sms_link(number: str, body: str = "") -> str:
    """Return an ``sms:`` link that opens a text message to ``number``."""

    link = f"sms:{dial_digits(number)}"
    if body:
        link += "?body=" + quote(body, safe="")
    return link


_EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


def is_email(address: str) -> bool:
    """Return ``True`` when ``address`` looks like a single email address."""

    return bool(_EMAIL.match((address or "").strip()))


def mailto_link(address: str, subject: str = "", body: str = "") -> str:
    """Return a ``mailto:`` link with ``subject`` and ``body`` filled in."""

    address = (address or "").strip()
    if not is_email(address):
        raise EmergencyError(f"'{address}' does not look like an email address.")
    params = []
    if subject:
        params.append("subject=" + quote(subject, safe=""))
    if body:
        params.append("body=" + quote(body, safe=""))
    link = f"mailto:{quote(address, safe='@')}"
    return link + ("?" + "&".join(params) if params else "")


def is_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """Return ``True`` when opening phone, SMS and email links is opted into."""

    env = os.environ if environ is None else environ
    return str(env.get(ENABLE_ENV_VAR, "")).strip().lower() in _TRUTHY


def opener_command(
    environ: Optional[Mapping[str, str]] = None, platform: Optional[str] = None
) -> List[str]:
    """Return the command that hands a link to the operating system."""

    env = os.environ if environ is None else environ
    configured = (env.get(COMMAND_ENV_VAR) or "").strip()
    if configured:
        try:
            parts = shlex.split(configured)
        except ValueError as exc:
            raise EmergencyError(f"I could not read {COMMAND_ENV_VAR}: {exc}") from exc
        if parts:
            return parts
    platform = sys.platform if platform is None else platform
    if platform == "darwin":
        return ["open"]
    if platform.startswith("win"):
        return ["rundll32", "url.dll,FileProtocolHandler"]
    return ["xdg-open"]


def open_link(link: str, *, timeout: float = DEFAULT_TIMEOUT) -> None:
    """Hand ``link`` to the operating system's phone, SMS or email app."""

    if not re.match(r"^(?:tel|sms|mailto):[^\s]+$", link or ""):
        raise EmergencyError("I can only open tel:, sms: and mailto: links.")
    command = [*opener_command(), link]
    try:
        subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)
    except FileNotFoundError as exc:
        raise EmergencyError(f"I could not find '{command[0]}' to open the link.") from exc
    except subprocess.TimeoutExpired as exc:
        raise EmergencyError("Opening the link took too long.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = f"'{command[0]}' could not open the link"
        raise EmergencyError(f"{message}: {detail}" if detail else f"{message}.") from exc
    except OSError as exc:
        raise EmergencyError(f"I could not open the link: {exc}") from exc


def handoff(
    link: str,
    *,
    opener: Optional[Callable[[str], object]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> str:
    """Open ``link`` when enabled and return a sentence saying what happened."""

    if not is_enabled(environ):
        return (
            f"Open {link} on your phone or computer to continue. "
            f"Set {ENABLE_ENV_VAR}=1 to let me open it for you."
        )
    (opener or open_link)(link)
    return f"I opened {link} — press call or send in the app to finish."


def share_text(entry: EmergencyNumbers) -> str:
    """Return a plain text summary suitable for a message or email body."""

    return f"{entry.describe()} {DISCLAIMER}"
