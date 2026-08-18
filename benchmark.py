#!/usr/bin/env python3
"""
Benchmark the in-memory cash reconciliation: captures wall-clock runtime and
peak RSS memory, so you can quote real numbers.

Usage:
    python benchmark.py --internal data/internal_ledger.csv \
                        --external data/external_feed.csv
"""
import argparse, time, os, resource, platform, json
import reconcile as R

def peak_rss_mb():
    # ru_maxrss is KB on Linux, bytes on macOS
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r/1024 if platform.system() == "Linux" else r/1024/1024

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--internal", required=True)
    ap.add_argument("--external", required=True)
    ap.add_argument("--out", default="out")
    ap.add_argument("--tolerance", type=float, default=0.01)
    a = ap.parse_args()

    in_mb = os.path.getsize(a.internal)/1e6
    ex_mb = os.path.getsize(a.external)/1e6

    t0 = time.perf_counter()
    stats = R.reconcile(a.internal, a.external, a.out, tolerance=a.tolerance)
    wall = time.perf_counter() - t0

    bench = {
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "input_mb": round(in_mb + ex_mb, 1),
        "internal_mb": round(in_mb, 1),
        "external_mb": round(ex_mb, 1),
        "wall_seconds": round(wall, 3),
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "rows_per_second": round((stats["internal_rows"] + stats["external_rows"]) / wall),
        "status_counts": stats["status_counts"],
    }
    print("\n" + "#"*60)
    print(" BENCHMARK")
    print("#"*60)
    print(json.dumps(bench, indent=2))
    with open(os.path.join(a.out, "benchmark.json"), "w") as f:
        json.dump(bench, f, indent=2)
    print(f"\nSaved to {a.out}/benchmark.json")
