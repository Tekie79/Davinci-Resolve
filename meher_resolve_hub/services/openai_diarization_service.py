"""OpenAI audio-transcription adapter used by Codex/Resolve Hub.

Supported OpenAI models:

- gpt-4o-transcribe-diarize
  Native speaker diarization with optional known-speaker references.

- whisper-1
  Multilingual transcription with timestamped segments. Whisper does not expose
  the same native speaker diarization / known-speaker interface, so its segments
  are intentionally returned as UNKNOWN_* speaker ranges. Those ranges are still
  useful for transcript review and the visual/hybrid marker workflow.

Transcript text remains secondary for Yekermo Sew speaker markers.
"""

from base64 import b64encode
from pathlib import Path
import tempfile
import wave

from ..credential_service import resolve_openai_api_key


MAX_UPLOAD_BYTES = 24 * 1024 * 1024
DEFAULT_MODEL = "gpt-4o-transcribe-diarize"
SUPPORTED_MODELS = (
    "gpt-4o-transcribe-diarize",
    "whisper-1",
)


class OpenAIDiarizationError(RuntimeError):
    pass


def _data_url(path):
    path = Path(path)
    mime = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".flac": "audio/flac",
    }.get(path.suffix.lower(), "application/octet-stream")
    encoded = b64encode(path.read_bytes()).decode("ascii")
    return "data:%s;base64,%s" % (mime, encoded)


def _value(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class OpenAIDiarizationAnalyzer:
    """Analyze exported Select-timeline audio with a supported OpenAI model."""

    def __init__(
        self,
        audio_path,
        api_key=None,
        known_speaker_references=None,
        model=DEFAULT_MODEL,
        include_transcript=False,
        max_upload_bytes=MAX_UPLOAD_BYTES,
        chunk_overlap_seconds=0.75,
    ):
        self.audio_path = Path(audio_path)
        self.api_key = resolve_openai_api_key(api_key)
        self.known_speaker_references = dict(known_speaker_references or {})
        self.model = str(model or DEFAULT_MODEL)
        self.include_transcript = bool(include_transcript)
        self.max_upload_bytes = int(max_upload_bytes)
        self.chunk_overlap_seconds = max(0.0, float(chunk_overlap_seconds))
        self.last_warnings = []
        self.language_detected = ""

        if self.model not in SUPPORTED_MODELS:
            raise OpenAIDiarizationError(
                "Unsupported OpenAI audio model %r. Supported models: %s."
                % (self.model, ", ".join(SUPPORTED_MODELS))
            )

    @property
    def supports_native_diarization(self):
        return self.model == "gpt-4o-transcribe-diarize"

    def _client(self):
        if not self.api_key:
            raise OpenAIDiarizationError(
                "No OpenAI API key is available. Save one securely in Resolve Hub "
                "Settings → AI / Providers, or set OPENAI_API_KEY as a compatibility "
                "fallback."
            )
        try:
            from openai import OpenAI
        except Exception as exc:
            raise OpenAIDiarizationError(
                "The OpenAI Python package is unavailable in the analysis environment. "
                "Re-run the Resolve Hub installer."
            ) from exc
        return OpenAI(api_key=self.api_key)

    def _known_speaker_payload(self):
        if not self.supports_native_diarization:
            if self.known_speaker_references:
                self.last_warnings.append(
                    "%s does not use the gpt-4o-transcribe-diarize known-speaker "
                    "reference interface; configured voice references were ignored."
                    % self.model
                )
            return [], []

        if not self.known_speaker_references:
            return [], []

        pairs = []
        for name, path in self.known_speaker_references.items():
            candidate = Path(path)
            if not candidate.is_file():
                self.last_warnings.append(
                    "Known-speaker reference for %s was not found: %s"
                    % (name, candidate)
                )
                continue
            pairs.append((str(name), candidate))

        if len(pairs) > 4:
            self.last_warnings.append(
                "OpenAI diarization accepts up to four known-speaker references per "
                "request; only the first four configured references were used."
            )
            pairs = pairs[:4]

        names = [name for name, _ in pairs]
        references = [_data_url(path) for _, path in pairs]
        return names, references

    def _wav_chunks(self):
        """Return (path, global_offset_seconds, owned_start, owned_end, cleanup)."""
        source = self.audio_path
        if source.stat().st_size <= self.max_upload_bytes:
            return [(source, 0.0, 0.0, float("inf"), False)]

        if source.suffix.lower() != ".wav":
            raise OpenAIDiarizationError(
                "Audio exceeds the transcription upload limit. Use the WAV fallback "
                "so Resolve Hub can split it safely, or provide a compressed file "
                "under the direct-upload limit."
            )

        temp_root = Path(tempfile.mkdtemp(prefix="meher-speaker-chunks-"))
        result = []

        try:
            with wave.open(str(source), "rb") as reader:
                channels = reader.getnchannels()
                sample_width = reader.getsampwidth()
                sample_rate = reader.getframerate()
                total_frames = reader.getnframes()
                bytes_per_frame = channels * sample_width
                if bytes_per_frame <= 0 or sample_rate <= 0:
                    raise OpenAIDiarizationError("Invalid WAV metadata.")

                target_bytes = min(self.max_upload_bytes, 20 * 1024 * 1024)
                max_frames = max(sample_rate, int(target_bytes / bytes_per_frame))
                overlap_frames = min(
                    max_frames // 4,
                    int(round(self.chunk_overlap_seconds * sample_rate)),
                )
                step = max(1, max_frames - overlap_frames)

                starts = list(range(0, total_frames, step))
                for index, start in enumerate(starts):
                    frame_count = min(max_frames, total_frames - start)
                    reader.setpos(start)
                    data = reader.readframes(frame_count)
                    chunk = temp_root / ("chunk-%04d.wav" % index)
                    with wave.open(str(chunk), "wb") as writer:
                        writer.setnchannels(channels)
                        writer.setsampwidth(sample_width)
                        writer.setframerate(sample_rate)
                        writer.writeframes(data)

                    chunk_start = start / float(sample_rate)
                    chunk_end = (start + frame_count) / float(sample_rate)
                    half_overlap = overlap_frames / float(sample_rate) / 2.0
                    owned_start = (
                        chunk_start if index == 0 else chunk_start + half_overlap
                    )
                    is_last = start + frame_count >= total_frames
                    owned_end = (
                        chunk_end if is_last else chunk_end - half_overlap
                    )
                    result.append(
                        (chunk, chunk_start, owned_start, owned_end, True)
                    )
        except Exception:
            for file in temp_root.glob("*"):
                try:
                    file.unlink()
                except Exception:
                    pass
            try:
                temp_root.rmdir()
            except Exception:
                pass
            raise

        return result

    def _transcribe_chunk(self, client, path, known_names, known_refs):
        with open(path, "rb") as audio_file:
            if self.supports_native_diarization:
                kwargs = {
                    "model": self.model,
                    "file": audio_file,
                    "response_format": "diarized_json",
                    "chunking_strategy": "auto",
                }
                if known_names:
                    kwargs["extra_body"] = {
                        "known_speaker_names": known_names,
                        "known_speaker_references": known_refs,
                    }
                return client.audio.transcriptions.create(**kwargs)

            # whisper-1 supports verbose_json timestamps but not native speaker
            # diarization/known-speaker references.
            return client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

    def _append_diarized_segments(
        self,
        response,
        offset,
        owned_start,
        owned_end,
        known_set,
        segments,
    ):
        for raw in list(_value(response, "segments", []) or []):
            speaker = str(_value(raw, "speaker", "") or "").strip()
            start = float(_value(raw, "start", 0.0) or 0.0) + offset
            end = float(_value(raw, "end", 0.0) or 0.0) + offset
            if not speaker or end <= start:
                continue

            midpoint = (start + end) / 2.0
            if midpoint < owned_start or midpoint >= owned_end:
                continue

            if speaker not in known_set and not speaker.upper().startswith(
                ("UNKNOWN_", "SPEAKER_")
            ):
                display_speaker = "UNKNOWN_%s" % speaker
                identity_confidence = None
            else:
                display_speaker = speaker
                identity_confidence = 1.0 if speaker in known_set else None

            text = str(_value(raw, "text", "") or "").strip()
            segments.append({
                "speaker": display_speaker,
                "start_seconds": start,
                "end_seconds": end,
                "confidence": 1.0,
                "identity_confidence": identity_confidence,
                "transcript": text if self.include_transcript else "",
                "source": "openai:%s" % self.model,
                "audio_confirmation": True,
                "visual_confirmation": False,
                "speaker_visibility": "unknown",
                "evidence_status": (
                    "AUDIO_CONFIRMED"
                    if identity_confidence is not None
                    else "UNKNOWN"
                ),
            })

    def _append_whisper_segments(
        self,
        response,
        offset,
        owned_start,
        owned_end,
        segments,
        counter,
    ):
        self.language_detected = str(
            _value(response, "language", self.language_detected) or
            self.language_detected
        )
        for raw in list(_value(response, "segments", []) or []):
            start = float(_value(raw, "start", 0.0) or 0.0) + offset
            end = float(_value(raw, "end", 0.0) or 0.0) + offset
            if end <= start:
                continue
            midpoint = (start + end) / 2.0
            if midpoint < owned_start or midpoint >= owned_end:
                continue

            counter += 1
            text = str(_value(raw, "text", "") or "").strip()
            segments.append({
                # Unique unknown IDs deliberately prevent adjacent Whisper
                # transcript segments from being merged into one fake speaker turn.
                "speaker": "UNKNOWN_WHISPER_%03d" % counter,
                "start_seconds": start,
                "end_seconds": end,
                "confidence": 1.0,
                "identity_confidence": None,
                "transcript": text if self.include_transcript else "",
                "source": "openai:whisper-1",
                "audio_confirmation": True,
                "visual_confirmation": False,
                "speaker_visibility": "unknown",
                "evidence_status": "UNKNOWN",
            })
        return counter

    def analyze(self, timeline, fps):
        if not self.audio_path.is_file():
            raise OpenAIDiarizationError(
                "Speaker-analysis audio file does not exist: %s" % self.audio_path
            )

        self.last_warnings = []
        client = self._client()
        known_names, known_refs = self._known_speaker_payload()
        known_set = set(known_names)
        chunks = self._wav_chunks()
        segments = []
        whisper_counter = 0

        if self.model == "whisper-1":
            self.last_warnings.append(
                "whisper-1 provides transcript/timestamp segments but not native "
                "speaker diarization. Speaker identities remain UNKNOWN unless a "
                "later visual/editor mapping resolves them."
            )

        try:
            for path, offset, owned_start, owned_end, cleanup in chunks:
                response = self._transcribe_chunk(
                    client, path, known_names, known_refs
                )
                if self.supports_native_diarization:
                    self._append_diarized_segments(
                        response,
                        offset,
                        owned_start,
                        owned_end,
                        known_set,
                        segments,
                    )
                else:
                    whisper_counter = self._append_whisper_segments(
                        response,
                        offset,
                        owned_start,
                        owned_end,
                        segments,
                        whisper_counter,
                    )
        finally:
            temp_dirs = set()
            for path, _, _, _, cleanup in chunks:
                if cleanup:
                    temp_dirs.add(path.parent)
                    try:
                        path.unlink()
                    except Exception:
                        pass
            for folder in temp_dirs:
                try:
                    folder.rmdir()
                except Exception:
                    pass

        segments.sort(
            key=lambda value: (
                value["start_seconds"],
                value["end_seconds"],
            )
        )
        return segments
