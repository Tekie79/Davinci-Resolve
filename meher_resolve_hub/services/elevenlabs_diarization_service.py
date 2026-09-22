"""ElevenLabs Scribe v2 diarization adapter for Resolve Hub.

This provider is additive to the existing OpenAI diarization provider. It
normalizes ElevenLabs word-level speaker timestamps into the same segment shape
consumed by SpeakerMarkerService.

Official API behavior used here:
- model_id=scribe_v2
- diarize=True
- optional num_speakers
- optional language_code
- optional keyterms
- optional use_speaker_library
"""

from pathlib import Path

from ..credential_service import resolve_elevenlabs_api_key


DEFAULT_MODEL = "scribe_v2"


class ElevenLabsDiarizationError(RuntimeError):
    pass


def _value(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _generic_speaker(value):
    text = str(value or "").strip()
    upper = text.upper()
    return (
        upper.startswith("SPEAKER_")
        or upper.startswith("UNKNOWN")
        or not text
    )


class ElevenLabsDiarizationAnalyzer:
    """Analyze exported Select audio with ElevenLabs Scribe v2."""

    def __init__(
        self,
        audio_path,
        api_key=None,
        credential_store=None,
        model=DEFAULT_MODEL,
        include_transcript=False,
        language_code=None,
        num_speakers=None,
        use_speaker_library=False,
        keyterms=None,
        merge_word_gap_seconds=0.35,
    ):
        self.audio_path = Path(audio_path)
        self.api_key = resolve_elevenlabs_api_key(api_key, credential_store)
        self.model = str(model or DEFAULT_MODEL)
        self.include_transcript = bool(include_transcript)
        self.language_code = (
            str(language_code).strip() if language_code not in (None, "") else None
        )
        self.num_speakers = (
            int(num_speakers) if num_speakers not in (None, "") else None
        )
        self.use_speaker_library = bool(use_speaker_library)
        self.keyterms = [
            str(value).strip()
            for value in (keyterms or [])
            if str(value).strip()
        ]
        self.merge_word_gap_seconds = max(0.0, float(merge_word_gap_seconds))
        self.last_warnings = []
        self.language_detected = ""
        self.language_probability = None

    def _client(self):
        if not self.api_key:
            raise ElevenLabsDiarizationError(
                "No ElevenLabs API key is available. Save one securely in Resolve "
                "Hub Settings → AI / Providers, or set ELEVENLABS_API_KEY as a "
                "compatibility fallback."
            )
        try:
            from elevenlabs.client import ElevenLabs
        except Exception as exc:
            raise ElevenLabsDiarizationError(
                "The ElevenLabs Python package is unavailable in the MCP runtime. "
                "Re-run the Resolve Hub installer."
            ) from exc
        return ElevenLabs(api_key=self.api_key)

    def _request(self, client):
        kwargs = {
            "model_id": self.model,
            "diarize": True,
        }
        if self.language_code:
            kwargs["language_code"] = self.language_code
        if self.num_speakers is not None:
            if not 1 <= int(self.num_speakers) <= 32:
                raise ElevenLabsDiarizationError(
                    "ElevenLabs num_speakers must be between 1 and 32."
                )
            kwargs["num_speakers"] = int(self.num_speakers)
        if self.use_speaker_library:
            kwargs["use_speaker_library"] = True
        if self.keyterms:
            kwargs["keyterms"] = list(self.keyterms)

        with self.audio_path.open("rb") as handle:
            kwargs["file"] = handle
            return client.speech_to_text.convert(**kwargs)

    def _segments_from_words(self, response):
        words = list(_value(response, "words", []) or [])
        segments = []
        current = None

        for raw in words:
            kind = str(_value(raw, "type", "word") or "word").casefold()
            if kind not in ("word", "spacing"):
                continue

            speaker = str(_value(raw, "speaker_id", "") or "").strip()
            if not speaker:
                # Spacing tokens often do not carry useful timing/speaker data.
                if kind == "spacing" and current is not None and self.include_transcript:
                    current["parts"].append(str(_value(raw, "text", "") or ""))
                continue

            start = _value(raw, "start", None)
            end = _value(raw, "end", None)
            if start is None or end is None:
                continue
            try:
                start = float(start)
                end = float(end)
            except (TypeError, ValueError):
                continue
            if end <= start:
                continue

            text = str(_value(raw, "text", "") or "")
            if (
                current is not None
                and current["raw_speaker"] == speaker
                and start <= current["end"] + self.merge_word_gap_seconds
            ):
                current["end"] = max(current["end"], end)
                if self.include_transcript:
                    current["parts"].append(text)
                continue

            if current is not None:
                segments.append(current)
            current = {
                "raw_speaker": speaker,
                "start": start,
                "end": end,
                "parts": [text] if self.include_transcript else [],
            }

        if current is not None:
            segments.append(current)

        result = []
        for row in segments:
            raw_speaker = row["raw_speaker"]
            if _generic_speaker(raw_speaker):
                display = (
                    raw_speaker
                    if raw_speaker.upper().startswith("UNKNOWN")
                    else "UNKNOWN_%s" % raw_speaker
                )
                identity_confidence = None
                evidence_status = "UNKNOWN"
            else:
                # Scribe speaker-library matches may return a registered identifier.
                # Preserve it verbatim; project/editor mapping may canonicalize it.
                display = raw_speaker
                identity_confidence = 1.0 if self.use_speaker_library else None
                evidence_status = (
                    "AUDIO_CONFIRMED" if self.use_speaker_library else "UNKNOWN"
                )

            result.append({
                "speaker": display,
                "start_seconds": row["start"],
                "end_seconds": row["end"],
                "confidence": 1.0,
                "identity_confidence": identity_confidence,
                "transcript": "".join(row["parts"]).strip()
                    if self.include_transcript else "",
                "source": "elevenlabs:%s" % self.model,
                "audio_confirmation": True,
                "visual_confirmation": False,
                "speaker_visibility": "unknown",
                "evidence_status": evidence_status,
                "provider_speaker_id": raw_speaker,
            })
        return result

    def analyze(self, timeline, fps):
        if not self.audio_path.is_file():
            raise ElevenLabsDiarizationError(
                "Speaker-analysis audio file does not exist: %s" % self.audio_path
            )

        self.last_warnings = []
        client = self._client()
        try:
            response = self._request(client)
        except Exception as exc:
            text = str(exc or "ElevenLabs transcription failed.")
            if self.api_key and self.api_key in text:
                text = text.replace(self.api_key, "[REDACTED]")
            raise ElevenLabsDiarizationError(
                "ElevenLabs Scribe transcription failed: %s" % text
            ) from exc

        self.language_detected = str(
            _value(response, "language_code", "") or ""
        )
        probability = _value(response, "language_probability", None)
        try:
            self.language_probability = (
                None if probability is None else float(probability)
            )
        except (TypeError, ValueError):
            self.language_probability = None

        segments = self._segments_from_words(response)
        if not segments:
            self.last_warnings.append(
                "ElevenLabs returned no diarized word ranges."
            )
        return segments
