#!/usr/bin/env python3
"""
Generate two synthetic cash-ledger feeds (internal vs external) for an
in-memory reconciliation demo.

Design: a typical cash rec keyed on  value_date + amount + reference (+ currency).
We inject realistic scenarios so the matcher has something to find:

  CLEAN            - identical on both sides (the bulk)
  ROUNDING         - amount differs by <=0.01 (float/rounding noise -> tolerance)
  TIMING           - same payment, value_date off by 1 business day
  INTERNAL_ONLY    - in our ledger, missing externally (unpresented / error)
  EXTERNAL_ONLY    - on the statement, missing internally (missed booking / fee)
  DUP_INTERNAL     - our side sent the same item twice (phantom-break risk)

Scale is controlled by --rows (number of CLEAN pairs). ~9.3M pairs ≈ 2 GB total
across the two CSVs. Use a smaller number to test quickly.
"""
import csv, random, argparse, datetime, os

def gen(rows, out_dir, seed=42):
    random.seed(seed)
    os.makedirs(out_dir, exist_ok=True)
    ccys = ["GBP","USD","EUR","JPY","CHF"]
    base = datetime.date(2025, 1, 6)

    int_path = os.path.join(out_dir, "internal_ledger.csv")
    ext_path = os.path.join(out_dir, "external_feed.csv")

    fi = open(int_path, "w", newline="")
    fe = open(ext_path, "w", newline="")
    wi = csv.writer(fi); we = csv.writer(fe)
    # NOTE: deliberately messy headers (spaces / mixed case) so the script must clean them
    wi.writerow([" Internal_ID ","Value Date","Amount","Currency","Reference"," Counterparty "])
    we.writerow(["External_ID"," value date ","AMOUNT","currency"," reference ","Counterparty"])

    iid = 0; eid = 0
    ref_seq = [0]
    def next_ref():
        ref_seq[0] += 1
        return f"REF{ref_seq[0]:010d}"
    def rdate():
        return (base + datetime.timedelta(days=random.randint(0, 250)))
    def ramt():
        # mix of round numbers (collision-prone) and precise amounts
        if random.random() < 0.3:
            return round(random.choice([100,250,500,1000,5000,10000]) * 1.0, 2)
        return round(random.uniform(10, 250000), 2)

    # scenario proportions relative to CLEAN count
    n_clean = rows
    n_round = max(1, rows // 50)
    n_timing = max(1, rows // 50)
    n_int_only = max(1, rows // 40)
    n_ext_only = max(1, rows // 40)
    n_dup = max(1, rows // 100)

    def write_int(d, amt, ccy, ref, cp):
        nonlocal iid; iid += 1
        wi.writerow([f"I{iid:09d}", d.isoformat(), f"{amt:.2f}", ccy, ref, cp]); return iid
    def write_ext(d, amt, ccy, ref, cp):
        nonlocal eid; eid += 1
        we.writerow([f"E{eid:09d}", d.isoformat(), f"{amt:.2f}", ccy, ref, cp]); return eid

    for _ in range(n_clean):
        d=rdate(); amt=ramt(); ccy=random.choice(ccys)
        ref=next_ref(); cp=f"CP{random.randint(1,500):04d}"
        write_int(d,amt,ccy,ref,cp); write_ext(d,amt,ccy,ref,cp)

    for _ in range(n_round):
        d=rdate(); amt=ramt(); ccy=random.choice(ccys)
        ref=next_ref(); cp=f"CP{random.randint(1,500):04d}"
        write_int(d,amt,ccy,ref,cp); write_ext(d, round(amt+0.01,2), ccy, ref, cp)

    for _ in range(n_timing):
        d=rdate(); amt=ramt(); ccy=random.choice(ccys)
        ref=next_ref(); cp=f"CP{random.randint(1,500):04d}"
        write_int(d,amt,ccy,ref,cp); write_ext(d+datetime.timedelta(days=1), amt, ccy, ref, cp)

    for _ in range(n_int_only):
        d=rdate(); amt=ramt(); ccy=random.choice(ccys)
        ref=next_ref(); cp=f"CP{random.randint(1,500):04d}"
        write_int(d,amt,ccy,ref,cp)

    for _ in range(n_ext_only):
        d=rdate(); amt=ramt(); ccy=random.choice(ccys)
        ref=next_ref(); cp=f"CP{random.randint(1,500):04d}"
        write_ext(d,amt,ccy,ref,cp)

    for _ in range(n_dup):
        d=rdate(); amt=ramt(); ccy=random.choice(ccys)
        ref=next_ref(); cp=f"CP{random.randint(1,500):04d}"
        write_int(d,amt,ccy,ref,cp); write_int(d,amt,ccy,ref,cp)  # twice our side
        write_ext(d,amt,ccy,ref,cp)                                # once their side

    fi.close(); fe.close()
    si = os.path.getsize(int_path)/1e6; se = os.path.getsize(ext_path)/1e6
    print(f"internal rows={iid}  ({si:.1f} MB)")
    print(f"external rows={eid}  ({se:.1f} MB)")
    print(f"total ~{si+se:.1f} MB")
    print("ground-truth injected:",
          dict(clean=n_clean, rounding=n_round, timing=n_timing,
               internal_only=n_int_only, external_only=n_ext_only, dup_internal=n_dup))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200_000,
                    help="number of CLEAN pairs; ~9.3M ≈ 2GB total")
    ap.add_argument("--out", default="./data")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    gen(a.rows, a.out, a.seed)
