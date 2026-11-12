"""Render the website's raster images with Playwright.

The social card (Open Graph / Twitter) and the PNG app icons are committed
to ``site/assets``. Re-run this script after changing the logo or the card
design::

    pip install playwright && python -m playwright install chromium
    python scripts/render_images.py

The card avoids numbers such as the skill count so it never goes stale.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "site" / "assets"

FONT_STACK = "Inter, 'DejaVu Sans', system-ui, sans-serif"
MONO_STACK = "'DejaVu Sans Mono', 'Liberation Mono', monospace"


#: Prompts shown on the social card; each reply must fit on one line.
CARD_PROMPTS = ("calculate 21 * 2", "convert 10 km to miles", "write hello in braille")


def _logo() -> str:
    return (ASSETS / "favicon.svg").read_text(encoding="utf-8")


def _transcript() -> str:
    """Return real Jarvis replies to :data:`CARD_PROMPTS` as card markup."""
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from jarvis.assistant import Assistant
    from jarvis.memory import Memory

    assistant = Assistant(memory=Memory(None))
    lines = []
    for prompt in CARD_PROMPTS:
        reply = assistant.respond(prompt)
        if "\n" in reply or len(reply) > 30:
            raise ValueError(f"card reply for {prompt!r} is too long: {reply!r}")
        lines.append(
            f'<div class="you-line"><span class="you">you&gt;</span> <span class="dim">{html.escape(prompt)}</span></div>'
            f'<div><span class="jar">jarvis&gt;</span> <span class="dim">{html.escape(reply)}</span></div>'
        )
    return "".join(lines)


def social_card_html() -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ box-sizing: border-box; margin: 0; }}
  html, body {{ width: 1200px; height: 630px; }}
  body {{
    font-family: {FONT_STACK};
    background: #070b18;
    color: #e8ecff;
    overflow: hidden;
    position: relative;
  }}
  .blob {{ position: absolute; border-radius: 50%; filter: blur(90px); opacity: .75; }}
  .b1 {{ width: 620px; height: 620px; left: -160px; top: -260px; background: #22d3ee55; }}
  .b2 {{ width: 640px; height: 640px; right: -220px; top: -120px; background: #8b5cf666; }}
  .b3 {{ width: 520px; height: 520px; left: 380px; bottom: -380px; background: #f472b644; }}
  .grid {{
    position: absolute; inset: 0;
    background-image:
      linear-gradient(#ffffff0c 1px, transparent 1px),
      linear-gradient(90deg, #ffffff0c 1px, transparent 1px);
    background-size: 48px 48px;
    mask-image: radial-gradient(ellipse at 40% 40%, #000 30%, transparent 75%);
  }}
  .content {{
    position: absolute; inset: 72px 80px; display: flex; gap: 48px; align-items: stretch;
  }}
  .left {{ flex: 1; display: flex; flex-direction: column; min-width: 0; }}
  .brand {{ display: flex; align-items: center; gap: 20px; }}
  .brand svg {{ width: 72px; height: 72px; filter: drop-shadow(0 10px 30px #8b5cf688); }}
  .brand span {{ font-size: 44px; font-weight: 800; letter-spacing: -0.02em; }}
  h1 {{
    margin-top: 40px; font-size: 58px; line-height: 1.06; font-weight: 800;
    letter-spacing: -0.035em;
  }}
  .grad {{
    background: linear-gradient(100deg, #22d3ee, #8b5cf6 55%, #f472b6);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }}
  .pills {{ margin-top: auto; display: flex; gap: 10px; }}
  .pill {{
    font-size: 19px; font-weight: 600; padding: 10px 17px; border-radius: 999px; white-space: nowrap;
    background: #ffffff10; border: 1px solid #ffffff22; color: #cfd6ff;
  }}
  .term {{
    align-self: center; width: 440px; flex: none;
    border-radius: 18px; background: #0b1124e6; border: 1px solid #ffffff24;
    box-shadow: 0 30px 80px #00000080, 0 0 0 1px #8b5cf633;
    font-family: {MONO_STACK}; font-size: 17px; line-height: 1.7;
    overflow: hidden;
  }}
  .bar {{ display: flex; gap: 8px; padding: 14px 18px; background: #ffffff0a; }}
  .bar i {{ width: 12px; height: 12px; border-radius: 50%; display: block; }}
  .bar i:nth-child(1) {{ background: #ff5f57; }}
  .bar i:nth-child(2) {{ background: #febc2e; }}
  .bar i:nth-child(3) {{ background: #28c840; }}
  .lines {{ padding: 16px 20px 22px; white-space: pre; }}
  .lines div + .you-line {{ margin-top: 8px; }}
  .you {{ color: #4ade80; font-weight: 700; }}
  .jar {{ color: #22d3ee; font-weight: 700; }}
  .dim {{ color: #c3cae8; }}
</style></head><body>
  <div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div>
  <div class="grid"></div>
  <div class="content">
    <div class="left">
      <div class="brand">{_logo()}<span>Jarvis</span></div>
      <h1>Your private AI companion, <span class="grad">right in your terminal.</span></h1>
      <div class="pills">
        <span class="pill">Offline-first</span>
        <span class="pill">Zero dependencies</span>
        <span class="pill">Open source</span>
      </div>
    </div>
    <div class="term">
      <div class="bar"><i></i><i></i><i></i></div>
      <div class="lines">{_transcript()}</div>
    </div>
  </div>
</body></html>"""


def icon_html(size: int) -> str:
    inset = round(size * 0.1)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin: 0; }}
  html, body {{ width: {size}px; height: {size}px; background: #070b18; overflow: hidden; }}
  body {{ display: grid; place-items: center; }}
  svg {{ width: {size - 2 * inset}px; height: {size - 2 * inset}px; }}
</style></head><body>{_logo()}</body></html>"""


def render(out_dir: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    jobs = [
        ("social-card.png", social_card_html(), 1200, 630),
        ("apple-touch-icon.png", icon_html(180), 180, 180),
        ("icon-512.png", icon_html(512), 512, 512),
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for name, markup, width, height in jobs:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.set_content(markup)
                page.evaluate("document.fonts.ready")
                target = out_dir / name
                page.screenshot(path=str(target), clip={"x": 0, "y": 0, "width": width, "height": height})
                page.close()
                written.append(target)
        finally:
            browser.close()
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ASSETS, help="output directory (default: site/assets)")
    args = parser.parse_args(argv)
    for path in render(args.out):
        print(f"Wrote {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
