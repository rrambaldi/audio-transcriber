"""What a model engine needs that is not the model: prompts in, sections out.

Every engine that actually writes prose faces the same three problems, and
none of them are about the runtime it uses:

* an hour of speech may not fit in one pass, so it is cut into chunks on
  sentence boundaries and summarised in two stages — each chunk on its own
  (*map*), then the chunk summaries together (*reduce*);
* the model has to be told what a summary of a meeting is, in the language
  that was spoken, and given the transcript with its minutes attached so it
  can cite them;
* whatever comes back is markdown written by a language model, which means it
  is *nearly* the shape that was asked for, and has to be read back into the
  same :class:`~audio_transcriber.summary.Sections` the extractive engine
  produces so both end up on the same page.

Keeping all three here rather than in an engine is what makes the next engine
cheap: a different runtime is a different way to turn a string into a string,
and nothing above.

Nothing in this module imports a model, a runtime or a network client, so the
whole of it is covered by the test suite on a machine that has none.
"""
import re

from ..formatting import format_clock
from ..summary import HEADINGS, Point, Sections, estimate_tokens, language_of

#: Tokens of transcript handed to the model in one pass. Deliberately well
#: under the context of any model worth using for this: the prompt, the
#: instructions and the answer all have to fit alongside it, and a model given
#: exactly its context window spends the last of it forgetting the beginning.
CHUNK_TOKENS = 6000

#: Room to leave for the answer, as a share of the material.
ANSWER_TOKENS = 1200

#: What the transcript is wrapped in inside a prompt. The same two markers in
#: every language, because they are delimiters rather than prose and because
#: :func:`parse` has to be able to recognise them: a model that echoes its
#: input instead of answering — small ones do — hands back a "summary" that is
#: the transcript again, and the marker is how that is caught before it
#: reaches the page.
FENCE_START = "-----BEGIN TRANSCRIPT-----"
FENCE_END = "-----END TRANSCRIPT-----"

#: Below this many characters, what survived an echo is not a summary.
MIN_ANSWER = 40

#: Reasoning models narrate before answering. The narration is not the
#: summary, and it must not reach the page.
_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)

#: A markdown heading, at any level.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*\s*$")

#: A bullet: a dash, a star, or a number.
_BULLET = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+(.*)$")

#: The clock the transcript was handed over with, coming back in an answer —
#: with or without the backticks the page puts around it.
_CLOCK = re.compile(r"^`?\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?`?[\s:—-]*")

#: A speaker in bold, as the page writes them.
_SPEAKER = re.compile(r"^\*\*(.+?)\*\*[\s:—-]*")

#: What the model is asked to write, per language. These are prompts, not
#: messages to the user, so they live here rather than in the catalogue — and
#: they are in the language that was *spoken*, which is the language the
#: summary has to come out in.
PROMPTS = {
    "it": {
        "system":
            "Sei un assistente che riassume trascrizioni di riunioni e "
            "registrazioni parlate. Rispondi sempre in italiano.\n"
            "Regole non negoziabili:\n"
            "- usa solo quello che c'e' nella trascrizione; non aggiungere "
            "niente che non sia stato detto;\n"
            "- se una sezione non ha contenuto, lasciala vuota invece di "
            "inventarla;\n"
            "- cita il minuto fra parentesi quadre, come [12:34], copiandolo "
            "dalla trascrizione;\n"
            "- niente preamboli e niente commenti: solo il documento chiesto.",
        "map":
            "Questa e' la parte {part} di {total} di una trascrizione.\n"
            "Elenca, in italiano, solo quello che compare in QUESTA parte: i "
            "punti trattati, le decisioni prese e le cose che qualcuno si e' "
            "impegnato a fare. Un elenco puntato, ogni riga con il minuto.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}",
        "reduce":
            "Questi sono i riassunti parziali di una registrazione, in "
            "ordine.\n\n{partials}\n\n"
            "Scrivi ora il riassunto finale in italiano, con esattamente "
            "queste intestazioni e in quest'ordine, saltando quelle che non "
            "hanno contenuto:\n\n"
            "## {abstract}\nUn paragrafo di tre o quattro righe.\n\n"
            "## {points}\nUn elenco puntato, ogni riga con il minuto.\n\n"
            "## {decisions}\nSolo le decisioni effettivamente prese.\n\n"
            "## {actions}\nChi si e' impegnato a fare cosa, ed entro quando "
            "se e' stato detto.",
        "single":
            "Questa e' la trascrizione di una registrazione.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}\n\n"
            "Scrivi il riassunto in italiano, con esattamente queste "
            "intestazioni e in quest'ordine, saltando quelle che non hanno "
            "contenuto:\n\n"
            "## {abstract}\nUn paragrafo di tre o quattro righe.\n\n"
            "## {points}\nUn elenco puntato, ogni riga con il minuto.\n\n"
            "## {decisions}\nSolo le decisioni effettivamente prese.\n\n"
            "## {actions}\nChi si e' impegnato a fare cosa, ed entro quando "
            "se e' stato detto.",
    },
    "en": {
        "system":
            "You summarise transcripts of meetings and recorded speech. "
            "Always answer in English.\n"
            "Rules you must not break:\n"
            "- use only what is in the transcript; add nothing that was not "
            "said;\n"
            "- leave a section out rather than inventing content for it;\n"
            "- cite the minute in square brackets, like [12:34], copied from "
            "the transcript;\n"
            "- no preamble and no commentary: only the document asked for.",
        "map":
            "This is part {part} of {total} of a transcript.\n"
            "List, in English, only what appears in THIS part: the points "
            "discussed, the decisions taken, and what somebody committed to "
            "doing. A bulleted list, every line carrying its minute.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}",
        "reduce":
            "These are the partial summaries of one recording, in order.\n\n"
            "{partials}\n\n"
            "Now write the final summary in English, under exactly these "
            "headings and in this order, leaving out any that would be "
            "empty:\n\n"
            "## {abstract}\nOne paragraph of three or four lines.\n\n"
            "## {points}\nA bulleted list, every line carrying its minute.\n\n"
            "## {decisions}\nOnly decisions actually taken.\n\n"
            "## {actions}\nWho committed to what, and by when if it was "
            "said.",
        "single":
            "This is the transcript of a recording.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}\n\n"
            "Write the summary in English, under exactly these headings and "
            "in this order, leaving out any that would be empty:\n\n"
            "## {abstract}\nOne paragraph of three or four lines.\n\n"
            "## {points}\nA bulleted list, every line carrying its minute.\n\n"
            "## {decisions}\nOnly decisions actually taken.\n\n"
            "## {actions}\nWho committed to what, and by when if it was "
            "said.",
    },
}


def prompts_for(language):
    """The prompt set for a spoken language, falling back to English."""
    return PROMPTS.get(language_of(language), PROMPTS["en"])


def transcript_for(sentences):
    """The transcript as the model reads it: a minute, a speaker, a sentence.

    The speaker is repeated only when it changes — in a two-person meeting
    that is half the labels gone, and those tokens are better spent on the
    words themselves."""
    lines, last_speaker = [], None
    for sentence in sentences:
        prefix = ""
        if sentence.start is not None:
            prefix = f"[{format_clock(sentence.start)}] "
        if sentence.speaker and sentence.speaker != last_speaker:
            prefix += f"{sentence.speaker}: "
        last_speaker = sentence.speaker or last_speaker
        lines.append(prefix + sentence.text)
    return "\n".join(lines)


def chunks(sentences, budget=CHUNK_TOKENS):
    """Cut the transcript into passes that each fit, on sentence boundaries.

    A sentence longer than the whole budget still gets its own chunk: cutting
    it would produce two halves of a thought, and a model handed a truncated
    sentence summarises the truncation."""
    if not sentences:
        return []
    made, current, size = [], [], 0
    for sentence in sentences:
        cost = estimate_tokens(sentence.text) + 8      # the minute and the name
        if current and size + cost > budget:
            made.append(current)
            current, size = [], 0
        current.append(sentence)
        size += cost
    if current:
        made.append(current)
    return made


def _clock_seconds(text):
    """``1:15`` or ``1:02:03`` as seconds, or None."""
    parts = text.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    return None


def _point(line):
    """One bullet from the model, back into a :class:`Point`."""
    start, speaker = None, None
    clock = _CLOCK.match(line)
    if clock:
        start = _clock_seconds(clock.group(1))
        line = line[clock.end():]
    named = _SPEAKER.match(line)
    if named:
        speaker = named.group(1).strip()
        line = line[named.end():]
    return Point(start, speaker, line.strip())


def _field_of(heading, language):
    """Which section a heading the model wrote belongs to, if any.

    Both the language that was asked for and English are accepted: a model
    told to write "## Decisioni" quite often writes "## Decisions" anyway, and
    losing a whole section to that would be a poor trade for strictness."""
    wanted = re.sub(r"[^\w\s]", "", heading).strip().lower()
    for words in (HEADINGS.get(language, HEADINGS["en"]), HEADINGS["en"]):
        for field in ("abstract", "points", "decisions", "actions", "keywords"):
            if wanted == re.sub(r"[^\w\s]", "", words[field]).strip().lower():
                return field
    return None


def parse(answer, language="it", prompt=None):
    """Read the model's markdown back into sections.

    The headings were asked for exactly, so most of the time this is a
    formality. When it is not — no heading the model wrote is one of ours —
    the whole answer becomes the abstract rather than being thrown away: a
    summary in the wrong shape is worth more than no summary, and the page it
    lands on is markdown either way.

    ``prompt`` is what was sent, and it is worth passing: it is the only way
    to tell an oddly-shaped summary from a model that simply repeated the
    question."""
    language = language_of(language)
    text = _THINK.sub("", str(answer or "")).strip()
    if not text:
        return Sections()

    collected = {"abstract": [], "points": [], "decisions": [], "actions": [],
                 "keywords": []}
    field, matched = None, False
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            found = _field_of(heading.group(1), language)
            field = found
            matched = matched or found is not None
            continue
        if field is None or not line.strip():
            continue
        bullet = _BULLET.match(line)
        if field == "abstract":
            collected["abstract"].append(bullet.group(1) if bullet else line.strip())
        elif bullet:
            collected[field].append(bullet.group(1))

    if not matched:
        return Sections(abstract=_not_an_echo(text, prompt))

    return Sections(
        abstract=" ".join(collected["abstract"]).strip(),
        points=[_point(line) for line in collected["points"]],
        decisions=[_point(line) for line in collected["decisions"]],
        actions=[_point(line) for line in collected["actions"]],
        keywords=[word.strip() for line in collected["keywords"]
                  for word in line.split(",") if word.strip()],
    )


def _not_an_echo(text, prompt=None):
    """What is left of an answer once the model's echo of the prompt is gone.

    A model too small for the job repeats its input instead of answering it.
    That is not a summary in an unexpected shape — the fallback this backs
    onto — it is the prompt again, and putting it on a page labelled "summary"
    would be the worst outcome available: it looks like it worked.

    Recognising it needs the prompt, because the echo is made of perfectly
    reasonable sentences — they are simply the ones that were sent. Leading
    lines that appear verbatim in what was asked are dropped, the transcript
    fence ends the answer wherever it appears, and if what survives is too
    short to be a summary there is no summary."""
    echoed = FENCE_START in text
    if echoed:
        text = text.split(FENCE_START, 1)[0].strip()
    if prompt:
        kept, dropping = [], True
        for line in text.splitlines():
            if dropping and (not line.strip() or line.strip() in prompt):
                echoed = echoed or bool(line.strip())
                continue
            dropping = False
            kept.append(line)
        text = "\n".join(kept).strip()
    return "" if echoed and len(text) < MIN_ANSWER else text


def plan(sentences, budget=CHUNK_TOKENS):
    """The passes to run: one prompt when it all fits, map/reduce when not."""
    parts = chunks(sentences, budget)
    return parts if len(parts) > 1 else [sentences] if sentences else []


def single_prompt(sentences, language):
    """The one-pass prompt: the whole transcript, and what to write about it."""
    words = HEADINGS.get(language_of(language), HEADINGS["en"])
    return prompts_for(language)["single"].format(
        transcript=transcript_for(sentences),
        fence_start=FENCE_START, fence_end=FENCE_END,
        abstract=words["abstract"], points=words["points"],
        decisions=words["decisions"], actions=words["actions"])


def map_prompt(sentences, language, part, total):
    """The prompt for one chunk of a transcript too long to read at once."""
    return prompts_for(language)["map"].format(
        part=part, total=total, transcript=transcript_for(sentences),
        fence_start=FENCE_START, fence_end=FENCE_END)


def reduce_prompt(partials, language):
    """The prompt that turns the chunk summaries into one summary."""
    words = HEADINGS.get(language_of(language), HEADINGS["en"])
    numbered = "\n\n".join(f"--- {index} ---\n{part.strip()}"
                           for index, part in enumerate(partials, start=1))
    return prompts_for(language)["reduce"].format(
        partials=numbered, abstract=words["abstract"], points=words["points"],
        decisions=words["decisions"], actions=words["actions"])
