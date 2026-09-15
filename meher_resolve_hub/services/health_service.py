"""Read-only media diagnostics with conservative classifications."""

import csv
import json
import os
from dataclasses import asdict
from pathlib import Path

from ..models.health import HealthIssue, HealthReport


def _number(value):
    try: return float(str(value).split()[0])
    except (TypeError, ValueError, IndexError): return None


def _resolution(properties):
    width = properties.get("Resolution") or ""
    if width: return str(width).replace(" ", "")
    w, h = properties.get("Resolution Width"), properties.get("Resolution Height")
    return "%sx%s" % (w, h) if w and h else ""


class HealthService:
    def scan(self, records, expected_fps=None, expected_resolutions=None, required_fields=None, expected_codecs=None, short_clip_frames=12, used_ids=None, scope="Selection"):
        expected_resolutions = {str(item).replace(" ", "").lower() for item in (expected_resolutions or []) if item}
        required_fields = list(required_fields or [])
        expected_codecs = {str(item).casefold() for item in (expected_codecs or []) if item}
        usage_known = used_ids is not None
        used_ids = set(used_ids) if usage_known else set()
        issues, skipped = [], {}
        if not usage_known:
            skipped["Unused"] = "Timeline usage is unknown; no unused classification was made."
        path_groups, signature_groups = {}, {}
        for record in records:
            props, meta = record.properties, record.metadata
            path = str(props.get("File Path") or record.file_path or "")
            offline_value = str(props.get("Offline") or props.get("Media Status") or "").casefold()
            explicitly_offline = offline_value in ("offline", "true", "1", "media offline")
            missing_absolute_path = bool(path and os.path.isabs(path) and not os.path.exists(path))
            if explicitly_offline or missing_absolute_path:
                issues.append(HealthIssue("Offline", "Error", record.unique_id, record.name, "Source media is unavailable.", actual=path or offline_value))
            elif not path:
                skipped["Offline"] = "Resolve did not expose a source path or offline state."
            elif not os.path.isabs(path) and not offline_value:
                skipped["Offline"] = "Resolve exposed a non-filesystem path without a reliable offline state."

            proxy = str(props.get("Proxy") or props.get("Proxy Media") or props.get("Proxy Media Path") or "")
            if proxy:
                if ("offline" in proxy.casefold()) or (os.path.isabs(proxy) and not os.path.exists(proxy)):
                    issues.append(HealthIssue("Missing Proxy", "Warning", record.unique_id, record.name, "Linked proxy is unavailable.", actual=proxy))
            else:
                skipped["Missing Proxy"] = "No reliable proxy property is exposed for one or more clips."

            fps = _number(props.get("FPS") or props.get("Frame Rate"))
            if expected_fps is not None and fps is not None and abs(fps - float(expected_fps)) > 0.02:
                issues.append(HealthIssue("Frame Rate", "Review", record.unique_id, record.name, "Frame rate differs from the timeline; review intentional high-frame-rate media.", str(expected_fps), str(fps)))

            resolution = _resolution(props)
            if expected_resolutions and resolution and resolution.casefold() not in expected_resolutions:
                issues.append(HealthIssue("Resolution", "Review", record.unique_id, record.name, "Resolution is outside the configured expected set.", ", ".join(sorted(expected_resolutions)), resolution))

            for field in required_fields:
                if not str(meta.get(field, "")).strip():
                    issues.append(HealthIssue("Metadata", "Warning", record.unique_id, record.name, "Required metadata is blank: %s" % field, field, "Blank"))

            codec = str(props.get("Video Codec") or props.get("Codec") or "")
            if expected_codecs and codec and codec.casefold() not in expected_codecs:
                issues.append(HealthIssue("Codec", "Review", record.unique_id, record.name, "Codec is outside the configured expected set.", ", ".join(sorted(expected_codecs)), codec))

            duration = _number(props.get("Frames") or props.get("Duration in Frames"))
            if duration is not None and duration < int(short_clip_frames):
                issues.append(HealthIssue("Short Clip", "Review", record.unique_id, record.name, "Clip is suspiciously short.", ">= %s frames" % short_clip_frames, "%s frames" % int(duration)))

            audio = str(props.get("Audio Codec") or props.get("Audio") or "")
            clip_type = str(props.get("Type") or "").casefold()
            if "video" in clip_type and audio.casefold() in ("none", "no audio"):
                issues.append(HealthIssue("Audio", "Review", record.unique_id, record.name, "Clip reports no audio.", "Audio", audio))

            if path: path_groups.setdefault(os.path.normcase(os.path.normpath(path)), []).append(record)
            filename = str(props.get("File Name") or Path(path).name or record.name).casefold()
            signature_groups.setdefault((filename, str(props.get("Duration") or props.get("Frames") or "")), []).append(record)
            if usage_known and record.unique_id not in used_ids:
                issues.append(HealthIssue("Unused", "Info", record.unique_id, record.name, "Clip is not used in the current timeline."))

        for group in path_groups.values():
            if len(group) > 1:
                for record in group: issues.append(HealthIssue("Duplicate Path", "Warning", record.unique_id, record.name, "Multiple clips reference the same source path.", actual=record.file_path))
        for group in signature_groups.values():
            if len(group) > 1:
                for record in group: issues.append(HealthIssue("Duplicate Name", "Review", record.unique_id, record.name, "Filename and duration match another clip."))
        return HealthReport(scope, len(records), issues, skipped)

    @staticmethod
    def filter_issues(report, category="All"):
        return list(report.issues) if category in ("", "All") else [item for item in report.issues if item.category == category]

    @staticmethod
    def export(report, path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".json":
            path.write_text(json.dumps({"scope": report.scope, "scanned": report.scanned, "summary": report.summary(), "skipped_checks": report.skipped_checks, "issues": [asdict(item) for item in report.issues]}, indent=2), encoding="utf-8")
        else:
            with path.open("w", newline="", encoding="utf-8-sig") as handle:
                fields = ["category", "severity", "clip_id", "clip_name", "message", "expected", "actual", "thumbnail_path"]
                writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
                for item in report.issues: writer.writerow(asdict(item))
        return path
