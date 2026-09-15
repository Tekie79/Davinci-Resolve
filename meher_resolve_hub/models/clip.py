"""Clip and metadata field models."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MetadataFieldDefinition:
    key: str
    label: str
    editable: bool = True
    type: str = "text"
    group: str = "Production"


@dataclass
class ClipRecord:
    unique_id: str
    media_pool_item: Any = field(repr=False, compare=False)
    timeline_items: List[Any] = field(default_factory=list, repr=False, compare=False)
    name: str = ""
    file_path: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
    properties: Dict[str, str] = field(default_factory=dict)
    thumbnail_path: Optional[str] = None

