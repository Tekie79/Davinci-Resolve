# Manual Resolve Acceptance — v0.3.23

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

- [ ] Close Resolve Hub with both the native window control and the in-app ×;
  confirm the window hides immediately, including after previewing a still.
- [ ] While the Hub is open, choose its Resolve Scripts menu entry again and
  confirm it raises the existing window without creating a duplicate.
- [ ] Add, edit, and delete markers with Resolve's native shortcuts while the
  Hub is open; confirm the list updates within one second without Refresh.
- [ ] Single-click a marker row; confirm the row remains visibly highlighted,
  the editor stays populated after Save, and the playhead moves to its start.
- [ ] Delete a marker from the editor; confirm the preview appears before Apply
  and Undo restores the marker.
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

## Speaker dialogue range markers

- [ ] Open a disposable Select timeline with dialogue clips on V1.
- [ ] Run the high-level operation in preview mode with known timed speaker segments; confirm no clip marker is written.
- [ ] Apply Mike=Blue and Sam=Yellow ranges; confirm the markers are clip markers on TimelineItems, not timeline markers or Media Pool source markers.
- [ ] Verify each marker starts at the detected speech start and its duration ends at the detected speech end.
- [ ] Verify a speaker turn crossing a clip boundary becomes one marker on each affected clip with correct relative offsets.
- [ ] Verify same-speaker fragments separated by <=350 ms merge when no other speaker occupies the gap.
- [ ] Verify exact simultaneous starts become one explicit Fuchsia overlap marker rather than shifted fake timing.
- [ ] Add a manual marker on a target clip frame and confirm a speaker-marker collision is reported before any generated marker mutation.
- [ ] Re-run the same analysis and confirm no duplicate speaker markers are created.
- [ ] Change the analysis ranges and re-run; confirm only previously generated speaker markers are replaced while manual markers remain untouched.
- [ ] Force an AddMarker/readback failure and confirm the previous generated speaker-marker state is restored.
- [ ] Verify the operation refuses a non-Select timeline by default.
- [ ] With no analyzer and no supplied segments, verify the service reports that speaker-segment analysis is unavailable instead of claiming Resolve exposed it.

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
