#!/bin/bash
# Backward-compatible UK dispatcher. Prefer: property <command>
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_DIR="$SCRIPT_DIR/cache"
mkdir -p "$CACHE_DIR"

usage() {
  cat <<'USAGE'
UK Property CLI

USAGE:
  ./fetch.sh all <beds> [rightmove_location_ids] [max_price]
  ./fetch.sh espc <beds>
  ./fetch.sh rightmove <beds> [max_pages] [location_ids] [max_price] [property_types]
  ./fetch.sh zoopla <beds>
  ./fetch.sh dedupe <files...>
  ./fetch.sh filter <file> [opts]
  ./fetch.sh compare <old> <new>

Prefer the international CLI:
  python3 -m open_properties.cli search --country GB --provider rightmove --min-beds 2 --location edinburgh
  uk-property search --profile edinburgh-brrr --apply-filters --rank
USAGE
  exit 1
}

[ $# -gt 0 ] || usage
COMMAND="$1"; shift

case "$COMMAND" in
  all)
    BEDS="${1:-4}"
    RM_LOCATIONS="${2:-REGION^475}"
    MAX_PRICE="${3:-}"
    python3 -m uk_property_cli.cli search --portal all --min-beds "$BEDS" --location-id "$RM_LOCATIONS" ${MAX_PRICE:+--max-price "$MAX_PRICE"}
    ;;
  rightmove)
    BEDS="${1:-4}"; MAX_PAGES="${2:-3}"; LOCATIONS="${3:-REGION^475}"; MAX_PRICE="${4:-}"; TYPES="${5:-}"
    python3 "$SCRIPT_DIR/parsers/rightmove.py" "$BEDS" "$MAX_PAGES" "$LOCATIONS" "$MAX_PRICE" "$TYPES"
    ;;
  espc|zoopla)
    BEDS="${1:-4}"
    python3 "$SCRIPT_DIR/parsers/${COMMAND}.py" "$BEDS"
    ;;
  dedupe)
    python3 -m uk_property_cli.cli dedupe "$@"
    ;;
  filter)
    python3 -m uk_property_cli.cli filter "$@"
    ;;
  compare)
    python3 -m uk_property_cli.cli compare "$@"
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    usage
    ;;
esac
