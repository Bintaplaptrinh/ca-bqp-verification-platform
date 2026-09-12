# Data contract: unit resolution, exact match stage

Version: 1.0.0
Owner: resolution track
Implementation: `pipelines/resolution` (Python reference implementation)
Consumers: backend service, database schema, review user interface

This contract is language neutral. The Python dataclasses in
`pipelines/resolution/contracts.py` are the reference implementation of the same
shapes, and `ResolutionResult.to_dict()` produces exactly the response object
described below.

## Request

    {
      "current_unit_text": "Benh vien 108",   // string or null
      "unit_code_text": null,                  // string or null
      "as_of_date": "2026-09-12"               // ISO date or null, default today
    }

Rules:

- at least one of current_unit_text and unit_code_text must be a non blank
  string. A request that satisfies neither is a client error; the reference
  implementation raises EmptyResolutionInputError and an HTTP layer should map
  it to 422.
- as_of_date is the business date of the case. It drives validity filtering.
  Callers that omit it accept the server date.
- the caller supplies already separated fields. Splitting raw document text into
  these fields is the job of the document intelligence stage.

## Response

    {
      "resolution_status": "MATCHED",
      "organization_type": "BQP",
      "matched_unit": {
        "unit_id": 770,
        "unit_code": "BQP_BV108",
        "canonical_name": "...",
        "organization_type": "BQP",
        "unit_level": "cap_bo",
        "valid_from": "2018-01-01",
        "valid_to": null,
        "registry_version": "v2.0.0",
        "qa_confidence": "HIGH"
      },
      "match_method": "ALIAS_EXACT",
      "requires_review": false,
      "review_reason": null,
      "registry_version": "v2.0.0",
      "evidence": { ... }
    }

matched_unit is null for every status other than MATCHED.

## Enumerations

    resolution_status   MATCHED | AMBIGUOUS | NOT_FOUND | CONFLICT
    organization_type   BCA | BQP | OTHER | UNKNOWN
    match_method        CODE_EXACT | CODE_ALIAS_EXACT | CANONICAL_EXACT
                        | ALIAS_EXACT | NONE
    review_reason       CODE_NAME_CONFLICT | AMBIGUOUS_CANDIDATES
                        | UNRESOLVED_CODE | NAME_NOT_IN_REGISTRY
                        | OUT_OF_VALIDITY_WINDOW | REGISTRY_DATA_DEFECT
                        | null
    normalization_level STRICT | ASCII_FOLDED
    validity_note       OUT_OF_WINDOW | INVALID_WINDOW | null

Storage guidance: persist these as text with a check constraint rather than a
database enum type, so that adding a value in a later milestone does not require
a type migration.

## Evidence object

    {
      "input": { "current_unit_text": ..., "unit_code_text": ..., "as_of_date": ... },
      "as_of_date": "2026-09-12",
      "registry_version": "v2.0.0",
      "normalization": {
        "name_strict": "benh vien 108",
        "name_ascii_folded": "benh vien 108",
        "code": null
      },
      "candidates": {
        "by_code": [ candidate, ... ],
        "by_code_as_alias": [ candidate, ... ],
        "by_name": [ candidate, ... ]
      },
      "candidate_counts": { "by_code": 0, "by_code_as_alias": 0, "by_name": 1 },
      "decision": {
        "resolution_status": "MATCHED",
        "match_method": "ALIAS_EXACT",
        "matched_unit_id": 770,
        "requires_review": false,
        "review_reason": null,
        "note": null
      }
    }

Candidate object:

    {
      "unit_id": 770,
      "unit_code": "BQP_BV108",
      "canonical_name": "...",
      "organization_type": "BQP",
      "matched_value": "BV 108",
      "matched_field": "alias",
      "normalization_level": "ASCII_FOLDED",
      "is_valid_at": true,
      "validity_note": null,
      "valid_from": "2018-01-01",
      "valid_to": null
    }

Candidate lists are capped at 10 entries; candidate_counts carries the full
counts. Evidence must be stored verbatim, for example in a JSONB column, because
it is the audit record for the decision.

## Behaviour guarantees the consumers can rely on

1. organization_type is UNKNOWN whenever resolution_status is not MATCHED.
   NOT_FOUND is never reported as OTHER.
2. A unit outside its validity window at as_of_date is never returned as
   MATCHED, and never appears as matched_unit.
3. requires_review is true for every non MATCHED status, and also for a MATCHED
   result whose review_reason is not null. The user interface should surface the
   review reason next to the status.
4. An exact code match is never overridden by a name match. A name that resolves
   to a different unit yields CONFLICT, not a silent choice.
5. registry_version identifies the snapshot that produced the answer. Storing it
   with the result is mandatory for reproducibility.
6. The response is fully JSON serializable and contains no framework specific
   objects.

## Suggested persistence mapping

    verification_results
      result_id           uuid primary key
      case_id             uuid references cases
      resolution_status   text, check constraint over the enumeration
      organization_type   text, check constraint over the enumeration
      matched_unit_id     bigint null, references units
      match_method        text
      requires_review     boolean
      review_reason       text null
      registry_version    text
      evidence            jsonb
      created_at          timestamptz

A review queue row should be created whenever requires_review is true, carrying
review_reason as the queue reason.

## Versioning

Any change to the enumerations or to the evidence keys is a contract change and
requires a version bump here, plus a note in the resolution README. Adding a new
review_reason value is additive and only requires a minor bump, provided
consumers treat unknown values as review required.
