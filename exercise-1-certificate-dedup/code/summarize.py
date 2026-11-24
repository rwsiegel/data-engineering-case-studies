#!/usr/bin/env python3
"""Turn audit.json (from dedup.py) into a one-page markdown summary.
Usage: python summarize.py --audit results/audit.json --out audit_summary.md"""
import argparse, json

def n(x): return f"{x:,}"
def pct(a, b): return f"{100*a/b:.1f}%" if b else "n/a"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = json.load(open(a.audit, encoding="utf-8")); s = d["stages"]; raw = s["raw_lines"]
    L = []; w = L.append
    w("# Certificate Transparency duplicate detection: audit summary\n")
    w(f"Input: `{d['input'].replace(chr(92), '/').split('/')[-1]}` ({n(raw)} records). Grouping key: `{d['settings']['fingerprint_path']}`.\n")
    w("## Headline numbers\n")
    w(f"- Input records: **{n(raw)}**")
    w(f"- Records in output: **{n(s['output_duplicate_records'])}** ({pct(s['output_duplicate_records'], raw)}), in **{n(s['output_duplicate_sets'])}** duplicate sets")
    w(f"- Records removed: **{n(raw - s['output_duplicate_records'])}** = {n(s['rejected'])} rejected (bad data) + {n(s['singletons_removed'])} singletons (no duplicate)")
    extra = s["output_duplicate_records"] - s["output_duplicate_sets"]
    w(f"- Share of records inside a duplicate set: **{pct(s['output_duplicate_records'], raw)}**")
    w(f"- Extra copies (records beyond one per certificate): **{n(extra)}** = **{pct(extra, raw)}** of input. This is the duplicate rate.\n")
    w("## Funnel\n")
    w("| Checkpoint | Kept | Removed | Why |\n|---|---:|---:|---|")
    w(f"| Raw | {n(raw)} | | |")
    w(f"| Parsed and staged | {n(s['staged_with_valid_fingerprint'])} | {n(s['rejected'])} | bad data (see reasons below) |")
    w(f"| Grouped | {n(s['grouped_distinct_fingerprints'])} distinct fingerprints | | |")
    w(f"| Output | {n(s['output_duplicate_records'])} | {n(s['singletons_removed'])} | fingerprint appears once |")
    w("\nEach step: kept + removed = records entering the step.\n")
    w("## Reasons for removal\n")
    if d["rejects_by_reason"]:
        w("| Reason | Count | Example line |\n|---|---:|---:|")
        for k, v in d["rejects_by_reason"].items(): w(f"| {k} | {n(v)} | {d['reject_example_line_numbers'].get(k, '')} |")
    else:
        w("No records rejected. Every line parsed and carried a valid fingerprint.")
    w(f"\nSingletons: {n(s['singletons_removed'])} records had a fingerprint that appears only once, so they are not duplicates.\n")
    w("## How many copies per duplicate set\n")
    w("| Set size | Sets | Share of sets |\n|---:|---:|---:|")
    tot = s["output_duplicate_sets"]
    for k, v in sorted(d["set_size_distribution"].items(), key=lambda kv: int(kv[0])): w(f"| {k} | {n(v)} | {pct(v, tot)} |")
    kinds = {"all precert": 0, "all final": 0, "mixed": 0}
    for k, v in d["set_update_type_combinations"].items():
        parts = set(k.split(" + "))
        kinds["all precert" if parts == {"PrecertLogEntry"} else "all final" if parts == {"X509LogEntry"} else "mixed"] += v
    w("\nWhat kind of entries are in each set:\n")
    for k, v in kinds.items(): w(f"- {k}: {n(v)} sets ({pct(v, tot)})")
    w("\n## Duplicate records by log operator\n")
    w("| Log | Records in output | Records in input |\n|---|---:|---:|")
    for k, v in list(d["duplicate_rows_by_log"].items())[:10]: w(f"| {k} | {n(v)} | {n(d['index']['rows_by_log'].get(k, 0))} |")
    w("\nMost common log pairs in two-member sets:\n")
    for pair, c in d["top_log_pairs_in_two_member_sets"][:5]: w(f"- {pair[0]} + {pair[1]}: {n(c)}")
    w(f"\nSets with both copies from the same log: {d['sets_with_two_members_from_the_same_log']}.\n")
    p = d["precert_final_pairs"]
    w("## Open item: precert/final pairs (reported, not grouped)\n")
    w(f"A precert and its final certificate have different fingerprints, so the strict definition does not group them. "
      f"By {p['definition']}, this file has **{n(p['pairs_found'])} pairs** ({n(p['fingerprints_in_pairs'])} fingerprints). "
      f"Serials with conflicting domains or validity: {n(p['serials_with_conflicting_domains_or_validity'])}. "
      "Question for the hiring team: should pairs count as duplicates?\n")
    w("## Integrity checks\n")
    for k, v in d["checks"].items(): w(f"- {'PASS' if v else 'FAIL'}: {k}")
    w(f"\n## Run details\n\n- Buckets: {d['buckets_used']} (prefix length {d['settings']['prefix_len']}); largest bucket {n(d['largest_bucket_rows'])} rows, which bounds memory.")
    w(f"- Indexing took {d['index']['seconds_indexing']} seconds; grouping and audit about {d['seconds_this_invocation']} seconds.")
    o = d["output"]; w(f"- Output mode for this audit: {o['mode']}. {o['note']}.")
    open(a.out, "w", encoding="utf-8").write("\n".join(L) + "\n")

if __name__ == "__main__":
    main()
