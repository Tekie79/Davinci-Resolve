"""Media health report models."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class HealthIssue:
    category: str
    severity: str
    clip_id: str
    clip_name: str
    message: str
    expected: str = ""
    actual: str = ""
    thumbnail_path: Optional[str] = None


@dataclass
class HealthReport:
    scope: str
    scanned: int
    issues: List[HealthIssue] = field(default_factory=list)
    skipped_checks: Dict[str, str] = field(default_factory=dict)

    def summary(self):
        result = {"Healthy": max(0, self.scanned - len({item.clip_id for item in self.issues}))}
        for issue in self.issues:
            result[issue.category] = result.get(issue.category, 0) + 1
        return result

