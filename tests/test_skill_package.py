"""Keep the skill package honest: frontmatter, versions, links, file modes."""

import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_yaml(lines):
    """Parse the small YAML subset used here: nested maps, `- item` lists, scalars."""
    rows = []
    for raw in lines:
        if raw.strip() and not raw.lstrip().startswith("#"):
            rows.append((len(raw) - len(raw.lstrip()), raw.strip()))

    def scalar(text):
        return text[1:-1] if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'" else text

    def block(pos, indent):
        if rows[pos][1].startswith("- "):
            items = []
            while pos < len(rows) and rows[pos][0] == indent and rows[pos][1].startswith("- "):
                items.append(scalar(rows[pos][1][2:].strip()))
                pos += 1
            return items, pos
        mapping = {}
        while pos < len(rows) and rows[pos][0] == indent:
            match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", rows[pos][1])
            assert match, "cannot parse YAML line: %r" % rows[pos][1]
            key, value = match.groups()
            pos += 1
            if value:
                mapping[key] = scalar(value)
            elif pos < len(rows) and rows[pos][0] > indent:
                mapping[key], pos = block(pos, rows[pos][0])
            else:
                mapping[key] = ""
        return mapping, pos

    data, pos = block(0, rows[0][0])
    assert pos == len(rows), "unparsed YAML near %r" % (rows[pos][1],)
    return data


def frontmatter(path):
    lines = path.read_text().splitlines()
    assert lines[0] == "---", "SKILL.md must start with YAML frontmatter"
    return parse_yaml(lines[1 : lines.index("---", 1)])


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
        docs = ("SKILL.md", "README.md", "references/api.md", "references/docker-compose.md", "references/sources.md")
        for doc in docs:
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
        for path in ("/tests", "/.github", "/README.md", "/CHANGELOG.md", "/SECURITY.md", "/SUPPORT.md", "/evals.json"):
            with self.subTest(path=path):
                self.assertRegex(rules, r"(?m)^%s\s+export-ignore\s*$" % re.escape(path))

    def test_splunk_metadata_block_is_complete(self):
        splunk = self.meta["metadata"]["splunk"]
        for key in ("domain", "products", "entities", "triggers", "not-for", "outcomes"):
            with self.subTest(key=key):
                self.assertTrue(splunk.get(key), "metadata.splunk.%s is missing or empty" % key)
        for key in ("products", "entities", "triggers", "not-for", "outcomes"):
            self.assertIsInstance(splunk[key], list)

    def test_agent_interface_file(self):
        data = parse_yaml((ROOT / "agents" / "openai.yaml").read_text().splitlines())["interface"]
        self.assertTrue(data["display_name"])
        self.assertLessEqual(len(data["short_description"]), 64)
        self.assertIn("$" + self.meta["name"], data["default_prompt"])

    def test_evals_are_well_formed(self):
        evals = json.loads((ROOT / "evals.json").read_text())
        self.assertEqual(evals["skill_name"], self.meta["name"])
        ids = [e["id"] for e in evals["evals"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate eval ids")
        triggers = [e for e in evals["evals"] if "trigger" in e["tags"]]
        self.assertTrue([e for e in triggers if e["expected_skill"] == self.meta["name"]])
        self.assertTrue([e for e in triggers if e["expected_skill"] is None], "need negative trigger evals")
        for item in evals["evals"]:
            with self.subTest(eval=item["id"]):
                self.assertTrue(item["prompt"] and item["description"])
                if "expected_skill" not in item:
                    scorer = item["scorer"]
                    self.assertEqual(scorer["type"], "model_graded_qa")
                    self.assertIn("GRADE: $LETTER", scorer["grading_instructions"])
                    self.assertTrue(scorer["expected"])

    def test_skill_md_documents_every_cli_format_and_exit_code(self):
        text = self.skill_md.read_text()
        for needle in ("--search", "--splunk-version", "--format env", "--partial", "SPLUNKBASE_PASSWORD"):
            self.assertIn(needle, text)

    def test_license_file_matches_declared_license_and_ships(self):
        self.assertEqual(self.meta["license"], "Apache-2.0")
        text = (ROOT / "LICENSE").read_text()
        self.assertIn("Apache License", text)
        self.assertIn("Version 2.0, January 2004", text)
        self.assertNotRegex((ROOT / ".gitattributes").read_text(), r"(?m)^/LICENSE\s+export-ignore")

    def test_no_hard_coded_release_versions_in_skill_instructions(self):
        # Versions rot; the skill must tell Claude to look them up instead.
        text = self.skill_md.read_text()
        self.assertNotRegex(text, r"/release/\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
