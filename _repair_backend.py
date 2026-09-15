"""One-shot source migration; removed by the repair workflow after tests pass."""
import ast
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parent


def put_method(relative, class_name, name, replacement):
    path = ROOT / relative
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    cls = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == class_name)
    node = next((node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name), None)
    body = textwrap.indent(textwrap.dedent(replacement).strip() + "\n", "    ")
    if node:
        first = min([node.lineno] + [item.lineno for item in node.decorator_list]) - 1
        lines[first:node.end_lineno] = [body]
    else:
        lines[cls.end_lineno:cls.end_lineno] = ["\n" + body]
    updated = "".join(lines)
    ast.parse(updated)
    path.write_text(updated, encoding="utf-8")


def replace_once(relative, old, new):
    path = ROOT / relative
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise RuntimeError("Unexpected source anchor in %s: %r (%s occurrences)" % (relative, old[:90], source.count(old)))
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def transform_method(relative, class_name, name, old, new):
    source = (ROOT / relative).read_text(encoding="utf-8")
    cls = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == class_name)
    node = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    first = min([node.lineno] + [item.lineno for item in node.decorator_list]) - 1
    snippet = "".join(source.splitlines(keepends=True)[first:node.end_lineno])
    if snippet.count(old) != 1:
        raise RuntimeError("Unexpected method anchor: %s.%s" % (class_name, name))
    put_method(relative, class_name, name, snippet.replace(old, new, 1))


def apply():
    rename = "meher_resolve_hub/services/rename_service.py"
    replace_once(rename, 'original = record.name.rsplit(".", 1)[0] if "." in record.name else record.name', 'suffix = record.name.rsplit(".", 1)[-1].casefold() if "." in record.name else ""\n    media_suffixes = {"mov", "mp4", "mxf", "avi", "mkv", "m4v", "r3d", "braw", "dng", "wav", "aif", "aiff", "mp3", "png", "jpg", "jpeg", "tif", "tiff", "exr", "dpx"}\n    original = record.name.rsplit(".", 1)[0] if suffix in media_suffixes else record.name')
    replace_once(rename, 'context={"missing": missing}', 'context={"missing": missing, "metadata_before": dict(record.metadata) if any(key not in ("Original", "Index") for key in TOKEN_PATTERN.findall(str(template))) else None}')
    put_method(rename, "RenameService", "set_name", '''
def set_name(self, record, value, record_history=True, expected_before=None):
    value = str(value)
    if not value.strip() or INVALID_NAME_CHARS.search(value) or len(value) > 255:
        return OperationResult(False, failed=1, errors=["Invalid Resolve clip name."])
    clip = record.media_pool_item
    try:
        current = str(clip.GetName() or "")
    except Exception as exc:
        return OperationResult(False, failed=1, errors=["Could not read clip name: %s" % exc])
    expected = record.name if expected_before is None else str(expected_before)
    if current != expected:
        return OperationResult(False, failed=1, errors=["%s changed after preview; refresh and preview again." % record.name])
    if current == value:
        return OperationResult(True, unchanged=1)
    try:
        clip.SetName(value)
        actual = str(clip.GetName() or "")
    except Exception as exc:
        return OperationResult(False, failed=1, errors=["Rename failed: %s" % exc])
    if actual != value:
        return OperationResult(False, failed=1, errors=["Resolve did not retain the new name for %s." % current])
    record.name = actual
    self._clips[record.unique_id] = record
    if record_history and self.history:
        self.history.add(OperationRecord("rename", "Rename clip", [record.unique_id], {record.unique_id: current}, {record.unique_id: actual}))
    return OperationResult(True, changed=1)
''')
    put_method(rename, "RenameService", "apply_preview", '''
def apply_preview(self, preview):
    # Validate the complete preview BEFORE any write. Never apply a stale plan.
    result = OperationResult(True)
    live, errors = {}, []
    active = [change for change in preview.changes if change.changed]
    identities = [change.object_id for change in preview.changes]
    if len(identities) != len(set(identities)):
        return OperationResult(False, failed=max(1, len(active)), errors=["The rename preview contains duplicate clip entries. Rebuild it."])
    for change in preview.changes:
        try:
            live[change.object_id] = str(change.source.media_pool_item.GetName() or "")
            if live[change.object_id] != str(change.before):
                errors.append("%s changed after preview." % change.label)
            expected_metadata = change.context.get("metadata_before")
            if change.changed and expected_metadata is not None:
                actual_metadata = dict(change.source.media_pool_item.GetMetadata() or {})
                if actual_metadata != expected_metadata:
                    errors.append("Metadata used by the naming template changed for %s." % change.label)
        except Exception as exc:
            errors.append("Could not revalidate %s: %s" % (change.label, exc))
        if change.changed:
            name = str(change.after)
            if not name.strip() or INVALID_NAME_CHARS.search(name) or len(name) > 255:
                errors.append("Invalid proposed name for %s." % change.label)
    final_names = {}
    for change in preview.changes:
        name = str(change.after) if change.changed else live.get(change.object_id, str(change.before))
        final_names.setdefault(name.casefold(), []).append(change)
    for group in final_names.values():
        if len(group) > 1 and any(change.changed for change in group):
            errors.append("A proposed name conflicts with another clip in this selection: %s." % group[0].after)
    if errors:
        return OperationResult(False, failed=max(1, len(active)), errors=errors + ["No rename was applied. Refresh and preview again."])
    before, after, ids = {}, {}, []
    for change in preview.changes:
        if not change.changed:
            result.unchanged += 1
            if change.status not in ("Ready", "Unchanged"):
                result.warnings.append("%s: %s" % (change.label, change.status))
            continue
        item = self.set_name(change.source, change.after, record_history=False, expected_before=change.before)
        result.absorb(item)
        if item.success and item.changed:
            ids.append(change.object_id)
            before[change.object_id], after[change.object_id] = change.before, change.after
    result.success = result.failed == 0
    if ids and self.history:
        self.history.add(OperationRecord("rename", "Rename %d clips" % len(ids), ids, before, after))
    return result
''')
    put_method(rename, "RenameService", "undo", '''
def undo(self, operation):
    result = OperationResult(True)
    for identity in dict.fromkeys(operation.object_ids):
        record = self._clips.get(identity)
        if not record:
            result.failed += 1
            result.errors.append("Clip %s is no longer loaded." % identity)
            continue
        try:
            current = str(record.media_pool_item.GetName() or "")
        except Exception as exc:
            result.failed += 1
            result.errors.append("Could not read clip name: %s" % exc)
            continue
        previous, expected = operation.before.get(identity), operation.after.get(identity)
        if previous is None or expected is None:
            result.failed += 1
            result.errors.append("Rename history is incomplete.")
        elif current == previous:
            record.name = current
            result.unchanged += 1
        elif current != expected:
            result.failed += 1
            result.errors.append("%s changed after rename; undo skipped." % record.name)
        else:
            result.absorb(self.set_name(record, previous, record_history=False, expected_before=expected))
    result.success = result.failed == 0
    return result
''')

    # Exclusive publication protects saved stills and files created after preview.
    (ROOT / "meher_resolve_hub/file_io.py").write_text('''"""Non-overwriting publication for application-generated stills."""
import os
import shutil
from pathlib import Path


def publish_new_file(source, destination):
    source, destination = Path(source), Path(destination)
    created = None
    try:
        with source.open("rb") as input_file, destination.open("xb") as output_file:
            created = os.fstat(output_file.fileno())
            shutil.copyfileobj(input_file, output_file)
            output_file.flush()
            os.fsync(output_file.fileno())
    except Exception:
        if created is not None:
            try:
                current = destination.lstat()
                if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                    destination.unlink()
            except FileNotFoundError:
                pass
        raise
    return destination
''', encoding="utf-8")
    still = "meher_resolve_hub/services/still_service.py"
    replace_once(still, "from ..models.operation import OperationResult", "from ..models.operation import OperationResult\nfrom ..file_io import publish_new_file")
    put_method(still, "StillService", "_export_current", '''
def _export_current(self, project, timeline, destination):
    # A fresh directory is essential: Gallery exports may change the filename.
    # Never discover fallback PNGs in the user's shared output directory.
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Output already exists: %s" % destination)
    with tempfile.TemporaryDirectory(prefix=".resolve-hub-export-", dir=str(destination.parent)) as folder:
        requested = Path(folder) / "frame.png"
        method = getattr(project, "ExportCurrentFrameAsStill", None)
        direct_failed = False
        if callable(method):
            try:
                method(str(requested))
            except Exception:
                direct_failed = True
        actual = requested if not direct_failed and requested.is_file() and requested.stat().st_size > 0 else None
        if actual is None:
            # Discard only this job's own incomplete direct-export file.
            if requested.exists():
                requested.unlink()
            try:
                captured = timeline.GrabStill()
                album = project.GetGallery().GetCurrentStillAlbum()
                if captured and album:
                    album.ExportStills([captured], folder, "frame", "png")
            except Exception:
                return None
            actual = find_exported_png(folder, requested)
            if not actual or actual.stat().st_size == 0:
                return None
        return publish_new_file(actual, destination)
''')
    replace_once(still, 'try: shutil.copy2(str(self.preview_path), str(destination))', 'try: publish_new_file(self.preview_path, destination)')
    put_method(still, "StillService", "detect_conflicts", '''
@staticmethod
def detect_conflicts(queue, output_folder):
    folder = Path(output_folder)
    counts = {}
    for item in queue:
        counts[item.filename.casefold()] = counts.get(item.filename.casefold(), 0) + 1
    for item in queue:
        if item.status in ("Captured", "Imported"):
            continue
        name = str(item.filename)
        if name != png_filename(name) or Path(name).name != name:
            item.status = "Invalid"
        elif counts[name.casefold()] > 1 or (folder / name).exists() or (folder / name).is_symlink():
            item.status = "Conflict"
        else:
            item.status = "Queued"
    return queue
''')
    put_method(still, "StillService", "execute_queue", '''
def execute_queue(self, queue, output_folder, target_bin=None, import_to_bin=True):
    context = self.context_service.refresh_context()
    if not context.project or not context.timeline:
        return OperationResult(False, errors=["Open the source project and timeline first."])
    if any(item.timeline_id != context.timeline_id for item in queue):
        return OperationResult(False, errors=["The capture queue belongs to another timeline."])
    folder = Path(os.path.expandvars(os.path.expanduser(str(output_folder))))
    try:
        folder.mkdir(parents=True, exist_ok=True)
        self.detect_conflicts(queue, folder)
    except Exception as exc:
        return OperationResult(False, failed=len(queue), errors=["Could not prepare the output folder: %s" % exc])
    previous = context.current_timecode
    result, paths = OperationResult(True), []
    try:
        for item in queue:
            if item.status in ("Captured", "Imported"):
                result.unchanged += 1
                continue
            if item.status in ("Conflict", "Invalid"):
                result.failed += 1
                result.errors.append("Skipped %s output: %s" % (item.status.lower(), item.filename))
                continue
            current = self.context_service.refresh_context()
            if current.project_id != context.project_id or current.timeline_id != context.timeline_id:
                result.failed += 1
                result.errors.append("Resolve context changed during capture; remaining jobs were not executed.")
                break
            try:
                context.timeline.SetCurrentTimecode(item.timecode)
                if not self._wait_for_timecode(context.timeline, item.timecode):
                    raise StillError("Resolve did not reach %s before capture." % item.timecode)
                destination = folder / item.filename
                actual = self._export_current(context.project, context.timeline, destination)
                if not actual:
                    raise StillError("Capture failed: %s" % item.source_label)
                item.output_path = str(destination)
                item.thumbnail_path = str(destination)
                item.status = "Captured"
                paths.append(destination)
                if not any(value.id == item.id for value in self.gallery):
                    self.gallery.append(item)
                result.changed += 1
                result.details.append({"source": item.source_label, "path": str(destination), "stage": "captured"})
            except FileExistsError:
                item.status = "Conflict"
                result.failed += 1
                result.errors.append("Output appeared after preview and was preserved: %s" % item.filename)
            except Exception as exc:
                item.status = "Failed"
                result.failed += 1
                result.errors.append("%s: %s" % (item.source_label, exc))
    finally:
        try:
            current = self.context_service.refresh_context()
            if current.project_id == context.project_id and current.timeline_id == context.timeline_id:
                context.timeline.SetCurrentTimecode(previous)
                if not self._wait_for_timecode(context.timeline, previous):
                    result.warnings.append("Resolve did not restore the previous playhead position.")
            else:
                result.warnings.append("Context changed; the Hub did not switch it back.")
        except Exception as exc:
            result.warnings.append("Could not restore the playhead: %s" % exc)
    if import_to_bin and paths:
        imported = self._import_paths(context.project, target_bin, paths)
        result.failed += imported.failed
        result.errors.extend(imported.errors)
        result.warnings.extend(imported.warnings)
        result.details.append({"stage": "import", "imported": imported.changed, "failed": imported.failed})
    result.success = result.failed == 0
    return result
''')
    # Use the real queue identity field; the model is inspected by the migration.
    model = (ROOT / "meher_resolve_hub/models/still.py").read_text(encoding="utf-8")
    fields = {node.target.id for node in ast.walk(ast.parse(model)) if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
    identity = next((name for name in ("id", "unique_id", "key") if name in fields), None)
    if identity is None:
        # Identity-free deduplication is safe because queue items are not cloned.
        replace_once(still, 'if not any(value.id == item.id for value in self.gallery):', 'if not any(value is item for value in self.gallery):')
    elif identity != "id":
        replace_once(still, 'if not any(value.id == item.id for value in self.gallery):', 'if not any(value.%s == item.%s for value in self.gallery):' % (identity, identity))

    health = "meher_resolve_hub/services/health_service.py"
    replace_once(health, 'used_ids = set(used_ids or [])', 'usage_known = used_ids is not None\n        used_ids = set(used_ids) if usage_known else set()')
    replace_once(health, 'issues, skipped = [], {}', 'issues, skipped = [], {}\n        if not usage_known:\n            skipped["Unused"] = "Timeline usage is unknown; no unused classification was made."')
    replace_once(health, 'if used_ids and record.unique_id not in used_ids:', 'if usage_known and record.unique_id not in used_ids:')
    transform_method("meher_resolve_hub/ui/shell.py", "ResolveHubShell", "_scan_health", 'used_ids = set()', 'used_ids = None')

    # Do not allow a user-selected cache directory to turn Clear Cache into an
    # arbitrary PNG deletion utility. Only remove Hub cache-key filenames.
    thumbs = "meher_resolve_hub/thumbnails.py"
    replace_once(thumbs, "import hashlib", "import hashlib\nimport re")
    replace_once(thumbs, 'CACHE_VERSION = "4"', 'CACHE_VERSION = "5"')
    transform_method(thumbs, "ThumbnailCache", "clear", 'for path in self.folder.glob("*.png"):', 'for path in self.folder.glob("*.png"):\n                if not re.fullmatch(r"[0-9a-f]{40}\\.png", path.name):\n                    continue')
    transform_method(thumbs, "ThumbnailCache", "delete_stale", 'for path in self.folder.glob("*.png"):', 'for path in self.folder.glob("*.png"):\n                if not re.fullmatch(r"[0-9a-f]{40}\\.png", path.name):\n                    continue')
    put_method(thumbs, "ThumbnailCache", "get", '''
def get(self, key):
    path = self.path_for(key)
    try:
        return path if path.is_file() and path.stat().st_size > 0 else None
    except OSError:
        return None
''')

    # An inline edit must not overwrite a change made in Resolve since selection.
    metadata = "meher_resolve_hub/services/metadata_service.py"
    replace_once(metadata, 'if expected_before is not None and current != str(expected_before):', 'expected_before = record.metadata.get(field, "") if expected_before is None else expected_before\n        if current != str(expected_before):')
    for name in ("Media Manager.py", "Meher Flow Resolve Hub.py", "meher_resolve_hub/constants.py", "README.md", "MANUAL_RESOLVE_ACCEPTANCE.md"):
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("0.3.22", "0.3.23").replace("v0322", "v0323"), encoding="utf-8")
    ignore = ROOT / ".gitignore"
    text = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    for line in ("__pycache__/", "*.py[cod]", ".pytest_cache/", "test-results*.txt", "source-snapshot.zip"):
        if line not in text.splitlines():
            text += "\n" + line
    ignore.write_text(text.lstrip("\n") + "\n", encoding="utf-8")


if __name__ == "__main__":
    apply()
