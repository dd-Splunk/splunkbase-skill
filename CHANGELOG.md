# Changelog

Versions follow [Semantic Versioning](https://semver.org). The newest entry must
match `metadata.version` in `SKILL.md` and `__version__`/`VERSION` in both
scripts (checked by `tests/test_skill_package.py`).

## [2.2.0] - 2026-10-28

### Added

- `--image REF` takes the Splunk version from a container image tag (`splunk/splunk:9.4.2`, `10.6.1-rhel9`, registry ports and digests handled). `latest`, untagged images and unexpanded variables produce a warning and skip the compatibility check; combining it with `--splunk-version` is a usage error.
- `--cloud` restricts the choice to releases marked Splunk Cloud compatible, and the JSON output gains a `cloud_compatible` field (`true`, `false` or `null`). Both scripts, with contract tests for each.
- Live API check that `cloud_compatible` is still a boolean on releases.

### Fixed

- The skill description claimed Kubernetes support. It only produces `SPLUNK_APPS_URL` values for the `splunk/splunk` image under Docker or Docker Compose; the Splunk Operator installs apps from object storage. The description, routing rules and Docker reference now say so.
- Docker reference verified against docker-splunk, Docker Hub and the Splunk Operator docs: `SPLUNK_GENERAL_TERMS` is required only from 10.x images, `linux/amd64` is the only published architecture, and an unverified claim about `@splunk.com` logins is removed.

## [2.1.1] - 2026-10-28

### Changed

- Made the project status explicit: personal project, not for production use, not endorsed or supported by Cisco or Splunk. Stated in the README banner, `SUPPORT.md` and a new Status section in `SKILL.md`, with a test that keeps all three in place.

## [2.1.0] - 2026-10-28

Aligned with the conventions of the official [splunk-agent-skills](https://github.com/splunk/splunk-agent-skills).

### Added

- `SKILL.md`: `metadata.splunk` block (domain, products, entities, triggers, not-for, outcomes) plus Prerequisites, When to Use / routing, Boundaries, Examples and Troubleshooting sections.
- `agents/openai.yaml` interface file for non-Claude agents.
- `evals.json`: trigger (positive/negative) and behaviour evals in the official format.
- `references/sources.md`, `SECURITY.md`, `SUPPORT.md`.
- Install with `npx skills add dd-Splunk/splunkbase-skill`.
- Apache-2.0 `LICENSE` (shipped in the `.skill` archive) and `license: Apache-2.0` in the `SKILL.md` frontmatter.

### Security

- API-supplied text (titles, slugs, release names in warnings) is stripped of control characters and truncated to 120 characters in both scripts, so a hostile listing cannot inject lines or terminal escape codes into output.

## [2.0.0] - 2026-10-28

### Breaking

- Scripts moved to `scripts/` (`scripts/splunkbase_urls.py`, `scripts/get_splunkbase_urls.sh`). The Python module is now a CLI with a small importable API; the old root-level functions are gone.
- Releases are now cut from `v*` tags. The per-push timestamp releases and the force-moved `latest` tag are no longer produced; install from `releases/latest/download/splunkbase-skill.skill`.

### Added

- `--splunk-version` selects the newest release compatible with a Splunk version.
- `--search` finds app IDs by name; `--format urls|env|json|table`; `--partial`; `--quiet`.
- App page URLs and comma/space-separated lists accepted as input; concurrent lookups with stable output order.
- Retries with backoff on 429/5xx/network errors; per-request timeout.
- Warnings for archived apps, unknown compatibility and platform-specific release names.
- Offline test suite (fake Splunkbase with real fixtures, one contract suite for both implementations), package checks, and a weekly live API check.
- `references/api.md` and `references/docker-compose.md`.

### Fixed

- Releases named `null` no longer produce `/release/null/download/` URLs.
- Release names with spaces are percent-encoded.
- Any failure now exits non-zero with no partial URL list on stdout (unless `--partial`).
- `SKILL.md` no longer hard-codes app versions, and its API description matches the real responses.
- Docker example no longer hard-codes an `@splunk.com` username.

## 1.0.0

Initial version (unversioned history before 2.0.0).
