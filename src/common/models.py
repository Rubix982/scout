# src/common/models.py
"""Domain models shared across layers.

`Role` lives here rather than in `src/sources/ats/` because both the source
adapters (which produce it) and the storage layer (which persists it) need it.
Having storage import from sources was a layering inversion, and it produced an
import cycle the moment the snapshot runner needed both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

# Evergreen / talent-pool postings: real board entries that are not real
# vacancies. Checkly's board leads with "Don't see the role you're looking for?
# Join our Talent Community!". Counting these as roles inflates every total and
# pollutes the department mix.
#
# They are FLAGGED, never dropped: this is a heuristic on free text, so it will
# occasionally misfire. The report states how many it set aside so the number is
# auditable rather than silently applied.
_EVERGREEN_PATTERNS = (
    r"talent (community|pool|network|pipeline)",
    r"don'?t see (the|a) role",
    r"can'?t find (the|a) (role|job)",
    r"(general|open|speculative|spontaneous) application",
    r"future opportunit",
    r"join our (talent|team) (community|network)",
    r"^expression of interest",
)
_EVERGREEN_RE = re.compile("|".join(_EVERGREEN_PATTERNS), re.I)


def is_evergreen(title: str) -> bool:
    """True for talent-pool style postings that are not actual vacancies."""
    return bool(_EVERGREEN_RE.search(title or ""))


@dataclass(frozen=True)
class Role:
    """One open role, normalised across ATS platforms."""

    platform: str
    token: str
    external_id: str
    title: str
    location: str
    department: str
    url: str
    first_published: Optional[str]
    updated_at: Optional[str]
    raw: str

    @property
    def identity(self) -> Tuple[str, str, str]:
        """Stable identity for diffing.

        Keyed on the ATS id, never the title: R-002 noted reposts and title
        churn, and keying on title would manufacture phantom "new role" events.
        """
        return (self.platform, self.token, self.external_id)

    @property
    def is_evergreen(self) -> bool:
        """See `is_evergreen` -- a talent-pool posting, not a real vacancy."""
        return is_evergreen(self.title)
