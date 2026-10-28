# Splunkbase API notes

Verified against the live service on 2026-10-28. This is the **unofficial** JSON
API behind splunkbase.splunk.com; Splunk does not document or version-guarantee
it. `.github/workflows/api-check.yml` runs `tests/test_live.py` weekly to catch drift.

Base URL: `https://splunkbase.splunk.com`

## Endpoints used

| Purpose | Request | Notes |
|---------|---------|-------|
| App metadata | `GET /api/v1/app/{id}` | `title`, `appid` (the slug, e.g. `Splunk_TA_aws`), `uid`, `is_archived`, `type`, `path` |
| Releases | `GET /api/v1/app/{id}/release` | JSON array, **newest first** as served. The script keeps API order. |
| Search | `GET /api/v1/app/?query=text&limit=n` | `{"offset","limit","total","results":[...]}`; each result has the app metadata fields above |
| Download | `GET /app/{id}/release/{version}/download/` | Needs a Splunkbase login. Keep the trailing slash; without it the server answers 301. |

An unknown app ID returns HTTP 404 with a JSON body (`{"status": 404, ...}`).

## Release object

Fields the script reads:

- `name`: version string, used in the download URL (percent-encoded).
- `published_datetime`
- `product_versions`: Splunk versions supported, `major.minor` strings such as `"9.4"`, `"10.2"`.

Other fields present: `id`, `app`, `filename`, `platform`, `product`, `size`,
`created_datetime`, `CIM_versions`, `cloud_compatible`, `fips_compatibility`,
`fedramp_validation`, `install_method_single`, `install_method_distributed`.

## Edge cases seen in real data

| Case | Example | Handling |
|------|---------|----------|
| Release `name` is the string `"null"` (or null/empty) | app 2941 | Skipped; not downloadable. If no release is usable the app fails with "no downloadable release". |
| Name contains spaces or extra text (`3.2.0 Windows 64 bit`) | app 1606 | URL is percent-encoded; warning says it may be a platform-specific build. |
| `product_versions` empty | various old apps | Compatibility is `unknown`; accepted with a warning when `--splunk-version` is given. |
| Newest release does not support the requested Splunk | app 4353 vs Splunk 10.6 | Walk down to the newest release that does; error with the supported range if none. |
| Archived app | `is_archived: true` | Resolved but flagged. |
| Duplicate IDs in one call | `7931 7931` | Resolved once, warning printed. |
| Transient 429/5xx or network failure | | Retried with exponential backoff (`--retries`, default 2). |

## Why the script does not validate the download URL

An unauthenticated request to any `/download/` URL returns 401, including for
versions that do not exist (`.../release/9.9.9/download/` is 401 too). A 401 is
therefore not evidence that a URL is valid, and the script does not rely on it.
Validity comes from the release list.

## Search v2

`/api/v2/apps` also exists with a different response shape (cursor paging, nested
objects). The script uses the v1 search because it returns the same objects as
the app endpoint. If v1 search is removed, v2 is the likely replacement.
