"""Checks against the real Splunkbase API. Skipped unless SPLUNKBASE_LIVE=1.

Run weekly by .github/workflows/api-check.yml so API drift is noticed when it
happens, not when someone next generates a Compose file. A failure here means
either Splunkbase changed (update scripts/ and references/api.md) or an
anchor app was renamed (update ANCHORS).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import unittest
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
BASE = "https://splunkbase.splunk.com"

# Long-lived, well-known apps: id -> substring expected in the title.
ANCHORS = {
    1876: "Amazon Web Services",
    833: "Unix and Linux",
    742: "Microsoft Windows",
    4353: "Config Explorer",
    7931: "Splunk MCP Server",
}
RELEASE_KEYS = {"name", "published_datetime", "product_versions", "filename", "platform"}


def get(path):
    request = urllib.request.Request(BASE + path, headers={"User-Agent": "splunkbase-skill-api-check"})
    with urllib.request.urlopen(request, timeout=30) as resp:
        return json.load(resp)


@unittest.skipUnless(os.environ.get("SPLUNKBASE_LIVE") == "1", "set SPLUNKBASE_LIVE=1 to hit the real API")
class LiveApiTests(unittest.TestCase):
    def test_anchor_apps_keep_their_titles(self):
        for app_id, expected in ANCHORS.items():
            with self.subTest(app_id=app_id):
                self.assertIn(expected, get("/api/v1/app/%d" % app_id)["title"])

    def test_release_objects_have_the_fields_the_skill_reads(self):
        for app_id in ANCHORS:
            with self.subTest(app_id=app_id):
                releases = get("/api/v1/app/%d/release" % app_id)
                self.assertIsInstance(releases, list)
                self.assertTrue(releases)
                self.assertTrue(RELEASE_KEYS <= set(releases[0]), set(releases[0]))
                for versions in (r["product_versions"] for r in releases):
                    self.assertTrue(all(re.fullmatch(r"\d+\.\d+", v) for v in versions), versions)

    def test_first_release_is_still_the_newest_published(self):
        for app_id in ANCHORS:
            with self.subTest(app_id=app_id):
                releases = get("/api/v1/app/%d/release" % app_id)
                newest = max(releases, key=lambda r: r["published_datetime"])
                self.assertEqual(releases[0]["name"], newest["name"])

    def test_search_returns_ids_and_titles(self):
        data = get("/api/v1/app/?query=aws&limit=5")
        self.assertIn(1876, [r["uid"] for r in data["results"]])
        self.assertTrue(all(r["title"] for r in data["results"]))

    def test_python_script_end_to_end(self):
        ids = [str(i) for i in ANCHORS]
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "splunkbase_urls.py"), *ids],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        urls = proc.stdout.strip().split(",")
        self.assertEqual(len(urls), len(ids))
        for url, app_id in zip(urls, ids):
            self.assertRegex(url, r"^https://splunkbase\.splunk\.com/app/%s/release/[^/]+/download/$" % app_id)

    @unittest.skipUnless(shutil.which("jq") and shutil.which("curl"), "needs curl and jq")
    def test_bash_and_python_agree_on_real_data(self):
        args = [str(i) for i in ANCHORS]
        python = subprocess.run([sys.executable, str(SCRIPTS / "splunkbase_urls.py"), "--format", "json", *args],
                                capture_output=True, text=True, timeout=120)
        bash = subprocess.run(["bash", str(SCRIPTS / "get_splunkbase_urls.sh"), "--format", "json", *args],
                              capture_output=True, text=True, timeout=240)
        self.assertEqual((python.returncode, bash.returncode), (0, 0), python.stderr + bash.stderr)
        self.assertEqual(json.loads(python.stdout), json.loads(bash.stdout))


if __name__ == "__main__":
    unittest.main()
