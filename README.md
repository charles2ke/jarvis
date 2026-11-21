# jarvis

Personal AI Companion — a small, dependency-free assistant you can run from your
terminal.

Jarvis matches what you type against a registry of skills and answers with the
first one that fits. Everything is plain Python, so most offline requests are
answered in milliseconds and you can read exactly how the answer was produced.
Skills that reach the network or call out to an external tool (speech, CUA,
opening phone and email links)
take as long as that service or subprocess does.

- **Offline first** — every skill works without a network connection, except
  the ones that say otherwise (`web-search`, `add-knowledge-website`, `answer`,
  and the live `weather`, `hazard-alerts` and `space-weather` feeds).
- **Looks up what it does not know** — a factual question that no skill can
  answer is searched on the web (Wikipedia by default) and summarised with
  numbered sources; `--web-search off` keeps Jarvis fully offline
  ([Searching the web](#searching-the-web)).
- **No runtime dependencies** — the standard library only, on Python 3.10+.
- **Private** — memory is a JSON file you own, and you can turn it off entirely.
- **Extensible** — a skill is a regular expression plus a handler
  ([Adding a skill](#adding-a-skill)).

## Contents

- [Quick start](#quick-start)
- [Built-in skills](#built-in-skills)
- [Time, dates and world clocks](#time-dates-and-world-clocks)
- [Everyday maths and percentages](#everyday-maths-and-percentages)
- [Small talk, names and notes](#small-talk-names-and-notes)
- [Poetry](#poetry)
- [World knowledge](#world-knowledge)
- [Traffic signs around the world](#traffic-signs-around-the-world)
- [Solving science problems](#solving-science-problems)
- [Economics and financial advice](#economics-and-financial-advice)
- [Health and fitness](#health-and-fitness)
- [Knowledge sources](#knowledge-sources)
- [Searching the web](#searching-the-web)
- [Weather and hazard alerts](#weather-and-hazard-alerts)
- [Text to speech](#text-to-speech)
- [Natural language to text](#natural-language-to-text)
- [Sign language](#sign-language)
- [Maritime safety (GMDSS)](#maritime-safety-gmdss)
- [Emergency numbers](#emergency-numbers)
- [The Bible as a knowledge source](#the-bible-as-a-knowledge-source)
- [ASCII sketches](#ascii-sketches)
- [Reading and writing braille](#reading-and-writing-braille)
- [Answering any query with a cloud session](#answering-any-query-with-a-cloud-session)
- [Computer use (CUA)](#computer-use-cua)
- [Connected projects](#connected-projects)
- [Project layout](#project-layout)
- [Adding a skill](#adding-a-skill)
- [Development](#development)
- [License](#license)

## Quick start

```bash
pip install -e .
jarvis "calculate 21 * 2"
```

Python 3.10+ is required. There are no runtime dependencies.

Interactive session:

```bash
jarvis
```

In a session, type `help` for the full skill list, `help <topic>` (for example
`help money`) to see only the skills that match, and `exit`, `quit` or Ctrl-D to
leave.

One-shot question:

```bash
jarvis "calculate 21 * 2"
```

Piped from another command or a script:

```bash
echo "what is the time?" | jarvis
printf 'my name is Ada\nwhat is my name\n' | jarvis
```

A single piped line is answered like a one-shot question; several lines are
replayed as a session, one line per turn.

Or without installing:

```bash
PYTHONPATH=src python -m jarvis "what is the time?"
```

Useful flags:

- `--memory PATH` — where to persist memory (default `~/.jarvis/memory.json`, override the directory with `JARVIS_HOME`).
- `--no-memory` — keep everything in RAM for the session.
- `--speak` — also read every reply aloud (see [Text to speech](#text-to-speech)).
- `--list-skills` — print every skill with an example and exit.
- `--web-search auto|manual|off` — when to search the web (default `auto`, or
  `JARVIS_WEB_SEARCH`); see [Searching the web](#searching-the-web).
- `--version` — print the version and exit.

### Memory and privacy

Memory is a single JSON file (`~/.jarvis/memory.json` by default) holding what
you asked Jarvis to keep — your name, your notes, your knowledge sources and
your paper-trading portfolio (`paper_portfolio`) —
plus one internal counter, `support_tip_index`, which `emotional-support` uses
to rotate through its coping suggestions. Deleting the file clears what is
stored, but a later normal run writes it again; run with `--no-memory` to keep
memory in RAM so nothing is written to disk at all. The in-session mood log used
by `psychiatrist` is never persisted. Memory is written to a temporary file and
then swapped into place, so an interrupted save never leaves a half-written
`memory.json` behind.

The network is used only to search the web for a factual question no skill can
answer, or when you ask it to ([Searching the web](#searching-the-web)); by
`add-knowledge-website`, when it fetches a page you asked for; by `answer`,
when you send a question to a cloud session; and by `weather`, `hazard-alerts`
and `space-weather`, when you ask for live weather or alerts
([Weather and hazard alerts](#weather-and-hazard-alerts)). Everything else is
answered from data shipped with the package. The results of the last web search are kept in
RAM for the session only; the pages, and the answer with the question it
answered, are written to memory only when you say `learn that`.

## Built-in skills

Say `help` at any time to see this list from inside a session, or `help <topic>`
(for example `help braille`) to see only the skills whose name, description or
example mentions that topic; `jarvis --list-skills` prints the same list from
your shell. The tables below group the skills by theme; the order they are
matched in is defined in `src/jarvis/skills.py`.

### Wellbeing and companionship

| Skill | Example |
| --- | --- |
| crisis-support | `I have been thinking about hurting myself` |
| mental-health | `I feel anxious` |
| console | `I am having a rough day` |
| psychiatrist | `I feel anxious about work` |
| mood-history | `how have I been feeling` |
| clear-mood-history | `clear my mood history` |
| emotional-support | `I need some emotional support` |
| love-support | `my girlfriend and I keep fighting` |
| couples-counseling | `we need couples counseling` |
| midlife-counseling | `I think I am having a midlife crisis` |
| career-counselling | `I am thinking about changing careers` |
| role-model | `be my role model` |
| coach | `coach me` |
| self-care | `how do I take care of myself` |
| uplift | `cheer me up` |

### Health and fitness

| Skill | Example |
| --- | --- |
| cancer-info | `lung cancer symptoms` |
| cancer-topics | `cancer topics` |
| workout-plan | `what's my workout today?` |

### Conversation and creativity

| Skill | Example |
| --- | --- |
| greeting | `hello` |
| small-talk | `how are you?` |
| thanks | `thank you` |
| about-jarvis | `who are you?` |
| repeat | `say that again` |
| farewell | `goodbye` |
| help | `help` |
| joke | `tell me a joke` |
| story | `tell me a story` |
| poetry | `write a poem about the sea` |
| poetry-forms | `what poems can you write` |
| sketch | `draw a cat` |
| sketch-topics | `what can you sketch?` |

### Maths, science and units

| Skill | Example |
| --- | --- |
| calculator | `calculate 21 * 2` |
| percentages | `what is 15% of 80?` |
| science-solver | `solve 2x + 3 = 11` |
| unit-conversion | `convert 10 km to miles` |
| unit-list | `what units can you convert?` |
| number-words | `spell out 42` |

### Money

| Skill | Example |
| --- | --- |
| money-math | `monthly payment on a 250000 mortgage at 5% over 30 years` |
| tax-estimate | `UK take-home on £50,000` |
| investment-math | `cost of equity for beta 1.3` |
| paper-trading | `paper buy 10 AAPL` |
| financial-advisor | `financial advice on investing` |
| economics | `what is inflation?` |
| economics-topics | `economics topics` |

### Reference knowledge

| Skill | Example |
| --- | --- |
| atlas | `what is the capital of Japan?` |
| cities | `what cities are in Japan?` |
| time-zone | `what time zone is Japan in?` |
| wonders | `what are the seven wonders of the world?` |
| history | `what happened in 1969?` |
| traffic-signs | `what does a give way sign mean?` |
| encyclopedia | `what is gravity?` |
| encyclopedia-topics | `encyclopedia topics` |
| bible | `what does the bible say about hope?` |
| bible-topics | `bible topics` |
| bible-books | `books of the bible` |
| gmdss | `what is an EPIRB?` |
| gmdss-topics | `gmdss topics` |

### Web research

| Skill | Example |
| --- | --- |
| web-search | `search the web for the tallest building in Africa` |
| web-more | `tell me more` |
| web-sources | `sources` |
| learn-answer | `learn that` |

Questions that no skill matches, such as `who invented the telephone?`, are
searched automatically too; see [Searching the web](#searching-the-web).

### Accessibility

| Skill | Example |
| --- | --- |
| braille | `read braille ⠓⠑⠇⠇⠕` |
| braille-alphabet | `braille alphabet` |
| sign-language | `how do I sign thank you?` |
| sign-language-alphabet | `sign language alphabet` |
| sign-language-topics | `what signs do you know` |
| fingerspell | `fingerspell Charles` |
| speak | `say out loud hello Charles` |

### Memory and personal data

| Skill | Example |
| --- | --- |
| remember-name | `my name is Charles` |
| recall-name | `what is my name?` |
| forget-name | `forget my name` |
| add-note | `remember buy milk` |
| list-notes | `list my notes` |
| search-notes | `search my notes for milk` |
| edit-note | `change note 2 to call dad` |
| delete-note | `delete note 2` |
| clear-notes | `clear my notes` |
| add-knowledge-website | `add https://example.com as a knowledge source` |
| add-knowledge-file | `add the file notes.md as a knowledge source` |
| list-knowledge-sources | `list my knowledge sources` |
| clear-knowledge-sources | `clear my knowledge sources` |

### Everyday and system

| Skill | Example |
| --- | --- |
| time | `what is the time?` |
| date | `what day is it` |
| date-calculator | `how many days until Christmas?` |
| world-clock | `what time is it in Tokyo?` |
| weather | `weather in Paris` |
| hazard-alerts | `any earthquakes near Lima` |
| space-weather | `space weather` |
| answer | `answer how does the skill registry work?` |
| computer-use | `use the computer to open Safari then click on Sign in` |
| emergency-numbers | `what are the emergency numbers in Japan?` |
| emergency-call | `call the police in Kenya` |
| emergency-text | `text the police in France: there is a break-in` |
| emergency-share | `email the emergency numbers for Kenya to me@example.com` |
| cua-actions | `computer use actions` |

### How routing works

The first skill whose pattern matches wins, so specific skills are registered
before broad ones. The wellbeing skills are registered first so that a message such as
`hi, I want to kill myself` reaches `crisis-support` rather than `greeting`.
Jarvis is a companion, not a substitute for professional help: `crisis-support`
always points to real help lines. The `psychiatrist` skill offers reflective,
empathetic listening and keeps an in-session mood log that is not written to
persistent memory; it is not a substitute for professional care.
`emotional-support` answers direct requests for comfort with validation and a
rotating coping suggestion, and `love-support` talks through relationships,
heartbreak, conflict and new feelings. `couples-counseling` answers explicit
requests to work on a marriage or relationship together, and
`midlife-counseling` reflects on ageing, regret, purpose and what comes next;
both point to a professional counsellor for ongoing work.
`career-counselling` works through
job loss, career moves, job searches and pay conversations. `role-model` talks
about character and the person you want to become, `coach` turns goals and
habits into a concrete next step, and `self-care` suggests a practical way to
look after yourself.

The same rule keeps everyday skills apart. `small-talk` and `thanks` come after
the wellbeing skills, so `not great, I want to die` still reaches
`crisis-support`, and `world-clock` and `date-calculator` come before `time` and
`date`, so `what time is it in Tokyo?` gets the world clock while
`what time is it?` still reads your own clock.

The web research skills come straight after `answer`, ahead of the notes and
encyclopedia skills, so `remember that answer` saves the last web answer while
`remember that the bins go out on Monday` is still a note. A message that no
skill matches is offered to the web search last of all, and only when it reads
like a factual question.

`cancer-info` comes after the crisis, counselling and web research skills but
before `love-support`, so `my wife has breast cancer` gets cancer information
with a kind acknowledgement rather than relationship advice, while `am I going
to die of cancer` still reaches `crisis-support`. A few skills — `cancer-info`,
`workout-plan`, `investment-math`, `paper-trading` and `tax-estimate` — check a
message against their data, and when it is not really for them (`Tropic of
Cancer`, `I just finished my workout`, `20% tax on 500`) they hand it on to the
skills registered after them.

## Time, dates and world clocks

`time` and `date` read your computer's clock: `what time is it?`, `what's the
date`, `what year is it?` and `what week number is it` (ISO 8601 weeks).
`date-calculator` answers the questions you would otherwise count out on a
calendar, offline:

```bash
jarvis "how many days until Christmas?"            # a countdown in days and weeks
jarvis "how long since 1 January 2000"             # the time since a date
jarvis "how many days between 1 Jan and 31 Dec"    # the gap between two dates
jarvis "what day of the week is 1 January 2027?"   # the weekday of any date
jarvis "what's the date in 3 weeks"                # add or subtract days, weeks, months or years
jarvis "what date is 90 days after 1 March 2027"   # ... from any date
jarvis "how old am I if I was born on 5 May 1990"  # an age and the next birthday
jarvis "is 2028 a leap year?"                      # leap years and month lengths
```

It reads dates such as `25 December 2026`, `Dec 25th`, `2027-01-01`,
`tomorrow` and `next Friday`, and the holidays that fall on the same day every
year (New Year's Day, Valentine's Day, St Patrick's Day, April Fools' Day,
Halloween, Christmas Eve, Christmas, Boxing Day and New Year's Eve). Holidays
that move from year to year, such as Easter, are not known. A date without a
year means its next occurrence, or its most recent one when you ask how long it
has been. Impossible dates such as `31 February` are reported rather than
guessed, and adding a month keeps the day of the month where it can: 31 January
plus one month is 28 February, or 29 February in a leap year.

`world-clock` tells the time in a major city, a country (which keeps its
capital's time) or a time zone (`UTC`, `Asia/Tokyo`), and the time difference
between two places:

```bash
jarvis "what time is it in Tokyo?"                  # local time, zone and offset from you
jarvis "time difference between London and Tokyo"   # how far apart, and the time in each
```

"Ahead of you" and "behind you" compare with your computer's own clock.
Daylight saving time comes from Python's `zoneinfo` database; where there is
none (for example on Windows without the `tzdata` package) Jarvis uses the
standard offset from its atlas and says that daylight saving time was not
applied.

## Everyday maths and percentages

`calculator` accepts sums the way people type them: `^` and `**`, `x`, `×` and
`÷`, `mod`, thousands separators (`1,000,000 / 4`), `squared`, `cubed`, `²` and
`³`, `2 to the power of 10`, `square root of 144`, `cube root of 27`, `√81` and
`∛64`. Whole-number roots stay exact (`sqrt(10 ** 40)` is exactly `10 ** 20`),
floating-point noise is trimmed (`0.1 + 0.2 = 0.3`), and a question with no
real-number answer, such as `sqrt(-4)`, says so instead of returning a complex
number.

`percentages` works out a percentage of an amount, what percentage one number is
of another, increases and decreases, discounts, tips and percentage changes,
and keeps the currency symbol you used:

```bash
jarvis "what is 15% of 80?"               # 15% of 80 is 12.
jarvis "what is 1 as a percentage of 3"   # 1 is about 33.33% of 3.
jarvis "increase 80 by 15%"               # 80 increased by 15% is 92 (a change of 12).
jarvis 'what is 20% off $50'              # 20% off $50 is $40, a saving of $10.
jarvis '18% tip on $45.50'                # A tip of 18% on $45.50 is $8.19, making $53.69 in total.
jarvis "percentage change from 80 to 60"  # From 80 to 60 is a decrease of 25%.
```

Use single quotes around a `$` amount in the shell, or `$50` is read as a shell
variable. The reply says "about" whenever it had to round.

## Small talk, names and notes

- `small-talk` answers `how are you?` and replies to how you say you are
  (`fine thanks, and you?`). A low mood such as `not great` or `could be better`
  gets an offer to talk instead of a cheerful reply, and the wellbeing skills are
  still matched first.
- `thanks` replies to `thank you`, `cheers` and the like, using your name if you
  shared one. A thank-you with a request attached (`thanks, what is the capital
  of France?`) is answered as the request.
- `about-jarvis` says who Jarvis is, how it works and which version is running
  (`who are you?`, `what version are you?`), `repeat` says the last reply again
  (`say that again`, `pardon?`), and `farewell` also answers `good night`.
- Names: `my name is Ada`, `call me Chuck` or `change my name to Ada`, and
  `forget my name` to stop using it.
- Notes: `remember buy milk` (or `note to self: ...`, `jot down ...`),
  `list my notes`, `how many notes do I have?`, `search my notes for milk`,
  `change note 2 to call dad`, `delete note 2` or `delete the last note`, and
  `clear my notes`. A search finds the notes that contain every word you give,
  ignoring case, so `milk` finds `buy oat milk` but `parking` does not find
  `parked`.

## Poetry

The `poetry` skill writes a new poem every time: it assembles lines from
curated word banks rather than reading back a stored poem, so `write a poem
about the sea` twice gives two different poems. Ask for a form by name, or
leave it out for free verse:

```
write a poem about the sea      # four lines of free verse
haiku about rain                # 5-7-5 syllables
write a limerick about cats     # five lines rhyming A-A-B-B-A
acrostic for Charles            # one line per letter
a rhyming couplet about coffee  # two rhyming lines
```

`what poems can you write` lists the forms. A poem `about me` uses your
remembered name when Jarvis knows it. The generator lives in
`src/jarvis/poetry.py`; `poetry.write_poem(topic, form=..., seed=...)` takes an
optional seed so a poem can be reproduced exactly.

## World knowledge

The `atlas` skill answers offline geography questions — capitals, the country
behind a capital, continents, currencies, population estimates and the
countries it knows on a continent. Its data set is small and hand-curated, so
population figures are rounded estimates. Around it sit four more world
knowledge skills that share the same offline data:

- `cities` — the major cities Jarvis knows in a country (`what cities are in
  Japan?`), capital first.
- `time-zone` — the IANA zone and standard UTC offset of a country or a major
  city (`what time zone is Japan in?`, `time zone of New York`), with a note
  when a country spans several zones.
- `wonders` — the Seven Wonders of the Ancient World, the New Seven Wonders of
  the World and the Seven Natural Wonders of the World, as lists or one at a
  time (`tell me about Machu Picchu`).
- `history` — major events in world history, by name (`when did the Berlin Wall
  fall?`), by year (`what happened in 1969?`) or as a timeline (`list major
  historical events`).

`time-zone` is registered before `time` so that `what is the time?` still
reports the clock, and city, wonder and event names are also reachable through
the `encyclopedia` fallback (`tell me about Sydney`).

## Traffic signs around the world

The `traffic-signs` skill explains road signs, signals and the two conventions
most of the world signs by: the Vienna Convention on Road Signs and Signals,
which is symbol based (triangles warn, red circles forbid, blue circles
instruct, rectangles inform), and the MUTCD used in the United States, which
leans on words plus shape and colour coding.

```bash
jarvis "what does a give way sign mean?"       # one sign, with regional names
jarvis "explain warning signs"                 # a family of signs
jarvis "tell me about traffic signs"           # the conventions and families
jarvis "list traffic signs"                    # everything it knows
jarvis "what do traffic lights mean?"          # signal colours and phases
```

Each entry records the shape, the colours, the meaning and how the sign varies
by region — the octagonal stop sign that reads 止まれ in Japan and ARRÊT in
Quebec, the deer, moose, kangaroo, camel and polar bear versions of the animal
crossing warning, and the orange work zones of North America.

## Solving science problems

The `science-solver` skill works through maths, physics, chemistry and biology
questions and shows the formula it used:

- maths — `solve 2x + 3 = 11`, `solve x^2 - 5x + 6 = 0`, `solve 3(y - 2) = 9 for y`
- physics — `calculate the force with mass 5 kg and acceleration 2 m/s^2`,
  `how fast is a car that travels 150 m in 10 s`,
  `what is the voltage with current 2 A and resistance 5 ohms`
- chemistry — `what is the molar mass of Ca(OH)2`,
  `how many moles are in 36 g of H2O`, `what is the pH of 0.001 M solution`,
  `ideal gas law with 2 mol at 300 K and pressure 1 atm`
- biology — `what is the complement of ATGC`, `transcribe ATGC`,
  `translate the RNA sequence AUGGCCUAA`, `gc content of ATGCGC`,
  `punnett square for Aa x Aa`

It is registered before `calculator`, so plain arithmetic such as
`calculate 21 * 2` is still answered by the calculator. Questions it does not
recognise get a short list of supported examples instead of a wrong answer.

The `unit-conversion` skill converts between length, mass, volume, time,
temperature, speed and area units without any network access. It understands
`convert 10 km to miles`, `how many pounds is 70 kg` and bare phrasings such as
`100 C in F`, and it refuses conversions across families (`convert 5 kg to
metres`). Ask `what units can you convert?` for the full list. It is registered
before `calculator`, so plain arithmetic is still answered by the calculator.

The `encyclopedia` skill answers factual questions (`what is ...`, `who was
...`, `tell me about ...`, `define ...`) from a small built-in, offline set of
articles — it never reaches the network. Lookups ignore case, punctuation and
aliases, tolerate small typos, and suggest close titles when a topic is
missing. It is registered last so that `what is the time?`, `what is my name?`
and `what is 21 * 2` still reach their own skills. Say `encyclopedia topics` to
list every entry.

## Economics and financial advice

Three skills explain money and do its everyday arithmetic, all of them offline
and all of them general education rather than personalised advice — every
coaching and calculator answer says so:

- `economics` explains economics and personal finance terms — inflation, GDP,
  recessions, interest rates, central banks, fiscal policy, shares, bonds,
  index funds, diversification, emergency funds, budgeting, debt repayment,
  credit scores, mortgages, retirement saving, insurance, taxes, opportunity
  cost, exchange rates and unemployment. Say `economics topics` to list every
  entry.
- `financial-advisor` coaches on a money situation (`how do I pay off debt`,
  `how should I start investing`, `advice on my budget`, `I am living paycheck
  to paycheck`) with a short, ordered playbook.
- `money-math` does the arithmetic:

```bash
jarvis "invest 10000 at 6% for 20 years adding 200 a month"
jarvis "monthly payment on a 250000 mortgage at 5% over 30 years"
jarvis "what is 50000 worth in 10 years with 3% inflation"
jarvis "how long does money double at 7%"
jarvis "50/30/20 budget on 3000 a month"
jarvis "emergency fund on 1800 a month"
```

`money-math` is registered before `science-solver` so that `how long does
money double at 7%` is answered as money rather than physics, and `economics`
is registered before `encyclopedia` so that `what is inflation?` reaches the
finance entries. The wellbeing skills still come first, so `I am broke and
want to kill myself` reaches `crisis-support`.

### Investment maths

`investment-math` brings the research calculators of
[Portfolio-Watcher](https://charles2ke.github.io/Portfolio-Watcher/) to numbers
you type — it has no market data, so it never looks up a company:

```bash
jarvis "dcf with fcf 100m growth 8% discount 9% terminal 2.5% 50m shares net debt 200m"
jarvis "cost of equity for beta 1.3"
jarvis "rsi 5 of 44, 44.3, 44.1, 43.6, 44.5, 44.9, 45.2"
jarvis "fibonacci levels between 100 and 150"
jarvis "max drawdown of 100, 120, 90, 130"
jarvis "drip 10000 at 3% yield 5% dividend growth for 10 years"
```

It covers discounted cash flow, CAPM, simple and exponential moving averages,
RSI, MACD, Bollinger bands, Fibonacci retracements, volatility, value at risk,
expected shortfall, maximum drawdown, the Sharpe ratio, return statistics and
dividend reinvestment. Every reply lists its assumptions, such as
Portfolio-Watcher's 4.2% risk-free rate, and says that model outputs do not
predict returns. Questions without numbers (`what is dcf`) still reach
`economics` or `encyclopedia`.

### Paper trading

`paper-trading` is [OpenTrading](https://charles2ke.github.io/OpenTrading/)'s
practice account: $100,000 of pretend cash and its six demo stocks (AAPL, MSFT,
TSLA, 7203, SAP and HSBA) at fixed demo prices from OpenTrading's built-in
snapshot, never live quotes.

```bash
jarvis "paper buy 10 AAPL"
jarvis "paper sell 5 shares of Apple"
jarvis "show my paper portfolio"
jarvis "paper quote TSLA"
jarvis "look up ISIN US0378331005"
jarvis "reset my paper portfolio"
```

The portfolio is kept in memory under `paper_portfolio`, so it survives a
restart unless you run with `--no-memory`. Jarvis has no brokerage connection:
an order that does not say paper (`buy 10 shares of Apple`) is never carried
out, and the reply shows the paper command to practise with instead.

### Income tax estimates

`tax-estimate` works out income tax and take-home pay on a salary with the
tables of [tax-break](https://charles2ke.github.io/tax-break/), offline, for
India, the UK (England, Wales and Northern Ireland), the US, Ireland, the
Netherlands and Singapore:

```bash
jarvis "income tax on 15 lakh in India"
jarvis "income tax on 20 lakh, old regime, max 80c and nps"
jarvis "UK tax on £4,000 a month with student loan plan 2"
jarvis 'US tax on $85,000 in California, married with 2 kids'
jarvis "Dutch tax on €70,000 with the 30% ruling"
jarvis 'Singapore tax on S$120,000'
jarvis "tax calculator"
```

Put an amount with a `$` sign in single quotes, as above, or the shell reads
`$8` or `$1` as a variable. Jarvis reads the country from the currency or the
words (`lakh`, `UK`, a US state, `Irish`, `Dutch`, `S$`) and asks when it
cannot tell — `€60,000` could be Irish or Dutch. It also reads the period
(`a month`), a bonus, the year, and each country's options: India's regimes,
age band and deductions such as `80C 1.5 lakh`, a UK student loan plan, a US
filing status, children and state (all 50 and DC), Ireland's filing status,
the Dutch 30% ruling and Singapore's age band and CPF contributions. India
gets both regimes side by side with the cheaper one named, or the regime you
name with the other's total for comparison.

Every estimate shows the year and assumptions it used, a line-by-line
breakdown and the effective and marginal rates, and says that it is for general
education, not tax advice. The tables are tax-break's: FY 2021-22 to FY 2025-26
for India, 2025/26 for the UK, 2025 for the US, Ireland and the Netherlands,
and YA 2025 for Singapore. For a year outside them, Jarvis says which years
tax-break has rather than guessing, and suggests asking without a year to use
the latest. Messages that only mention tax
(`what is a tax bracket?`, `20% tax on 500`) go to the skills that handle them.

## Health and fitness

`cancer-info` answers from [beat-it](https://charles2ke.github.io/beat-it/)'s
reviewed information on 22 cancer types, offline:

```bash
jarvis "lung cancer symptoms"
jarvis "breast cancer screening"
jarvis "leukemia medicines"
jarvis "is cancer hereditary?"
jarvis "cancer topics"
```

It covers each type's overview, symptoms, risk factors, screening, treatments,
medicines and recent FDA approvals, beat-it's frequently asked questions and
its worldwide figures. It is general information, never a diagnosis: questions
about your own symptoms get a gentle reply that urges you to see a doctor, a
message that you or someone close to you has cancer is acknowledged kindly
first, and answers about a particular type say when beat-it last reviewed it.
Messages that only mention the word — the star sign, the Tropic of Cancer, a
poem or a note — go to the skills that handle them, and thoughts of ending your
life still reach `crisis-support` first.

`workout-plan` shows the 7-Day Longevity & Strength Program from
[workout](https://charles2ke.github.io/workout/), using your computer's date:

```bash
jarvis "what's my workout today?"
jarvis "Friday workout"
jarvis "when is leg day?"
jarvis "is today a rest day?"
jarvis "weekly workout plan"
```

Each day's session lists its exercises with sets, reps and rest, and ends with
a short safety note. The Zone 2 heart-rate range comes from the plan's author
and is not a target for everyone.

## Knowledge sources

Jarvis can learn from your own material. Point it at a text file or a web page
and the readable text is stored alongside the rest of its memory:

```bash
jarvis "add the file ~/notes/handbook.md as a knowledge source"
jarvis "add https://example.com/docs as a knowledge source"
jarvis "list my knowledge sources"
jarvis "clear my knowledge sources"
```

Afterwards, questions that no built-in skill answers are looked up in the
sources, and the reply quotes the matching passage and says where it came from
(`what is the release cadence?`). Files are read as plain text — HTML files and
web pages have their markup, scripts and styles stripped first — and anything
that is not a text file, is empty or cannot be reached is reported rather than
guessed at. Adding the same location twice replaces the earlier copy, and only
fetching a website reaches the network. `clear my knowledge sources` also
forgets the web answers saved with `learn that`.

## Searching the web

When you ask a factual question that none of the skills can answer, Jarvis
looks it up online and replies with a short summary and numbered sources. The
reply has this shape (the sentences and pages depend on what the search
returns):

```text
you> who invented the telephone?
(searching Wikipedia for 'invented the telephone'...)
jarvis> I searched Wikipedia for 'invented the telephone'. Here is a summary:
<two or three sentences quoted from the pages> [1] <another sentence> [2]

Sources:
[1] <page title> - https://en.wikipedia.org/wiki/...
[2] <page title> - https://en.wikipedia.org/wiki/...

(Automatic summary: check the sources. Say 'tell me more', 'sources' or 'learn that'.)
```

You can also search on purpose, and follow up on what was found:

```bash
jarvis "search the web for the tallest building in Africa"
jarvis "google the speed of sound"
jarvis "look up the Voyager probes online"
```

- `tell me more` continues the summary with the next most relevant sentences.
- `sources` or `where did you find that?` lists every page the search returned.
- `look it up` searches the web for your previous question.
- `learn that` saves the answer, with the question it answered, and keeps the
  pages as knowledge sources ([Knowledge sources](#knowledge-sources)). Asking
  again with the same keywords and question word (`who invented the
  telephone`) gets the saved answer offline, even after a restart or with web
  search off; other questions are answered from the pages when they cover
  them. `clear my knowledge sources` forgets both.

### When Jarvis goes online

`--web-search` (or the `JARVIS_WEB_SEARCH` environment variable) decides:

| Mode | What happens |
| --- | --- |
| `auto` (the CLI default) | Factual questions that no skill answers are searched automatically, as are encyclopedia questions with no built-in entry. |
| `manual` | Jarvis searches only when you ask (`search the web for ...`, `look it up`); otherwise it says it does not know and how to look it up. |
| `off` | Jarvis never searches the web. |

Used as a library, `Assistant()` defaults to `manual`; pass
`Assistant(web_search="auto")` to behave like the CLI. The live `weather`,
`hazard-alerts` and `space-weather` skills read their feeds when you ask in
`auto` or `manual` mode, and stay offline in `off` mode
([Weather and hazard alerts](#weather-and-hazard-alerts)).

Only messages that read like a factual question are searched automatically.
Personal messages are never sent unless you ask: anything that mentions *me*,
*my*, *we* or *you*, or *I* (other than in a how-to question such as
`how do I tie a tie?`, or in a name such as *Elizabeth I*, *World War I* or
*Stage I* when no first-person wording follows: `Under this Act I pay...` is
personal). This is a word-level check, not understanding, so use `manual` or
`off` if a message must never be sent by mistake. Questions about suicide,
self-harm or lethal doses are never searched or offered for search, even after
`look it up` or `tell me more`; Jarvis shows the crisis help lines instead.
This errs on the side of caution, so `what is a lethal dose of caffeine?` gets
the help lines too. The reply starts with the words that were sent
(`I searched Wikipedia for '...'`), and a progress note is printed on stderr
while the search runs, so piped output stays clean.

### Search providers

| Provider | Setup |
| --- | --- |
| Wikipedia (default) | None. `JARVIS_WIKIPEDIA_LANG` picks the language edition (default `en`). |
| Brave Search | Set `JARVIS_BRAVE_API_KEY` to a [Brave Search API](https://brave.com/search/api/) key. |
| SearXNG | Set `JARVIS_SEARXNG_URL` to your instance, with `json` listed under `search.formats` in its `settings.yml`. |

`JARVIS_SEARCH_PROVIDER` (`wikipedia`, `brave` or `searxng`) picks one
explicitly; otherwise Brave is used when its key is set, then SearXNG when its
URL is set, then Wikipedia. With Brave and SearXNG, Jarvis also reads the top
three result pages so it can quote them. It skips any page on your own machine
or private network, checking both the addresses a name resolves to and, unless
you use a proxy, the address it actually connects to. When a page cannot be
read, Jarvis falls back to the search snippet.

### Limitations

- Summaries are *extractive*: Jarvis quotes the sentences that mention most of
  your question's keywords. It does not reason over them or write new text, so
  it can quote something related that does not quite answer the question.
  Check the sources.
- Wikipedia is an encyclopedia, not a live feed. Questions about news, weather,
  prices or scores get a note suggesting Brave Search or SearXNG instead;
  today's weather and recent alerts for a place have their own skills
  ([Weather and hazard alerts](#weather-and-hazard-alerts)).
- The search request gives up after 10 seconds without data. Result pages give
  up after 8 seconds without data, and Jarvis stops waiting for them 15 seconds
  after the search returns, using their search snippets instead. Press Ctrl-C
  to cancel a slow search in a session.
- Web search widens what Jarvis can answer, but Jarvis is still a rule-based
  assistant, not artificial general intelligence.

## Weather and hazard alerts

Three skills from [5-Mins](https://charles2ke.github.io/5-Mins/) read free
public feeds that need no API key:

```bash
jarvis "weather in Paris"
jarvis "what's the weather like in Tokyo"
jarvis "is it raining in Seattle"
jarvis "weather alerts for Miami"
jarvis "any earthquakes near Lima"
jarvis "hazards near Manila"
jarvis "space weather"
```

| Skill | Feeds |
| --- | --- |
| `weather` | Current conditions and today's range from the [Open-Meteo](https://open-meteo.com/) forecast. |
| `hazard-alerts` | Alerts from the last seven days: the US National Weather Service (US places only), USGS earthquakes of magnitude 4.5 or more within 300 km, and GDACS disaster alerts and NASA EONET natural events within 1000 km. |
| `space-weather` | The latest alerts, watches and warnings from the NOAA Space Weather Prediction Center. |

Places are found with the Open-Meteo geocoding API: name a city, add its
region or country (`Paris, Texas`), or give coordinates (`48.85, 2.35`). Only
the place name, never the rest of your message, is sent to the geocoder, and
the feeds receive its coordinates. Jarvis does not know where you are, so
`weather near me` asks you to name a place. Weather covers now and today only;
Jarvis does not forecast later days. Each alert feed is asked on its own, so one
failure never hides the others. Every reply lists its sources and when they were
read, and says that Jarvis is not an official warning system — follow your
local authorities.

These skills go online only when you ask, in `auto` or `manual` mode. With
`--web-search off` they say that web access is off rather than going online,
and, like a web search, they are never sent for a message about suicide or
self-harm.

## Text to speech

Jarvis can read text aloud with the `speak` skill:

```bash
jarvis "say out loud hello Charles"
jarvis 'read "the report is ready" aloud'
jarvis "text to speech: good morning"
```

Use `--speak` to hear every reply of a session:

```bash
jarvis --speak "what is the time?"
```

Speech stays dependency free: Jarvis uses the first text to speech program it
finds on the system — `say` (macOS), `espeak-ng`, `espeak` or `spd-say` (Linux),
or the PowerShell speech synthesiser (Windows). Set `JARVIS_TTS_COMMAND` to use
a different command (the text is appended as the last argument). If nothing is
available, Jarvis says so instead of failing.

## Natural language to text

Jarvis converts loosely written requests into the plain text its skills expect:

- `number-words` spells numbers out and reads them back: `spell out 42`,
  `42 in words`, `how do you spell 1005`, `forty-two in digits`,
  `write one hundred and five in digits`.
- Multi-line input and literal escapes are flattened, so `calculate\n  21 *\n 2`
  still reaches the calculator.
- Polite wrappers are trimmed and spelled numbers and operator words are
  rewritten, so `Jarvis, please tell me a joke` and
  `what is twenty one times two` route like `tell me a joke` and
  `what is 21 * 2`.
- The cloud `answer` skill also understands plain-text phrasings such as
  `answer in plain text: ...`, `give me a text answer to ...` and
  `turn this into text: ...`.

Rewriting only happens when the original wording does not already reach a more
specific skill, so existing phrasing keeps its usual routing. The helpers live
in `jarvis.nl` (`normalize`, `flatten`, `number_to_words`, `words_to_number`).

## Sign language

The `sign-language` skill explains sign language and describes, in words, how
to make everyday American Sign Language (ASL) signs — `how do I sign thank
you?`, `what is the sign for water`, `how do you say hello in sign language`.
`sign-language-alphabet` walks through the manual alphabet, `fingerspell`
spells a word or name letter by letter (`fingerspell Charles`, `spell hi in
ASL`), and `what signs do you know` lists every sign in the data set. Signs
Jarvis does not know are answered with a suggestion to fingerspell them.

The descriptions are hand-curated and offline, cover ASL only, and leave out
the facial expressions and movement that carry much of the grammar: they are a
starting point, not a substitute for learning from Deaf teachers and native
signers.

## Maritime safety (GMDSS)

The `gmdss` skill is an offline reference for the Global Maritime Distress and
Safety System: sea areas A1 to A4, DSC, EPIRB, SART, NAVTEX, Inmarsat, MMSI,
the mayday/pan-pan/securite priorities, the Morse SOS it replaced in 1999 and
the distress alert procedure. It is registered before `encyclopedia` so that
`what is an EPIRB?` reaches the maritime entries, and after `crisis-support` so
that a message such as `mayday, I want to kill myself` still reaches the help
lines. Say `gmdss topics` to list every entry.

## Emergency numbers

`emergency-numbers` knows the police, ambulance and fire numbers of all 193 UN
member states plus Kosovo, Palestine, Taiwan, Vatican City, Hong Kong and Macau
(`list emergency countries` shows them all):

```bash
jarvis "what are the emergency numbers in Japan?"
jarvis "ambulance number in India"
jarvis "call the police in Kenya"
jarvis "call an ambulance in Germany"
jarvis "text the police in France: there is a break-in at 12 Main St"
jarvis "email the emergency numbers for Kenya to me@example.com"
jarvis "dm the emergency numbers for Japan to +81 90 1234 5678"
```

Jarvis cannot place a call or send a message by itself. `emergency-call`,
`emergency-text` and `emergency-share` build a standard `tel:`, `sms:` or
`mailto:` link with the number and message filled in, and reply with it. A DM
is sent as a text message. Handing the link to your phone, messages or email
app is opt-in:

- `JARVIS_DIAL_ENABLED` — set to `1` (or `true`/`yes`) to let Jarvis open the
  link. You still press call or send in that app yourself.
- `JARVIS_DIAL_COMMAND` — optional command that opens a link, for example
  `kdeconnect-cli -n "My phone" --share` to pass it to a paired phone. The default is `open`
  on macOS, `xdg-open` on Linux and the URL protocol handler on Windows.

The numbers are an offline, hand-curated snapshot and can be wrong or out of
date, and some countries route calls differently by region, so confirm them
locally. On a mobile phone, 112 works across Europe and in many other
countries, and 911 works across North America and in many others. Emergency SMS
destinations are stored separately from voice numbers. Jarvis only prepares
emergency SMS for these verified services and includes their eligibility rules:

- France: [114](https://www.service-public.gouv.fr/particuliers/vosdroits/F33954),
  for people unable to hear or speak, even temporarily, including when speaking
  aloud would be unsafe.
- United Kingdom: [999 emergencySMS](https://www.relayuk.bt.com/how-to-use-relay-uk/contact-999-using-relay-uk.html),
  for people who are deaf, hard of hearing or have speech difficulties.
  Register your mobile first by texting `register` to 999, following the
  instructions and waiting for confirmation before relying on the service.

For other countries, including places where SMS availability varies locally,
Jarvis declines emergency SMS hand-offs and gives the voice number instead.
If you can speak, call. `crisis-support` is registered before these
skills, so a message that mentions self-harm still gets the crisis help lines.
The helpers live in `jarvis.emergency` (`find`, `tel_link`, `sms_link`,
`mailto_link`, `handoff`).

## The Bible as a knowledge source

The `bible` skill answers questions from an offline, hand-curated Bible
reference — passages, books and themes — and never reaches the network:

```bash
jarvis "bible John 3:16"                        # a verse, quoted
jarvis "what does the bible say about hope?"    # a theme, with its passages
jarvis "bible verses about anxiety"             # the same, phrased differently
jarvis "tell me about the book of Job"          # one of the 66 books
jarvis "who was Moses in the bible"             # people and figures
jarvis "bible shepherd"                         # keyword search over the verses
jarvis "bible topics"                           # every theme it knows
jarvis "books of the bible"                     # the canon, by testament
```

It knows all 66 books (testament, division, chapter count and a one-line
summary), a selection of well known verses quoted from the public domain World
English Bible, and themes such as love, fear, anxiety, grief, forgiveness,
faith, hope, justice, prayer, money and the Ten Commandments. References are
parsed forgivingly (`1 cor 13:13`, `Psalm 23:1`, `revelations`). Because the
selection is not the complete text of scripture, a passage it does not hold is
reported as missing rather than invented.

It is registered before `encyclopedia` so that `what is the bible` reaches the
Bible entries, and after `crisis-support` so that a message asking for help
still reaches the help lines.

## ASCII sketches

The `sketch` skill draws small ASCII pictures from a hand-curated, offline
gallery — `draw a cat`, `sketch a boat`, `can you draw me a house?`, `show me a
sketch of the moon`. Subjects are matched by name or alias and tolerate small
typos; an unknown subject is answered with the closest alternatives rather than
an invented drawing. `what can you sketch?` lists the whole gallery.

## Reading and writing braille

The `braille` skill translates Grade 1 (uncontracted) English braille in both
directions and never reaches the network:

- `read braille ⠓⠑⠇⠇⠕` → `hello`
- paste bare cells such as `⠠⠓⠊` and Jarvis reads them
- `write Hello 42 in braille` → `⠠⠓⠑⠇⠇⠕⠀⠼⠙⠃`
- `braille alphabet` prints the letter chart

Capitals use the capital sign (dot 6) and numbers the number sign (dots
3-4-5-6), with number mode ending at the next space. Letters, digits and common
punctuation are supported; anything else is reported rather than guessed.

## Answering any query with a cloud session

The `answer` skill hands a question to a GitHub Copilot cloud session running on
this repository with the Opus 5 max model (`claude-opus-5`, reasoning effort
`max`), and replies with a link to the session:

```bash
jarvis "answer how does the skill registry resolve matches?"
jarvis "ask the cloud what does memory.py persist?"
jarvis "spawn a cloud session on this repo to answer: who owns the CLI?"
```

It reads its configuration from the environment:

- `JARVIS_GITHUB_TOKEN` (or `GITHUB_TOKEN` / `GH_TOKEN`) — token used to start the session.
- `JARVIS_GITHUB_REPO` (or `GITHUB_REPOSITORY`) — `owner/repo` to run on (defaults to the `origin` remote of the checkout).
- `JARVIS_CLOUD_MODEL` — override the model (default `claude-opus-5`).
- `JARVIS_COPILOT_API` — override the Copilot API base URL (default `https://api.githubcopilot.com`).

If no token is configured, Jarvis explains what is missing instead of failing.

## Computer use (CUA)

The `computer-use` skill turns a plain English instruction into an ordered
computer use agent plan:

```bash
jarvis "use the computer to open Safari then click on Sign in and type hello"
jarvis "cua take a screenshot, scroll down 5, then press ctrl+s"
jarvis "computer use actions"
```

Planning is offline and has no side effects: Jarvis prints the numbered steps
it would take. Running them drives the real machine, so it is opt-in and reads
its configuration from the environment:

- `JARVIS_CUA_COMMAND` — the backend command that performs one action. Jarvis
  appends the action and its arguments, for example
  `my-cua-tool click "Save button"`.
- `JARVIS_CUA_ENABLED` — set to `1` (or `true`/`yes`) to let Jarvis actually
  run a plan. Without it, Jarvis replies with the plan and says how to enable
  execution.

The planner understands `open`, `click`, `double_click`, `right_click`,
`move`, `drag`, `type`, `key`, `scroll`, `wait` and `screenshot`, split on
`then`, `and` and commas. Steps it does not recognise are reported, together
with how much of the instruction it did understand, rather than guessed at.
The helpers live in `jarvis.cua` (`plan`, `execute`, `actions_chart`).

## Connected projects

Six of the author's other projects are built into Jarvis. Each is a Python
port of the project's logic or data, not a link to its running app, so Jarvis
never needs those sites to be up. Answers credit the project they come from and
link to it.

| Project | Skills | Ported into | Commit | Licence |
| --- | --- | --- | --- | --- |
| [tax-break](https://charles2ke.github.io/tax-break/) | `tax-estimate` | `tax.py` — the tax engine's salary calculators | [`a3d630c`](https://github.com/charles2ke/tax-break/commit/a3d630c7eb45d188ffb28da7507df948ca8be59b) | AGPL-3.0 (its `package.json` says MIT) |
| [Portfolio-Watcher](https://charles2ke.github.io/Portfolio-Watcher/) | `investment-math` | `investing.py` — the research calculators | [`4dddc15`](https://github.com/charles2ke/Portfolio-Watcher/commit/4dddc15734246445eedb7b040b0722bcbe49bc02) | MIT |
| [OpenTrading](https://charles2ke.github.io/OpenTrading/) | `paper-trading` | `papertrade.py` — the paper account and demo stocks | [`a252eb4`](https://github.com/charles2ke/OpenTrading/commit/a252eb47adae72cab77b04368f682b74710e9968) | Apache-2.0 |
| [beat-it](https://charles2ke.github.io/beat-it/) | `cancer-info`, `cancer-topics` | `cancer.py`, `cancer_data.py` — the reviewed cancer information | [`647f8d1`](https://github.com/charles2ke/beat-it/commit/647f8d15468105089d71a39de137408f427c5534) | AGPL-3.0-only |
| [5-Mins](https://charles2ke.github.io/5-Mins/) | `weather`, `hazard-alerts`, `space-weather` | `alerts.py` — the weather and alert feed lookups | [`560f23e`](https://github.com/charles2ke/5-Mins/commit/560f23e4fada678e605517d100e5f0a968e490ae) | AGPL-3.0 |
| [workout](https://charles2ke.github.io/workout/) | `workout-plan` | `workout.py` — the 7-day plan | [`0c0d425`](https://github.com/charles2ke/workout/commit/0c0d425759094649654a1cd483f6360bf8c15b71) | MIT |

Only the 5-Mins skills go online, straight to the public feeds and only as
[Weather and hazard alerts](#weather-and-hazard-alerts) describes; the rest
answer offline. The ported data is a snapshot from those commits and does not
update itself: the tax tables are listed under
[Income tax estimates](#income-tax-estimates), beat-it last reviewed its
entries on 12 November 2026, and paper-trading prices are OpenTrading's
built-in demo snapshot. To refresh beat-it's data, regenerate `cancer_data.py`
from a beat-it checkout with `python3 scripts/import_beat_it.py
/path/to/beat-it`; the other ports are updated by hand.

Some parts were left out on purpose: tax-break's document parsers, filing
exports and non-salary income; Portfolio-Watcher's market data; OpenTrading's
live quotes and server; beat-it's daily news feed; and 5-Mins' features for
alerting other people and its safety check-ins. Each module's docstring lists
what it follows and how it differs, and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) keeps each project's licence
notice.

## Project layout

```
src/jarvis/
  cli.py          command line entry point (jarvis)
  assistant.py    ties a registry, memory and the normaliser together
  skills.py       every built-in skill and the registry that routes to them
  memory.py       JSON backed memory, or RAM only when no path is given
  nl.py           natural language normalisation and number words
  <topic>.py      the data and logic behind a family of skills
                  (alerts, atlas, bible, braille, calculator, cancer, clock,
                  cloud, cua, dates, emergency, encyclopedia, finance,
                  investing, knowledge, maritime, papertrade, percentages,
                  poetry, science, signlanguage, sketch, speech, tax, traffic,
                  units, websearch, workout)
  cancer_data.py  beat-it's cancer information, generated by
                  scripts/import_beat_it.py
scripts/
  build_site.py   builds the GitHub Pages site from the skill registry
  import_beat_it.py  regenerates cancer_data.py from a beat-it checkout
tests/            one unittest module per topic
```

## Adding a skill

Skills are regular expressions paired with a handler. Register your own on top of
the defaults:

```python
from jarvis import Assistant, Skill, build_default_registry

registry = build_default_registry()
registry.register(
    Skill(
        name="coin-flip",
        description="Flip a coin.",
        patterns=[r"\bflip a coin\b"],
        handler=lambda match, context: "Heads.",
        examples=["flip a coin"],
    )
)

assistant = Assistant(registry=registry)
print(assistant.respond("flip a coin"))
```

The first skill whose pattern matches wins, so register more specific skills first.

## Development

Run the test suite with the standard library test runner — there is nothing to
install first:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

The suite never goes online. To also check web search against the real
Wikipedia, opt in to the live test:

```bash
JARVIS_LIVE_WEB_TESTS=1 PYTHONPATH=src python -m unittest tests.test_websearch
```

`pytest` works too, since `pyproject.toml` already points it at `tests/` and
`src/`. New skills should come with a test in the matching `tests/test_*.py`
module, and any new routing order should be covered there as well.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE). Files ported from the author's
other projects keep those projects' notices and terms in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
