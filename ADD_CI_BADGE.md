# Adding the CI "tests passing" badge — step by step

This makes GitHub run your `pytest` suite automatically on every push and show a
green **tests · passing** badge at the top of your repo. It's the detail that
signals "properly engineered" to a Head of Technology.

## What's included
- `.github/workflows/tests.yml` — the workflow. **The folder path matters**: it must
  sit at `.github/workflows/tests.yml` inside your repo, exactly.
- The README now has a badge line near the top that points at your Actions.

## Step 1 — put the files in place

If you unzipped this kit fresh, the `.github/workflows/tests.yml` path is already
correct — just copy the `.github` folder and the updated `README.md` into your repo
folder (`~/Downloads/cash_rec_polars_kit`), overwriting the old README.

To check the hidden `.github` folder copied across:
```bash
cd ~/Downloads/cash_rec_polars_kit
ls -la .github/workflows/          # should list tests.yml
```
(`.github` starts with a dot, so it's hidden in Finder — `ls -la` reveals it.)

## Step 2 — commit and push

```bash
cd ~/Downloads/cash_rec_polars_kit
git add -A
git commit -m "Add GitHub Actions CI (pytest) and status badge"
git push
```

## Step 3 — watch it run

1. Go to `https://github.com/abrcp/cash-recon-polars/actions`.
2. You'll see a workflow run called **"Add GitHub Actions CI…"** with a spinning
   amber dot. It installs Polars + pytest and runs your tests on Python 3.11 and
   3.12.
3. After ~1–2 minutes it turns into a **green tick**. The badge at the top of your
   README (on the repo home page) then shows **tests · passing**.

## If the badge shows the wrong account
The badge URL in `README.md` is hard-coded to `abrcp`. Since you pushed to
`github.com/abrcp/cash-recon-polars`, it's already correct. If you ever move the
repo to a different account/name, edit the two `abrcp/cash-recon-polars` strings in
the badge line at the top of `README.md` to match.

## If the run goes red (fails)
Click the failed run → the **test** job → expand **Run tests** to see the error.
The tests pass cleanly here, so a red run almost always means a file didn't get
committed — check that `reconcile.py`, `generate_feeds.py`, `test_reconcile.py` and
`requirements.txt` are all in the repo (`git ls-files` lists what's tracked).

## What the workflow does (so you can explain it)
On every push or pull request to `main`, GitHub spins up a clean Ubuntu machine,
installs Python, installs your `requirements.txt`, and runs `pytest -q`. It runs on
two Python versions (3.11 and 3.12) to prove the code isn't tied to one. A green
badge = the reconciliation's correctness tests pass on a fresh machine, which is
exactly the assurance a reviewer wants before trusting the code.
