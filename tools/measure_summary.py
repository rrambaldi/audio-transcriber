"""Measure the summary feature on this machine, and write down what happened.

The catalogue in ``summarizers/plan.py`` decides which model writes a summary
here, and the numbers behind that decision have to be measured rather than
assumed. Two of them cannot be measured on a small machine at all: the largest
size class needs memory a two-core server does not have, and the OpenVINO
engine needs an Intel device. This script is how somebody with either runs the
same measurements and sends back one file.

It answers three questions, in order of how much they matter:

*does this model summarise Italian at all*
    the one that decided the smallest size class. A model can score
    respectably on an English benchmark and, asked in Italian to summarise a
    news article in three sentences, hand back the article. Not a poor
    summary — the article, verbatim. That is checked first because it is
    cheap and because nothing else matters if it fails.
*how well, against a reference*
    ROUGE against Evalita-LLM's Fanpage summarisation task, which is the
    nearest published thing to the real job. A small sample and a rough
    metric: it is a screening, not a leaderboard, and it is here to separate
    "usable" from "not" rather than to rank two models a point apart.
*does the whole thing work end to end*
    a real Italian meeting transcript through the real pipeline, with the
    page it produced and everything the run said along the way.

Nothing here is imported by the program. It downloads: the dataset is small,
the models are not, and it says what it is about to fetch before it starts.

    python tools/measure_summary.py --help
    python tools/measure_summary.py --sample 10 --out report.json
    python tools/measure_summary.py --engine openvino --convert
    python tools/measure_summary.py --resume --out report.json   # finish a run
"""
import argparse
import io
import json
import platform
import re
import sys
import time
import traceback
import unicodedata
import urllib.request
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audio_transcriber import hardware, paths, summary  # noqa: E402
from audio_transcriber.summarizers import llamacpp, plan, prompting  # noqa: E402

#: Evalita-LLM's summarisation task: Italian news from Fanpage, with a
#: reference summary for each article. The hundred-article subset is the right
#: size for a screening on a machine without an accelerator.
DATASET = ("https://huggingface.co/datasets/evalitahf/summarization-fp/"
           "resolve/main/test_100.jsonl")

#: Deliberately the simplest instruction that can be given. A model that
#: cannot follow this one will not follow the program's real prompt either,
#: and when it fails here the failure is unmistakable.
SYSTEM = "Sei un assistente che riassume articoli di giornale in italiano."
ASK = "Riassumi in italiano in tre frasi:\n\n{article}"

#: An article longer than this is cut, so that the screening measures the
#: model rather than the size class's context window.
ARTICLE_CHARS = 4000

#: Answer budget for the screening. The reference summaries are three or four
#: sentences; this is room for twice that.
ANSWER_TOKENS = 220

HERE = Path(__file__).resolve().parent


# --- ROUGE, by hand -------------------------------------------------------
# Implemented here rather than pulled in, because this script must run on a
# machine that has the program installed and nothing else.

def _fold(word):
    return "".join(character for character in unicodedata.normalize("NFKD", word.lower())
                   if not unicodedata.combining(character))


def words(text):
    return [_fold(word) for word in re.findall(r"[^\W\d_]+|\d+", text or "", re.UNICODE)]


def _grams(items, size):
    return [tuple(items[at:at + size]) for at in range(len(items) - size + 1)]


def _f1(overlap, hypothesis, reference):
    if not overlap or not hypothesis or not reference:
        return 0.0
    precision, recall = overlap / hypothesis, overlap / reference
    return 2 * precision * recall / (precision + recall)


def rouge_n(hypothesis, reference, size=1):
    hyp, ref = _grams(hypothesis, size), _grams(reference, size)
    counts = {}
    for gram in ref:
        counts[gram] = counts.get(gram, 0) + 1
    overlap = 0
    for gram in hyp:
        if counts.get(gram):
            counts[gram] -= 1
            overlap += 1
    return _f1(overlap, len(hyp), len(ref))


def rouge_l(hypothesis, reference):
    """The longest common subsequence, as an F1. Order matters, gaps do not."""
    previous = [0] * (len(reference) + 1)
    for left in hypothesis:
        current = [0]
        for index, right in enumerate(reference):
            current.append(previous[index] + 1 if left == right
                           else max(current[index], previous[index + 1]))
        previous = current
    return _f1(previous[-1], len(hypothesis), len(reference))


def copies_the_input(answer, article):
    """Whether the model handed the article back instead of summarising it.

    The single most useful thing this script measures. A model that does this
    is not a weak summariser, it is not a summariser, and no amount of prompt
    work fixes it."""
    head = " ".join(article.split())[:60]
    return " ".join(str(answer or "").split()).startswith(head)


# --- what to measure, and with what ---------------------------------------

def dataset(path=None):
    """The articles and their reference summaries, fetched once if need be.

    Kept in the managed cache directory rather than beside the script: this
    program writes nothing into the working directory, and a benchmark set is
    exactly the kind of regenerable file that directory is for."""
    target = Path(path) if path else Path(paths.cache_dir(), "evalita-summarization-fp.jsonl")
    if not target.exists():
        paths.ensure(str(target.parent))
        print(f"fetching the dataset once: {DATASET}", file=sys.stderr)
        with urllib.request.urlopen(DATASET, timeout=120) as answer:
            target.write_bytes(answer.read())
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def candidates(engine, names=None, usable=None):
    """The models to measure: those asked for, or those this machine can hold."""
    if names:
        wanted = [plan.named(name) for name in names]
        missing = [name for name, found in zip(names, wanted, strict=True) if found is None]
        if missing:
            raise SystemExit(f"not in the catalogue: {', '.join(missing)}")
        return [model for model in wanted if plan.runnable(model, engine)]
    return [model for model in plan.CATALOGUE
            if plan.runnable(model, engine)
            and (usable is None or (plan.estimate_ram_gb(
                model, "Q4_K_M", 2048, "q8_0", "q4_0") or 0) <= usable)]


def plan_for(engine, model):
    """The plan this model would run under, as the program would build it."""
    plan.forget()
    return plan.resolve_plan(engine, {"summary_model": model.name})


def open_model(engine, model, chosen, convert=False):
    """Load one model the way its engine loads it, and hand back the pipeline."""
    if engine == plan.LLAMACPP:
        path = llamacpp.fetch(model, chosen.quant, None)
        return llamacpp.open_pipeline(path, chosen, {})

    from audio_transcriber.summarizers import openvino_genai

    directory = openvino_genai.converted_dir(model.hf_id)
    if not Path(directory, "openvino_tokenizer.xml").exists() and not convert:
        raise SystemExit(f"{model.name} is not converted yet; pass --convert to convert it "
                         "(several gigabytes and some minutes, once per model)")
    return openvino_genai.Pipeline(openvino_genai.prepare(model.hf_id),
                                   openvino_genai.resolve_device("auto"))


def screen(pipeline, rows, sample):
    """Score one loaded model against the reference summaries.

    An empty answer is counted rather than scored. Zero is what a model that
    said nothing gets and also what a model that said something useless gets,
    and those are different problems: the first is usually a reasoning model
    whose reasoning could not be switched off, narrating until the allowance
    ran out. Averaging them into one number hides the only clue."""
    scores, copied, empty, started, written = [], 0, 0, time.time(), []
    for index, row in enumerate(rows[:sample], start=1):
        article = row["source"][:ARTICLE_CHARS]
        raw = pipeline.ask(SYSTEM, ASK.format(article=article),
                           max_new_tokens=ANSWER_TOKENS, think=False)
        answer = prompting.without_thinking(raw)
        note = ""
        if not answer.strip():
            empty += 1
            note = ("  EMPTY — the model was still reasoning when it ran out"
                    if prompting.thought_without_answering(raw) else "  EMPTY")
        elif copies_the_input(answer, article):
            copied += 1
            note = "  COPIED THE ARTICLE"
        hypothesis, reference = words(answer), words(row["target"])
        scores.append((rouge_n(hypothesis, reference, 1),
                       rouge_n(hypothesis, reference, 2),
                       rouge_l(hypothesis, reference)))
        written.append(answer[:400] if answer.strip() else f"<empty> raw: {raw[:200]}")
        print(f"    {index}/{sample}  rouge1={scores[-1][0]:.3f}{note}", flush=True)
    rouge1, rouge2, rougeL = (sum(column) / len(column) for column in zip(*scores, strict=True))
    return {"rouge1": round(rouge1, 4), "rouge2": round(rouge2, 4),
            "rougeL": round(rougeL, 4), "copied_the_article": copied,
            "answered_nothing": empty, "items": len(scores), "first_answers": written[:3],
            "seconds_per_item": round((time.time() - started) / len(scores), 1)}


def end_to_end(engine, transcript):
    """One real summary, through the program rather than around it."""
    material = summary.material_from_text(transcript.read_text(encoding="utf-8"),
                                          title=transcript.stem, language="it")
    noise = io.StringIO()
    started = time.time()
    try:
        import sys
        sys.stderr.write(f"[TRACE] end_to_end() START\n")
        sys.stderr.flush()

##        with redirect_stderr(noise):
        sys.stderr.write(f"[TRACE] end_to_end() calling summary.summarize\n")
        sys.stderr.flush()
        result = summary.summarize(material, {"summarizer": engine})
        sys.stderr.write(f"[TRACE] end_to_end() summary.summarize returned\n")
        sys.stderr.flush()
        
        sys.stderr.write(f"[TRACE] end_to_end() RETURNED\n")
        sys.stderr.flush()
        return {"ok": True, "engine": result.engine, "tier": result.tier,
                "seconds": round(time.time() - started, 1), "note": result.note,
                "sections": {"points": len(result.sections.points),
                             "decisions": len(result.sections.decisions),
                             "actions": len(result.sections.actions),
                             "abstract_chars": len(result.sections.abstract)},
                "page": result.text, "said": noise.getvalue()}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(), "said": noise.getvalue()}


def machine():
    """Everything about this computer that changes any of the answers."""
    return {"platform": platform.platform(), "python": platform.python_version(),
            "processor": platform.processor(), "cores": hardware.cpu_count(),
            "physical_cores": hardware.physical_cores(),
            "ram_total_gb": hardware.total_ram_gb(),
            "ram_available_gb": hardware.available_ram_gb(),
            "openvino_devices": hardware.openvino_devices(),
            "cuda": hardware.has_cuda(),
            "models_dir": paths.models_dir("summary")}


def why_missing(engine):
    """What is absent, and the line that would fix it — or None if it is here.

    "No engine is installed" is a true thing to say to somebody whose machine
    reports an Intel GPU and three OpenVINO devices, and a useless one. The
    devices come from ``openvino``; writing a summary needs ``openvino_genai``
    as well, and that distinction is the whole of the confusion."""
    from audio_transcriber import summarizers

    if summarizers.is_installed(engine):
        return None
    if engine == plan.OPENVINO:
        seen = hardware.openvino_devices()
        found = (f"OpenVINO itself is here ({', '.join(seen)}), but "
                 "openvino_genai is not") if seen else "openvino_genai is not installed"
        return f"{found}\n      pip install \"audio-transcriber-ov[summarize-ov]\""
    return ("neither llama-cpp-python nor a llama-server binary was found\n"
            "      pip install llama-cpp-python\n"
            "      or put llama-server on the PATH, or name it in config.toml")


def engines_here(asked):
    """Which engines to measure: the ones asked for, or the ones installed."""
    from audio_transcriber import summarizers

    wanted = [asked] if asked and asked != "both" else [plan.OPENVINO, plan.LLAMACPP]
    return [name for name in wanted if summarizers.is_installed(name)]


def save(path, report):
    """Write what is known so far.

    Called after every model rather than once at the end: the runs this script
    is for take hours, and the ways they end — a name lookup that fails
    halfway, a model that swaps the machine to a halt, a laptop that sleeps —
    all end with the process gone. Writing as it goes costs a few kilobytes and
    turns every one of those into something ``--resume`` can finish."""
    Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def done_already(path):
    """The previous report, when there is a readable one at ``path``.

    A run interrupted halfway still wrote nothing — the file is written at the
    end — so this is only useful together with a first pass that finished, or
    with a ``--out`` from a run that was narrowed by ``--models``. Anything
    unreadable is treated as absent: a resume must never be the reason the
    measurement stops."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def measured(entry):
    """Whether an earlier entry holds a real score and not a failure.

    A model whose conversion died on a dropped name lookup left an ``error``
    behind, and that is precisely what a second pass is for."""
    return bool(entry) and "rouge1" in entry and "error" not in entry


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the summary feature on this machine.")
    parser.add_argument("--engine", choices=["openvino", "llamacpp", "both"],
                        default="both", help="default: every engine installed here")
    parser.add_argument("--models", default=None,
                        help="comma-separated catalogue names; default: what this "
                             "machine can hold")
    parser.add_argument("--sample", type=int, default=10,
                        help="articles to score per model (default: 10)")
    parser.add_argument("--dataset", default=None, help="a local copy of the .jsonl")
    parser.add_argument("--transcript", default=str(HERE / "sample-verbale.txt"),
                        help="the transcript to summarise end to end")
    parser.add_argument("--convert", action="store_true",
                        help="allow the OpenVINO engine to convert a model it has not "
                             "converted yet: gigabytes, and minutes, once each")
    parser.add_argument("--resume", action="store_true",
                        help="read --out first and measure only what is missing from "
                             "it, so a run cut short by a dropped network or a "
                             "timeout can be finished in a second pass")
    parser.add_argument("--skip-screening", action="store_true")
    parser.add_argument("--skip-end-to-end", action="store_true")
    parser.add_argument("--out", default="summary-measurements.json")
    args = parser.parse_args(argv)

    earlier = done_already(args.out) if args.resume else {}
    report = {"machine": machine(), "when": time.strftime("%Y-%m-%d %H:%M:%S%z"),
              "engines": {}}
    if earlier:
        report["resumed"] = earlier.get("when")
    print(hardware.summary())
    usable = plan.usable_ram_gb(report["machine"]["ram_available_gb"],
                                report["machine"]["ram_total_gb"])
    print(f"usable for a model: {usable:.1f} GB" if usable is not None
          else "usable for a model: unknown")

    found = engines_here(args.engine)
    if not found:
        asked = [args.engine] if args.engine != "both" else [plan.OPENVINO, plan.LLAMACPP]
        lines = ["nothing here can load a model, so there is nothing to measure:"]
        lines += [f"  {name}: {why_missing(name)}" for name in asked]
        raise SystemExit("\n".join(lines))
    names = [name.strip() for name in args.models.split(",")] if args.models else None
    rows = [] if args.skip_screening else dataset(args.dataset)

    for engine in found:
        before = (earlier.get("engines") or {}).get(engine) or {}
        here = {"models": {}}
        report["engines"][engine] = here
        for model in candidates(engine, names, usable if names is None else None):
            chosen = plan_for(engine, model)
            label = f"{model.name} [{engine}]"
            kept = (before.get("models") or {}).get(model.name)
            if measured(kept):
                here["models"][model.name] = kept
                print(f"\n=== {label}: kept from the earlier run "
                      f"(rouge1={kept['rouge1']})")
                continue
            here["models"][model.name] = entry = {
                "tier": chosen.tier, "quant": chosen.quant,
                "context": chosen.context_tokens,
                "cache": f"{chosen.kv_k}/{chosen.kv_v}",
                "estimated_gb": chosen.est_ram_gb}
            print(f"\n=== {label}: {chosen.quant}, context {chosen.context_tokens}, "
                  f"cache {chosen.kv_k}/{chosen.kv_v}, about {chosen.est_ram_gb} GB")
            if args.skip_screening:
                continue
            pipeline = None
            try:
                pipeline = open_model(engine, model, chosen, args.convert)
                entry.update(screen(pipeline, rows, args.sample))
            except SystemExit:
                raise
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                entry["traceback"] = traceback.format_exc()
                print(f"    failed: {entry['error']}", file=sys.stderr)
            finally:
                close = getattr(pipeline, "close", None)
                if close:
                    close()
                save(args.out, report)

        if (before.get("end_to_end") or {}).get("ok"):
            here["end_to_end"] = before["end_to_end"]
            print(f"\n=== {engine}: the real summary is kept from the earlier run")
        elif not args.skip_end_to_end:
            print(f"\n=== {engine}: one real summary, end to end")
            here["end_to_end"] = end_to_end(engine, Path(args.transcript))
            print("    ok" if here["end_to_end"]["ok"]
                  else f"    failed: {here['end_to_end']['error']}")
            save(args.out, report)

    save(args.out, report)
    print(f"\nwritten to {args.out} — send that file back")
    return 0


if __name__ == "__main__":
    sys.exit(main())
