"""What the desktop window shows, worked out without importing Qt.

Everything here is a plain function over plain data: the menus offered, the
rows of the two tables, the blocks the transcript is laid out in, the name a
new recording gets. Keeping it out of the widgets means the interesting
decisions can be tested on a machine with no display and no Qt installed,
which is exactly the machine this project's test suite has to run on.

The widgets are therefore only wiring: they read these lists, show them, and
hand the answers back to :class:`audio_transcriber.jobs.JobQueue`.
"""
import math
import os
from datetime import datetime

from .. import recording, vocabularies
from ..backends import BACKENDS
from ..formatting import format_bytes, format_clock, format_duration
from ..i18n import t
from ..jobs import (
    CANCELLED,
    DONE,
    FAILED,
    FINISHED,
    HELD,
    NOT_STARTED,
    QUEUED,
    RUNNING,
)
from ..library import LibraryError
from ..transcription import AUTO, LANGUAGE_CHOICES, MODEL_CHOICES, recommend_model
from ..vocabularies import MAX_CUSTOM_VOCABULARY

#: Extensions offered by the file dialog. ffmpeg reads far more than this, so
#: the dialog also offers "every file": this list is a convenience, not a rule.
MEDIA_EXTENSIONS = ("mp3", "m4a", "wav", "flac", "ogg", "opus", "aac", "wma",
                    "mp4", "mkv", "mov", "avi", "webm", "m4v", "mpg", "mpeg")

#: Language names shown in the spoken-language menu. Only the ones offered in
#: the menu need a name; anything else is passed through as its code.
LANGUAGE_NAMES = {"it": "Italiano", "en": "English", "fr": "Français",
                  "de": "Deutsch", "es": "Español"}


# --------------------------------------------------------------------------
# the menus
# --------------------------------------------------------------------------

def model_choices(recommended=None):
    """``(label, value)`` for the model menu.

    ``auto`` is labelled with what it actually resolves to on this machine:
    "auto" alone tells the user nothing, and the whole point of the automatic
    choice is that they can see it and disagree."""
    if recommended is None:
        recommended = recommend_model()
    choices = [(t("gui.model_auto", model=recommended), AUTO)]
    choices += [(name, name) for name in MODEL_CHOICES if name != AUTO]
    return choices


def language_choices():
    """``(label, value)`` for the spoken-language menu; ``""`` auto-detects."""
    choices = [(t("gui.language_auto"), "")]
    for code in LANGUAGE_CHOICES:
        if not code:
            continue
        name = LANGUAGE_NAMES.get(code, code)
        choices.append((f"{name} ({code})", code))
    return choices


def backend_choices():
    """``(label, value)`` for the engine menu."""
    return [(t("gui.backend_auto"), "auto")] + [(name, name) for name in BACKENDS
                                                if name != "auto"]


def vocabulary_items(vocab_dir=None):
    """The installed keyword sets, described for a checkable list.

    The same two origins the command line and the web page use, so a set added
    with ``vocab new`` shows up in the window without anything else happening.
    """
    items = []
    for item in vocabularies.available(vocab_dir):
        text = item.text
        items.append({
            "name": item.name,
            "title": item.title,
            "source": item.source,
            "language": item.language,
            "terms": len(vocabularies.terms(text)),
            "chars": len(text),
            "label": t("gui.vocab_label", title=item.title, name=item.name,
                       terms=len(vocabularies.terms(text))),
            "tooltip": text,
        })
    return items


def defaults_from(settings):
    """The state the option widgets start in, taken from the resolved settings.

    The window is a front end for the same configuration the CLI reads, so
    ``config.toml`` decides what is preselected."""
    settings = settings or {}
    return {
        "model": settings.get("model") or AUTO,
        "language": settings.get("language") or "",
        "backend": settings.get("backend") or "auto",
        "diarize": bool(settings.get("diarize")),
        "speakers": int(settings.get("speakers") or 0),
        "vocabulary": vocabularies.split_names(settings.get("vocabulary")),
    }


def overrides_from(choices):
    """Turn the window's answers into the overrides the queue expects.

    ``None`` means "not chosen here", which is how the queue knows to leave the
    configured value alone; ``language`` is the exception, because an empty
    string is a real choice ("detect it")."""
    return {
        "model": choices.get("model") or None,
        "language": choices.get("language") if choices.get("language") is not None else None,
        "backend": choices.get("backend") or None,
        "diarize": True if choices.get("diarize") else None,
        "speakers": choices.get("speakers") or None,
    }


def custom_vocabulary_problem(text):
    """Why the typed-in vocabulary cannot be used, or ``None`` if it can."""
    if len(text or "") > MAX_CUSTOM_VOCABULARY:
        return t("gui.vocab_too_long", limit=MAX_CUSTOM_VOCABULARY)
    return None


def media_filter():
    """The file dialog's filter string, media first, everything second."""
    patterns = " ".join(f"*.{extension}" for extension in MEDIA_EXTENSIONS)
    return f"{t('gui.filter_media')} ({patterns});;{t('gui.filter_any')} (*)"


# --------------------------------------------------------------------------
# the queue table
# --------------------------------------------------------------------------

def job_headers():
    """Column headings of the queue table, in order."""
    return [t("gui.col_title"), t("gui.col_status"), t("gui.col_progress"),
            t("gui.col_model"), t("gui.col_duration"), t("gui.col_words")]


#: Human wording for each job state.
_STATUS_KEYS = {HELD: "gui.status_held", QUEUED: "gui.status_queued",
                RUNNING: "gui.status_running", DONE: "gui.status_done",
                FAILED: "gui.status_failed", CANCELLED: "gui.status_cancelled"}


def status_text(job):
    """What the status column says: the state, and what it is doing in it.

    The stage matters more than it looks. A transcription is one long blocking
    call, and on an engine that reports no progress of its own the bar stands
    still for the whole of it — "transcribing" next to a motionless bar is the
    difference between waiting and wondering."""
    label = t(_STATUS_KEYS.get(job.status, "gui.status_queued"))
    if job.status == FAILED and job.error:
        return f"{label}: {first_line(job.error)}"
    stage = getattr(job, "stage", None)
    if job.status == RUNNING and stage:
        return f"{label}: {t(stage)}"
    return label


def job_row(job):
    """One row of the queue table, as strings plus the progress percentage."""
    return {
        "id": job.id,
        "title": job.title,
        "status": status_text(job),
        "progress": int(job.progress or 0),
        "model": job.settings.get("model") or AUTO,
        "duration": format_duration(job.audio_duration),
        "words": "-" if job.words is None else str(job.words),
        "entry_id": job.entry_id,
        "finished": job.status in FINISHED,
        "failed": job.status == FAILED,
        "held": job.status == HELD,
        "cancellable": job.status in NOT_STARTED,
        "running": job.status == RUNNING,
        "tooltip": job.error or job.filename,
    }


def queue_summary(jobs):
    """One line under the table: what the queue is doing right now."""
    if not jobs:
        return t("gui.queue_empty")
    held = sum(1 for job in jobs if job.status == HELD)
    running = sum(1 for job in jobs if job.status == RUNNING)
    waiting = sum(1 for job in jobs if job.status == QUEUED)
    if held:
        # What needs doing wins over what is happening: the table already
        # shows the running job and its bar, and this line is the only place
        # that can say the queue is waiting for a button.
        return t("gui.queue_held", count=held)
    if running or waiting:
        return t("gui.queue_busy", running=running, waiting=waiting)
    failed = sum(1 for job in jobs if job.status == FAILED)
    done = sum(1 for job in jobs if job.status == DONE)
    cancelled = sum(1 for job in jobs if job.status == CANCELLED)
    return t("gui.queue_idle", done=done, failed=failed, cancelled=cancelled)


# --------------------------------------------------------------------------
# the library table and the reading pane
# --------------------------------------------------------------------------

def entry_headers():
    """Column headings of the library table, in order."""
    return [t("gui.col_date"), t("gui.col_title"), t("gui.col_duration"),
            t("gui.col_words"), t("gui.col_model"), t("gui.col_notes")]


def entry_row(entry):
    """One row of the library table, or ``None`` for an unreadable entry.

    A folder with broken metadata must not stop the whole list from being
    shown: the library is meant to survive this program."""
    try:
        data = entry.metadata
    except LibraryError:
        return None
    audio = data.get("audio") or {}
    stats = data.get("stats") or {}
    transcription = data.get("transcription") or {}
    return {
        "id": entry.id,
        "date": (data.get("created_at") or "")[:16].replace("T", " "),
        "title": data.get("title") or entry.id,
        "duration": format_duration(audio.get("duration_seconds")),
        "words": str(stats.get("words") or "-"),
        "model": transcription.get("model") or "-",
        "notes": t("gui.notes_yes") if entry.has_written_notes() else "",
        "diarized": bool(transcription.get("diarized")),
        "path": entry.path,
    }


def entry_rows(entries):
    """Every readable row, in the order the library returned them."""
    return [row for row in (entry_row(entry) for entry in entries) if row]


def entry_details(entry):
    """The lines shown above the transcript: what this recording is."""
    try:
        data = entry.metadata
    except LibraryError:
        return []
    audio = data.get("audio") or {}
    transcription = data.get("transcription") or {}
    source = data.get("source") or {}
    names = transcription.get("vocabulary") or []
    lines = [
        (t("gui.detail_created"), (data.get("created_at") or "-")[:19].replace("T", " ")),
        (t("gui.detail_duration"), format_duration(audio.get("duration_seconds"))),
        (t("gui.detail_model"), " / ".join(
            str(part) for part in (transcription.get("model"),
                                   transcription.get("backend"),
                                   transcription.get("device")) if part) or "-"),
        (t("gui.detail_language"), transcription.get("language") or "-"),
        (t("gui.detail_elapsed"), format_duration(transcription.get("elapsed_seconds"))),
        (t("gui.detail_vocabulary"), ", ".join(names) if names else "-"),
        (t("gui.detail_folder"), entry.path),
    ]
    if source.get("bytes"):
        # Worth showing: a filed hour of audio is hundreds of megabytes, and on
        # a small disk that is the number people actually want to see.
        lines.insert(2, (t("gui.detail_size"), format_bytes(source["bytes"])))
    if transcription.get("diarized"):
        lines.insert(4, (t("gui.detail_speakers"),
                         str(transcription.get("speakers") or t("gui.detail_detected"))))
    return lines


def transcript_blocks(segments, text=""):
    """The transcript as ``(seconds, clock, body)`` blocks.

    With segments there is a timestamp per block, and clicking it seeks the
    player — the desktop equivalent of the web page's minute links. Without
    them (an entry transcribed before segments were stored, or a backend that
    returned none) the plain text is shown as one block per paragraph, with no
    timestamp to click."""
    blocks = []
    for segment in segments or []:
        body = str(segment.get("text") or "").strip()
        if not body:
            continue
        start = float(segment.get("start") or 0.0)
        speaker = segment.get("speaker")
        if speaker:
            body = f"{speaker}: {body}"
        blocks.append((start, format_clock(start), body))
    if blocks:
        return blocks
    return [(None, "", paragraph.strip())
            for paragraph in (text or "").split("\n\n") if paragraph.strip()]


def search_summary(query, count):
    """What the label next to the search box says."""
    if not (query or "").strip():
        return t("gui.library_count", count=count)
    return t("gui.library_matches", count=count, query=query.strip())


# --------------------------------------------------------------------------
# what the recording menus say
# --------------------------------------------------------------------------

def source_label(source, with_host_api=False):
    """How one recordable source reads in a menu.

    A loopback is marked as such, because "Speakers" among the *recording*
    sources is otherwise a contradiction: it records what those speakers
    play. ``with_host_api`` is for the "together with" menu, which mixes
    sources from different audio systems and would otherwise show two
    identical names."""
    label = (t("gui.rec_loopback_label", name=source.label)
             if source.is_loopback else source.label)
    return f"{label} - {source.host_api}" if with_host_api else label


def mix_candidates(sources, primary_key):
    """What may be recorded *together with* the chosen source.

    Anything but the source itself: mixing a microphone with itself would
    only make it twice as loud. Loopbacks come first, because they are the
    reason this menu exists — a call has the others in the speakers."""
    others = [source for source in sources if source.key != primary_key]
    return sorted(others, key=lambda source: not source.is_loopback)


#: Quietest peak the level meter shows. Below it the bar is empty: -60 dBFS is
#: a silent room, and stretching the scale further down only makes the noise
#: floor look like signal.
LEVEL_FLOOR_DB = -60.0


def level_percent(peak):
    """A peak amplitude (0..1) as a bar length (0..100), in decibels.

    A linear bar makes a useless meter: ordinary speech peaks at around a tenth
    of full scale and would barely leave the left edge, so a working microphone
    would look like a broken one. Decibels are how every audio meter is read —
    speech at -20 dBFS fills two thirds of this one."""
    if not peak or peak <= 0:
        return 0
    decibels = 20.0 * math.log10(min(1.0, float(peak)))
    if decibels <= LEVEL_FLOOR_DB:
        return 0
    return int(round((decibels - LEVEL_FLOOR_DB) / -LEVEL_FLOOR_DB * 100))


def speech_verdict(verdict, detail):
    """One line about what the audio test is hearing, and the numbers behind it.

    The numbers are there on purpose: a verdict nobody can argue with is no
    help to someone whose microphone is not working. Level, dynamics and how
    much of the energy sits in the band a voice lives in are exactly what the
    guess is made of."""
    if not detail or not detail.get("ready"):
        return t("gui.rec_test_listening")
    key = {recording.SILENCE: "gui.rec_test_silence",
           recording.SOUND: "gui.rec_test_sound",
           recording.SPEECH: "gui.rec_test_speech"}.get(verdict)
    if key is None:
        return t("gui.rec_test_listening")
    return t(key, level=int(round(detail["level_db"])),
             dynamic=int(round(detail["dynamic_db"])),
             band=int(round(detail["band_ratio"] * 100)))


def host_api_summary(sources):
    """Tooltip for one audio system: how many sources it offers."""
    loopbacks = sum(1 for source in sources if source.is_loopback)
    return t("gui.rec_host_api_summary", count=len(sources), loopbacks=loopbacks)


# --------------------------------------------------------------------------
# recording and file names
# --------------------------------------------------------------------------

def recording_stem(when=None):
    """Stem of a new recording's file: sortable, and readable in a folder."""
    return (when or datetime.now()).strftime("%Y-%m-%d_%H%M%S") + "-recording"


def recording_title(when=None):
    """Default title of a recording made in the window."""
    when = when or datetime.now()
    return t("gui.recording_title", when=when.strftime("%Y-%m-%d %H:%M"))


def title_from_path(path):
    """The title a dropped file gets: its name without the extension."""
    return os.path.splitext(os.path.basename(str(path or "")))[0]


def playable_files(paths):
    """Keep the dropped paths that are files, in order, without duplicates.

    A drop can carry a directory, a URL to something that is not a file, or the
    same file twice; none of that should reach the queue."""
    kept = []
    for path in paths or []:
        if not path:
            continue
        absolute = os.path.abspath(os.path.expanduser(str(path)))
        if os.path.isfile(absolute) and absolute not in kept:
            kept.append(absolute)
    return kept


def first_line(text):
    """First line of a possibly multi-line message, for a one-line cell."""
    for line in str(text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""
