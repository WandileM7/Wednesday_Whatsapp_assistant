#!/usr/bin/env bash
# Start the iMessage sidecar with the project's .env loaded.
#
# It used to be started by hand with the variables typed on the command line,
# and that is a trap: PHOTON_* and IMESSAGE_HOOK_URL then live only in shell
# history, so the next restart comes up authenticated-but-deaf — healthy in
# /health, connected to Photon, and quietly posting inbound messages nowhere.
# Node reads the file itself here, so a value containing spaces or '#' survives.
set -euo pipefail
cd "$(dirname "$0")"
exec node --env-file=../.env server-spectrum.js
