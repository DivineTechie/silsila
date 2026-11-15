# Demo index result (FHIR R4B)

`newborn_cah_index_result.json` is a FICTIONAL record: an invented newborn, an invented identifier and an
invented result. It is shaped like the record that starts a cascade: a Patient, a genomics Observation
(LOINC 69548-6 with gene, allelic state and clinical significance) and a confirmed Condition.

It is "Malaffi-style" only in the sense that it is a FHIR record of the kind a health information exchange
carries. It follows no Malaffi interface specification: the team has not seen one, and a pilot would map to
whatever profile the exchange publishes.

Silsila reads it at counsellor intake (`backend/src/silsila/api/fhir_import.py`, Cases tab, "Import an index
result"). The name, identifier and date of birth in the file are deliberately present so the import can show
that it does not store them.
