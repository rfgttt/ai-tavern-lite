#!/usr/bin/env sh
set -eu
if [ "$#" -lt 3 ]; then
  echo "Usage: $0 BASE_URL USERNAME PASSWORD [--test-rate-limit]" >&2
  exit 2
fi
BASE_URL=$1
USERNAME=$2
PASSWORD=$3
shift 3
exec python3 scripts/test_p0_security.py --base-url "$BASE_URL" --username "$USERNAME" --password "$PASSWORD" "$@"
