#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

printf '\nAutoGrid Alpaca connection test\n'
printf 'The key is used only in this terminal process and is cleared when finished.\n\n'

if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3.11 or newer is required: https://www.python.org/downloads/\n' >&2
  exit 1
fi

read -r -p 'Paste ALPACA API Key ID: ' ALPACA_API_KEY_ID
read -r -s -p 'Paste ALPACA Secret Key (input is hidden): ' ALPACA_API_SECRET_KEY
printf '\n'
export ALPACA_API_KEY_ID ALPACA_API_SECRET_KEY
trap 'unset ALPACA_API_KEY_ID ALPACA_API_SECRET_KEY' EXIT

python3 -m pip install -e .

end_date="$(date -u -v-1d +%Y-%m-%d 2>/dev/null || date -u -d 'yesterday' +%Y-%m-%d)"
start_date="$(date -u -v-14d +%Y-%m-%d 2>/dev/null || date -u -d '14 days ago' +%Y-%m-%d)"

python3 -m autogrid.cli download-alpaca \
  --output data/alpaca_connection_test.csv \
  --start "$start_date" \
  --end "$end_date" \
  --symbols SPY,QQQ,GLD,SLV,IBIT,BITI,BITX \
  --feed sip

printf '\nSUCCESS: Alpaca connection and SIP sample download completed.\n'
printf 'Created: %s/data/alpaca_connection_test.csv\n' "$project_root"
printf 'Tell ChatGPT only: connection successful. Never send the keys.\n'
