# In-Memory Cash Reconciliation (Polars)

[![tests](https://github.com/abrcp/cash-recon-polars/actions/workflows/tests.yml/badge.svg)](https://github.com/abrcp/cash-recon-polars/actions/workflows/tests.yml)

A runnable, tested reference implementation of a **cash reconciliation performed
entirely in memory** — internal ledger vs external feed, matched on value date,
amount, reference and currency — with **no database engine involved**. Built with
[Polars](https://pola.rs) on the Apache Arrow columnar layout.

This exists to answer the interview question *"how would you reconcile ~2 GB of
cash data in Python, in memory, and what technology would you use?"* — with code
someone can clone and run straight away.

> Shared for information. The design and numbers below are reproducible from this repo.

---

## Why Polars, in memory (the short answer)

- **True in-memory, columnar.** Polars stores data contiguously in RAM as Apache
  Arrow. No PostgreSQL/SQLite/DuckDB server is started or required.
- **Lazy + vectorised.** `scan_csv` builds a query plan; the optimiser pushes down
  projections/predicates and streams the join. No row-by-row Python iteration, so
  it's fast and memory-lean.
- **Handles the cash-rec realities** that a naive `join` misses: float/rounding
  noise, one-sided breaks, duplicates, and near-misses within tolerance.

---

## Quick start

```bash
# 1. install (a virtualenv is optional but tidy)
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. generate synthetic feeds (start small; ~9.3M rows ≈ 2 GB)
python generate_feeds.py --rows 200000 --out data       # ~25 MB, runs in ~1s
#   for a ~2 GB pair on a laptop with >=12 GB RAM:
#   python generate_feeds.py --rows 9300000 --out data

# 3. run the reconciliation
python reconcile.py --internal data/internal_ledger.csv \
                    --external data/external_feed.csv \
                    --out out

# 4. (optional) run with runtime + peak-memory capture
python benchmark.py --internal data/internal_ledger.csv \
                    --external data/external_feed.csv --out out

# 5. (optional) prove correctness against ground truth
pytest -q
```

Outputs land in `out/`: `breaks.csv`, `near_misses.csv`,
`duplicates_internal.csv`, `run_stats.json`, and (from the benchmark)
`benchmark.json`.

---

## What the matcher does

The reconciliation is a two-pass, side-aware pipeline:

1. **Load lazily** (`scan_csv`) and **clean headers** (the sample feeds have
   deliberately messy headers like `" Value Date "` so the code has to normalise
   them).
2. **Normalise** both sides: parse `value_date` to a real date, cast `amount` to
   float and **round to 2 dp in-pipeline** (float-safety), upper-case/trim
   currency and reference.
3. **Duplicate control**: group the internal side on the full key; any group with
   count > 1 is flagged (a duplicated ledger item creates a phantom break).
4. **Pass 1 — exact match** on `value_date + amount + reference + currency` via a
   **full outer join with `coalesce=True`** so a one-sided row keeps its key
   values (the classic bug this fixes). Rows bucket into `MATCHED`,
   `INTERNAL_ONLY`, `EXTERNAL_ONLY`.
5. **Pass 2 — tolerance / near-miss**: re-join the two one-sided populations on the
   key *minus amount*, and keep pairs whose amounts differ within `--tolerance`
   (default 0.01). These are the rounding breaks you'd auto-explain.
6. **Report + export**: a status summary, break files, and a JSON of stats and
   timings.

The matching key and tolerance are **CLI-configurable** (`--key`, `--tolerance`),
so you can demonstrate the "what makes two records the same?" conversation live.

---

## Measured performance (reproducible)

Run on a constrained **single-core** sandbox (1 vCPU, 3.9 GB RAM, Polars 1.43):

| Input (both files) | Rows/side | Wall time | Peak RAM | Throughput |
|---|---|---|---|---|
| 24.6 MB | 217k | ~1.8 s | 178 MB | ~243k rows/s |
| 246 MB | 2.17M | ~11 s | 1.09 GB | ~394k rows/s |

**Extrapolation to a true 2 GB pair** (~35M rows/side at this row density):
- **Single-core:** ~3 minutes.
- **A typical 4–8 core laptop** runs Polars in parallel, so expect **low tens of
  seconds** — matching the "a few seconds to tens of seconds" claim, honestly
  qualified by core count.
- **Peak RAM** scales roughly linearly: a 2 GB input needs **~8–12 GB RAM**
  comfortably. (The optimistic "2 GB fits in 2–4 GB RAM" is *not* safe once you
  account for join intermediates — plan for headroom, or use the streaming engine.)

Your own numbers will be written to `out/benchmark.json` when you run
`benchmark.py`, so you can quote figures from your actual machine.

---

## Scenarios in the synthetic data (ground truth)

The generator injects, relative to the number of `--rows` (clean pairs):
`CLEAN` (the bulk), `ROUNDING` (amount off by 0.01 → near-miss), `TIMING`
(value date off by 1 day → one-sided on exact key), `INTERNAL_ONLY`,
`EXTERNAL_ONLY`, and `DUP_INTERNAL` (same item twice our side). The test suite
asserts the reconciliation output ties **exactly** to these injected counts.

---

## Honest notes (worth saying in the interview)

- **This is a demo, not a production platform.** A real deployment would add:
  schema validation on ingest, a persisted audit trail, configurable
  match-pass ordering, one-to-many/partial-fill aggregation, and monitoring/alerting.
- **In-memory suits batch EOD recs up to a few GB.** Beyond RAM headroom you'd
  switch to Polars' streaming engine, chunk by date/currency, or move to a
  columnar store (DuckDB) — still no server, but disk-backed.
- **The float-safety fix is real, not cosmetic.** Comparing `abs(a-b) <= 0.01`
  directly *fails* on values like `0.0100000000001`; rounding the diff to the
  amount's dp before the tolerance test is what makes near-miss detection correct.
  (You can see this: without the round, ~1,683 of 4,000 rounding breaks are missed.)
- **A reference in the key is essential.** Matching on amount + date alone
  cross-matches every same-amount/same-date payment — a Cartesian blow-up on 2 GB.

---

## Files

| File | Purpose |
|---|---|
| `reconcile.py` | The reconciliation engine (the thing to read) |
| `generate_feeds.py` | Synthetic feed generator with injected scenarios |
| `benchmark.py` | Runtime + peak-memory harness |
| `test_reconcile.py` | Pytest correctness suite (ties to ground truth) |
| `requirements.txt` | Dependencies |

---

## What was wrong with the "quick" version (for reference)

The common first-draft script (`internal.join(external, on=["value_date","amount"],
how="full")`) has four issues this repo fixes: (1) no `coalesce`, so one-sided rows
lose their key values; (2) amount+date-only key → Cartesian explosion on real
volumes; (3) rounding advised but not applied, and the `<= tol` test then fails on
float representation error; (4) no duplicate handling, tolerance pass, or runtime
capture. The approach was right; the implementation needed hardening.
