#!/usr/bin/env python3
"""
In-memory cash reconciliation with Polars — internal ledger vs external feed.

WHY POLARS (the interview answer):
  * True in-memory columnar processing on the Apache Arrow layout — no database
    engine touched. 2 GB fits comfortably in a laptop's RAM.
  * Lazy execution (scan_csv) lets the query optimiser push down projections and
    predicates and stream the join, so we never materialise more than we need.
  * Vectorised — no per-row Python iteration — so a 2 GB rec runs in seconds, not
    minutes.

WHAT THIS FIXES vs a naive full-outer-join script:
  1. COALESCED keys (coalesce=True) so external-only rows keep their key values
     after the join (the classic silent bug).
  2. A REFERENCE in the matching key (not just amount+date) to stop a Cartesian
     explosion where thousands of same-amount/same-date payments cross-match.
  3. AMOUNT ROUNDING applied in-pipeline (float-safety) + an optional tolerance
     pass for near-misses.
  4. DUPLICATE detection on the internal side (phantom-break control).
  5. Full break accounting: matched / internal-only / external-only / near-miss.
  6. Runtime + memory instrumentation, and results written to an output folder.

Usage:
    python reconcile.py --internal data/internal_ledger.csv \
                        --external data/external_feed.csv \
                        --out out --tolerance 0.01

The reconciliation key and tolerance are CLI-configurable so you can demo the
"what makes two records the same?" conversation live.
"""
import argparse, time, os, json, sys
import polars as pl


def clean_headers(df: pl.LazyFrame) -> pl.LazyFrame:
    # strip spaces, lowercase, collapse internal spaces to underscores
    return df.rename({c: c.strip().lower().replace(" ", "_") for c in df.collect_schema().names()})


def reconcile(internal_path, external_path, out_dir,
              key=("value_date", "amount", "reference", "currency"),
              tolerance=0.01, amount_dp=2):
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.perf_counter()
    timings = {}

    # ---- 1. LAZY scan (no data read yet) -----------------------------------
    # scan_csv builds a query plan; nothing is loaded until .collect().
    internal = clean_headers(pl.scan_csv(internal_path, infer_schema_length=10_000))
    external = clean_headers(pl.scan_csv(external_path, infer_schema_length=10_000))

    # ---- 2. Normalise both sides to a common shape -------------------------
    def prep(lf, id_col, src):
        return (
            lf.rename({id_col: "row_id"})
              .with_columns([
                  pl.col("value_date").cast(pl.Utf8).str.strptime(pl.Date, "%Y-%m-%d", strict=False),
                  pl.col("amount").cast(pl.Float64).round(amount_dp),   # float-safety in-pipeline
                  pl.col("currency").cast(pl.Utf8).str.to_uppercase().str.strip_chars(),
                  pl.col("reference").cast(pl.Utf8).str.strip_chars(),
                  pl.lit(src).alias("source"),
              ])
        )

    internal = prep(internal, "internal_id", "INTERNAL")
    external = prep(external, "external_id", "EXTERNAL")

    # ---- 3. Duplicate control on our side ----------------------------------
    # Count occurrences of the full key on the internal side; >1 = phantom-break risk.
    dup_lf = (
        internal.group_by(list(key))
                .agg(pl.len().alias("n"))
                .filter(pl.col("n") > 1)
    )

    # ---- 4. PASS 1: exact match on the full economic key -------------------
    # coalesce=True keeps a single key column populated from whichever side is present
    # (this is the fix for external-only rows losing their key values).
    matched = (
        internal.join(external, on=list(key), how="full", coalesce=True, suffix="_ext")
    )

    # Status: MATCHED where both row_ids present; else one-sided.
    matched = matched.with_columns(
        pl.when(pl.col("row_id").is_not_null() & pl.col("row_id_ext").is_not_null())
          .then(pl.lit("MATCHED"))
          .when(pl.col("row_id_ext").is_null())
          .then(pl.lit("INTERNAL_ONLY"))
          .otherwise(pl.lit("EXTERNAL_ONLY"))
          .alias("recon_status")
    )

    # ---- 5. Collect (this is where the work actually happens) --------------
    t1 = time.perf_counter()
    result = matched.collect(engine="streaming")      # streaming lets Polars spill if RAM is tight
    timings["match_collect_s"] = round(time.perf_counter() - t1, 3)

    dup = dup_lf.collect(engine="streaming")
    n_dup_groups = dup.height

    # ---- 6. PASS 2 (optional): tolerance / near-miss on the residual -------
    # Take internal-only and external-only, join on the key WITHOUT amount, and
    # keep pairs whose amounts differ but within tolerance -> near-miss breaks.
    near_key = [k for k in key if k != "amount"]
    int_resid = result.filter(pl.col("recon_status") == "INTERNAL_ONLY").select(
        [pl.col(k) for k in near_key] + [pl.col("amount"), pl.col("row_id")]
    )
    ext_resid = result.filter(pl.col("recon_status") == "EXTERNAL_ONLY").select(
        [pl.col(k) for k in near_key] + [pl.col("amount").alias("amount_ext"),
                                         pl.col("row_id_ext")]
    )
    if int_resid.height and ext_resid.height and near_key:
        near = (
            int_resid.join(ext_resid, on=near_key, how="inner")
                     # round the diff to amount_dp so float representation error
                     # (e.g. 0.01 stored as 0.010000000001) doesn't wrongly fail the
                     # tolerance test — this is the real float-safety fix.
                     .with_columns(
                         (pl.col("amount") - pl.col("amount_ext")).abs().round(amount_dp).alias("amt_diff")
                     )
                     .filter((pl.col("amt_diff") > 0) & (pl.col("amt_diff") <= tolerance))
        )
    else:
        near = pl.DataFrame()
    n_near = near.height

    timings["total_s"] = round(time.perf_counter() - t0, 3)

    # ---- 7. Summary + outputs ---------------------------------------------
    summary = (result.group_by("recon_status").len()
                     .sort("len", descending=True))
    status_counts = {r["recon_status"]: r["len"] for r in summary.to_dicts()}
    # near-misses are a refinement of the one-sided populations
    status_counts["NEAR_MISS_WITHIN_TOL"] = n_near
    status_counts["DUPLICATE_INTERNAL_GROUPS"] = n_dup_groups

    breaks = result.filter(pl.col("recon_status") != "MATCHED")
    breaks.write_csv(os.path.join(out_dir, "breaks.csv"))
    if n_near:
        near.write_csv(os.path.join(out_dir, "near_misses.csv"))
    if n_dup_groups:
        dup.write_csv(os.path.join(out_dir, "duplicates_internal.csv"))

    stats = {
        "internal_rows": int(result.filter(pl.col("row_id").is_not_null()).height),
        "external_rows": int(result.filter(pl.col("row_id_ext").is_not_null()).height),
        "result_rows": int(result.height),
        "status_counts": status_counts,
        "matching_key": list(key),
        "tolerance": tolerance,
        "timings_seconds": timings,
        "polars_version": pl.__version__,
    }
    with open(os.path.join(out_dir, "run_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    # ---- append a one-line status record to a durable history file ---------
    # This is the "status summary" a scheduled job accumulates over time.
    import csv, datetime
    hist_path = os.path.join(out_dir, "status_history.csv")
    hist_exists = os.path.exists(hist_path)
    with open(hist_path, "a", newline="") as f:
        w = csv.writer(f)
        if not hist_exists:
            w.writerow(["run_ts", "internal_rows", "external_rows", "matched",
                        "internal_only", "external_only", "near_miss", "dup_groups",
                        "total_seconds"])
        w.writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            stats["internal_rows"], stats["external_rows"],
            status_counts.get("MATCHED", 0),
            status_counts.get("INTERNAL_ONLY", 0),
            status_counts.get("EXTERNAL_ONLY", 0),
            status_counts.get("NEAR_MISS_WITHIN_TOL", 0),
            status_counts.get("DUPLICATE_INTERNAL_GROUPS", 0),
            timings.get("total_s", ""),
        ])

    # ---- 8. Print a human-readable report ---------------------------------
    print("\n" + "="*60)
    print(" CASH RECONCILIATION — IN-MEMORY (Polars)")
    print("="*60)
    print(f" Matching key : {' + '.join(key)}")
    print(f" Tolerance    : {tolerance}")
    print(f" Internal rows: {stats['internal_rows']:,}")
    print(f" External rows: {stats['external_rows']:,}")
    print("-"*60)
    for k, v in status_counts.items():
        print(f"   {k:<28} {v:>12,}")
    print("-"*60)
    print(f" Match collect : {timings['match_collect_s']}s")
    print(f" TOTAL runtime : {timings['total_s']}s")
    print("="*60)
    print(f" Outputs written to: {out_dir}/  (breaks.csv, near_misses.csv,")
    print(f"                     duplicates_internal.csv, run_stats.json)")
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="In-memory cash reconciliation (Polars).")
    ap.add_argument("--internal", required=True)
    ap.add_argument("--external", required=True)
    ap.add_argument("--out", default="out")
    ap.add_argument("--key", default="value_date,amount,reference,currency",
                    help="comma-separated matching key columns")
    ap.add_argument("--tolerance", type=float, default=0.01)
    ap.add_argument("--amount-dp", type=int, default=2)
    a = ap.parse_args()
    reconcile(a.internal, a.external, a.out,
              key=tuple(k.strip() for k in a.key.split(",")),
              tolerance=a.tolerance, amount_dp=a.amount_dp)
