# Splunkbase App URL Skill

A Claude Skill for fetching the latest download URLs from Splunkbase applications. This skill is particularly useful when creating Docker Compose configurations for Splunk deployments.

## Overview

This skill enables Claude to:

- Fetch the latest release download URL for any Splunkbase app by ID
- Generate comma-separated URLs for multiple apps
- Create properly formatted `SPLUNK_APPS_URL` environment variables
- Integrate seamlessly with Docker Compose configurations

## Installation

### As a Claude Skill

1. Download the `splunkbase-skill.zip` file from the [latest GitHub release](https://github.com/dd-Splunk/splunkbase-skill/releases/download/latest/splunkbase-skill.zip)
2. Follow the instructions: [Using Skills in Claude](https://support.claude.com/en/articles/12512180-using-skills-in-claude)
3. Extract and import the skill in your Claude workspace

### Python Implementation

#### Requirements

```bash
pip install requests
```

#### Usage

```python
from splunkbase_urls import get_splunkbase_app_url, get_multiple_splunkbase_urls

# Single app
url = get_splunkbase_app_url("4353")
print(url)
# Output: https://splunkbase.splunk.com/app/4353/release/1.8.20/download/

# Multiple apps
urls = get_multiple_splunkbase_urls(["4353", "7931"])
print(urls)
# Output: https://splunkbase.splunk.com/app/4353/release/1.8.20/download/,https://splunkbase.splunk.com/app/7931/release/0.2.6/download/
```

### Bash Script

#### Bash Setup

- `curl`
- `jq` (install with `brew install jq` on macOS or `apt-get install jq` on Linux)

#### Bash Installationation

Make the script executable:

```bash
chmod +x get_splunkbase_urls.sh
```

#### Bash Examples

```bash
# Single app
./get_splunkbase_urls.sh 4353

# Multiple apps
./get_splunkbase_urls.sh 4353 7931 1876 833

# Verbose output with app details
./get_splunkbase_urls.sh -v 4353 7931

# Use in Docker Compose generation
SPLUNK_APPS_URL=$(./get_splunkbase_urls.sh 4353 7931)
echo "SPLUNK_APPS_URL: $SPLUNK_APPS_URL"

# Use in environment file (.env)
echo "SPLUNK_APPS_URL=$(./get_splunkbase_urls.sh 4353 7931)" >> .env
```

#### Features

- **Multiple app support**: Fetch URLs for one or more apps at once
- **Verbose mode**: Display app names, versions, and URLs with `-v` flag
- **Error handling**: Graceful error handling with meaningful error messages
- **Dependency check**: Validates `curl` and `jq` are installed
- **Input validation**: Ensures app IDs are numeric
- **Docker Compose ready**: Output format compatible with SPLUNK_APPS_URL environment variable

## Examples

### Example 1: Fetch Single App URL

**Request to Claude:**

```text
Get me the latest download URL for Splunkbase app 4353
```

**Claude Response:**

```text
https://splunkbase.splunk.com/app/4353/release/1.8.20/download/
```

### Example 2: Generate Docker Compose Configuration

**Request to Claude:**

```text
Create a Docker Compose service for Splunk with apps 4353 and 7931.
```

**Claude Response:**

```yaml
services:
  splunk:
    hostname: splunk
    container_name: splunk
    image: splunk/splunk:latest
    platform: linux/amd64
    environment:
      SPLUNK_GENERAL_TERMS: --accept-sgt-current-at-splunk-com
      SPLUNK_START_ARGS: --accept-license
      SPLUNK_PASSWORD: ${SPLUNK_PASSWORD}
      SPLUNKBASE_USERNAME: ${SPLUNKBASE_USER}@splunk.com
      SPLUNKBASE_PASSWORD: ${SPLUNKBASE_PASS}
      SPLUNK_APPS_URL: https://splunkbase.splunk.com/app/4353/release/1.8.20/download/,https://splunkbase.splunk.com/app/7931/release/0.2.6/download/
      TZ: ${TZ:-Europe/Brussels}
    volumes:
      - ./default.yml:/tmp/defaults/default.yml
      - splunk-var:/opt/splunk/var
      - splunk-etc:/opt/splunk/etc
    ports:
      - "8000:8000"
      - "8089:8089"
    networks:
      - splunk
    restart: always

volumes:
  splunk-var:
  splunk-etc:

networks:
  splunk:
```

### Example 3: Update Existing Docker Compose

**Request to Claude:**

```text
Update my SPLUNK_APPS_URL with the latest versions of apps 4353 and 7931.
```

**Claude Response:**

```yaml
SPLUNK_APPS_URL: https://splunkbase.splunk.com/app/4353/release/1.8.20/download/,https://splunkbase.splunk.com/app/7931/release/0.2.6/download/
```

## API Details

### Splunkbase API Endpoint

```text
https://splunkbase.splunk.com/api/v1/app/{app_id}/release
```

### Response Format

```json
[
  {
    "name": "1.8.20",
    "title": "Version 1.8.20",
    "created_time": "2024-01-15T10:30:00Z",
    "published": true
  }
]
```

The first element contains the latest release information.

## Common Splunkbase Apps

| App ID | Name | Description |
|--------|------|-------------|
| 4353 | Splunk Add-on for Cisco ISE | Cisco Identity Services Engine integration |
| 1809 | Splunk Add-on for Windows | Windows event log collection |
| 742 | Splunk Add-on for Unix and Linux | Unix/Linux system monitoring |
| 3212 | Splunk Add-on for AWS | Amazon Web Services integration |
| 1621 | Splunk Add-on for Microsoft Cloud Services | Microsoft 365 and Azure integration |

## Troubleshooting

### Issue: "Error fetching details for Splunkbase app"

**Cause:** Invalid app ID or network connectivity issue

**Solution:**

1. Verify the app ID by visiting `https://splunkbase.splunk.com/app/{app_id}/`
2. Check your internet connection
3. Ensure the Splunkbase API is accessible

### Issue: "Unexpected response structure"

**Cause:** The app may not have any releases or the API response changed

**Solution:**

1. Check if the app exists on Splunkbase
2. Verify the app has published releases
3. Update the script to handle the new API format

### Issue: jq not found (Bash script)

**Cause:** `jq` is not installed

**Solution:**

```bash
# macOS
brew install jq

# Ubuntu/Debian
sudo apt-get install jq

# CentOS/RHEL
sudo yum install jq
```

## Security Best Practices

1. **Never hardcode credentials** in Docker Compose files
2. Use environment variables for sensitive data:

   ```bash
   # .env file
   SPLUNK_PASSWORD=your_password
   SPLUNKBASE_USER=your_username
   SPLUNKBASE_PASS=your_splunkbase_password
   ```

3. Add `.env` to `.gitignore`
4. Use secrets management for production deployments

## Contributing

To improve this skill:

1. Test with various Splunkbase apps
2. Add error handling for edge cases
3. Extend with caching for frequently accessed apps
4. Add support for specific version fetching (not just latest)

## License

This skill is provided as-is for use with Claude and Splunk deployments.

## Version

**v1.0.0** - Initial release (2025-11-27)
