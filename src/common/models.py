# src/common/models.py
"""Domain models shared across layers.

`Role` lives here rather than in `src/sources/ats/` because both the source
adapters (which produce it) and the storage layer (which persists it) need it.
Having storage import from sources was a layering inversion, and it produced an
import cycle the moment the snapshot runner needed both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


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
