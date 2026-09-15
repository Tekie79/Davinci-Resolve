"""Visual clip records, verified metadata edits, batch diffs, CSV scaffolding, and undo."""

import csv
from pathlib import Path

from ..models.clip import ClipRecord, MetadataFieldDefinition
from ..models.operation import Change, OperationRecord, OperationResult, PreviewSummary
from ..utils import proxy_id


COMMON_FIELDS = [
    MetadataFieldDefinition("Scene", "Scene", True, group="Production"),
    MetadataFieldDefinition("Shot", "Shot", True, group="Production"),
    MetadataFieldDefinition("Take", "Take", True, group="Production"),
    MetadataFieldDefinition("Camera #", "Camera", True, group="Camera"),
    MetadataFieldDefinition("Camera ID", "Camera ID", True, group="Camera"),
    MetadataFieldDefinition("Reel Name", "Reel", True, group="Camera"),
    MetadataFieldDefinition("Keywords", "Keywords", True, group="Descriptive"),
    MetadataFieldDefinition("Comments", "Comments", True, group="Editorial"),
    MetadataFieldDefinition("Description", "Description", True, group="Descriptive"),
    MetadataFieldDefinition("Good Take", "Good Take", True, group="Editorial"),
    MetadataFieldDefinition("Production Name", "Production Name", True, group="Production"),
]


def metadata_operation(before, operation, value, other_value=""):
    before = "" if before is None else str(before)
    value = "" if value is None else str(value)
    if operation == "Set": return value
    if operation == "Clear": return ""
    if operation == "Append": return before + value
    if operation == "Prepend": return value + before
    if operation == "Find / Replace" or operation == "Find/Replace":
        return before.replace(value, str(other_value))
    if operation == "Copy Field": return str(other_value or "")
    if operation == "Leave unchanged": return before
    raise ValueError("Unsupported metadata operation: %s" % operation)


class MetadataService:
    def __init__(self, history=None):
        self.history = history
        self._clips = {}
        if history:
            history.register("metadata", self.undo)

    def build_records(self, clips, timeline_items=None):
        timeline_items = list(timeline_items or [])
        linked = {}
        for item in timeline_items:
            try:
                media_item = item.GetMediaPoolItem()
                linked.setdefault(proxy_id(media_item), []).append(item)
            except Exception:
                continue
        records = []
        for clip in clips:
            identity = proxy_id(clip)
            try: metadata = dict(clip.GetMetadata() or {})
            except Exception: metadata = {}
            try: properties = dict(clip.GetClipProperty() or {})
            except Exception: properties = {}
            try: name = str(clip.GetName() or "")
            except Exception: name = str(properties.get("Clip Name") or properties.get("File Name") or "Clip")
            path = str(properties.get("File Path") or properties.get("File Name") or "")
            record = ClipRecord(identity, clip, linked.get(identity, []), name, path, metadata, properties)
            records.append(record)
            self._clips[identity] = record
        return records

    @staticmethod
    def available_fields(record):
        actual = set(record.metadata)
        result = []
        known = {item.key for item in COMMON_FIELDS}
        for item in COMMON_FIELDS:
            # Resolve accepts SetMetadata dictionaries, but verify after write.
            result.append(MetadataFieldDefinition(item.key, item.label, item.editable, item.type, item.group))
        for key in sorted(actual - known):
            result.append(MetadataFieldDefinition(str(key), str(key), True, group="Custom"))
        return result

    @staticmethod
    def search(records, query="", missing_field=""):
        query = str(query or "").casefold()
        result = []
        for record in records:
            haystack = " ".join([record.name, record.file_path] + [str(value) for value in record.metadata.values()]).casefold()
            if query and query not in haystack:
                continue
            if missing_field and str(record.metadata.get(missing_field, "")).strip():
                continue
            result.append(record)
        return result

    def set_field(self, record, field, value, record_history=True):
        clip = record.media_pool_item
        try: current = str((clip.GetMetadata() or {}).get(field, ""))
        except Exception as exc: return OperationResult(False, failed=1, errors=["Could not read metadata: %s" % exc])
        value = str(value or "")
        if current == value:
            return OperationResult(True, unchanged=1)
        try:
            returned = bool(clip.SetMetadata({field: value}))
            actual = str((clip.GetMetadata() or {}).get(field, ""))
        except Exception as exc:
            return OperationResult(False, failed=1, errors=["Metadata update failed: %s" % exc])
        if not returned or actual != value:
            return OperationResult(False, failed=1, errors=["Resolve did not retain %s for %s." % (field, record.name)])
        record.metadata[field] = value
        if record_history and self.history:
            self.history.add(OperationRecord("metadata", "Edit %s" % field, [record.unique_id], {record.unique_id: {field: current}}, {record.unique_id: {field: value}}))
        return OperationResult(True, changed=1)

    def preview_batch(self, records, field, operation, value="", replacement="", blanks_only=False, copy_field=""):
        changes = []
        for record in records:
            before = str(record.metadata.get(field, ""))
            if blanks_only and before.strip():
                changes.append(Change(record.unique_id, record.name, field, before, before, "Unchanged", source=record))
                continue
            try:
                other = record.metadata.get(copy_field, "") if operation == "Copy Field" else replacement
                after = metadata_operation(before, operation, value, other)
                status = "Unchanged" if before == after else "Ready"
            except ValueError:
                after, status = before, "Invalid"
            changes.append(Change(record.unique_id, record.name, field, before, after, status, source=record))
        return PreviewSummary(changes)

    def apply_preview(self, preview, label="Batch metadata edit"):
        result, before, after, ids = OperationResult(True), {}, {}, []
        for change in preview.changes:
            if not change.changed:
                result.unchanged += 1
                if change.status not in ("Ready", "Unchanged"): result.warnings.append("%s: %s" % (change.label, change.status))
                continue
            item = self.set_field(change.source, change.field, change.after, record_history=False)
            result.absorb(item)
            if item.success and item.changed:
                ids.append(change.object_id)
                before[change.object_id] = {change.field: change.before}
                after[change.object_id] = {change.field: change.after}
        result.success = result.failed == 0
        if ids and self.history:
            self.history.add(OperationRecord("metadata", label, ids, before, after))
        return result

    def undo(self, operation):
        result = OperationResult(True)
        for identity in operation.object_ids:
            record = self._clips.get(identity)
            if not record:
                result.failed += 1; result.errors.append("Clip %s is no longer loaded." % identity); continue
            expected = operation.after.get(identity, {})
            try: actual = dict(record.media_pool_item.GetMetadata() or {})
            except Exception: actual = {}
            if any(str(actual.get(key, "")) != str(value) for key, value in expected.items()):
                result.failed += 1; result.errors.append("%s changed after the operation; undo skipped." % record.name); continue
            for key, value in operation.before.get(identity, {}).items():
                result.absorb(self.set_field(record, key, value, record_history=False))
        result.success = result.failed == 0
        return result

    @staticmethod
    def export_csv(records, path, fields=None):
        path = Path(path)
        fields = list(fields or sorted({key for record in records for key in record.metadata}))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Unique ID", "Clip Name"] + fields)
            writer.writeheader()
            for record in records:
                row = {"Unique ID": record.unique_id, "Clip Name": record.name}
                row.update({key: record.metadata.get(key, "") for key in fields})
                writer.writerow(row)
        return path

    @staticmethod
    def preview_csv_import(records, path):
        indexed = {item.unique_id: item for item in records}
        changes = []
        with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                record = indexed.get(str(row.get("Unique ID", "")))
                if not record:
                    continue
                for field, value in row.items():
                    if field in ("Unique ID", "Clip Name"):
                        continue
                    before = str(record.metadata.get(field, ""))
                    after = str(value or "")
                    changes.append(Change(record.unique_id, record.name, field, before, after, "Ready" if before != after else "Unchanged", source=record))
        return PreviewSummary(changes)
