"""Local stdio MCP server for Codex -> installed Resolve Hub runtime.

Run with:
    python -m meher_resolve_hub.mcp_server

The server connects to the currently running DaVinci Resolve instance and
exposes high-level, guarded tools. Secrets are never accepted as MCP tool
arguments; OpenAI credentials are resolved from the OS credential store.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from mcp.server import MCPServer

from .app import get_resolve_app
from .constants import APP_VERSION, MARKER_COLORS
from .credential_service import OpenAICredentialStore
from .speaker_markers import analyze_select_speakers_and_mark


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
def resolve_status() -> Dict[str, object]:
    """Return current Resolve context and secure OpenAI credential status."""
    resolve = _resolve()
    project = _project(resolve)
    timeline = project.GetCurrentTimeline()
    credential = OpenAICredentialStore().status()
    return {
        "resolve_hub_version": APP_VERSION,
        "project": str(project.GetName() or ""),
        "timeline": _name(timeline),
        "openai_configured": bool(credential.configured),
        "credential_backend": credential.backend,
        "credential_masked": credential.masked,
    }


@mcp.tool()
def list_select_timelines() -> List[str]:
    """List Select timelines in the currently open Resolve project."""
    project = _project(_resolve())
    return [
        _name(timeline)
        for timeline in _all_timelines(project)
        if "SELECT" in _name(timeline).upper()
    ]


@mcp.tool()
def analyze_select_speakers_and_mark_tool(
    episode: Optional[int] = None,
    scene: Optional[str] = None,
    timeline_name: Optional[str] = None,
    characters: Optional[List[str]] = None,
    speaker_colors: Optional[Dict[str, str]] = None,
    mode: str = "preview",
    voice_reference_dir: Optional[str] = None,
    include_transcript: bool = False,
) -> Dict[str, object]:
    """Analyze a Select timeline audio and write speaker range clip markers.

    The OpenAI key is read from secure local credential storage. Do not pass a
    secret to this tool. characters limits known voice references to the people
    expected in this scene (maximum four).
    """
    if mode not in ("preview", "apply"):
        raise RuntimeError("mode must be preview or apply.")

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
    switched = previous is not target

    references, reference_warnings = _voice_references(
        characters or [], voice_reference_dir
    )

    try:
        if switched:
            changed = project.SetCurrentTimeline(target)
            if not changed:
                raise RuntimeError("Resolve could not activate the target Select timeline.")

        result = analyze_select_speakers_and_mark(
            resolve,
            timeline=target,
            known_speaker_references=references,
            speaker_colors=colors,
            mode=mode,
            include_transcript=bool(include_transcript),
        )
        result.warnings = reference_warnings + list(result.warnings)
        output = _result_dict(result)
        output["characters_requested"] = list(characters or [])
        output["voice_references_used"] = sorted(references)
        output["timeline"] = _name(target)
        output["mode"] = mode
        return output
    finally:
        if switched and previous:
            try:
                project.SetCurrentTimeline(previous)
            except Exception:
                pass


if __name__ == "__main__":
    mcp.run()
