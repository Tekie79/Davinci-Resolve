"""Marker browsing, filtering, safe mutation, batch preview, and rollback."""

import json

from ..constants import MARKER_COLORS
from ..models.marker import MarkerRecord
from ..models.operation import Change, OperationRecord, OperationResult, PreviewSummary
from ..timecode import clamp_frame
from ..utils import proxy_id


def marker_info_value(info, *names, **kwargs):
    default = kwargs.get("default", "")
    for name in names:
        if name in info:
            return info[name]
    return default


class MarkerService:
    def __init__(self, context_service, history=None):
        self.context_service = context_service
        self.history = history
        self._index = {}
        if history:
            history.register("marker", self.undo)

    def list_markers(self, timeline=None):
        context = self.context_service.refresh_context()
        timeline = timeline or context.timeline
        if not timeline:
            return []
        try:
            raw = dict(timeline.GetMarkers() or {})
        except Exception:
            raw = {}
        scope_id = proxy_id(timeline, context.timeline_id)
        records = []
        for frame, info in raw.items():
            info = dict(info or {})
            duration = max(1, int(marker_info_value(info, "duration", "Duration", default=1) or 1))
            start = int(round(float(frame)))
            custom = marker_info_value(info, "customData", "custom_data", default=None)
            if custom in (None, ""):
                try:
                    custom = timeline.GetMarkerCustomData(frame) or None
                except Exception:
                    custom = None
            record = MarkerRecord(
                "timeline", scope_id, start, start, start + duration - 1, duration,
                str(marker_info_value(info, "color", "Color", default="Blue")),
                str(marker_info_value(info, "name", "Name", default="")),
                str(marker_info_value(info, "note", "Note", default="")),
                custom, source_object=timeline,
            )
            records.append(record)
            self._index[record.stable_key] = record
        return sorted(records, key=lambda item: item.start_frame)

    @staticmethod
    def filter_markers(records, search="", color="All", marker_type="All", with_notes=None, sort="Timecode"):
        query = str(search or "").casefold()
        result = []
        for item in records:
            if query and query not in (item.name + " " + item.note + " " + (item.custom_data or "")).casefold():
                continue
            if color not in ("", "All") and item.color != color:
                continue
            if marker_type == "Point" and item.duration_frames > 1:
                continue
            if marker_type == "Range" and item.duration_frames <= 1:
                continue
            if with_notes is True and not item.note.strip():
                continue
            if with_notes is False and item.note.strip():
                continue
            result.append(item)
        key = {
            "Name": lambda value: value.name.casefold(),
            "Color": lambda value: value.color.casefold(),
            "Duration": lambda value: value.duration_frames,
        }.get(sort, lambda value: value.start_frame)
        return sorted(result, key=key)

    def _validate(self, record, candidate):
        if candidate.color not in MARKER_COLORS:
            return "Unsupported marker color: %s" % candidate.color
        if candidate.duration_frames < 1:
            return "Marker duration must be at least one frame."
        if candidate.start_frame < 0:
            return "Marker start cannot be negative."
        if candidate.end_frame != candidate.start_frame + candidate.duration_frames - 1:
            return "Marker start, end, and duration are inconsistent."
        timeline = record.source_object
        try:
            lower = int(timeline.GetStartFrame())
            upper = int(timeline.GetEndFrame())
            # Timeline marker frame ids are relative offsets even when timeline start is non-zero.
            span = max(0, upper - lower)
            if candidate.start_frame > span or candidate.end_frame > span:
                return "Marker range is outside the timeline."
        except Exception:
            pass
        return ""

    @staticmethod
    def _snapshot(record):
        return {
            "scope_type": record.scope_type, "scope_id": record.scope_id,
            "frame": record.frame, "start_frame": record.start_frame,
            "end_frame": record.end_frame, "duration_frames": record.duration_frames,
            "color": record.color, "name": record.name, "note": record.note,
            "custom_data": record.custom_data, "thumbnail_path": record.thumbnail_path,
        }

    @staticmethod
    def _matches(info, record):
        if not info:
            return False
        duration = int(marker_info_value(info, "duration", "Duration", default=1) or 1)
        custom = marker_info_value(info, "customData", "custom_data", default=None)
        if custom is None:
            try:
                custom = record.source_object.GetMarkerCustomData(record.frame)
            except Exception:
                custom = None
        expected_custom = "" if record.custom_data is None else str(record.custom_data)
        actual_custom = "" if custom is None else str(custom)
        return (
            str(marker_info_value(info, "color", "Color", default="")) == record.color
            and str(marker_info_value(info, "name", "Name", default="")) == record.name
            and str(marker_info_value(info, "note", "Note", default="")) == record.note
            and duration == record.duration_frames
            and actual_custom == expected_custom
        )

    def replace_marker(self, original, candidate, record_history=True, label="Edit marker"):
        """Validate, delete, recreate, verify, and rollback if recreation fails."""
        error = self._validate(original, candidate)
        if error:
            return OperationResult(False, failed=1, errors=[error])
        timeline = original.source_object
        try:
            markers = dict(timeline.GetMarkers() or {})
        except Exception as exc:
            return OperationResult(False, failed=1, errors=["Could not read current markers: %s" % exc])
        current = markers.get(original.frame)
        if not self._matches(current, original):
            return OperationResult(False, failed=1, errors=["The marker changed in Resolve. Refresh before editing."])
        if candidate.start_frame != original.frame and candidate.start_frame in markers:
            return OperationResult(False, failed=1, errors=["Another marker already exists at the target frame."])
        if self._snapshot(original) == self._snapshot(candidate):
            return OperationResult(True, unchanged=1)
        try:
            deleted = bool(timeline.DeleteMarkerAtFrame(original.frame))
        except Exception:
            deleted = False
        if not deleted:
            return OperationResult(False, failed=1, errors=["Resolve did not delete the original marker."])

        try:
            created = bool(timeline.AddMarker(candidate.start_frame, candidate.color, candidate.name, candidate.note, candidate.duration_frames, candidate.custom_data or ""))
            verified = self._matches(dict(timeline.GetMarkers() or {}).get(candidate.start_frame), candidate)
        except Exception:
            created, verified = False, False
        if created and verified:
            if record_history and self.history:
                self.history.add(OperationRecord("marker", label, [original.stable_key], {original.stable_key: self._snapshot(original)}, {original.stable_key: self._snapshot(candidate)}))
            return OperationResult(True, changed=1, details=[{"before": self._snapshot(original), "after": self._snapshot(candidate)}])

        try:
            # Remove an unverified partial replacement before restoring.
            replacement = dict(timeline.GetMarkers() or {}).get(candidate.start_frame)
            if replacement:
                timeline.DeleteMarkerAtFrame(candidate.start_frame)
            restored = bool(timeline.AddMarker(original.frame, original.color, original.name, original.note, original.duration_frames, original.custom_data or ""))
            rollback_verified = restored and self._matches(dict(timeline.GetMarkers() or {}).get(original.frame), original)
        except Exception:
            rollback_verified = False
        if rollback_verified:
            return OperationResult(False, failed=1, errors=["Marker update failed; the original marker was restored."])
        return OperationResult(False, failed=1, errors=["CRITICAL: marker update and rollback both failed. Restore the marker manually from the operation details."], details=[{"original": self._snapshot(original)}])

    def add_marker(self, timeline, frame, color, name, note="", duration=1, custom_data="", label="Add marker"):
        """Add and verify a marker, recording a guarded Undo operation."""
        context = self.context_service.refresh_context()
        scope_id = proxy_id(timeline, context.timeline_id)
        frame = int(frame); duration = max(1, int(duration))
        record = MarkerRecord("timeline", scope_id, frame, frame, frame + duration - 1, duration, str(color), str(name), str(note), custom_data or None, source_object=timeline)
        error = self._validate(record, record)
        if error:
            return OperationResult(False, failed=1, errors=[error])
        try:
            if frame in dict(timeline.GetMarkers() or {}):
                return OperationResult(False, failed=1, errors=["A marker already exists at the playhead."])
            created = bool(timeline.AddMarker(frame, record.color, record.name, record.note, record.duration_frames, custom_data or ""))
            verified = created and self._matches(dict(timeline.GetMarkers() or {}).get(frame), record)
        except Exception as exc:
            return OperationResult(False, failed=1, errors=["Resolve could not add the marker: %s" % exc])
        if not verified:
            return OperationResult(False, failed=1, errors=["Resolve did not add the marker."])
        if self.history:
            self.history.add(OperationRecord("marker", label, [record.stable_key], {record.stable_key: {"deleted": True}}, {record.stable_key: self._snapshot(record)}))
        return OperationResult(True, changed=1, details=[{"after": self._snapshot(record)}])

    @staticmethod
    def edit_range(record, start=None, end=None, duration=None, move=None):
        if move is not None:
            new_start = record.start_frame + int(move)
            return record.copy(frame=new_start, start_frame=new_start, end_frame=new_start + record.duration_frames - 1)
        new_start = record.start_frame if start is None else int(start)
        if duration is not None:
            new_duration = max(1, int(duration))
            new_end = new_start + new_duration - 1
        elif end is not None:
            new_end = int(end)
            new_duration = new_end - new_start + 1
        else:
            new_end = record.end_frame
            new_duration = new_end - new_start + 1
        return record.copy(frame=new_start, start_frame=new_start, end_frame=new_end, duration_frames=new_duration)

    def preview_batch(self, records, field, operation, value):
        changes = []
        for record in records:
            if field == "range":
                before = "%s..%s (%s)" % (record.start_frame, record.end_frame, record.duration_frames)
            elif field == "delete":
                before = "Marker"
            else:
                before = getattr(record, field)
            after, status = before, "Ready"
            try:
                if field in ("name", "note"):
                    text = str(value or "")
                    if operation == "Set": after = text
                    elif operation == "Prefix": after = text + str(before)
                    elif operation == "Suffix": after = str(before) + text
                    elif operation == "Append": after = str(before) + text
                    elif operation == "Prepend": after = text + str(before)
                    elif operation == "Clear": after = ""
                    elif operation == "Find/Replace":
                        old, replacement = text.split("=>", 1)
                        after = str(before).replace(old, replacement)
                    else: status = "Invalid"
                elif field == "color":
                    after = str(value)
                    if after not in MARKER_COLORS: status = "Invalid"
                elif field == "duration_frames":
                    amount = int(value)
                    if operation == "Set": after = amount
                    elif operation == "Extend End": after = int(before) + amount
                    elif operation == "Contract End": after = int(before) - amount
                    else: status = "Invalid"
                    if int(after) < 1: status = "Invalid"
                elif field == "start_frame" and operation == "Move":
                    after = int(before) + int(value)
                elif field == "range":
                    amount = int(value)
                    if operation == "Set Duration": candidate = self.edit_range(record, duration=amount)
                    elif operation == "Extend Start": candidate = self.edit_range(record, start=record.start_frame - amount)
                    elif operation == "Extend End": candidate = self.edit_range(record, end=record.end_frame + amount)
                    elif operation == "Contract Start": candidate = self.edit_range(record, start=record.start_frame + amount)
                    elif operation == "Contract End": candidate = self.edit_range(record, end=record.end_frame - amount)
                    else: candidate, status = record, "Invalid"
                    after = "%s..%s (%s)" % (candidate.start_frame, candidate.end_frame, candidate.duration_frames)
                elif field == "delete":
                    before, after = "Marker", "Deleted"
                else:
                    status = "Invalid"
            except Exception:
                status = "Invalid"
            if before == after and status == "Ready": status = "Unchanged"
            context = {"candidate": candidate} if field == "range" and status != "Invalid" else {}
            changes.append(Change(record.stable_key, record.name or "Marker", field, before, after, status, source=record, context=context))
        return PreviewSummary(changes)

    def apply_preview(self, preview, label="Batch marker edit"):
        result = OperationResult(True)
        before, after, keys = {}, {}, []
        for change in preview.changes:
            if not change.changed:
                result.unchanged += 1
                if change.status not in ("Ready", "Unchanged"):
                    result.warnings.append("%s: %s" % (change.label, change.status))
                continue
            record = change.source
            if change.field == "delete":
                record = change.source
                try:
                    markers = dict(record.source_object.GetMarkers() or {})
                    valid = self._matches(markers.get(record.frame), record)
                    deleted = valid and bool(record.source_object.DeleteMarkerAtFrame(record.frame))
                    verified = record.frame not in dict(record.source_object.GetMarkers() or {})
                except Exception:
                    deleted, verified = False, False
                if deleted and verified:
                    result.changed += 1
                    keys.append(record.stable_key)
                    before[record.stable_key] = self._snapshot(record)
                    after[record.stable_key] = {"deleted": True}
                else:
                    result.failed += 1; result.errors.append("Could not safely delete %s." % change.label)
                continue
            if change.field == "range":
                candidate = change.context["candidate"]
            elif change.field == "start_frame":
                candidate = self.edit_range(record, move=int(change.after) - record.start_frame)
            elif change.field == "duration_frames":
                candidate = self.edit_range(record, duration=int(change.after))
            else:
                candidate = record.copy(**{change.field: change.after})
            item = self.replace_marker(record, candidate, record_history=False, label=label)
            result.absorb(item)
            if item.success and item.changed:
                keys.append(record.stable_key)
                before[record.stable_key] = self._snapshot(record)
                after[record.stable_key] = self._snapshot(candidate)
        result.success = result.failed == 0
        if keys and self.history:
            self.history.add(OperationRecord("marker", label, keys, before, after))
        return result

    def undo(self, operation):
        result = OperationResult(True)
        current_records = self.list_markers()
        current_by_state = {(item.start_frame, item.name, item.color): item for item in current_records}
        context = self.context_service.refresh_context()
        for key in operation.object_ids:
            before = operation.before.get(key)
            after = operation.after.get(key)
            if not before or not after:
                result.failed += 1
                result.errors.append("History data is incomplete for a marker.")
                continue
            if before.get("deleted"):
                current = current_by_state.get((after["start_frame"], after["name"], after["color"]))
                if not current or not self._matches(dict(current.source_object.GetMarkers() or {}).get(current.frame), current):
                    result.failed += 1; result.errors.append("The added marker no longer matches the value Resolve Hub applied."); continue
                try:
                    deleted = bool(current.source_object.DeleteMarkerAtFrame(current.frame))
                    verified = current.frame not in dict(current.source_object.GetMarkers() or {})
                except Exception:
                    deleted, verified = False, False
                if deleted and verified: result.changed += 1
                else: result.failed += 1; result.errors.append("Resolve could not remove the added marker.")
                continue
            if after.get("deleted"):
                timeline = context.timeline
                if not timeline:
                    result.failed += 1; result.errors.append("Open the timeline used by this marker operation."); continue
                try:
                    current_scope = proxy_id(timeline, context.timeline_id)
                    occupied = before["start_frame"] in dict(timeline.GetMarkers() or {})
                except Exception:
                    current_scope, occupied = "", True
                if current_scope != before.get("scope_id") or occupied:
                    result.failed += 1; result.errors.append("The deleted marker cannot be restored safely in the current timeline."); continue
                original = MarkerRecord(source_object=timeline, **before)
                try:
                    restored = bool(timeline.AddMarker(original.frame, original.color, original.name, original.note, original.duration_frames, original.custom_data or ""))
                    verified = restored and self._matches(dict(timeline.GetMarkers() or {}).get(original.frame), original)
                except Exception:
                    restored, verified = False, False
                if verified: result.changed += 1
                else: result.failed += 1; result.errors.append("Resolve could not restore the deleted marker.")
                continue
            current = current_by_state.get((after["start_frame"], after["name"], after["color"]))
            if not current:
                result.failed += 1
                result.errors.append("A marker no longer matches the value Resolve Hub applied.")
                continue
            original = MarkerRecord(source_object=current.source_object, **before)
            item = self.replace_marker(current, original, record_history=False, label="Undo " + operation.label)
            result.absorb(item)
        result.success = result.failed == 0
        return result
