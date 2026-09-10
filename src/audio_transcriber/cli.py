"""Command-line interface.

``audio-transcriber FILE`` still does the obvious thing; everything else lives
behind a subcommand (``summarize``, ``library``, ``vocab``, ``web``, ``gui``,
``hardware``, ``paths``, ``config``). When the first argument is not a known command it is
taken to be a file, so the original one-argument form keeps working.
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

from . import paths, pipeline
from .config import OUTPUTS, ConfigError, load_config, load_dotenv, resolve
from .formatting import format_duration
from .i18n import AVAILABLE_LANGUAGES, set_language, t
from .library import STORE_COPY, STORE_MODES, Library, LibraryError
from .reference import POOR_MATCH, ReferenceError
from .subtitles import PROBLEM_GROUPS, TIMING_PROBLEMS
from .summarizers import CHOICES as SUMMARY_ENGINES
from .summary import LENGTHS as SUMMARY_LENGTHS
from .transcription import BACKENDS
from .vocabularies import MAX_PROMPT_CHARS, VocabularyError

COMMANDS = ("transcribe", "summarize", "library", "vocab", "web", "gui",
            "hardware", "paths", "config")

CONFIG_TEMPLATE = '''\
# audio-transcriber configuration.
# Every value here is a default: a command-line option always wins.
# Remove or comment out anything you want to leave at its built-in default.

[general]
# Interface language for messages and help: "en" or "it".
# interface_language = "en"
# Spoken language of the recordings; "" auto-detects it.
language = "it"
# What a run is for, and what settles the options below: "text" (just the
# words), "speakers" (who said what) or "subtitles" (cues, saved as .srt).
# Omit it and the individual flags are the whole story.
# output = "text"

[transcription]
# auto | faster-whisper | openvino
backend = "auto"
# auto | CPU | GPU | NPU | CUDA
device = "auto"
# auto | tiny | base | small | medium | large-v3-turbo | large-v3
# "auto" picks the best model this machine can run at a sensible speed:
# see "audio-transcriber hardware".
model = "auto"
# faster-whisper only: int8 | int8_float16 | float16 | float32
# compute_type = "int8"
# CPU threads; omit to use every available core.
# threads = 4
# Filter silence with the VAD. Leave on unless you know why not.
vad = true
# Domain vocabulary, to stop Whisper mangling recurring technical terms.
# Either inline...
# prompt = "asset, control, threat, risk treatment plan"
# ...or from a file, which is easier to maintain:
# prompt_file = "~/.config/audio-transcriber/vocabulary.txt"
# ...or, better, by the name of a keyword set: see "audio-transcriber vocab list".
# Several sets can be combined, comma-separated.
# vocabulary = "iso27001-it"

[output]
# Seconds of pause that start a new paragraph.
paragraph_gap = 1.2
# Maximum characters in one paragraph.
paragraph_max_chars = 600
# Keep the phrases Whisper hallucinates over silence.
keep_fillers = false

[subtitles]
# Subtitles are always available from the library; this is about saving them
# next to the transcript. "srt", "vtt", or "srt,vtt"; omit to save neither.
# save = "srt"
# The numbers to cut them by, as a named set: netflix, bbc, ebu_broadcast,
# fcc_verbatim, social_vertical, social_karaoke, kids_accessible. Your own
# sets go in <config>/srt-presets.json and win over these.
# preset = "netflix"
# Any of the preset's numbers can be overridden on their own:
# max_chars_per_line = 42
# max_lines = 2
# A new subtitle every so many words, if that is how you would rather think
# about it. Not one of the trade's numbers, but honoured when given.
# max_words_per_cue = 12

[summary]
# Who writes the summary of a transcript. "auto" picks the best engine this
# machine has — see "audio-transcriber hardware":
#   openvino    a local model on an Intel iGPU, which writes real prose;
#               needs the [summarize-ov] extra
#   llamacpp    a GGUF on the CPU, for a machine with no accelerator; needs
#               llama-cpp-python or the 'llama-server' binary
#   extractive  no model at all: the sentences that carry the transcript,
#               printed as they were said. Works everywhere, downloads nothing.
engine = "auto"
# How much of the transcript to keep, with the extractive engine:
# short | medium | long.
# length = "medium"
# Which model writes it: "auto" picks the largest recommended one that fits in
# this machine's free memory. Any Hugging Face id works, as does the path of a
# directory already converted to OpenVINO IR.
# model = "Qwen/Qwen3-8B"
# Intel device for the model: auto | CPU | GPU | NPU. "auto" means the iGPU,
# then the CPU. The NPU is skipped on purpose: its LLM pipeline tops out at 8K
# tokens of prompt, and an hour of transcript is nearer fifteen.
# device = "auto"
# Tokens of transcript per pass. Below this the whole thing goes in at once;
# above it, the transcript is read in chunks and the chunks summarised
# together. Left unset, the plan works it out from the model's context.
# chunk_tokens = 6000
# Everything below is worked out from this machine's memory and is here for a
# controlled deployment, or to reproduce somebody else's result. See the plan
# that would be chosen with "audio-transcriber hardware".
# Size class to force: xs | s | m | l.
# tier = "s"
# Context window to give the model. Bigger is not better: the KV cache grows
# with it, and a model reads the middle of a long prompt least faithfully.
# context_tokens = 4096
# Precision of the KV cache, "key/value" or one type for both. The key is
# never taken below q8_0 whatever is written here: a q4 key does not fail
# loudly, it quietly stops being faithful to the transcript.
# kv_type = "q8_0/q4_0"
# How many partial summaries one folding pass may merge. Left unset, as many
# as the model's context can hold.
# reduce_fanin = 6
# Path to the 'llama-server' binary, when it is not on the PATH. With it, the
# llamacpp engine needs no Python packages at all.
# llama_server = "/opt/llama.cpp/llama-server"

[diarization]
# Work out who said what. Needs the [diarize] extra and pyannote models.
enabled = false
# Number of speakers, when known; it improves the result a lot.
# speakers = 3
# HF repo id (online, needs a token) or path to a local config.yaml (offline).
# model = "pyannote/speaker-diarization-3.1"

[paths]
# Override where models, recordings and keyword sets are kept. On a server,
# point these at the volume with the room: an hour of recording is hundreds of
# megabytes, and uploads pass through the cache directory before being filed.
# models = "~/whisper-models"
# library = "~/recordings"
# vocabularies = "~/shared/vocabularies"
# cache = "/mnt/volume/audio-transcriber/cache"
'''


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------

def print_table(rows, headers=None):
    """Left-aligned columns sized to the content; headers are optional."""
    if not rows:
        return
    columns = max(len(row) for row in rows)
    widths = [0] * columns
    for row in ([headers] if headers else []) + list(rows):
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    if headers:
        print("  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)).rstrip())
        print("  ".join("-" * widths[i] for i in range(columns)))
    for row in rows:
        print("  ".join(str(cell).ljust(widths[i])
                        for i, cell in enumerate(row)).rstrip())


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------

def preparse_language(argv):
    """Read --lang before argparse runs, so even the help text is translated."""
    for index, token in enumerate(argv):
        if token == "--lang" and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith("--lang="):
            return token.split("=", 1)[1]
    return None


def insert_default_command(argv):
    """Treat a leading non-command argument as a file to transcribe."""
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in ("-h", "--help", "--version"):
            return argv
        if token == "--lang":
            index += 2
            continue
        if token.startswith("--lang="):
            index += 1
            continue
        break
    if index >= len(argv) or argv[index] in COMMANDS:
        return argv
    return argv[:index] + ["transcribe"] + argv[index:]


def add_language_option(parser):
    parser.add_argument("--lang", default=None, choices=list(AVAILABLE_LANGUAGES),
                        help=t("help.lang", choices="|".join(AVAILABLE_LANGUAGES)))


def build_parser(defaults):
    """Build the parser, showing the defaults actually in effect."""
    from . import __version__

    parser = argparse.ArgumentParser(
        prog="audio-transcriber",
        description=t("cli.description"),
        epilog=t("help.epilog"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_language_option(parser)
    parser.add_argument("--version", action="version",
                        version=f"audio-transcriber {__version__}",
                        help=t("help.version"))
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND",
                                       help=t("help.command"))

    # --- transcribe -------------------------------------------------------
    tr = subparsers.add_parser("transcribe", help=t("help.cmd_transcribe"),
                               description=t("help.cmd_transcribe"))
    add_language_option(tr)
    tr.add_argument("input", help=t("help.input"))
    tr.add_argument("--out", default=None, help=t("help.out"))
    tr.add_argument("--model", default=None,
                    help=t("help.model", default=defaults["model"]))
    tr.add_argument("--language", default=None,
                    help=t("help.language", default=defaults["language"]))
    tr.add_argument("--backend", default=None, choices=list(BACKENDS),
                    help=t("help.backend"))
    tr.add_argument("--device", default=None, help=t("help.device"))
    tr.add_argument("--compute-type", dest="compute_type", default=None,
                    help=t("help.compute_type"))
    tr.add_argument("--threads", type=int, default=None, help=t("help.threads"))
    tr.add_argument("--no-vad", dest="no_vad", action="store_true", default=None,
                    help=t("help.no_vad"))
    tr.add_argument("--model-dir", dest="models_dir", default=None,
                    help=t("help.model_dir"))
    tr.add_argument("--prompt", default=None, help=t("help.prompt"))
    tr.add_argument("--prompt-file", dest="prompt_file", default=None,
                    help=t("help.prompt_file"))
    tr.add_argument("--vocab", dest="vocabulary", action="append", default=None,
                    metavar="NAME", help=t("help.vocab"))
    tr.add_argument("--para-gap", dest="para_gap", type=float, default=None,
                    help=t("help.para_gap"))
    tr.add_argument("--para-max-chars", dest="para_max_chars", type=int, default=None,
                    help=t("help.para_max_chars"))
    tr.add_argument("--keep-fillers", dest="keep_fillers", action="store_true",
                    default=None, help=t("help.keep_fillers"))
    # The choice the two graphical front ends ask first; here it is one
    # option that settles the others, so a command line can say what it is
    # for instead of listing the flags that add up to it.
    tr.add_argument("--output", default=None, choices=list(OUTPUTS),
                    help=t("help.output"))
    tr.add_argument("--diarize", action="store_true", default=None,
                    help=t("help.diarize"))
    tr.add_argument("--speakers", type=int, default=None, help=t("help.speakers"))
    tr.add_argument("--hf-token", dest="hf_token", default=None, help=t("help.hf_token"))
    tr.add_argument("--diar-model", dest="diar_model", default=None,
                    help=t("help.diar_model"))
    tr.add_argument("--library", action="store_true", help=t("help.library"))
    tr.add_argument("--library-store", dest="library_store", default=STORE_COPY,
                    choices=list(STORE_MODES), help=t("help.library_store"))
    tr.add_argument("--library-dir", dest="library_dir", default=None,
                    help=t("help.lib_root"))
    tr.add_argument("--title", default=None, help=t("help.title"))
    tr.add_argument("--json", dest="json_out", default=None, help=t("help.json"))
    tr.add_argument("--srt", action="store_true", default=None, help=t("help.srt"))
    tr.add_argument("--vtt", action="store_true", default=None, help=t("help.vtt"))
    tr.add_argument("--subtitle-preset", dest="subtitle_preset", default=None,
                    metavar="NAME", help=t("help.subtitle_preset"))
    tr.add_argument("--subtitle-chars", dest="subtitle_chars", type=int,
                    default=None, metavar="N", help=t("help.subtitle_chars"))
    tr.add_argument("--subtitle-lines", dest="subtitle_lines", type=int,
                    default=None, metavar="N", help=t("help.subtitle_lines"))
    tr.add_argument("--subtitle-words", dest="subtitle_words", type=int,
                    default=None, metavar="N", help=t("help.subtitle_words"))
    # A text you already have for this recording: it helps the engine spell
    # and then proof-reads what it heard. See audio_transcriber/reference.py.
    tr.add_argument("--reference", dest="reference_file", default=None,
                    metavar="FILE", help=t("help.reference"))

    # --- summarize --------------------------------------------------------
    sm = subparsers.add_parser("summarize", help=t("help.cmd_summarize"),
                               description=t("help.cmd_summarize"))
    add_language_option(sm)
    sm.add_argument("query", help=t("help.sum_query"))
    sm.add_argument("--engine", dest="summarizer", default=None,
                    choices=list(SUMMARY_ENGINES), help=t("help.sum_engine"))
    sm.add_argument("--length", dest="summary_length", default=None,
                    choices=list(SUMMARY_LENGTHS), help=t("help.sum_length"))
    sm.add_argument("--model", dest="summary_model", default=None,
                    help=t("help.sum_model"))
    sm.add_argument("--device", dest="summary_device", default=None,
                    help=t("help.sum_device"))
    sm.add_argument("--context-tokens", dest="summary_context_tokens", type=int,
                    default=None, metavar="N", help=t("help.sum_context"))
    sm.add_argument("--kv-type", dest="summary_kv_type", default=None,
                    metavar="TYPE", help=t("help.sum_kv"))
    sm.add_argument("--tier", dest="summary_tier", default=None,
                    metavar="TIER", help=t("help.sum_tier"))
    sm.add_argument("--out", dest="out", default=None, help=t("help.sum_out"))
    sm.add_argument("--print", dest="show", action="store_true",
                    help=t("help.sum_print"))
    sm.add_argument("--library-dir", dest="library_dir", default=None,
                    help=t("help.lib_root"))

    # --- library ----------------------------------------------------------
    lib = subparsers.add_parser("library", help=t("help.cmd_library"),
                                description=t("help.cmd_library"))
    add_language_option(lib)
    lib.add_argument("--library-dir", dest="library_dir", default=None,
                     help=t("help.lib_root"))
    lib_sub = lib.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    lib_sub.add_parser("list", help=t("help.lib_list"))
    show = lib_sub.add_parser("show", help=t("help.lib_show"))
    show.add_argument("query", help=t("help.lib_query"))
    search = lib_sub.add_parser("search", help=t("help.lib_search"))
    search.add_argument("text", help=t("help.lib_text"))
    remove = lib_sub.add_parser("remove", help=t("help.lib_remove"))
    remove.add_argument("query", help=t("help.lib_query"))
    remove.add_argument("-y", "--yes", action="store_true", help=t("help.lib_yes"))
    entry_path = lib_sub.add_parser("path", help=t("help.lib_path"))
    entry_path.add_argument("query", nargs="?", help=t("help.lib_query"))

    # --- vocab ------------------------------------------------------------
    voc = subparsers.add_parser("vocab", help=t("help.cmd_vocab"),
                                description=t("help.cmd_vocab"))
    add_language_option(voc)
    voc.add_argument("--vocab-dir", dest="vocab_dir", default=None,
                     help=t("help.vocab_dir"))
    voc_sub = voc.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    voc_sub.add_parser("list", help=t("help.vocab_list"))
    voc_show = voc_sub.add_parser("show", help=t("help.vocab_show"))
    voc_show.add_argument("name", help=t("help.vocab_name"))
    voc_path = voc_sub.add_parser("path", help=t("help.vocab_path"))
    voc_path.add_argument("name", nargs="?", help=t("help.vocab_name"))
    voc_new = voc_sub.add_parser("new", help=t("help.vocab_new"))
    voc_new.add_argument("name", help=t("help.vocab_name"))
    voc_new.add_argument("--title", default=None, help=t("help.vocab_title"))
    voc_new.add_argument("--language", default="", help=t("help.vocab_language"))
    voc_new.add_argument("--from", dest="source_file", default=None,
                         help=t("help.vocab_from"))
    voc_new.add_argument("--force", action="store_true", help=t("help.vocab_force"))

    # --- web ---------------------------------------------------------------
    web = subparsers.add_parser("web", help=t("help.cmd_web"),
                                description=t("help.cmd_web"))
    add_language_option(web)
    web.add_argument("--host", default="127.0.0.1", help=t("help.web_host"))
    web.add_argument("--port", type=int, default=8765, help=t("help.web_port"))
    web.add_argument("--root-path", dest="root_path", default="",
                     help=t("help.web_root_path"))
    web.add_argument("--library-dir", dest="library_dir", default=None,
                     help=t("help.lib_root"))

    # --- gui ---------------------------------------------------------------
    gui = subparsers.add_parser("gui", help=t("help.cmd_gui"),
                                description=t("help.cmd_gui"))
    add_language_option(gui)
    gui.add_argument("--library-dir", dest="library_dir", default=None,
                     help=t("help.lib_root"))

    # --- hardware, paths, config -----------------------------------------
    hw = subparsers.add_parser("hardware", help=t("help.cmd_hardware"),
                               description=t("help.cmd_hardware"))
    add_language_option(hw)
    hw.add_argument("--device", default=None, help=t("help.device"))

    pt = subparsers.add_parser("paths", help=t("help.cmd_paths"),
                               description=t("help.cmd_paths"))
    add_language_option(pt)

    cfg = subparsers.add_parser("config", help=t("help.cmd_config"),
                                description=t("help.cmd_config"))
    add_language_option(cfg)
    cfg_sub = cfg.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    cfg_sub.add_parser("show", help=t("help.cfg_show"))
    cfg_sub.add_parser("path", help=t("help.cfg_path"))
    init = cfg_sub.add_parser("init", help=t("help.cfg_init"))
    init.add_argument("--force", action="store_true", help=t("help.cfg_force"))

    return parser


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def command_transcribe(args, settings):
    """Transcribe one file and write the result where it was asked for."""
    source = os.path.abspath(os.path.expanduser(args.input))
    if not os.path.exists(source):
        sys.exit(t("cli.file_not_found", path=source))

    try:
        prompt = pipeline.resolve_prompt(settings)
    except ConfigError as exc:
        sys.exit(str(exc))
    if len(prompt) > MAX_PROMPT_CHARS:
        print(t("vocab.prompt_too_long", chars=len(prompt), limit=MAX_PROMPT_CHARS),
              file=sys.stderr)

    try:
        result = pipeline.run(source, settings, prompt=prompt)
    except pipeline.EmptyTranscription as exc:
        sys.exit(str(exc))
    except ReferenceError as exc:
        sys.exit(str(exc))
    if settings["diarize"] and not result.diarized:
        print(t("diarize.no_turns"))
    if result.reference:
        report_reference(result.reference)

    written = write_result(args, settings, source, result)

    print(t("cli.done", path=written))
    summary = t("cli.summary", words=len(result.text.split()),
                backend=result.info["backend"], device=result.info["device"],
                language=settings["language"] or "auto")
    if result.diarized:
        summary += t("cli.summary_diarized")
    print(summary)
    speed = (t("cli.speed_realtime", factor=result.audio_duration / result.elapsed)
             if result.elapsed > 0 and result.audio_duration
             else t("cli.speed_unknown"))
    print(t("cli.elapsed", elapsed=format_duration(result.elapsed), speed=speed))


def report_reference(report):
    """Say what the given text corrected, and how much of it was said at all.

    Two numbers, and the second is the one that catches a mistake: a text of
    another recording corrects almost nothing, and without saying how much of
    it turned up in the audio, "corrected 3 words" reads like a success."""
    print(t("reference.corrected", corrected=report["corrected"],
            heard=report["heard"]))
    percent = round(report["coverage"] * 100)
    if report["coverage"] < POOR_MATCH:
        print(t("reference.poor", percent=percent), file=sys.stderr)
    else:
        print(t("reference.matched", percent=percent))


def write_subtitle_files(settings, target_stem, result):
    """Write the subtitle files beside the transcript, and say what happened.

    Only for a run that is not going into the library: an entry gets them from
    :func:`pipeline.file_in_library`, next to everything else it holds."""
    kinds = pipeline.subtitle_formats(settings)
    if not kinds:
        return
    spec = pipeline.subtitle_spec(settings)
    cue_list = pipeline.subtitles_of(result, settings)
    for kind in kinds:
        text = (pipeline.to_srt(cue_list, spec.get("line_ending", "\n"))
                if kind == "srt" else pipeline.to_vtt(cue_list))
        path = f"{target_stem}.{kind}"
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        print(t("cli.subtitles_written", path=path, cues=len(cue_list)))
    report_subtitle_problems(
        pipeline.tally(pipeline.validate(cue_list, spec)), spec,
        measured=pipeline.timings_measured(result.segments))


def report_subtitle_problems(counts, spec, measured=True):
    """Say what a subtitler would object to, grouped by who can do anything.

    Nothing is fixed silently: the guidance's own remedy for speech too fast
    to read is to shorten the text, and shortening someone's words is not a
    decision this program makes. But "41 remarks" on its own says nothing
    about which of them are worth acting on, so they are split three ways —
    the speech, the engine's clock, this program's own layout — and where the
    clock was interpolated rather than measured, that is said outright,
    because half these remarks then rest on times nobody ever measured."""
    if not counts:
        return
    print(t("cli.subtitles_problems", preset=spec.get("name", "-"),
            total=sum(counts.values())), file=sys.stderr)
    reported = set()
    for heading, keys in PROBLEM_GROUPS:
        group = {key: count for key, count in counts.items() if key in keys}
        if not group:
            continue
        print(t(heading), file=sys.stderr)
        for key, count in sorted(group.items()):
            print(f"      {t(key)} x{count}", file=sys.stderr)
        reported.update(group)
    for key, count in sorted(counts.items()):
        if key not in reported:         # a kind added without a group
            print(f"      {t(key)} x{count}", file=sys.stderr)
    if not measured and any(key in TIMING_PROBLEMS for key in counts):
        print(t("cli.subtitles_interpolated"), file=sys.stderr)


def write_result(args, settings, source, result):
    """Store the transcript, in the library or beside the input, and return
    the path a human should look at."""
    if args.json_out:
        import json
        target = os.path.abspath(os.path.expanduser(args.json_out))
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"schema": 1, "segments": result.segments}, handle,
                      ensure_ascii=False, indent=2)
            handle.write("\n")

    if not args.library:
        out = (os.path.abspath(os.path.expanduser(args.out)) if args.out
               else os.path.splitext(source)[0] + ".txt")
        with open(out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(result.text)
        write_subtitle_files(settings, os.path.splitext(out)[0], result)
        return out

    library = Library(settings["library_dir"])
    try:
        entry = pipeline.file_in_library(library, source, result, settings,
                                         title=args.title, store=args.library_store)
    except LibraryError as exc:
        sys.exit(str(exc))

    print(t("library.created", path=entry.path))
    recorded = entry.metadata.get("subtitles") or {}
    for kind in entry.subtitles():
        print(t("cli.subtitles_written", path=entry.subtitle_path(kind),
                cues=recorded.get("cues", 0)))
    if entry.subtitles():
        report_subtitle_problems(recorded.get("remarks") or {},
                                 pipeline.subtitle_spec(settings),
                                 measured=recorded.get("timings") != "interpolated")
    if args.out:
        out = os.path.abspath(os.path.expanduser(args.out))
        with open(out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(result.text)
        return out
    return entry.transcript_path


def command_summarize(args, settings):
    """Summarise a transcript — one already in the library, or a bare file.

    Both are worth supporting for the same reason ``transcribe`` takes a path:
    the library is where recordings made with this program live, but a
    transcript that arrived by other means is still a transcript."""
    from . import summary as summarising
    from .library import Library

    source = os.path.abspath(os.path.expanduser(args.query))
    entry = None
    if os.path.isfile(source):
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        material = summarising.material_from_text(
            text, title=os.path.splitext(os.path.basename(source))[0],
            language=settings.get("language") or "")
    else:
        try:
            entry = Library(settings.get("library_dir")).get(args.query)
        except LibraryError as exc:
            sys.exit(str(exc))
        material = summarising.material_from_entry(entry)

    try:
        result = summarising.summarize(material, settings)
    except summarising.SummaryError as exc:
        sys.exit(str(exc))

    if args.show:
        print(result.text, end="")
    elif args.out:
        target = os.path.abspath(os.path.expanduser(args.out))
        paths.ensure(os.path.dirname(target))
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(result.text)
        print(t("summary.written", path=target))
    elif entry is not None:
        entry.write_summary(result.text)
        entry.update(summary={
            "engine": result.engine,
            "length": settings.get("summary_length") or summarising.DEFAULT_LENGTH,
            "sentences_kept": result.kept,
            "sentences_total": result.of,
            "tier": result.tier,
            "caveat": result.note,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        print(t("summary.written", path=entry.summary_path))
    else:
        target = os.path.splitext(source)[0] + ".summary.md"
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(result.text)
        print(t("summary.written", path=target))

    print(t("summary.stats", kept=result.kept, of=result.of,
            engine=result.engine, elapsed=result.elapsed), file=sys.stderr)


def command_library(args):
    """Browse the library."""
    library = Library(args.library_dir)
    subcommand = getattr(args, "subcommand", None) or "list"

    if subcommand == "path" and not getattr(args, "query", None):
        print(library.root)
        return

    if subcommand == "list":
        entries = library.entries()
        if not entries:
            print(t("library.empty", path=library.root))
            return
        rows = []
        for entry in entries:
            try:
                data = entry.metadata
            except LibraryError:
                print(t("library.corrupt_metadata", path=entry.path), file=sys.stderr)
                continue
            audio = data.get("audio") or {}
            stats = data.get("stats") or {}
            rows.append([
                entry.id,
                (data.get("created_at") or "")[:10],
                format_duration(audio.get("duration_seconds")),
                stats.get("words", "-"),
                data.get("title", ""),
            ])
        print_table(rows, headers=[
            t("library.header_id"), t("library.header_date"),
            t("library.header_duration"), t("library.header_words"),
            t("library.header_title")])
        return

    if subcommand == "search":
        matches = library.search(args.text)
        if not matches:
            print(t("library.no_match", query=args.text))
            return
        for entry in matches:
            print(f"{entry.id}  {entry.metadata.get('title', '')}")
        return

    try:
        entry = library.get(args.query)
    except LibraryError as exc:
        sys.exit(str(exc))

    if subcommand == "path":
        print(entry.path)
    elif subcommand == "show":
        data = entry.metadata
        audio = data.get("audio") or {}
        transcription = data.get("transcription") or {}
        print(f"{data.get('title', entry.id)}  [{entry.id}]")
        print(f"  {data.get('created_at', '')}"
              f"  {format_duration(audio.get('duration_seconds'))}"
              f"  {transcription.get('model', '')}"
              f"  {transcription.get('backend', '')}")
        print(f"  {entry.path}")
        print()
        print(entry.read_transcript().rstrip())
    elif subcommand == "remove":
        if not args.yes:
            answer = input(f"{entry.path}\nremove? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                return
        print(t("library.removed", path=library.remove(entry)))


def command_vocab(args, settings):
    """List, inspect or create the named keyword sets."""
    from . import vocabularies

    extra = getattr(args, "vocab_dir", None) or settings.get("vocab_dir")
    subcommand = getattr(args, "subcommand", None) or "list"

    if subcommand == "path" and not getattr(args, "name", None):
        print(vocabularies.user_dir())
        return

    if subcommand == "list":
        sets = vocabularies.available(extra)
        if not sets:
            print(t("vocab.none", path=vocabularies.user_dir()))
            return
        rows = [[item.name, item.source, item.language or "-",
                 len(vocabularies.terms(item.text)), item.title]
                for item in sets]
        print_table(rows, headers=[
            t("vocab.header_name"), t("vocab.header_source"),
            t("vocab.header_language"), t("vocab.header_terms"),
            t("vocab.header_title")])
        return

    if subcommand == "new":
        text = template_or_file(args)
        try:
            path = vocabularies.create(args.name, text, overwrite=args.force)
        except VocabularyError as exc:
            sys.exit(str(exc))
        print(t("vocab.created", path=path))
        return

    try:
        item = vocabularies.get(args.name, extra)
    except VocabularyError as exc:
        sys.exit(str(exc))

    if subcommand == "path":
        print(item.path)
        return

    print(f"{item.title}  [{item.name}]")
    print("  " + t("vocab.show_stats", source=item.source,
                   language=item.language or "-",
                   terms=len(vocabularies.terms(item.text)),
                   chars=len(item.text)))
    print(f"  {item.path}")
    print()
    print(item.text)


def template_or_file(args):
    """Body of a new vocabulary: an existing file, or the empty template."""
    from . import vocabularies

    if not args.source_file:
        return vocabularies.template(args.name, args.title, args.language)
    source = os.path.abspath(os.path.expanduser(args.source_file))
    try:
        with open(source, encoding="utf-8") as handle:
            body = handle.read()
    except OSError as exc:
        sys.exit(f"--from: {exc}")
    if vocabularies.metadata(body).get("title"):
        return body
    return vocabularies.template(args.name, args.title, args.language) + body


def command_web(args, settings):
    """Serve the local web interface."""
    from .web import run

    print(t("web.starting", host=args.host, port=args.port))
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(t("web.exposed"))
    return run(args.host, args.port, settings, root_path=args.root_path)


def command_gui(settings):
    """Open the desktop window."""
    from .gui import run

    return run(settings)


def command_hardware(args):
    """Report what the machine can do, and what it would choose.

    Returns 1 when this installation cannot transcribe at all, so a script can
    tell, but it always prints the whole report first."""
    from .backends import resolve_backend
    from .diarization import NO_MODEL, NOT_INSTALLED, availability
    from .hardware import summary
    from .summary import SummaryError
    from .transcription import recommend_model

    print(summary())
    device = args.device or "auto"
    try:
        backend = resolve_backend("auto", device)
    except SystemExit as exc:
        # This is the command people run *because* something is missing, so an
        # absent engine belongs in the report rather than in place of it:
        # exiting here would hide the hardware summary and the diarization
        # state, which are exactly what they came for.
        print(exc)
        backend = None
    if backend:
        print(t("hardware.auto_backend", backend=backend))
        print(t("hardware.auto_model", model=recommend_model(backend, device)))

    try:
        from .summarizers import resolve_summarizer
        engine = resolve_summarizer("auto")
        print(t("summary.auto_engine", engine=engine))
        print(_summary_plan_line(engine))
    except SummaryError as exc:
        print(exc)

    state, detail = availability()
    print(t({NOT_INSTALLED: "hardware.diarize_missing",
             NO_MODEL: "hardware.diarize_unconfigured"}.get(state, "hardware.diarize_ready"),
            detail=detail))
    return 0 if backend else 1


def _summary_plan_line(engine):
    """What the summary engine would load here, and what it would take.

    The policy that decides between a written page and a quoted one lives in
    arithmetic nobody can see; this is where it is made to say so out loud,
    and it is worth more than any amount of documentation about it."""
    from .summarizers import plan as planning

    # With no model engine installed the question is still worth answering:
    # "would a model fit here if I installed one" is exactly what somebody
    # reading this report wants to know before installing one.
    engine = engine if engine in (planning.OPENVINO,
                                  planning.LLAMACPP) else planning.LLAMACPP
    chosen = planning.resolve_plan(engine, {})
    if chosen is None:
        needed = planning.cheapest(engine)
        return t("summary.plan_none",
                 needed="?" if needed is None else f"{needed:.1f}")
    return t("summary.plan_line", tier=chosen.tier, model=chosen.model.name,
             quant=chosen.quant or "-", context=chosen.context_tokens,
             kv=f"{chosen.kv_k}/{chosen.kv_v}",
             ram="?" if chosen.est_ram_gb is None else f"{chosen.est_ram_gb:.1f}")


def command_paths(settings=None):
    """Report where files are kept, configuration included."""
    print(t("cli.paths_header"))
    rows = []
    for label, path, exists, configured in paths.describe(settings):
        note = "" if exists else t("cli.paths_missing")
        if configured:
            note = (note + " " if note else "") + t("cli.paths_configured")
        rows.append((label, path, note))
    print_table(rows)


def command_config(args, settings, config_path):
    """Inspect or create the configuration file."""
    subcommand = getattr(args, "subcommand", None) or "show"
    if subcommand == "path":
        print(paths.config_file())
        return
    if subcommand == "init":
        target = paths.config_file()
        if os.path.exists(target) and not args.force:
            sys.exit(f"{target} already exists (use --force to overwrite)")
        paths.ensure(os.path.dirname(target))
        if os.path.exists(target):
            shutil.copy2(target, target + ".bak")
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(CONFIG_TEMPLATE)
        print(target)
        return
    if config_path:
        print(t("cli.config_loaded", path=config_path))
    for key in sorted(settings):
        value = settings[key]
        print(f"  {key:20} {'' if value is None else value}")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def main(argv=None):
    # With output redirected to a file stdout would be block-buffered and the
    # progress messages, which go to stderr, would appear out of order.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    argv = list(sys.argv[1:] if argv is None else argv)
    set_language(preparse_language(argv))
    load_dotenv()

    # A broken config.toml must not block the commands that inspect or repair
    # it, so the error is carried and only raised where the settings matter.
    config_error = None
    try:
        file_settings, config_path, warnings = load_config()
    except ConfigError as exc:
        file_settings, config_path, warnings = {}, None, []
        config_error = t("cli.config_invalid", path=paths.config_file(), error=exc)
    for warning in warnings:
        print(f"  {warning}", file=sys.stderr)

    display_defaults = resolve({}, file_settings)
    parser = build_parser(display_defaults)
    if not argv:
        parser.print_help(sys.stderr)
        return 1

    args = parser.parse_args(insert_default_command(argv))
    if getattr(args, "lang", None):
        set_language(args.lang)

    command = args.command or "transcribe"
    if config_error:
        if command in ("transcribe", "library"):
            sys.exit(config_error)
        print(config_error, file=sys.stderr)

    if command == "hardware":
        return command_hardware(args)

    settings = resolve(collect_cli_settings(args), file_settings)
    if command == "paths":
        return command_paths(settings)
    if command == "vocab":
        return command_vocab(args, settings)
    if command == "web":
        return command_web(args, settings)
    if command == "gui":
        return command_gui(settings)
    if command == "config":
        return command_config(args, settings, config_path)
    if command == "library":
        return command_library(args)
    if command == "summarize":
        return command_summarize(args, settings)
    return command_transcribe(args, settings)


def collect_cli_settings(args):
    """Pull the configurable options out of the parsed arguments.

    Absent options are None so they never override the configuration file;
    ``--no-vad`` is the one flag that has to be inverted."""
    names = ("language", "backend", "device", "model", "compute_type", "threads",
             "prompt", "prompt_file", "vocabulary", "para_gap", "para_max_chars",
             "keep_fillers", "diarize", "speakers", "diar_model", "models_dir",
             "library_dir", "vocab_dir", "subtitle_preset", "subtitle_chars",
             "subtitle_lines", "subtitle_words", "output", "summarizer",
             "summary_length", "summary_model", "summary_device",
             "summary_chunk_tokens", "summary_context_tokens",
             "summary_kv_type", "summary_tier", "summary_llama_server")
    values = {name: getattr(args, name, None) for name in names}
    # --srt and --vtt are flags; together they are the "save these formats"
    # setting, and neither given means the configured value stands.
    asked = [kind for kind in ("srt", "vtt") if getattr(args, kind, None)]
    values["subtitles"] = ",".join(asked) if asked else None
    values["vad"] = False if getattr(args, "no_vad", None) else None
    values["hf_token"] = getattr(args, "hf_token", None)
    return values


if __name__ == "__main__":
    sys.exit(main() or 0)
