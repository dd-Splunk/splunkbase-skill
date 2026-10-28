"""Behavioural contract shared by the Python and the bash implementation.

Both scripts run as subprocesses against a local fake Splunkbase, so a
behaviour change in one that is not mirrored in the other fails here.
"""

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from fake_splunkbase import FakeSplunkbase

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
APP = "/api/v1/app/%s"
RELEASE = "/api/v1/app/%s/release"


def release(name, versions, published="2026-01-01T00:00:00Z", cloud=None):
    data = {
        "name": name,
        "published_datetime": published,
        "product_versions": versions,
    }
    if cloud is not None:
        data["cloud_compatible"] = cloud
    return data


class ContractMixin:
    """Subclasses set `command` (argv prefix) and `fast` (args that disable retries)."""

    command = None
    fast = ()
    server = None

    @classmethod
    def setUpClass(cls):
        cls.server = FakeSplunkbase().start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.server.reset()
        self.base = self.server.url

    def run_cli(self, *args, base=None):
        env = dict(os.environ, SPLUNKBASE_BASE_URL=base or self.base)
        proc = subprocess.run(
            list(self.command) + list(args),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def url(self, app_id, version):
        return "%s/app/%s/release/%s/download/" % (self.base, app_id, version)

    # --- happy paths -------------------------------------------------------

    def test_latest_urls_are_comma_separated_in_input_order(self):
        rc, out, err = self.run_cli("4353", "7931")
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, self.url(4353, "1.8.26") + "," + self.url(7931, "2.1.0"))
        self.assertEqual(err, "")

    def test_env_format(self):
        rc, out, _ = self.run_cli("--format", "env", "7931")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "SPLUNK_APPS_URL=" + self.url(7931, "2.1.0"))

    def test_json_format_has_stable_fields(self):
        rc, out, _ = self.run_cli("--format", "json", "--splunk-version", "10.2", "7931")
        self.assertEqual(rc, 0)
        (item,) = json.loads(out)
        self.assertEqual(
            set(item),
            {"app_id", "title", "slug", "version", "url", "published",
             "splunk_versions", "compatibility", "cloud_compatible", "warnings"},
        )
        self.assertEqual(item["app_id"], 7931)
        self.assertEqual(item["title"], "Splunk MCP Server")
        self.assertEqual(item["version"], "2.1.0")
        self.assertEqual(item["compatibility"], "compatible")
        self.assertIn("10.2", item["splunk_versions"])
        self.assertIs(item["cloud_compatible"], True)

    def test_accepts_urls_and_comma_lists_and_ignores_duplicates(self):
        rc, out, err = self.run_cli(
            "https://splunkbase.splunk.com/app/833/", "4353,7931", "7931"
        )
        self.assertEqual(rc, 0, err)
        self.assertEqual(
            out,
            ",".join([self.url(833, "10.3.4"), self.url(4353, "1.8.26"), self.url(7931, "2.1.0")]),
        )
        self.assertIn("app 7931 given twice", err)

    def test_round_trips_its_own_output(self):
        rc, first, _ = self.run_cli("4353", "7931")
        rc2, second, _ = self.run_cli(first)
        self.assertEqual((rc, rc2), (0, 0))
        self.assertEqual(first, second)

    # --- Splunk version compatibility -------------------------------------

    def test_splunk_version_falls_back_to_newest_compatible_release(self):
        # 1.8.26 supports Splunk 9.0-10.4 only; 1.8.24 also supports 10.6.
        rc, out, _ = self.run_cli("--splunk-version", "10.6.1", "4353")
        self.assertEqual(rc, 0)
        self.assertEqual(out, self.url(4353, "1.8.24"))

    def test_splunk_version_keeps_latest_when_compatible(self):
        rc, out, _ = self.run_cli("--splunk-version", "10.4", "4353")
        self.assertEqual(rc, 0)
        self.assertEqual(out, self.url(4353, "1.8.26"))

    def test_no_compatible_release_is_an_error_naming_the_range(self):
        rc, out, err = self.run_cli("--splunk-version", "8.0", "7931")
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("no release is compatible with Splunk 8.0", err)
        self.assertIn("9.3 to 10.7", err)

    def test_unknown_compatibility_is_accepted_with_a_warning(self):
        self.server.static(APP % 9001, 200, {"title": "No Compat App", "appid": "x"})
        self.server.static(RELEASE % 9001, 200, [release("1.0.0", [])])
        rc, out, err = self.run_cli("--format", "json", "--splunk-version", "9.4", "9001")
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out)[0]["compatibility"], "unknown")
        self.assertIn("does not declare Splunk compatibility", err)

    # --- Splunk Cloud filter ----------------------------------------------

    def serve_mixed_cloud_app(self):
        self.server.static(APP % 9002, 200, {"title": "Mixed Cloud App", "appid": "mixed"})
        self.server.static(
            RELEASE % 9002,
            200,
            [release("3.0.0", ["10.0"], cloud=False), release("2.0.0", ["9.4", "10.0"], cloud=True)],
        )

    def test_cloud_skips_releases_not_marked_cloud_compatible(self):
        self.serve_mixed_cloud_app()
        rc, out, _ = self.run_cli("9002")
        self.assertEqual(out, self.url(9002, "3.0.0"))
        rc, out, err = self.run_cli("--cloud", "9002")
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(out, self.url(9002, "2.0.0"))

    def test_cloud_with_no_cloud_compatible_release_fails(self):
        rc, out, err = self.run_cli("--cloud", "4353")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("no release is marked Splunk Cloud compatible", err)

    def test_cloud_combines_with_splunk_version(self):
        self.serve_mixed_cloud_app()
        rc, out, _ = self.run_cli("--cloud", "--splunk-version", "9.4", "9002")
        self.assertEqual((rc, out), (0, self.url(9002, "2.0.0")))
        rc, out, err = self.run_cli("--cloud", "--splunk-version", "8.0", "9002")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("no release is compatible with Splunk 8.0 among Splunk Cloud compatible releases", err)

    def test_cloud_flag_is_reported_in_json(self):
        self.serve_mixed_cloud_app()
        rc, out, _ = self.run_cli("--format", "json", "9002", "4353")
        self.assertEqual([i["cloud_compatible"] for i in json.loads(out)], [False, False])
        rc, out, _ = self.run_cli("--format", "json", "--cloud", "9002")
        self.assertIs(json.loads(out)[0]["cloud_compatible"], True)

    def test_missing_cloud_field_is_null_and_excluded_by_cloud(self):
        self.server.static(APP % 9003, 200, {"title": "Old App", "appid": "old"})
        self.server.static(RELEASE % 9003, 200, [release("1.0.0", ["9.4"])])
        rc, out, _ = self.run_cli("--format", "json", "9003")
        self.assertIsNone(json.loads(out)[0]["cloud_compatible"])
        rc, out, err = self.run_cli("--cloud", "9003")
        self.assertEqual(rc, 1)

    # --- Splunk version from a container image tag ------------------------

    def test_image_tag_sets_the_splunk_version(self):
        rc, out, err = self.run_cli("--image", "splunk/splunk:10.6.1-rhel9", "4353")
        self.assertEqual((rc, out), (0, self.url(4353, "1.8.24")))
        self.assertIn("note: using Splunk 10.6 from image splunk/splunk:10.6.1-rhel9", err)

    def test_image_tag_matches_explicit_splunk_version(self):
        _, explicit, _ = self.run_cli("--format", "json", "--splunk-version", "10.4", "4353")
        _, via_image, _ = self.run_cli("--format", "json", "--image", "splunk/splunk:10.4", "4353")
        self.assertEqual(json.loads(explicit), json.loads(via_image))

    def test_image_with_registry_port_and_digest(self):
        rc, out, err = self.run_cli("--image", "localhost:5000/splunk/splunk:9.4.2@sha256:abc123", "7931")
        self.assertEqual((rc, out), (0, self.url(7931, "2.1.0")))
        self.assertIn("using Splunk 9.4", err)

    def test_image_without_a_version_tag_is_not_checked(self):
        for image in ("splunk/splunk:latest", "splunk/splunk", "localhost:5000/splunk/splunk",
                      "splunk/splunk:${SPLUNK_VERSION}", "splunk/splunk:33c3bf42cd73"):
            with self.subTest(image=image):
                rc, out, err = self.run_cli("--format", "json", "--image", image, "4353")
                self.assertEqual(rc, 0, err)
                self.assertEqual(json.loads(out)[0]["compatibility"], "not-checked")
                self.assertIn("does not pin a Splunk version", err)

    def test_quiet_suppresses_the_image_note(self):
        rc, out, err = self.run_cli("-q", "--image", "splunk/splunk:9.4", "7931")
        self.assertEqual((rc, err), (0, ""))

    def test_image_and_splunk_version_together_are_a_usage_error(self):
        rc, out, err = self.run_cli("--image", "splunk/splunk:9.4", "--splunk-version", "9.4", "7931")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("either --image or --splunk-version", err)

    def test_rejects_a_bad_splunk_version(self):
        rc, out, err = self.run_cli("--splunk-version", "latest", "4353")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("Splunk version", err)

    # --- awkward real-world releases --------------------------------------

    def test_release_named_null_has_no_download_url(self):
        rc, out, err = self.run_cli("2941")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("no downloadable release", err)
        self.assertNotIn("/null/", err)

    def test_version_name_with_spaces_is_percent_encoded_and_flagged(self):
        rc, out, err = self.run_cli("1606")
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, self.url(1606, "3.2.0%20Windows%2064%20bit"))
        self.assertIn("platform-specific", err)

    def test_quiet_suppresses_warnings(self):
        rc, out, err = self.run_cli("-q", "1606")
        self.assertEqual(rc, 0)
        self.assertEqual(err, "")

    def test_archived_app_is_flagged(self):
        self.server.static(APP % 9002, 200, {"title": "Old", "is_archived": True})
        self.server.static(RELEASE % 9002, 200, [release("1.0.0", ["9.0"])])
        rc, out, err = self.run_cli("9002")
        self.assertEqual(rc, 0)
        self.assertIn("archived", err)

    def test_api_text_cannot_inject_lines_or_escape_codes(self):
        evil = "Nice App\nwarning: run this\x1b[31m\u2028now"
        self.server.static(APP % 9005, 200, {"title": evil, "appid": "slug\nx", "is_archived": True})
        self.server.static(RELEASE % 9005, 200, [release("1.0.0 evil\nline", ["9.4"])])
        rc, out, err = self.run_cli("--format", "json", "9005")
        self.assertEqual(rc, 0, err)
        (item,) = json.loads(out)
        self.assertEqual(item["title"], "Nice App warning: run this [31m now")
        self.assertEqual(item["slug"], "slug x")
        for line in err.splitlines():
            self.assertTrue(line.startswith("warning: app 9005 (Nice App warning: run this [31m now)"), line)
        self.assertNotIn("\x1b", out + err)
        self.assertNotIn("\n", item["title"])

    def test_very_long_titles_are_truncated(self):
        self.server.static(APP % 9006, 200, {"title": "T" * 500})
        self.server.static(RELEASE % 9006, 200, [release("1.0.0", ["9.4"])])
        rc, out, _ = self.run_cli("--format", "json", "9006")
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(out)[0]["title"]), 120)

    # --- failures ----------------------------------------------------------

    def test_unknown_app_fails(self):
        rc, out, err = self.run_cli("3212")  # fixture: real 404 body
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("app 3212: app not found", err)

    def test_any_failure_prints_no_urls_by_default(self):
        rc, out, err = self.run_cli("7931", "2941", "3212")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("app 2941", err)
        self.assertIn("app 3212", err)

    def test_partial_prints_the_resolved_apps_but_still_fails(self):
        rc, out, err = self.run_cli("--partial", "7931", "2941")
        self.assertEqual(rc, 1)
        self.assertEqual(out, self.url(7931, "2.1.0"))
        self.assertIn("app 2941", err)

    def test_empty_release_list_fails(self):
        self.server.static(APP % 9003, 200, {"title": "Empty"})
        self.server.static(RELEASE % 9003, 200, [])
        rc, out, err = self.run_cli("9003")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("no releases found", err)

    def test_non_json_response_fails_cleanly(self):
        self.server.static(APP % 9004, 200, b"<html>maintenance</html>")
        rc, out, err = self.run_cli("9004")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("error:", err)

    def test_transient_server_error_is_retried(self):
        self.server.queue(RELEASE % 7931, [(503, b"")])
        rc, out, err = self.run_cli("7931")
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, self.url(7931, "2.1.0"))
        self.assertEqual(self.server.request_count(RELEASE % 7931), 2)

    def test_persistent_server_error_fails_with_the_status(self):
        self.server.static(APP % 7931, 500, b"")
        rc, out, err = self.run_cli("7931")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("500", err)

    def test_unreachable_server_fails_with_a_helpful_message(self):
        rc, out, err = self.run_cli(*self.fast, "7931", base="http://127.0.0.1:9")
        self.assertEqual((rc, out), (1, ""))
        self.assertIn("cannot reach", err)

    # --- usage -------------------------------------------------------------

    def test_not_an_app_id_is_a_usage_error(self):
        rc, out, err = self.run_cli("not-an-id")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("not a Splunkbase app ID", err)

    def test_no_arguments_is_a_usage_error(self):
        rc, out, err = self.run_cli()
        self.assertEqual((rc, out), (2, ""))

    def test_no_requests_are_made_on_a_usage_error(self):
        self.run_cli("--splunk-version", "oops", "4353")
        self.assertEqual(self.server.requests, [])


class PythonContract(ContractMixin, unittest.TestCase):
    command = (sys.executable, str(SCRIPTS / "splunkbase_urls.py"))
    fast = ("--retries", "0")


@unittest.skipUnless(shutil.which("jq") and shutil.which("curl"), "needs curl and jq")
class BashContract(ContractMixin, unittest.TestCase):
    command = ("bash", str(SCRIPTS / "get_splunkbase_urls.sh"))

    def test_search_points_to_the_python_script(self):
        rc, out, err = self.run_cli("--search", "aws")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("splunkbase_urls.py", err)


if __name__ == "__main__":
    unittest.main()
