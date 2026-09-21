"""Speaker-dialogue range marker orchestration for Resolve Select timelines.

The documented Resolve scripting API can write markers on TimelineItem objects,
but it does not expose Resolve's internal speaker-detection segments through a
stable public API. This service therefore accepts either:
  * precomputed speaker segments, or
  * an injected analyzer adapter with analyze(timeline, fps).

It then maps those timeline ranges to clip-relative markers, preserves manual
markers, replaces only markers it generated previously, verifies all writes,
and rolls back generated markers if a batch write fails.
"""

from dataclasses import dataclass, field
from hashlib import sha1
import json

from ..constants import MARKER_COLORS
from ..models.operation import OperationResult
from ..utils import proxy_id


GENERATED_SYSTEM = "meher-flow"
GENERATED_TYPE = "speaker_dialogue"
LEGACY_SYSTEMS = {"meher-flow", "yekermo-sew"}


def _call(proxy, name, default=None, *args):
    if proxy is None:
        return default
    try:
        method = getattr(proxy, name)
    except Exception:
        return default
    if not callable(method):
        return default
    try:
        value = method(*args)
        return default if value is None else value
    except Exception:
        return default


def _marker_at(markers, frame):
    target = int(frame)
    for key, value in dict(markers or {}).items():
        try:
            if int(round(float(key))) == target:
                return value
        except (TypeError, ValueError):
            continue
    return None


def _custom_data(item, frame, info):
    info = dict(info or {})
    value = info.get("customData", info.get("custom_data", ""))
    if value in (None, ""):
        value = _call(item, "GetMarkerCustomData", "", frame)
    return "" if value is None else str(value)


def _custom_json(item, frame, info):
    try:
        value = json.loads(_custom_data(item, frame, info))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _is_generated(item, frame, info):
    data = _custom_json(item, frame, info)
    return data.get("type") == GENERATED_TYPE and data.get("system") in LEGACY_SYSTEMS


@dataclass(frozen=True)
class SpeakerSegment:
    """Absolute timeline range. end_frame is exclusive."""

    speaker: str
    start_frame: int
    end_frame: int
    confidence: float = 1.0
    transcript: str = ""
    source: str = "provided"
    identity_confidence: float = None

    @property
    def duration(self):
        return max(0, self.end_frame - self.start_frame)


@dataclass
class SpeakerMarker:
    item: object = field(repr=False)
    item_id: str = ""
    track_index: int = 1
    speaker: str = ""
    absolute_start: int = 0
    absolute_end: int = 0
    clip_frame: int = 0
    duration: int = 1
    color: str = "Cream"
    name: str = ""
    note: str = ""
    custom_data: str = ""

    def state(self):
        return {
            "color": self.color,
            "name": self.name,
            "note": self.note,
            "duration": int(self.duration),
            "customData": self.custom_data,
        }


@dataclass
class SpeakerMarkerPlan:
    timeline: object = field(repr=False)
    timeline_id: str = ""
    timeline_name: str = ""
    fps: float = 24.0
    track_index: int = 1
    markers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    source_segments: int = 0
    merged_segments: int = 0


class SpeakerMarkerService:
    """Convert timed speaker turns into verified clip markers."""

    def __init__(self, context_service, analyzer=None):
        self.context_service = context_service
        self.analyzer = analyzer

    def _normalize(self, value, timeline_start, fps):
        if isinstance(value, SpeakerSegment):
            return value
        if not isinstance(value, dict):
            raise ValueError("Speaker segment must be a dict or SpeakerSegment.")

        speaker = str(value.get("speaker") or value.get("speaker_id") or "").strip()
        if not speaker:
            raise ValueError("Speaker segment is missing speaker.")

        if value.get("start_frame") is not None and value.get("end_frame") is not None:
            start = int(round(float(value["start_frame"])))
            end = int(round(float(value["end_frame"])))
            origin = str(value.get("frame_origin") or "absolute").lower()
            if origin in ("relative", "timeline", "timeline_start"):
                start += timeline_start
                end += timeline_start
        elif value.get("relative_start_frame") is not None and value.get("relative_end_frame") is not None:
            start = timeline_start + int(round(float(value["relative_start_frame"])))
            end = timeline_start + int(round(float(value["relative_end_frame"])))
        elif value.get("start_seconds") is not None and value.get("end_seconds") is not None:
            start = timeline_start + int(round(float(value["start_seconds"]) * fps))
            end = timeline_start + int(round(float(value["end_seconds"]) * fps))
        else:
            raise ValueError("Speaker segment needs frame or second start/end values.")

        if end <= start:
            raise ValueError("Speaker segment end must be after start.")

        identity = value.get("identity_confidence")
        return SpeakerSegment(
            speaker=speaker,
            start_frame=start,
            end_frame=end,
            confidence=float(value.get("confidence", 1.0) or 0.0),
            transcript=str(value.get("transcript") or ""),
            source=str(value.get("source") or "provided"),
            identity_confidence=None if identity is None else float(identity),
        )

    @staticmethod
    def _map_speaker(segment, speaker_map, threshold):
        mapping = (speaker_map or {}).get(segment.speaker)
        if mapping is None:
            raw = segment.speaker
            if raw.upper().startswith(("SPEAKER_", "UNKNOWN")):
                return raw, False
            return raw, True

        confidence = segment.identity_confidence
        if isinstance(mapping, dict):
            name = str(mapping.get("name") or mapping.get("speaker") or segment.speaker)
            if mapping.get("confidence") is not None:
                confidence = float(mapping["confidence"])
        else:
            name = str(mapping)

        if confidence is not None and confidence < float(threshold):
            return "UNKNOWN_" + segment.speaker, False
        return name, True

    @staticmethod
    def _merge(segments, gap_frames):
        ordered = sorted(segments, key=lambda x: (x.start_frame, x.end_frame, x.speaker))
        if not ordered:
            return []
        result = [ordered[0]]
        for segment in ordered[1:]:
            previous = result[-1]
            if (
                segment.speaker == previous.speaker
                and segment.start_frame <= previous.end_frame + gap_frames
                and segment.start_frame >= previous.start_frame
            ):
                transcript = " ".join(
                    part for part in (previous.transcript.strip(), segment.transcript.strip()) if part
                )
                identity_values = [
                    value for value in (previous.identity_confidence, segment.identity_confidence)
                    if value is not None
                ]
                result[-1] = SpeakerSegment(
                    previous.speaker,
                    previous.start_frame,
                    max(previous.end_frame, segment.end_frame),
                    min(previous.confidence, segment.confidence),
                    transcript,
                    previous.source if previous.source == segment.source else "mixed",
                    min(identity_values) if identity_values else None,
                )
            else:
                result.append(segment)
        return result

    @staticmethod
    def _item_span(item):
        start = int(_call(item, "GetStart", 0) or 0)
        duration = int(_call(item, "GetDuration", 0) or 0)
        if duration > 0:
            return start, start + duration
        end = int(_call(item, "GetEnd", start) or start)
        return start, max(start, end)

    def _video_items(self, timeline, preferred_track=1):
        count = int(_call(timeline, "GetTrackCount", 0, "video") or 0)
        if count < 1:
            return [], int(preferred_track)

        order = [int(preferred_track)] + [
            index for index in range(1, count + 1) if index != int(preferred_track)
        ]
        for track_index in order:
            if not 1 <= track_index <= count:
                continue
            items = list(_call(timeline, "GetItemListInTrack", [], "video", track_index) or [])
            spans = []
            for item in items:
                start, end = self._item_span(item)
                if end > start:
                    spans.append((start, end, item))
            if spans:
                return sorted(spans, key=lambda row: (row[0], row[1])), track_index
        return [], int(preferred_track)

    @staticmethod
    def _segment_id(timeline_id, item_id, speaker, start, end, transcript):
        raw = "%s|%s|%s|%s|%s|%s" % (
            timeline_id, item_id, speaker, start, end, transcript.strip()
        )
        return sha1(raw.encode("utf-8")).hexdigest()[:20]

    def plan(
        self,
        segments,
        timeline=None,
        speaker_map=None,
        speaker_colors=None,
        identity_threshold=0.85,
        merge_gap_ms=350,
        minimum_duration_ms=300,
        unknown_color="Cream",
        overlap_color="Fuchsia",
        primary_video_track=1,
    ):
        context = self.context_service.refresh_context()
        timeline = timeline or context.timeline
        if not timeline:
            raise ValueError("Open a Resolve timeline first.")

        fps = float(self.context_service.get_project_fps())
        start_frame = int(_call(timeline, "GetStartFrame", 0) or 0)
        timeline_id = proxy_id(timeline, context.timeline_id)
        timeline_name = str(_call(timeline, "GetName", context.timeline_name) or "")

        normalized = [self._normalize(value, start_frame, fps) for value in (segments or [])]
        mapped = []
        for value in normalized:
            speaker, confirmed = self._map_speaker(value, speaker_map, identity_threshold)
            mapped.append(SpeakerSegment(
                speaker, value.start_frame, value.end_frame, value.confidence,
                value.transcript, value.source, value.identity_confidence
            ))

        min_frames = max(1, int(round(float(minimum_duration_ms) * fps / 1000.0)))
        gap_frames = max(0, int(round(float(merge_gap_ms) * fps / 1000.0)))
        # Merge short same-speaker fragments before the minimum-duration filter.
        # Diarization can split one natural line into sub-300 ms pieces; dropping
        # those pieces first would create false holes in the speaker range.
        merged = self._merge(mapped, gap_frames)
        merged = [value for value in merged if value.duration >= min_frames]

        items, track_index = self._video_items(timeline, primary_video_track)
        if not items:
            raise ValueError("No video TimelineItems were found on the target timeline.")

        colors = dict(speaker_colors or {})
        warnings = []
        planned = []

        for segment in merged:
            color = str(colors.get(segment.speaker, unknown_color))
            if color not in MARKER_COLORS:
                warnings.append(
                    "Unsupported marker color %r for %s; using %s."
                    % (color, segment.speaker, unknown_color)
                )
                color = unknown_color if unknown_color in MARKER_COLORS else "Cream"

            intersections = []
            for item_start, item_end, item in items:
                seg_start = max(segment.start_frame, item_start)
                seg_end = min(segment.end_frame, item_end)
                if seg_end > seg_start:
                    intersections.append((seg_start, seg_end, item_start, item))

            if not intersections:
                warnings.append(
                    "No video clip covers %s at frames %s..%s."
                    % (segment.speaker, segment.start_frame, segment.end_frame - 1)
                )
                continue

            for part, (seg_start, seg_end, item_start, item) in enumerate(intersections, 1):
                item_id = proxy_id(item, str(id(item)))
                segment_id = self._segment_id(
                    timeline_id, item_id, segment.speaker,
                    segment.start_frame, segment.end_frame, segment.transcript
                )
                if len(intersections) > 1:
                    segment_id += "-p%s" % part

                transcript = segment.transcript.replace("\n", " ").strip()
                if len(transcript) > 160:
                    transcript = transcript[:157] + "..."

                note = "Speaker: %s" % segment.speaker
                if segment.identity_confidence is not None:
                    note += " | Identity confidence: %.2f" % segment.identity_confidence
                if transcript:
                    note += ' | "%s"' % transcript

                custom = json.dumps({
                    "system": GENERATED_SYSTEM,
                    "type": GENERATED_TYPE,
                    "version": 1,
                    "timeline_id": timeline_id,
                    "item_id": item_id,
                    "speaker": segment.speaker,
                    "segment_id": segment_id,
                    "analysis_source": segment.source,
                    "identity_confidence": segment.identity_confidence,
                    "timeline_start_frame": int(seg_start),
                    "timeline_end_frame_exclusive": int(seg_end),
                }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

                planned.append(SpeakerMarker(
                    item=item,
                    item_id=item_id,
                    track_index=track_index,
                    speaker=segment.speaker,
                    absolute_start=int(seg_start),
                    absolute_end=int(seg_end),
                    clip_frame=int(seg_start - item_start),
                    duration=max(1, int(seg_end - seg_start)),
                    color=color,
                    name="DIALOGUE — %s" % segment.speaker,
                    note=note,
                    custom_data=custom,
                ))

        # Resolve stores one marker per frame on a TimelineItem. Preserve exact
        # simultaneous starts as one overlap marker rather than moving one.
        by_position = {}
        for marker in planned:
            by_position.setdefault((marker.item_id, marker.clip_frame), []).append(marker)

        final = []
        for group in by_position.values():
            speakers = sorted(set(marker.speaker for marker in group))
            if len(group) == 1:
                final.append(group[0])
                continue
            if len(speakers) == 1:
                final.append(max(group, key=lambda marker: marker.duration))
                continue

            first = group[0]
            absolute_end = max(marker.absolute_end for marker in group)
            speaker_text = " + ".join(speakers)
            color = overlap_color if overlap_color in MARKER_COLORS else "Fuchsia"
            segment_id = self._segment_id(
                timeline_id, first.item_id, speaker_text,
                first.absolute_start, absolute_end, "overlap"
            )
            custom = json.dumps({
                "system": GENERATED_SYSTEM,
                "type": GENERATED_TYPE,
                "version": 1,
                "timeline_id": timeline_id,
                "item_id": first.item_id,
                "speaker": speakers,
                "segment_id": segment_id,
                "analysis_source": "overlap",
                "timeline_start_frame": first.absolute_start,
                "timeline_end_frame_exclusive": absolute_end,
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            final.append(SpeakerMarker(
                item=first.item,
                item_id=first.item_id,
                track_index=first.track_index,
                speaker=speaker_text,
                absolute_start=first.absolute_start,
                absolute_end=absolute_end,
                clip_frame=first.clip_frame,
                duration=max(1, absolute_end - first.absolute_start),
                color=color,
                name="OVERLAP — %s" % speaker_text,
                note="Overlapping dialogue: %s" % ", ".join(speakers),
                custom_data=custom,
            ))
            warnings.append("Combined exact-start overlap for %s." % ", ".join(speakers))

        final.sort(key=lambda marker: (marker.absolute_start, marker.item_id))
        return SpeakerMarkerPlan(
            timeline=timeline,
            timeline_id=timeline_id,
            timeline_name=timeline_name,
            fps=fps,
            track_index=track_index,
            markers=final,
            warnings=warnings,
            source_segments=len(normalized),
            merged_segments=len(merged),
        )

    @staticmethod
    def _generated_for_item(item):
        result = {}
        for raw_frame, raw_info in dict(_call(item, "GetMarkers", {}) or {}).items():
            try:
                frame = int(round(float(raw_frame)))
            except (TypeError, ValueError):
                continue
            if not _is_generated(item, frame, raw_info):
                continue
            info = dict(raw_info or {})
            result[frame] = {
                "color": str(info.get("color", info.get("Color", ""))),
                "name": str(info.get("name", info.get("Name", ""))),
                "note": str(info.get("note", info.get("Note", ""))),
                "duration": int(info.get("duration", info.get("Duration", 1)) or 1),
                "customData": _custom_data(item, frame, info),
            }
        return result

    @staticmethod
    def _state_matches(item, frame, expected):
        info = _marker_at(_call(item, "GetMarkers", {}) or {}, frame)
        if not info:
            return False
        info = dict(info or {})
        return (
            str(info.get("color", info.get("Color", ""))) == expected["color"]
            and str(info.get("name", info.get("Name", ""))) == expected["name"]
            and str(info.get("note", info.get("Note", ""))) == expected["note"]
            and int(info.get("duration", info.get("Duration", 1)) or 1) == expected["duration"]
            and _custom_data(item, frame, info) == expected["customData"]
        )

    @staticmethod
    def _delete_generated(item):
        current = SpeakerMarkerService._generated_for_item(item)
        for frame in list(current):
            _call(item, "DeleteMarkerAtFrame", False, frame)
            if _marker_at(_call(item, "GetMarkers", {}) or {}, frame):
                return False
        return True

    @staticmethod
    def _restore_generated(item, snapshot):
        if not SpeakerMarkerService._delete_generated(item):
            return False
        for frame, state in sorted(snapshot.items()):
            try:
                item.AddMarker(
                    frame, state["color"], state["name"], state["note"],
                    state["duration"], state["customData"]
                )
            except Exception:
                return False
            if not SpeakerMarkerService._state_matches(item, frame, state):
                return False
        return True

    def apply(self, plan, mode="apply", replace_generated=True):
        mode = str(mode or "apply").lower()
        if mode not in ("apply", "preview"):
            return OperationResult(False, failed=1, errors=["MODE must be preview or apply."])

        desired = {}
        items = {}
        for marker in plan.markers:
            items[marker.item_id] = marker.item
            desired.setdefault(marker.item_id, {})[marker.clip_frame] = marker.state()

        if replace_generated:
            spans, _ = self._video_items(plan.timeline, plan.track_index)
            for _, _, item in spans:
                item_id = proxy_id(item, str(id(item)))
                items[item_id] = item
                desired.setdefault(item_id, {})

        snapshots = {
            item_id: self._generated_for_item(item)
            for item_id, item in items.items()
        }

        collisions = []
        for marker in plan.markers:
            existing = _marker_at(_call(marker.item, "GetMarkers", {}) or {}, marker.clip_frame)
            if existing and not _is_generated(marker.item, marker.clip_frame, existing):
                collisions.append(
                    "%s @ clip frame %s on %s"
                    % (marker.speaker, marker.clip_frame, _call(marker.item, "GetName", "clip"))
                )

        if collisions:
            return OperationResult(
                False,
                failed=len(collisions),
                warnings=list(plan.warnings),
                errors=["Manual marker collision: %s" % value for value in collisions],
                details=[{"timeline": plan.timeline_name, "planned": len(plan.markers), "mode": mode}],
            )

        already_current = all(
            snapshots.get(item_id, {}) == desired.get(item_id, {})
            for item_id in items
        )
        summary = {
            "timeline": plan.timeline_name,
            "fps": plan.fps,
            "mode": mode,
            "source_segments": plan.source_segments,
            "merged_segments": plan.merged_segments,
            "planned_markers": len(plan.markers),
            "replace_generated": replace_generated,
            "speakers": sorted(set(marker.speaker for marker in plan.markers)),
        }

        if already_current:
            return OperationResult(
                True,
                unchanged=len(plan.markers),
                warnings=list(plan.warnings),
                details=[dict(summary, status="already-current")],
            )

        details = [summary] + [{
            "speaker": marker.speaker,
            "clip": _call(marker.item, "GetName", ""),
            "timeline_start_frame": marker.absolute_start,
            "timeline_end_frame_exclusive": marker.absolute_end,
            "clip_marker_frame": marker.clip_frame,
            "duration_frames": marker.duration,
            "color": marker.color,
        } for marker in plan.markers]

        if mode == "preview":
            return OperationResult(
                True, changed=len(plan.markers),
                warnings=list(plan.warnings), details=details
            )

        failure = ""
        for item in items.values():
            if not self._delete_generated(item):
                failure = "Could not remove existing generated speaker markers."
                break

        if not failure:
            for marker in plan.markers:
                try:
                    marker.item.AddMarker(
                        marker.clip_frame, marker.color, marker.name, marker.note,
                        marker.duration, marker.custom_data
                    )
                except Exception as exc:
                    failure = "Resolve could not add %s: %s" % (marker.name, exc)
                    break
                if not self._state_matches(marker.item, marker.clip_frame, marker.state()):
                    failure = "Resolve did not verify %s." % marker.name
                    break

        if not failure:
            for item_id, item in items.items():
                if self._generated_for_item(item) != desired.get(item_id, {}):
                    failure = "Final speaker-marker readback did not match the plan."
                    break

        if not failure:
            return OperationResult(
                True,
                changed=len(plan.markers),
                warnings=list(plan.warnings),
                details=details + [{"verified": True}],
            )

        rollback_failed = []
        for item_id, item in items.items():
            if not self._restore_generated(item, snapshots.get(item_id, {})):
                rollback_failed.append(_call(item, "GetName", item_id))
        if rollback_failed:
            failure = "CRITICAL: %s Rollback failed for %s." % (
                failure, ", ".join(rollback_failed)
            )
        else:
            failure += " Previous generated speaker markers were restored."

        return OperationResult(
            False, failed=1, warnings=list(plan.warnings),
            errors=[failure], details=details
        )

    def analyze_select_speakers_and_mark(
        self,
        segments=None,
        analyzer=None,
        timeline=None,
        speaker_map=None,
        speaker_colors=None,
        mode="apply",
        identity_threshold=0.85,
        merge_gap_ms=350,
        minimum_duration_ms=300,
        unknown_color="Cream",
        overlap_color="Fuchsia",
        primary_video_track=1,
        require_select=True,
        replace_generated=True,
    ):
        """Analyze/consume speaker turns and add range markers to Select clips."""

        context = self.context_service.refresh_context()
        timeline = timeline or context.timeline
        if not timeline:
            return OperationResult(False, failed=1, errors=["Open a Resolve timeline first."])

        timeline_name = str(_call(timeline, "GetName", "") or "")
        if require_select and "SELECT" not in timeline_name.upper():
            return OperationResult(
                False, failed=1,
                errors=["Target timeline is not a Select timeline: %s" % (timeline_name or "<unnamed>")]
            )

        fps = float(self.context_service.get_project_fps())
        if segments is None:
            backend = analyzer or self.analyzer
            if backend is None:
                return OperationResult(
                    False,
                    failed=1,
                    errors=[
                        "Speaker analysis backend is unavailable. Resolve can write clip markers, "
                        "but its documented scripting API does not expose speaker-detection segments. "
                        "Provide a diarization/analyzer adapter or precomputed segments."
                    ],
                )
            try:
                if callable(backend):
                    segments = backend(timeline, fps)
                elif callable(getattr(backend, "analyze", None)):
                    segments = backend.analyze(timeline, fps)
                else:
                    return OperationResult(False, failed=1, errors=["Speaker analyzer is not callable."])
            except Exception as exc:
                return OperationResult(False, failed=1, errors=["Speaker analysis failed: %s" % exc])

        try:
            plan = self.plan(
                segments=segments,
                timeline=timeline,
                speaker_map=speaker_map,
                speaker_colors=speaker_colors,
                identity_threshold=identity_threshold,
                merge_gap_ms=merge_gap_ms,
                minimum_duration_ms=minimum_duration_ms,
                unknown_color=unknown_color,
                overlap_color=overlap_color,
                primary_video_track=primary_video_track,
            )
        except Exception as exc:
            return OperationResult(False, failed=1, errors=["Could not plan speaker markers: %s" % exc])

        return self.apply(plan, mode=mode, replace_generated=replace_generated)
