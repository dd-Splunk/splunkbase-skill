"""Python-only behaviour: unit tests, search, concurrency and timeouts."""

import json
import os
import subprocess
import sys
import tempfile
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


URL = "https://splunkbase.splunk.com/app/%s/release/%s/download/"


class ParsePinnedTests(unittest.TestCase):
    def test_env_file_line(self):
        text = "SPLUNK_PASSWORD=x\nSPLUNK_APPS_URL=%s,%s\n" % (URL % (4353, "1.8.24"), URL % (7931, "2.1.0"))
        self.assertEqual(sb.parse_pinned(text), ([(4353, "1.8.24"), (7931, "2.1.0")], 0))

    def test_quotes_export_yaml_forms_and_missing_trailing_slash(self):
        forms = [
            'export SPLUNK_APPS_URL="%s"' % (URL % (1, "1.0")),
            "      - SPLUNK_APPS_URL=%s" % (URL % (1, "1.0")),
            "      SPLUNK_APPS_URL: '%s'" % (URL % (1, "1.0")),
            "SPLUNK_APPS_URL=%s" % (URL % (1, "1.0")).rstrip("/"),
            "SPLUNK_APPS_URL=%s  # pinned" % (URL % (1, "1.0")),
        ]
        for line in forms:
            with self.subTest(line=line):
                self.assertEqual(sb.parse_pinned(line), ([(1, "1.0")], 0))

    def test_comments_and_other_variables_are_ignored(self):
        text = "# SPLUNK_APPS_URL=%s\nMY_SPLUNK_APPS_URL=%s\n" % (URL % (1, "1.0"), URL % (2, "2.0"))
        self.assertEqual(sb.parse_pinned(text), ([], 0))

    def test_percent_encoded_versions_are_decoded_and_duplicates_dropped(self):
        url = URL % (1606, "3.2.0%20Windows%2064%20bit")
        text = "SPLUNK_APPS_URL=%s,%s\n" % (url, url)
        self.assertEqual(sb.parse_pinned(text), ([(1606, "3.2.0 Windows 64 bit")], 0))

    def test_other_entries_are_counted_not_parsed(self):
        text = "SPLUNK_APPS_URL=${SPLUNK_APPS_URL},https://example.com/app.tgz,%s\n" % (URL % (5, "1.0"))
        self.assertEqual(sb.parse_pinned(text), ([(5, "1.0")], 2))

    def test_other_hosts_with_the_same_path_are_not_splunkbase(self):
        text = "SPLUNK_APPS_URL=https://mirror.example/app/5/release/1.0/download/\n"
        self.assertEqual(sb.parse_pinned(text), ([], 1))

    def test_multi_line_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "multi-line"):
            sb.parse_pinned("SPLUNK_APPS_URL: >-\n  a,b\n")

    def test_image_from_compose(self):
        found = sb.image_from_compose("services:\n  s:\n    image: splunk/splunk:9.4.2\n")
        self.assertEqual(found, "splunk/splunk:9.4.2")
        found = sb.image_from_compose("  - image: 'docker.io/splunk/splunk:10.2'")
        self.assertEqual(found, "docker.io/splunk/splunk:10.2")
        self.assertIsNone(sb.image_from_compose("image: nginx:1.27\n# image: splunk/splunk:9.4\n"))
        self.assertIsNone(sb.image_from_compose("image: splunk/universalforwarder:9.4\n"))


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

    # --- --check -----------------------------------------------------------

    def check(self, content, *args, name=".env"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(content)
            return self.run_cli("--check", str(path), *args)

    def pins(self, *pairs):
        return "SPLUNK_APPS_URL=" + ",".join(URL % pair for pair in pairs) + "\n"

    def test_check_reports_current_and_outdated_and_exits_3(self):
        rc, out, _ = self.check(self.pins((4353, "1.8.24"), (7931, "2.1.0")))
        self.assertEqual(rc, 3)
        header, first, second = out.splitlines()
        self.assertEqual(header.split(), ["ID", "TITLE", "PINNED", "LATEST", "STATUS"])
        self.assertEqual((first.split()[-3:]), ["1.8.24", "1.8.26", "outdated"])
        self.assertEqual((second.split()[-3:]), ["2.1.0", "2.1.0", "current"])

    def test_check_exits_0_when_everything_is_current(self):
        rc, out, err = self.check(self.pins((4353, "1.8.26"), (7931, "2.1.0")))
        self.assertEqual(rc, 0, err)
        self.assertNotIn("outdated", out)

    def test_check_json(self):
        rc, out, _ = self.check(self.pins((4353, "1.8.24")), "--format", "json")
        self.assertEqual(rc, 3)
        (item,) = json.loads(out)
        self.assertEqual(
            set(item), {"app_id", "title", "pinned", "latest", "status", "url", "compatibility", "warnings"}
        )
        self.assertEqual((item["pinned"], item["latest"], item["status"]), ("1.8.24", "1.8.26", "outdated"))
        self.assertEqual(item["url"], "%s/app/4353/release/1.8.26/download/" % self.server.url)

    def test_check_reads_the_splunk_version_from_the_compose_image(self):
        compose = "services:\n  splunk:\n    image: splunk/splunk:10.6.1\n    environment:\n      SPLUNK_APPS_URL: %s\n"
        # 1.8.26 only supports Splunk up to 10.4, so on 10.6 it is not eligible.
        rc, out, err = self.check(compose % (URL % (4353, "1.8.26")), "--format", "json", name="docker-compose.yml")
        self.assertEqual(rc, 3, err)
        (item,) = json.loads(out)
        self.assertEqual((item["latest"], item["status"]), ("1.8.24", "unsupported"))
        self.assertIn("note: using Splunk 10.6 from image splunk/splunk:10.6.1 in", err)
        self.assertIn("newer than the newest eligible release (1.8.24)", err)

    def test_explicit_splunk_version_beats_the_file_image(self):
        compose = "    image: splunk/splunk:10.6.1\n    SPLUNK_APPS_URL: %s\n" % (URL % (4353, "1.8.26"))
        rc, out, err = self.check(compose, "--splunk-version", "10.4", name="docker-compose.yml")
        self.assertEqual(rc, 0, err)
        self.assertNotIn("from image", err)

    def test_check_without_any_version_says_compatibility_is_not_checked(self):
        rc, _, err = self.check(self.pins((7931, "2.1.0")))
        self.assertEqual(rc, 0)
        self.assertIn("note: no Splunk version known", err)

    def test_pin_that_is_older_and_unsupported_by_the_splunk_version_is_warned(self):
        rc, _, err = self.check(self.pins((4353, "1.8.1")), "--splunk-version", "10.4")
        self.assertEqual(rc, 3)
        self.assertRegex(err, r"(?m)^warning: .*(not in Splunkbase's release list|does not list Splunk 10.4)")

    def test_unknown_pinned_version(self):
        rc, out, err = self.check(self.pins((4353, "0.0.1")))
        self.assertEqual(rc, 3)
        self.assertIn("unknown", out)
        self.assertIn("not in Splunkbase's release list", err)

    def test_percent_encoded_release_names_match(self):
        rc, out, _ = self.check("SPLUNK_APPS_URL=%s\n" % (URL % (1606, "3.2.0%20Windows%2064%20bit")))
        self.assertEqual(rc, 0)
        self.assertIn("current", out)

    def test_cloud_filter_applies_to_the_check(self):
        rc, out, err = self.check(self.pins((4353, "1.8.26")), "--cloud")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("no release is marked Splunk Cloud compatible", err)

    def test_failure_prints_no_table_unless_partial(self):
        content = self.pins((7931, "2.1.0"), (3212, "1.0.0"))
        rc, out, err = self.check(content)
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("app 3212: app not found", err)
        rc, out, _ = self.check(content, "--partial")
        self.assertEqual(rc, 1)
        self.assertIn("7931", out)

    def test_ignored_entries_are_noted(self):
        content = "SPLUNK_APPS_URL=https://example.com/a.tgz,%s\n" % (URL % (7931, "2.1.0"))
        rc, _, err = self.check(content)
        self.assertEqual(rc, 0)
        self.assertIn("note: ignored 1 SPLUNK_APPS_URL entry", err)

    def test_file_without_pins_is_a_usage_error_with_a_hint(self):
        rc, out, err = self.check("services:\n  s:\n    environment:\n      SPLUNK_APPS_URL: ${SPLUNK_APPS_URL}\n")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("check the .env file", err)

    def test_unreadable_file_and_bad_combinations_are_usage_errors(self):
        self.assertEqual(self.run_cli("--check", "/no/such/file")[0], 2)
        self.assertEqual(self.check(self.pins((7931, "2.1.0")), "7931")[0], 2)
        self.assertEqual(self.check(self.pins((7931, "2.1.0")), "--format", "env")[0], 2)
        self.assertEqual(self.check(self.pins((7931, "2.1.0")), "--image", "x:9.4", "--splunk-version", "9.4")[0], 2)

    def test_check_resolves_each_app_once(self):
        self.check(self.pins((4353, "1.8.24"), (4353, "1.8.25")))
        self.assertEqual(self.server.request_count("/api/v1/app/4353/release"), 1)

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
