#!/usr/bin/env bash
set -euo pipefail

# --- Defaults ---
MUSIC_EXE="${MUSIC_EXE:-../MUSIC2/build/MUSIC}"
CONFIG_DIR="configs"

usage() {
    echo "Usage: $0 <halo_name> [--all] [--config-files-dir DIR] [--music-exe PATH]"
    echo ""
    echo "  halo_name              Required. Run only configs matching this halo name."
    echo "  --all                  Run MUSIC for all matching configs in --config-files-dir."
    echo "  --config-files-dir DIR Directory containing MUSIC config files (default: configs/)."
    echo "  --music-exe PATH       Path to MUSIC executable (default: \$MUSIC_EXE or ../MUSIC2/build/MUSIC)."
    exit 1
}

# --- Parse arguments ---
HALO_NAME=""
RUN_ALL=false

if [[ $# -lt 1 ]]; then
    usage
fi

HALO_NAME="$1"
shift

while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)              RUN_ALL=true; shift ;;
        --config-files-dir) CONFIG_DIR="$2"; shift 2 ;;
        --music-exe)        MUSIC_EXE="$2"; shift 2 ;;
        -h|--help)          usage ;;
        *)                  echo "Unknown option: $1"; usage ;;
    esac
done

# --- Validate ---
if [[ -z "$HALO_NAME" ]]; then
    echo "ERROR: halo_name is required."
    usage
fi

if [[ ! -x "$MUSIC_EXE" ]]; then
    echo "ERROR: MUSIC executable not found or not executable at: $MUSIC_EXE"
    echo "  Set --music-exe or export MUSIC_EXE=/path/to/MUSIC"
    exit 1
fi

if [[ ! -d "$CONFIG_DIR" ]]; then
    echo "ERROR: Config directory not found: $CONFIG_DIR"
    exit 1
fi

# --- Find matching config files ---
mapfile -t CONFIGS < <(ls "$CONFIG_DIR"/music_"${HALO_NAME}"_*.conf 2>/dev/null || true)

if [[ ${#CONFIGS[@]} -eq 0 ]]; then
    echo "No config files found for halo '${HALO_NAME}' in ${CONFIG_DIR}/."
    exit 1
fi

if [[ "$RUN_ALL" = false ]]; then
    if [[ ${#CONFIGS[@]} -gt 1 ]]; then
        echo "Found ${#CONFIGS[@]} configs for halo '${HALO_NAME}'. Use --all to run all of them."
        echo "Available:"
        for f in "${CONFIGS[@]}"; do echo "  $f"; done
        exit 1
    fi
    CONFIGS=("${CONFIGS[0]}")
fi

# --- Run MUSIC ---
echo "Using MUSIC executable: $MUSIC_EXE"
echo "Config directory:       $CONFIG_DIR"
echo "Halo:                   $HALO_NAME"
echo "Configs to run:         ${#CONFIGS[@]}"
echo "==========================================="

ok=0
failed=0
for conf in "${CONFIGS[@]}"; do
    echo "Running: $conf ..."
    if "$MUSIC_EXE" "$conf"; then
        echo "  OK: $conf"
        ok=$((ok + 1))
    else
        echo "  FAILED: $conf"
        failed=$((failed + 1))
    fi
done

echo "==========================================="
echo "Done: $ok succeeded, $failed failed."
[[ $failed -eq 0 ]]
