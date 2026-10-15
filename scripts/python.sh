#!/bin/sh
# Resolve Python rather than assuming Apple's developer tools are installed.
set -eu
for candidate in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        exec "$candidate" "$@"
    fi
done
printf '%s\n' 'codex-session-organizer: Python 3.9+ is required. Install Python and restart Codex.' >&2
exit 1
