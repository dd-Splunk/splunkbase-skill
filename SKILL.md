---
name: splunkbase-skill
description: A Claude Skill for fetching the latest download URLs from Splunkbase applications. This skill is particularly useful when creating Docker Compose configurations for Splunk deployments.
---
# Splunkbase App URL Skill

## Overview

This skill enables Claude to fetch the latest download URL for Splunkbase applications. Given a Splunkbase app ID, it returns the complete download URL including the latest release number.

## When to Use This Skill

Use this skill when:

- Building Docker Compose files for Splunk configurations
- Generating `SPLUNK_APPS_URL` environment variables
- Retrieving the latest version of Splunkbase apps
- Creating automated Splunk deployment scripts

## How It Works

The skill queries the Splunkbase API to:

1. Fetch release information for a given app ID
2. Extract the latest release number
3. Construct the full download URL

## Usage Examples

### Single App URL

**User Request**: "Get me the download URL for Splunkbase app 4353"

**Claude Response**:

```text
https://splunkbase.splunk.com/app/4353/release/1.8.20/download/
```

### Multiple Apps for Docker Compose

**User Request**: "I need SPLUNK_APPS_URL for apps 4353 and 7931"

**Claude Response**:

```text
SPLUNK_APPS_URL: https://splunkbase.splunk.com/app/4353/release/1.8.20/download/,https://splunkbase.splunk.com/app/7931/release/0.2.6/download/
```

### Full Docker Compose Integration

**User Request**: "Create a Docker Compose service with Splunkbase apps 4353 and 7931"

**Claude Response**: Claude will generate a complete Docker Compose service configuration with the fetched URLs.

## Implementation

### Python Function

```python
import requests
from typing import Optional, Tuple


def get_splunkbase_app_info(app_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Fetch app name, version, and latest download URL for a Splunkbase app.
    
    Args:
        app_id: The Splunkbase app ID (e.g., "4353")
        
    Returns:
        Tuple of (app_name, version, download_url) or (None, None, None) on error
    """
    app_url = f"https://splunkbase.splunk.com/api/v1/app/{app_id}"
    release_url = f"https://splunkbase.splunk.com/api/v1/app/{app_id}/release"
    
    try:
        # Get app details for name
        app_response = requests.get(app_url, timeout=10)
        app_response.raise_for_status()
        app_data = app_response.json()
        app_name = app_data.get("title", "Unknown")
        
        # Get latest release
        release_response = requests.get(release_url, timeout=10)
        release_response.raise_for_status()
        release_data = release_response.json()
        
        if release_data and isinstance(release_data, list) and len(release_data) > 0:
            version = release_data[0]["name"]
            download_url = f"https://splunkbase.splunk.com/app/{app_id}/release/{version}/download/"
            return app_name, version, download_url
        else:
            print(f"Error: Unexpected response structure for app {app_id}")
            return app_name, None, None
            
    except requests.RequestException as e:
        print(f"Error fetching details for app {app_id}: {e}")
        return None, None, None
    except (KeyError, IndexError) as e:
        print(f"Unexpected response structure for app {app_id}: {e}")
        return None, None, None


def get_multiple_splunkbase_urls(app_ids: list[str]) -> str:
    """
    Fetch download URLs for multiple Splunkbase apps and format them for Docker Compose.
    
    Args:
        app_ids: List of Splunkbase app IDs
        
    Returns:
        Comma-separated URLs suitable for SPLUNK_APPS_URL environment variable
    """
    urls = []
    for app_id in app_ids:
        _, _, url = get_splunkbase_app_info(app_id)
        if url:
            urls.append(url)
    
    return ",".join(urls)
```

### Bash Alternative (Using curl and jq)

```bash
#!/bin/bash
# get_splunkbase_urls.sh - Fetch Splunkbase app download URLs

get_app_info() {
    local app_id="$1"
    local app_url="https://splunkbase.splunk.com/api/v1/app/${app_id}"
    local release_url="https://splunkbase.splunk.com/api/v1/app/${app_id}/release"

    # Validate app_id is numeric
    if ! [[ "$app_id" =~ ^[0-9]+$ ]]; then
        echo "Error: Invalid app ID '${app_id}' (must be numeric)" >&2
        return 1
    fi

    # Fetch app details for title (--location follows redirects to get JSON response)
    local app_response
    if ! app_response=$(curl -s --location --max-time 10 "$app_url" 2>/dev/null); then
        echo "Error: Network error fetching app details for ID ${app_id}" >&2
        return 1
    fi

    # Extract app title
    local app_name
    app_name=$(echo "$app_response" | jq -r '.title // "Unknown"' 2>/dev/null)
    if [ -z "$app_name" ] || [ "$app_name" = "null" ]; then
        app_name="Unknown"
    fi

    # Fetch release information
    local release_response
    if ! release_response=$(curl -s --location --max-time 10 "$release_url" 2>/dev/null); then
        echo "Error: Network error fetching releases for app ID ${app_id}" >&2
        return 1
    fi

    # Extract latest version
    local version
    version=$(echo "$release_response" | jq -r '.[0].name // empty' 2>/dev/null)
    if [ -z "$version" ]; then
        echo "Error: No releases found for app ID ${app_id}" >&2
        return 1
    fi

    # Construct download URL
    local download_url="https://splunkbase.splunk.com/app/${app_id}/release/${version}/download/"

    # Output in pipe-delimited format for parsing
    echo "${app_name}|${version}|${download_url}"
    return 0
}

# Usage: get_app_info "4353"
```

### Bash Function Examples

```bash
# Single app with full details
app_info=$(get_app_info "4353")
IFS='|' read -r name version url <<< "$app_info"
echo "App: $name v$version"
echo "URL: $url"

# Multiple apps for Docker Compose
SPLUNK_APPS_URL=$(
    for app_id in 4353 7931 1876; do
        get_app_info "$app_id" | cut -d'|' -f3
    done | paste -sd, -
)
echo "SPLUNK_APPS_URL: $SPLUNK_APPS_URL"
```

## Response Guidelines

When using this skill, Claude should:

1. **Always fetch live data**: Don't use cached or example URLs - query the API for current releases
2. **Handle errors gracefully**: If an app ID is invalid or the API is unreachable, inform the user clearly
3. **Format appropriately**:
   - Single URL: Return just the URL
   - Multiple URLs: Return comma-separated for Docker Compose
   - Docker Compose context: Include the full environment variable line
4. **Provide context**: When generating Docker Compose files, explain what apps are being installed
5. **Validate app IDs**: If an app ID seems invalid (non-numeric, too short/long), confirm with the user

## Best Practices

### Error Handling

Always check for and handle these scenarios:

- Network timeouts
- Invalid app IDs
- API rate limiting
- Malformed responses

### Docker Compose Integration

When generating Docker Compose configurations:

- Include both `SPLUNKBASE_USERNAME` and `SPLUNKBASE_PASSWORD` environment variables
- Use the `SPLUNK_APPS_URL` format with comma-separated URLs (no spaces)
- Consider platform architecture (`platform: linux/amd64` for M1/M2 Macs)
- Include appropriate volumes for persistent data

#### Exemple

Request to Claude: Create a Docker Compose service for Splunk with apps 4353 and 7931

Claude Response:

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

### Security Considerations

- Never hardcode Splunkbase credentials in the output
- Use environment variables via `.env` file or `${VARIABLE}` syntax
- Remind users to keep their Splunkbase credentials secure

## Common Splunkbase Apps

Here are some commonly used Splunkbase apps for reference:

- **4353**: Splunk Add-on for Cisco Identity Services Engine
- **7931**: Specific app (would need to verify)
- **1809**: Splunk Add-on for Microsoft Windows
- **742**: Splunk Add-on for Unix and Linux
- **3212**: Splunk Add-on for Amazon Web Services (AWS)

## API Reference

**Endpoint**: `https://splunkbase.splunk.com/api/v1/app/{app_id}/release`

**Response Structure**:

```json
[
  {
    "name": "1.8.20",
    "title": "Version 1.8.20",
    "created_time": "2024-01-15T10:30:00Z",
    "published": true,
    ...
  },
  ...
]
```

The first element (`[0]`) contains the latest release information.

## Troubleshooting

### Issue: Empty or malformed response

**Solution**: Verify the app ID is correct by checking Splunkbase directly

### Issue: API timeout

**Solution**: Retry with exponential backoff or inform user of temporary unavailability

### Issue: Invalid app ID

**Solution**: Ask user to verify the app ID from the Splunkbase URL (e.g., `https://splunkbase.splunk.com/app/4353/`)

## Integration with Docker Compose

Example workflow:

1. User provides app IDs: `4353`, `7931`
2. Skill fetches latest URLs for each
3. Generate complete Docker Compose service with:
   - Correct environment variables
   - Volume mounts
   - Network configuration
   - Port mappings

## Notes

- Release numbers are version strings (e.g., "1.8.20", "0.2.6")
- The API returns releases in reverse chronological order (latest first)
- Some apps may have beta or pre-release versions - always use the first stable release
- The skill should handle both string and numeric app IDs gracefully

## Version History

- **v1.0.0** (2025-11-27): Initial skill creation based on Python implementation
