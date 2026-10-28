#!/usr/bin/env python3
"""Resolve Splunkbase apps to their latest download URLs.

Given Splunkbase app IDs (or app page URLs), print the download URL of each
app's latest release, optionally restricted to releases that support a given
Splunk version. Output is shaped for Docker's ``SPLUNK_APPS_URL`` variable.

Standard library only (Python 3.9+). Talks to Splunkbase's public JSON API;
see references/api.md for the endpoints and the edge cases handled here.

Exit status: 0 = every app resolved, 1 = at least one app failed
(by default nothing is printed to stdout in that case, so a half-resolved
SPLUNK_APPS_URL can never be used by mistake), 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

__version__ = "2.0.0"

DEFAULT_BASE_URL = "https://splunkbase.splunk.com"
USER_AGENT = f"splunkbase-skill/{__version__}"
RETRY_STATUSES = (429, 500, 502, 503, 504)
MAX_WORKERS = 8


class SplunkbaseError(Exception):
    """A problem resolving an app or talking to Splunkbase."""


class NotFoundError(SplunkbaseError):
    """Splunkbase answered 404."""


class Client:
    """Minimal JSON-over-HTTP client with timeouts and retry/backoff."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        retries: int = 2,
        backoff: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def get_json(self, path: str, params: Optional[dict] = None) -> Any:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(self.backoff * 2 ** (attempt - 1))
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise NotFoundError(f"not found ({url})") from exc
                last_error = exc
                if exc.code not in RETRY_STATUSES:
                    break
            except (urllib.error.URLError, socket.timeout, ConnectionError) as exc:
                last_error = exc
            except json.JSONDecodeError as exc:
                raise SplunkbaseError(f"invalid JSON from {url}") from exc
        if isinstance(last_error, urllib.error.HTTPError):
            raise SplunkbaseError(f"HTTP {last_error.code} from {url}")
        raise SplunkbaseError(
            f"cannot reach {self.base_url} ({last_error}); "
            "check the network connection and any proxy or sandbox restrictions"
        )


@dataclass
class Resolved:
    """The release chosen for one app."""

    app_id: int
    title: str
    slug: Optional[str]
    version: str
    url: str
    published: Optional[str]
    splunk_versions: list = field(default_factory=list)
    compatibility: str = "not-checked"  # not-checked | compatible | unknown
    warnings: list = field(default_factory=list)


def parse_app_id(value: str) -> int:
    """Accept '4353' or a Splunkbase app page / download URL."""
    text = value.strip()
    if re.fullmatch(r"\d+", text):
        return int(text)
    match = re.search(r"/app/(\d+)(?:[/?#]|$)", text)
    if match:
        return int(match.group(1))
    raise ValueError(f"not a Splunkbase app ID or app URL: {value!r}")


def split_app_args(values: list) -> list:
    """Flatten args so '4353,7931', '4353 7931' and pasted URL lists all work."""
    parts = []
    for value in values:
        parts.extend(p for p in re.split(r"[,\s]+", value) if p)
    return parts


def normalize_splunk_version(value: str) -> str:
    """'10.2.1' -> '10.2' (Splunkbase tracks compatibility as major.minor)."""
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\w+)*", value.strip())
    if not match:
        raise ValueError(f"not a Splunk version like 9.4 or 10.2.1: {value!r}")
    return f"{match.group(1)}.{match.group(2)}"


def is_downloadable(release: dict) -> bool:
    """Some apps list a release whose name is the literal string 'null'."""
    name = release.get("name")
    return isinstance(name, str) and name.strip().lower() not in ("", "null", "none")


def _supported_range(release: dict) -> str:
    versions = release.get("product_versions") or []
    return f"{versions[-1]} to {versions[0]}" if versions else "unknown"


def select_release(
    releases: list, splunk_version: Optional[str] = None
) -> tuple[dict, str, list]:
    """Pick a release. Returns (release, compatibility, warnings).

    Splunkbase lists releases newest first. Without a Splunk version the first
    downloadable release wins. With one, the newest release that is not known
    to be incompatible wins: explicitly compatible, or compatibility unknown
    (empty ``product_versions``, flagged with a warning).
    """
    usable = [r for r in releases if isinstance(r, dict) and is_downloadable(r)]
    if not usable:
        raise SplunkbaseError(
            "no downloadable release (the release has no version name, "
            "so no download URL can be built)"
        )
    if splunk_version is None:
        return usable[0], "not-checked", []
    for release in usable:
        supported = release.get("product_versions") or []
        if splunk_version in supported:
            return release, "compatible", []
        if not supported:
            return (
                release,
                "unknown",
                [
                    f"release {release['name']} does not declare Splunk "
                    f"compatibility; cannot confirm it supports {splunk_version}"
                ],
            )
    raise SplunkbaseError(
        f"no release is compatible with Splunk {splunk_version} "
        f"(latest is {usable[0]['name']}, which supports "
        f"{_supported_range(usable[0])})"
    )


def resolve_app(
    client: Client, app_id: int, splunk_version: Optional[str] = None
) -> Resolved:
    try:
        app = client.get_json(f"/api/v1/app/{app_id}")
    except NotFoundError:
        raise SplunkbaseError(f"app {app_id}: app not found on Splunkbase") from None
    except SplunkbaseError as exc:
        raise SplunkbaseError(f"app {app_id}: {exc}") from None
    if not isinstance(app, dict):
        raise SplunkbaseError(f"app {app_id}: unexpected app response")
    title = app.get("title") or "Unknown"
    label = f"app {app_id} ({title})"

    try:
        releases = client.get_json(f"/api/v1/app/{app_id}/release")
    except NotFoundError:
        raise SplunkbaseError(f"{label}: no releases found") from None
    except SplunkbaseError as exc:
        raise SplunkbaseError(f"{label}: {exc}") from None
    if not isinstance(releases, list) or not releases:
        raise SplunkbaseError(f"{label}: no releases found")

    try:
        release, compatibility, warnings = select_release(releases, splunk_version)
    except SplunkbaseError as exc:
        raise SplunkbaseError(f"{label}: {exc}") from None

    version = release["name"].strip()
    if app.get("is_archived"):
        warnings.append("app is archived on Splunkbase")
    if not re.fullmatch(r"[0-9][A-Za-z0-9_.+-]*", version):
        warnings.append(
            f'release name "{version}" has extra text; it may be a platform-specific '
            "build, check it is the one you need"
        )
    url = (
        f"{client.base_url}/app/{app_id}/release/"
        f"{urllib.parse.quote(version, safe='')}/download/"
    )
    return Resolved(
        app_id=app_id,
        title=title,
        slug=app.get("appid"),
        version=version,
        url=url,
        published=release.get("published_datetime"),
        splunk_versions=list(release.get("product_versions") or []),
        compatibility=compatibility,
        warnings=warnings,
    )


def resolve_many(
    client: Client, app_ids: list, splunk_version: Optional[str] = None
) -> list:
    """Resolve concurrently; returns [(app_id, Resolved | None, error | None)]."""

    def one(app_id: int) -> tuple:
        try:
            return app_id, resolve_app(client, app_id, splunk_version), None
        except SplunkbaseError as exc:
            return app_id, None, str(exc)

    with ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(app_ids)))) as pool:
        return list(pool.map(one, app_ids))


def search_apps(client: Client, query: str, limit: int = 10) -> list:
    data = client.get_json("/api/v1/app/", {"query": query, "limit": limit})
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        raise SplunkbaseError("unexpected search response")
    return [
        {
            "app_id": r.get("uid"),
            "title": r.get("title"),
            "slug": r.get("appid"),
            "type": r.get("type"),
            "archived": bool(r.get("is_archived")),
        }
        for r in results
    ]


def _table(headers: list, rows: list) -> str:
    rows = [[str(c) for c in row] for row in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip()]
    lines += ["  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows]
    return "\n".join(lines)


def render(resolved: list, fmt: str) -> str:
    joined = ",".join(r.url for r in resolved)
    if fmt == "urls":
        return joined
    if fmt == "env":
        return f"SPLUNK_APPS_URL={joined}"
    if fmt == "json":
        return json.dumps([asdict(r) for r in resolved], indent=2)
    rows = [
        [r.app_id, r.title, r.version, r.compatibility, r.url] for r in resolved
    ]
    return _table(["ID", "TITLE", "VERSION", "COMPAT", "URL"], rows)


def render_search(results: list, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(results, indent=2)
    rows = [
        [r["app_id"], r["type"] or "", r["title"] or "", r["slug"] or ""]
        for r in results
    ]
    return _table(["ID", "TYPE", "TITLE", "SLUG"], rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="splunkbase_urls.py",
        description="Print the latest Splunkbase download URL for each app.",
        epilog="Downloading a URL needs Splunkbase credentials; resolving it does not.",
    )
    parser.add_argument(
        "apps",
        nargs="*",
        metavar="APP",
        help="Splunkbase app ID or app page URL (commas allowed: 4353,7931)",
    )
    parser.add_argument(
        "--search",
        metavar="QUERY",
        help="search Splunkbase by name instead of resolving app IDs",
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="max search results (default: 10)"
    )
    parser.add_argument(
        "--splunk-version",
        metavar="VER",
        help="only pick releases that support this Splunk version (e.g. 9.4, 10.2.1)",
    )
    parser.add_argument(
        "--format",
        choices=("urls", "env", "json", "table"),
        help="urls: comma-separated (default); env: SPLUNK_APPS_URL=...; "
        "json; table (default for --search)",
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help="still print URLs for the apps that resolved when others fail "
        "(exit status stays 1)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SPLUNKBASE_BASE_URL", DEFAULT_BASE_URL),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="per-request timeout, seconds"
    )
    parser.add_argument(
        "--retries", type=int, default=2, help="retries on 429/5xx/network errors"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress warnings on stderr"
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = Client(args.base_url, timeout=args.timeout, retries=args.retries)

    if args.search:
        if args.apps:
            parser.error("--search cannot be combined with app IDs")
        try:
            results = search_apps(client, args.search, args.limit)
        except SplunkbaseError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if not results:
            print(f"error: no apps found for {args.search!r}", file=sys.stderr)
            return 1
        print(render_search(results, "json" if args.format == "json" else "table"))
        return 0

    if not args.apps:
        parser.error("give at least one app ID or use --search")
    splunk_version = None
    if args.splunk_version:
        try:
            splunk_version = normalize_splunk_version(args.splunk_version)
        except ValueError as exc:
            parser.error(str(exc))

    app_ids: list = []
    for token in split_app_args(args.apps):
        try:
            app_id = parse_app_id(token)
        except ValueError as exc:
            parser.error(str(exc))
        if app_id in app_ids:
            if not args.quiet:
                print(f"warning: app {app_id} given twice, using it once", file=sys.stderr)
            continue
        app_ids.append(app_id)

    outcomes = resolve_many(client, app_ids, splunk_version)
    failed = [(app_id, error) for app_id, resolved, error in outcomes if error]
    resolved = [r for _, r, _ in outcomes if r]

    for error in (e for _, e in failed):
        print(f"error: {error}", file=sys.stderr)
    if not args.quiet:
        for item in resolved:
            for warning in item.warnings:
                print(f"warning: app {item.app_id} ({item.title}): {warning}", file=sys.stderr)

    if resolved and (not failed or args.partial):
        print(render(resolved, args.format or "urls"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
