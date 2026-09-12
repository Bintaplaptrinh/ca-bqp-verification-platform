"""Unit resolution, exact match stage.

Public entry point:

    from pipelines.resolution import CsvUnitRegistryLookup, ResolutionInput, resolve

    lookup = CsvUnitRegistryLookup.from_dataset_dir()
    result = resolve(ResolutionInput(current_unit_text="Cong an Ha Noi"), lookup)
"""

from pipelines.resolution.contracts import (
    Candidate,
    MatchMethod,
    NormalizationLevel,
    OrganizationType,
    ResolutionInput,
    ResolutionResult,
    ResolutionStatus,
    ReviewReason,
    UnitRecord,
    ValidityNote,
)
from pipelines.resolution.registry_lookup import (
    CsvUnitRegistryLookup,
    RegistryIntegrityReport,
    UnitRegistryLookup,
)
from pipelines.resolution.resolver import EmptyResolutionInputError, resolve
from pipelines.resolution.text_normalize import (
    fold_ascii,
    normalize_code,
    normalize_name,
)

__all__ = [
    "Candidate",
    "CsvUnitRegistryLookup",
    "EmptyResolutionInputError",
    "MatchMethod",
    "NormalizationLevel",
    "OrganizationType",
    "RegistryIntegrityReport",
    "ResolutionInput",
    "ResolutionResult",
    "ResolutionStatus",
    "ReviewReason",
    "UnitRecord",
    "UnitRegistryLookup",
    "ValidityNote",
    "fold_ascii",
    "normalize_code",
    "normalize_name",
    "resolve",
]
