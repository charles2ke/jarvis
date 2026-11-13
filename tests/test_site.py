"""Tests for the website generator in ``scripts/build_site.py``."""

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("build_site", module)
    spec.loader.exec_module(module)
    return module


build_site = _load_builder()

from jarvis.skills import Skill, build_default_registry  # noqa: E402

BASE_URL = "https://example.org/jarvis/"
BUILT = date(2026, 1, 2)


class BuiltSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = build_site.build(Path(cls._tmp.name) / "site", BASE_URL, BUILT)
        cls.index = (cls.out / "index.html").read_text(encoding="utf-8")
        cls.skills = list(build_default_registry())

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def meta(self, key, value):
        match = re.search(rf'<meta {key}="{re.escape(value)}" content="([^"]*)"', self.index)
        self.assertIsNotNone(match, f"missing <meta {key}={value!r}>")
        return match.group(1)

    def test_every_skill_is_in_exactly_one_category(self):
        listed = [name for _, _, _, names in build_site.CATEGORIES for name in names]
        self.assertEqual(len(listed), len(set(listed)), "a skill is listed in two categories")
        self.assertEqual(set(listed), {skill.name for skill in self.skills})

    def test_every_skill_has_a_linkable_card(self):
        self.assertEqual(self.index.count('<article class="card"'), len(self.skills))
        for skill in self.skills:
            self.assertIn(f'id="skill-{skill.name}"', self.index)

    def test_search_engine_metadata(self):
        self.assertIn(f'<link rel="canonical" href="{BASE_URL}">', self.index)
        self.assertLessEqual(len(self.meta("name", "description")), 160)
        self.assertEqual(self.meta("property", "og:url"), BASE_URL)
        self.assertEqual(self.meta("property", "og:image"), BASE_URL + "assets/social-card.png")
        self.assertTrue((self.out / "assets" / "social-card.png").is_file())
        self.assertNotIn("{{", self.index)

    def test_structured_data_offers_a_site_search(self):
        block = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.index, re.S)
        data = json.loads(block.group(1))
        by_type = {node["@type"]: node for node in data["@graph"]}
        self.assertEqual(by_type["SoftwareApplication"]["url"], BASE_URL)
        action = by_type["WebSite"]["potentialAction"]
        self.assertEqual(action["target"]["urlTemplate"], BASE_URL + "?q={search_term_string}")

    def test_sitemap_and_robots(self):
        tree = ElementTree.parse(self.out / "sitemap.xml")
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        self.assertEqual([loc.text for loc in tree.findall(".//s:loc", ns)], [BASE_URL])
        self.assertEqual(tree.find(".//s:lastmod", ns).text, "2026-01-02")
        robots = (self.out / "robots.txt").read_text(encoding="utf-8")
        self.assertIn(f"Sitemap: {BASE_URL}sitemap.xml", robots)

    def test_pages_satisfy_the_content_security_policy(self):
        for name in ("index.html", "404.html"):
            page = (self.out / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertNotRegex(page, r"\sstyle=")
                self.assertNotRegex(page, r"\son[a-z]+=")
                for tag in re.findall(r"<script\b[^>]*>", page):
                    self.assertTrue(
                        "src=" in tag or "application/ld+json" in tag or "application/json" in tag,
                        f"inline script: {tag}",
                    )
                for url in re.findall(r'<(?:script|link)\b[^>]*(?:src|href)="([^"]+)"', page):
                    if url.startswith("http"):
                        self.assertTrue(url.startswith(BASE_URL), f"external resource: {url}")

    def test_not_found_page_works_at_any_depth(self):
        page = (self.out / "404.html").read_text(encoding="utf-8")
        self.assertIn('href="/jarvis/assets/style.css"', page)
        self.assertIn('action="/jarvis/"', page)

    def test_demo_replies_are_real_answers(self):
        fallback = build_site.Assistant(memory=build_site.Memory(None)).respond("qwertyuiop")
        for transcript in build_site.demo_transcripts():
            with self.subTest(prompt=transcript["prompt"]):
                self.assertNotEqual(transcript["reply"], fallback)

    def test_build_is_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            again = build_site.build(Path(tmp) / "site", BASE_URL, BUILT)
            self.assertEqual((again / "index.html").read_text(encoding="utf-8"), self.index)


class EscapingTests(unittest.TestCase):
    def test_card_text_is_escaped(self):
        skill = Skill(
            name="x",
            description='<img src=x onerror="alert(1)">',
            patterns=(),
            handler=lambda *_: "",
            examples=("say <b>hi</b> & 'bye'",),
        )
        html = build_site.render_card(skill, "everyday", "Everyday", ["<i>topic</i>"], False)
        self.assertNotIn("<img", html)
        self.assertNotIn("<b>", html)
        self.assertNotIn("<i>topic", html)

    def test_json_data_cannot_close_its_script_block(self):
        text = build_site._json_for_script({"reply": "</script><script>alert(1)</script>"})
        self.assertNotIn("</script", text)
        self.assertEqual(json.loads(text)["reply"], "</script><script>alert(1)</script>")


class OutputDirectoryTests(unittest.TestCase):
    def test_refuses_to_replace_the_repository(self):
        with self.assertRaises(ValueError):
            build_site.build(ROOT, BASE_URL, BUILT)

    def test_refuses_to_replace_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = Path(tmp) / "notes.txt"
            keep.write_text("precious", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_site.build(Path(tmp), BASE_URL, BUILT)
            self.assertTrue(keep.exists())

    def test_rejects_a_relative_base_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                build_site.build(Path(tmp) / "site", "jarvis/", BUILT)


if __name__ == "__main__":
    unittest.main()
