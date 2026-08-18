#!/usr/bin/env bash
# ============================================================================
# run_recon.sh — the entry point a scheduler (cron / launchd) calls.
#
# It: picks up today's feeds, writes results into a DATED output folder,
# tees all console output to a log, and exits non-zero on failure so the
# scheduler can alert. A durable status_history.csv accumulates one row per run.
#
# Configure the three paths below (or pass them as env vars), then schedule it.
# ============================================================================
set -euo pipefail

# --- configuration (edit these, or override with env vars) ------------------
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")" && pwd)}"   # where this script lives
FEED_DIR="${FEED_DIR:-$REPO_DIR/data}"                   # where today's CSVs land
OUT_ROOT="${OUT_ROOT:-$REPO_DIR/runs}"                   # where results go
PYTHON="${PYTHON:-python3}"                              # or the venv's python
TOLERANCE="${TOLERANCE:-0.01}"

# --- derived ----------------------------------------------------------------
RUN_DATE="$(date +%Y-%m-%d)"
OUT_DIR="$OUT_ROOT/$RUN_DATE"
LOG_DIR="$OUT_ROOT/logs"
mkdir -p "$OUT_DIR" "$LOG_DIR"
LOG="$LOG_DIR/recon_${RUN_DATE}.log"

INTERNAL="$FEED_DIR/internal_ledger.csv"
EXTERNAL="$FEED_DIR/external_feed.csv"

echo "==== cash recon run $(date -u +%FT%TZ) ====" | tee -a "$LOG"

# --- pre-flight: feeds present? --------------------------------------------
if [[ ! -f "$INTERNAL" || ! -f "$EXTERNAL" ]]; then
  echo "ERROR: feed(s) missing. Expected:" | tee -a "$LOG"
  echo "  $INTERNAL" | tee -a "$LOG"
  echo "  $EXTERNAL" | tee -a "$LOG"
  exit 2
fi

# --- run --------------------------------------------------------------------
cd "$REPO_DIR"
if "$PYTHON" reconcile.py \
      --internal "$INTERNAL" \
      --external "$EXTERNAL" \
      --out "$OUT_DIR" \
      --tolerance "$TOLERANCE" 2>&1 | tee -a "$LOG"; then
  echo "OK: recon complete. Results in $OUT_DIR" | tee -a "$LOG"
  # keep a single rolling status history at the root of OUT_ROOT
  if [[ -f "$OUT_DIR/status_history.csv" ]]; then
    cp "$OUT_DIR/status_history.csv" "$OUT_ROOT/status_history.csv"
  fi
  exit 0
else
  echo "ERROR: recon failed — see $LOG" | tee -a "$LOG"
  exit 1
fi
