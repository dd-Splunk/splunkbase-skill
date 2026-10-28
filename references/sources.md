# Sources

Public documentation behind the guidance in `SKILL.md`. Splunkbase's JSON API
itself is unofficial; see [api.md](api.md) for what was verified directly.

| Topic | Source |
|-------|--------|
| `splunk/splunk` image, `SPLUNK_APPS_URL`, `SPLUNKBASE_USERNAME`/`SPLUNKBASE_PASSWORD` | https://splunk.github.io/docker-splunk/ and https://github.com/splunk/docker-splunk |
| App management and packaging | https://dev.splunk.com/enterprise/docs/developapps/manageapps/ |
| Splunk product documentation | https://help.splunk.com |
| Official Splunk agent skills (lifecycle, product questions) | https://github.com/splunk/splunk-agent-skills |

When the user needs an authoritative compatibility statement, the app's own
Splunkbase listing and release notes win over this skill's `compatibility`
field, which only reflects the `product_versions` list the release declares.
