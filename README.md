# splunkbase-skill

> [!WARNING]
> **Personal project, not for production use.** This is not a Splunk or Cisco
> product and is **not endorsed or supported by Cisco or Splunk**. It uses
> Splunkbase's undocumented API and is provided "as is" under the
> [Apache-2.0](LICENSE) license, without warranty. See [SUPPORT.md](SUPPORT.md).

A Claude Skill that resolves Splunkbase apps to their current download URLs (optionally for a given Splunk version) and finds app IDs by name. Built for generating `SPLUNK_APPS_URL` in `splunk/splunk` Docker Compose setups.

## Install

Download [`splunkbase-skill.skill`](https://github.com/dd-Splunk/splunkbase-skill/releases/latest/download/splunkbase-skill.skill) from the latest release and add it to Claude (see [Using Skills in Claude](https://support.claude.com/en/articles/12512180-using-skills-in-claude)). For Claude Code, unzip it into `~/.claude/skills/`.

Or with the [`skills` CLI](https://github.com/vercel-labs/skills), the same installer the official [Splunk Agent Skills](https://github.com/splunk/splunk-agent-skills) use:

```bash
npx skills add dd-Splunk/splunkbase-skill --agent claude-code --copy --yes
```

`agents/openai.yaml` provides the interface metadata for other agents. This skill complements the official lifecycle and product-question skills: they give advice and citations, this one resolves exact release URLs from the live API. It is an unofficial personal project, see [SUPPORT.md](SUPPORT.md); licensed under [Apache-2.0](LICENSE).

Then ask, for example: *"Give me SPLUNK_APPS_URL for Splunkbase apps 4353 and 7931 for Splunk 9.4"* or *"Find the Splunkbase app for Config Explorer"*.

## Command line

The scripts work without Claude. Python 3.9+ (standard library only):

```bash
python3 scripts/splunkbase_urls.py 4353 7931                    # comma-separated URLs
python3 scripts/splunkbase_urls.py --format env 4353 7931       # SPLUNK_APPS_URL=...
python3 scripts/splunkbase_urls.py --splunk-version 9.4 4353    # newest release supporting Splunk 9.4
python3 scripts/splunkbase_urls.py --image splunk/splunk:9.4.2 4353  # same, version read from the image tag
python3 scripts/splunkbase_urls.py --cloud 4353                 # only Splunk Cloud compatible releases
python3 scripts/splunkbase_urls.py --check .env                 # which pinned URLs are outdated (exit 3 if any)
python3 scripts/splunkbase_urls.py --format json 4353           # app, version, compatibility, warnings
python3 scripts/splunkbase_urls.py --search "config explorer"   # find IDs by name
```

`scripts/get_splunkbase_urls.sh` (needs `curl` and `jq`, works with macOS bash 3.2) provides the same options except `--search`, `--check` and the `table` format.

Exit status: `0` all resolved, `1` at least one app failed (nothing on stdout unless `--partial`), `2` bad arguments. Warnings go to stderr.

Resolving URLs needs no login; downloading them does. See [references/docker-compose.md](references/docker-compose.md) for the credential setup.

## Development

```bash
python3 -m unittest discover -s tests          # offline: fake Splunkbase + real fixtures, ~15 s
SPLUNKBASE_LIVE=1 python3 -m unittest tests.test_live   # hits the real API
shellcheck scripts/get_splunkbase_urls.sh
```

- `tests/test_cli_contract.py` runs one behaviour suite against both implementations, so they cannot drift apart.
- `tests/test_skill_package.py` validates `SKILL.md` frontmatter, the `metadata.splunk` block, `agents/openai.yaml`, `evals.json`, version consistency and links.
- `evals.json` holds model-graded trigger/behaviour evals in the official format; they need an eval runner and are only structure-checked here.
- `.github/workflows/api-check.yml` runs the live tests weekly, because the Splunkbase API is unofficial. See [references/api.md](references/api.md).

## Releasing

1. Bump the version in `SKILL.md` (`metadata.version`), both scripts, and add a `CHANGELOG.md` entry.
2. Merge to `main`, then `git tag v2.1.0 && git push origin v2.1.0`.
3. The release workflow checks the tag matches `SKILL.md`, runs the tests, builds `splunkbase-skill.skill` from `git archive` (files marked `export-ignore` in `.gitattributes` are left out) and publishes the release with the changelog notes.

## License

[Apache-2.0](LICENSE).
