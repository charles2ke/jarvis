"""Browser tests for the website, driven by Playwright and Chromium.

They are skipped when Playwright or its Chromium build is missing, unless
``JARVIS_REQUIRE_BROWSER_TESTS=1`` is set (CI sets it). To run them::

    pip install playwright && python -m playwright install chromium
    PYTHONPATH=src python -m unittest tests.test_site_browser

Set ``JARVIS_SCREENSHOT_DIR`` to save a screenshot of each scenario.
"""

import functools
import http.server
import importlib.util
import os
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = os.environ.get("JARVIS_REQUIRE_BROWSER_TESTS") == "1"
SHOTS = os.environ.get("JARVIS_SCREENSHOT_DIR")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # pragma: no cover - depends on the environment
    sync_playwright = None

CARDS = "#skill-grid > .card:not([hidden])"


def _skip_or_fail(reason):
    if REQUIRED:
        raise RuntimeError(f"browser tests are required but {reason}")
    raise unittest.SkipTest(reason)


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("build_site", module)
    spec.loader.exec_module(module)
    return module


class _SiteHandler(http.server.SimpleHTTPRequestHandler):
    """Serve the built site, answering missing paths with 404.html like GitHub Pages."""

    def send_error(self, code, message=None, explain=None):
        page = Path(self.directory) / "404.html"
        if code != 404 or not page.is_file():
            return super().send_error(code, message, explain)
        body = page.read_bytes()
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, *args):
        pass


def setUpModule():
    global server, base_url, playwright, browser, _tmp
    if sync_playwright is None:
        _skip_or_fail("Playwright is not installed")
    _tmp = tempfile.TemporaryDirectory()
    site = Path(_tmp.name) / "site"
    handler = functools.partial(_SiteHandler, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    base_url = f"http://127.0.0.1:{server.server_address[1]}/"
    _load_builder().build(site, base_url)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch()
    except Exception as exc:  # pragma: no cover - depends on the environment
        playwright.stop()
        server.shutdown()
        _tmp.cleanup()
        _skip_or_fail(f"Chromium could not start ({exc.__class__.__name__})")


def tearDownModule():
    browser.close()
    playwright.stop()
    server.shutdown()
    server.server_close()
    _tmp.cleanup()


class SiteBrowserTests(unittest.TestCase):
    def open(self, path="", *, width=1280, height=800, motion="reduce", scheme="dark", **options):
        context = browser.new_context(
            viewport={"width": width, "height": height},
            reduced_motion=motion,
            color_scheme=scheme,
            **options,
        )
        self.addCleanup(context.close)
        page = context.new_page()
        page.errors = []
        page.on(
            "console",
            lambda msg: msg.type == "error" and page.errors.append(f"{msg.text} [{msg.location.get('url', '')}]"),
        )
        page.on("pageerror", lambda exc: page.errors.append(str(exc)))
        page.goto(base_url + path)
        return page

    def shot(self, page, name, **options):
        if SHOTS:
            Path(SHOTS).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(SHOTS) / name), **options)

    def assert_clean(self, page, allow=()):
        """No script errors, failed requests or Content Security Policy violations."""

        self.assertEqual([error for error in page.errors if error not in allow], [])

    def search(self, page, text):
        page.fill("#q", text)
        expect(page.locator("#result-count")).not_to_contain_text("featured")
        page.press("#q", "Enter")  # submitting scrolls to the results

    def test_home_page_loads_cleanly_on_desktop_and_mobile(self):
        for name, width, height in (("home-desktop.png", 1280, 800), ("home-mobile.png", 375, 812)):
            with self.subTest(width=width):
                page = self.open(width=width, height=height)
                expect(page.locator(CARDS)).to_have_count(len(page.locator("[data-featured]").all()))
                expect(page.locator("#result-count")).to_contain_text("featured skills of 72")
                overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                self.assertLessEqual(overflow, 0, "the page scrolls sideways")
                self.shot(page, name, full_page=True)
                self.assert_clean(page)

    def test_search_filters_highlights_and_updates_the_address(self):
        page = self.open()
        self.search(page, "braille")
        expect(page.locator("#skill-braille")).to_be_visible()
        expect(page.locator("#skill-braille-alphabet")).to_be_visible()
        expect(page.locator(f"{CARDS} mark").first).to_have_text("braille", ignore_case=True)
        self.assertLess(page.locator(CARDS).count(), 72)
        expect(page).to_have_url(base_url + "?q=braille")
        self.shot(page, "search-braille.png")
        self.assert_clean(page)

    def test_misspelt_search_is_corrected(self):
        page = self.open()
        self.search(page, "brialle")
        expect(page.locator("#did-you-mean")).to_contain_text("braille")
        expect(page.locator("#skill-braille")).to_be_visible()
        self.shot(page, "did-you-mean.png")
        self.assert_clean(page)

    def test_shared_link_restores_the_search_and_shows_topic_matches(self):
        page = self.open("?q=kenya")
        expect(page.locator("#q")).to_have_value("kenya")
        card = page.locator("#skill-emergency-numbers")
        expect(card).to_be_visible()
        expect(card.locator(".matches")).to_contain_text("Kenya")
        self.assert_clean(page)

    def test_category_chip_filters_the_grid(self):
        page = self.open()
        chip = page.locator('.chip[data-category="accessibility"]')
        expected = int(chip.locator(".chip-count").inner_text())
        chip.click()
        expect(chip).to_have_attribute("aria-pressed", "true")
        expect(page.locator(CARDS)).to_have_count(expected)
        self.assertEqual(
            set(page.locator(CARDS).evaluate_all("cards => cards.map(c => c.dataset.category)")),
            {"accessibility"},
        )
        expect(page).to_have_url(base_url + "?cat=accessibility")
        page.evaluate("document.getElementById('skills').scrollIntoView()")
        self.shot(page, "category-accessibility.png")
        self.assert_clean(page)

    def test_keyboard_shortcuts(self):
        page = self.open()
        page.keyboard.press("/")
        self.assertEqual(page.evaluate("document.activeElement.id"), "q")
        page.keyboard.type("haiku")
        expect(page.locator("#result-count")).to_contain_text("haiku")
        page.keyboard.press("Escape")
        expect(page.locator("#q")).to_have_value("")
        expect(page.locator("#result-count")).to_contain_text("featured")
        self.assert_clean(page)

    def test_empty_state_offers_a_way_back(self):
        page = self.open()
        self.search(page, "zzqxjv")
        expect(page.locator("#empty-state")).to_be_visible()
        expect(page.locator(CARDS)).to_have_count(0)
        self.shot(page, "empty-state.png")
        page.locator('#empty-state [data-action="clear"]').click()
        expect(page.locator("#empty-state")).to_be_hidden()
        expect(page.locator("#q")).to_have_value("")
        self.assert_clean(page)

    def test_show_all_and_links_to_hidden_skills(self):
        page = self.open()
        page.click("#show-all")
        expect(page.locator(CARDS)).to_have_count(72)
        expect(page.locator("#show-all-wrap")).to_be_hidden()

        linked = self.open("#skill-gmdss-topics")
        expect(linked.locator("#skill-gmdss-topics")).to_be_visible()
        self.assert_clean(page)
        self.assert_clean(linked)

    def test_theme_choice_is_remembered(self):
        page = self.open()
        root = page.locator("html")
        expect(root).to_have_attribute("data-theme", "dark")
        page.click("#theme-toggle")
        expect(root).to_have_attribute("data-theme", "light")
        page.reload()
        expect(root).to_have_attribute("data-theme", "light")
        self.shot(page, "home-light.png")
        self.assert_clean(page)

    def test_demo_replays_the_chosen_prompt(self):
        page = self.open()
        tab = page.locator(".demo-tab", has_text="convert 10 km to miles")
        tab.click()
        expect(tab).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#terminal-log")).to_contain_text("6.2137 miles")
        self.shot(page, "demo.png", clip=page.locator("#demo").bounding_box())
        self.assert_clean(page)

    def test_not_found_page_searches_the_site(self):
        page = self.open("no/such/page")
        expect(page).to_have_title("Page not found · Jarvis")
        expect(page.locator(".btn-primary")).to_have_css("border-radius", re.compile(r"[1-9]"))
        self.shot(page, "not-found.png")
        page.fill("#q", "braille")
        page.keyboard.press("Enter")
        page.wait_for_url(base_url + "?q=braille")
        expect(page.locator("#skill-braille")).to_be_visible()
        # The 404 page itself is served with a 404 status, which Chromium logs.
        status = f"Failed to load resource: the server responded with a status of 404 (Not Found) [{base_url}no/such/page]"
        self.assert_clean(page, allow=(status,))


if __name__ == "__main__":
    unittest.main()
