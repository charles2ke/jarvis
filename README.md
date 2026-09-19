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
| couples-counseling | `we need couples counseling` |
| midlife-counseling | `I think I am having a midlife crisis` |
| emotional-support | `I need some emotional support` |
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
