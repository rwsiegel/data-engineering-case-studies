# Exercise 2 commentary

Plain-language notes on the approach, what stood out, and what I would change. Numbers come from the synthetic run in this repository.

## What counts as evidence, and the unit

The unit is the **infected machine** (`log_id`), not the saved-login row. A hundred logins from one computer is one piece of evidence. For each (machine, domain) pair I keep one observation and carry the row counts. After cleaning there are 58,706 observations over 560 machines.

Evidence for a domain is: how many machines hold it (**co-occurrence**), how many saved logins per machine, how rare the words in its name are, and how close the name's meaning is to the seed. Machine details (malware family, antivirus, country, operating system) did not separate client domains from others when tested, so they are not scored.

## Name similarity is not ownership

Anyone can register a name that resembles another company's: competitors, fan sites, phishing sites. A similar name says someone chose a similar word, not who registered it. So the name clues carry 35% of the score, a domain with no machine evidence cannot be recommended, and `validate.py` checks that a domain scoring on name alone cannot reach the cutoff.

**Tier A** (12 domains) carry the seed name and behave like the seed. **Tier B** (9) match on behavior and theme only and need client confirmation. The domains built around one invented theme word (the `kendo*` family) are possibly related but unconfirmed, because their machine overlap with the seed family is no higher than chance.

## What I found interesting

- **Public services dominate the raw candidate set by machines held.** Of the 26 domains on more than 100 machines, 23 are well-known public services. By count the long tail dominates instead: 82% of the 33,131 candidates sit on a single machine. Removing widespread services first made the remaining pattern much easier to read, and in clustering the easy-to-understand logins stood out.
- **Word-vector relationships are worth a closer look.** Domains whose names sit close to the seed's meaning but share no letters came up, and some names that merely "sound related" scored high. This is a lead to check with the client, not a result.
- **One login per machine was the clue that did the most work**: removing it replaces 8 of the 21 recommended domains, and removing any other single clue replaces at most 2. But the seed itself holds 1.83 logins per machine, not 1.0, so the clue encodes a hypothesis about how company sites behave.

## Data quality

- 5,080 rows were hosts that are IP addresses (discarded and logged).
- 36 rows had a hostname written backwards (`com.example.` for `example.com`); I reversed them and logged each as a repair.
- A few internal names (`.local`, `.corp`) were set aside, not ranked.
- The same machine, host and login page appears several times (21,126 groups hold 77,532 rows). Only the download time differs, by under a second. I cannot tell whether this is the stealer, the ingestion process or the same account saved twice without a credential identifier.
- There are no usernames or passwords, so two logins on one domain cannot be told apart from one login seen twice.

## What is missing that would give better answers

1. A **credential identifier** (a hash of the username, never the username) to explain repeated rows and count distinct accounts.
2. **Known client domains** to measure how well the ranking recovers them.
3. **Dates on each saved login.** The `downloaded` field is ingestion time, so relationships cannot be placed in time.
4. **Registration data** for each domain (below).
5. More machines: 560 is a small sample, so many domains have too few machines to score.

## Representing relationships as a footprint grows and recommendations are accepted or rejected

Store **relationship records**, not a flat list. Each record is an edge between two domains with: evidence type (shared machines, shared registrant, shared certificate, similar name), strength, `first_seen`, `last_seen`, and the source. Recommendations reference these edges and carry an as-of date. A separate **decision history** records accepted or rejected, the reason, who and when. Decisions feed back as labels, so over time a supervised model becomes possible. See `relationship_sketch.mmd` and `visuals/ex2_relationship_sketch.png`.

## One additional field or source

**The registrant organization from domain registration data (WHOIS or its modern replacement RDAP, the Registration Data Access Protocol).** A shared registrant would directly show ownership, which this data can only hint at. If registrant details are redacted, the fallback is the list of certificates issued for each domain from Certificate Transparency logs (see Exercise 1): a shared certificate name or issuer is strong evidence, and it would let a candidate be confirmed rather than guessed.

## Questions I would ask the data owner

1. Why do the same machine, host and login page repeat, and is there a credential identifier that was removed?
2. Is a sister brand of the client a useful recommendation, or only domains the client owns?
3. Are there known client domains I can check the list against?
4. Is a short high-confidence list preferred to a longer list with lower confidence?
5. Is `downloaded` the time of theft or of ingestion?
