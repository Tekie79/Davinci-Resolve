"""Metadata-driven editorial clip naming from Resolve Keywords.

This service never renames source files on disk. It renames Resolve Media Pool
clip labels only, which is the same label seen by timeline items that reference
those clips.

Recommended Keywords syntax:

    Name=Mike; ShotType=MCU; Frames=103245-103612
    Character=Sam; Shot=CU; FrameStart=2030; FrameEnd=2148
    Subject=Phone; ShotType=INSERT; Frames=550-612

A compact fallback is also accepted:

    Mike, MCU, 103245-103612

Required for automatic naming:
- Name/Character/Subject
- ShotType/Shot/Framing

Frames are optional but, when present, provide deterministic ordering for take
numbers within the same Name + ShotType group.

Generated label:
    Character_ShotType_T##
"""

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Optional, Tuple

from ..models.operation import Change, OperationResult, PreviewSummary
from .rename_service import RenameService


_KEY_VALUE = re.compile(
    r"""(?ix)
    (?:^|[;,|\n])
    \s*
    (?P<key>
        character|characters|name|subject|
        shot\s*type|shottype|shot|framing|size|
        frames?|frame\s*range|range|
        frame\s*start|framestart|start\s*frame|
        frame\s*end|frameend|end\s*frame|
        take
    )
    \s*[:=]\s*
    (?P<value>[^;,|\n]+)
    """
)

_FRAME_RANGE = re.compile(r"(?i)\b(\d+)\s*(?:-|\.\.|:)\s*(\d+)\b")
_INTEGER = re.compile(r"^\s*(?:T)?(\d+)\s*$", re.I)

_SHOT_ALIASES = {
    "EXTREME CLOSE UP": "ECU",
    "EXTREME CLOSEUP": "ECU",
    "ECU": "ECU",
    "CLOSE UP": "CU",
    "CLOSEUP": "CU",
    "CU": "CU",
    "MEDIUM CLOSE UP": "MCU",
    "MEDIUM CLOSEUP": "MCU",
    "MCU": "MCU",
    "MEDIUM SHOT": "MS",
    "MEDIUM": "MS",
    "MS": "MS",
    "MEDIUM LONG SHOT": "MLS",
    "MLS": "MLS",
    "LONG SHOT": "LS",
    "LS": "LS",
    "WIDE SHOT": "WS",
    "WIDE": "WS",
    "WS": "WS",
    "EXTREME WIDE SHOT": "EWS",
    "EXTREME WIDE": "EWS",
    "EWS": "EWS",
    "OVER THE SHOULDER": "OTS",
    "OVER-THE-SHOULDER": "OTS",
    "OTS": "OTS",
    "TWO SHOT": "2SHOT",
    "TWO-SHOT": "2SHOT",
    "2 SHOT": "2SHOT",
    "2SHOT": "2SHOT",
    "THREE SHOT": "3SHOT",
    "THREE-SHOT": "3SHOT",
    "3 SHOT": "3SHOT",
    "3SHOT": "3SHOT",
    "INSERT": "INSERT",
    "POV": "POV",
}


@dataclass(frozen=True)
class ParsedKeywords:
    raw: str
    subject: str = ""
    shot_type: str = ""
    frame_start: Optional[int] = None
    frame_end: Optional[int] = None
    explicit_take: Optional[int] = None

    @property
    def complete(self):
        return bool(self.subject and self.shot_type)


def _clean_subject(value: str) -> str:
    """Return a filesystem-safe editorial subject token without guessing identity."""
    text = str(value or "").strip()
    # Common multi-subject separators become concatenation per naming examples:
    # Mike+Sam -> MikeSam; Mike & Sam -> MikeSam.
    text = re.sub(r"\s*(?:\+|&|/|,)\s*", " ", text)
    # Preserve Unicode word characters; remove punctuation and whitespace.
    pieces = re.findall(r"\w+", text, flags=re.UNICODE)
    return "".join(pieces)


def _normalize_shot_type(value: str) -> str:
    text = re.sub(r"[_\s]+", " ", str(value or "").strip()).upper()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return ""
    return _SHOT_ALIASES.get(text, re.sub(r"[^A-Z0-9]+", "", text))


def _parse_int(value) -> Optional[int]:
    match = _INTEGER.match(str(value or ""))
    return int(match.group(1)) if match else None


def parse_keywords(value) -> ParsedKeywords:
    raw = str(value or "").strip()
    found: Dict[str, str] = {}

    for match in _KEY_VALUE.finditer(raw):
        key = re.sub(r"\s+", "", match.group("key").casefold())
        found[key] = match.group("value").strip()

    subject = (
        found.get("character")
        or found.get("characters")
        or found.get("name")
        or found.get("subject")
        or ""
    )
    shot = (
        found.get("shottype")
        or found.get("shot")
        or found.get("framing")
        or found.get("size")
        or ""
    )

    frame_start = (
        _parse_int(found.get("framestart"))
        or _parse_int(found.get("startframe"))
    )
    frame_end = (
        _parse_int(found.get("frameend"))
        or _parse_int(found.get("endframe"))
    )

    range_value = (
        found.get("frames")
        or found.get("frame")
        or found.get("framerange")
        or found.get("range")
        or ""
    )
    range_match = _FRAME_RANGE.search(range_value)
    if range_match:
        frame_start = int(range_match.group(1))
        frame_end = int(range_match.group(2))

    explicit_take = _parse_int(found.get("take"))

    # Compact fallback: Name, ShotType, 100-200
    if not subject or not shot:
        tokens = [part.strip() for part in re.split(r"[;,|\n]+", raw) if part.strip()]
        bare = []
        for token in tokens:
            if ":" in token or "=" in token:
                continue
            match = _FRAME_RANGE.search(token)
            if match:
                if frame_start is None:
                    frame_start = int(match.group(1))
                    frame_end = int(match.group(2))
                continue
            normalized = _normalize_shot_type(token)
            if token.upper() in _SHOT_ALIASES or normalized in set(_SHOT_ALIASES.values()):
                if not shot:
                    shot = token
                continue
            bare.append(token)
        if not subject and bare:
            subject = bare[0]

    if frame_start is not None and frame_end is not None and frame_end < frame_start:
        frame_start, frame_end = frame_end, frame_start

    return ParsedKeywords(
        raw=raw,
        subject=_clean_subject(subject),
        shot_type=_normalize_shot_type(shot),
        frame_start=frame_start,
        frame_end=frame_end,
        explicit_take=explicit_take,
    )


def _order_key(record, parsed: ParsedKeywords, fallback_index: int, order_hints=None):
    order_hints = order_hints or {}
    if parsed.frame_start is not None:
        return (0, int(parsed.frame_start), fallback_index)
    hint = order_hints.get(record.unique_id)
    if hint is not None:
        return (1, int(hint), fallback_index)
    return (2, fallback_index, fallback_index)


class KeywordClipRenameService:
    """Build/apply metadata-authoritative Yekermo Sew clip labels."""

    def __init__(self, rename_service: Optional[RenameService] = None):
        self.rename_service = rename_service or RenameService()

    def preview(
        self,
        records: Iterable,
        keyword_field: str = "Keywords",
        take_width: int = 2,
        order_hints: Optional[Dict[str, int]] = None,
    ) -> PreviewSummary:
        records = list(records)
        parsed_rows: List[Tuple[int, object, ParsedKeywords]] = []
        for index, record in enumerate(records):
            parsed_rows.append(
                (index, record, parse_keywords(record.metadata.get(keyword_field, "")))
            )

        sorted_rows = sorted(
            parsed_rows,
            key=lambda row: _order_key(row[1], row[2], row[0], order_hints),
        )

        used_takes: Dict[Tuple[str, str], set] = {}
        assigned: Dict[str, Optional[int]] = {}

        # Reserve explicit take numbers first so automatic numbering never collides.
        for _index, record, parsed in sorted_rows:
            if not parsed.complete or parsed.explicit_take is None:
                continue
            group = (parsed.subject.casefold(), parsed.shot_type.casefold())
            used_takes.setdefault(group, set()).add(int(parsed.explicit_take))
            assigned[record.unique_id] = int(parsed.explicit_take)

        for _index, record, parsed in sorted_rows:
            if not parsed.complete:
                assigned.setdefault(record.unique_id, None)
                continue
            if record.unique_id in assigned:
                continue
            group = (parsed.subject.casefold(), parsed.shot_type.casefold())
            occupied = used_takes.setdefault(group, set())
            take = 1
            while take in occupied:
                take += 1
            occupied.add(take)
            assigned[record.unique_id] = take

        changes = []
        for original_index, record, parsed in parsed_rows:
            take = assigned.get(record.unique_id)
            missing = []
            if not parsed.subject:
                missing.append("Name/Character")
            if not parsed.shot_type:
                missing.append("ShotType")

            if missing:
                after = record.name
                status = "REVIEW_REQUIRED"
            else:
                after = "%s_%s_T%s" % (
                    parsed.subject,
                    parsed.shot_type,
                    str(int(take)).zfill(max(1, int(take_width))),
                )
                status = "Unchanged" if after == record.name else "Ready"

            context = {
                "keyword_field": keyword_field,
                "keywords": parsed.raw,
                "subject": parsed.subject,
                "shot_type": parsed.shot_type,
                "frame_start": parsed.frame_start,
                "frame_end": parsed.frame_end,
                "take": take,
                "explicit_take": parsed.explicit_take,
                "missing": missing,
                # RenameService.apply_preview revalidates this exact snapshot.
                "metadata_before": dict(record.metadata),
                "input_order": original_index,
            }

            changes.append(
                Change(
                    record.unique_id,
                    record.name,
                    "name",
                    record.name,
                    after,
                    status,
                    source=record,
                    context=context,
                )
            )

        # Catch duplicate explicit take labels or accidental collisions before apply.
        by_name: Dict[str, List[Change]] = {}
        for change in changes:
            if change.status in ("Ready", "Unchanged"):
                by_name.setdefault(str(change.after).casefold(), []).append(change)
        for group in by_name.values():
            if len(group) > 1:
                for change in group:
                    change.status = "CONFLICT"

        return PreviewSummary(changes)

    def apply_preview(self, preview: PreviewSummary) -> OperationResult:
        blockers = [
            change for change in preview.changes
            if change.status not in ("Ready", "Unchanged")
        ]
        if blockers:
            labels = [
                "%s: %s" % (change.label, change.status)
                for change in blockers[:20]
            ]
            return OperationResult(
                False,
                failed=max(1, len(blockers)),
                errors=[
                    "Rename preview contains unresolved/blocking rows. Nothing was renamed.",
                    *labels,
                ],
            )
        return self.rename_service.apply_preview(preview)
