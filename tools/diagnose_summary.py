"""Run one summary with everything switched on, and write down what it cost.

This exists for one bug. A summary of a twenty-two minute meeting came back
describing the first seven, and every step of it had succeeded: the reading
read every chunk, the fold folded every group, the root wrote a well-formed
page. The material went missing between them, through fallbacks that put
something plausible where something absent should have been and said nothing.

The machinery to see that is in the program now — coverage measured twice,
a line per reading pass and per fold, a count of what each fallback swallowed.
What is not here is the machine that reproduces the bug: it needs an Intel
device and a model this program will not load on a server with a gigabyte
free. So this script is the whole diagnosis in one command, run by whoever has
that machine.

It writes **two** files, and the split is the point:

``<name>.numbers.json``
    the plan, the timings, every pass, every fold, and the metrics. Numbers
    and status words only — no sentence of the recording, no line of the
    summary. This is the one to send on.
``<name>.page.md``
    the summary the run produced, and the transcript's own length. This is
    meeting content: keep it where the transcript is kept.

    python tools/diagnose_summary.py path\\to\\gold.srt
    python tools/diagnose_summary.py gold.srt --out C:\\work\\diagnosi
    python tools/diagnose_summary.py gold.srt --engine openvino --style split
    python tools/diagnose_summary.py gold.srt --keep-cache      # don't clear it
"""
import argparse
import io
import json
import os
import platform
import sys
import time
from contextlib import redirect_stderr
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "src"
if (SOURCE / "audio_transcriber").is_dir():      # running from a checkout
    sys.path.insert(0, str(SOURCE))

from audio_transcriber import summary as summarising  # noqa: E402
from audio_transcriber.summarizers import (  # noqa: E402
    ENGINES,
    EXTRACTIVE,
    is_installed,
    partials,
    plan,
    prompting,
    resolve_summarizer,
)
from audio_transcriber.summarizers import trace as tracing  # noqa: E402


class Tee(io.StringIO):
    """Keep every line, and let the person watching see it go past."""

    def __init__(self, mirror):
        super().__init__()
        self._mirror = mirror

    def write(self, text):
        self._mirror.write(text)
        self._mirror.flush()
        return super().write(text)


def machine():
    """What this was run on, which decides which model the plan picks."""
    found = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor(),
    }
    try:
        import psutil

        memory = psutil.virtual_memory()
        found["ram_total_gb"] = round(memory.total / 1024 ** 3, 1)
        found["ram_available_gb"] = round(memory.available / 1024 ** 3, 1)
    except Exception:                       # noqa: BLE001 - a nice-to-have
        found["ram_total_gb"] = found["ram_available_gb"] = None
    return found


def why_missing(name):
    """What stopped an engine from counting as installed, in one line.

    "Not available" is the answer that wastes an afternoon. An import that
    fails because a package is absent and one that fails because a DLL was
    found in the wrong order are the same sentence here and nothing alike on
    the disk."""
    if name != "openvino":
        return None
    try:
        import openvino_genai  # noqa: F401
    except BaseException as refused:                     # noqa: BLE001
        return f"{type(refused).__name__}: {refused}"
    return None


def engines_here(settings):
    """Which engines this machine could run, and why the others could not."""
    found = {}
    for name in ENGINES:
        if is_installed(name, settings):
            found[name] = "installed"
        else:
            found[name] = why_missing(name) or "not installed"
    return found


def chosen_plan(engine, settings):
    """The model, the context and the passes the plan settled on.

    Written down because every number below is only readable next to it: four
    chunks and eleven chunks are different runs of the same recording, and the
    fold behaves differently in each."""
    try:
        chosen = plan.resolve_plan(engine, settings)
    except Exception as refused:            # noqa: BLE001 - reported, not raised
        return {"error": f"{type(refused).__name__}: {refused}"}
    if chosen is None:
        # Nothing in the catalogue fits this machine. Everything below will be
        # the extractive engine quoting, and the numbers mean something else.
        return {"error": "no model fits this machine: nothing was planned"}
    return {
        "model": getattr(getattr(chosen, "model", None), "name", None),
        "quant": getattr(chosen, "quant", None),
        "tier": getattr(chosen, "tier", None),
        "context_tokens": getattr(chosen, "context_tokens", None),
        "chunk_tokens": getattr(chosen, "chunk_tokens", None),
        "chunk_overlap": getattr(chosen, "chunk_overlap", None),
        "max_passes": getattr(chosen, "max_passes", None),
        "prereduce": getattr(chosen, "prereduce", None),
        "map_answer_tokens": getattr(chosen, "map_answer_tokens", None),
        "reduce_answer_tokens": getattr(chosen, "reduce_answer_tokens", None),
        "estimated_ram_gb": getattr(chosen, "estimate", None),
    }


def read_material(path, language):
    """The transcript, as cues when it is cues and as prose when it is not."""
    text = Path(path).read_text(encoding="utf-8")
    title = Path(path).stem
    if summarising.looks_like_subtitles(text):
        return summarising.material_from_subtitles(text, title, language), "cues"
    return summarising.material_from_text(text, title, language), "prose"


def clear_cache(settings):
    """Throw away the partial answers of previous runs.

    Not politeness: a run that went wrong is filed under the same key as one
    that did not, and comes back looking like a fresh pass. Every comparison
    between two attempts starts here."""
    directory = partials.directory(settings.get("cache_dir"))
    removed = 0
    try:
        for name in os.listdir(directory):
            try:
                os.unlink(os.path.join(directory, name))
                removed += 1
            except OSError:
                pass
    except OSError:
        return None
    return removed


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("transcript",
                        help="the .srt, .vtt or .txt to summarise")
    parser.add_argument("--out", default=None, metavar="PREFIX",
                        help="where the two files go (default: beside the "
                             "transcript, named after it)")
    parser.add_argument("--engine", default=None,
                        help="openvino | llamacpp | extractive (default: auto)")
    parser.add_argument("--style", default=None, choices=["combined", "split"],
                        help="how the last page is asked for")
    parser.add_argument("--length", default=None,
                        help="short | medium | long")
    parser.add_argument("--language", default="it")
    parser.add_argument("--context-tokens", type=int, default=None,
                        help="override the plan's context window")
    parser.add_argument("--keep-cache", action="store_true",
                        help="do not clear the partial answers first")
    args = parser.parse_args(argv)

    source = Path(args.transcript).expanduser().resolve()
    if not source.is_file():
        sys.exit(f"no such file: {source}")
    prefix = Path(args.out).expanduser() if args.out else source.with_suffix("")
    prefix.parent.mkdir(parents=True, exist_ok=True)

    settings = {
        "summary_debug": True,
        "summary_dump_notes": str(prefix) + ".passes.json",
        "summarizer": args.engine,
        "summary_style": args.style,
        "summary_length": args.length,
        "summary_context_tokens": args.context_tokens,
        "language": args.language,
    }
    settings = {name: value for name, value in settings.items()
                if value is not None}

    material, shape = read_material(source, args.language)
    if not material.sentences:
        sys.exit(f"nothing to summarise in {source}")
    if shape == "prose":
        print("! read as prose: no minutes, so coverage cannot be measured.",
              file=sys.stderr)

    engine_name = resolve_summarizer(args.engine)
    installed = engines_here(settings)

    # The whole point of this script is the engine that reads in passes. It
    # has quietly done the other one once already, on a machine where the
    # model was one conda environment away, and printed a page of numbers
    # about a run nobody wanted. Not again.
    the_plan = ({"error": "the extractive engine loads no model"}
                if engine_name == EXTRACTIVE
                else chosen_plan(engine_name, settings))

    # The whole point of this script is the engine that reads in passes. It
    # has quietly done the other one once already, on a machine where the
    # model was one conda environment away, and printed a page of numbers
    # about a run nobody wanted. Not again.
    if args.engine is None and (engine_name == EXTRACTIVE
                                or the_plan.get("error")):
        if engine_name == EXTRACTIVE:
            print("\nThe extractive engine is the only one this environment "
                  "has, and it reads in\none pass: no chunks, no folds, "
                  "nothing to diagnose.", file=sys.stderr)
        else:
            print(f"\n{engine_name} is installed but no model will load here:"
                  f"\n    {the_plan['error']}\nThe run would quietly fall "
                  "back to quoting sentences, which is not what this\nscript "
                  "measures.", file=sys.stderr)
        print("\nWhat each engine said:", file=sys.stderr)
        for name, state in installed.items():
            print(f"    {name:<12} {state}", file=sys.stderr)
        print("\nOn Windows this is nearly always the wrong environment: "
              "conda's base has no\nopenvino-genai. Activate the one the "
              "project was installed into and try again.\n"
              "\n    --engine extractive   run it anyway, on purpose",
              file=sys.stderr)
        return 2

    report = {
        "schema": 1,
        "when": datetime.now().astimezone().isoformat(timespec="seconds"),
        "machine": machine(),
        "transcript": {"name": source.name, "shape": shape,
                       "sentences": len(material.sentences),
                       "duration_s": material.duration},
        "engines": installed,
        "asked": {"engine": engine_name, "style": args.style,
                  "length": args.length,
                  "context_tokens": args.context_tokens},
        "prompt_version": prompting.PROMPT_VERSION,
        "plan": the_plan,
        "cache_cleared": None if args.keep_cache else clear_cache(settings),
    }

    print(f"engine: {engine_name}   model: {report['plan'].get('model')}   "
          f"context: {report['plan'].get('context_tokens')}", file=sys.stderr)
    if report["plan"].get("error"):
        print(f"! no plan: {report['plan']['error']}", file=sys.stderr)
    print(f"transcript: {len(material.sentences)} lines, "
          f"{material.duration and round(material.duration)}s\n", file=sys.stderr)

    heard = Tee(sys.stderr)
    started = time.time()
    failure = None
    result = None
    try:
        with redirect_stderr(heard):
            result = summarising.summarize(material, settings)
    except BaseException as stopped:        # noqa: BLE001 - reported, not raised
        failure = f"{type(stopped).__name__}: {stopped}"
    report["elapsed_s"] = round(time.time() - started, 1)
    report["failed"] = failure
    report["said"] = [line for line in heard.getvalue().splitlines() if line.strip()]

    # The passes, as the program itself wrote them down.
    passes = Path(settings["summary_dump_notes"])
    if passes.is_file():
        try:
            report["passes"] = json.loads(passes.read_text(encoding="utf-8"))
        except ValueError as unreadable:
            report["passes"] = {"error": str(unreadable)}
        # Its "points" carry the summary's own sentences: content, not numbers.
        content = report["passes"].pop("points", None)
        passes.unlink()
    else:
        content, report["passes"] = None, None

    if result is not None and result.engine == EXTRACTIVE \
            and engine_name != EXTRACTIVE:
        # It got all the way in and fell back anyway: the model refused to
        # load, or ran and gave back nothing usable. Either way the numbers
        # below would describe quoted sentences. The page says which.
        print(f"\n{engine_name} fell back to quoting sentences part way "
              "through. Nothing here\ndescribes a reading pass. What it "
              "said is in the report, and on the page.", file=sys.stderr)

    if result is not None:
        points = summarising.points_of(result.sections)
        report["result"] = {
            "engine": result.engine,
            "tier": result.tier,
            "sentences_kept": result.kept,
            "sentences_of": result.of,
            "points_on_page": len(points),
            "points_with_a_minute": sum(1 for point in points
                                        if point.start is not None),
            "last_minute_on_page": max(
                [point.start for point in points if point.start is not None],
                default=None),
            "had_a_caveat": bool(result.note),
        }
        page_share = tracing.coverage([point.start for point in points],
                                      material.duration)
        reading_share = ((report.get("passes") or {}).get("metrics") or {}).get(
            "reading_coverage")
        report["metrics"] = {
            "page_coverage": page_share,
            "reading_coverage": reading_share,
            "lost_between_them": (None if None in (page_share, reading_share)
                                  else round(reading_share - page_share, 3)),
            "copy_rate": tracing.copy_rate(
                [point.text for point in points],
                " ".join(str(line) for line in material.sentences)),
        }
        report["metrics"].update((report.get("passes") or {}).get("metrics") or {})

    numbers = Path(str(prefix) + ".numbers.json")
    numbers.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf-8")

    page = Path(str(prefix) + ".page.md")
    body = [f"<!-- {source.name}, {report['when']} -->\n"]
    if result is not None:
        body.append(result.text)
    if failure:
        body.append(f"\n\nNothing was written: {failure}\n")
    if content:
        body.append("\n\n<!-- what the page says, point by point -->\n")
        for point in content:
            body.append(f"- [{point.get('start')}] {point.get('text')}\n")
    page.write_text("".join(body), encoding="utf-8")

    print(f"\nnumbers  -> {numbers}      (no meeting content: send this one)",
          file=sys.stderr)
    print(f"page     -> {page}      (meeting content: keep it with the "
          f"transcript)", file=sys.stderr)
    if failure:
        print(f"\nthe run did not finish: {failure}", file=sys.stderr)
        return 1
    found = report.get("metrics") or {}
    print(f"\nread {_percent(found.get('reading_coverage'))} of the recording, "
          f"page carries {_percent(found.get('page_coverage'))}; "
          f"folds collapsed: {found.get('folds_collapsed')}, "
          f"partials lost: {found.get('partials_lost')}", file=sys.stderr)
    return 0


def _percent(value):
    return "?" if value is None else f"{round(value * 100)}%"


if __name__ == "__main__":
    sys.exit(main())
