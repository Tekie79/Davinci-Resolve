# P0 Implementation Notes

## Resolve API boundaries

- Resolve 21.1 exposes marker read/add/delete and custom-data methods, but no
  marker property setters. All marker changes therefore use verified
  delete/recreate with rollback.
- The scripting API does not expose a general timeline playback command. **Play
  Range** is visible but disabled with an explanation. Start/end navigation is
  frame accurate.
- The marker range editor uses separate draggable start/end sliders because
  Fusion UIManager has no portable dual-handle range control. Exact range
  editing also remains available through timecode fields, playhead setters, and
  1/5/10-frame nudge controls.
- Proxy state is reported only when Resolve exposes a reliable proxy property.
  Otherwise Media Health identifies the check as skipped instead of asserting a
  missing proxy.
- Thumbnail generation uses direct current-frame export, waits for Resolve to
  display the requested frame, and restores the original playhead. Cached PNGs
  are reduced toward 960×540 using Pillow when available or macOS `sips` as a
  dependency-free fallback. A thumbnail failure never blocks editing.
- Cross-session Undo records persist, but an operation is refused when its
  target proxy is no longer loaded or its current value no longer matches the
  value Resolve Hub applied.

- Resolve 21 can detect/transcribe speakers in the UI, but the documented scripting API does not expose the speaker-detection segment list as a stable callable interface. The production speaker-marker path therefore exports the Select timeline audio and uses OpenAI `gpt-4o-transcribe-diarize`; precomputed segments and injected analyzers remain supported for tests/alternate backends.
- TimelineItem marker APIs use clip-relative marker offsets. Speaker turns are kept in absolute timeline frames for analysis, split at TimelineItem boundaries, then converted to clip-relative offsets before AddMarker.
- Resolve supports a fixed named marker palette. Orange is not in the supported marker color set used by Resolve Hub; project mappings must use supported names such as Yellow, Sand, or Cocoa.
- Transcript text is deliberately optional for speaker markers. Mixed Amharic/English projects use diarization timing and confirmed voice references rather than treating transcript wording as identity proof.
- OpenAI file transcription accepts bounded file uploads. Oversized WAV analysis is split into overlapping chunks; only the owned midpoint region of each chunk is retained to avoid duplicate overlap segments.
- Known speaker references are optional and limited to four per diarization request. Unmatched speakers remain UNKNOWN instead of being inferred from unreliable text.

- On macOS the OpenAI API key is stored with native Security.framework Keychain APIs. It is never written to settings.json, MCP arguments, marker data, or Git. OPENAI_API_KEY remains a compatibility fallback only.
- The Resolve Settings UI clears the key input immediately after save and shows only masked credential status.
- The local MCP server is launched from the installed runtime. Production Codex use does not require reading the development repository.
- Speaker-analysis audio is rendered safely as WAV first. If ffmpeg is available, the temporary upload copy is converted to mono MP3 (64 kbps default) to reduce file size; WAV remains the fallback.
- The MCP speaker tool accepts 1-4 scene character names and resolves only those local reference files. The API key is intentionally not an MCP parameter.

## Safety decisions

- P0 renames Resolve clip names only. Camera-original files remain untouched.
- Health scans never mutate or delete media.
- Batch still captures build and validate a queue before capture. Import is a
  separate action so queued or newly captured files can be renamed safely first.
- Once a still has been imported, Resolve Hub refuses to rename its disk file;
  doing so would break the Media Pool reference.
- Every unsupported selection mode remains explicit and disabled/unavailable;
  the application does not substitute another source.
- Speaker-marker reruns remove/replace only markers carrying Resolve Hub speaker-dialogue customData. Manual markers and unrelated generated markers are preserved.
- Speaker-marker batch writes are read back. On failure, the service restores the previous generated speaker-marker snapshot; it never shifts a manual marker to hide a same-frame collision.

## Compatibility retained from v0.2.2

- Resolve, Fusion, and BMD connection handling.
- Direct current-frame export with Gallery fallback.
- Temporary preview cleanup.
- Safe filename and generated still naming.
- Folder creation and fixed `.png` suffix.
- Recursive bin enumeration and Master fallback.
- Media Pool import retries and Media Storage fallbacks.
- Restoration of the previously active Media Pool bin.
- Return to the Stills workspace after saving.
