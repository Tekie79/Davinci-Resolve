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

## Safety decisions

- P0 renames Resolve clip names only. Camera-original files remain untouched.
- Health scans never mutate or delete media.
- Batch still captures build and validate a queue before capture. Import is a
  separate action so queued or newly captured files can be renamed safely first.
- Once a still has been imported, Resolve Hub refuses to rename its disk file;
  doing so would break the Media Pool reference.
- Every unsupported selection mode remains explicit and disabled/unavailable;
  the application does not substitute another source.

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
