"""Human-readable numbers, shared by the interfaces.

A duration, a file size and a position in a recording are formatted the same
way whether they end up in a terminal table or in a Qt label, so the helpers
live here rather than once per front end. Nothing in this module is
translated: these are numbers with units, not sentences.
"""

#: Suffixes for :func:`format_bytes`, smallest first.
_UNITS = ("B", "KiB", "MiB", "GiB", "TiB")


def format_duration(seconds):
    """Compact, readable duration: 45s, 3m 20s, 1h 40m."""
    if not seconds or seconds < 0:
        return "-"
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_clock(seconds):
    """A position in a recording, as a player shows it: ``m:ss`` or ``h:mm:ss``.

    Unlike :func:`format_duration` this never collapses to an approximation,
    because it labels a point someone is about to jump to — and it truncates
    rather than rounds, so the label of a sentence starting at 61.5s reads
    1:01 and jumping there lands just before the sentence, never after it."""
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_bytes(size):
    """A file size in the largest unit that keeps it readable."""
    size = float(size or 0)
    for unit in _UNITS:
        if size < 1024 or unit == _UNITS[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {_UNITS[-1]}"       # pragma: no cover - unreachable
