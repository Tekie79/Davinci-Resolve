"""Marker records independent from unstable Resolve proxy lifetimes."""

from dataclasses import dataclass, field, replace
from hashlib import sha1
from typing import Any, Optional


@dataclass
class MarkerRecord:
    scope_type: str
    scope_id: str
    frame: int
    start_frame: int
    end_frame: int
    duration_frames: int
    color: str
    name: str
    note: str
    custom_data: Optional[str] = None
    thumbnail_path: Optional[str] = None
    source_object: Any = field(default=None, repr=False, compare=False)

    @property
    def stable_key(self):
        raw = "%s|%s|%s|%s|%s|%s|%s" % (
            self.scope_type, self.scope_id, self.frame, self.color,
            self.name, self.note, self.duration_frames,
        )
        return sha1(raw.encode("utf-8")).hexdigest()

    def copy(self, **changes):
        return replace(self, **changes)

