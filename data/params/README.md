# Parameter register

`loci.yaml` holds every population-genetics input the risk engine uses: published UAE carrier rates or
incidence, test detection rates and the population inbreeding coefficient, each with citation, PMID and
URL. Purpose: risk calculation only. Conversions to allele frequencies are formulas in
`backend/src/silsila/params.py`; `backend/tests/test_params.py` checks that every published value is
reproduced exactly. Conditions without the necessary UAE data are listed under `excluded_loci` with the
reason, and are not calculated.
