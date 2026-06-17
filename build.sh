#!/usr/bin/env bash
# Build CrudeMaps for the Instinct 2 and (optionally) launch it in the simulator.
#   ./build.sh         -> compile to bin/CrudeMaps.prg
#   ./build.sh run     -> compile, start the simulator, and side-load the app
set -euo pipefail

SDK="$(cat "$HOME/.Garmin/ConnectIQ/current-sdk.cfg" 2>/dev/null || true)"
SDK="${SDK%/}"
if [[ -z "${SDK}" || ! -d "${SDK}" ]]; then
    SDK="$(ls -d "$HOME"/.Garmin/ConnectIQ/Sdks/connectiq-sdk-* | sort | tail -1)"
fi
BIN="${SDK}/bin"
KEY="$HOME/.Garmin/developer_key.der"
DEVICE="instinct2"
OUT="bin/CrudeMaps.prg"

mkdir -p bin
echo "Using SDK: ${SDK}"

if [[ "${1:-}" == "package" ]]; then
    # Store export: a single .iq bundling every product in the manifest.
    IQ="bin/CrudeMaps.iq"
    "${BIN}/monkeyc" -e -f monkey.jungle -o "${IQ}" -y "${KEY}" -w -r
    echo "Packaged ${IQ} (upload this to the Connect IQ store)"
    exit 0
fi

"${BIN}/monkeyc" -d "${DEVICE}" -f monkey.jungle -o "${OUT}" -y "${KEY}" -w
echo "Built ${OUT}"

if [[ "${1:-}" == "run" ]]; then
    ( "${BIN}/connectiq" >/dev/null 2>&1 & )
    sleep 4
    "${BIN}/monkeydo" "${OUT}" "${DEVICE}"
fi
