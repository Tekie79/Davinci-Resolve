"""Frame-accurate SMPTE timecode utilities."""

from decimal import Decimal, InvalidOperation


class TimecodeError(ValueError):
    pass


def parse_fps(value):
    try:
        fps = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise TimecodeError("Invalid frame rate: %s" % value)
    if fps <= 0:
        raise TimecodeError("Frame rate must be positive.")
    return fps


def nominal_fps(value):
    fps = parse_fps(value)
    return int(fps.to_integral_value(rounding="ROUND_HALF_UP"))


def is_drop_frame_rate(value):
    fps = parse_fps(value)
    return abs(fps - Decimal("29.97")) < Decimal("0.01") or abs(fps - Decimal("59.94")) < Decimal("0.01")


def timecode_to_frames(timecode, fps, start_timecode=None, clamp_negative=False):
    """Convert SMPTE timecode to its frame number, including drop-frame notation."""
    text = str(timecode or "").strip()
    drop = ";" in text
    parts = text.replace(";", ":").split(":")
    if len(parts) != 4:
        raise TimecodeError("Use HH:MM:SS:FF timecode.")
    try:
        hours, minutes, seconds, frames = [int(part) for part in parts]
    except ValueError:
        raise TimecodeError("Timecode contains a non-numeric field.")
    rate = nominal_fps(fps)
    if min(hours, minutes, seconds, frames) < 0 or minutes > 59 or seconds > 59 or frames >= rate:
        raise TimecodeError("Timecode is outside the valid range for %s fps." % fps)
    total = ((hours * 3600 + minutes * 60 + seconds) * rate) + frames
    if drop:
        if not is_drop_frame_rate(fps):
            raise TimecodeError("Drop-frame timecode requires 29.97 or 59.94 fps.")
        dropped = 2 if rate == 30 else 4
        if seconds == 0 and minutes % 10 != 0 and frames < dropped:
            raise TimecodeError("This frame number is skipped by drop-frame timecode.")
        total -= dropped * ((hours * 60 + minutes) - ((hours * 60 + minutes) // 10))
    if start_timecode is not None:
        total -= timecode_to_frames(start_timecode, fps)
    if clamp_negative:
        total = max(0, total)
    return total


def frames_to_timecode(frame, fps, start_timecode=None, drop_frame=None):
    """Convert a frame count to SMPTE timecode, respecting an optional start TC."""
    rate = nominal_fps(fps)
    total = int(round(frame))
    if start_timecode is not None:
        total += timecode_to_frames(start_timecode, fps)
    if total < 0:
        raise TimecodeError("Frame number cannot produce a negative timecode.")
    if drop_frame is None:
        drop_frame = bool(start_timecode and ";" in str(start_timecode))
    if drop_frame:
        if not is_drop_frame_rate(fps):
            raise TimecodeError("Drop-frame timecode requires 29.97 or 59.94 fps.")
        dropped = 2 if rate == 30 else 4
        frames_per_10_minutes = rate * 600 - dropped * 9
        frames_per_minute = rate * 60 - dropped
        ten_minute_chunks, remainder = divmod(total, frames_per_10_minutes)
        added = dropped * 9 * ten_minute_chunks
        if remainder >= dropped:
            added += dropped * ((remainder - dropped) // frames_per_minute)
        total += added
    hours, remainder = divmod(total, rate * 3600)
    minutes, remainder = divmod(remainder, rate * 60)
    seconds, frame_number = divmod(remainder, rate)
    separator = ";" if drop_frame else ":"
    return "%02d:%02d:%02d%s%02d" % (hours % 24, minutes, seconds, separator, frame_number)


def duration_frames_to_display(duration, fps):
    return frames_to_timecode(max(0, int(duration)), fps, drop_frame=False)


def duration_display_to_frames(value, fps):
    """Accept either a frame count or HH:MM:SS:FF duration."""
    text = str(value or "").strip()
    duration = timecode_to_frames(text, fps) if ":" in text or ";" in text else int(text)
    if duration < 1:
        raise TimecodeError("Marker duration must be at least one frame.")
    return duration


def nudge_frame(frame, amount, minimum=None, maximum=None):
    return clamp_frame(int(frame) + int(amount), minimum, maximum)


def clamp_frame(frame, minimum=None, maximum=None):
    result = int(frame)
    if minimum is not None:
        result = max(int(minimum), result)
    if maximum is not None:
        result = min(int(maximum), result)
    return result


def timeline_start_frame(timeline):
    return int(timeline.GetStartFrame())


def timeline_end_frame(timeline):
    return int(timeline.GetEndFrame())


def timeline_frame_to_timecode(timeline, frame, fps):
    start_frame = timeline_start_frame(timeline)
    start_tc = timeline.GetStartTimecode() if callable(getattr(timeline, "GetStartTimecode", None)) else "00:00:00:00"
    return frames_to_timecode(int(frame) - start_frame, fps, start_timecode=start_tc)


def timeline_timecode_to_frame(timeline, timecode, fps):
    start_frame = timeline_start_frame(timeline)
    start_tc = timeline.GetStartTimecode() if callable(getattr(timeline, "GetStartTimecode", None)) else "00:00:00:00"
    return start_frame + timecode_to_frames(timecode, fps, start_timecode=start_tc)
