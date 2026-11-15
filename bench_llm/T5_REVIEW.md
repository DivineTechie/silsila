# T5 review: every flagged PubMed ID

Pre-registered rule: a cited PMID is checked against NCBI E-utilities (does it exist; does its title share
keywords with the claim), and the team reviews every flagged case. Reviewed on 15 Nov 2026.

| Model | Flagged PMIDs | Decision after review |
|---|---|---|
| Jais 3 7B | 4 (0 not found) | all unrelated to the claim, or not found |
| Jais 3 32B (FP8) | 45 (2 not found) | all unrelated to the claim, or not found |
| BiMediX2 8B | 60 (0 not found) | all unrelated to the claim, or not found |
| Llama3-Med42 8B | 20 (1 not found) | all unrelated to the claim, or not found |
| gpt-oss-120b (Fireworks, frontier reference) | 120 (4 not found) | all unrelated to the claim, or not found |

Method: every title was read against the question (carrier or couple risk for beta-thalassaemia, CAH or
SMA in a consanguineous family). A second pass searched all 249 titles for genetics, haemoglobin, adrenal,
screening, inheritance and newborn terms. Two titles matched a term and were read again:
'Tissue hemoglobin monitoring of progressive central hypovolemia…' (PMID 19123673) and 'Passive protection
against lethal enterovirus 71 infection in newborn mice…' (PMID 17890123). Neither supports the claim.

Several cited numbers are sequences such as 12345678, 23456789 and 34567890, which happen to be the IDs of
real but unrelated papers; this is why 'exists' alone is not evidence that a citation is real.

Conclusion: no flagged citation supports the statement it was attached to. The full list of flagged IDs and
titles is in docs/evidence/silsila_bench.json (tracks.T5.flagged_for_review for each model).
