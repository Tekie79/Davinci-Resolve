# Manual Resolve Acceptance — v0.3.0

Use a disposable test project/timeline before testing mutations. Record Resolve
version, OS, page, project, timeline, and selection source with each run.

## Shell and shared foundation

- [ ] Launch **Workspace → Scripts → Meher Flow Resolve Hub** from Media, Cut,
  Edit, Fusion, Color, Fairlight, and Deliver with an active timeline.
- [ ] Confirm a single 1240×780 resizable shell opens and a second launch raises
  the existing shell.
- [ ] Close and reopen the shell; confirm no stale hidden window appears.
- [ ] Confirm project, timeline, page, and playhead context refresh accurately.
- [ ] Exercise Media Pool Selection, Timeline Selection, Current Bin, Bin +
  Sub-Bins, and Current Timeline. Unsupported sources must explain why and never
  fall back.
- [ ] Confirm workspace and settings persistence after restart.
- [ ] Confirm serious errors appear in the global error panel, not status text
  alone.

## Marker Manager

- [ ] Browse 500+ markers; search name/notes/custom data and filter by color,
  point/range, notes, and sort order.
- [ ] Navigate previous/next, same-color previous/next, start/end, and Return.
- [ ] Refresh one and all visible thumbnails; verify no playhead drift.
- [ ] Edit name, color, and notes; confirm read-back and one History record.
- [ ] Edit start, end, and duration; nudge each edge by 1/5/10 frames.
- [ ] Set start/end/move from playhead and verify duration rules.
- [ ] Select multiple markers; preview/apply name, color, notes, range, movement,
  and delete operations. Confirm no silent batch apply.
- [ ] Add/update/reorder/delete marker presets and apply a preset.
- [ ] Force replacement failure and confirm the original marker is restored.
- [ ] Force rollback failure in a disposable timeline and confirm the critical
  error includes recovery data.
- [ ] Undo supported marker edits and verify values.

## Metadata Manager

- [ ] Browse 1,000+ selected/current-bin clips without re-traversal per click.
- [ ] Navigate previous/next and Reveal without changing Resolve selection on
  every row move.
- [ ] Inspect common and custom fields; verify failed/non-editable fields report
  a per-clip error.
- [ ] Preview/apply Set, Clear, Append, Prepend, Find/Replace, Copy Field, and Fill
  Blanks Only across a multi-selection.
- [ ] Export CSV, change it externally, preview import, apply, and Undo.

## Rename Manager

- [ ] Preview all documented tokens, prefix/suffix, literal and regex replace,
  whitespace normalization, case, and sequential numbering.
- [ ] Confirm missing tokens, empty names, invalid values, length, and duplicate
  outputs are excluded from Apply.
- [ ] Apply only selected safe rows; confirm Resolve clip names change and source
  filenames do not.
- [ ] Undo and confirm original Resolve clip names return.

## Still Manager

- [ ] Grab Current Frame from each Resolve page; name the still; select a disk
  folder and Media Pool bin; save and confirm both file and bin item.
- [ ] Leave the bin unset and confirm Master fallback.
- [ ] Force direct-export unavailability and verify Gallery fallback.
- [ ] Build/preview queues from selected markers, visible marker results, and
  selected timeline clips at first/middle/last frames.
- [ ] Verify filename templates and disk/queue conflict detection.
- [ ] Capture a queue and confirm the original playhead is restored.
- [ ] Rename captured-but-unimported stills, import them, then confirm disk rename
  is blocked to protect the Media Pool link.
- [ ] Navigate from a captured still to its source and Return.
- [ ] Confirm still import restores the previously active Media Pool bin.

## Media Health

- [ ] Scan each supported selection scope and verify grouped summary counts.
- [ ] Validate offline, proxy-when-reliable, FPS Review, resolution, required
  metadata, duplicate path/name+duration, codec, short clip, audio-when-reliable,
  and used/unused classifications.
- [ ] Confirm high-frame-rate mismatches say Review rather than Error.
- [ ] Navigate previous/next problems, Reveal, and Ignore for Session.
- [ ] Export CSV and JSON and confirm the scan did not modify media.

## History, failure, and drift

- [ ] Verify Undo validates current state and reports partial failure.
- [ ] Verify stale proxies, `False`, `None`, exceptions, and silent write failures
  show exact actionable errors.
- [ ] Confirm no lost marker after failed mutation, no playhead drift after
  thumbnails/batch stills, and no current-bin drift after still import.

