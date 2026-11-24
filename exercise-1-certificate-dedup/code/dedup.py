"""Exercise 1: group CT records by leaf fingerprint and write the duplicate sets.

Usage:  python dedup.py --input FILE[.gz] --out-dir DIR [--work-dir DIR] [--prefix-len N] [--max-seconds S]

Layers
  RAW      the input file, never copied or changed.
  INDEX    one small row per record (the "leaf index"): where the record is (line number, byte offset,
           byte length) plus leaf-level facts only: cleaned fingerprint, update_type, log name,
           cert_index, serial, validity dates, a short hash of the domain list. The chain is never read
           into the index. Rows are partitioned into bucket files by the first N hex characters of the
           cleaned fingerprint (16**N buckets), so grouping can run one bucket at a time.
  OUTPUT   for each fingerprint seen in 2+ index rows, the original lines are fetched from RAW by
           position and written, exactly as they were in the input.

Steps
  1. INDEX    one pass over RAW (resumable: --max-seconds saves a checkpoint; rerun the same command).
  2. GROUP    one bucket at a time: find fingerprints with 2+ rows, write a plan (positions only).
  3. FETCH    read the planned lines from RAW and write duplicate_sets.jsonl and the trace file.
  4. PAIRS    count precert/final pairs (same serial, domains, validity, different fingerprint) using a
              second, serial-keyed split of the index. Reported only; not part of the output.
  5. AUDIT    funnel counts, reject reasons, set sizes, per-log breakdown, invariant checks.

Outputs (in --out-dir)
  duplicate_sets.jsonl        the deliverable: {"fingerprint": ..., "certificates": [A, B, ...]}
  duplicate_sets_trace.jsonl  side file: input line numbers (and byte offsets) behind each output line
  audit.json                  everything needed for the summary
"""
import argparse, collections, gzip, hashlib, json, os, re, shutil, sys, time

# ---------------- SETTINGS (edit here, not in the code below) ----------------
FINGERPRINT_PATH = ("data", "leaf_cert", "fingerprint")  # where the fingerprint sits in each record
SUMMARY_PATHS = {                                        # leaf-level facts copied into the index
    "update_type": ("data", "update_type"),
    "source": ("data", "source", "name"),
    "cert_index": ("data", "cert_index"),
    "serial": ("data", "leaf_cert", "serial_number"),
    "not_before": ("data", "leaf_cert", "not_before"),
    "not_after": ("data", "leaf_cert", "not_after"),
    "domains": ("data", "leaf_cert", "all_domains"),
}
VALID_HASH_LENGTHS = (40, 64)                            # hex characters: SHA-1 or SHA-256
DEFAULT_PREFIX_LEN = 2                                   # hex chars per bucket name (2 -> 256 buckets)
FLUSH_BYTES = 64 * 1024 * 1024                           # buffered index data written to disk at this size
PRECERT, FINAL = "PrecertLogEntry", "X509LogEntry"
# -----------------------------------------------------------------------------

HEX_RE = re.compile(r"^[0-9a-f]+$")
# index row positions
LINE, OFFSET, LENGTH, KEY, UTYPE, SOURCE, CERT_INDEX, SERIAL, NBEFORE, NAFTER, DHASH = range(11)

def clean_fp(fp):
    # DECIDED: lowercase hex, colons and whitespace removed. Used for grouping and bucketing only.
    return re.sub(r"[:\s]", "", fp).lower()

def dig(obj, path):
    for k in path:
        if not isinstance(obj, dict) or k not in obj:
            raise KeyError(k)
        obj = obj[k]
    return obj

def dig_opt(obj, path):
    try:
        return dig(obj, path)
    except KeyError:
        return None

def domains_hash(domains):
    if isinstance(domains, list) and all(isinstance(d, str) for d in domains):
        return hashlib.blake2b("\n".join(sorted(domains)).encode("utf-8"), digest_size=8).hexdigest()
    return None

def pair_bucket(serial):
    return hashlib.md5(serial.encode("utf-8")).hexdigest()[:2]

def compact(row):
    return json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n"

def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)

def main():
    ap = argparse.ArgumentParser(description="Group CT records by leaf fingerprint.")
    ap.add_argument("--input", required=True, help="JSON Lines file, plain or .gz")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--work-dir", help="index and plan files (default: OUT_DIR/_work); needs under 1 GB for the full sample")
    ap.add_argument("--prefix-len", type=int, default=DEFAULT_PREFIX_LEN, help="hex chars per bucket name")
    ap.add_argument("--max-seconds", type=float, default=0, help="stop indexing after about this long and save a checkpoint (plain files only); rerun the same command to continue")
    ap.add_argument("--progress-every", type=int, default=0, help="print progress to stderr every N input lines (0 = off)")
    ap.add_argument("--skip-output", action="store_true", help="audit only: build the index, group, count pairs, but do not fetch or write the duplicate sets")
    ap.add_argument("--output-sample", type=int, default=0, help="write only N evenly spaced duplicate sets (a spot check) instead of all of them")
    ap.add_argument("--keep-work", action="store_true", help="keep the index files after a successful run")
    ap.add_argument("--fresh", action="store_true", help="discard any saved index and start over")
    a = ap.parse_args()
    t0 = time.time()
    def log(msg):
        print(f"[{time.time() - t0:7.0f}s] {msg}", file=sys.stderr, flush=True)

    os.makedirs(a.out_dir, exist_ok=True)
    wd = os.path.abspath(a.work_dir or os.path.join(a.out_dir, "_work"))
    idx_dir, pair_dir = os.path.join(wd, "index"), os.path.join(wd, "pairs")
    state_path = os.path.join(wd, "index_state.json")
    plan_path = os.path.join(wd, "sets_plan.jsonl")
    with open(a.input, "rb") as f:
        is_gz = f.read(2) == b"\x1f\x8b"
    if is_gz and a.max_seconds:
        sys.exit("--max-seconds needs an uncompressed input: a .gz file cannot be resumed part-way")
    in_size = os.path.getsize(a.input)
    in_abs = os.path.abspath(a.input)

    def open_raw():
        return gzip.open(a.input, "rb") if is_gz else open(a.input, "rb")

    if a.fresh:
        shutil.rmtree(wd, ignore_errors=True)
    state = None
    if os.path.exists(state_path):
        state = json.load(open(state_path, encoding="utf-8"))
        if state["input"] != in_abs or state["input_size"] != in_size or state["prefix_len"] != a.prefix_len:
            sys.exit("the work dir holds an index from a different input or prefix length; rerun with --fresh")
        if is_gz and not state["done"]:
            shutil.rmtree(wd, ignore_errors=True); state = None
    if state is None:
        state = {"input": in_abs, "input_size": in_size, "prefix_len": a.prefix_len, "next_offset": 0, "next_line": 1,
                 "raw_n": 0, "staged_n": 0, "no_serial_rows": 0, "rejects": {}, "reject_examples": {},
                 "rows_by_log": {}, "rows_by_update_type": {}, "bucket_sizes": {}, "done": False,
                 "chunks": 0, "seconds_indexing": 0.0}
    for d in (idx_dir, pair_dir):
        os.makedirs(d, exist_ok=True)
        for name in os.listdir(d):                      # drop anything written after the last checkpoint
            p = os.path.join(d, name)
            keep = state["bucket_sizes"].get(f"{os.path.basename(d)}/{name}", 0)
            if os.path.getsize(p) > keep:
                with open(p, "r+b") as fh:
                    fh.truncate(keep)

    # ------------------------------------------------------------ 1. INDEX
    if not state["done"]:
        rejects = collections.Counter(state["rejects"])
        examples = {k: list(v) for k, v in state["reject_examples"].items()}
        by_log = collections.Counter(state["rows_by_log"])
        by_ut = collections.Counter(state["rows_by_update_type"])
        buf_i, buf_p = collections.defaultdict(list), collections.defaultdict(list)
        buffered = 0
        raw_n, staged_n, no_serial = state["raw_n"], state["staged_n"], state["no_serial_rows"]

        def flush():
            nonlocal buffered
            for d, buf in ((idx_dir, buf_i), (pair_dir, buf_p)):
                for name, rows in buf.items():
                    with open(os.path.join(d, name + ".jsonl"), "a", encoding="utf-8", newline="\n") as bf:
                        bf.writelines(rows)
                buf.clear()
            buffered = 0

        def process(line, line_no, offset):
            """Index one line. Returns a reject reason, or None if the line was indexed."""
            nonlocal buffered, staged_n, no_serial
            try:
                text = line.rstrip(b"\r\n").decode("utf-8")     # strict: never silently alters bytes
            except UnicodeDecodeError:
                return "invalid_utf8"
            if not text.strip():
                return "blank_line"
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                return "unparseable_json"
            try:
                fp = dig(obj, FINGERPRINT_PATH)
            except KeyError:
                return "missing_fingerprint"
            if not isinstance(fp, str):
                return "fingerprint_not_string"
            key = clean_fp(fp)
            if not HEX_RE.match(key) or len(key) not in VALID_HASH_LENGTHS:
                return "fingerprint_not_valid_hex_hash"
            f = {name: dig_opt(obj, path) for name, path in SUMMARY_PATHS.items()}
            row = [line_no, offset, len(line), key, f["update_type"], f["source"], f["cert_index"],
                   f["serial"], f["not_before"], f["not_after"], domains_hash(f["domains"])]
            r = compact(row)
            buf_i[key[:a.prefix_len]].append(r)
            buffered += len(r)
            staged_n += 1
            by_log[f["source"]] += 1
            by_ut[f["update_type"]] += 1
            if isinstance(f["serial"], str) and f["update_type"] in (PRECERT, FINAL):
                p = compact([f["serial"], row[DHASH], f["not_before"], f["not_after"], f["update_type"], key])
                buf_p[pair_bucket(f["serial"])].append(p)
                buffered += len(p)
            else:
                no_serial += 1
            return None

        offset, line_no = state["next_offset"], state["next_line"]
        t_i = time.time()
        finished = True
        with open_raw() as fh:
            if not is_gz:
                fh.seek(offset)
            for line in fh:
                if a.max_seconds and line_no % 500 == 0 and time.time() - t_i >= a.max_seconds:
                    finished = False
                    break
                raw_n += 1
                reason = process(line, line_no, offset)
                if reason:
                    rejects[reason] += 1
                    if len(examples.setdefault(reason, [])) < 5:
                        examples[reason].append(line_no)
                offset += len(line)
                line_no += 1
                if buffered >= FLUSH_BYTES:
                    flush()
                if a.progress_every and raw_n % a.progress_every == 0:
                    log(f"index: {raw_n:,} lines, {staged_n:,} indexed, {offset / 1e9:.2f} GB read")
        flush()
        sizes = {}
        for d in (idx_dir, pair_dir):
            for name in os.listdir(d):
                sizes[f"{os.path.basename(d)}/{name}"] = os.path.getsize(os.path.join(d, name))
        state.update(next_offset=offset, next_line=line_no, raw_n=raw_n, staged_n=staged_n, no_serial_rows=no_serial,
                     rejects=dict(rejects), reject_examples=examples, rows_by_log=dict(by_log),
                     rows_by_update_type=dict(by_ut), bucket_sizes=sizes, done=finished,
                     chunks=state["chunks"] + 1, seconds_indexing=state["seconds_indexing"] + (time.time() - t_i))
        write_json_atomic(state_path, state)
        if not finished:
            pct = 100.0 * offset / in_size
            print(json.dumps({"status": "partial", "indexed_percent": round(pct, 1), "lines_so_far": raw_n,
                              "next_step": "run the same command again to continue"}))
            sys.exit(2)
        log(f"index done: {raw_n:,} lines, {staged_n:,} indexed, {sum(rejects.values()):,} rejected")

    raw_n, staged_n = state["raw_n"], state["staged_n"]
    rejects, reject_examples = state["rejects"], state["reject_examples"]
    total_rejects = sum(rejects.values())

    # ------------------------------------------------------------ 2. GROUP (one bucket at a time)
    grouped_keys = singleton_rows = output_sets = output_rows = 0
    set_size_dist = collections.Counter()
    set_types = collections.Counter()
    rows_in_sets_by_log = collections.Counter()
    log_pairs = collections.Counter()
    same_log_sets = 0
    bucket_summary = []
    index_rows = 0
    with open(plan_path, "w", encoding="utf-8", newline="\n") as plan:
        for name in sorted(os.listdir(idx_dir)):
            groups = collections.defaultdict(list)
            rows_here = 0
            with open(os.path.join(idx_dir, name), encoding="utf-8", newline="\n") as bf:
                for row in bf:
                    r = json.loads(row)
                    groups[r[KEY]].append(r)
                    rows_here += 1
            index_rows += rows_here
            sets_here = singles_here = 0
            for key in sorted(groups):
                members = sorted(groups[key], key=lambda r: r[LINE])      # A, B, C in input line order
                grouped_keys += 1
                if len(members) == 1:
                    singles_here += 1; singleton_rows += 1
                    continue
                sets_here += 1; output_sets += 1; output_rows += len(members)
                set_size_dist[len(members)] += 1
                set_types[tuple(sorted(str(m[UTYPE]) for m in members))] += 1
                logs = [str(m[SOURCE]) for m in members]
                rows_in_sets_by_log.update(logs)
                if len(set(logs)) < len(logs):
                    same_log_sets += 1
                if len(members) == 2:
                    log_pairs[tuple(sorted(logs))] += 1
                plan.write(compact([key, [[m[LINE], m[OFFSET], m[LENGTH]] for m in members]]))
            bucket_summary.append({"bucket": name[:-6], "rows": rows_here, "duplicate_sets": sets_here, "singletons": singles_here})
    log(f"group done: {output_sets:,} duplicate sets across {len(bucket_summary)} buckets")

    # ------------------------------------------------------------ 3. FETCH originals, write output
    mode = "skipped" if a.skip_output else ("sample" if a.output_sample else "full")
    stride = max(1, -(-output_sets // a.output_sample)) if mode == "sample" else 1
    written_sets = written_rows = mixed_format_sets = key_mismatches = 0
    if mode == "skipped":
        log("fetch skipped (--skip-output): no duplicate_sets.jsonl written")
    else:
        needed_map = None
        extract_path = os.path.join(wd, "extract.bin")
        if is_gz:                                   # a .gz cannot be seeked: pull the needed lines out in one pass
            needed = set()
            with open(plan_path, encoding="utf-8") as pf:
                for i, row in enumerate(pf):
                    if i % stride == 0:
                        for m in json.loads(row)[1]:
                            needed.add(m[0])
            needed_map, pos = {}, 0
            with open_raw() as fh, open(extract_path, "wb") as ex:
                for n, line in enumerate(fh, 1):
                    if n in needed:
                        needed_map[n] = (pos, len(line)); ex.write(line); pos += len(line)
            src = open(extract_path, "rb")
        else:
            src = open(a.input, "rb")

        def fetch(line_no, offset, length):
            if needed_map is not None:
                offset, length = needed_map[line_no]
            src.seek(offset)
            return src.read(length).rstrip(b"\r\n").decode("utf-8")

        with open(plan_path, encoding="utf-8") as pf, \
             open(os.path.join(a.out_dir, "duplicate_sets.jsonl"), "w", encoding="utf-8", newline="\n") as out, \
             open(os.path.join(a.out_dir, "duplicate_sets_trace.jsonl"), "w", encoding="utf-8", newline="\n") as trace:
            for i, row in enumerate(pf):
                if i % stride:
                    continue
                key, members = json.loads(row)
                texts = [fetch(*m) for m in members]
                fps = [dig(json.loads(t), FINGERPRINT_PATH) for t in texts]
                if any(clean_fp(f) != key for f in fps):
                    key_mismatches += 1             # the fetched line is not the indexed record
                if len(set(fps)) > 1:
                    mixed_format_sets += 1
                shown_fp = fps[0]                   # original string of the member with the lowest line number
                # Certificates are the original input lines, joined as-is (never re-serialized).
                out.write('{"fingerprint": ' + json.dumps(shown_fp, ensure_ascii=False)
                          + ', "certificates": [' + ", ".join(texts) + ']}\n')
                trace.write(json.dumps({"fingerprint": shown_fp, "input_lines": [m[0] for m in members],
                                        "input_offsets": None if is_gz else [[m[1], m[2]] for m in members]}) + "\n")
                written_sets += 1; written_rows += len(members)
        src.close()
        if os.path.exists(extract_path):
            os.remove(extract_path)
        log(f"fetch done: {written_sets:,} sets written ({mode})")

    # ------------------------------------------------------------ 4. PAIRS (reported only)
    pair_groups = pair_rows = precert_only = final_only = conflicts = distinct_serials = pair_index_rows = 0
    for name in sorted(os.listdir(pair_dir)):
        by_serial = collections.defaultdict(list)
        with open(os.path.join(pair_dir, name), encoding="utf-8", newline="\n") as bf:
            for row in bf:
                r = json.loads(row)                 # [serial, dhash, not_before, not_after, update_type, key]
                by_serial[r[0]].append(r)
                pair_index_rows += 1
        for serial, rows in by_serial.items():
            distinct_serials += 1
            variants = collections.defaultdict(lambda: {"pre": set(), "fin": set()})
            for _, dh, nb, na, ut, key in rows:
                variants[(dh, nb, na)]["pre" if ut == PRECERT else "fin"].add(key)
            if len(variants) > 1:
                conflicts += 1
            for v in variants.values():
                if v["pre"] and v["fin"]:
                    pair_groups += 1; pair_rows += len(v["pre"]) + len(v["fin"])
                elif v["pre"]:
                    precert_only += 1
                else:
                    final_only += 1
    log("pairs done")

    # ------------------------------------------------------------ 5. AUDIT
    audit = {
        "input": a.input,
        "input_is_gzip": is_gz,
        "output": {"mode": mode, "stride": stride, "sets_written": written_sets, "records_written": written_rows,
                   "note": {"full": "all duplicate sets written", "sample": "a spot check: every stride-th duplicate set only, not the full result",
                            "skipped": "audit only: no duplicate sets written"}[mode]},
        "settings": {"fingerprint_path": ".".join(FINGERPRINT_PATH), "valid_hash_lengths": list(VALID_HASH_LENGTHS), "prefix_len": a.prefix_len},
        "buckets_used": len(bucket_summary),
        "largest_bucket_rows": max((b["rows"] for b in bucket_summary), default=0),
        "index": {"chunks": state["chunks"], "seconds_indexing": round(state["seconds_indexing"]),
                  "rows_by_update_type": state["rows_by_update_type"],
                  "rows_by_log": dict(sorted(state["rows_by_log"].items(), key=lambda kv: -kv[1]))},
        "stages": {
            "raw_lines": raw_n,
            "rejected": total_rejects,
            "staged_with_valid_fingerprint": staged_n,
            "grouped_distinct_fingerprints": grouped_keys,
            "singletons_removed": singleton_rows,
            "output_duplicate_sets": output_sets,
            "output_duplicate_records": output_rows,
        },
        "rejects_by_reason": rejects,
        "reject_example_line_numbers": reject_examples,
        "set_size_distribution": dict(sorted(set_size_dist.items())),
        "set_update_type_combinations": {" + ".join(k): v for k, v in set_types.items()},
        "duplicate_rows_by_log": dict(rows_in_sets_by_log.most_common()),
        "top_log_pairs_in_two_member_sets": [[list(k), v] for k, v in log_pairs.most_common(10)],
        "sets_with_two_members_from_the_same_log": same_log_sets,
        "sets_with_mixed_fingerprint_formats": mixed_format_sets if mode != "skipped" else None,
        "precert_final_pairs": {
            "pairs_found": pair_groups,
            "fingerprints_in_pairs": pair_rows,
            "precert_groups_without_a_final_in_this_file": precert_only,
            "final_groups_without_a_precert_in_this_file": final_only,
            "serials_with_conflicting_domains_or_validity": conflicts,
            "distinct_serials": distinct_serials,
            "rows_without_a_serial_or_update_type": state["no_serial_rows"],
            "definition": "same serial number, domain list, and validity dates, with both a precert and a final cert present, under different fingerprints",
        },
        "checks": {
            "raw == staged + rejected": raw_n == staged_n + total_rejects,
            "staged == singletons + output records": staged_n == singleton_rows + output_rows,
            "output records == sum(set sizes)": output_rows == sum(k * v for k, v in set_size_dist.items()),
            "index rows == staged": index_rows == staged_n,
            "pair rows + no-serial rows == staged": pair_index_rows + state["no_serial_rows"] == staged_n,
        },
        "bucket_summary": bucket_summary,
        "seconds_this_invocation": round(time.time() - t0),
    }
    if mode != "skipped":
        audit["checks"]["fetched lines all matched their indexed fingerprint"] = key_mismatches == 0
    with open(os.path.join(a.out_dir, "audit.json"), "w", encoding="utf-8") as af:
        json.dump(audit, af, indent=2)
    if not a.keep_work:
        shutil.rmtree(wd, ignore_errors=True)
    print(json.dumps({k: v for k, v in audit.items() if k not in ("bucket_summary", "index")}, indent=2))

if __name__ == "__main__":
    main()
