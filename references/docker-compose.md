# Installing Splunkbase apps in the `splunk/splunk` image

The container downloads each URL in `SPLUNK_APPS_URL` at start-up, authenticating
with your Splunkbase account. This applies to the `splunk/splunk` image run with
Docker or Docker Compose. It does not apply to the Splunk Operator for Kubernetes:
its App Framework installs app packages from S3, Azure Blob or GCP storage, so
download the packages (needs a Splunkbase login) and host them there instead.

Verified 2026-10-28 against the docker-splunk repository (`README.md`,
`docs/advanced/APP_INSTALL.md`, `uf/common-files/entrypoint.sh`), Docker Hub tags
and the Splunk Operator `docs/operate/AppFramework.md`.

## Compose example

```yaml
services:
  splunk:
    image: splunk/splunk:${SPLUNK_VERSION:-9.4}
    platform: linux/amd64          # the image has no arm64 build; needed on Apple silicon
    environment:
      # Required to start, and the user's decision to accept (see Notes); add only once they have:
      # SPLUNK_GENERAL_TERMS: --accept-sgt-current-at-splunk-com   # 10.x images, ignored by 9.x
      # SPLUNK_START_ARGS: --accept-license
      SPLUNK_PASSWORD: ${SPLUNK_PASSWORD}
      SPLUNKBASE_USERNAME: ${SPLUNKBASE_USERNAME}
      SPLUNKBASE_PASSWORD: ${SPLUNKBASE_PASSWORD}
      SPLUNK_APPS_URL: ${SPLUNK_APPS_URL}
    ports:
      - "8000:8000"
```

Generate the value and keep credentials in an untracked `.env`:

```bash
python3 scripts/splunkbase_urls.py --format env --image splunk/splunk:9.4 4353 7931 >> .env
cat >> .env <<'ENV'
SPLUNK_PASSWORD=change-me-please
SPLUNKBASE_USERNAME=you@example.com
SPLUNKBASE_PASSWORD=...
ENV
echo ".env" >> .gitignore
```

Notes:

- `SPLUNK_APPS_URL` is comma-separated with no spaces.
- Use your own Splunkbase account credentials.
- Match the Splunk version to the image tag so apps are compatible with the
  container: `--image` reads it from the tag, or pass `--splunk-version`. If the
  compose file uses `${SPLUNK_VERSION:-9.4}`, expand the variable first.
- Image tags look like `9.4`, `9.4.2`, `10.6.1.1` and `10.6.1-rhel9`, plus `latest`.
  Splunkbase tracks compatibility as major.minor, so `10.6.1.1` is treated as 10.6.
- `SPLUNK_START_ARGS: --accept-license` is required on every container. From 10.x
  images `SPLUNK_GENERAL_TERMS: --accept-sgt-current-at-splunk-com` is required
  too. Accepting is the user's decision: do not add these lines unless they have
  said they accept, and tell them the container will not start without them.
- Re-run the script when upgrading; the URLs pin exact versions.
- To see what has moved since, run `python3 scripts/splunkbase_urls.py --check .env`
  (add `--splunk-version`, or point it at the compose file so it reads the `image:`
  tag). It reports each pin as `current`, `outdated`, `unsupported` or `unknown`
  and exits 3 if any is not current, so it also works in a scheduled job.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| App missing after start-up, 401/403 in `docker logs` | Wrong or missing `SPLUNKBASE_USERNAME` / `SPLUNKBASE_PASSWORD`, or an account that has not accepted the app's licence on splunkbase.splunk.com |
| "No such file" or garbled filename | Platform-specific release name (see the warning from the script); pick the intended build |
| App installed but disabled or erroring | App does not support the Splunk version in the image; re-run with `--splunk-version` |
| Slow start on Apple silicon | `linux/amd64` runs under emulation |
| Container exits at once with "License not accepted" | `SPLUNK_START_ARGS` and, on 10.x, `SPLUNK_GENERAL_TERMS` are missing |
