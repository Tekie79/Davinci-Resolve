"""Marker browsing, filtering, safe mutation, batch preview, and rollback."""

from ..constants import MARKER_COLORS
from ..models.marker import MarkerRecord
from ..models.operation import Change, OperationRecord, OperationResult, PreviewSummary
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

    def _scope_error(self, record):
        """Never let a stale editor/history entry write into a different scope."""
        try:
            context = self.context_service.refresh_context()
            if (
                record.scope_type != "timeline"
                or not context.timeline
                or not record.scope_id
                or proxy_id(context.timeline, context.timeline_id) != record.scope_id
                or proxy_id(record.source_object) != record.scope_id
            ):
                return "Open the timeline used by this marker operation and refresh before editing."
        except Exception as exc:
            return "Could not verify the marker timeline: %s" % exc
        return ""

    def _validate(self, record, candidate):
        error = self._scope_error(record)
        if error:
            return error
        if (candidate.scope_type, candidate.scope_id) != (record.scope_type, record.scope_id):
            return "A marker edit cannot change its owning timeline."
        if candidate.frame != candidate.start_frame:
            return "Marker frame and start are inconsistent."
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
            # Preserve the existing relative-frame convention in this safety fix.
            span = max(0, upper - lower)
            if candidate.start_frame > span or candidate.end_frame > span:
                return "Marker range is outside the timeline."
        except Exception:
            pass
        return ""

    @staticmethod
    def _marker_at_frame(markers, frame):
        """Read a Resolve marker without depending on its numeric key type."""
        target = int(frame)
        for key, value in dict(markers or {}).items():
            try:
                if int(round(float(key))) == target:
                    return value
            except (TypeError, ValueError):
                continue
        return None

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
        try:
            duration = int(marker_info_value(info, "duration", "Duration", default=1) or 1)
        except (TypeError, ValueError):
            return False
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
        """Validate, delete, recreate, verify, and conservatively restore on failure."""
        error = self._validate(original, candidate)
        if error:
            return OperationResult(False, failed=1, errors=[error])
        timeline = original.source_object
        try:
            markers = dict(timeline.GetMarkers() or {})
        except Exception as exc:
            return OperationResult(False, failed=1, errors=["Could not read current markers: %s" % exc])
        current = self._marker_at_frame(markers, original.frame)
        if not self._matches(current, original):
            return OperationResult(False, failed=1, errors=["The marker changed in Resolve. Refresh before editing."])
        if candidate.start_frame != original.frame and self._marker_at_frame(markers, candidate.start_frame) is not None:
            return OperationResult(False, failed=1, errors=["Another marker already exists at the target frame."])
        if self._snapshot(original) == self._snapshot(candidate):
            return OperationResult(True, unchanged=1)
        try:
            timeline.DeleteMarkerAtFrame(original.frame)
            deleted = self._marker_at_frame(timeline.GetMarkers(), original.frame) is None
        except Exception:
            deleted = False
        if not deleted:
            return OperationResult(False, failed=1, errors=["Resolve did not delete the original marker."])

        try:
            timeline.AddMarker(candidate.start_frame, candidate.color, candidate.name, candidate.note, candidate.duration_frames, candidate.custom_data or "")
            verified = self._matches(self._marker_at_frame(timeline.GetMarkers(), candidate.start_frame), candidate)
        except Exception:
            verified = False
        if verified:
            if record_history and self.history:
                self.history.add(OperationRecord("marker", label, [original.stable_key], {original.stable_key: self._snapshot(original)}, {original.stable_key: self._snapshot(candidate)}))
            return OperationResult(True, changed=1, details=[{"before": self._snapshot(original), "after": self._snapshot(candidate)}])

        warnings = []
        try:
            # An unverified occupant may belong to another user/tool. Never delete
            # it as rollback cleanup: restore only into an empty original slot.
            markers = dict(timeline.GetMarkers() or {})
            occupant = self._marker_at_frame(markers, original.frame)
            if occupant is None:
                timeline.AddMarker(original.frame, original.color, original.name, original.note, original.duration_frames, original.custom_data or "")
            rollback_verified = self._matches(self._marker_at_frame(timeline.GetMarkers(), original.frame), original)
            if candidate.start_frame != original.frame and self._marker_at_frame(timeline.GetMarkers(), candidate.start_frame) is not None:
                warnings.append("An unverified marker remains at the target frame; it was left intact for review.")
        except Exception:
            rollback_verified = False
        details = [{"original": self._snapshot(original), "attempted": self._snapshot(candidate)}]
        if rollback_verified:
            return OperationResult(False, failed=1, warnings=warnings, errors=["Marker update failed; the original marker was restored."], details=details)
        return OperationResult(False, failed=1, warnings=warnings, errors=["CRITICAL: marker update and rollback both failed. Restore the marker manually from the operation details."], details=details)

    def add_marker(self, timeline, frame, color, name, note="", duration=1, custom_data="", label="Add marker"):
        """Add and verify a marker, recording a guarded Undo operation."""
        context = self.context_service.refresh_context()
        scope_id = proxy_id(timeline, context.timeline_id)
        try:
            frame = int(frame)
            duration = int(duration)
        except (TypeError, ValueError):
            return OperationResult(False, failed=1, errors=["Marker frame and duration must be integers."])
        record = MarkerRecord("timeline", scope_id, frame, frame, frame + duration - 1, duration, str(color), str(name), str(note), custom_data or None, source_object=timeline)
        error = self._validate(record, record)
        if error:
            return OperationResult(False, failed=1, errors=[error])
        try:
            if self._marker_at_frame(timeline.GetMarkers(), frame) is not None:
                return OperationResult(False, failed=1, errors=["A marker already exists at the playhead."])
            # Some Resolve bindings return None even after a successful write.
            # The authoritative result is the marker read back from the timeline.
            timeline.AddMarker(frame, record.color, record.name, record.note, record.duration_frames, custom_data or "")
            verified = self._matches(self._marker_at_frame(timeline.GetMarkers(), frame), record)
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
            new_duration = int(duration)
            if new_duration < 1:
                raise ValueError("Marker duration must be at least one frame.")
            new_end = new_start + new_duration - 1
        elif end is not None:
            new_end = int(end)
            new_duration = new_end - new_start + 1
        else:
            new_end = record.end_frame
            new_duration = new_end - new_start + 1
        return record.copy(frame=new_start, start_frame=new_start, end_frame=new_end, duration_frames=new_duration)

    def _candidate_for_change(self, change):
        record = change.source
        if change.field == "range":
            return change.context["candidate"]
        if change.field == "start_frame":
            return self.edit_range(record, move=int(change.after) - record.start_frame)
        if change.field == "duration_frames":
            return self.edit_range(record, duration=int(change.after))
        return record.copy(**{change.field: change.after})

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
            candidate = None
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
            context = {"candidate": candidate} if field == "range" and candidate is not None else {}
            change = Change(record.stable_key, record.name or "Marker", field, before, after, status, source=record, context=context)
            if change.changed and field != "delete":
                try:
                    if self._validate(record, self._candidate_for_change(change)):
                        change.status = "Invalid"
                except Exception:
                    change.status = "Invalid"
            changes.append(change)
        return PreviewSummary(changes)

    def _ordered_changes(self, changes):
        """Preflight moving batches and order dependencies without deleting first.

        For example, move B 20->30 before A 10->20. Cycles and duplicate
        destinations are refused rather than staging markers destructively.
        """
        ready = [change for change in changes if change.changed]
        candidates = {id(change): self._candidate_for_change(change) for change in ready if change.field != "delete"}
        if not any(candidate.start_frame != change.source.frame for change in ready if (candidate := candidates.get(id(change))) is not None):
            return list(changes)
        origins = {(change.source.scope_id, change.source.frame) for change in ready}
        if len(origins) != len(ready):
            raise ValueError("The batch contains more than one edit for the same marker.")
        targets = set()
        for change in ready:
            source = change.source
            error = self._scope_error(source)
            if error:
                raise ValueError(error)
            markers = dict(source.source_object.GetMarkers() or {})
            if not self._matches(self._marker_at_frame(markers, source.frame), source):
                raise ValueError("A marker changed since preview. Refresh and preview again.")
            candidate = candidates.get(id(change))
            if candidate is None:
                continue
            error = self._validate(source, candidate)
            if error:
                raise ValueError(error)
            target = (source.scope_id, candidate.start_frame)
            if target in targets:
                raise ValueError("Multiple markers would occupy the same target frame.")
            targets.add(target)
            if self._marker_at_frame(markers, candidate.start_frame) is not None and target not in origins:
                raise ValueError("An unselected marker occupies a target frame. No batch changes were applied.")
        ordered = [change for change in changes if not change.changed]
        pending = list(ready)
        while pending:
            occupied = {(change.source.scope_id, change.source.frame) for change in pending}
            for index, change in enumerate(pending):
                candidate = candidates.get(id(change))
                if candidate is None or candidate.start_frame == change.source.frame or (candidate.scope_id, candidate.start_frame) not in occupied:
                    ordered.append(pending.pop(index))
                    break
            else:
                raise ValueError("The batch contains a marker-position cycle. No changes were applied.")
        return ordered

    def apply_preview(self, preview, label="Batch marker edit"):
        result = OperationResult(True)
        before, after, keys = {}, {}, []
        try:
            changes = self._ordered_changes(preview.changes)
        except Exception as exc:
            return OperationResult(False, failed=max(1, preview.changed), errors=[str(exc)])
        for change in changes:
            if not change.changed:
                result.unchanged += 1
                if change.status not in ("Ready", "Unchanged"):
                    result.warnings.append("%s: %s" % (change.label, change.status))
                continue
            record = change.source
            if change.field == "delete":
                valid = False
                try:
                    markers = dict(record.source_object.GetMarkers() or {})
                    valid = not self._scope_error(record) and self._matches(self._marker_at_frame(markers, record.frame), record)
                    if valid:
                        record.source_object.DeleteMarkerAtFrame(record.frame)
                    verified = self._marker_at_frame(record.source_object.GetMarkers(), record.frame) is None
                except Exception:
                    verified = False
                if valid and verified:
                    result.changed += 1
                    keys.append(record.stable_key)
                    before[record.stable_key] = self._snapshot(record)
                    after[record.stable_key] = {"deleted": True}
                else:
                    result.failed += 1; result.errors.append("Could not safely delete %s." % change.label)
                continue
            candidate = self._candidate_for_change(change)
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
        """Compare the complete recorded after-state in its original timeline.

        Reverse actual execution order so dependent batch moves remain reversible.
        Never compare a freshly read marker to itself as an undo conflict check.
        """
        result = OperationResult(True)
        context = self.context_service.refresh_context()
        timeline = context.timeline
        if not timeline:
            return OperationResult(False, failed=1, errors=["Open the timeline used by this marker operation."])
        current_scope = proxy_id(timeline, context.timeline_id)
        for key in reversed(operation.object_ids):
            before = operation.before.get(key)
            after = operation.after.get(key)
            if not before or not after:
                result.failed += 1; result.errors.append("History data is incomplete for a marker."); continue
            states = [state for state in (before, after) if not state.get("deleted")]
            if not states or any(state.get("scope_type") != "timeline" or state.get("scope_id") != current_scope for state in states):
                result.failed += 1; result.errors.append("Open the original timeline before undoing this marker operation."); continue
            try:
                markers = dict(timeline.GetMarkers() or {})
                if before.get("deleted"):
                    expected = MarkerRecord(source_object=timeline, **after)
                    info = self._marker_at_frame(markers, expected.frame)
                    if info is None:
                        result.unchanged += 1
                        continue
                    if not self._matches(info, expected):
                        result.failed += 1; result.errors.append("The added marker changed after the operation; undo skipped."); continue
                    timeline.DeleteMarkerAtFrame(expected.frame)
                    verified = self._marker_at_frame(timeline.GetMarkers(), expected.frame) is None
                    if verified: result.changed += 1
                    else: result.failed += 1; result.errors.append("Resolve could not remove the added marker.")
                    continue
                original = MarkerRecord(source_object=timeline, **before)
                original_info = self._marker_at_frame(markers, original.frame)
                if self._matches(original_info, original):
                    # A previous partial undo already restored this entry.
                    result.unchanged += 1
                    continue
                if after.get("deleted"):
                    if original_info is not None:
                        result.failed += 1; result.errors.append("The deleted marker's original frame is occupied; undo skipped."); continue
                    timeline.AddMarker(original.frame, original.color, original.name, original.note, original.duration_frames, original.custom_data or "")
                    verified = self._matches(self._marker_at_frame(timeline.GetMarkers(), original.frame), original)
                    if verified: result.changed += 1
                    else: result.failed += 1; result.errors.append("Resolve could not restore the deleted marker.")
                    continue
                expected = MarkerRecord(source_object=timeline, **after)
                if not self._matches(self._marker_at_frame(markers, expected.frame), expected):
                    result.failed += 1; result.errors.append("The marker changed after the operation; undo skipped."); continue
                result.absorb(self.replace_marker(expected, original, record_history=False, label="Undo " + operation.label))
            except Exception as exc:
                result.failed += 1; result.errors.append("Marker undo failed: %s" % exc)
        result.success = result.failed == 0
        return result
