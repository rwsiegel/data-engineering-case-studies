# Exercise 1: decision log

| Decision | Why | Note |
|---|---|---|
| Duplicate test = leaf certificate fingerprint only | The chain fingerprint repeats across thousands of unrelated rows and would create false groups. | Strict reading of the task. |
| Precertificate and final certificate are not grouped; pairs are counted and reported | They have different fingerprints, so the strict test excludes them. | Open question for the data owner. |
| Unpaired precertificates are ordinary singletons | Their matching final certificate is not in the file. |  |
| Cleaned key = lowercase hex without colons; the original string is kept in the output | A formatting difference cannot hide a duplicate, and no information is lost. | All fingerprints already shared one format. |
| Bucket by the first two hex characters, not a hash | Fingerprints are already uniform, so 256 buckets come out even and are easy to explain. |  |
| One bucket in memory at a time | Memory stays flat as the input grows. |  |
| Output lines are exact copies of the input lines | All fields survive by construction; a verifier checks it byte for byte. | JSON Lines output. |
| Pointer index (fingerprint, line number, byte position) instead of full rows in the buckets | Cut temporary disk from about 35 GB to about 1.4 GB on the original 31.8 GB input. |  |
| Deliver an audit summary, reproduction steps and a verified sample instead of the full output | The full output is very large and one command regenerates it. | Confirm with the data owner. |
| Add an independent recount and report peak memory | Prove the numbers with a second method. | sort | uniq -c matched every number. |
| Report extra copies as well as sets | Sets alone understate how much data repeats. |  |
