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


@dataclass(frozen=True)
class TimeZone:
    """The civil time a place keeps."""

    zone: str
    utc_offset: str
    note: str = ""


TIMEZONES: Dict[str, TimeZone] = {
    "Argentina": TimeZone("America/Argentina/Buenos_Aires", "UTC-03:00"),
    "Australia": TimeZone(
        "Australia/Sydney",
        "UTC+10:00",
        "Australia spans UTC+08:00 in Perth to UTC+10:00 in Sydney, with a "
        "half-hour zone in Adelaide.",
    ),
    "Austria": TimeZone("Europe/Vienna", "UTC+01:00"),
    "Bangladesh": TimeZone("Asia/Dhaka", "UTC+06:00"),
    "Belgium": TimeZone("Europe/Brussels", "UTC+01:00"),
    "Brazil": TimeZone(
        "America/Sao_Paulo", "UTC-03:00", "Brazil spans UTC-05:00 to UTC-02:00."
    ),
    "Canada": TimeZone(
        "America/Toronto",
        "UTC-05:00",
        "Canada spans six zones, from UTC-08:00 in Vancouver to UTC-03:30 in "
        "Newfoundland.",
    ),
    "Chile": TimeZone("America/Santiago", "UTC-04:00"),
    "China": TimeZone(
        "Asia/Shanghai",
        "UTC+08:00",
        "All of China keeps a single official time despite spanning five "
        "geographic zones.",
    ),
    "Colombia": TimeZone("America/Bogota", "UTC-05:00"),
    "Czechia": TimeZone("Europe/Prague", "UTC+01:00"),
    "Denmark": TimeZone("Europe/Copenhagen", "UTC+01:00"),
    "Egypt": TimeZone("Africa/Cairo", "UTC+02:00"),
    "Ethiopia": TimeZone("Africa/Addis_Ababa", "UTC+03:00"),
    "Finland": TimeZone("Europe/Helsinki", "UTC+02:00"),
    "France": TimeZone(
        "Europe/Paris",
        "UTC+01:00",
        "Counting its overseas territories, France uses more time zones than "
        "any other country.",
    ),
    "Germany": TimeZone("Europe/Berlin", "UTC+01:00"),
    "Ghana": TimeZone("Africa/Accra", "UTC+00:00"),
    "Greece": TimeZone("Europe/Athens", "UTC+02:00"),
    "India": TimeZone(
        "Asia/Kolkata",
        "UTC+05:30",
        "India keeps one nationwide zone offset by half an hour.",
    ),
    "Indonesia": TimeZone(
        "Asia/Jakarta", "UTC+07:00", "Indonesia spans UTC+07:00 to UTC+09:00."
    ),
    "Iran": TimeZone("Asia/Tehran", "UTC+03:30"),
    "Ireland": TimeZone("Europe/Dublin", "UTC+00:00"),
    "Israel": TimeZone("Asia/Jerusalem", "UTC+02:00"),
    "Italy": TimeZone("Europe/Rome", "UTC+01:00"),
    "Japan": TimeZone(
        "Asia/Tokyo", "UTC+09:00", "Japan has a single zone and no daylight saving."
    ),
    "Kenya": TimeZone("Africa/Nairobi", "UTC+03:00"),
    "Malaysia": TimeZone("Asia/Kuala_Lumpur", "UTC+08:00"),
    "Mexico": TimeZone(
        "America/Mexico_City", "UTC-06:00", "Mexico spans UTC-08:00 to UTC-05:00."
    ),
    "Morocco": TimeZone("Africa/Casablanca", "UTC+01:00"),
    "Netherlands": TimeZone("Europe/Amsterdam", "UTC+01:00"),
    "New Zealand": TimeZone(
        "Pacific/Auckland",
        "UTC+12:00",
        "The Chatham Islands run 45 minutes ahead of the mainland.",
    ),
    "Nigeria": TimeZone("Africa/Lagos", "UTC+01:00"),
    "Norway": TimeZone("Europe/Oslo", "UTC+01:00"),
    "Pakistan": TimeZone("Asia/Karachi", "UTC+05:00"),
    "Peru": TimeZone("America/Lima", "UTC-05:00"),
    "Philippines": TimeZone("Asia/Manila", "UTC+08:00"),
    "Poland": TimeZone("Europe/Warsaw", "UTC+01:00"),
    "Portugal": TimeZone(
        "Europe/Lisbon", "UTC+00:00", "The Azores run an hour behind the mainland."
    ),
    "Romania": TimeZone("Europe/Bucharest", "UTC+02:00"),
    "Russia": TimeZone(
        "Europe/Moscow",
        "UTC+03:00",
        "Russia spans eleven time zones, from UTC+02:00 to UTC+12:00.",
    ),
    "Saudi Arabia": TimeZone("Asia/Riyadh", "UTC+03:00"),
    "Singapore": TimeZone("Asia/Singapore", "UTC+08:00"),
    "South Africa": TimeZone("Africa/Johannesburg", "UTC+02:00"),
    "South Korea": TimeZone("Asia/Seoul", "UTC+09:00"),
    "Spain": TimeZone(
        "Europe/Madrid",
        "UTC+01:00",
        "The Canary Islands run an hour behind the mainland.",
    ),
    "Sweden": TimeZone("Europe/Stockholm", "UTC+01:00"),
    "Switzerland": TimeZone("Europe/Zurich", "UTC+01:00"),
    "Thailand": TimeZone("Asia/Bangkok", "UTC+07:00"),
    "Turkey": TimeZone(
        "Europe/Istanbul", "UTC+03:00", "Turkey stays on UTC+03:00 all year."
    ),
    "Ukraine": TimeZone("Europe/Kyiv", "UTC+02:00"),
    "United Arab Emirates": TimeZone("Asia/Dubai", "UTC+04:00"),
    "United Kingdom": TimeZone(
        "Europe/London",
        "UTC+00:00",
        "Greenwich, in London, gives its name to Greenwich Mean Time.",
    ),
    "United States": TimeZone(
        "America/New_York",
        "UTC-05:00",
        "The United States spans six main zones, from UTC-10:00 in Hawaii to "
        "UTC-05:00 on the east coast.",
    ),
    "Vietnam": TimeZone("Asia/Ho_Chi_Minh", "UTC+07:00"),
}


@dataclass(frozen=True)
class City:
    """A major city, with the country and civil time it belongs to."""

    name: str
    country: str
    timezone: str
    utc_offset: str
    note: str = ""
    aliases: Tuple[str, ...] = field(default_factory=tuple)


CITIES: Tuple[City, ...] = (
    City("Auckland", "New Zealand", "Pacific/Auckland", "UTC+12:00", "New Zealand's largest city."),
    City("Barcelona", "Spain", "Europe/Madrid", "UTC+01:00", "Capital of Catalonia and a Mediterranean port."),
    City("Cape Town", "South Africa", "Africa/Johannesburg", "UTC+02:00", "South Africa's legislative capital."),
    City("Casablanca", "Morocco", "Africa/Casablanca", "UTC+01:00", "Morocco's largest city and business hub."),
    City("Chicago", "United States", "America/Chicago", "UTC-06:00", "Great Lakes port and home of the skyscraper."),
    City("Dubai", "United Arab Emirates", "Asia/Dubai", "UTC+04:00", "Home of the Burj Khalifa, the tallest building on Earth."),
    City("Durban", "South Africa", "Africa/Johannesburg", "UTC+02:00", "Africa's busiest container port."),
    City("Frankfurt", "Germany", "Europe/Berlin", "UTC+01:00", "Seat of the European Central Bank."),
    City("Guangzhou", "China", "Asia/Shanghai", "UTC+08:00", "Pearl River Delta manufacturing centre."),
    City("Hong Kong", "China", "Asia/Hong_Kong", "UTC+08:00", "A special administrative region and global financial centre."),
    City("Ho Chi Minh City", "Vietnam", "Asia/Ho_Chi_Minh", "UTC+07:00", "Vietnam's largest city, formerly Saigon.", ("saigon",)),
    City("Istanbul", "Turkey", "Europe/Istanbul", "UTC+03:00", "The only major city set on two continents.", ("constantinople",)),
    City("Johannesburg", "South Africa", "Africa/Johannesburg", "UTC+02:00", "South Africa's largest city, founded on gold."),
    City("Karachi", "Pakistan", "Asia/Karachi", "UTC+05:00", "Pakistan's largest city and main port."),
    City("Kolkata", "India", "Asia/Kolkata", "UTC+05:30", "Former capital of British India.", ("calcutta",)),
    City("Kyoto", "Japan", "Asia/Tokyo", "UTC+09:00", "Japan's imperial capital for over a thousand years."),
    City("Lagos", "Nigeria", "Africa/Lagos", "UTC+01:00", "Africa's largest metropolitan area."),
    City("Los Angeles", "United States", "America/Los_Angeles", "UTC-08:00", "Centre of the film industry.", ("la",)),
    City("Melbourne", "Australia", "Australia/Melbourne", "UTC+10:00", "Victoria's capital and Australia's cultural rival to Sydney."),
    City("Milan", "Italy", "Europe/Rome", "UTC+01:00", "Italy's finance and fashion capital."),
    City("Montreal", "Canada", "America/Toronto", "UTC-05:00", "The largest French-speaking city in the Americas."),
    City("Mumbai", "India", "Asia/Kolkata", "UTC+05:30", "India's financial capital and home of Bollywood.", ("bombay",)),
    City("Munich", "Germany", "Europe/Berlin", "UTC+01:00", "Bavaria's capital and host of Oktoberfest."),
    City("New York", "United States", "America/New_York", "UTC-05:00", "The United States' largest city and seat of the United Nations.", ("new york city", "nyc")),
    City("Osaka", "Japan", "Asia/Tokyo", "UTC+09:00", "Japan's historic merchant city."),
    City("Rio de Janeiro", "Brazil", "America/Sao_Paulo", "UTC-03:00", "Brazil's former capital, famous for Carnival.", ("rio",)),
    City("San Francisco", "United States", "America/Los_Angeles", "UTC-08:00", "Gateway to Silicon Valley."),
    City("Shanghai", "China", "Asia/Shanghai", "UTC+08:00", "China's largest city and busiest container port."),
    City("Shenzhen", "China", "Asia/Shanghai", "UTC+08:00", "China's first special economic zone."),
    City("St Petersburg", "Russia", "Europe/Moscow", "UTC+03:00", "Russia's imperial capital until 1918.", ("saint petersburg", "leningrad")),
    City("Sydney", "Australia", "Australia/Sydney", "UTC+10:00", "Australia's largest city, known for its harbour and opera house."),
    City("São Paulo", "Brazil", "America/Sao_Paulo", "UTC-03:00", "The largest city in the southern hemisphere.", ("sao paulo",)),
    City("Tel Aviv", "Israel", "Asia/Jerusalem", "UTC+02:00", "Israel's economic and technology centre."),
    City("Toronto", "Canada", "America/Toronto", "UTC-05:00", "Canada's largest city."),
    City("Vancouver", "Canada", "America/Vancouver", "UTC-08:00", "Canada's main Pacific port."),
    City("Zurich", "Switzerland", "Europe/Zurich", "UTC+01:00", "Switzerland's largest city and banking centre."),
)


@dataclass(frozen=True)
class Wonder:
    """A wonder of the world, ancient, modern or natural."""

    name: str
    category: str
    location: str
    summary: str
    aliases: Tuple[str, ...] = field(default_factory=tuple)


WONDER_CATEGORIES: Tuple[str, ...] = (
    "Seven Wonders of the Ancient World",
    "New Seven Wonders of the World",
    "Seven Natural Wonders of the World",
)


WONDERS: Tuple[Wonder, ...] = (
    Wonder(
        "Great Pyramid of Giza",
        "Seven Wonders of the Ancient World",
        "Giza, Egypt",
        "Built around 2560 BC as the tomb of pharaoh Khufu, it stood as the "
        "tallest human-made structure for nearly four thousand years and is "
        "the only ancient wonder still standing.",
        ("pyramid of giza", "great pyramid", "pyramids of giza"),
    ),
    Wonder(
        "Hanging Gardens of Babylon",
        "Seven Wonders of the Ancient World",
        "Babylon, in modern Iraq",
        "Terraced gardens said to have been built for a homesick queen around "
        "600 BC. No archaeological trace has been confirmed, so they may be "
        "legend or may have stood at Nineveh.",
        ("hanging gardens",),
    ),
    Wonder(
        "Temple of Artemis",
        "Seven Wonders of the Ancient World",
        "Ephesus, in modern Turkey",
        "A vast marble temple to the goddess Artemis, rebuilt several times "
        "and finally destroyed in AD 401. Only foundations and a single "
        "column remain.",
        ("temple of artemis at ephesus", "temple of diana"),
    ),
    Wonder(
        "Statue of Zeus at Olympia",
        "Seven Wonders of the Ancient World",
        "Olympia, Greece",
        "A twelve-metre seated figure of Zeus in ivory and gold, made by "
        "Phidias around 435 BC and lost in late antiquity.",
        ("statue of zeus",),
    ),
    Wonder(
        "Mausoleum at Halicarnassus",
        "Seven Wonders of the Ancient World",
        "Bodrum, Turkey",
        "The tomb of Mausolus, built around 350 BC and so admired that his "
        "name became the word mausoleum. Earthquakes destroyed it by the "
        "15th century.",
        ("mausoleum of halicarnassus", "tomb of mausolus"),
    ),
    Wonder(
        "Colossus of Rhodes",
        "Seven Wonders of the Ancient World",
        "Rhodes, Greece",
        "A bronze statue of the sun god Helios about 33 metres tall, finished "
        "around 280 BC and toppled by an earthquake some 54 years later.",
        ("colossus",),
    ),
    Wonder(
        "Lighthouse of Alexandria",
        "Seven Wonders of the Ancient World",
        "Alexandria, Egypt",
        "A lighthouse over 100 metres tall built on the island of Pharos in "
        "the 3rd century BC; its name still means lighthouse in several "
        "languages.",
        ("pharos of alexandria", "pharos"),
    ),
    Wonder(
        "Great Wall of China",
        "New Seven Wonders of the World",
        "Northern China",
        "Fortifications built and rebuilt over two thousand years, most "
        "famously by the Ming dynasty; its branches total more than 21,000 "
        "kilometres.",
        ("great wall",),
    ),
    Wonder(
        "Petra",
        "New Seven Wonders of the World",
        "Ma'an, Jordan",
        "The rock-cut capital of the Nabataeans, carved into red sandstone "
        "cliffs from around the 5th century BC and reached through a narrow "
        "gorge called the Siq.",
    ),
    Wonder(
        "Christ the Redeemer",
        "New Seven Wonders of the World",
        "Rio de Janeiro, Brazil",
        "A 30-metre art deco statue of Jesus completed in 1931 on Corcovado "
        "mountain, overlooking the city and its harbour.",
        ("cristo redentor",),
    ),
    Wonder(
        "Machu Picchu",
        "New Seven Wonders of the World",
        "Cusco Region, Peru",
        "A 15th-century Inca citadel on an Andean ridge 2,430 metres up, "
        "abandoned during the Spanish conquest and brought to world attention "
        "in 1911.",
    ),
    Wonder(
        "Chichén Itzá",
        "New Seven Wonders of the World",
        "Yucatán, Mexico",
        "A Maya city whose step pyramid, El Castillo, encodes the calendar and "
        "casts a serpent-shaped shadow at the equinoxes.",
        ("chichen itza",),
    ),
    Wonder(
        "Colosseum",
        "New Seven Wonders of the World",
        "Rome, Italy",
        "The largest amphitheatre ever built, opened in AD 80 and able to hold "
        "some 50,000 spectators for gladiatorial games.",
        ("the colosseum", "flavian amphitheatre"),
    ),
    Wonder(
        "Taj Mahal",
        "New Seven Wonders of the World",
        "Agra, India",
        "A white marble mausoleum built by the Mughal emperor Shah Jahan for "
        "his wife Mumtaz Mahal, completed around 1653.",
    ),
    Wonder(
        "Grand Canyon",
        "Seven Natural Wonders of the World",
        "Arizona, United States",
        "A gorge 446 kilometres long and up to 1.8 kilometres deep, cut by the "
        "Colorado River through two billion years of rock.",
    ),
    Wonder(
        "Great Barrier Reef",
        "Seven Natural Wonders of the World",
        "Queensland, Australia",
        "The largest coral reef system on Earth, stretching over 2,300 "
        "kilometres and visible from orbit.",
    ),
    Wonder(
        "Harbour of Rio de Janeiro",
        "Seven Natural Wonders of the World",
        "Rio de Janeiro, Brazil",
        "Guanabara Bay, ringed by granite peaks including Sugarloaf Mountain "
        "and Corcovado.",
        ("guanabara bay", "harbor of rio de janeiro"),
    ),
    Wonder(
        "Mount Everest",
        "Seven Natural Wonders of the World",
        "Nepal and Tibet",
        "The highest mountain above sea level at about 8,849 metres, first "
        "climbed by Tenzing Norgay and Edmund Hillary in 1953.",
        ("everest",),
    ),
    Wonder(
        "Aurora",
        "Seven Natural Wonders of the World",
        "Polar skies of both hemispheres",
        "Curtains of light created when solar particles excite gases in the "
        "upper atmosphere; the northern lights and their southern twin.",
        ("northern lights", "aurora borealis", "aurora australis"),
    ),
    Wonder(
        "Parícutin",
        "Seven Natural Wonders of the World",
        "Michoacán, Mexico",
        "A volcano that rose out of a cornfield in 1943 and grew more than 400 "
        "metres in nine years, watched from the first day.",
        ("paricutin",),
    ),
    Wonder(
        "Victoria Falls",
        "Seven Natural Wonders of the World",
        "Zambia and Zimbabwe",
        "A curtain of water 1.7 kilometres wide on the Zambezi, known locally "
        "as Mosi-oa-Tunya, the smoke that thunders.",
        ("mosi-oa-tunya",),
    ),
)


@dataclass(frozen=True)
class HistoricalEvent:
    """A major event in world history."""

    name: str
    period: str
    year: Optional[int]
    summary: str
    aliases: Tuple[str, ...] = field(default_factory=tuple)
    start_year: Optional[int] = None
    end_year: Optional[int] = None


EVENTS: Tuple[HistoricalEvent, ...] = (
    HistoricalEvent(
        "The Agricultural Revolution",
        "about 10,000 BC",
        -10000,
        "Farming began independently in the Fertile Crescent, China and the "
        "Americas, letting people settle, store surplus food and build the "
        "first towns.",
        ("neolithic revolution", "agricultural revolution"),
    ),
    HistoricalEvent(
        "Invention of writing",
        "about 3200 BC",
        -3200,
        "Cuneiform in Sumer and hieroglyphs in Egypt turned spoken language "
        "into records, marking the boundary between prehistory and history.",
        ("cuneiform", "first writing"),
    ),
    HistoricalEvent(
        "Founding of Rome's republic",
        "509 BC",
        -509,
        "Rome expelled its kings and built a republic of elected magistrates "
        "and a senate, a model still quoted by modern constitutions.",
        ("roman republic",),
    ),
    HistoricalEvent(
        "Fall of the Western Roman Empire",
        "AD 476",
        476,
        "The last western emperor was deposed, ending centralised Roman rule "
        "in western Europe and opening the medieval period.",
        ("fall of rome", "fall of the roman empire"),
    ),
    HistoricalEvent(
        "The Hijra and the rise of Islam",
        "AD 622",
        622,
        "Muhammad's migration from Mecca to Medina starts the Islamic "
        "calendar; within a century Islamic rule reached Spain and India.",
        ("hijra", "rise of islam"),
    ),
    HistoricalEvent(
        "The Black Death",
        "1347-1351",
        1347,
        "Plague spread along trade routes and killed perhaps a third of "
        "Europe's population, reshaping labour, wages and belief.",
        ("black death", "bubonic plague"),
        start_year=1347,
        end_year=1351,
    ),
    HistoricalEvent(
        "Gutenberg's printing press",
        "about 1440",
        1440,
        "Movable metal type made books cheap in Europe, spreading literacy, "
        "the Reformation and the scientific revolution.",
        ("printing press", "gutenberg"),
    ),
    HistoricalEvent(
        "Columbus reaches the Americas",
        "1492",
        1492,
        "European contact with the Americas began the Columbian exchange of "
        "crops, people and disease, and centuries of colonisation.",
        ("columbus", "discovery of america"),
    ),
    HistoricalEvent(
        "The Protestant Reformation",
        "1517",
        1517,
        "Martin Luther's ninety-five theses split western Christianity and "
        "redrew Europe's political map.",
        ("reformation", "martin luther"),
    ),
    HistoricalEvent(
        "The Scientific Revolution",
        "16th-17th centuries",
        1543,
        "From Copernicus to Newton, observation and mathematics replaced "
        "authority as the test of truth about nature.",
        ("scientific revolution",),
        start_year=1500,
        end_year=1699,
    ),
    HistoricalEvent(
        "The American Revolution",
        "1775-1783",
        1776,
        "Thirteen British colonies declared independence in 1776 and won it by "
        "1783, creating the United States.",
        ("american revolution", "american war of independence", "declaration of independence"),
        start_year=1775,
        end_year=1783,
    ),
    HistoricalEvent(
        "The French Revolution",
        "1789-1799",
        1789,
        "The storming of the Bastille began a decade that abolished the French "
        "monarchy and spread the language of rights across Europe.",
        ("french revolution", "storming of the bastille"),
        start_year=1789,
        end_year=1799,
    ),
    HistoricalEvent(
        "The Industrial Revolution",
        "about 1760-1840",
        1760,
        "Steam power, factories and railways began in Britain and transformed "
        "work, cities and living standards worldwide.",
        ("industrial revolution",),
        start_year=1760,
        end_year=1840,
    ),
    HistoricalEvent(
        "Abolition of the transatlantic slave trade",
        "1807-1888",
        1807,
        "Britain banned the trade in 1807; emancipation followed through the "
        "century, ending with Brazil in 1888.",
        ("abolition of slavery", "slave trade abolition"),
        start_year=1807,
        end_year=1888,
    ),
    HistoricalEvent(
        "The First World War",
        "1914-1918",
        1914,
        "A four-year industrial war that killed around 17 million people, "
        "ended four empires and redrew Europe and the Middle East.",
        ("world war i", "world war 1", "ww1", "wwi", "great war"),
        start_year=1914,
        end_year=1918,
    ),
    HistoricalEvent(
        "The Russian Revolution",
        "1917",
        1917,
        "The tsar fell and the Bolsheviks took power, founding the Soviet "
        "Union and a communist bloc that lasted until 1991.",
        ("russian revolution", "october revolution"),
    ),
    HistoricalEvent(
        "The Great Depression",
        "1929-1939",
        1929,
        "A global slump that began with the Wall Street crash, throwing "
        "millions out of work and fuelling political extremism.",
        ("great depression", "wall street crash"),
        start_year=1929,
        end_year=1939,
    ),
    HistoricalEvent(
        "The Second World War",
        "1939-1945",
        1939,
        "The deadliest conflict in history, killing an estimated 70 to 85 "
        "million people, including six million Jews murdered in the "
        "Holocaust, and ending with the first use of atomic weapons.",
        ("world war ii", "world war 2", "ww2", "wwii", "second world war"),
        start_year=1939,
        end_year=1945,
    ),
    HistoricalEvent(
        "Founding of the United Nations",
        "1945",
        1945,
        "Fifty-one states signed the UN Charter in San Francisco to keep the "
        "peace after the Second World War.",
        ("united nations", "un charter"),
    ),
    HistoricalEvent(
        "Indian independence and partition",
        "1947",
        1947,
        "British India became independent India and Pakistan; partition "
        "displaced some 15 million people.",
        ("indian independence", "partition of india"),
    ),
    HistoricalEvent(
        "Universal Declaration of Human Rights",
        "1948",
        1948,
        "The UN General Assembly adopted a common standard of rights for all "
        "peoples, now translated into more than 500 languages.",
        ("universal declaration of human rights", "human rights declaration"),
    ),
    HistoricalEvent(
        "The Cold War",
        "1947-1991",
        1947,
        "Four decades of rivalry between the United States and the Soviet "
        "Union, fought through proxy wars, espionage and an arms race.",
        ("cold war",),
        start_year=1947,
        end_year=1991,
    ),
    HistoricalEvent(
        "The Apollo 11 Moon landing",
        "1969",
        1969,
        "Neil Armstrong and Buzz Aldrin became the first people to walk on "
        "the Moon, watched by an estimated 600 million viewers.",
        ("moon landing", "apollo 11"),
    ),
    HistoricalEvent(
        "Decolonisation of Africa and Asia",
        "1945-1975",
        1960,
        "Dozens of colonies became independent states; 1960 alone, the Year "
        "of Africa, saw seventeen African countries gain independence.",
        ("decolonisation", "decolonization", "year of africa"),
        start_year=1945,
        end_year=1975,
    ),
    HistoricalEvent(
        "Fall of the Berlin Wall",
        "1989",
        1989,
        "The wall dividing Berlin was opened, leading to German reunification "
        "and, two years later, the dissolution of the Soviet Union.",
        ("berlin wall",),
    ),
    HistoricalEvent(
        "The end of apartheid",
        "1994",
        1994,
        "South Africa held its first fully democratic election and Nelson "
        "Mandela became president.",
        ("apartheid", "nelson mandela"),
    ),
    HistoricalEvent(
        "Birth of the World Wide Web",
        "1989-1991",
        1991,
        "Tim Berners-Lee's design at CERN put the first website online in "
        "1991 and made the internet a public medium.",
        ("world wide web", "first website"),
        start_year=1989,
        end_year=1991,
    ),
    HistoricalEvent(
        "The 11 September attacks",
        "2001",
        2001,
        "Coordinated attacks in the United States killed nearly 3,000 people "
        "and reshaped security policy and two decades of conflict.",
        ("9/11", "september 11", "11 september attacks"),
    ),
    HistoricalEvent(
        "The COVID-19 pandemic",
        "2020-2023",
        2020,
        "A coronavirus pandemic that closed borders and economies worldwide, "
        "answered by the fastest vaccine development in history.",
        ("covid", "covid-19", "coronavirus pandemic"),
        start_year=2020,
        end_year=2023,
    ),
)


def timezone_for_country(country: Country) -> Optional[TimeZone]:
    """Return the civil time kept by ``country``'s capital."""

    return TIMEZONES.get(country.name)


def find_city(name: str) -> Optional[City]:
    """Return the major city matching ``name`` or one of its aliases."""

    key = _strip_article(normalise(name))
    if not key:
        return None
    for city in CITIES:
        if key == normalise(city.name) or key in {
            normalise(alias) for alias in city.aliases
        }:
            return city
    return None


def cities_in(country_name: str) -> List[City]:
    """Return the known major cities of ``country_name``, sorted by name."""

    country = find_country(country_name)
    if country is None:
        return []
    return sorted(
        (city for city in CITIES if city.country == country.name),
        key=lambda city: city.name,
    )


def find_wonder(name: str) -> Optional[Wonder]:
    """Return the wonder matching ``name`` or one of its aliases."""

    key = _strip_article(normalise(name))
    if not key:
        return None
    for wonder in WONDERS:
        if key == normalise(wonder.name) or key in {
            normalise(alias) for alias in wonder.aliases
        }:
            return wonder
    return None


def find_wonder_category(name: str) -> Optional[str]:
    """Return the canonical wonder list named by ``name``."""

    key = _strip_article(normalise(name))
    if not key:
        return None
    if "natural" in key:
        return "Seven Natural Wonders of the World"
    if "ancient" in key or "classical" in key:
        return "Seven Wonders of the Ancient World"
    if "new" in key or "modern" in key:
        return "New Seven Wonders of the World"
    return None


def wonders_in(category: str) -> List[Wonder]:
    """Return the wonders belonging to ``category``, in canonical order."""

    canonical = find_wonder_category(category)
    if canonical is None:
        return []
    return [wonder for wonder in WONDERS if wonder.category == canonical]


def describe_wonder(wonder: Wonder) -> str:
    """Return a one paragraph profile of ``wonder``."""

    return sentence(
        f"{wonder.name} ({wonder.location}) is one of the "
        f"{wonder.category}. {wonder.summary}"
    )


def find_event(name: str) -> Optional[HistoricalEvent]:
    """Return the historical event matching ``name`` or one of its aliases."""

    key = _strip_article(normalise(name))
    if not key:
        return None
    for event in EVENTS:
        if key == normalise(event.name) or key in {
            normalise(alias) for alias in event.aliases
        }:
            return event
    for event in EVENTS:
        haystacks = [normalise(event.name)] + [
            normalise(alias) for alias in event.aliases
        ]
        if any(key in haystack for haystack in haystacks) and len(key) > 3:
            return event
    return None


def events_in_year(year: int) -> List[HistoricalEvent]:
    """Return every event whose span covers ``year``, in chronological order."""

    matches: List[HistoricalEvent] = []
    for event in EVENTS:
        bounds = [
            bound
            for bound in (event.start_year, event.end_year, event.year)
            if bound is not None
        ]
        if not bounds:
            continue
        if min(bounds) <= year <= max(bounds):
            matches.append(event)
    return matches


def describe_event(event: HistoricalEvent) -> str:
    """Return a one paragraph profile of ``event``."""

    return sentence(f"{event.name} ({event.period}): {event.summary}")


def known_cities() -> Sequence[str]:
    """Return the names of every major city in the atlas, sorted."""

    return tuple(sorted(city.name for city in CITIES))


def known_events() -> Sequence[str]:
    """Return the names of every historical event, in chronological order."""

    return tuple(event.name for event in EVENTS)
