"""Application-owned operation history with guarded undo dispatch."""

import json
from pathlib import Path

from .models.operation import OperationRecord, OperationResult


class OperationHistory:
    def __init__(self, path=None, limit=100):
        self.path = Path(path) if path else None
        self.limit = int(limit)
        self.records = []
        self.undo_handlers = {}

    def register(self, operation_type, handler):
        self.undo_handlers[operation_type] = handler

    def add(self, record):
        if record.reversible:
            self.records.append(record)
            self.records = self.records[-self.limit:]
            self.save()
        return record

    def peek(self):
        return self.records[-1] if self.records else None

    def undo(self):
        record = self.peek()
        if not record:
            return OperationResult(False, errors=["Nothing to undo."])
        handler = self.undo_handlers.get(record.type)
        if not handler:
            return OperationResult(False, errors=["Undo is unavailable for %s." % record.label])
        result = handler(record)
        if result.success:
            self.records.pop()
            self.save()
        return result

    def save(self):
        if not self.path:
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps([record.to_dict() for record in self.records], indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return self.path

    def load(self):
        if self.path and self.path.is_file():
            try:
                values = json.loads(self.path.read_text(encoding="utf-8"))
                self.records = [OperationRecord.from_dict(item) for item in values if item.get("reversible")]
            except Exception:
                self.records = []
        return self.records
