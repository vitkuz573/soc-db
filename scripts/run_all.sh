#!/usr/bin/env bash
# Run all SoC scrapers sequentially
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$DIR/.."

echo "=== SOC-DB Scraper Suite ==="
echo ""

# Restore original carefully-curated data
cd "$ROOT"
git checkout -- data/*.json 2>/dev/null || true

# List all vendors
VENDORS=(
    Qualcomm MediaTek Samsung HiSilicon Google
    Rockchip Allwinner Amlogic Nvidia "TI OMAP" "Intel Atom" Ingenic "NXP i.MX"
)

echo "--- Wikipedia scraper ---"
python3 "$DIR/scraper_wikipedia.py" "${VENDORS[@]}"
echo ""

echo "--- Apple Silicon scraper ---"
python3 "$DIR/scraper_apple.py"
echo ""

echo "=== Validating ==="
python3 "$ROOT/tests/validate.py"
