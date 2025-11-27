#!/bin/bash
#
# Splunkbase App URL Fetcher
#
# This script fetches the latest download URLs from Splunkbase applications.
# Useful for creating Docker Compose configurations with SPLUNK_APPS_URL environment variable.
#
# Usage:
#   ./get_splunkbase_urls.sh <app_id> [app_id2] [app_id3] ...
#
# Examples:
#   ./get_splunkbase_urls.sh 4353
#   ./get_splunkbase_urls.sh 4353 7931 1876 833
#

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SPLUNKBASE_API_BASE="https://splunkbase.splunk.com/api/v1/app"
TIMEOUT=10

#################################################################################
# Function: print_usage
# Description: Print usage information
#################################################################################
print_usage() {
    cat << EOF
Usage: $(basename "$0") <app_id> [app_id2] [app_id3] ...

Fetch latest download URLs from Splunkbase for one or more apps.

Arguments:
    app_id    Splunkbase app ID(s) (numeric, e.g., 4353, 7931)

Options:
    -h, --help      Show this help message
    -v, --verbose   Enable verbose output

Examples:
    $(basename "$0") 4353
    $(basename "$0") 4353 7931 1876 833
    SPLUNK_APPS_URL=\$($0 4353 7931)

EOF
}

#################################################################################
# Function: check_dependencies
# Description: Verify that required commands are available
#################################################################################
check_dependencies() {
    local missing_deps=0

    if ! command -v curl &> /dev/null; then
        echo -e "${RED}Error: curl is not installed${NC}" >&2
        missing_deps=1
    fi

    if ! command -v jq &> /dev/null; then
        echo -e "${RED}Error: jq is not installed${NC}" >&2
        echo "Install with: brew install jq (macOS) or apt-get install jq (Linux)" >&2
        missing_deps=1
    fi

    if [ $missing_deps -eq 1 ]; then
        return 1
    fi
    return 0
}

#################################################################################
# Function: get_app_info
# Description: Fetch app name and latest release info from Splunkbase API
#
# Arguments:
#   $1 - app_id: The Splunkbase app ID
#
# Returns:
#   0 on success, 1 on error
#   Echoes: "app_name|version|download_url"
#################################################################################
get_app_info() {
    local app_id="$1"
    local app_url="${SPLUNKBASE_API_BASE}/${app_id}"
    local release_url="${SPLUNKBASE_API_BASE}/${app_id}/release"

    # Validate app_id is numeric
    if ! [[ "$app_id" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}Error: Invalid app ID '${app_id}' (must be numeric)${NC}" >&2
        return 1
    fi

    # Fetch app details for title
    local app_response
    if ! app_response=$(curl -s --location --max-time "$TIMEOUT" "$app_url" 2>/dev/null); then
        echo -e "${RED}Error: Network error fetching app details for ID ${app_id}${NC}" >&2
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
    if ! release_response=$(curl -s --location --max-time "$TIMEOUT" "$release_url" 2>/dev/null); then
        echo -e "${RED}Error: Network error fetching releases for app ID ${app_id}${NC}" >&2
        return 1
    fi

    # Extract latest version
    local version
    version=$(echo "$release_response" | jq -r '.[0].name // empty' 2>/dev/null)
    if [ -z "$version" ]; then
        echo -e "${RED}Error: No releases found for app ID ${app_id}${NC}" >&2
        return 1
    fi

    # Construct download URL
    local download_url="${SPLUNKBASE_API_BASE%/api/v1/app}/app/${app_id}/release/${version}/download/"

    # Output in pipe-delimited format for parsing
    echo "${app_name}|${version}|${download_url}"
    return 0
}

#################################################################################
# Function: get_multiple_urls
# Description: Fetch URLs for multiple apps and format for Docker Compose
#
# Arguments:
#   $@ - app_ids: One or more Splunkbase app IDs
#
# Returns:
#   Comma-separated URLs suitable for SPLUNK_APPS_URL environment variable
#################################################################################
get_multiple_urls() {
    local app_ids=("$@")
    local urls=()
    local failed=0

    for app_id in "${app_ids[@]}"; do
        if app_info=$(get_app_info "$app_id"); then
            local app_name version download_url
            IFS='|' read -r app_name version download_url <<< "$app_info"

            if [ -n "${VERBOSE:-}" ]; then
                echo -e "${GREEN}✓${NC} App ID: ${app_id}" >&2
                echo -e "  Name: ${app_name}" >&2
                echo -e "  Version: ${version}" >&2
                echo -e "  URL: ${download_url}" >&2
            fi

            urls+=("$download_url")
        else
            failed=$((failed + 1))
        fi
    done

    # Output the comma-separated URLs
    if [ ${#urls[@]} -gt 0 ]; then
        (IFS=','; echo "${urls[*]}")
    fi

    if [ $failed -gt 0 ]; then
        return 1
    fi
    return 0
}

#################################################################################
# Main Script Logic
#################################################################################
main() {
    local verbose_flag=""
    local app_ids=()

    # Parse command-line arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                print_usage
                exit 0
                ;;
            -v|--verbose)
                verbose_flag="1"
                shift
                ;;
            -*)
                echo "Unknown option: $1" >&2
                print_usage
                exit 1
                ;;
            *)
                app_ids+=("$1")
                shift
                ;;
        esac
    done

    # Check if verbose mode
    if [ -n "$verbose_flag" ]; then
        export VERBOSE=1
    fi

    # Validate that at least one app ID was provided
    if [ ${#app_ids[@]} -eq 0 ]; then
        echo -e "${RED}Error: No app IDs provided${NC}" >&2
        print_usage
        exit 1
    fi

    # Check dependencies
    if ! check_dependencies; then
        exit 1
    fi

    # Fetch and output URLs
    get_multiple_urls "${app_ids[@]}"
}

# Run main if script is executed (not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
