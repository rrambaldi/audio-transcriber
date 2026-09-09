"""Subtitles: cutting a transcript into cues that can be read in time.

Whisper hands back segments of twenty or thirty seconds and hundreds of
characters. As subtitles they are useless — nobody reads three lines that
appear for half a minute — so they are cut again here, against the numbers the
subtitling trade actually uses: characters per line, lines per cue, characters
per second, a minimum and maximum duration, and a minimum gap so two cues do
not appear to flicker into one another.

Those numbers come in named sets — ``netflix``, ``bbc``, ``ebu_broadcast``,
``fcc_verbatim``, ``social_vertical``, ``social_karaoke``,
``kids_accessible`` — shipped as ``data/srt-presets.json`` and overridable by
name from ``<config>/srt-presets.json``, the same two-places arrangement the
keyword sets use.

What this module does *not* do is rewrite anybody's words. Two of the rules in
the trade's guidance — condensing text that is too fast to read, and
simplifying it for a young audience — are editorial acts, not typography: they
change what was said. When the numbers cannot be met, the cue is emitted as it
is and :func:`validate` says so, which is a warning a human can act on rather
than a sentence a program invented. That is also why ``cps_overshoot_tolerance``
is carried but never acted on: it is what the guidance allows *before*
condensing, and condensing is the step this program declines.

The other deliberate omissions, for the same reason (this program cannot know
the thing the rule needs): scene cuts, which need the video; ``[music]`` and
other sound labels, which need sound-event detection; spelling numbers under
ten as words, which is a language-by-language editorial rule; and the
adjective/noun line break, which needs a part-of-speech tagger. Everything
else in the guidance is here.
"""
import json
import math
import os
import re

from .paths import config_dir

#: Where the bundled presets live.
BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "data", "srt-presets.json")

#: Preset used when nothing says otherwise: the de facto reference for
#: professional multi-language subtitles.
DEFAULT_PRESET = "netflix"

#: Knobs an interface may set on top of a preset. Characters per line and
#: lines are what the trade measures in; words per cue is not one of its
#: numbers, but it is the one people reach for first ("a new subtitle every so
#: many words"), so it is honoured when given.
OVERRIDABLE = ("max_chars_per_line", "max_lines", "max_words_per_cue",
               "max_chars_per_second", "min_duration_ms", "max_duration_ms")

#: Sentence ends, kept with the word they follow.
SENTENCE_END = re.compile(r"[.!?;:]+[\"'”»)\]]*$")

#: A weaker break: a comma, a dash, a closing bracket.
CLAUSE_END = re.compile(r"[,—–)\]]+[\"'”»]*$")

#: Words that must not be left at the end of a line, because what follows
#: belongs to them: articles and articulated prepositions, bare prepositions,
#: auxiliaries and negations. Breaking after one of these reads as a stumble.
NO_BREAK_AFTER = {
    "it": {
        # articles, and the prepositions that swallowed one
        "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "l'", "un'",
        "del", "dello", "della", "dell'", "dei", "degli", "delle",
        "al", "allo", "alla", "all'", "ai", "agli", "alle",
        "dal", "dallo", "dalla", "dall'", "dai", "dagli", "dalle",
        "nel", "nello", "nella", "nell'", "nei", "negli", "nelle",
        "sul", "sullo", "sulla", "sull'", "sui", "sugli", "sulle",
        "col", "coi", "quel", "quello", "quella", "quei", "quegli", "quelle",
        # bare prepositions
        "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
        # auxiliaries, before a participle
        "ho", "hai", "ha", "abbiamo", "avete", "hanno", "avevo", "aveva",
        "avevamo", "avevano", "avrei", "avrebbe", "avremmo", "avranno",
        "sono", "sei", "e'", "è", "siamo", "siete", "ero", "era", "eravamo",
        "erano", "sara'", "sarà", "sarei", "sarebbe", "essere", "stato",
        # negation
        "non", "ne'", "né",
    },
    "en": {
        "a", "an", "the", "of", "to", "in", "on", "at", "by", "for", "with",
        "from", "into", "about", "as", "is", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "will", "would", "can",
        "could", "should", "may", "might", "must", "not", "no", "my", "your",
        "his", "her", "its", "our", "their", "this", "that", "these", "those",
    },
}

#: Words that should not be left at the start of a line: the clitic pronouns
#: that belong to the verb before them.
NO_BREAK_BEFORE = {
    "it": {"mi", "ti", "si", "ci", "vi", "lo", "la", "li", "le", "ne", "gli",
           "glielo", "gliela", "glieli", "gliele", "gliene"},
    "en": set(),
}

#: A break *before* one of these is a good break: the conjunctions and
#: relatives that open a clause.
PREFER_BREAK_BEFORE = {
    "it": {"e", "ed", "ma", "pero'", "però", "perche'", "perché", "che",
           "quando", "mentre", "oppure", "o", "se", "come", "quindi",
           "dunque", "anche", "poi", "invece", "cioe'", "cioè"},
    "en": {"and", "but", "or", "because", "that", "which", "while", "when",
           "so", "then", "however", "although", "if"},
}


class SubtitleError(Exception):
    """A preset that cannot be read or does not exist."""


# --------------------------------------------------------------------------
# presets
# --------------------------------------------------------------------------

def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise SubtitleError(f"{path}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def user_file():
    """Where a hand-written set of presets goes, next to config.toml."""
    return os.path.join(config_dir(), "srt-presets.json")


def presets():
    """Every preset available, by name, with the defaults merged in.

    Two places, the user's winning: a file in the config directory can replace
    ``netflix`` with its own numbers, or add a house style of its own, without
    touching the package."""
    bundled, mine = _read(BUNDLED), _read(user_file())
    defaults = dict(bundled.get("defaults") or {})
    defaults.update(mine.get("defaults") or {})
    found = {}
    for source in (bundled.get("presets") or {}, mine.get("presets") or {}):
        for name, values in source.items():
            if isinstance(values, dict):
                found[name] = {**defaults, **found.get(name, {}), **values}
    return found


def preset(name=None, overrides=None):
    """One preset by name, with any per-run overrides applied.

    ``overrides`` are the knobs an interface offers — characters per line,
    lines, characters per second, the durations — so a preset can be the
    starting point rather than a straitjacket."""
    name = (name or DEFAULT_PRESET).strip()
    available = presets()
    if name not in available:
        known = ", ".join(sorted(available)) or "none"
        raise SubtitleError(f"unknown subtitle preset '{name}' (available: {known})")
    chosen = dict(available[name])
    chosen["name"] = name
    for key, value in (overrides or {}).items():
        if value is not None:
            chosen[key] = value
    return chosen


# --------------------------------------------------------------------------
# words, with a time each
# --------------------------------------------------------------------------

#: What marks a change of speaker in a subtitle. Two speakers are never put
#: in one cue - the cue is split at the change instead - so the hyphen says
#: "somebody else now", which is the convention every subtitle reader knows.
SPEAKER_MARK = "- "


class Word:
    """One word, when it is said, and by whom if that is known."""

    __slots__ = ("text", "start", "end", "speaker")

    def __init__(self, text, start, end, speaker=None):
        self.text = text
        self.start = float(start)
        self.end = max(float(end), float(start))
        self.speaker = speaker

    @property
    def length(self):
        return len(self.text)

    def __repr__(self):
        return f"Word({self.text!r}, {self.start:.2f}, {self.end:.2f})"


def words_of(segments):
    """Every word in ``segments``, with a time each.

    A backend that reports word timings (faster-whisper, asked for them) gives
    them directly, and the cuts then fall exactly where the speaker paused.
    Without them the times are interpolated across the segment by character
    count, which is good to a few tenths of a second — visible in a subtitle,
    which is why the word timings are worth asking for."""
    words = []
    for segment in segments or []:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        start = segment.get("start")
        end = segment.get("end")
        speaker = segment.get("speaker")
        reported = segment.get("words") or []
        if reported:
            for word in reported:
                body = str(word.get("word") or word.get("text") or "").strip()
                if not body:
                    continue
                words.append(Word(body, word.get("start", start) or 0.0,
                                  word.get("end", end) or 0.0,
                                  word.get("speaker", speaker)))
            continue
        if start is None or end is None:
            continue
        pieces = text.split()
        total = sum(len(piece) for piece in pieces) or 1
        span = max(float(end) - float(start), 0.001)
        at = float(start)
        for piece in pieces:
            share = span * len(piece) / total
            words.append(Word(piece, at, at + share, speaker))
            at += share
    return words


# --------------------------------------------------------------------------
# grouping words into cues
# --------------------------------------------------------------------------

def sentences(words):
    """Split a word stream on a change of speaker, then on strong punctuation.

    Sentence first, clause second, is the order the trade's guidance gives —
    but a change of speaker comes before both. Two people in one cue would
    have to share two lines, and splitting there instead means every cue has
    one voice in it."""
    groups, current = [], []
    for word in words:
        if current and word.speaker != current[-1].speaker:
            groups.append(current)
            current = []
        current.append(word)
        if SENTENCE_END.search(word.text):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _chars(words):
    return sum(word.length for word in words) + max(0, len(words) - 1)


def _capacity(spec):
    """The most characters a cue may hold: lines times their width."""
    return int(spec.get("max_chars_per_line", 42)) * int(spec.get("max_lines", 2))


def _break_score(words, index, language):
    """How good a break after ``words[index]`` is; higher is better.

    The order is the guidance's: after punctuation, then before a conjunction,
    then anywhere that is not forbidden."""
    word = words[index].text
    lowered = word.lower().strip("\"'“”«»()[]")
    following = words[index + 1].text.lower() if index + 1 < len(words) else ""
    if lowered in NO_BREAK_AFTER.get(language, set()):
        return -1
    if following.strip("\"'“”") in NO_BREAK_BEFORE.get(language, set()):
        return -1
    # Two capitalised words in a row are very often a name and a surname, and
    # a tagger would be needed to be sure. Refusing the break is the cheap side
    # of the mistake.
    if (index + 1 < len(words) and word[:1].isupper() and following[:1].isupper()
            and not SENTENCE_END.search(word)):
        return -1
    if SENTENCE_END.search(word):
        return 4
    if CLAUSE_END.search(word):
        return 3
    if following in PREFER_BREAK_BEFORE.get(language, set()):
        return 2
    return 1


def _split_point(words, spec, language):
    """Where to cut a group that is too long, nearest its middle.

    Nearest the middle rather than as late as possible: two balanced cues read
    better than a full one followed by a scrap."""
    capacity = _capacity(spec)
    middle = len(words) / 2
    best, best_key = None, None
    for index in range(len(words) - 1):
        score = _break_score(words, index, language)
        if score < 0:
            continue
        if _chars(words[:index + 1]) > capacity:
            break                       # past here the first half will not fit
        key = (-score, abs((index + 1) - middle))
        if best_key is None or key < best_key:
            best, best_key = index, key
    if best is None:
        # Everything is forbidden: take the last word that still fits, because
        # a cue that overflows the screen is worse than an awkward break.
        for index in range(len(words) - 2, -1, -1):
            if _chars(words[:index + 1]) <= capacity:
                return index
        return 0
    return best


def _fits(words, spec):
    """Whether these words can be one cue: they fit the screen and the clock.

    Reading speed is deliberately not a reason to split. Splitting does not
    change it — half the text in half the time is the same characters per
    second — and using it as a trigger drove this down to one word per cue,
    each padded out to the minimum duration, which is nonsense on screen.
    Speech faster than the preset allows is a fact about the speech: the
    guidance's own answer is to condense the text, this program does not
    rewrite what was said, and so :func:`validate` reports it instead."""
    limit_words = spec.get("max_words_per_cue")
    return (_chars(words) <= _capacity(spec)
            and (not limit_words or len(words) <= int(limit_words))
            and (words[-1].end - words[0].start) * 1000 <= float(
                spec.get("max_duration_ms", 7000)))


def group(words, spec, language="it"):
    """Cut a word stream into groups that each fit one cue."""
    if not words:
        return []
    by_words = spec.get("segment_by_words") or {}
    if by_words:
        # The karaoke shape: a couple of words at a time, timed word by word.
        # The width still applies - four short words fit twenty characters,
        # four long ones do not, and a line that overflows is off the screen.
        size = max(1, int(by_words.get("max", 4)))
        capacity = _capacity(spec)
        chunks, current = [], []
        for word in words:
            too_many = len(current) >= size
            too_wide = current and _chars(current + [word]) > capacity
            if too_many or too_wide:
                chunks.append(current)
                current = []
            current.append(word)
        if current:
            chunks.append(current)
        return chunks

    groups = []
    pending = list(sentences(words))
    while pending:
        candidate = pending.pop(0)
        # A single word is taken whatever it measures: there is nothing left to
        # split, and this is also what makes the loop finite - every other
        # branch pushes back strictly shorter pieces.
        if len(candidate) == 1 or _fits(candidate, spec):
            groups.append(candidate)
            continue
        at = _split_point(candidate, spec, language)
        head, tail = candidate[:at + 1], candidate[at + 1:]
        if not head or not tail:
            groups.append(candidate)
            continue
        pending.insert(0, tail)
        pending.insert(0, head)     # looked at again: it may still be too long
    return groups


# --------------------------------------------------------------------------
# laying a cue out
# --------------------------------------------------------------------------

def wrap(words, spec, language="it"):
    """Break one cue's words into lines, balanced and never mid-thought.

    Pyramid where it can: a shorter first line over a longer second reads more
    easily than the other way round, and the guidance asks for it — but only
    after the break itself is in a good place. A break before a conjunction
    beats a balanced break in the middle of a phrase, which is why the two
    lines are not always the same length."""
    limit = int(spec.get("max_chars_per_line", 42))
    lines_allowed = max(1, int(spec.get("max_lines", 2)))
    if lines_allowed == 1 or _chars(words) <= limit:
        return [" ".join(word.text for word in words)]

    best, best_key = None, None
    for index in range(len(words) - 1):
        first, second = words[:index + 1], words[index + 1:]
        if _chars(first) > limit or _chars(second) > limit:
            continue
        score = _break_score(words, index, language)
        if score < 0:
            continue
        head, tail_chars = _chars(first), _chars(second)
        imbalance = abs(head - tail_chars)
        # The guidance asks for two things in this order: a break at a good
        # place, and lines that are not wildly different in length. A lopsided
        # split is therefore demoted rather than forbidden - it is still
        # better than breaking between an article and its noun.
        lopsided = 1 if imbalance > 0.5 * max(head, tail_chars) else 0
        pyramid = 0 if head <= tail_chars else 1
        key = (lopsided, -score, pyramid, imbalance)
        if best_key is None or key < best_key:
            best, best_key = index, key
    if best is None:
        # No legal break fits two lines: fall back to filling greedily, which
        # at least keeps every line inside the width.
        lines, current = [], []
        for word in words:
            if current and _chars(current + [word]) > limit:
                lines.append(" ".join(w.text for w in current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(w.text for w in current))
        return lines[:lines_allowed] if len(lines) > lines_allowed else lines
    return [" ".join(w.text for w in words[:best + 1]),
            " ".join(w.text for w in words[best + 1:])]


class Cue:
    """One subtitle: an index, a span of time, and one or two lines."""

    __slots__ = ("index", "start", "end", "lines")

    def __init__(self, index, start, end, lines):
        self.index = index
        self.start = float(start)
        self.end = float(end)
        self.lines = list(lines)

    @property
    def text(self):
        return "\n".join(self.lines)

    @property
    def duration(self):
        return self.end - self.start

    @property
    def chars(self):
        return max(len(line) for line in self.lines) if self.lines else 0

    @property
    def cps(self):
        return (len(self.text.replace("\n", " ")) / self.duration
                if self.duration > 0 else math.inf)

    def as_dict(self):
        return {"index": self.index, "start": self.start, "end": self.end,
                "lines": list(self.lines)}

    def __repr__(self):
        return f"Cue({self.index}, {self.start:.2f}-{self.end:.2f}, {self.text!r})"


def cues(segments, spec=None, language="it", mark_speakers=False):
    """Turn transcribed segments into subtitle cues.

    ``mark_speakers`` puts a hyphen in front of a cue whose voice is not the
    one before it, which is how dialogue is marked in subtitles. It needs
    segments that say who is speaking, so it is only worth asking for after
    diarization.

    Timing, in the order the guidance sets out: a cue may appear slightly
    before the first word (never later), stays a moment after the last one,
    is never shorter than the minimum nor longer than the maximum, and leaves
    the minimum gap before the next. Where a gap comes out very small it is
    snapped to that minimum instead — a gap of thirty milliseconds is not read
    as two subtitles but as one that flickered."""
    spec = spec or preset()
    groups = group(words_of(segments), spec, language)
    lead_in = float(spec.get("sync_lead_in_ms", 0) or 0) / 1000.0
    tail = spec.get("tail_ms") or {}
    tail_min = float(tail.get("min", 0) or 0) / 1000.0
    tail_max = float(tail.get("max", tail_min * 1000) or 0) / 1000.0
    min_duration = float(spec.get("min_duration_ms", 0) or 0) / 1000.0
    max_duration = float(spec.get("max_duration_ms", 7000) or 7000) / 1000.0
    min_gap = float(spec.get("min_gap_ms", 0) or 0) / 1000.0

    built = []
    for position, words in enumerate(groups):
        # It may appear a little early, never late, and never before the
        # previous cue has had its gap.
        start = max(0.0, words[0].start - lead_in)
        if built:
            start = max(start, built[-1].end + min_gap)
        # However long the tail, it stops short of the next cue's turn.
        ceiling = (groups[position + 1][0].start - min_gap
                   if position + 1 < len(groups) else math.inf)
        end = min(words[-1].end + tail_max, ceiling)
        end = max(end, min(words[-1].end + tail_min, ceiling))
        if end - start < min_duration:
            end = min(start + min_duration, ceiling)
        end = min(end, start + max_duration)
        if end <= start:
            # The next cue starts on top of this one: the engine's timings
            # overlap. Give it something readable and let validate() say so.
            end = start + max(min_duration, 0.2)
        lines = wrap(words, spec, language)
        if mark_speakers and _voice_changed(groups, position):
            lines[0] = SPEAKER_MARK + lines[0]
        built.append(Cue(len(built) + 1, start, end, lines))

    _chain(built, spec)
    return built


def _voice_changed(groups, position):
    """Whether this group is spoken by someone other than the last one.

    The first group counts as a change only when there is more than one voice
    in the recording: a hyphen in front of every cue of a monologue would say
    nothing at all."""
    speaker = groups[position][0].speaker
    if speaker is None:
        return False
    if position == 0:
        return len({word.speaker for group in groups for word in group}) > 1
    return speaker != groups[position - 1][0].speaker


def _chain(built, spec):
    """Close the gaps that are too small to read as gaps.

    A hole of thirty milliseconds between two cues does not look like two
    subtitles, it looks like one that blinked. Anything under the snapping
    threshold is pulled out to exactly the minimum gap."""
    chaining = spec.get("gap_chaining") or {}
    snap_below = float(chaining.get("snap_below_ms", 0) or 0) / 1000.0
    snap_to = float(chaining.get("snap_to_ms", spec.get("min_gap_ms", 0) or 0)) / 1000.0
    if snap_below <= 0:
        return
    for first, second in zip(built, built[1:], strict=False):
        gap = second.start - first.end
        if 0 <= gap < snap_below:
            first.end = max(first.start + 0.2, second.start - snap_to)


# --------------------------------------------------------------------------
# the files
# --------------------------------------------------------------------------

def timestamp(seconds, separator=","):
    """``HH:MM:SS,mmm`` — the comma is SRT's, the dot is WebVTT's."""
    total = max(0.0, float(seconds))
    hours, rest = divmod(int(total), 3600)
    minutes, secs = divmod(rest, 60)
    milliseconds = int(round((total - int(total)) * 1000))
    if milliseconds == 1000:            # 1.9995 must not become ...:01,1000
        milliseconds, secs = 0, secs + 1
        if secs == 60:
            secs, minutes = 0, minutes + 1
            if minutes == 60:
                minutes, hours = 0, hours + 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{milliseconds:03d}"


def to_srt(cue_list, line_ending="\n"):
    """The SRT file as text: index, times with a comma, lines, blank line."""
    blocks = []
    for cue in cue_list:
        blocks.append(f"{cue.index}\n"
                      f"{timestamp(cue.start)} --> {timestamp(cue.end)}\n"
                      f"{cue.text}\n")
    text = "\n".join(blocks)
    return text.replace("\n", line_ending) if line_ending != "\n" else text


def to_vtt(cue_list):
    """The same cues as WebVTT: a header, and dots instead of commas."""
    blocks = ["WEBVTT\n"]
    for cue in cue_list:
        blocks.append(f"{cue.index}\n"
                      f"{timestamp(cue.start, '.')} --> {timestamp(cue.end, '.')}\n"
                      f"{cue.text}\n")
    return "\n".join(blocks)


# --------------------------------------------------------------------------
# checking the result
# --------------------------------------------------------------------------

def validate(cue_list, spec=None):
    """Everything about these cues that a subtitler would object to.

    Returned rather than raised, and returned as message keys with numbers:
    subtitles that break a rule are still better than no subtitles, and the
    person who asked for them is the one who decides."""
    spec = spec or preset()
    problems = []
    limit_cps = spec.get("max_chars_per_second")
    limit_cpl = int(spec.get("max_chars_per_line", 42))
    max_lines = int(spec.get("max_lines", 2))
    min_duration = float(spec.get("min_duration_ms", 0) or 0) / 1000.0
    max_duration = float(spec.get("max_duration_ms", 7000) or 7000) / 1000.0
    min_gap = float(spec.get("min_gap_ms", 0) or 0) / 1000.0
    words_per_minute = spec.get("max_words_per_minute")

    for position, cue in enumerate(cue_list):
        where = cue.index
        if not cue.text.strip():
            problems.append(("subtitles.empty", where, 0))
        if cue.end <= cue.start:
            problems.append(("subtitles.backwards", where, 0))
        if cue.chars > limit_cpl:
            problems.append(("subtitles.too_wide", where, cue.chars))
        if len(cue.lines) > max_lines:
            problems.append(("subtitles.too_many_lines", where, len(cue.lines)))
        if min_duration and cue.duration < min_duration - 0.001:
            problems.append(("subtitles.too_short", where, round(cue.duration, 2)))
        if cue.duration > max_duration + 0.001:
            problems.append(("subtitles.too_long", where, round(cue.duration, 2)))
        if limit_cps and cue.cps > float(limit_cps):
            problems.append(("subtitles.too_fast", where, round(cue.cps, 1)))
        if words_per_minute:
            rate = len(cue.text.split()) / (cue.duration / 60) if cue.duration else math.inf
            if rate > float(words_per_minute):
                problems.append(("subtitles.too_many_words", where, int(rate)))
        if position + 1 < len(cue_list):
            gap = cue_list[position + 1].start - cue.end
            if gap < -0.001:
                problems.append(("subtitles.overlap", where, round(gap, 3)))
            elif min_gap and gap < min_gap - 0.001:
                problems.append(("subtitles.gap_too_small", where, round(gap, 3)))
    return problems
