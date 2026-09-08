# src/common/entities.py
"""Entity kinds (E-010).

The company list holds two different kinds of thing, and conflating them is what
made R-002's coverage number meaningless:

- an **employer** yields *roles* to track
- a **source** (board / agency / investor / community) yields *companies* to add

Scout previously modelled only employers, so a job board looked like an employer
whose token could not be resolved. ~16 of 36 rows are sources.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet


class EntityType(str, Enum):
    EMPLOYER = "employer"
    BOARD = "board"
    AGENCY = "agency"
    INVESTOR = "investor"
    COMMUNITY = "community"
    UNKNOWN = "unknown"

    @property
    def is_source(self) -> bool:
        """True for kinds that yield companies rather than roles."""
        return self in _SOURCE_KINDS


_SOURCE_KINDS = frozenset(
    {
        EntityType.BOARD,
        EntityType.AGENCY,
        EntityType.INVESTOR,
        EntityType.COMMUNITY,
    }
)

VALID_VALUES: FrozenSet[str] = frozenset(e.value for e in EntityType)


def parse(value: str) -> str:
    """Normalise a sheet `Type` cell into an EntityType value.

    Blank maps to `unknown`, **never** to `employer`. Defaulting a blank to
    employer would recreate the silent failure this module exists to remove: a
    misclassified row would be attempted for role fetching, fail to resolve, and
    be indistinguishable from a genuine coverage gap.

    An unrecognised value raises -- a typo must not quietly become `unknown`
    either, or the same silence returns by a different route.
    """
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return EntityType.UNKNOWN.value
    if cleaned not in VALID_VALUES:
        raise ValueError(
            f"unrecognised entity type {value!r}; expected one of "
            f"{', '.join(sorted(VALID_VALUES))}"
        )
    return cleaned
