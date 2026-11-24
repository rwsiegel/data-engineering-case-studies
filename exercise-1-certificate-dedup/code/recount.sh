#!/usr/bin/env bash
# Independent recount for Exercise 1. Shares no code with dedup.py: pulls the leaf fingerprint from each line with a
# separate one-liner, then counts with sort | uniq -c.   Usage: bash recount.sh INPUT.jsonlines
set -euo pipefail
python3 -c 'import sys,json
for l in open(sys.argv[1],encoding="utf-8"): print(json.loads(l)["data"]["leaf_cert"]["fingerprint"].replace(":","").lower())' "$1" | sort | uniq -c | awk '
 {n=$1; recs+=n; fp++; size[n]++; if(n==1){single+=1} else {sets++; dupr+=n}}
 END{print "records", recs; print "distinct fingerprints", fp; print "singletons", single; print "duplicate sets", sets; print "records in duplicate sets", dupr;
     for(s in size) if(s>1) print "sets of size", s, size[s]}' | sort
