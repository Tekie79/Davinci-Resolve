# Meher Flow Resolve Hub

**Meher Flow Resolve Hub v0.4.1** is a modular DaVinci Resolve companion built
with Fusion UIManager. It centralizes marker, metadata, clip-name, still,
media-health, and Codex-driven speaker analysis workflows.

The P0 interaction model is:

> See it → navigate it → edit it → preview it → apply it → verify it → undo/rollback when needed

---

## What v0.4.x adds

The speaker-dialogue workflow is designed for **Amharic, English, and mixed
Amharic/English production audio** without depending on Resolve transcription or
caption generation.

The editor triggers Codex. Codex calls the locally installed Resolve Hub through
MCP. Resolve Hub exports the actual Select-timeline audio, OpenAI
**gpt-4o-transcribe-diarize** returns speaker start/end ranges, and Resolve Hub
writes verified duration **clip markers** back to the Select timeline.

~~~text
Editor
  ↓
Codex prompt / MCP tool
  ↓
Installed Meher Flow Resolve Hub
  ↓
Resolve Select timeline audio
  ↓
temporary WAV → mono MP3 when ffmpeg is available
  ↓
OpenAI speaker diarization
  + only the 1–4 expected character reference samples
  ↓
speaker + start + end
  ↓
verified TimelineItem range markers in Resolve
~~~

The OpenAI API key is **not passed through Codex or MCP**. On macOS it is stored
in **macOS Keychain** by Resolve Hub.

---

## Workspaces

- **Markers** — browse/filter/sort markers, navigate, edit frame-accurate ranges,
  apply presets, preview batch changes, verify writes, and Undo.
- **Speaker dialogue markers** — analyze Select-timeline audio and create
  character-specific duration clip markers while preserving manual markers.
- **Metadata** — browse and batch-edit supported clip metadata.
- **Rename** — safely rename Resolve clip names without renaming camera-original
  files.
- **Stills** — capture, name, queue, save, and import stills.
- **Health** — read-only media-health checks and reports.
- **History** — persistent operation history and guarded Undo.
- **Settings** — general preferences plus **AI / OpenAI** credential management.

---

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

Copy both launchers into Resolve's per-user `Fusion/Scripts/Utility` directory.
Install the `meher_resolve_hub` package in the Resolve Hub runtime directory so
Resolve does not recursively expose internal modules as menu scripts. On macOS:

```text
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/
~/Library/Application Support/Meher Flow/Resolve Hub/runtime/meher_resolve_hub/

MCP virtual environment:
~/Library/Application Support/Meher Flow/Resolve Hub/mcp-venv/

MCP launcher:
~/Library/Application Support/Meher Flow/Resolve Hub/bin/run-resolve-mcp

Resolve menu launcher:
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/Meher Flow Resolve Hub.py
~~~

The MCP runtime requires **Python 3.10+**.

## 3. Restart Resolve

Open DaVinci Resolve, then:

~~~text
Workspace
→ Scripts
→ Meher Flow Resolve Hub
~~~

## 4. Save the OpenAI API key securely

Inside Resolve Hub:

~~~text
Settings
→ AI / OpenAI
→ API key
→ paste key
→ Save Securely
~~~

On macOS, Resolve Hub stores the key in:

~~~text
macOS Keychain
Service: Meher Flow Resolve Hub
Account: openai-api-key
~~~

The key is **not** stored in:

~~~text
settings.json
local-config.yaml
.env
the Git repository
Codex prompts
MCP tool arguments
marker customData
~~~

After saving, the input field is cleared and the UI only shows a masked status.

Use **Test Connection** to verify that the stored key can access the configured
OpenAI model.

To replace the key, paste a new one and choose **Save Securely** again.

To remove it:

~~~text
Settings → AI / OpenAI → Remove Key
~~~

## 5. Provide character voice references

For automatic character naming, prepare a clean **2–10 second** reference sample
for each recurring character.

MP3 is recommended for small files. WAV, M4A, FLAC, OGG, and WebM are also
supported by the OpenAI audio endpoint.

The Resolve Hub itself is project-agnostic. The calling Codex project supplies
the reference directory to the MCP tool. For Yekermo Sew that directory is:

~~~text
<Ysew-Post-Prod-Assistant>/voice-references/
~~~

Reference rules:

- one confirmed speaker only;
- little/no background dialogue;
- normal speaking voice;
- 2–10 seconds;
- do not use an uncertain clip;
- do not commit actor voice references to Git.

The speaker request uses only the character names supplied for the current
scene, with a maximum of **four known references per request**.

## 6. Optional: install ffmpeg for smaller timeline uploads

Resolve Hub always creates a safe temporary WAV first.

If ffmpeg is available, it converts the analysis copy to a **mono MP3**
(default 64 kbps) before the OpenAI upload.

Check:

~~~bash
ffmpeg -version
~~~

If it is unavailable, the workflow automatically uses WAV instead. MP3 is an
optimization, not a requirement.

## 7. Register the installed Resolve Hub MCP server with Codex

The MCP server must point at the **installed runtime launcher**, not the Git
repository.

Example:

~~~bash
codex mcp add meher-resolve -- \
  "$HOME/Library/Application Support/Meher Flow/Resolve Hub/bin/run-resolve-mcp"
~~~

Verify:

~~~bash
codex mcp list
~~~

Inside Codex you can also use:

~~~text
/mcp
~~~

You should see the local **meher-resolve** server.

The exposed tools include:

~~~text
resolve_status
list_select_timelines
analyze_select_speakers_and_mark
rename_clips_from_keywords
list_reference_stills
export_timeline_clip_visuals
cleanup_visual_analysis_frames
~~~

The OpenAI API key is **not** included in the MCP configuration because the
installed Resolve Hub retrieves it from macOS Keychain.

For Yekermo Sew, Codex passes the project-specific voice-reference directory
(e.g. `<Ysew-Post-Prod-Assistant>/voice-references`) to the MCP speaker tool on
each request. `YSEW_VOICE_REFERENCE_DIR` remains available only as an optional
fallback/override.

---

# Keywords-driven clip naming

Resolve Hub can rename Resolve Media Pool **clip labels** from the standard
`Keywords` metadata field.

It never renames source files on disk.

Recommended Keywords:

~~~text
Name=Mike; ShotType=MCU; Frames=103245-103612
Character=Sam; Shot=CU; FrameStart=2030; FrameEnd=2148
Subject=Phone; ShotType=INSERT; Frames=550-612
~~~

Compact form:

~~~text
Mike, MCU, 103245-103612
~~~

Generated labels:

~~~text
Mike_MCU_T01
Mike_MCU_T02
Sam_CU_T01
MikeSam_2SHOT_T01
Phone_INSERT_T01
~~~

MCP tool:

~~~text
rename_clips_from_keywords
~~~

Supported sources:

~~~text
timeline
timeline_selection
current_bin
media_pool_selection
~~~

Run with `mode=preview` first. Missing Name/Character/Subject or ShotType,
duplicate labels, stale metadata, or invalid names block the entire apply.

For timeline sources, the tool renames the shared Media Pool clip label, so all
timeline instances referencing that media item show the updated label.

## Codex visual-assisted clip review

Resolve Hub also exposes project-agnostic helpers for Codex vision:

~~~text
list_reference_stills
export_timeline_clip_visuals
cleanup_visual_analysis_frames
~~~

`list_reference_stills` returns filenames, local paths, and metadata from a
Media Pool bin such as:

~~~text
Master/01_MEDIA/STILLS/CODEX_REF
~~~

`export_timeline_clip_visuals` exports representative PNGs from the current
Select timeline and returns local filesystem paths. Codex can attach/view those
local images and analyze shot framing, composition, OTS/2SHOT/group coverage,
inserts, wardrobe, props, location/background, and continuity.

Character identity must come from explicit project metadata/editor confirmation.
The visual helper is not a face-identification system and must not assign a real
person's identity from facial appearance.

The visual pass is advisory. The actual rename remains metadata-driven through
`rename_clips_from_keywords`.

---

# Daily speaker-marker workflow

## 1. Open the episode project in Resolve

Example:

~~~text
Ysew_Season01_EP01
~~~

## 2. Make sure the Select timeline exists

Example:

~~~text
YSEW_EP01_SC04_RESTAURANT_SELECT
~~~

The tool can resolve the current/appropriate Select timeline from episode and
scene, or Codex can pass an exact timeline name.

## 3. Tell Codex which characters speak in the scene

Example:

~~~text
Mike, Sam
~~~

Only those character references are considered for the request.

This avoids sending unrelated cast references and improves identity
disambiguation.

## 4. Run Preview first

From the Yekermo Sew Codex project:

~~~text
/prompts:ys-speaker-markers EP=1 SCENE=04 CHARACTERS=Mike,Sam MODE=preview
~~~

Preview performs the audio export and analysis but does not write markers.

Review:

- target timeline;
- characters requested;
- references found;
- named/unknown speakers;
- detected ranges;
- proposed marker colors;
- overlaps;
- manual-marker collisions;
- warnings.

## 5. Apply

When the preview looks correct:

~~~text
/prompts:ys-speaker-markers EP=1 SCENE=04 CHARACTERS=Mike,Sam MODE=apply
~~~

Codex calls the installed MCP tool. Resolve Hub then:

1. exports the current Select mix;
2. compresses the temporary analysis file to MP3 when available;
3. sends the timeline audio plus only the requested available voice references
   to OpenAI;
4. receives diarized speaker ranges;
5. converts seconds to actual Resolve timeline frames;
6. maps ranges to the correct TimelineItems;
7. splits a range if it crosses a clip boundary;
8. writes duration clip markers;
9. reads the markers back and verifies them;
10. removes the temporary analysis audio;
11. restores the previous generated speaker markers if a batch write fails.

No Resolve transcription/caption workflow is involved.

---

# Marker behavior

Example:

~~~text
Mike speaks        Sam speaks       Mike speaks again
████████████       █████████        █████████████
Blue range         Yellow range     Blue range
~~~

Generated names:

~~~text
DIALOGUE — Mike
DIALOGUE — Sam
DIALOGUE — UNKNOWN_A
OVERLAP — Mike + Sam
~~~

Speaker marker colors are independent from Yekermo Sew Select **clip colors**.

~~~text
Select clip:
Green   = primary
Orange  = alternate

Speaker marker:
Blue    = Mike
Yellow  = Sam / Spidey
Cream   = unresolved speaker
Fuchsia = exact-start overlap
~~~

Resolve Hub uses only marker color names supported by Resolve.

Generated markers contain customData so rerunning the analysis replaces only
previously generated speaker markers.

Manual markers are preserved.

---

# Amharic / English behavior

This workflow is intentionally **not dependent on transcript accuracy**.

For Yekermo Sew:

~~~text
Primary signals:
speaker voice identity
speaker start time
speaker end time

Secondary/optional:
transcribed words
~~~

Transcript text is disabled by default for marker notes.

The audio may contain:

- Amharic;
- English;
- code-switching between Amharic and English.

Unknown identity is preserved as **UNKNOWN_*** instead of being guessed from
imperfect text.

---

# OpenAI audio behavior

The production model is:

~~~text
gpt-4o-transcribe-diarize
~~~

The request uses:

~~~text
response_format = diarized_json
chunking_strategy = auto
~~~

Known character references are supplied using:

~~~text
known_speaker_names
known_speaker_references
~~~

OpenAI supports up to four known speaker references per request, each 2–10
seconds long.

Supported uploaded audio formats include MP3 and WAV.

For oversized WAV analysis files, Resolve Hub can split them into overlapping
chunks and restore the returned timestamps to the original timeline.

---

# Security model

~~~text
Editor enters API key once
        ↓
macOS Keychain
        ↓
installed Resolve Hub / MCP runtime
        ↓
OpenAI API
~~~

Codex receives only tool results. It does not need the API key as prompt text.

Do not put the key in:

- AGENTS.md;
- prompt shortcuts;
- shell-history commands;
- Git;
- voice-reference YAML;
- Resolve marker notes.

---

# Updating the installed runtime

After pulling a newer Davinci-Resolve commit:

~~~bash
git pull
bash scripts/install-resolve-hub-runtime.sh
~~~

The repository remains the source for development; the installer refreshes the
production runtime used by Resolve and Codex.

---

# Troubleshooting

## Codex cannot see the Resolve MCP server

Run:

~~~bash
codex mcp list
~~~

Then verify the launcher exists:

~~~bash
ls -l "$HOME/Library/Application Support/Meher Flow/Resolve Hub/bin/run-resolve-mcp"
~~~

## MCP says Resolve is unreachable

Start Resolve and open a project before running the Codex command.

Also verify the standard Resolve scripting module path exists:

~~~text
/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules
~~~

## OpenAI key shows Not configured

Open:

~~~text
Resolve Hub → Settings → AI / OpenAI
~~~

Paste the key and choose **Save Securely**.

## Test Connection fails

Check:

- the key is active;
- the Platform project/key has appropriate API access;
- the Mac has network access;
- the configured model is available to the Platform project.

## Character is returned as UNKNOWN

Check that:

1. the character was included in CHARACTERS=;
2. the reference file exists in YSEW_VOICE_REFERENCE_DIR;
3. the filename matches the character, such as Mike.mp3;
4. the reference contains one clear speaker;
5. the reference is 2–10 seconds.

Do not force an UNKNOWN segment to a character solely from script dialogue.

## MP3 is not created

Install/enable ffmpeg, or allow the workflow to use WAV. WAV remains fully
supported.

---

## User data

macOS user data:

~~~text
~/Library/Application Support/Meher Flow/Resolve Hub/
~~~

Preferences/history do not contain the OpenAI API key.

The Keychain item is managed separately by macOS.

---

## Development and tests

Pure logic / mocked Resolve tests:

~~~bash
python3 -m unittest discover -s tests -v
~~~

Live Resolve checks:

- [MANUAL_RESOLVE_ACCEPTANCE.md](./MANUAL_RESOLVE_ACCEPTANCE.md)
- [P0_IMPLEMENTATION_NOTES.md](./P0_IMPLEMENTATION_NOTES.md)

Keyword rename tests cover:

- Keywords parsing and aliases;
- frame/timeline take ordering;
- explicit Take reservation;
- REVIEW_REQUIRED blockers;
- non-destructive Media Pool label rename;
- source file path preservation.

Speaker-specific tests cover:

- clip-relative range markers;
- cross-clip speech;
- same-speaker pause merging;
- idempotent reruns;
- manual marker collisions;
- overlap markers;
- OpenAI diarization parsing;
- timeline audio export;
- secure credential resolution.

The repository is the development source. Production use should go through the
installed runtime and registered local MCP server.
