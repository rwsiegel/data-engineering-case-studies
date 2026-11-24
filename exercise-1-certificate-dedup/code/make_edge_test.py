"""Build a small file of awkward cases from the fixture, to test the script's edge handling."""
import json, collections
import sys
src = sys.argv[1]            # any record file; the first 50 lines are used
out_path = sys.argv[2]
good = []
for i, l in enumerate(open(src, encoding="utf-8")):
    if i >= 50: break
    l = l.rstrip("\n")
    try: o = json.loads(l)
    except Exception: continue
    good.append((o["data"]["leaf_cert"]["fingerprint"], l))
by = collections.defaultdict(list)
for fp, l in good: by[fp].append(l)
pair_fp = next(fp for fp, v in by.items() if len(v) == 2)
a, b = by[pair_fp]
a2 = a.replace('"aggregated": "', '"aggregated": "é', 1); assert a2 != a          # non-ASCII text
b2 = b.replace(pair_fp, pair_fp.replace(":", "").lower()); assert b2 != b           # same fingerprint, other format
singles = [l for fp, v in by.items() if len(v) == 1 for l in v][:10]
lines = [a2.encode("utf-8"), b2.encode("utf-8")] + [s.encode("utf-8") for s in singles] + [
    b"", b'\xff\xfe{"data": 1}', b'{"data": {"leaf_cert": {}}}',
    b'{"data": {"leaf_cert": {"fingerprint": "ZZ:ZZ"}}}', b'{"data": {"leaf_cert": {"fingerprint": "BROKEN"']
open(out_path, "wb").write(b"\r\n".join(lines) + b"\r\n")     # CRLF line endings
print("pair fingerprint:", pair_fp, "| lines written:", len(lines))
