"""Keep the skill package honest: frontmatter, versions, links, file modes."""

import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def frontmatter(path):
    """Tiny parser for the flat/one-level YAML used in SKILL.md (no PyYAML needed)."""
    lines = path.read_text().splitlines()
    assert lines[0] == "---", "SKILL.md must start with YAML frontmatter"
    end = lines.index("---", 1)
    data, parent = {}, None
    for line in lines[1:end]:
        if not line.strip():
            continue
        match = re.match(r"^(\s*)([A-Za-z0-9_-]+):\s*(.*)$", line)
        assert match, "cannot parse frontmatter line: %r" % line
        indent, key, value = match.groups()
        if indent and parent is not None:
            data[parent][key] = value.strip()
        elif value == "":
            data[key], parent = {}, key
        else:
            data[key], parent = value.strip(), None
    return data


def script_version(path):
    text = path.read_text()
    return re.search(r'^(?:__version__|VERSION)\s*=\s*"([^"]+)"', text, re.M).group(1)


class SkillFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill_md = ROOT / "SKILL.md"
        cls.meta = frontmatter(cls.skill_md)

    def test_name_follows_the_skill_naming_rules(self):
        self.assertRegex(self.meta["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(self.meta["name"]), 64)
        self.assertEqual(self.meta["name"], "splunkbase-skill")

    def test_description_says_what_and_when_within_limits(self):
        description = self.meta["description"]
        self.assertGreater(len(description), 80)
        self.assertLessEqual(len(description), 1024)
        self.assertNotRegex(description, r"[<>]")
        self.assertIn("Use when", description)

    def test_only_documented_frontmatter_keys_are_used(self):
        allowed = {"name", "description", "license", "allowed-tools", "metadata"}
        self.assertLessEqual(set(self.meta), allowed)

    def test_skill_md_stays_small(self):
        self.assertLess(len(self.skill_md.read_text().splitlines()), 500)

    def test_versions_agree_everywhere(self):
        declared = self.meta["metadata"]["version"]
        self.assertRegex(declared, r"^\d+\.\d+\.\d+$")
        self.assertEqual(script_version(ROOT / "scripts" / "splunkbase_urls.py"), declared)
        self.assertEqual(script_version(ROOT / "scripts" / "get_splunkbase_urls.sh"), declared)
        changelog = (ROOT / "CHANGELOG.md").read_text()
        first = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M).group(1)
        self.assertEqual(first, declared, "newest CHANGELOG entry must match metadata.version")

    def test_relative_links_resolve(self):
        for doc in ("SKILL.md", "README.md", "references/api.md", "references/docker-compose.md"):
            path = ROOT / doc
            for target in re.findall(r"\]\((?!https?:|#|mailto:)([^)\s#]+)", path.read_text()):
                with self.subTest(doc=doc, target=target):
                    self.assertTrue((path.parent / target).exists(), "%s -> %s" % (doc, target))

    def test_every_script_mentioned_in_skill_md_exists(self):
        for name in set(re.findall(r"scripts/([A-Za-z0-9_.-]+)", self.skill_md.read_text())):
            with self.subTest(script=name):
                self.assertTrue((ROOT / "scripts" / name).is_file())

    def test_scripts_are_executable(self):
        for script in (ROOT / "scripts").iterdir():
            if script.suffix in (".py", ".sh"):
                with self.subTest(script=script.name):
                    self.assertTrue(os.access(script, os.X_OK))

    def test_release_archive_excludes_development_files(self):
        rules = (ROOT / ".gitattributes").read_text()
        for path in ("/tests", "/.github", "/README.md", "/CHANGELOG.md"):
            with self.subTest(path=path):
                self.assertRegex(rules, r"(?m)^%s\s+export-ignore\s*$" % re.escape(path))

    def test_no_hard_coded_release_versions_in_skill_instructions(self):
        # Versions rot; the skill must tell Claude to look them up instead.
        text = self.skill_md.read_text()
        self.assertNotRegex(text, r"/release/\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
