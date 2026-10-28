# Sources

Public documentation behind the guidance in `SKILL.md`. Splunkbase's JSON API
itself is unofficial; see [api.md](api.md) for what was verified directly.

| Topic | Source |
|-------|--------|
| `splunk/splunk` image, `SPLUNK_APPS_URL`, `SPLUNKBASE_USERNAME`/`SPLUNKBASE_PASSWORD` | https://splunk.github.io/docker-splunk/ and https://github.com/splunk/docker-splunk |
| `SPLUNK_GENERAL_TERMS` (10.x), license acceptance, comma-separated `SPLUNK_APPS_URL`, credentials | https://github.com/splunk/docker-splunk (`README.md`, `docs/advanced/APP_INSTALL.md`, `uf/common-files/entrypoint.sh`) |
| Image tags and architectures (`linux/amd64` only) | https://hub.docker.com/r/splunk/splunk/tags |
| Kubernetes app installs (object storage, not Splunkbase URLs) | https://github.com/splunk/splunk-operator (`docs/operate/AppFramework.md`) |
| App management and packaging | https://dev.splunk.com/enterprise/docs/developapps/manageapps/ |
| Splunk product documentation | https://help.splunk.com |
| Official Splunk agent skills (lifecycle, product questions) | https://github.com/splunk/splunk-agent-skills |

When the user needs an authoritative compatibility statement, the app's own
Splunkbase listing and release notes win over this skill's `compatibility`
field, which only reflects the `product_versions` list the release declares.
