# Deploy & Schedule — Step by Step

Three parts: **(A)** publish to GitHub from scratch, **(B)** run it on a schedule
every day, **(C)** read the status summary. At the end there's a short **"how I'd
describe enterprise prod"** section for the interview.

This matches the honest scope: this is a batch Python job, so "prod" means *a
version-controlled repo plus a reliable scheduled run with logging and a status
trail* — not Kubernetes.

---

## Part A — Publish to GitHub (assuming you've never used git)

### A1. One-time setup on your Mac

Git ships with macOS. Check and set your identity:

```bash
git --version                     # if it prompts to install Xcode tools, accept
git config --global user.name  "Abdul Rahim"
git config --global user.email "your-github-email@example.com"
```

### A2. Create the GitHub account & an empty repo

1. Sign up / log in at **github.com**.
2. Click the **+** (top right) → **New repository**.
3. Name it e.g. `cash-recon-polars`. Choose **Private** (safer to share by invite)
   or **Public**. **Do NOT** tick "Add a README" (you already have one).
4. Click **Create repository**. Leave that page open — you'll copy the URL from it.

### A3. Authentication — set up a Personal Access Token (once)

GitHub no longer accepts your password on the command line. Create a token:

1. github.com → your avatar → **Settings** → **Developer settings** (bottom left)
   → **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**.
2. Note: "cli", Expiration: 90 days, tick the **repo** scope. Generate, then
   **copy the token** (you won't see it again).
3. When git later asks for a **password**, paste this **token** instead. macOS
   Keychain will remember it after the first push.

### A4. Turn your project folder into a repo and push

In Terminal, go to the folder with the code (the unzipped kit):

```bash
cd ~/Downloads/cash_rec_polars_kit        # wherever the files are

git init                                   # start version control here
git add .                                  # stage all files
git commit -m "Initial commit: in-memory cash reconciliation (Polars)"

git branch -M main                         # name the branch 'main'
git remote add origin https://github.com/YOUR_USERNAME/cash-recon-polars.git
git push -u origin main                    # username = your GitHub name,
                                           # password = the token from A3
```

Refresh the GitHub page — your files are there. **Done — it's published.**

The included `.gitignore` keeps generated data and run outputs out of the repo, so
only source is versioned (which is correct).

### A5. Making changes later (the everyday loop)

```bash
# edit a file, then:
git add -A
git commit -m "describe what changed"
git push
```

### A6. (Optional) Tag a release so a reviewer gets a clean version

```bash
git tag -a v1.0 -m "First shareable version"
git push origin v1.0
```
On GitHub → **Releases** → **Draft a new release** → pick tag `v1.0` → publish.
Share that release link with the interviewer.

---

## Part B — Run it on a schedule (the "deploy" for a batch job)

The wrapper `run_recon.sh` is what the scheduler calls. It expects the day's feeds
at `data/internal_ledger.csv` and `data/external_feed.csv`, writes results into a
**dated** folder `runs/YYYY-MM-DD/`, logs to `runs/logs/`, and appends one line to
`runs/status_history.csv`. It exits non-zero on failure so the scheduler can alert.

### B0. First, prove it runs by hand

```bash
cd ~/Downloads/cash_rec_polars_kit
pip install -r requirements.txt
python generate_feeds.py --rows 100000 --out data     # stand-in for real feeds
chmod +x run_recon.sh
./run_recon.sh                                         # should end with "OK: recon complete"
cat runs/status_history.csv                            # one row appeared
```

For real use you'd replace the `generate_feeds.py` step with your actual feed
delivery dropping the two CSVs into `data/` (or point `FEED_DIR` at wherever they
land).

### B1. Schedule on macOS — launchd (recommended on Mac)

macOS prefers **launchd** over cron. Create a job file:

```bash
mkdir -p ~/Library/LaunchAgents
nano ~/Library/LaunchAgents/com.abdul.cashrecon.plist
```

Paste this (edit the two paths and the hour/minute — this example runs 06:30 daily):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.abdul.cashrecon</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/ayaansh/Downloads/cash_rec_polars_kit/run_recon.sh</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>REPO_DIR</key><string>/Users/ayaansh/Downloads/cash_rec_polars_kit</string>
    <key>PYTHON</key><string>/usr/bin/python3</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>6</integer>
    <key>Minute</key><integer>30</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/ayaansh/Downloads/cash_rec_polars_kit/runs/logs/launchd.out</string>
  <key>StandardErrorPath</key>
  <string>/Users/ayaansh/Downloads/cash_rec_polars_kit/runs/logs/launchd.err</string>
</dict>
</plist>
```

Load and test it:

```bash
launchctl load ~/Library/LaunchAgents/com.abdul.cashrecon.plist   # register it
launchctl start com.abdul.cashrecon                               # run once now to test
cat runs/logs/recon_$(date +%Y-%m-%d).log                        # check it worked
```

Manage it later:
```bash
launchctl list | grep cashrecon         # is it registered?
launchctl unload ~/Library/LaunchAgents/com.abdul.cashrecon.plist   # stop scheduling
```

### B2. Schedule on Linux (or WSL) — cron

```bash
crontab -e            # opens your crontab in an editor
```
Add one line (runs 06:30 daily; adjust the path):
```
30 6 * * *  REPO_DIR=/home/USER/cash_rec_polars_kit /home/USER/cash_rec_polars_kit/run_recon.sh >> /home/USER/cash_rec_polars_kit/runs/logs/cron.log 2>&1
```
Cron fields are `minute hour day month weekday`. Save and exit. Check it's there
with `crontab -l`.

### B3. Using a virtualenv (recommended)

If you installed deps in a venv, point the scheduler at that Python so it finds
Polars. In the launchd plist set `PYTHON` to
`/Users/ayaansh/Downloads/cash_rec_polars_kit/.venv/bin/python`, or in cron prefix
the line with `PYTHON=/home/USER/cash_rec_polars_kit/.venv/bin/python`.

---

## Part C — The status summary

Every run produces, in `runs/YYYY-MM-DD/`:

- **console output** — the human-readable block (matched / internal-only /
  external-only / near-miss / duplicates, plus match-collect and total runtime).
- **`run_stats.json`** — the same numbers as JSON (for dashboards / programmatic use).
- **`breaks.csv`, `near_misses.csv`, `duplicates_internal.csv`** — the actual
  exceptions to work.

And at the root, **`runs/status_history.csv`** accumulates **one row per run** —
your at-a-glance trend of matched vs breaks vs runtime over time. Example:

```
run_ts,internal_rows,external_rows,matched,internal_only,external_only,near_miss,dup_groups,total_seconds
2026-08-18T06:30:04,2170000,2170000,2040000,130000,130000,40000,20000,13.4
2026-08-19T06:30:05,2180000,2175000,2050000,131000,129000,41000,20500,13.6
```

Quick ways to read it:
```bash
column -s, -t runs/status_history.csv | less -S     # pretty table in the terminal
tail -5 runs/status_history.csv                     # the last five runs
```

If you want the JSON from the latest run:
```bash
cat runs/$(date +%Y-%m-%d)/run_stats.json
```

---

## How I'd describe *enterprise* prod (interview talking point)

Be explicit that the above is the honest scope for a batch script, then show you
know what a real production deployment adds:

- **Source control & CI:** the repo triggers **GitHub Actions** on every push —
  run `pytest`, lint, and build — so nothing merges that fails the tests.
- **Packaging:** containerise with a small **Dockerfile** (Python + Polars) so the
  runtime is identical everywhere; publish the image to a registry.
- **Orchestration:** schedule with an enterprise scheduler (**Airflow / Control-M /
  Autosys**) rather than cron, with dependency gates ("all feeds arrived before the
  match runs"), retries, and SLA alerts.
- **Config & secrets:** externalise feed paths, tolerances and the matching key to
  config; no credentials in the repo.
- **Observability:** ship `run_stats.json` to a metrics/dashboard stack, alert on
  match-rate deltas or break-volume spikes, and page on a non-zero exit.
- **Controls:** a persisted audit trail of each run and its breaks, maker-checker
  sign-off, and retention — the same discipline as the IntelliMatch release process
  (GitHub → package → dress-rehearse in pre-prod → Jira sign-off → deploy → rollback).

Line to say: *"For a script this size, 'prod' honestly means a versioned repo and a
reliable scheduled run with logging, a status trail, and non-zero-exit alerting.
The moment it becomes a real control, I'd add CI, containerisation, an enterprise
scheduler with feed-dependency gates, and monitoring — but I wouldn't over-engineer
a batch job that runs once a day."*
