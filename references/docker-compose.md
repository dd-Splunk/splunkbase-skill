# Installing Splunkbase apps in the `splunk/splunk` image

The container downloads each URL in `SPLUNK_APPS_URL` at start-up, authenticating
with your Splunkbase account.

## Compose example

```yaml
services:
  splunk:
    image: splunk/splunk:${SPLUNK_VERSION:-9.4}
    platform: linux/amd64          # the image has no arm64 build; needed on Apple silicon
    environment:
      SPLUNK_GENERAL_TERMS: --accept-sgt-current-at-splunk-com
      SPLUNK_START_ARGS: --accept-license
      SPLUNK_PASSWORD: ${SPLUNK_PASSWORD}
      SPLUNKBASE_USERNAME: ${SPLUNKBASE_USERNAME}
      SPLUNKBASE_PASSWORD: ${SPLUNKBASE_PASSWORD}
      SPLUNK_APPS_URL: ${SPLUNK_APPS_URL}
    ports:
      - "8000:8000"
```

Generate the value and keep credentials in an untracked `.env`:

```bash
python3 scripts/splunkbase_urls.py --format env --splunk-version 9.4 4353 7931 >> .env
cat >> .env <<'ENV'
SPLUNK_PASSWORD=change-me-please
SPLUNKBASE_USERNAME=you@example.com
SPLUNKBASE_PASSWORD=...
ENV
echo ".env" >> .gitignore
```

Notes:

- `SPLUNK_APPS_URL` is comma-separated with no spaces.
- Use your own Splunkbase login name; it is not necessarily an `@splunk.com` address.
- Match `--splunk-version` to the image tag so apps are compatible with the container.
- Re-run the script when upgrading; the URLs pin exact versions.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| App missing after start-up, 401/403 in `docker logs` | Wrong or missing `SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD`, or an account that has not accepted the app's licence on splunkbase.splunk.com |
| "No such file" or garbled filename | Platform-specific release name (see the warning from the script); pick the intended build |
| App installed but disabled or erroring | App does not support the Splunk version in the image; re-run with `--splunk-version` |
| Slow start on Apple silicon | `linux/amd64` runs under emulation |
