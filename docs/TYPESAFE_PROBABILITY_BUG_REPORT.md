# Draft provider report: Choice probability totals of 0.99

**Unsent. User approval is required before sending this report or any attachments.**
No source descriptions, game titles, credentials, account identifiers, or private evidence are
needed in the proposed provider attachment. The probability-only fixture can be further reduced
to these three answers before sending; no repository or benchmark snapshot access is required.

Environment: TypeSafe Python SDK 0.7.0; requested `jev-latest`, returned `jev-1.13.0`.
Saved experiment: September 18, 2026 Pacific time. Stable local case/attempt IDs below are anonymized
experiment references, not provider request IDs. HTTP request IDs and original wire JSON are
unavailable. The available artifacts were serialized from SDK-parsed responses.

The Choice documentation describes a full distribution totaling one and defines confidence from
its shape, separately from the selected option probability. We enforce a total tolerance of 0.001.
See [Choice](https://docs.typesafe.ai/primitives/choice),
[API](https://docs.typesafe.ai/api), and [confidence](https://docs.typesafe.ai/confidence).

| Saved attempt | Question | Option count | Nonzero saved values | Decimal total |
| --- | --- | ---: | --- | ---: |
| legacy100:1101:attempt-2 | mechanic_ranged_combat | 4 | insufficient_evidence .93; present .05; conflicting_evidence .01 | .99 |
| legacy100:1139:attempt-2 | genre_family | 15 | action .17; horror .81; adventure_narrative .01 | .99 |
| legacy100:972:attempt-2 | genre:action | 23 | action_adventure .04; insufficient_evidence .81; character_action .14 | .99 |

All omitted options were present with zero probability. Saved values have at most two decimal
places. Exact `Decimal` summation yields 0.99; a 0.01 deficit is not binary floating-point noise.
SDK reparsing of the saved JSON preserves the numbers. Without the wire bodies, we cannot isolate
server behavior from the original SDK parsing/serialization path. Decimal quantization is a
hypothesis, not an established diagnosis.

In this fixed 100-record run, 12 first attempts failed validation. A single full-case retry recovered
nine; three still failed. Only error summaries survive for the first-attempt failures, so their
original numeric totals cannot be reconstructed. The question that failed can differ on retry
(e.g. the retained case 1101 errors concern different tags); this is not proof that the same answer
repeatedly sums to .99. No additional paid reproduction was performed for this report.

Expected: complete finite/ranged distributions with a total of one, or a documented precision
contract that explains any bounded discrepancy. Please confirm the intended precision semantics,
whether these deficits are expected, and whether SDK 0.7.0 can alter numeric values on decode.
A fresh wire-level reproduction can be authorized separately if necessary.

Current handling: strict rejection of invalid questions, preservation of valid independent answers,
bounded question-specific retries, retained raw values, and explicit incomplete genre computation
when a dependency fails. No tolerance expansion or silent normalization is proposed here.

If bounded decimal quantization is confirmed, a separate explicit decision would be required for a
versioned compatibility policy: preserve raw values; flag adjusted answers; store distinct derived
values; specify precision/error bounds; and test ranking/threshold sensitivity. This PR implements
no such policy.
