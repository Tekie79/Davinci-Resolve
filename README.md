# Meher Flow Resolve Hub

**Meher Flow Resolve Hub v0.3.22** is a modular DaVinci Resolve companion built
with Fusion UIManager. It centralizes marker, metadata, clip-name, still, and
media-health work into one matte Meher Flow Amber workstation.

The P0 interaction model is:

> See it → navigate it → edit it → batch it → preview it → apply it → undo it

## Workspaces

- **Markers** — browse/filter/sort timeline markers, navigate, edit details and
  frame-accurate ranges, nudge by 1/5/10 frames, apply presets, batch preview,
  safely replace markers with rollback, create still queues, and Undo.
- **Metadata** — browse selected/current-bin clips, inspect and edit fields,
  batch set/clear/append/prepend/find-replace/copy, preview, apply, Undo, and
  export/import CSV previews.
- **Rename** — preview Resolve clip names using tokens, prefix/suffix,
  find/replace, regex, case, whitespace normalization, numbering, missing-token
  validation, conflict detection, safe-count apply, and Undo. Source files are
  never renamed.
- **Stills** — preserve Grab Current Frame, editable names, fixed PNG suffix,
  folder and Media Pool bin selection, Master fallback, plus marker and selected
  timeline-clip first/middle/last batch queues, lazy image preview, and
  double-click source navigation.
- **Health** — read-only checks for offline paths, reliably detectable proxies,
  frame-rate/resolution/codec review, required metadata, audio, short clips,
  duplicate paths/names, and current-timeline usage. Reports export to CSV/JSON.
- **History** — persistent application operation history and guarded Undo.
- **Settings** — selection, window, thumbnail, marker preset, metadata, and still
  preferences stored in a user-writable JSON file.

## Architecture

The Resolve menu entry is [`Meher Flow Resolve Hub.py`](./Meher%20Flow%20Resolve%20Hub.py).
It adds its containing directory to `sys.path` and launches the
`meher_resolve_hub` package. [`Media Manager.py`](./Media%20Manager.py) remains a
temporary compatibility launcher and preserves the v0.2.2 helper API.

```text
meher_resolve_hub/
├── app.py                 composition root
├── resolve_context.py     fresh project/timeline context
├── selection.py           explicit shared selection modes
├── navigation.py          playhead and return-position state
├── timecode.py            SMPTE/frame conversion, including drop-frame
├── capabilities.py        guarded Resolve API detection
├── thumbnails.py          shared lazy thumbnail cache
├── history.py             operation history and Undo dispatch
├── preferences.py         cross-platform JSON settings
├── models/                stable records, previews, results, reports
├── services/              marker/metadata/rename/still/health workflows
└── ui/                    one shell plus modular workspace layouts
```

Resolve-facing mutations return structured results and verify important writes.
Marker edits use one transaction path: validate, read, delete, recreate, verify,
restore the original on failure, and prominently report rollback failure.

## Install

On macOS, deploy or update everything with one command from this directory:

```bash
./deploy.sh
```

The command validates the Python entry points, runs the automated tests, and
installs the runtime package and Resolve Utility menu scripts. If the Hub is
already open, close it and reopen it after deployment.

Copy both launchers into Resolve's per-user `Fusion/Scripts/Utility` directory.
Install the `meher_resolve_hub` package in the Resolve Hub runtime directory so
Resolve does not recursively expose internal modules as menu scripts. On macOS:

```text
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/
~/Library/Application Support/Meher Flow/Resolve Hub/runtime/meher_resolve_hub/
```

Restart Resolve, then use **Workspace → Scripts → Meher Flow Resolve Hub**.
The old **Media Manager** menu entry launches the same application during the
migration period.

## User data

macOS stores preferences, history, logs, and thumbnails under:

```text
~/Library/Application Support/Meher Flow/Resolve Hub/
```

The default durable still folder is:

```text
~/Pictures/DaVinci Resolve/Meher Flow Resolve Hub/<Project>/
```

Media Pool bins reference the saved PNG; they do not contain its bytes.

## Development

```bash
'/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Applications/ResolvePython' \
  -m unittest discover -s tests -v
```

The suite contains Resolve proxy mocks and pure-logic tests. See
[`MANUAL_RESOLVE_ACCEPTANCE.md`](./MANUAL_RESOLVE_ACCEPTANCE.md) for the live
Resolve matrix and [`P0_IMPLEMENTATION_NOTES.md`](./P0_IMPLEMENTATION_NOTES.md)
for API limitations and deliberate safe degradations.
