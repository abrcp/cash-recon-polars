"""
Correctness tests for the in-memory cash reconciliation.

Run:  pytest -q
These regenerate a small deterministic dataset and assert the reconciliation
output ties exactly to the injected ground truth.
"""
import os, tempfile, shutil
import generate_feeds as G
import reconcile as R


def _build(tmp, rows=20_000):
    G.gen(rows, tmp, seed=42)
    return os.path.join(tmp, "internal_ledger.csv"), os.path.join(tmp, "external_feed.csv")


def test_counts_tie_to_ground_truth():
    tmp = tempfile.mkdtemp()
    out = tempfile.mkdtemp()
    try:
        rows = 20_000
        i, e = _build(tmp, rows)
        stats = R.reconcile(i, e, out)
        sc = stats["status_counts"]

        n_round = max(1, rows // 50)     # 400
        n_timing = max(1, rows // 50)    # 400
        n_int = max(1, rows // 40)       # 500
        n_ext = max(1, rows // 40)       # 500
        n_dup = max(1, rows // 100)      # 200

        # MATCHED = clean + duplicate pairs (2 internal copies each match the 1 external)
        assert sc["MATCHED"] == rows + 2 * n_dup
        # one-sided = own-only + rounding side + timing side
        assert sc["INTERNAL_ONLY"] == n_int + n_round + n_timing
        assert sc["EXTERNAL_ONLY"] == n_ext + n_round + n_timing
        # every rounding pair is a near-miss within tolerance
        assert sc["NEAR_MISS_WITHIN_TOL"] == n_round
        # duplicate groups detected
        assert sc["DUPLICATE_INTERNAL_GROUPS"] == n_dup
    finally:
        shutil.rmtree(tmp); shutil.rmtree(out)


def test_outputs_written():
    tmp = tempfile.mkdtemp(); out = tempfile.mkdtemp()
    try:
        i, e = _build(tmp, 20_000)
        R.reconcile(i, e, out)
        for f in ("breaks.csv", "near_misses.csv", "duplicates_internal.csv", "run_stats.json"):
            assert os.path.exists(os.path.join(out, f)), f"missing {f}"
    finally:
        shutil.rmtree(tmp); shutil.rmtree(out)


def test_no_cartesian_explosion():
    # result rows must be bounded (matched + both one-sided), never a blow-up
    tmp = tempfile.mkdtemp(); out = tempfile.mkdtemp()
    try:
        rows = 20_000
        i, e = _build(tmp, rows)
        stats = R.reconcile(i, e, out)
        # with a reference in the key, result rows stay close to max(side sizes)
        assert stats["result_rows"] < stats["internal_rows"] + stats["external_rows"]
    finally:
        shutil.rmtree(tmp); shutil.rmtree(out)
