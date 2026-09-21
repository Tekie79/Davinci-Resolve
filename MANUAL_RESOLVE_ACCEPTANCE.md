# Manual Resolve Acceptance — v0.4.0

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

## AI / OpenAI secure settings

- [ ] Open Settings → AI / OpenAI and confirm the key field is empty on load.
- [ ] Paste a disposable/test Platform API key and choose Save Securely.
- [ ] Confirm the field clears immediately and only a masked credential status remains.
- [ ] Inspect Resolve Hub settings.json and confirm the API key is absent.
- [ ] On macOS, confirm Keychain contains service `Meher Flow Resolve Hub` / account `openai-api-key`.
- [ ] Choose Test Connection and confirm success/failure is reported without exposing the key.
- [ ] Restart Resolve Hub and confirm the stored credential is still detected.
- [ ] Replace the key and confirm the Keychain value updates.
- [ ] Choose Remove Key and confirm Resolve Hub reports Not configured.

## Local Codex MCP

- [ ] Run the installed MCP launcher from `~/Library/Application Support/Meher Flow/Resolve Hub/bin/run-resolve-mcp`.
- [ ] Confirm `codex mcp list` shows `meher-resolve` after registration.
- [ ] Call `resolve_status` and verify project/timeline plus masked credential state.
- [ ] Call `list_select_timelines` and verify only Select timelines are returned.
- [ ] Verify the speaker tool accepts 1-4 character names and refuses more than four.
- [ ] Verify the OpenAI key is not part of the MCP tool schema or tool output.

## Speaker dialogue range markers

- [ ] Open a disposable Select timeline with dialogue clips on V1.
- [ ] Provide 1-4 expected character names and confirm only those available voice references are sent.
- [ ] With ffmpeg installed, confirm the temporary WAV is compressed to mono MP3 before analysis and removed afterward.
- [ ] Without ffmpeg, confirm the workflow falls back to WAV and continues.
- [ ] Confirm MP3 voice references are accepted for known speakers.
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


## Keywords clip naming

- [ ] On a disposable clip, set Keywords to `Name=Mike; ShotType=MCU; Frames=100-200`.
- [ ] Call `rename_clips_from_keywords(source="timeline", mode="preview")` and confirm `Mike_MCU_T01` is proposed.
- [ ] Confirm source file path/name on disk is unchanged.
- [ ] Add a second Mike MCU with later Frames and confirm `T02`.
- [ ] Remove ShotType from one clip and confirm the whole apply is blocked as REVIEW_REQUIRED.
- [ ] Test `timeline_selection`, `current_bin`, and `media_pool_selection`.
- [ ] Change Keywords after preview and confirm stale apply is rejected.
- [ ] Verify a repeated Media Pool clip used multiple times in the timeline is renamed once at the shared clip-label level.

## Codex visual-assisted clip review

- [ ] Populate `Master/01_MEDIA/STILLS/CODEX_REF` with test reference stills.
- [ ] Call `list_reference_stills` and verify local paths/metadata are returned.
- [ ] Call `export_timeline_clip_visuals` on a disposable Select timeline.
- [ ] Confirm representative PNGs match the intended timeline clips.
- [ ] Confirm previous playhead position is restored after export.
- [ ] Inspect returned PNGs with Codex image input and verify shot-size/OTS/2SHOT/INSERT analysis.
- [ ] Do not infer character identity from a face; use Keywords/editor confirmation.
- [ ] Confirm shot-type disagreements are reported for review before rename.
- [ ] Call `cleanup_visual_analysis_frames` and verify only the owned temporary directory is deleted.
