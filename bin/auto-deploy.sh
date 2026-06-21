#!/bin/bash
# auto-deploy.sh — run pipeline and push updates to GitHub
# Can be triggered by cron or systemd timer.
#
# Usage:
#   ./bin/auto-deploy.sh              # Full pipeline
#   ./bin/auto-deploy.sh --skip-scrape  # Skip scraping (faster)
#
# Set GIT_REMOTE and GIT_BRANCH in the environment to override defaults.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"
LOG_FILE="${LOG_FILE:-/tmp/soc-db-auto-deploy.log}"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] Starting soc-db auto-deploy..." >> "$LOG_FILE"

# 1. Run the pipeline
cd "$REPO_DIR"
if [ "${1:-}" = "--skip-scrape" ]; then
    echo "[$TIMESTAMP] Running pipeline (skip scrape)..." >> "$LOG_FILE"
    python3 scripts/pipeline.py --skip-scrape >> "$LOG_FILE" 2>&1
else
    echo "[$TIMESTAMP] Running full pipeline..." >> "$LOG_FILE"
    python3 scripts/pipeline.py >> "$LOG_FILE" 2>&1
fi

# 2. Commit and push if there are changes
cd "$REPO_DIR"
if git diff --quiet && git diff --cached --quiet; then
    echo "[$TIMESTAMP] No changes to commit." >> "$LOG_FILE"
else
    git add -A
    git commit -m "auto-deploy: $(date '+%Y-%m-%d %H:%M')" >> "$LOG_FILE" 2>&1
    echo "[$TIMESTAMP] Pushing to $GIT_REMOTE/$GIT_BRANCH..." >> "$LOG_FILE"
    git push "$GIT_REMOTE" "$GIT_BRANCH" >> "$LOG_FILE" 2>&1
    echo "[$TIMESTAMP] Push complete." >> "$LOG_FILE"
fi

echo "[$TIMESTAMP] Auto-deploy finished." >> "$LOG_FILE"
