"""Resolve clip-name templates, transformations, conflict detection, apply, and undo."""

import re

from ..models.operation import Change, OperationRecord, OperationResult, PreviewSummary

TOKEN_PATTERN = re.compile(r"\{([A-Za-z][A-Za-z0-9 _#-]*)\}")
INVALID_NAME_CHARS = re.compile(r'[\x00-\x1f]')


def clip_tokens(record, index=1):
    metadata = record.metadata
    original = record.name.rsplit(".", 1)[0] if "." in record.name else record.name
    values = {
        "Original": original,
        "Scene": metadata.get("Scene", ""),
        "Shot": metadata.get("Shot", ""),
        "Take": metadata.get("Take", ""),
        "Camera": metadata.get("Camera #", metadata.get("Camera ID", "")),
        "Reel": metadata.get("Reel Name", metadata.get("Reel", "")),
        "Index": str(index),
        "Character": metadata.get("Character", ""),
        "ShotType": metadata.get("Shot Type", metadata.get("ShotType", "")),
        "Episode": metadata.get("Episode", ""),
    }
    return {key: str(value or "") for key, value in values.items()}


def render_template(template, tokens, index=1, index_width=0):
    missing = []

    def replace(match):
        key = match.group(1)
        value = tokens.get(key, "")
        if key == "Index" and index_width:
            value = str(index).zfill(int(index_width))
        if value == "":
            missing.append(key)
        return value

    return TOKEN_PATTERN.sub(replace, str(template or "")), missing


def transform_name(value, prefix="", suffix="", find="", replace="", regex=False, whitespace=False, collapse=True, case="Keep"):
    result = str(value or "")
    if find:
        if regex:
            result = re.sub(find, replace, result)
        else:
            result = result.replace(find, replace)
    result = str(prefix or "") + result + str(suffix or "")
    if whitespace:
        result = re.sub(r"\s+", "_", result)
    if collapse:
        result = re.sub(r"_{2,}", "_", result)
        result = re.sub(r" {2,}", " ", result)
    if case == "Upper": result = result.upper()
    elif case == "Lower": result = result.lower()
    elif case == "Title": result = result.title()
    return result.strip()


class RenameService:
    def __init__(self, history=None):
        self.history = history
        self._clips = {}
        if history:
            history.register("rename", self.undo)

    def preview(self, records, template="{Original}", prefix="", suffix="", find="", replace="", regex=False, whitespace=False, collapse=True, case="Keep", start=1, width=0, fallbacks=None):
        fallbacks = dict(fallbacks or {})
        changes = []
        for offset, record in enumerate(records):
            index = int(start) + offset
            tokens = clip_tokens(record, index)
            for key, value in fallbacks.items():
                if not tokens.get(key): tokens[key] = str(value)
            try:
                rendered, missing = render_template(template, tokens, index, width)
                after = transform_name(rendered, prefix, suffix, find, replace, regex, whitespace, collapse, case)
                if missing: status = "Missing Token"
                elif not after: status = "Invalid"
                elif INVALID_NAME_CHARS.search(after) or len(after) > 255: status = "Invalid"
                elif after == record.name: status = "Unchanged"
                else: status = "Ready"
            except re.error:
                after, missing, status = record.name, [], "Invalid"
            self._clips[record.unique_id] = record
            changes.append(Change(record.unique_id, record.name, "name", record.name, after, status, source=record, context={"missing": missing}))
        counts = {}
        for item in changes:
            if item.status in ("Ready", "Unchanged"):
                counts[item.after.casefold()] = counts.get(item.after.casefold(), 0) + 1
        for item in changes:
            if counts.get(item.after.casefold(), 0) > 1 and item.status == "Ready":
                item.status = "Conflict"
        return PreviewSummary(changes)

    def set_name(self, record, value, record_history=True):
        clip = record.media_pool_item
        try: current = str(clip.GetName() or "")
        except Exception as exc: return OperationResult(False, failed=1, errors=["Could not read clip name: %s" % exc])
        if current == value: return OperationResult(True, unchanged=1)
        try:
            returned = bool(clip.SetName(str(value)))
            actual = str(clip.GetName() or "")
        except Exception as exc:
            return OperationResult(False, failed=1, errors=["Rename failed: %s" % exc])
        if not returned or actual != str(value):
            return OperationResult(False, failed=1, errors=["Resolve did not retain the new name for %s." % current])
        record.name = actual
        if record_history and self.history:
            self.history.add(OperationRecord("rename", "Rename clip", [record.unique_id], {record.unique_id: current}, {record.unique_id: actual}))
        return OperationResult(True, changed=1)

    def apply_preview(self, preview):
        result, before, after, ids = OperationResult(True), {}, {}, []
        for change in preview.changes:
            if not change.changed:
                result.unchanged += 1
                if change.status not in ("Ready", "Unchanged"): result.warnings.append("%s: %s" % (change.label, change.status))
                continue
            item = self.set_name(change.source, change.after, record_history=False)
            result.absorb(item)
            if item.success and item.changed:
                ids.append(change.object_id); before[change.object_id] = change.before; after[change.object_id] = change.after
        result.success = result.failed == 0
        if ids and self.history:
            self.history.add(OperationRecord("rename", "Rename %d clips" % len(ids), ids, before, after))
        return result

    def undo(self, operation):
        result = OperationResult(True)
        for identity in operation.object_ids:
            record = self._clips.get(identity)
            if not record:
                result.failed += 1; result.errors.append("Clip %s is no longer loaded." % identity); continue
            try: current = str(record.media_pool_item.GetName() or "")
            except Exception: current = ""
            if current != operation.after.get(identity):
                result.failed += 1; result.errors.append("%s changed after rename; undo skipped." % record.name); continue
            result.absorb(self.set_name(record, operation.before.get(identity, ""), record_history=False))
        result.success = result.failed == 0
        return result

