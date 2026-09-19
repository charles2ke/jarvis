"""A small offline atlas: countries, capitals, continents and currencies.

The data set is deliberately compact and dependency free. Population figures
are rounded estimates in millions and are only meant to give a sense of scale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Country:
    """A single entry of the atlas."""

    name: str
    capital: str
    continent: str
    currency: str
    population_millions: float
    aliases: Tuple[str, ...] = field(default_factory=tuple)


COUNTRIES: Tuple[Country, ...] = (
    Country("Argentina", "Buenos Aires", "South America", "Argentine peso", 46.0),
    Country("Australia", "Canberra", "Oceania", "Australian dollar", 26.0),
    Country("Austria", "Vienna", "Europe", "euro", 9.1),
    Country("Bangladesh", "Dhaka", "Asia", "Bangladeshi taka", 171.0),
    Country("Belgium", "Brussels", "Europe", "euro", 11.7),
    Country("Brazil", "Brasília", "South America", "Brazilian real", 216.0, ("brasil",)),
    Country("Canada", "Ottawa", "North America", "Canadian dollar", 39.0),
    Country("Chile", "Santiago", "South America", "Chilean peso", 19.6),
    Country("China", "Beijing", "Asia", "renminbi", 1425.0, ("prc", "people's republic of china")),
    Country("Colombia", "Bogotá", "South America", "Colombian peso", 52.0),
    Country("Czechia", "Prague", "Europe", "Czech koruna", 10.5, ("czech republic",)),
    Country("Denmark", "Copenhagen", "Europe", "Danish krone", 5.9),
    Country("Egypt", "Cairo", "Africa", "Egyptian pound", 112.0),
    Country("Ethiopia", "Addis Ababa", "Africa", "Ethiopian birr", 126.0),
    Country("Finland", "Helsinki", "Europe", "euro", 5.6),
    Country("France", "Paris", "Europe", "euro", 68.0),
    Country("Germany", "Berlin", "Europe", "euro", 84.0),
    Country("Ghana", "Accra", "Africa", "Ghanaian cedi", 34.0),
    Country("Greece", "Athens", "Europe", "euro", 10.4),
    Country("India", "New Delhi", "Asia", "Indian rupee", 1429.0),
    Country("Indonesia", "Jakarta", "Asia", "Indonesian rupiah", 278.0),
    Country("Iran", "Tehran", "Asia", "Iranian rial", 89.0),
    Country("Ireland", "Dublin", "Europe", "euro", 5.3),
    Country("Israel", "Jerusalem", "Asia", "Israeli new shekel", 9.7),
    Country("Italy", "Rome", "Europe", "euro", 59.0),
    Country("Japan", "Tokyo", "Asia", "Japanese yen", 123.0),
    Country("Kenya", "Nairobi", "Africa", "Kenyan shilling", 55.0),
    Country("Malaysia", "Kuala Lumpur", "Asia", "Malaysian ringgit", 34.0),
    Country("Mexico", "Mexico City", "North America", "Mexican peso", 128.0),
    Country("Morocco", "Rabat", "Africa", "Moroccan dirham", 37.0),
    Country("Netherlands", "Amsterdam", "Europe", "euro", 17.8, ("holland", "the netherlands")),
    Country("New Zealand", "Wellington", "Oceania", "New Zealand dollar", 5.2),
    Country("Nigeria", "Abuja", "Africa", "Nigerian naira", 224.0),
    Country("Norway", "Oslo", "Europe", "Norwegian krone", 5.5),
    Country("Pakistan", "Islamabad", "Asia", "Pakistani rupee", 240.0),
    Country("Peru", "Lima", "South America", "Peruvian sol", 34.0),
    Country("Philippines", "Manila", "Asia", "Philippine peso", 117.0),
    Country("Poland", "Warsaw", "Europe", "Polish złoty", 36.7),
    Country("Portugal", "Lisbon", "Europe", "euro", 10.2),
    Country("Romania", "Bucharest", "Europe", "Romanian leu", 19.0),
    Country("Russia", "Moscow", "Europe", "Russian ruble", 144.0),
    Country("Saudi Arabia", "Riyadh", "Asia", "Saudi riyal", 36.9),
    Country("Singapore", "Singapore", "Asia", "Singapore dollar", 6.0),
    Country("South Africa", "Pretoria", "Africa", "South African rand", 60.0),
    Country("South Korea", "Seoul", "Asia", "South Korean won", 51.8, ("korea", "republic of korea")),
    Country("Spain", "Madrid", "Europe", "euro", 47.5),
    Country("Sweden", "Stockholm", "Europe", "Swedish krona", 10.6),
    Country("Switzerland", "Bern", "Europe", "Swiss franc", 8.8),
    Country("Thailand", "Bangkok", "Asia", "Thai baht", 71.8),
    Country("Turkey", "Ankara", "Asia", "Turkish lira", 85.8, ("türkiye",)),
    Country("Ukraine", "Kyiv", "Europe", "Ukrainian hryvnia", 37.0),
    Country(
        "United Arab Emirates",
        "Abu Dhabi",
        "Asia",
        "UAE dirham",
        9.5,
        ("uae", "emirates"),
    ),
    Country(
        "United Kingdom",
        "London",
        "Europe",
        "pound sterling",
        67.7,
        ("uk", "britain", "great britain", "england"),
    ),
    Country(
        "United States",
        "Washington, D.C.",
        "North America",
        "US dollar",
        335.0,
        ("usa", "us", "u.s.", "u.s.a.", "america", "united states of america"),
    ),
    Country("Vietnam", "Hanoi", "Asia", "Vietnamese dong", 98.9, ("viet nam",)),
)


CONTINENTS: Tuple[str, ...] = (
    "Africa",
    "Asia",
    "Europe",
    "North America",
    "Oceania",
    "South America",
    "Antarctica",
)


_ARTICLES = ("the ", "a ", "an ")


def normalise(value: str) -> str:
    """Return a lowercase, punctuation-light key for ``value``."""

    lowered = (value or "").strip().lower()
    lowered = lowered.strip(" \t.,!?;:'\"")
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _strip_article(value: str) -> str:
    for article in _ARTICLES:
        if value.startswith(article):
            return value[len(article) :]
    return value


def _index() -> Dict[str, Country]:
    index: Dict[str, Country] = {}
    for country in COUNTRIES:
        for key in (country.name, *country.aliases):
            index[normalise(key)] = country
    return index


_BY_NAME: Dict[str, Country] = _index()


def find_country(name: str) -> Optional[Country]:
    """Return the country matching ``name`` or one of its aliases."""

    key = normalise(name)
    if not key:
        return None
    country = _BY_NAME.get(key) or _BY_NAME.get(_strip_article(key))
    return country


def find_by_capital(capital: str) -> Optional[Country]:
    """Return the country whose capital is ``capital``."""

    key = _strip_article(normalise(capital))
    if not key:
        return None
    for country in COUNTRIES:
        capital_key = normalise(country.capital)
        if key == capital_key:
            return country
        # Allow 'washington' for 'Washington, D.C.'.
        if key == capital_key.split(",")[0].strip():
            return country
    return None


def find_continent(name: str) -> Optional[str]:
    """Return the canonical continent name for ``name``."""

    key = _strip_article(normalise(name))
    aliases = {
        "america": None,  # Ambiguous: handled as a country alias instead.
        "the americas": None,
        "australia": "Oceania",
        "australasia": "Oceania",
    }
    if key in aliases:
        return aliases[key]
    for continent in CONTINENTS:
        if key == normalise(continent):
            return continent
    return None


def countries_in(continent: str) -> List[Country]:
    """Return the known countries of ``continent``, sorted by name."""

    canonical = find_continent(continent)
    if canonical is None:
        return []
    return sorted(
        (country for country in COUNTRIES if country.continent == canonical),
        key=lambda country: country.name,
    )


_DEFINITE_ARTICLE_NAMES = frozenset(
    {"Netherlands", "United Arab Emirates", "United Kingdom", "United States"}
)


def display_name(country: Country) -> str:
    """Return the country name with a definite article where English needs one."""

    if country.name in _DEFINITE_ARTICLE_NAMES:
        return f"the {country.name}"
    return country.name


def sentence(text: str) -> str:
    """Terminate ``text`` with a full stop, avoiding a doubled one."""

    text = text.rstrip()
    if text.endswith((".", "!", "?")):
        return text
    return text + "."


def format_population(country: Country) -> str:
    """Return a human readable population estimate for ``country``."""

    millions = country.population_millions
    if millions >= 1000:
        return f"about {millions / 1000:.2f} billion people"
    if millions >= 10:
        return f"about {millions:.0f} million people"
    return f"about {millions:.1f} million people"


def describe(country: Country) -> str:
    """Return a one line profile of ``country``."""

    name = display_name(country)
    return sentence(
        f"{name} is in {country.continent}. Its capital is "
        f"{country.capital}, it uses the {country.currency}, and it has "
        f"{format_population(country)}"
    )


def known_countries() -> Sequence[str]:
    """Return the names of every country in the atlas, sorted."""

    return tuple(sorted(country.name for country in COUNTRIES))
