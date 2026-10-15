#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec sh "$ROOT/scripts/python.sh" "$ROOT/scripts/session_organizer.py"
