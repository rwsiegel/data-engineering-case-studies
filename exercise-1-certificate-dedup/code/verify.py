"""Check a dedup run: every output certificate must be the exact original input line.

Usage:  python verify.py --input FILE[.gz] --out-dir DIR [--sample N]

Structural checks run on every output set. The byte-for-byte comparison against the input runs on
every set when there are N or fewer, otherwise on an evenly spaced sample of N sets (bounded memory).
Exit code 1 if any check fails.
"""
import argparse, collections, gzip, json, os, re, sys

def open_input(path):
    with open(path, "rb") as f:
        magic = f.read(2)
    return gzip.open(path, "rb") if magic == b"\x1f\x8b" else open(path, "rb")

def clean_fp(fp):
    return re.sub(r"[:\s]", "", fp).lower()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--sample", type=int, default=2000)
    a = ap.parse_args()
    audit = json.load(open(os.path.join(a.out_dir, "audit.json"), encoding="utf-8"))
    out_info = audit.get("output", {"mode": "full", "sets_written": audit["stages"]["output_duplicate_sets"],
                                    "records_written": audit["stages"]["output_duplicate_records"]})
    if out_info["mode"] == "skipped":
        sys.exit("this run was audit-only (--skip-output): there is no output to verify")
    out_path = os.path.join(a.out_dir, "duplicate_sets.jsonl")
    trace_path = os.path.join(a.out_dir, "duplicate_sets_trace.jsonl")
    trace = [json.loads(l) for l in open(trace_path, encoding="utf-8")]

    step = max(1, -(-len(trace) // a.sample))
    sampled = set(range(0, len(trace), step))
    needed = {n for i in sampled for n in trace[i]["input_lines"]}
    raw = {}
    with open_input(a.input) as fh:
        for line_no, line in enumerate(fh, 1):
            if line_no in needed:
                raw[line_no] = line.rstrip(b"\r\n").decode("utf-8")

    fails = collections.Counter(); examples = {}
    def fail(name, i):
        fails[name] += 1; examples.setdefault(name, i)
    sets = rows = 0; prev_key = ""
    with open(out_path, encoding="utf-8", newline="\n") as fo:
        for i, out_line in enumerate(fo):
            t = trace[i]
            sets += 1
            try:
                o = json.loads(out_line)
            except json.JSONDecodeError:
                fail("output_line_not_valid_json", i); continue
            certs = o.get("certificates", [])
            rows += len(certs)
            if set(o.keys()) != {"fingerprint", "certificates"}: fail("wrong_keys", i)
            if len(certs) < 2: fail("set_smaller_than_2", i)
            if o["fingerprint"] != t["fingerprint"]: fail("trace_fingerprint_mismatch", i)
            if len(certs) != len(t["input_lines"]): fail("trace_length_mismatch", i)
            if t["input_lines"] != sorted(t["input_lines"]): fail("members_not_in_line_order", i)
            keys = {clean_fp(c["data"]["leaf_cert"]["fingerprint"]) for c in certs}
            if keys != {clean_fp(o["fingerprint"])}: fail("members_do_not_share_fingerprint", i)
            key = clean_fp(o["fingerprint"])
            if key < prev_key: fail("sets_not_in_fingerprint_order", i)
            prev_key = key
            if i in sampled:
                expected = '{"fingerprint": ' + json.dumps(o["fingerprint"], ensure_ascii=False) + ', "certificates": [' \
                           + ", ".join(raw[n] for n in t["input_lines"]) + ']}'
                if out_line.rstrip("\n") != expected: fail("not_byte_identical_to_input", i)
    st = audit["stages"]
    if sets != out_info["sets_written"]: fail("set_count_differs_from_audit", -1)
    if rows != out_info["records_written"]: fail("record_count_differs_from_audit", -1)
    if len(trace) != sets: fail("trace_length_differs_from_output", -1)
    if any(v is False for v in audit["checks"].values()): fail("audit_invariant_failed", -1)

    print(f"output mode: {out_info['mode']}; sets checked structurally: {sets}; byte-for-byte checked: {len(sampled)} of {len(trace)}")
    if fails:
        print("FAIL:", dict(fails), "first example set index:", examples); sys.exit(1)
    print("PASS: all checks")

if __name__ == "__main__":
    main()
