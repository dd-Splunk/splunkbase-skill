"""Python-only behaviour: unit tests, search, concurrency and timeouts."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import splunkbase_urls as sb  # noqa: E402
from fake_splunkbase import FakeSplunkbase  # noqa: E402

SCRIPT = Path(sb.__file__)


class ParsingTests(unittest.TestCase):
    def test_parse_app_id(self):
        cases = {
            "4353": 4353,
            " 4353 ": 4353,
            "https://splunkbase.splunk.com/app/4353/": 4353,
            "https://splunkbase.splunk.com/app/4353": 4353,
            "https://splunkbase.splunk.com/app/4353/release/1.8.26/download/": 4353,
            "https://splunkbase.splunk.com/app/4353?x=1": 4353,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(sb.parse_app_id(text), expected)

    def test_parse_app_id_rejects_junk(self):
        for text in ("", "abc", "43x3", "https://example.com/app/abc/", "-1", "4353.5"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                sb.parse_app_id(text)

    def test_split_app_args(self):
        self.assertEqual(
            sb.split_app_args(["4353,7931", "833 742", ",1876,"]),
            ["4353", "7931", "833", "742", "1876"],
        )

    def test_normalize_splunk_version(self):
        self.assertEqual(sb.normalize_splunk_version("10.2.1"), "10.2")
        self.assertEqual(sb.normalize_splunk_version("9.4"), "9.4")
        self.assertEqual(sb.normalize_splunk_version("9.4.0.1"), "9.4")
        for bad in ("9", "latest", "9.x", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sb.normalize_splunk_version(bad)


class CleanTextTests(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(sb.clean_text("a\tb\n c\x1b[0m\x00d"), "a b c [0m d")
        self.assertEqual(sb.clean_text("  x  "), "x")
        self.assertEqual(len(sb.clean_text("y" * 999)), 120)
        self.assertEqual(sb.clean_text(123), "123")


class ImageTagTests(unittest.TestCase):
    def test_splunk_version_from_image(self):
        cases = {
            "splunk/splunk:9.4": "9.4",
            "splunk/splunk:9.4.2": "9.4",
            "splunk/splunk:10.6.1.1-rhel9": "10.6",
            "docker.io/splunk/universalforwarder:10.2-rhel9": "10.2",
            "localhost:5000/splunk/splunk:9.4.2@sha256:abc": "9.4",
            "  splunk/splunk:9.4  ": "9.4",
            "splunk/splunk:latest": None,
            "splunk/splunk": None,
            "localhost:5000/splunk/splunk": None,
            "splunk/splunk:${SPLUNK_VERSION:-9.4}": None,
            "splunk/splunk:33c3bf42cd73": None,
            "splunk/splunk@sha256:abc": None,
            "": None,
        }
        for ref, expected in cases.items():
            with self.subTest(ref=ref):
                self.assertEqual(sb.splunk_version_from_image(ref), expected)


class SelectReleaseTests(unittest.TestCase):
    def test_cloud_only_filters_before_version_matching(self):
        releases = [
            {"name": "3", "product_versions": ["10.0"], "cloud_compatible": False},
            {"name": "2", "product_versions": ["10.0"], "cloud_compatible": True},
        ]
        self.assertEqual(sb.select_release(releases, None, cloud_only=True)[0]["name"], "2")
        self.assertEqual(sb.select_release(releases, "10.0")[0]["name"], "3")

    def test_cloud_only_requires_an_explicit_true(self):
        with self.assertRaisesRegex(sb.SplunkbaseError, "Cloud compatible"):
            sb.select_release([{"name": "1"}, {"name": "2", "cloud_compatible": None}], cloud_only=True)

    def test_skips_leading_releases_without_a_usable_name(self):
        releases = [{"name": "null"}, {"name": ""}, {"name": None}, {"name": "1.0.0"}]
        chosen, compat, _ = sb.select_release(releases)
        self.assertEqual((chosen["name"], compat), ("1.0.0", "not-checked"))

    def test_names_are_case_insensitively_checked_for_null(self):
        with self.assertRaises(sb.SplunkbaseError):
            sb.select_release([{"name": "NULL"}, {"name": " None "}])

    def test_api_order_is_respected_not_re_sorted(self):
        releases = [{"name": "2.0.0"}, {"name": "10.0.0"}]
        self.assertEqual(sb.select_release(releases)[0]["name"], "2.0.0")

    def test_newest_compatible_wins_over_older_compatible(self):
        releases = [
            {"name": "3", "product_versions": ["10.0"]},
            {"name": "2", "product_versions": ["9.4", "10.0"]},
            {"name": "1", "product_versions": ["9.4"]},
        ]
        self.assertEqual(sb.select_release(releases, "9.4")[0]["name"], "2")

    def test_unknown_compat_stops_the_search_with_a_warning(self):
        releases = [{"name": "2", "product_versions": []}, {"name": "1", "product_versions": ["9.4"]}]
        chosen, compat, warnings = sb.select_release(releases, "9.4")
        self.assertEqual((chosen["name"], compat), ("2", "unknown"))
        self.assertEqual(len(warnings), 1)

    def test_error_when_nothing_matches(self):
        with self.assertRaisesRegex(sb.SplunkbaseError, "9.4.*supports 10.0 to 10.7"):
            sb.select_release([{"name": "1", "product_versions": ["10.7", "10.0"]}], "9.4")


class PythonCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = FakeSplunkbase().start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.server.reset()

    def run_cli(self, *args):
        env = dict(os.environ, SPLUNKBASE_BASE_URL=self.server.url)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, env=env, timeout=60,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def test_search_table(self):
        rc, out, _ = self.run_cli("--search", "aws")
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines()[0].split(), ["ID", "TYPE", "TITLE", "SLUG"])
        self.assertIn("Splunk Add-on for Amazon Web Services (AWS)", out)
        self.assertIn("Splunk_TA_aws", out)

    def test_search_json(self):
        rc, out, _ = self.run_cli("--search", "aws", "--format", "json")
        self.assertEqual(rc, 0)
        results = json.loads(out)
        self.assertEqual(results[0]["app_id"], 1876)
        self.assertEqual(set(results[0]), {"app_id", "title", "slug", "type", "archived"})

    def test_search_without_hits_fails(self):
        rc, out, err = self.run_cli("--search", "zzz-nothing")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("no apps found", err)

    def test_search_rejects_app_ids(self):
        rc, _, err = self.run_cli("--search", "aws", "4353")
        self.assertEqual(rc, 2)
        self.assertIn("cannot be combined", err)

    def test_table_format(self):
        rc, out, _ = self.run_cli("--format", "table", "--splunk-version", "10.6", "4353")
        self.assertEqual(rc, 0)
        header, row = out.splitlines()
        self.assertEqual(header.split(), ["ID", "TITLE", "VERSION", "COMPAT", "URL"])
        self.assertIn("Config Explorer", row)
        self.assertIn("1.8.24", row)

    def test_output_order_follows_input_even_when_responses_arrive_out_of_order(self):
        self.server.delay["/api/v1/app/7931/release"] = 0.6
        rc, out, _ = self.run_cli("7931", "4353", "833")
        self.assertEqual(rc, 0)
        ids = [part.split("/app/")[1].split("/")[0] for part in out.split(",")]
        self.assertEqual(ids, ["7931", "4353", "833"])

    def test_requests_run_concurrently(self):
        for app_id in (7931, 4353, 833):
            self.server.delay["/api/v1/app/%d/release" % app_id] = 0.8
        import time

        started = time.monotonic()
        rc, _, _ = self.run_cli("7931", "4353", "833")
        elapsed = time.monotonic() - started
        self.assertEqual(rc, 0)
        self.assertLess(elapsed, 2.2, "three 0.8s requests should overlap")

    def test_timeout_is_enforced(self):
        self.server.delay["/api/v1/app/7931"] = 2
        rc, out, err = self.run_cli("--timeout", "0.3", "--retries", "0", "7931")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("cannot reach", err)

    def test_user_agent_identifies_the_skill(self):
        rc, _, _ = self.run_cli("7931")
        self.assertEqual(rc, 0)
        self.assertTrue(self.server.user_agents)
        for agent in self.server.user_agents:
            self.assertEqual(agent, "splunkbase-skill/" + sb.__version__)


if __name__ == "__main__":
    unittest.main()
