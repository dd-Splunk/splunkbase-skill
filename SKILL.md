---
name: splunkbase-skill
description: Resolves Splunkbase apps to their current download URLs, optionally for a specific Splunk version, and finds app IDs by name. Use when the user wants the latest release URL of a Splunkbase app or add-on, needs SPLUNK_APPS_URL for splunk/splunk Docker Compose or Kubernetes deployments, asks which Splunkbase release supports their Splunk version, or gives a splunkbase.splunk.com link or app ID.
metadata:
  version: 2.0.0
---

# Splunkbase release URLs

Never write a Splunkbase release URL from memory. Versions change constantly and
some releases have odd names; always run the bundled script and use its output.

## Workflow

1. **Identify the apps.** Accept numeric app IDs (`4353`), app page URLs
   (`https://splunkbase.splunk.com/app/4353/`), or comma/space-separated lists.
   If the user only gave a name, find the ID first:

   ```bash
   python3 scripts/splunkbase_urls.py --search "config explorer"
   ```

   Show the matches and confirm the ID if the result is ambiguous.

2. **Resolve the URLs.**

   ```bash
   python3 scripts/splunkbase_urls.py 4353 7931                       # comma-separated URLs
   python3 scripts/splunkbase_urls.py --format env 4353 7931          # SPLUNK_APPS_URL=...
   python3 scripts/splunkbase_urls.py --format json --splunk-version 9.4 4353
   ```

   - Pass `--splunk-version` whenever the user's Splunk version is known (from
     the image tag, the conversation, or the compose file). The script then
     picks the newest release that supports it instead of blindly taking the latest.
   - No Python? `scripts/get_splunkbase_urls.sh` needs only `curl` and `jq`
     and gives the same results, except that it has no `--search`.

3. **Report.** Give the user the URLs (or the finished compose snippet) and
   relay every warning the script printed on stderr. Mention the resolved
   version numbers so they can pin or review them.

## Output and exit codes

| Exit | Meaning | What to do |
|------|---------|------------|
| 0 | All apps resolved | Use stdout. Read stderr for warnings. |
| 1 | At least one app failed; stdout is empty | Report the per-app errors from stderr. Do not guess URLs. `--partial` prints the apps that did resolve. |
| 2 | Bad arguments | Fix the invocation. |

If the network is blocked (`cannot reach ...`), say so and ask the user to run
the command themselves. Do not fall back to remembered versions.

## Things to tell the user

- **Resolving needs no login; downloading does.** The URLs only work for a
  Splunkbase account (`SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD` for the
  `splunk/splunk` image). Never ask the user to paste credentials into the
  chat; reference environment variables or a `.env` file.
- **Compatibility.** `compatibility` is `compatible`, `unknown` (the release
  declares no Splunk versions) or `not-checked` (no `--splunk-version`). Treat
  `unknown` as a prompt to verify, not as a pass.
- **Platform-specific builds.** A warning that the release name has extra text
  (for example a "Windows 64 bit" build) means the app ships OS-specific
  packages; confirm it is the build the user needs.
- **Archived apps** are flagged; suggest looking for a successor.
- **Pinning.** `latest` moves. For reproducible deployments, suggest pinning the
  resolved version and re-running the script on upgrades.

## Docker Compose

For a full `splunk/splunk` service example, credentials handling and
troubleshooting, read [references/docker-compose.md](references/docker-compose.md).
Insert the script's URLs into `SPLUNK_APPS_URL` (comma-separated, no spaces).

## API details

The script uses Splunkbase's unofficial JSON API. Endpoints, fields, and the
edge cases the script handles (releases named `null`, empty compatibility
lists, redirects, why an unauthenticated 401 proves nothing) are in
[references/api.md](references/api.md). Read it only when debugging the
script or when the user asks how the lookup works.
