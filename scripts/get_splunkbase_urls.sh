#!/usr/bin/env bash
#
# Resolve Splunkbase apps to their latest download URLs (curl + jq).
#
# Fallback for machines without Python. Same behaviour as splunkbase_urls.py,
# minus --search and --format table, and apps are resolved one at a time.
#
# Usage:
#   get_splunkbase_urls.sh [options] APP [APP ...]
#
# Exit status: 0 = every app resolved, 1 = at least one failed (by default
# nothing is printed to stdout then), 2 = usage error.

set -euo pipefail

VERSION="2.3.0"
BASE_URL="${SPLUNKBASE_BASE_URL:-https://splunkbase.splunk.com}"
BASE_URL="${BASE_URL%/}"
TIMEOUT=10
RETRIES=2
USER_AGENT="splunkbase-skill/${VERSION}"

usage() {
    cat <<EOF
Usage: $(basename "$0") [options] APP [APP ...]

Print the latest Splunkbase download URL for each app.

APP is a Splunkbase app ID or app page URL (commas allowed: 4353,7931).

Options:
  --splunk-version VER  only pick releases supporting this Splunk version
                        (e.g. 9.4 or 10.2.1)
  --image REF           take the Splunk version from a container image tag
                        (e.g. splunk/splunk:9.4.2); latest or untagged
                        images are not checked
  --cloud               only pick releases marked Splunk Cloud compatible
  --format FMT          urls (default): comma-separated
                        env: SPLUNK_APPS_URL=...
                        json
  --partial             still print URLs for apps that resolved when others
                        fail (exit status stays 1)
  -q, --quiet           suppress warnings on stderr
  --version             print version
  -h, --help            show this help

Downloading a URL needs Splunkbase credentials; resolving it does not.
EOF
}

die_usage() {
    echo "$(basename "$0"): error: $1" >&2
    exit 2
}

warn() { [ "$QUIET" = 1 ] || echo "warning: $1" >&2; }

# parse_app_id VALUE -> prints the numeric app ID, returns 1 if not parseable
parse_app_id() {
    local value="$1"
    local url_re='/app/([0-9]+)([/?#]|$)'
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "$value" =~ ^[0-9]+$ ]]; then
        echo "$value"
    elif [[ "$value" =~ $url_re ]]; then
        echo "${BASH_REMATCH[1]}"
    else
        return 1
    fi
}

# fetch_json URL -> body on stdout. Returns 0 on HTTP 200, 2 on 404, 1 otherwise
# (with a message on stderr).
fetch_json() {
    local url="$1" body code
    body="$(mktemp)"
    if ! code="$(curl -sSL --max-time "$TIMEOUT" --retry "$RETRIES" --retry-delay 1 \
        -A "$USER_AGENT" -H 'Accept: application/json' \
        -o "$body" -w '%{http_code}' "$url" 2>/dev/null)"; then
        rm -f "$body"
        echo "cannot reach ${BASE_URL}; check the network connection and any proxy or sandbox restrictions" >&2
        return 1
    fi
    if [ "$code" = 200 ]; then
        cat "$body"
        rm -f "$body"
        return 0
    fi
    rm -f "$body"
    if [ "$code" = 404 ]; then
        return 2
    fi
    echo "HTTP ${code} from ${url}" >&2
    return 1
}

# jq program: choose a release and build the result object (or {error: ...}).
# Mirrors select_release()/resolve_app() in splunkbase_urls.py.
# shellcheck disable=SC2016  # $-variables belong to jq, not the shell
JQ_RESOLVE='
def clean: gsub("^\\s+|\\s+$"; "");
def tidy: gsub("[\\p{Cc}\\p{Zl}\\p{Zp}]+"; " ") | gsub("\\s+"; " ") | gsub("^ | $"; "") | if length > 120 then .[0:119] + "…" else . end;
def supported: if length > 0 then "\(.[-1]) to \(.[0])" else "unknown" end;
($rel | map(select(type == "object" and (.name | type) == "string"
        and ((.name | ascii_downcase | clean) as $n
             | ($n == "" or $n == "null" or $n == "none") | not)))) as $downloadable
| (if $cloud == "1" then $downloadable | map(select(.cloud_compatible == true)) else $downloadable end) as $usable
| if ($downloadable | length) == 0 then
    {error: "no downloadable release (the release has no version name, so no download URL can be built)"}
  elif ($usable | length) == 0 then
    {error: "no release is marked Splunk Cloud compatible"}
  else
    (if $sv == "" then {r: $usable[0], c: "not-checked", w: []}
     else
       ([ $usable[] | select(((.product_versions // []) | any(. == $sv))
                             or ((.product_versions // []) | length) == 0) ] | .[0]) as $pick
       | if $pick == null then
           {error: "no release is compatible with Splunk \($sv)\(if $cloud == "1" then " among Splunk Cloud compatible releases" else "" end) (latest is \($usable[0].name), which supports \(($usable[0].product_versions // []) | supported))"}
         elif ($pick.product_versions // []) | any(. == $sv) then
           {r: $pick, c: "compatible", w: []}
         else
           {r: $pick, c: "unknown",
            w: ["release \($pick.name) does not declare Splunk compatibility; cannot confirm it supports \($sv)"]}
         end
     end)
    | if .error then . else
        (.r.name | clean) as $v
        | {app_id: ($id | tonumber),
           title: (($app.title // "Unknown") | tidy),
           slug: (if $app.appid then ($app.appid | tidy) else null end),
           version: $v,
           url: "\($base)/app/\($id)/release/\($v | @uri)/download/",
           published: (.r.published_datetime // null),
           splunk_versions: (.r.product_versions // []),
           compatibility: .c,
           cloud_compatible: (if (.r.cloud_compatible | type) == "boolean" then .r.cloud_compatible else null end),
           warnings: (.w
             + (if $app.is_archived then ["app is archived on Splunkbase"] else [] end)
             + (if ($v | test("^[0-9][A-Za-z0-9_.+-]*$")) then [] else
                 ["release name \"\($v | tidy)\" has extra text; it may be a platform-specific build, check it is the one you need"] end))}
      end
  end'

# resolve_app ID SPLUNK_VERSION CLOUD -> one compact JSON object on stdout.
# On failure prints an "error: ..." line to stderr and returns 1.
resolve_app() {
    local id="$1" sv="$2" cloud="$3" app rel rc title label out
    rc=0
    app="$(fetch_json "${BASE_URL}/api/v1/app/${id}")" || rc=$?
    if [ "$rc" = 2 ]; then
        echo "error: app ${id}: app not found on Splunkbase" >&2
        return 1
    elif [ "$rc" != 0 ]; then
        echo "error: app ${id}: unexpected response" >&2
        return 1
    fi
    if ! title="$(jq -r 'if type == "object" then (.title // "Unknown") else error("x") end | gsub("[\\p{Cc}\\p{Zl}\\p{Zp}]+"; " ") | gsub("\\s+"; " ") | gsub("^ | $"; "") | if length > 120 then .[0:119] + "…" else . end' <<<"$app" 2>/dev/null)"; then
        echo "error: app ${id}: unexpected app response" >&2
        return 1
    fi
    label="app ${id} (${title})"

    rc=0
    rel="$(fetch_json "${BASE_URL}/api/v1/app/${id}/release")" || rc=$?
    if [ "$rc" = 2 ] || { [ "$rc" = 0 ] && ! jq -e 'type == "array" and length > 0' <<<"$rel" >/dev/null 2>&1; }; then
        echo "error: ${label}: no releases found" >&2
        return 1
    elif [ "$rc" != 0 ]; then
        echo "error: ${label}: unexpected response" >&2
        return 1
    fi

    out="$(jq -c --argjson app "$app" --argjson rel "$rel" --arg id "$id" \
        --arg sv "$sv" --arg cloud "$cloud" --arg base "$BASE_URL" "$JQ_RESOLVE" <<<null)"
    if jq -e 'has("error")' <<<"$out" >/dev/null; then
        echo "error: ${label}: $(jq -r .error <<<"$out")" >&2
        return 1
    fi
    echo "$out"
}

FORMAT="urls"
SPLUNK_VERSION=""
IMAGE=""
CLOUD=0
PARTIAL=0
QUIET=0
RAW_APPS=()

while [ $# -gt 0 ]; do
    case "$1" in
        -h | --help) usage; exit 0 ;;
        --version) echo "$VERSION"; exit 0 ;;
        --splunk-version)
            [ $# -ge 2 ] || die_usage "--splunk-version needs a value"
            SPLUNK_VERSION="$2"; shift 2 ;;
        --image)
            [ $# -ge 2 ] || die_usage "--image needs a value"
            IMAGE="$2"; shift 2 ;;
        --cloud) CLOUD=1; shift ;;
        --format)
            [ $# -ge 2 ] || die_usage "--format needs a value"
            FORMAT="$2"; shift 2 ;;
        --partial) PARTIAL=1; shift ;;
        -q | --quiet) QUIET=1; shift ;;
        --search | --search=*) die_usage "--search is only available in splunkbase_urls.py" ;;
        --check | --check=*) die_usage "--check is only available in splunkbase_urls.py" ;;
        -*) die_usage "unknown option: $1" ;;
        *) RAW_APPS+=("$1"); shift ;;
    esac
done

case "$FORMAT" in
    urls | env | json) ;;
    *) die_usage "--format must be urls, env or json" ;;
esac
[ ${#RAW_APPS[@]} -gt 0 ] || die_usage "give at least one app ID"

sv_re='^([0-9]+)\.([0-9]+)(\.[A-Za-z0-9]+)*$'
if [ -n "$IMAGE" ]; then
    [ -z "$SPLUNK_VERSION" ] || die_usage "use either --image or --splunk-version, not both"
    image_name="${IMAGE%%@*}"
    image_name="${image_name##*/}"
    image_tag=""
    if [[ "$image_name" == *:* ]]; then
        image_tag="${image_name#*:}"
        image_tag="${image_tag%%-*}"
    fi
    if [[ "$image_tag" =~ $sv_re ]]; then
        SPLUNK_VERSION="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
        [ "$QUIET" = 1 ] || echo "note: using Splunk ${SPLUNK_VERSION} from image ${IMAGE}" >&2
    else
        warn "image ${IMAGE} does not pin a Splunk version; compatibility not checked"
    fi
elif [ -n "$SPLUNK_VERSION" ]; then
    if [[ "$SPLUNK_VERSION" =~ $sv_re ]]; then
        SPLUNK_VERSION="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
    else
        die_usage "not a Splunk version like 9.4 or 10.2.1: '${SPLUNK_VERSION}'"
    fi
fi

for tool in curl jq; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "error: ${tool} is not installed" >&2
        exit 1
    }
done

APP_IDS=()
SEEN=" "
for arg in "${RAW_APPS[@]}"; do
    IFS=$', \t\n' read -r -a parts <<<"$arg"
    for part in ${parts[@]+"${parts[@]}"}; do
        [ -n "$part" ] || continue
        id="$(parse_app_id "$part")" || die_usage "not a Splunkbase app ID or app URL: '${part}'"
        if [[ "$SEEN" == *" ${id} "* ]]; then
            warn "app ${id} given twice, using it once"
            continue
        fi
        SEEN="${SEEN}${id} "
        APP_IDS+=("$id")
    done
done

RESULTS="$(mktemp)"
trap 'rm -f "$RESULTS"' EXIT
failed=0
for id in "${APP_IDS[@]}"; do
    if line="$(resolve_app "$id" "$SPLUNK_VERSION" "$CLOUD")"; then
        echo "$line" >>"$RESULTS"
    else
        failed=1
    fi
done

if [ -s "$RESULTS" ]; then
    if [ "$QUIET" != 1 ]; then
        jq -r '. as $r | .warnings[] | "warning: app \($r.app_id) (\($r.title)): \(.)"' "$RESULTS" >&2
    fi
    if [ "$failed" = 0 ] || [ "$PARTIAL" = 1 ]; then
        case "$FORMAT" in
            urls) jq -rs 'map(.url) | join(",")' "$RESULTS" ;;
            env) jq -rs '"SPLUNK_APPS_URL=" + (map(.url) | join(","))' "$RESULTS" ;;
            json) jq -s '.' "$RESULTS" ;;
        esac
    fi
fi
exit "$failed"
