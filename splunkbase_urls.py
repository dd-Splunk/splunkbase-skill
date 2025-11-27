#!/usr/bin/env python3
"""
Splunkbase App Information Fetcher

This script fetches the latest download URL and app information from Splunkbase.
"""

import requests
from typing import Optional, Tuple


def get_splunkbase_app_info(
    app_id: str,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
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


if __name__ == "__main__":
    # Example usage
    app_ids = ["4353", "7931", "1876", "833"]

    print("Splunkbase App Information:\n")
    print("=" * 80)

    for app_id in app_ids:
        name, version, url = get_splunkbase_app_info(app_id)
        if name and url:
            print(f"\nApp ID: {app_id}")
            print(f"Name: {name}")
            print(f"Version: {version}")
            print(f"URL: {url}")
        else:
            print(f"\nApp ID: {app_id} - Error fetching info")

    print("\n" + "=" * 80)
    print("\nDocker Compose SPLUNK_APPS_URL format:")
    print(get_multiple_splunkbase_urls(app_ids))
