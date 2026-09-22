"""Local stdio MCP server for Codex -> installed Resolve Hub runtime.

Run with:
    python -m meher_resolve_hub.mcp_server

The server connects to the currently running DaVinci Resolve instance and
exposes high-level, guarded tools. Secrets are never accepted as MCP tool
arguments; OpenAI credentials are resolved from the OS credential store.
"""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from mcp.server import MCPServer

from .app import get_resolve_app
from .constants import APP_VERSION, MARKER_COLORS
from .credential_service import ElevenLabsCredentialStore, OpenAICredentialStore
from .resolve_context import ResolveContextService
from .selection import SelectionEngine, SelectionUnavailable
from .services.keyword_clip_rename_service import KeywordClipRenameService
from .services.metadata_service import MetadataService
from .services.rename_service import RenameService
from .services.speaker_marker_service import SpeakerMarkerService
from .services.still_service import StillService
from .speaker_markers import analyze_select_speakers_and_mark as run_speaker_marker_workflow
from .timecode import timeline_frame_to_timecode
from .utils import proxy_id, same_proxy


mcp = MCPServer(
    "Meher Flow Resolve Hub",
    instructions=(
        "Use these tools only against the running local DaVinci Resolve instance. "
        "For speaker dialogue markers, prefer mode=preview first, require a Select "
        "timeline, preserve manual markers, and never request or transmit the OpenAI "
        "API key through MCP; Resolve Hub reads it from the OS credential store."
    ),
)


def _resolve():
    resolve = get_resolve_app()
    if not resolve:
        raise RuntimeError(
            "DaVinci Resolve is not reachable. Start Resolve and enable its local "
            "scripting integration before calling this tool."
        )
    return resolve


def _project(resolve):
    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject() if manager else None
    if not project:
        raise RuntimeError("Open a DaVinci Resolve project first.")
    return project


def _all_timelines(project):
    result = []
    try:
        count = int(project.GetTimelineCount() or 0)
    except Exception:
        count = 0
    for index in range(1, count + 1):
        try:
            timeline = project.GetTimelineByIndex(index)
            if timeline:
                result.append(timeline)
        except Exception:
            continue
    return result


def _name(timeline):
    try:
        return str(timeline.GetName() or "")
    except Exception:
        return ""


def _scene_tokens(scene):
    text = str(scene or "").strip()
    if not text:
        return []
    tokens = {text.upper()}
    if re.fullmatch(r"\d+", text):
        tokens.add("SC%02d" % int(text))
        tokens.add("SC%s" % int(text))
    else:
        tokens.add("SC" + text.upper())
    return sorted(tokens)


def _target_timeline(project, timeline_name=None, episode=None, scene=None):
    timelines = _all_timelines(project)
    if timeline_name:
        matches = [timeline for timeline in timelines if _name(timeline) == str(timeline_name)]
        if len(matches) != 1:
            raise RuntimeError(
                "Expected one exact timeline named %s; found %d."
                % (timeline_name, len(matches))
            )
        return matches[0]

    current = project.GetCurrentTimeline()
    current_name = _name(current).upper() if current else ""
    episode_token = "EP%02d" % int(episode) if episode is not None else ""
    scene_tokens = _scene_tokens(scene)

    def matches(name):
        upper = name.upper()
        if "SELECT" not in upper:
            return False
        if episode_token and episode_token not in upper:
            return False
        if scene_tokens and not any(token in upper for token in scene_tokens):
            return False
        return True

    if current and matches(current_name):
        return current

    candidates = [timeline for timeline in timelines if matches(_name(timeline))]
    if len(candidates) != 1:
        names = [_name(value) for value in candidates]
        raise RuntimeError(
            "Could not resolve exactly one Select timeline for EP=%s SCENE=%s. "
            "Candidates: %s"
            % (episode, scene, ", ".join(names) if names else "none")
        )
    return candidates[0]


def _safe_character_filename(value):
    text = re.sub(r"[^A-Za-z0-9 _.-]+", "", str(value or "")).strip()
    return text


def _voice_references(characters, reference_dir=None):
    characters = [str(value).strip() for value in (characters or []) if str(value).strip()]
    if len(characters) > 4:
        raise RuntimeError("A maximum of four known speaker references is supported per request.")

    root_value = reference_dir or os.environ.get("YSEW_VOICE_REFERENCE_DIR", "")
    if not root_value:
        return {}, [
            "No voice-reference directory was supplied. Speakers without an API "
            "known-reference match will remain UNKNOWN."
        ]

    root = Path(root_value).expanduser()
    if not root.is_dir():
        return {}, ["Voice-reference directory does not exist: %s" % root]

    references = {}
    warnings = []
    extensions = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".webm")
    for character in characters:
        base = _safe_character_filename(character)
        stems = [base, base.replace(" ", "_"), base.replace(" ", "-")]
        found = None
        for stem in dict.fromkeys(stems):
            for extension in extensions:
                candidate = root / (stem + extension)
                if candidate.is_file():
                    found = candidate
                    break
            if found:
                break
        if found:
            references[character] = str(found)
        else:
            warnings.append("No confirmed voice reference found for %s." % character)
    return references, warnings


def _find_bin_by_path(media_pool, bin_path):
    root = media_pool.GetRootFolder() if media_pool else None
    if not root:
        raise RuntimeError("Resolve Media Pool is unavailable.")

    parts = [part for part in str(bin_path or "").replace("\\", "/").split("/") if part]
    if not parts:
        return root

    try:
        root_name = str(root.GetName() or "")
    except Exception:
        root_name = ""
    if parts and parts[0].casefold() == root_name.casefold():
        parts = parts[1:]

    current = root
    for part in parts:
        try:
            children = list(current.GetSubFolderList() or [])
        except Exception:
            children = []
        matches = []
        for child in children:
            try:
                name = str(child.GetName() or "")
            except Exception:
                name = ""
            if name.casefold() == part.casefold():
                matches.append(child)
        if len(matches) != 1:
            raise RuntimeError(
                "Media Pool bin path could not be resolved at %s in %s."
                % (part, bin_path)
            )
        current = matches[0]
    return current


def _video_timeline_items(timeline, selected_only=False):
    if not timeline:
        return []
    if selected_only:
        try:
            selected = list(timeline.GetSelectedClips() or [])
        except Exception:
            selected = []
        result = []
        for item in selected:
            try:
                if item.GetMediaPoolItem():
                    result.append(item)
            except Exception:
                continue
        return result

    result = []
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        track_count = 0
    for track_index in range(1, track_count + 1):
        try:
            result.extend(list(timeline.GetItemListInTrack("video", track_index) or []))
        except Exception:
            continue
    return result


def _unique_media_items(items):
    clips, seen = [], set()
    for item in items:
        try:
            clip = item.GetMediaPoolItem()
        except Exception:
            clip = None
        if not clip:
            continue
        identity = proxy_id(clip)
        if identity in seen:
            continue
        seen.add(identity)
        clips.append(clip)
    return clips


def _timeline_order_hints(items):
    result = {}
    for item in items:
        try:
            clip = item.GetMediaPoolItem()
            identity = proxy_id(clip)
            start = int(item.GetStart())
        except Exception:
            continue
        if identity not in result or start < result[identity]:
            result[identity] = start
    return result


def _keyword_rename_source(resolve, source, recursive=False):
    context_service = ResolveContextService(resolve)
    context = context_service.refresh_context()
    if not context.project:
        raise RuntimeError("Open a Resolve project first.")

    source_key = str(source or "timeline").strip().casefold().replace("-", "_")
    selection_engine = SelectionEngine(context_service)

    if source_key in ("timeline", "current_timeline"):
        items = _video_timeline_items(context.timeline, selected_only=False)
        return _unique_media_items(items), items, "Current Timeline"
    if source_key in ("timeline_selection", "selected_timeline", "selection"):
        items = _video_timeline_items(context.timeline, selected_only=True)
        return _unique_media_items(items), items, "Timeline Selection"
    if source_key in ("bin", "media_bin", "current_bin"):
        selection = selection_engine.get_current_bin_items(bool(recursive))
        return selection.clips, [], selection.mode
    if source_key in ("media_pool_selection", "media_selection"):
        selection = selection_engine.get_media_pool_selection()
        return selection.clips, [], selection.mode
    raise RuntimeError(
        "source must be timeline, timeline_selection, current_bin, or media_pool_selection."
    )


def _preview_dict(preview):
    rows = []
    for change in preview.changes:
        context = dict(change.context or {})
        rows.append({
            "current_name": str(change.before),
            "proposed_name": str(change.after),
            "status": str(change.status),
            "keywords": context.get("keywords", ""),
            "subject": context.get("subject", ""),
            "shot_type": context.get("shot_type", ""),
            "frame_start": context.get("frame_start"),
            "frame_end": context.get("frame_end"),
            "take": context.get("take"),
            "explicit_take": context.get("explicit_take"),
            "missing": list(context.get("missing", []) or []),
        })
    return {
        "changed": int(preview.changed),
        "unchanged": int(preview.unchanged),
        "conflicts": int(preview.conflicts),
        "rows": rows,
    }


def _result_dict(result):
    return {
        "success": bool(result.success),
        "changed": int(result.changed),
        "unchanged": int(result.unchanged),
        "failed": int(result.failed),
        "warnings": list(result.warnings),
        "errors": list(result.errors),
        "details": list(result.details),
    }


@mcp.tool()
async def resolve_status() -> Dict[str, object]:
    """Return current Resolve context and secure OpenAI credential status."""
    resolve = _resolve()
    project = _project(resolve)
    timeline = project.GetCurrentTimeline()
    credential = OpenAICredentialStore().status()
    elevenlabs_credential = ElevenLabsCredentialStore().status()
    return {
        "resolve_hub_version": APP_VERSION,
        "project": str(project.GetName() or ""),
        "timeline": _name(timeline),
        "openai_configured": bool(credential.configured),
        "openai_credential_backend": credential.backend,
        "openai_credential_masked": credential.masked,
        "elevenlabs_configured": bool(elevenlabs_credential.configured),
        "elevenlabs_credential_backend": elevenlabs_credential.backend,
        "elevenlabs_credential_masked": elevenlabs_credential.masked,
    }


@mcp.tool()
async def list_select_timelines() -> List[str]:
    """List Select timelines in the currently open Resolve project."""
    project = _project(_resolve())
    return [
        _name(timeline)
        for timeline in _all_timelines(project)
        if "SELECT" in _name(timeline).upper()
    ]


@mcp.tool()
async def analyze_select_speakers_and_mark(
    episode: Optional[int] = None,
    scene: Optional[str] = None,
    timeline_name: Optional[str] = None,
    characters: Optional[List[str]] = None,
    speaker_colors: Optional[Dict[str, str]] = None,
    mode: str = "preview",
    voice_reference_dir: Optional[str] = None,
    include_transcript: bool = False,
    provider: str = "openai",
    audio_render_preset: str = "Codex_Mp3",
    audio_primary_dir: str = "/Volumes/Harvest SSD/Select_ref_mp3_audios",
    audio_fallback_dir: str = "/Users/harvest/Documents/Ysew_Project/Ref audio",
    elevenlabs_model: str = "scribe_v2",
    elevenlabs_language_code: Optional[str] = None,
    elevenlabs_num_speakers: Optional[int] = None,
    elevenlabs_use_speaker_library: bool = False,
    elevenlabs_keyterms: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Analyze Select audio with OpenAI or ElevenLabs and write clip markers.

    Provider API keys are read from secure local credential storage. Do not pass
    secrets through MCP. OpenAI may use up to four requested local voice
    references; ElevenLabs can optionally use its workspace speaker library.
    """
    if mode not in ("preview", "apply"):
        raise RuntimeError("mode must be preview or apply.")
    provider = str(provider or "openai").strip().casefold()
    if provider not in ("openai", "elevenlabs"):
        raise RuntimeError("provider must be openai or elevenlabs.")

    colors = dict(speaker_colors or {})
    unsupported = sorted(set(colors.values()) - set(MARKER_COLORS))
    if unsupported:
        raise RuntimeError(
            "Unsupported Resolve marker colors: %s" % ", ".join(unsupported)
        )

    resolve = _resolve()
    project = _project(resolve)
    target = _target_timeline(
        project,
        timeline_name=timeline_name,
        episode=episode,
        scene=scene,
    )
    previous = project.GetCurrentTimeline()
    switched = not same_proxy(previous, target)

    if provider == "openai":
        references, reference_warnings = _voice_references(
            characters or [], voice_reference_dir
        )
    else:
        references, reference_warnings = {}, []

    try:
        if switched:
            changed = project.SetCurrentTimeline(target)
            if not changed:
                raise RuntimeError("Resolve could not activate the target Select timeline.")

        result = run_speaker_marker_workflow(
            resolve,
            timeline=target,
            known_speaker_references=references,
            speaker_colors=colors,
            mode=mode,
            include_transcript=bool(include_transcript),
            analysis_provider=provider,
            elevenlabs_model=str(elevenlabs_model or "scribe_v2"),
            elevenlabs_language_code=elevenlabs_language_code,
            elevenlabs_num_speakers=elevenlabs_num_speakers,
            elevenlabs_use_speaker_library=bool(elevenlabs_use_speaker_library),
            elevenlabs_keyterms=list(elevenlabs_keyterms or []),
            audio_export_options={
                "render_preset": str(audio_render_preset),
                "primary_output_dir": str(audio_primary_dir),
                "fallback_output_dir": str(audio_fallback_dir),
                "preferred_format": "mp3",
            },
        )
        result.warnings = reference_warnings + list(result.warnings)
        output = _result_dict(result)
        output["characters_requested"] = list(characters or [])
        output["voice_references_used"] = sorted(references)
        output["timeline"] = _name(target)
        output["mode"] = mode
        output["provider"] = provider
        output["elevenlabs_use_speaker_library"] = bool(elevenlabs_use_speaker_library)
        return output
    finally:
        if switched and previous:
            try:
                project.SetCurrentTimeline(previous)
            except Exception:
                pass



@mcp.tool()
async def rename_clips_from_keywords(
    source: str = "timeline",
    mode: str = "preview",
    keyword_field: str = "Keywords",
    recursive: bool = False,
    take_width: int = 2,
) -> Dict[str, object]:
    """Preview/apply Character_ShotType_T## labels from Resolve Keywords metadata.

    source:
      timeline             all video clips in the current timeline
      timeline_selection   selected timeline video clips
      current_bin          clips in the current Media Pool bin
      media_pool_selection selected Media Pool clips

    This changes Resolve Media Pool clip labels only. It never renames source
    files on disk. Timeline instances that reference the same Media Pool clip
    will display the updated shared clip label.
    """
    if mode not in ("preview", "apply"):
        raise RuntimeError("mode must be preview or apply.")

    resolve = _resolve()
    clips, timeline_items, resolved_source = _keyword_rename_source(
        resolve, source, recursive=recursive
    )
    if not clips:
        raise RuntimeError("No clips were found for the requested source.")

    metadata = MetadataService()
    records = metadata.build_records(clips, timeline_items)
    rename = RenameService()
    service = KeywordClipRenameService(rename)
    preview = service.preview(
        records,
        keyword_field=keyword_field,
        take_width=max(1, int(take_width)),
        order_hints=_timeline_order_hints(timeline_items),
    )

    output = {
        "source": resolved_source,
        "mode": mode,
        "keyword_field": keyword_field,
        "naming_standard": "Character_ShotType_T##",
        "preview": _preview_dict(preview),
        "source_files_renamed": False,
    }
    if mode == "preview":
        return output

    result = service.apply_preview(preview)
    output["result"] = _result_dict(result)
    return output


@mcp.tool()
async def list_reference_stills(
    bin_path: str = "Master/01_MEDIA/STILLS/CODEX_REF",
) -> Dict[str, object]:
    """Return local reference-still paths and metadata from a Media Pool bin."""
    resolve = _resolve()
    project = _project(resolve)
    media_pool = project.GetMediaPool()
    folder = _find_bin_by_path(media_pool, bin_path)
    try:
        clips = list(folder.GetClipList() or [])
    except Exception:
        clips = []

    assets = []
    for clip in clips:
        try:
            name = str(clip.GetName() or "")
        except Exception:
            name = ""
        try:
            metadata = dict(clip.GetMetadata() or {})
        except Exception:
            metadata = {}
        try:
            properties = dict(clip.GetClipProperty() or {})
        except Exception:
            properties = {}
        path = str(properties.get("File Path") or properties.get("File Name") or "")
        assets.append({
            "name": name,
            "path": path,
            "keywords": str(metadata.get("Keywords", "") or ""),
            "metadata": metadata,
        })

    return {
        "bin_path": bin_path,
        "count": len(assets),
        "assets": assets,
        "note": (
            "Reference filenames/metadata may provide project context. Do not use "
            "face matching to identify a real person; character identity must come "
            "from explicit project metadata or editor confirmation."
        ),
    }


@mcp.tool()
async def export_timeline_clip_visuals(
    selected_only: bool = False,
    position: str = "middle",
    max_clips: int = 100,
) -> Dict[str, object]:
    """Export representative PNGs for current-timeline video clips for Codex vision."""
    resolve = _resolve()
    context_service = ResolveContextService(resolve)
    context = context_service.refresh_context()
    if not context.project or not context.timeline:
        raise RuntimeError("Open the target Resolve timeline first.")
    if "SELECT" not in str(context.timeline_name or "").upper():
        raise RuntimeError(
            "Visual clip analysis defaults to a Select timeline. Open the Select timeline first."
        )

    normalized_position = str(position or "middle").strip().title()
    if normalized_position not in ("First", "Middle", "Last"):
        raise RuntimeError("position must be first, middle, or last.")

    items = _video_timeline_items(context.timeline, selected_only=bool(selected_only))
    limit = max(1, min(int(max_clips), 500))
    items = items[:limit]
    if not items:
        raise RuntimeError("No video clips were found to export.")

    service = StillService(resolve, context_service)
    fps = context_service.get_project_fps()
    queue = service.queue_from_timeline_items(
        items,
        normalized_position,
        "CodexVisual_{Index}_{Clip}",
        fps,
        context.project_name,
        context.timeline_name,
        context.timeline,
    )
    folder = Path(tempfile.mkdtemp(prefix="meher-visual-frames-"))
    result = service.execute_queue(queue, folder, import_to_bin=False)

    rows = []
    for item, job in zip(items, queue):
        try:
            clip = item.GetMediaPoolItem()
            clip_name = str(clip.GetName() or item.GetName() or "")
            metadata = dict(clip.GetMetadata() or {})
            media_id = proxy_id(clip)
            start = int(item.GetStart())
            end = int(item.GetEnd())
        except Exception:
            clip_name, metadata, media_id, start, end = "", {}, "", None, None
        rows.append({
            "timeline_item_id": proxy_id(item),
            "media_pool_id": media_id,
            "clip_name": clip_name,
            "timeline_start": start,
            "timeline_end": end,
            "keywords": str(metadata.get("Keywords", "") or ""),
            "image_path": str(job.output_path or ""),
            "status": str(job.status),
        })

    return {
        "timeline": context.timeline_name,
        "selected_only": bool(selected_only),
        "position": normalized_position.lower(),
        "temporary_directory": str(folder),
        "capture": _result_dict(result),
        "clips": rows,
        "instruction": (
            "Use Codex image viewing on image_path values for shot type, composition, "
            "wardrobe, props, and location analysis. Do not identify a real person "
            "from facial appearance; use Keywords/editor metadata for character names."
        ),
    }


@mcp.tool()
async def export_active_speaker_visual_samples(
    selected_only: bool = False,
    sample_fps: float = 6.0,
    max_frames_per_clip: int = 24,
    max_clips: int = 50,
) -> Dict[str, object]:
    """Export temporal PNG samples for visual active-speaker analysis.

    This tool exports multiple frames per video TimelineItem so Codex can inspect
    mouth/body motion over time. It does not use audio and does not assign
    character identity from faces.
    """
    resolve = _resolve()
    context_service = ResolveContextService(resolve)
    context = context_service.refresh_context()
    if not context.project or not context.timeline:
        raise RuntimeError("Open the target Resolve timeline first.")
    if "SELECT" not in str(context.timeline_name or "").upper():
        raise RuntimeError(
            "Active-speaker visual analysis requires a Select timeline."
        )

    fps = float(context_service.get_project_fps())
    requested_sample_fps = max(1.0, min(float(sample_fps), min(12.0, fps)))
    max_frames = max(3, min(int(max_frames_per_clip), 120))
    items = _video_timeline_items(
        context.timeline, selected_only=bool(selected_only)
    )[: max(1, min(int(max_clips), 200))]
    if not items:
        raise RuntimeError("No video TimelineItems were found.")

    folder = Path(tempfile.mkdtemp(prefix="meher-visual-frames-"))
    stills = StillService(resolve, context_service)
    previous_timecode = str(context.current_timecode or "")
    groups = []
    capture_errors = []

    try:
        for clip_index, item in enumerate(items, 1):
            try:
                start = int(item.GetStart())
                end = int(item.GetEnd()) - 1
                clip = item.GetMediaPoolItem()
                clip_name = str(clip.GetName() or item.GetName() or "Clip")
                metadata = dict(clip.GetMetadata() or {})
            except Exception as exc:
                capture_errors.append("Clip %s metadata: %s" % (clip_index, exc))
                continue
            if end < start:
                continue

            stride = max(1, int(round(fps / requested_sample_fps)))
            frames = list(range(start, end + 1, stride))
            if frames and frames[-1] != end:
                frames.append(end)
            if len(frames) > max_frames:
                if max_frames == 1:
                    frames = [start]
                else:
                    span = max(0, end - start)
                    frames = sorted(set(
                        start + int(round(span * index / float(max_frames - 1)))
                        for index in range(max_frames)
                    ))

            samples = []
            for sample_index, frame in enumerate(frames, 1):
                try:
                    tc = timeline_frame_to_timecode(
                        context.timeline, frame, fps
                    )
                    context.timeline.SetCurrentTimecode(tc)
                    if not stills._wait_for_timecode(context.timeline, tc):
                        raise RuntimeError(
                            "Resolve did not reach %s before capture." % tc
                        )
                    filename = "clip-%03d_sample-%03d_f%s.png" % (
                        clip_index, sample_index, frame
                    )
                    destination = folder / filename
                    actual = stills._export_current(
                        context.project, context.timeline, destination
                    )
                    if not actual:
                        raise RuntimeError("frame export failed")
                    samples.append({
                        "timeline_frame": int(frame),
                        "timecode": tc,
                        "image_path": str(actual),
                    })
                except Exception as exc:
                    capture_errors.append(
                        "%s frame %s: %s" % (clip_name, frame, exc)
                    )

            groups.append({
                "timeline_item_id": proxy_id(item),
                "media_pool_id": proxy_id(clip),
                "clip_name": clip_name,
                "timeline_start": start,
                "timeline_end_exclusive": end + 1,
                "keywords": str(metadata.get("Keywords", "") or ""),
                "samples": samples,
            })
    finally:
        if previous_timecode:
            try:
                context.timeline.SetCurrentTimecode(previous_timecode)
                stills._wait_for_timecode(
                    context.timeline, previous_timecode
                )
            except Exception:
                capture_errors.append(
                    "Could not restore the previous playhead position."
                )

    return {
        "timeline": context.timeline_name,
        "sample_fps": requested_sample_fps,
        "temporary_directory": str(folder),
        "clips": groups,
        "errors": capture_errors,
        "instruction": (
            "Analyze temporal mouth/body motion to find active visible speakers. "
            "Do not identify real people from facial appearance; use Keywords or "
            "editor-confirmed metadata for character identity."
        ),
    }


@mcp.tool()
async def apply_speaker_segments_to_clips(
    segments: List[Dict[str, object]],
    episode: Optional[int] = None,
    scene: Optional[str] = None,
    timeline_name: Optional[str] = None,
    speaker_colors: Optional[Dict[str, str]] = None,
    mode: str = "preview",
) -> Dict[str, object]:
    """Preview/apply precomputed visual, audio, or hybrid ranges as clip markers."""
    if mode not in ("preview", "apply"):
        raise RuntimeError("mode must be preview or apply.")
    if not segments:
        raise RuntimeError("At least one speaker segment is required.")

    colors = dict(speaker_colors or {})
    unsupported = sorted(set(colors.values()) - set(MARKER_COLORS))
    if unsupported:
        raise RuntimeError(
            "Unsupported Resolve marker colors: %s" % ", ".join(unsupported)
        )

    resolve = _resolve()
    project = _project(resolve)
    target = _target_timeline(
        project,
        timeline_name=timeline_name,
        episode=episode,
        scene=scene,
    )
    previous = project.GetCurrentTimeline()
    switched = not same_proxy(previous, target)

    try:
        if switched:
            changed = project.SetCurrentTimeline(target)
            if not changed:
                raise RuntimeError(
                    "Resolve could not activate the target Select timeline."
                )

        context = ResolveContextService(resolve)
        result = SpeakerMarkerService(context).analyze_select_speakers_and_mark(
            segments=list(segments),
            timeline=target,
            speaker_colors=colors,
            mode=mode,
        )
        output = _result_dict(result)
        output["timeline"] = _name(target)
        output["mode"] = mode
        output["segment_source"] = "precomputed"
        output["marker_target"] = "TimelineItem clip markers"
        return output
    finally:
        if switched and previous:
            try:
                project.SetCurrentTimeline(previous)
            except Exception:
                pass


@mcp.tool()
async def cleanup_visual_analysis_frames(directory: str) -> Dict[str, object]:
    """Delete only a temporary directory created by export_timeline_clip_visuals."""
    path = Path(str(directory or "")).expanduser().resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if path.parent != temp_root or not path.name.startswith("meher-visual-frames-"):
        raise RuntimeError("Refusing to delete a directory not created by visual analysis.")
    existed = path.exists()
    if existed:
        shutil.rmtree(str(path))
    return {"removed": bool(existed), "directory": str(path)}


if __name__ == "__main__":
    mcp.run()
