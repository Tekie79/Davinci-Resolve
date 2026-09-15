"""Operation, preview, and result models shared by every manager."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4


@dataclass
class Change:
    object_id: str
    label: str
    field: str
    before: Any
    after: Any
    status: str = "Ready"
    source: Any = field(default=None, repr=False, compare=False)
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def changed(self):
        return self.before != self.after and self.status == "Ready"


@dataclass
class PreviewSummary:
    changes: List[Change] = field(default_factory=list)

    @property
    def changed(self):
        return sum(1 for item in self.changes if item.changed)

    @property
    def unchanged(self):
        return sum(1 for item in self.changes if item.status == "Unchanged" or item.before == item.after)

    @property
    def conflicts(self):
        return sum(1 for item in self.changes if item.status not in ("Ready", "Unchanged"))


@dataclass
class OperationResult:
    success: bool
    changed: int = 0
    unchanged: int = 0
    failed: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    details: List[Dict[str, Any]] = field(default_factory=list)

    def absorb(self, other):
        self.changed += other.changed
        self.unchanged += other.unchanged
        self.failed += other.failed
        self.warnings.extend(other.warnings)
        self.errors.extend(other.errors)
        self.details.extend(other.details)
        self.success = self.success and other.success
        return self


@dataclass
class OperationRecord:
    type: str
    label: str
    object_ids: List[str]
    before: Dict[str, Any]
    after: Dict[str, Any]
    reversible: bool = True
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result

    @classmethod
    def from_dict(cls, value):
        data = dict(value)
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

