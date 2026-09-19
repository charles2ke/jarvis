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
| mental-health | `I feel anxious` |
| console | `I am having a rough day` |
| story | `tell me a story` |
| joke | `tell me a joke` |
| uplift | `cheer me up` |
| greeting | `hello` |
| remember-name | `my name is Charles` |
| recall-name | `what is my name?` |
| time | `what is the time?` |
| date | `what day is it` |
| calculator | `calculate 21 * 2` |
| add-note | `remember buy milk` |
| list-notes | `list my notes` |
| clear-notes | `clear my notes` |
| psychiatrist | `I feel anxious about work` |
| mood-history | `how have I been feeling` |
| clear-mood-history | `clear my mood history` |
| love-support | `my girlfriend and I keep fighting` |
| emotional-support | `I need some emotional support` |
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
heartbreak, conflict and new feelings.

The `encyclopedia` skill answers factual questions (`what is ...`, `who was
...`, `tell me about ...`, `define ...`) from a small built-in, offline set of
articles — it never reaches the network. Lookups ignore case, punctuation and
aliases, tolerate small typos, and suggest close titles when a topic is
missing. It is registered last so that `what is the time?`, `what is my name?`
and `what is 21 * 2` still reach their own skills. Say `encyclopedia topics` to
list every entry.

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
