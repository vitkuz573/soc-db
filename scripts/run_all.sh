#!/usr/bin/env bash
# Run all SoC scrapers sequentially
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== SOC-DB Scraper Suite ==="
echo ""

ROOT="$DIR/.."

# First restore original manual data
echo "--- Restoring original manual data ---"
cd "$ROOT"
git checkout -- data/qualcomm.json data/mediatek.json data/exynos.json \
                 data/kirin.json data/tensor.json data/apple.json 2>/dev/null || true
echo "  Done"
echo ""

# Run unified Wikipedia scraper (all vendors except Apple, which uses a different page structure)
echo "--- Wikipedia scraper ---"
python3 "$DIR/scraper_wikipedia.py" Qualcomm MediaTek Samsung HiSilicon Google
echo ""

# Run Apple-specific scraper
echo "--- Apple Silicon scraper ---"
python3 "$DIR/scraper_apple.py"
echo ""

# Validate
echo "=== Validating ==="
python3 "$ROOT/tests/validate.py"
