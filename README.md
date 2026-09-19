# jarvis

Personal AI Companion — a small, dependency-free assistant you can run from your terminal.

## Install

```bash
pip install -e .
```

Python 3.10+ is required. There are no runtime dependencies.

## Usage

Interactive session:

```bash
jarvis
```

One-shot question:

```bash
jarvis "calculate 21 * 2"
```

Or without installing:

```bash
PYTHONPATH=src python -m jarvis "what is the time?"
```

Useful flags:

- `--memory PATH` — where to persist memory (default `~/.jarvis/memory.json`, override the directory with `JARVIS_HOME`).
- `--no-memory` — keep everything in RAM for the session.
- `--speak` — also read every reply aloud (see [Text to speech](#text-to-speech)).

## Built-in skills

| Skill | Example |
| --- | --- |
| crisis-support | `I have been thinking about hurting myself` |
| answer | `answer how does the skill registry work?` |
| speak | `say out loud hello Charles` |
| computer-use | `use the computer to open Safari then click on Sign in` |
| cua-actions | `computer use actions` |
| mental-health | `I feel anxious` |
| console | `I am having a rough day` |
| story | `tell me a story` |
| joke | `tell me a joke` |
| uplift | `cheer me up` |
| role-model | `be my role model` |
| coach | `coach me` |
| self-care | `how do I take care of myself` |
| greeting | `hello` |
| remember-name | `my name is Charles` |
| recall-name | `what is my name?` |
| time | `what is the time?` |
| date | `what day is it` |
| calculator | `calculate 21 * 2` |
| number-words | `spell out 42` |
| science-solver | `solve 2x + 3 = 11` |
| braille | `read braille ⠓⠑⠇⠇⠕` |
| braille-alphabet | `braille alphabet` |
| atlas | `what is the capital of Japan?` |
| cities | `what cities are in Japan?` |
| time-zone | `what time zone is Japan in?` |
| wonders | `what are the seven wonders of the world?` |
| history | `what happened in 1969?` |
| traffic-signs | `what does a give way sign mean?` |
| add-knowledge-website | `add https://example.com as a knowledge source` |
| add-knowledge-file | `add the file notes.md as a knowledge source` |
| list-knowledge-sources | `list my knowledge sources` |
| clear-knowledge-sources | `clear my knowledge sources` |
| add-note | `remember buy milk` |
| list-notes | `list my notes` |
| clear-notes | `clear my notes` |
| psychiatrist | `I feel anxious about work` |
| mood-history | `how have I been feeling` |
| clear-mood-history | `clear my mood history` |
| love-support | `my girlfriend and I keep fighting` |
| couples-counseling | `we need couples counseling` |
| midlife-counseling | `I think I am having a midlife crisis` |
| career-counselling | `I am thinking about changing careers` |
| emotional-support | `I need some emotional support` |
| sketch-topics | `what can you sketch?` |
| sketch | `draw a cat` |
| sign-language-alphabet | `sign language alphabet` |
| fingerspell | `fingerspell Charles` |
| sign-language-topics | `what signs do you know` |
| sign-language | `how do I sign thank you?` |
| encyclopedia | `what is gravity?` |
| encyclopedia-topics | `encyclopedia topics` |
| gmdss | `what is an EPIRB?` |
| gmdss-topics | `gmdss topics` |
| help | `help` |
| farewell | `goodbye` |

The wellbeing skills are registered first so that a message such as
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

The `encyclopedia` skill answers factual questions (`what is ...`, `who was
...`, `tell me about ...`, `define ...`) from a small built-in, offline set of
articles — it never reaches the network. Lookups ignore case, punctuation and
aliases, tolerate small typos, and suggest close titles when a topic is
missing. It is registered last so that `what is the time?`, `what is my name?`
and `what is 21 * 2` still reach their own skills. Say `encyclopedia topics` to
list every entry.

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
fetching a website reaches the network.

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

The `gmdss` skill is an offline reference for the Global Maritime Distress and
Safety System: sea areas A1 to A4, DSC, EPIRB, SART, NAVTEX, Inmarsat, MMSI,
the mayday/pan-pan/securite priorities, the Morse SOS it replaced in 1999 and
the distress alert procedure. It is registered before `encyclopedia` so that
`what is an EPIRB?` reaches the maritime entries, and after `crisis-support` so
that a message such as `mayday, I want to kill myself` still reaches the help
lines. Say `gmdss topics` to list every entry.

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

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
