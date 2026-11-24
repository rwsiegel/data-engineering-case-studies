# Certificate Transparency duplicate detection: audit summary

Input: `synthetic_ct_records.jsonlines` (50,037 records). Grouping key: `data.leaf_cert.fingerprint`.

## Headline numbers

- Input records: **50,037**
- Records in output: **23,952** (47.9%), in **10,747** duplicate sets
- Records removed: **26,085** = 0 rejected (bad data) + 26,085 singletons (no duplicate)
- Share of records inside a duplicate set: **47.9%**
- Extra copies (records beyond one per certificate): **13,205** = **26.4%** of input. This is the duplicate rate.

## Funnel

| Checkpoint | Kept | Removed | Why |
|---|---:|---:|---|
| Raw | 50,037 | | |
| Parsed and staged | 50,037 | 0 | bad data (see reasons below) |
| Grouped | 36,832 distinct fingerprints | | |
| Output | 23,952 | 26,085 | fingerprint appears once |

Each step: kept + removed = records entering the step.

## Reasons for removal

No records rejected. Every line parsed and carried a valid fingerprint.

Singletons: 26,085 records had a fingerprint that appears only once, so they are not duplicates.

## How many copies per duplicate set

| Set size | Sets | Share of sets |
|---:|---:|---:|
| 2 | 8,644 | 80.4% |
| 3 | 1,790 | 16.7% |
| 4 | 281 | 2.6% |
| 5 | 26 | 0.2% |
| 6 | 3 | 0.0% |
| 7 | 2 | 0.0% |
| 8 | 1 | 0.0% |

What kind of entries are in each set:

- all precert: 6,926 sets (64.4%)
- all final: 3,821 sets (35.6%)
- mixed: 0 sets (0.0%)

## Duplicate records by log operator

| Log | Records in output | Records in input |
|---|---:|---:|
| Google 'Argon2019' log | 6,479 | 14,018 |
| Let's Encrypt 'Oak2019' log | 6,007 | 12,880 |
| Google 'Icarus' log | 3,316 | 4,833 |
| Google 'Rocketeer' log | 2,700 | 5,959 |
| Google 'Pilot' log | 2,669 | 6,138 |
| Cloudflare 'Nimbus2019' Log | 1,100 | 1,933 |
| Google 'Skydiver' log | 570 | 772 |
| Sectigo 'Mammoth' CT log | 526 | 904 |
| DigiCert Yeti2019 Log | 289 | 812 |
| Cloudflare 'Nimbus2020' Log | 76 | 238 |

Most common log pairs in two-member sets:

- Google 'Argon2019' log + Let's Encrypt 'Oak2019' log: 3,153
- Google 'Pilot' log + Google 'Rocketeer' log: 1,707
- Google 'Argon2019' log + Google 'Icarus' log: 1,334
- Google 'Icarus' log + Let's Encrypt 'Oak2019' log: 834
- Cloudflare 'Nimbus2019' Log + Google 'Argon2019' log: 406

Sets with both copies from the same log: 1.

## Open item: precert/final pairs (reported, not grouped)

A precert and its final certificate have different fingerprints, so the strict definition does not group them. By same serial number, domain list, and validity dates, with both a precert and a final cert present, under different fingerprints, this file has **10,099 pairs** (20,198 fingerprints). Serials with conflicting domains or validity: 0. Question for the hiring team: should pairs count as duplicates?

## Integrity checks

- PASS: raw == staged + rejected
- PASS: staged == singletons + output records
- PASS: output records == sum(set sizes)
- PASS: index rows == staged
- PASS: pair rows + no-serial rows == staged

## Run details

- Buckets: 256 (prefix length 2); largest bucket 243 rows, which bounds memory.
- Indexing took 1 seconds; grouping and audit about 1 seconds.
- Output mode for this audit: skipped. audit only: no duplicate sets written.
