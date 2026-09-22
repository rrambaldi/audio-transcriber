"""What each pass actually did, written down while it happens.

This module exists because of one bug. A summary of a twenty-two minute
meeting came back describing the first seven minutes, and nothing anywhere —
not the page, not the console, not the log — said that two thirds of the
recording had gone missing. Every step had succeeded. The reading pass read
every chunk; the fold folded every group; the root wrote a page. The material
disappeared between them, through fallbacks that substitute something
plausible for something absent and say nothing about it.

So: every pass reports what went in, what came out, and which of the two it
was. And one number is computed from the result and printed whether anybody
asked for it or not — ``coverage``, the share of the recording's minutes that
the finished page mentions at all. On the summary that started this, it would
have read 34% and the bug would have been visible in ten seconds instead of
after a reading.

Nothing here is a logging framework. It is a list of records, a formatter, and
two pure functions over text, so that it can be tested without a model.
"""
import json
import unicodedata
from dataclasses import asdict, dataclass, field

#: The pass did what it was asked.
OK = "ok"

#: The answer came back from the cache instead of the model.
REUSED = "REUSED"

#: The model returned nothing at all.
EMPTY_OUTPUT = "EMPTY_OUTPUT"

#: The model returned its own question, and the transcript's own sentences
#: were put in its place. Whatever comes out of that chunk is quoted speech,
#: not a summary, and both ``copy_rate`` and the reader need to know.
ECHOED = "ECHOED"

#: There was nothing in the chunk worth an answer — silence, or convenevoli.
#: A legitimate zero, and the only one.
NO_CONTENT = "NO_CONTENT"

#: A fold produced nothing and the group fell back to its first partial. The
#: others are gone; ``lost`` says how many.
COLLAPSED = "COLLAPSED"

#: The answer stopped exactly at its allowance, which means it was cut off
#: rather than finished.
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"

#: How close to its allowance an answer has to land to count as cut off.
BUDGET_MARGIN = 0.98

#: Minutes of recording per bucket, for coverage.
BUCKET_SECONDS = 60.0

#: Below this share of the recording, the page is not a summary of it, and it
#: says so out loud whether or not anybody asked for diagnostics.
COVERAGE_FLOOR = 0.80

#: Above this share of copied speech, the model is selecting rather than
#: summarising.
COPY_FLOOR = 0.30

#: Length in words of the window compared against the transcript.
COPY_WINDOW = 8

#: How much more of the recording the reading may cover than the page before
#: the difference is a bug rather than editing. A summary does not mention
#: every minute it read; it does not drop two thirds of them either.
LOST_ON_THE_WAY = 0.25


@dataclass
class ChunkRecord:
    """One reading pass over one chunk."""
    index: int
    total: int
    in_tokens: int
    out_tokens: int
    notes: int
    #: How many of those notes say when they happened. Every measured run has
    #: had a pass that wrote notes and placed none of them, which is a pass
    #: that contributes nothing to what the recording was covered by.
    placed: int = 0
    #: Headings the model invented. Their notes are kept, as facts; the names
    #: are kept too, because a model inventing the same heading every run is
    #: a heading the catalogue is missing.
    unknown_headings: list = field(default_factory=list)
    #: What the pass was allowed to say. Without it "out=630" is a number
    #: with no scale: generous on one budget and the ceiling on another.
    budget: int = 0
    status: str = OK
    #: The minutes this pass wrote about. Kept so that what the *reading*
    #: covered can be compared with what the *page* covers: the first says
    #: whether the recording was read, the second whether it survived.
    starts: list = field(default_factory=list)
    #: The stretch of recording the chunk itself held, in seconds. Without it
    #: the minutes above cannot be read: notes about one minute are a good
    #: pass over a one-minute chunk and a truncated one over a seven-minute
    #: chunk, and those are not the same finding.
    span: tuple = (None, None)

    @property
    def covered(self):
        """Share of its own chunk this pass wrote about, 0..1.

        The number that says a pass was cut off rather than selective. A model
        that chose what mattered would write about the whole stretch sparsely;
        one that was cut off writes about the beginning of it and stops."""
        first, last = self.span
        said = [start for start in self.starts if start is not None]
        if first is None or last is None or last <= first or not said:
            return None
        return min(1.0, (max(said) - min(said)) / (last - first))

    def line(self):
        head = f"chunk {self.index:02d}/{self.total:02d}"
        if self.status == REUSED:
            return f"{head}  cache-hit{'':22}{REUSED}"
        covered = self.covered
        share = "" if covered is None else f"  covered={covered * 100:.0f}%"
        return (f"{head}  in={self.in_tokens} tok  "
                f"out={self.out_tokens}/{self.budget} tok  "
                f"note={self.placed}/{self.notes}{share}  {self.status}")


@dataclass
class FoldRecord:
    """One fold of one group of partials, at one level of the tree."""
    level: int
    group: int
    groups: int
    partials_in: int
    in_tokens: int
    budget: int
    out_tokens: int
    status: str = OK
    lost: int = 0

    def line(self):
        head = (f"fold  L{self.level} g{self.group}/{self.groups}  "
                f"in={self.partials_in} parz ({self.in_tokens} tok)  "
                f"budget={self.budget}  out={self.out_tokens} tok")
        if self.status == COLLAPSED:
            return f"{head}  {COLLAPSED}->texts[0]  persi={self.lost}"
        return f"{head}  {self.status}"


class Trace:
    """Every pass of one summary, and what it did."""

    def __init__(self):
        self.chunks = []
        self.folds = []
        #: What each reading pass actually wrote. Content, so it never goes
        #: near the numbers: it is kept so that a question about the *parsing*
        #: can be answered without asking a graphics card to read an hour of
        #: meeting again.
        self.answers = []
        #: Every note every pass produced, in order. The product of the
        #: reading, and what the grouping will be given once there is one.
        self.notes = []

    # --- recording ---------------------------------------------------------

    def chunk(self, budget=None, **fields):
        record = ChunkRecord(budget=int(budget or 0), **fields)
        if (record.status in (OK, REUSED) and budget
                and record.out_tokens >= budget * BUDGET_MARGIN):
            # It stopped where it ran out, not where it had finished. On a
            # bullet list that is invisible: what comes back parses perfectly
            # and is simply missing the rest of the chunk. A cache hit is
            # marked too — an answer that was cut off when it was written is
            # still cut off when it is read back, and a control run against a
            # stale cache is exactly where that would have been missed.
            record.status = BUDGET_EXHAUSTED
        self.chunks.append(record)
        return record

    def fold(self, **fields):
        record = FoldRecord(**fields)
        self.folds.append(record)
        return record

    # --- reading it back ---------------------------------------------------

    def lines(self):
        return [record.line() for record in self.chunks + self.folds]

    def failures(self):
        """The records worth a line on the console even when all is well.

        A chunk that produced nothing is one of these, and a fold that lost
        partials is one of these. A cache hit is not."""
        return ([record for record in self.chunks
                 if record.status in (EMPTY_OUTPUT, ECHOED, BUDGET_EXHAUSTED)
                 or (record.notes == 0 and record.status != NO_CONTENT)]
                + [record for record in self.folds if record.status != OK])

    def reading_coverage(self, duration_seconds):
        """Share of the recording the reading passes wrote about at all.

        Paired with the coverage of the finished page, this is the diagnosis:
        both low means the recording was never read, the first high and the
        second low means it was read and then lost on the way up."""
        return coverage([start for record in self.chunks
                         for start in record.starts], duration_seconds)

    def counts(self):
        collapsed = [record for record in self.folds
                     if record.status == COLLAPSED]
        return {
            "chunks": len(self.chunks),
            "empty_chunks": sum(1 for record in self.chunks
                                if record.notes == 0
                                and record.status != NO_CONTENT),
            "echoed_chunks": sum(1 for record in self.chunks
                                 if record.status == ECHOED),
            "folds": len(self.folds),
            "folds_collapsed": len(collapsed),
            "partials_lost": sum(record.lost for record in collapsed),
            "folds_exhausted": sum(1 for record in self.folds
                                   if record.status == BUDGET_EXHAUSTED),
            "chunks_exhausted": sum(1 for record in self.chunks
                                    if record.status == BUDGET_EXHAUSTED),
            "notes": sum(record.notes for record in self.chunks),
            "notes_placed": sum(record.placed for record in self.chunks),
            "unplaced_chunks": sum(1 for record in self.chunks
                                   if record.notes and not record.placed),
            "unknown_headings": sorted({name for record in self.chunks
                                        for name in record.unknown_headings}),
            "map_budget": max((record.budget for record in self.chunks),
                              default=0),
            "least_covered_chunk": min(
                [record.covered for record in self.chunks
                 if record.covered is not None], default=None),
        }

    def as_document(self, extra=None):
        """Everything recorded, as JSON, for ``--dump-notes``."""
        payload = {
            "schema": 1,
            "chunks": [asdict(record) for record in self.chunks],
            "folds": [asdict(record) for record in self.folds],
            "counts": self.counts(),
        }
        payload.update(extra or {})
        return json.dumps(payload, ensure_ascii=False, indent=2)


# --- the two numbers that need no model -----------------------------------

def _fold_word(word):
    """A word without its accents, lowercased: Whisper writes them, a person
    typing the same word into a comparison often does not."""
    stripped = unicodedata.normalize("NFD", word.lower())
    return "".join(letter for letter in stripped
                   if not unicodedata.combining(letter))


def _words(text):
    return [_fold_word(word) for word in str(text or "").split() if word]


def coverage(starts, duration_seconds, bucket=BUCKET_SECONDS):
    """Share of the recording's minutes the page mentions at all, 0..1.

    ``starts`` are the seconds carried by whatever the page ended up saying —
    one per point on it. A page whose last timestamp is 7:30 out of 22 minutes
    scores 0.34, and that is the whole of the bug it was written to catch.

    ``None`` when the recording's length is unknown: an invented denominator
    would be worse than no number."""
    if not duration_seconds or duration_seconds <= 0:
        return None
    buckets = max(1, int((float(duration_seconds) + bucket - 1) // bucket))
    seen = {int(float(start) // bucket) for start in starts
            if start is not None and 0 <= float(start) < duration_seconds}
    return min(1.0, len(seen) / buckets)


def copy_rate(texts, transcript, window=COPY_WINDOW):
    """Share of the summary's word windows found verbatim in the transcript.

    A summary is meant to be written, not selected. This is how much of it was
    selected. Measured on runs of :data:`COPY_WINDOW` words with the accents
    folded away, because a coincidence of eight words in a row is not a
    coincidence.

    ``None`` when there is not enough text to ask the question."""
    source = _words(transcript)
    if len(source) < window:
        return None
    haystack = {tuple(source[at:at + window])
                for at in range(len(source) - window + 1)}
    windows, copied = 0, 0
    for text in texts:
        said = _words(text)
        for at in range(len(said) - window + 1):
            windows += 1
            if tuple(said[at:at + window]) in haystack:
                copied += 1
    return copied / windows if windows else None
