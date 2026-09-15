"""Still capture queue model."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class StillQueueItem:
    id: str
    source_label: str
    frame: int
    timecode: str
    filename: str
    timeline_id: str
    timeline_name: str
    source_type: str
    source_id: str
    timeline: Any = field(default=None, repr=False, compare=False)
    source_object: Any = field(default=None, repr=False, compare=False)
    output_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    status: str = "Queued"
    metadata: Dict[str, str] = field(default_factory=dict)

