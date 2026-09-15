# Resolve Hub v0.3.23 — follow-up repairs

Based on main `0cffc390105f1048e57307d702e7206bb02db7af`, retaining the marker/metadata safety fixes from `ca6f233124a0992af694969722ba63883a766938`.

## Marker browser and reported row movement

Click handlers no longer clear an icon, paint it blank, load it again, and resize all table columns. Thumbnail swaps perform one icon assignment; sizing runs only when window geometry changes. Normal, hover, selection and focus styles keep identical padding, borders and font weight. The marker tree uses fixed row hints, uniform row heights and Hub-owned logical selection instead of cycling native selection on every click. Narrow widths no longer force a 620-pixel table. Timecode/status fields and selection-bar styles have stable geometry.

The first marker column now reserves a 96 x 54 preview slot before images load. Missing visible previews and the selected preview are queued cooperatively on the existing UI loop, one job at a time, with an idle delay after clicks, nudges and slider movements. No background thread calls Resolve or UIManager. Failed captures require an explicit retry rather than looping. Cache keys depend on timeline/frame, not marker name/color. A move clears its stale image and queues the correct one. This is code-level mitigation of the reported wiggle; native macOS/Resolve visual acceptance remains required.

## Marker editing

Filter membership and sort order are recomputed after edits. Rows update in place when order/membership did not change. List rebuilds preserve a visible anchor where UIManager supports viewport rectangles. The shortened notes cell is read-only: double-click it to focus the full notes editor in the same workspace. Clear Selection no longer leaves a stale current item available for editing. Numeric modifier masks preserve Ctrl/Cmd/Shift multi-selection. Periodic marker sync does not discard an in-progress draft in the same timeline.

## Other workspaces

Rename Apply revalidates original names, metadata used by templates, output validity and collisions across the selection before writing. It uses read-back verification and retry-safe partial Undo. Non-extension periods are preserved by the Original token.

Still jobs recheck conflicts at execution, reject escaping filenames and case-insensitive duplicate outputs, skip captured jobs on retry, and export each frame into an isolated staging directory. Final files are created exclusively, never overwritten. Gallery fallback can only discover images from its own job directory. Successful exports returning None are accepted after file verification, including delayed file creation. Capture/import counts no longer count the same asset twice. Playhead restoration is verified and failures are reported.

Health distinguishes unknown usage from a known-empty timeline. Inline metadata editing validates its selection snapshot before writing. Cache cleanup only deletes Hub cache-key filenames, preserving unrelated PNGs in user-selected folders. Tracked Python bytecode is removed and ignored.

## Automated validation

Run `python3 -m unittest discover -s tests -v`. New coverage is in `tests/test_followup_repairs.py`; earlier audit regressions remain in `tests/test_audit_regressions.py`. CI artifacts retain exact test output. No assertion is removed or skipped to make the suite pass.

## Native Resolve acceptance — still required

Use a disposable project. Open installed v0.3.23 and test repeated clicks, Ctrl/Cmd/Shift selection, scrolling during thumbnail loading, narrow/wide resizing, inline name/time edits, color changes under a filter, marker moves crossing sort positions, notes longer than 80 characters with line breaks, rapid start/end nudges, Clear Selection, batch moves and Undo, source timeline changes, still filename collisions, CSV metadata Undo, and ordinary Grab Still import/bin restoration. Verify image content, not just its timecode: API playhead read-back alone cannot prove the native viewer has finished rendering.

This change does not claim that all P0 functionality or every Resolve build is fully validated. The existing disabled Play Range control remains disabled; unsupported API features are not simulated. No source camera files are renamed/deleted, no main-branch merge is performed, and no local Resolve installation is changed by this repository update.
