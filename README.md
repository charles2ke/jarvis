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

## Built-in skills

| Skill | Example |
| --- | --- |
| crisis-support | `I have been thinking about hurting myself` |
| answer | `answer how does the skill registry work?` |
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
| science-solver | `solve 2x + 3 = 11` |
| braille | `read braille ⠓⠑⠇⠇⠕` |
| braille-alphabet | `braille alphabet` |
| atlas | `what is the capital of Japan?` |
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
| sign-language-alphabet | `sign language alphabet` |
| fingerspell | `fingerspell Charles` |
| sign-language-topics | `what signs do you know` |
| sign-language | `how do I sign thank you?` |
| encyclopedia | `what is gravity?` |
| encyclopedia-topics | `encyclopedia topics` |
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

The `atlas` skill answers offline geography questions — capitals, the country
behind a capital, continents, currencies, population estimates and the
countries it knows on a continent. Its data set is small and hand-curated, so
population figures are rounded estimates.

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
