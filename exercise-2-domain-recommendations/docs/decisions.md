# Exercise 2: decision log

| Decision | Why | Note |
|---|---|---|
| Methods chosen before opening the data: an explainable score, not a trained model | There are no labels, so a model would fit guesses. | Plan |
| Unit of evidence = the infected machine; one observation per machine and registrable domain | One heavy machine must not look like strong evidence. |  |
| Staged score with four named clues | A reviewer can dispute each part. | Weights are judgment. |
| Clustering done as a time-boxed check, after the score | Not needed to produce a list; used to look for missed domains. |  |
| Name meaning from word vectors (GloVe), not character n-grams | Captures meaning, not spelling. | External file needed. |
| Strip 21 generic business words before comparing names | Words like 'group' or 'capital' match everything. | Found by frequency: words in 3% or more of domains. |
| Public-service filter at 35% of machines | Widespread services are not client-specific. | 9 domains removed. |
| Gate: at least 10 machines | Too little co-occurrence evidence below this. | 438 pass. |
| Tenants and internal names set aside, not ranked | Related, not owned. | 7 tenants. |
| Weights 0.30 / 0.35 / 0.20 / 0.15; cutoff 0.75; tiers A and B | Name parts total 0.35 so the name alone cannot top the list. | Cutoff tested from 0.65 to 0.85. |
| Repair hostnames written backwards and log them as repairs, not discards | Otherwise they create a false lead and undercount a real domain. | 36 rows. |
| Count saved-login rows by default; distinct login pages as an option | The cause of repeated rows is unknown. | 15 of 21 stay under the option. |
| A domain scoring on name clues alone cannot reach the cutoff (checked by `validate.py`) | Name similarity is not ownership. |  |
| Machine overlap is not used as a clue | Overlap among name-family domains is no higher than chance would predict. | Documented as a limit. |
| Label results as initial recommendations for discussion | Nothing here confirms ownership. | Banner on the explorer. |
