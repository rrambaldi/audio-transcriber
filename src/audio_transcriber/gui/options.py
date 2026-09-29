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

from .. import recording, subtitles, vocabularies
from ..backends import BACKENDS
from ..config import output_of
from ..diarization import LEARN_MINUTES
from ..formatting import format_bytes, format_clock, format_duration, format_when
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
    SUMMARY,
)
from ..library import Entry, LibraryError
from ..summarizers import CHOICES as SUMMARY_ENGINES
from ..summarizers import available as summary_engines_available
from ..summarizers import plan
from ..summary import DEFAULT_LENGTH, DEFAULT_STYLE, LENGTHS, STYLES
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

def output_choices():
    """``(label, note, value)`` for the four things a run can be for.

    The choice people arrive with — "I want the text", "I want subtitles",
    each of them with or without who said what — said in those words.
    Everything else in the options box is a detail of one of these four.

    Who said what is one of the four answers rather than a tick box beside
    them: as a box it sat there meaning nothing for two of the three, and
    made the third two answers wearing one name."""
    return [
        (t("gui.output_text"), t("gui.output_text_note"), "text"),
        (t("gui.output_speakers"), t("gui.output_speakers_note"), "speakers"),
        (t("gui.output_subtitles"), t("gui.output_subtitles_note"), "subtitles"),
        (t("gui.output_subtitles_speakers"), t("gui.output_subtitles_speakers_note"),
         "subtitles_speakers"),
    ]


#: The answers that ask who was speaking: they enable the count of speakers,
#: and they are the ones a machine without pyannote cannot offer at all.
DIARIZING = ("speakers", "subtitles_speakers")


def output_label(output):
    """The name of a choice, for a section that reports itself when closed."""
    for label, _note, value in output_choices():
        if value == output:
            return label
    return ""


def subtitle_summary_line(preset, chars, words, srt, vtt):
    """What the subtitle section says with its panel shut.

    The numbers people actually changed, and the files that will be written:
    a row that says only "Subtitles" has hidden the choice it was holding."""
    parts = [preset or subtitles.DEFAULT_PRESET]
    if chars:
        parts.append(t("gui.sub_chars_short", count=chars))
    if words:
        parts.append(t("gui.sub_words_short", count=words))
    kept = [kind for kind, on in (("srt", srt), ("vtt", vtt)) if on]
    parts.append(", ".join(f".{kind}" for kind in kept) if kept
                 else t("gui.sub_saved_none"))
    return "  ·  ".join(str(part) for part in parts)


def output_note(output):
    """The one-line explanation of what a choice produces."""
    for _label, note, value in output_choices():
        if value == output:
            return note
    return ""


def output_enables(output):
    """Which of the dependent controls this choice makes meaningful.

    Returned as data so the window can grey out the rest instead of leaving
    boxes that do nothing: a subtitle preset means nothing when the answer is
    plain text, and "how many speakers" means nothing when nobody asked who
    they were."""
    return {
        "speakers": output in DIARIZING,
        "subtitles": output in ("subtitles", "subtitles_speakers"),
    }


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
    """``(label, value, available)`` for the engine menu.

    An engine this machine does not have is still listed, greyed out: it is
    part of what the program is, and seeing it with the reason attached beats
    wondering why the machine down the hall has two. What it must not be is
    choosable, because choosing it used to mean a job that failed after the
    audio had been decoded."""
    from ..backends import is_installed

    return [(t("gui.backend_auto"), "auto", True)] + [
        (name, name, is_installed(name)) for name in BACKENDS if name != "auto"]


def usable_backend(name):
    """The engine to start on: the one asked for, if this machine has it.

    The window remembers the last engine chosen, and ``gui.ini`` outlives an
    environment: a 'faster-whisper' remembered from one install turns every
    job in another into the same failure, and nothing on screen says why."""
    from ..backends import is_installed

    name = (name or "auto").strip().lower()
    return name if name == "auto" or is_installed(name) else "auto"


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
            "label": t("gui.vocab_label", title=item.title,
                       terms=len(vocabularies.terms(text))),
            # The file name is what a set is called on the command line; in
            # the list it is noise, so it heads the tooltip instead.
            "tooltip": f"{item.name}\n\n{text}",
        })
    return items


def output_settings(choices):
    """The output part of what the window is asking for.

    The name of the answer and nothing else: what it implies — diarization,
    a subtitle format — is settled by :func:`config.resolve_output`, in the
    one place all three interfaces go through."""
    return {"output": choices.get("output") or "text"}


def defaults_from(settings):
    """The state the option widgets start in, taken from the resolved settings.

    The window is a front end for the same configuration the CLI reads, so
    ``config.toml`` decides what is preselected."""
    settings = settings or {}
    return {
        "model": settings.get("model") or AUTO,
        "language": settings.get("language") if settings.get("language") is not None else "it",
        "backend": settings.get("backend") or "auto",
        "diarize": bool(settings.get("diarize")),
        "summary_after": bool(settings.get("summary_after")),
        "auto_title": bool(settings.get("auto_title")),
        "speakers": int(settings.get("speakers") or 0),
        "learn_voices": bool(settings.get("diar_learn_minutes")),
        "vocabulary": vocabularies.split_names(settings.get("vocabulary")),
        "subtitle_preset": settings.get("subtitle_preset") or subtitles.DEFAULT_PRESET,
        "subtitles": str(settings.get("subtitles") or ""),
        "output": output_of(settings),
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
        # Not "diarize": the chosen answer says whether anybody asked who was
        # speaking, and resolve_output turns that into the flag.
        "speakers": choices.get("speakers") or None,
        # 0 rather than None when it is not ticked: None would leave a
        # config.toml that learns the voices learning them anyway.
        "diar_learn_minutes": LEARN_MINUTES if choices.get("learn_voices") else 0,
        "summary_after": True if choices.get("summary_after") else None,
        "auto_title": True if choices.get("auto_title") else None,
    }


def subtitle_preset_choices():
    """``(label, name)`` for the subtitle preset menu.

    Labelled with the numbers that matter, because "bbc" tells you nothing
    about how wide a line will be."""
    choices = []
    for name, spec in sorted(subtitles.presets().items()):
        numbers = t("gui.sub_preset_numbers",
                    chars=spec.get("max_chars_per_line", "-"),
                    lines=spec.get("max_lines", "-"),
                    cps=spec.get("max_chars_per_second", "-"))
        choices.append((f"{name} - {numbers}", name))
    return choices


def subtitle_settings(choices):
    """The subtitle part of what the window is asking for.

    Zero means "whatever the preset says", which is how a spin box says "not
    chosen" without a second widget next to it."""
    formats = [kind for kind in ("srt", "vtt") if choices.get(kind)]
    return {
        "subtitles": ",".join(formats) or None,
        "subtitle_preset": choices.get("subtitle_preset") or None,
        "subtitle_chars": choices.get("subtitle_chars") or None,
        "subtitle_words": choices.get("subtitle_words") or None,
        # A text somebody already has: it helps the engine spell and then
        # proof-reads what it heard. See audio_transcriber/reference.py.
        "reference": (choices.get("reference") or "").strip() or None,
    }


def subtitle_summary(entry):
    """What the library says about an entry's subtitles, or ``None``."""
    try:
        data = (entry.metadata.get("subtitles") or {})
    except LibraryError:
        return None
    kinds = entry.subtitles()
    if not kinds:
        return None
    return t("gui.sub_saved", formats=", ".join(kinds),
             cues=data.get("cues") or 0, preset=data.get("preset") or "-")


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
    """Column headings of the queue table, in order.

    Three, not six. Model, duration and word count used to be columns of
    their own, which meant they were empty for the whole of a job's life and
    filled in a moment before the row stopped being interesting; they are the
    second line of the recording now, where they read as facts about it."""
    return [t("gui.col_recording"), t("gui.col_status"), t("gui.col_progress"),
            t("gui.col_actions")]


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
    stage = getattr(job, "stage", None)
    if job.status != RUNNING:
        return label
    if stage:
        label = f"{label}: {t(stage)}"
    # And the clock, because a step can take twenty minutes and the bar does
    # not move inside one: something on the row has to be going up.
    running = getattr(job, "running_seconds", None)
    return f"{label}  ·  {format_duration(running)}" if running else label


def job_details(job):
    """The second line of a queue row: what is known about the recording.

    Only what is known. A job that has not started has a model and nothing
    else, and a dash under three headings said less than nothing — it looked
    like a value that had failed to arrive."""
    # What the recording *is* — how long, how big, when it was made — comes
    # first and is there whatever the job's state: those are the facts that
    # tell one row from another in a queue of files named by date, and they
    # are known before anything has been done to them. A summary carries the
    # facts of the recording it was made from, which is the recording the
    # person at the list is thinking of.
    parts = _recording_facts(job)
    if job.kind == SUMMARY:
        # Its "model" is the one that transcribed the entry, which has nothing
        # to do with what this job is doing to it: what this row is, is said
        # instead.
        parts.append(t("gui.row_summary_of",
                       engine=job.settings.get("summary_engine") or AUTO))
        return "  ·  ".join(str(part) for part in parts if part)
    parts.append(job.settings.get("model") or AUTO)
    if job.words:
        parts.append(t("gui.n_words", count=job.words))
    if job.status == FAILED and job.error:
        # And why it failed, after them rather than instead of them: the row
        # still has to say which recording this was.
        parts.append(first_line(job.error))
    return "  ·  ".join(str(part) for part in parts if part)


def _recording_facts(job):
    """How long, how big and when, for whichever recording the row is about."""
    return [format_duration(job.audio_duration) if job.audio_duration else "",
            format_bytes(job.size_bytes) if getattr(job, "size_bytes", None) else "",
            format_when(getattr(job, "source_created_at", None))]


def row_title(job):
    """The name at the top of a queue row.

    A summary has no recording of its own: it is made with the title of the
    entry it reads, so on the list it looked exactly like the transcription
    that produced that entry — same name, and no length or size under it,
    because a summary has neither. Five retries of one summary read as five
    mystery files. Saying what the row *is* costs one word."""
    if job.kind == SUMMARY:
        return t("gui.row_summary_title", title=job.title)
    return job.title


def job_row(job):
    """One row of the queue table, as strings plus the progress percentage."""
    return {
        "id": job.id,
        "title": row_title(job),
        "details": job_details(job),
        #: How loud the recording is, slice by slice, or None until the queue
        #: has measured it. Drawn under the name by widgets.JobDelegate.
        "loudness": job.loudness,
        "status": status_text(job),
        "progress": int(job.progress or 0),
        "model": job.settings.get("model") or AUTO,
        "duration": format_duration(job.audio_duration),
        "words": "-" if job.words is None else str(job.words),
        "entry_id": job.entry_id,
        "finished": job.status in FINISHED,
        "done": job.status == DONE,
        "failed": job.status == FAILED,
        "held": job.status == HELD,
        "cancellable": job.status in NOT_STARTED,
        "running": job.status == RUNNING,
        "retryable": job.status in (FAILED, CANCELLED),
        "tooltip": job.error or job.filename,
        **job_actions(job),
    }


def job_actions(job):
    """What the three buttons on a row say, for the state it is in.

    "Start it" and "stop it" are the same place in the row and never both
    apply, so the first button changes rather than the row growing a fourth
    button that is disabled most of the time."""
    # And what it looks like: a symbol and a role, which gui/symbols.py turns
    # into a drawing and a colour. Stopping a transcription throws away what
    # it has done, so it is said in the colour of the other things that lose
    # something.
    if job.status == HELD:
        action, look = t("gui.row_transcribe"), ("transcribe", "go")
    elif job.status in (QUEUED, RUNNING):
        action, look = t("gui.row_stop"), ("stop", "danger")
    elif job.status == DONE and job.entry_id:
        action, look = t("gui.row_open"), ("open", None)
    elif job.status in (FAILED, CANCELLED):
        action, look = t("gui.row_retry"), ("retry", "go")
    else:
        action, look = "", None
    return {
        "action": action,
        "action_look": look,
        # A summary is not asked what it is for: the four questions are about
        # transcribing, and a summary job that went through them would have
        # its settings replaced with answers about something else.
        "asks": job.kind != SUMMARY,
        "removable": job.status != RUNNING,
        "removable_label": t("gui.row_remove"),
        "play_audio": t("gui.row_play"),
        "stop_audio": t("gui.row_stop_audio"),
    }


def start_label(held):
    """What the primary button says: the verb, and how much it will start.

    A button that says only "Transcribe" leaves the count to be worked out
    from the list; with it on the button, pressing it is a decision with a
    known size."""
    if not held:
        return t("gui.start")
    return t("gui.start_one" if held == 1 else "gui.start_many", count=held)


def queue_summary(jobs):
    """One line under the table: what the queue is doing right now.

    States are listed, not chosen between. The first version of this picked
    the one it thought mattered most — what is waiting for a button — and so
    a queue with one job running at 34% and one waiting said "1 waiting,
    press Transcribe", which is a screen telling the user something it can
    see is not the whole truth."""
    if not jobs:
        return t("gui.queue_empty")
    held = sum(1 for job in jobs if job.status == HELD)
    running = sum(1 for job in jobs if job.status == RUNNING)
    waiting = sum(1 for job in jobs if job.status == QUEUED)
    parts = []
    if running:
        percent = max(int(job.progress or 0) for job in jobs
                      if job.status == RUNNING)
        parts.append(t("gui.queue_part_running", count=running, percent=percent))
    if waiting:
        parts.append(t("gui.queue_part_waiting", count=waiting))
    if held:
        parts.append(t("gui.queue_part_held", count=held))
    if parts:
        line = "  ·  ".join(parts)
        return f"{line}  {t('gui.queue_press_start')}" if held else line
    failed = sum(1 for job in jobs if job.status == FAILED)
    done = sum(1 for job in jobs if job.status == DONE)
    cancelled = sum(1 for job in jobs if job.status == CANCELLED)
    return t("gui.queue_idle", done=done, failed=failed, cancelled=cancelled)


# --------------------------------------------------------------------------
# the library table and the reading pane
# --------------------------------------------------------------------------

#: The commands that add what an option needs. They go in tooltips, never in
#: the text on screen: whoever reads the window is not necessarily whoever
#: installs it, and a pip command is not a sentence.
INSTALL_COMMANDS = {
    "diarize": 'pip install "audio-transcriber-ov[diarize]"',
    "multimedia": "pip install PySide6-Addons",
    "record": 'pip install "audio-transcriber-ov[record]"',
}

#: What a row of the library carries when it is dragged onto a folder.
ENTRY_MIME = "application/x-audio-transcriber-entry"


def folder_of(entry_id):
    """The folder an entry id is in: "" at the top of the library."""
    return str(entry_id or "").rpartition("/")[0]


def folder_choices(folders):
    """The top of the library and every folder, as ``(folder, label)``.

    A folder is labelled by its whole path, so two folders called "2026" in
    different places can be told apart in a menu."""
    return [("", t("gui.tree_library"))] + [
        (folder, folder.replace("/", " › ")) for folder in folders]


def entry_headers():
    """Column headings of the library table: one, as the queue's has.

    Date, title, length, words, model and notes were six columns, and beside
    the folders the title - the one worth reading - was squeezed to nothing.
    They are the title and the line of facts under it now, the way a queue
    row has always been drawn."""
    return [t("gui.col_recording")]


def entry_facts(row):
    """The line under a library row's title: when, how long, how many words,
    by which model, and what else the entry holds."""
    parts = [row["date"], row["duration"],
             t("gui.n_words", count=row["words"]) if row["words"] != "-" else "",
             row["model"]]
    for key, label in (("summary", "gui.badge_summary"),
                       ("subtitles", "gui.badge_subtitles"),
                       ("diarized", "gui.badge_speakers"),
                       ("notes", "gui.badge_notes")):
        if row.get(key):
            parts.append(t(label))
    return "  ·  ".join(str(part) for part in parts if part and part != "-")


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
        # Only what is already on disk. Measuring an entry that has never been
        # measured is a pass of ffmpeg over the whole recording, and a list
        # must not do forty of those to draw itself: the panel asks for the
        # missing ones in the background, a row at a time.
        "loudness": entry.read_waveform(),
        "path": entry.path,
        "folder": folder_of(entry.id),
        "summary": entry.has_summary(),
        "subtitles": bool(entry.subtitles()),
    }


def entry_rows(entries, copies=None):
    """Every readable row, in the order the library returned them.

    ``copies`` is :meth:`Library.copies`: a recording transcribed more than
    once is one row, its newest transcription, saying how many there are -
    the others are a menu on the Transcript tab, not rows reading as the same
    name over and over."""
    copies = copies or {}
    rows, shown = [], set()
    for row in (entry_row(entry) for entry in entries):
        if not row:
            continue
        group = copies.get(row["id"], ())
        if group:
            # Newest first, as the library lists them: the first one seen is
            # the one the row stands for.
            if group[0].id in shown:
                continue
            shown.add(group[0].id)
            row["summary"] = row["summary"] or any(
                member.has_summary() for member in group)
        row["copies"] = len(group)
        # The one row shows the newest title: the others are named in its
        # tooltip, or a copy renamed by hand would vanish from the list.
        titles = list(dict.fromkeys(_title(member) for member in group))
        row["titles"] = titles if len(titles) > 1 else []
        rows.append(row)
    return rows


def _title(entry):
    """An entry's title, its id when the metadata cannot be read."""
    try:
        return str(entry.metadata.get("title") or entry.id)
    except LibraryError:
        return entry.id


def same_recording(copies, first, second):
    """Whether two entry ids are transcriptions of one recording."""
    return first == second or any(
        entry.id == second for entry in copies.get(first, ()))


def _recording(entry, copies):
    """The transcriptions of the recording ``entry`` is one of, newest first,
    read afresh: the ones in ``copies`` are as old as the list, and a summary
    written since would be missing from them."""
    return [entry if other.id == entry.id else Entry(other.path, other.root)
            for other in copies.get(entry.id) or [entry]]


def transcription_choices(entry, copies):
    """The transcriptions of the recording ``entry`` is one of, newest first,
    as ``(id, label)``; empty when it was transcribed once.

    Labelled by date and model, which is what differs between them, and by
    title too when the titles are not all the same: a copy renamed by hand is
    otherwise found nowhere but here."""
    rows = [row for row in (entry_row(other) for other in _recording(entry, copies))
            if row]
    named = len({row["title"] for row in rows}) > 1
    choices = [(row["id"], " · ".join([row["date"], row["model"]]
                                      + ([row["title"]] if named else [])))
               for row in rows]
    return choices if len(choices) > 1 else []


def summary_choices(entry, copies):
    """Every summary of the recording ``entry`` is one of, newest first.

    Each transcription's own and the ones it kept, because a summary written
    from yesterday's transcription is still the latest page about the
    meeting. Each is a dict: the ``entry`` it lives in, its ``file`` (None
    for the current one), a ``label`` for the menu and the ``caption``."""
    names = dict(transcription_choices(entry, copies))
    found = []
    for member in _recording(entry, copies):
        try:
            data = member.metadata
        except LibraryError:
            continue
        pages = [(None, data.get("summary") or {})] if member.read_summary().strip() else []
        pages += [(version["file"], version) for version in member.summary_versions()]
        for file, made in pages:
            caption = summary_caption(made)
            if member.id != entry.id:
                caption += t("gui.summary_from", version=names.get(member.id, member.id))
            found.append({
                "entry": member, "file": file,
                "created_at": made.get("created_at") or "",
                "label": " · ".join(part for part in (
                    (made.get("created_at") or "")[:16].replace("T", " "),
                    made.get("engine") or "") if part) or file or "-",
                "caption": caption,
            })
    # Stable: a page with no date keeps its place after the one that replaced it.
    found.sort(key=lambda choice: choice["created_at"], reverse=True)
    return found


def summary_engine_choices(settings=None):
    """The summary engines this machine can actually run, best first.

    A menu of one is furniture, so the window hides the row when that is all
    there is — which on a server with no accelerator is the usual case. The
    label says what the engine does rather than what it is called: "openvino"
    means nothing to somebody deciding whether to wait for it."""
    return [(name, t(f"gui.summary_engine_{name}")) for name in
            summary_engines_available(settings) if name in SUMMARY_ENGINES]


#: How the model menu names an engine under its heading.
ENGINE_NAMES = {plan.OPENVINO: "OpenVINO", plan.LLAMACPP: "llama.cpp"}

#: The order of the headings: an accelerator first, the processor after it,
#: and the engine with no model last.
WHERE_ORDER = ("GPU", "NPU", "CPU", None)


def summary_where(engine, settings=None):
    """Where this engine would write a summary: GPU, NPU, CPU, or None.

    Asked of the engine the way it decides for itself: OpenVINO's device, and
    for llama.cpp whether its server sees an accelerator - a Vulkan build on
    an Arc does, the binding ``pip`` installs never does."""
    settings = settings or {}
    if engine == plan.OPENVINO:
        from ..summarizers.openvino_genai import resolve_device
        return str(resolve_device(settings.get("summary_device"))).split(".")[0].upper()
    if engine == plan.LLAMACPP:
        from ..summarizers import llamacpp
        binary = llamacpp.server_path(settings)
        return "GPU" if binary and llamacpp.device_for(binary, settings)[0] else "CPU"
    return None


def model_value(engine, model):
    """What the model menu stores for an entry: engine and model, one string."""
    return f"{engine or ''}\t{model or ''}"


def summary_model_menu(settings, engines, free, total, where=summary_where):
    """The model menu: automatic, then every model by where it would run.

    ``[(heading, [(value, label)])]``, the first group without a heading and
    holding only the automatic entry, which says what it would pick now. Each
    model says what it needs, in memory, and whether that fits in what is
    free now; a model that does not fit is still offered, because naming one
    is the person's call. The engine with no model comes last."""
    settings = dict(settings or {})
    usable = plan.usable_ram_gb(free, total)

    def plan_for(engine, model):
        asked = dict(settings, summary_model=model)
        return plan.resolve_plan(engine, asked, ram=free, total=total)

    asked_engine = str(settings.get("summarizer") or "auto").lower()
    first = asked_engine if asked_engine in engines else (engines or [None])[0]
    if first in ENGINE_NAMES:
        now = plan_for(first, "auto")
        picks = now.model.name if now else t("gui.summary_model_nothing_fits")
    else:
        picks = t("gui.summary_model_group_none")
    menu = [(None, [(model_value("", "auto"),
                     t("gui.summary_model_auto", model=picks))])]

    placed = sorted(((where(engine, settings), engine) for engine in engines),
                    key=lambda pair: WHERE_ORDER.index(pair[0])
                    if pair[0] in WHERE_ORDER else 2)
    for device, engine in placed:
        if engine not in ENGINE_NAMES:
            menu.append((t("gui.summary_model_group_none"),
                         [(model_value(engine, ""), t("gui.summary_model_extractive"))]))
            continue
        items = []
        for model in plan.CATALOGUE:
            if not plan.runnable(model, engine):
                continue
            need = plan_for(engine, model.hf_id).est_ram_gb
            if need is None or usable is None:
                label = model.name
            elif need <= usable:
                label = t("gui.summary_model_fits", model=model.name,
                          need=f"{need:.1f}")
            else:
                label = t("gui.summary_model_too_big", model=model.name,
                          need=f"{need:.1f}", usable=f"{usable:.1f}")
            items.append((model_value(engine, model.hf_id), label))
        menu.append((t("gui.summary_model_group", where=device or "CPU",
                       engine=ENGINE_NAMES[engine]), items))
    return menu


def summary_length_choices():
    """How much of the transcript to keep, by name."""
    return [(name, t(f"gui.summary_{name}")) for name in LENGTHS]


def summary_default_length():
    return DEFAULT_LENGTH


def summary_style_choices():
    """How a model engine asks for the four sections, by name."""
    return [(name, t(f"gui.summary_style_{name}")) for name in STYLES]


def summary_default_style():
    return DEFAULT_STYLE


#: What the last entry of the sections menu carries. Not a template name -
#: names are slugs - so it cannot collide with one.
SUMMARY_OWN_TEMPLATE = "__own__"


def summary_template_choices(settings=None, language="it"):
    """Which sections the page can be made of, by name.

    Two of the entries are not files: the empty one, which is the page the
    recording decides for itself, and the last, which is the box underneath.
    A directory that cannot be read is no templates rather than an error -
    the window has to open on a machine where nothing has been set up."""
    from ..summarizers import templates

    settings = settings or {}
    try:
        found = templates.available(settings.get("summary_templates_dir"),
                                    language)
    except Exception:               # noqa: BLE001 - a menu, not the work
        found = []
    choices = [("", t("gui.summary_template_auto"))]
    choices.extend((item.name, item.title) for item in found)
    choices.append((SUMMARY_OWN_TEMPLATE, t("gui.summary_template_mine")))
    return choices


def summary_state(choices, index=0):
    """What the summary tab shows: the page ``choices[index]`` and its caption.

    ``choices`` is :func:`summary_choices`; with none, the caption says so
    rather than leaving an empty box to be puzzled over."""
    if not choices:
        return "", t("gui.summary_none")
    choice = choices[max(0, min(index, len(choices) - 1))]
    entry, file = choice["entry"], choice["file"]
    text = entry.read_summary_version(file) if file else entry.read_summary()
    return text, choice["caption"]


def summary_caption(made):
    """Which engine wrote a summary and when, from what the metadata says.

    The caption is what makes a summary trustworthy or not. A page that does
    not say is a page somebody will quote in a meeting without knowing
    whether a model or a sentence-picker produced it."""
    when = (made.get("created_at") or "")[:16].replace("T", " ")
    caption = t("gui.summary_made_by",
                engine=made.get("engine") or "-", when=when or "-")
    # What was actually read matters as much as who read it: a page written by
    # a one-billion-parameter model from two fifths of the speech is a
    # different thing from one written by a model that read all of it, and
    # somebody about to quote it in a meeting should be able to tell.
    if made.get("tier"):
        caption += t("gui.summary_tier", tier=made["tier"])
    if made.get("caveat"):
        caption += f" — {made['caveat']}"
    return caption


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
    saved = subtitle_summary(entry)
    if saved:
        lines.insert(-1, (t("gui.detail_subtitles"), saved))
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

    A linear bar makes a useless meter: ordinary speech loudness at around a tenth
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
