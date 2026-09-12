# Unit Resolution - Exact Match Engine

Deterministic resolution of a work unit mention against the Master Unit Registry.
This module answers one question: which registry unit does this input denote, and
is the evidence strong enough to accept the answer without a human.

It is a plain Python package. It does not import a web framework, an ORM or a
database driver, and it does not read configuration from the environment. The
system team builds the database, the API and the frontend on top of it.

## Scope

In scope:

- exact match on unit code
- exact match on canonical name
- exact match on approved alias
- validity period filtering against the date of the case
- conflict and ambiguity detection
- full evidence for every outcome

Out of scope, by design:

- fuzzy, phonetic, BM25 or embedding matching, ranking, scoring, calibration
  (next milestone of the resolution track)
- OCR, document parsing, named entity recognition, relation extraction
  (document intelligence stage)
- subject group classification and the policy or eligibility engine
- database schema, HTTP API, user interface, authentication, audit storage
  (system team)

## Layout

    pipelines/resolution/
      contracts.py         data contracts and enums, the public vocabulary
      text_normalize.py    normalization rules shared by index and query
      registry_lookup.py   UnitRegistryLookup protocol plus CSV implementation
      resolver.py          the cascade, the decision rules, the evidence
      tests/               unit tests and the golden regression suite

## Quick start

    from datetime import date
    from pipelines.resolution import CsvUnitRegistryLookup, ResolutionInput, resolve

    lookup = CsvUnitRegistryLookup.from_dataset_dir()   # datasets/samples by default
    result = resolve(
        ResolutionInput(
            current_unit_text="Benh vien 108",
            unit_code_text=None,
            as_of_date=date(2026, 9, 12),
        ),
        lookup,
    )

    result.resolution_status    # MATCHED
    result.organization_type    # BQP
    result.match_method         # ALIAS_EXACT
    result.requires_review      # False
    result.matched_unit.unit_id # 770
    result.to_dict()            # JSON serializable, evidence included

`resolve` raises `EmptyResolutionInputError` when neither a unit name nor a unit
code is supplied. Every other outcome, including NOT_FOUND and CONFLICT, is a
normal return value, never an exception.

## Cascade

1. unit code, exact match against the code index
2. unit code text read as an approved alias, only when step 1 returned nothing
   (documents often carry a short form such as C08 instead of BCA_C08)
3. canonical name, exact match
4. approved alias, exact match

An exact code match is the strongest evidence and is never overridden by a name
match. A name that resolves to a different unit does not override the code, it
produces CONFLICT.

## Decision table

    code side        name side            outcome     review reason
    ---------------- -------------------- ----------- ----------------------
    one unit         same unit            MATCHED     none
    one unit         different unit       CONFLICT    CODE_NAME_CONFLICT
    one unit         several units, one   MATCHED     none
                     of them the code one
    one unit         no match, name given MATCHED     NAME_NOT_IN_REGISTRY
    one unit         not supplied         MATCHED     none
    several units    any                  AMBIGUOUS   AMBIGUOUS_CANDIDATES
    no match         one unit             MATCHED     UNRESOLVED_CODE
    not supplied     one unit             MATCHED     none
    not supplied     several units        AMBIGUOUS   AMBIGUOUS_CANDIDATES
    no valid match   no valid match       NOT_FOUND   see below

NOT_FOUND review reasons, in priority order:

- REGISTRY_DATA_DEFECT: the only candidates carry an invalid validity window
- OUT_OF_VALIDITY_WINDOW: candidates exist but none is valid at the case date
- UNRESOLVED_CODE: a code was supplied and matches nothing
- NAME_NOT_IN_REGISTRY: a name was supplied and matches nothing

Invariants enforced:

- organization_type is UNKNOWN unless the status is MATCHED. NOT_FOUND never
  becomes OTHER.
- a unit outside its validity window is never returned as MATCHED.
- requires_review is true for every non MATCHED status and for every MATCHED
  result that carries a review reason.

## Normalization

Two deterministic levels, both exact string equality after normalization.

    STRICT        Unicode NFC, trim, collapse inner whitespace, case fold.
                  Diacritics preserved.
    ASCII_FOLDED  STRICT plus d-stroke folded to d and all combining marks
                  removed.

The strict index is consulted first. The folded index is consulted only when the
strict index returns nothing, and the level that produced the match is recorded
in the evidence. The folded level is required because real inputs drop
diacritics, and because the generated no_accent aliases in the registry still
keep the d-stroke character.

Unit codes are normalized separately: trim, collapse inner whitespace, strip
surrounding punctuation, upper case. Underscores, hyphens and digits are kept.

Alias rows with alias_type typo_ocr, or generator_source noise_injector, are
excluded from the default index. They are synthetic noise for model training,
not aliases approved by a human, and rule 2 of the decision policy only allows
auto accept on approved entries.

## Result and evidence

`ResolutionResult` carries resolution_status, organization_type, matched_unit,
match_method, requires_review, review_reason, registry_version and evidence.

The evidence dictionary is the audit record and is JSON serializable:

    input               the request as received
    as_of_date          the date the validity filter used
    registry_version    the snapshot the answer came from
    normalization       the normalized forms actually used for lookup
    candidates          by_code, by_code_as_alias, by_name, each entry with
                        unit id, code, canonical name, organization type,
                        matched value, matched field, normalization level,
                        is_valid_at, validity note, validity window
    candidate_counts    full counts, since candidate lists are capped at 10
    decision            status, method, matched unit id, review flag, reason,
                        and a short note explaining the branch taken

Storing only the status and the unit id is not sufficient. The candidate lists
are what make a conflict or an abstention explainable later.

## Data inputs

    datasets/samples/master_units.csv                 1633 canonical units
    datasets/samples/unit_aliases.csv                 10124 generated aliases
    datasets/samples/unit_aliases_approved_delta.csv  aliases approved after QA
    datasets/samples/master_units.csv.sha256          artifact checksum

master_units.csv and unit_aliases.csv are regenerated by
`pipelines/registry_ingestion/Registy.py` and `pipelines/registry_ingestion/Aliases.py`.
The loaded snapshot reproduces the registry_checksum recorded in
datasets/manifests/dataset_manifest.yaml
(751ebf50385c4f04b9c743be813a037fd49889ecc8905968b7843be761f7a13d), which proves
that the registry used here is the same one the published dataset was built from.
`CsvUnitRegistryLookup.integrity_report()` returns that checksum together with the
data quality signals listed under known issues.

The delta file is the path for aliases approved after the dataset was published.
It keeps human approved additions separate from generated data, so the dataset
manifest and the machine learning lineage stay intact. Columns: unit_code,
alias_name, alias_type, generator_source, source_ref, approved_by, approved_at,
note.

## Integration guide for the system team

The seam is the `UnitRegistryLookup` protocol in registry_lookup.py:

    registry_version() -> str
    find_by_code(code_text, as_of) -> list[Candidate]
    find_by_name(name_text, as_of, approved_only=True) -> list[Candidate]

To serve from PostgreSQL, implement that protocol over the registry tables and
pass the instance to `resolve`. Nothing in resolver.py needs to change.

Requirements for any implementation:

1. Build the index columns with `text_normalize.normalize_name`,
   `text_normalize.fold_ascii` and `text_normalize.normalize_code`. Two
   implementations that normalize differently will disagree about what an exact
   match is. Store the normalized forms as generated columns and index them.
2. Return candidates that are outside their validity window as well, with
   is_valid_at false and the validity note set. The resolver needs them to tell
   an unknown unit apart from a unit that only existed in the past, and the
   evidence needs them to explain the abstention.
3. Prefer strict matches over folded matches inside find_by_name, exactly as the
   CSV implementation does: query the strict column first and only fall back to
   the folded column when it returns no rows.
4. Exclude unapproved alias rows when approved_only is true.
5. Keep one published snapshot per registry_version and resolve against a single
   snapshot for the whole request.

Suggested minimum column set, mapped from the CSV artifacts:

    units        unit_id, unit_code, canonical_name, organization_type,
                 unit_level, valid_from, valid_to, registry_version,
                 qa_confidence
    unit_names   unit_id, name, name_strict, name_folded, name_type,
                 is_approved, source_ref, valid_from, valid_to

A code that appears twice with disjoint validity windows is legitimate and must
be preserved, see known issues.

## Tests

    pytest pipelines/resolution/tests
    ruff check pipelines/resolution

No Docker and no database required. Current state: 51 passed, 1 skipped,
2 expected failures.

Hard case coverage, from datasets/samples/hard_cases.jsonl, driven by
tests/fixtures/hard_case_inputs.json:

    in scope and passing (13): HC001 HC002 HC003 HC004 HC005 HC006 HC007
                               HC009 HC011 HC012 HC013 HC014 HC016
    deferred, strict xfail (2): HC010 HC015
    out of scope, skipped (1): HC008

The deferred cases stay in the suite as strict expected failures. If a later
change makes one of them pass, the suite fails and forces the fixture to be
updated, so the backlog cannot rot silently.

The fixture supplies the structured input that the document intelligence stage
will later produce from raw text. Encoding it by hand is deliberate: it keeps the
golden suite honest about what this module is actually responsible for.

## Known issues and findings

1. Inverted validity windows, 38 units. Every Ha Tay unit carries valid_to
   2008-08-01 with valid_from 2018-01-01, so it is valid at no date at all.
   Cause: `Registy.py` derives valid_from from year_start, which is 2018 for
   every crawled row, while valid_to comes from the historical merge table. Fix
   belongs to the registry ingestion pipeline and should ship as registry
   v2.0.1. Until then the resolver reports REGISTRY_DATA_DEFECT instead of
   silently answering NOT_FOUND, and HC010 stays an expected failure.
2. Repeated unit codes are correct, not a defect. BQP_F308 and BQP_F312 each
   appear twice because the divisions moved from Quan doan 1 to Quan doan 12
   after the 2023 merge. The two rows have disjoint validity windows, so a code
   lookup filtered by the case date returns exactly one unit. The clean stage
   warning about duplicate unit codes can be closed with this explanation.
   `integrity_report().duplicate_codes_same_window` is empty, which is the
   condition that actually matters.
3. Alias collisions. 183 normalized alias strings map to more than one unit at
   the strict level and 205 at the folded level, mostly generated initial
   abbreviations. They surface as AMBIGUOUS rather than a silent pick.
4. Alias coverage gaps. Short forms that appear in real documents are missing
   from the generated dictionary, for example CA HN. They are added through the
   approved delta file after review, not by weakening the matching rules.

## Next milestone

Fuzzy and semantic candidate generation, ranking, top 1 to top 2 margin,
calibration and threshold configuration. That milestone should reuse this
contract, add scores to the evidence, and turn HC001, HC010 and HC015 into
passing cases.
