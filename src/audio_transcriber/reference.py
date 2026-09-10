"""A text you already have, used to help the transcription and fix its spelling.

The case: somebody has the recording *and* something written for it - a
script, a press release, the slides, a transcript from somewhere else. The
audio is still the authority on what was actually said, because a speaker
improvises, skips a paragraph and adds a sentence that was never written down.
What the text is good for is the two things an engine is bad at: knowing that
a name is spelled *Rambaldi* and not *Rambardi*, and finishing a word it only
half caught.

So the text is used twice, and never as a replacement.

**Before**, as a prompt: its distinctive words are handed to the engine, which
is the same mechanism a keyword set uses (:mod:`audio_transcriber.vocabularies`)
and biases the decoder towards spellings it would otherwise invent. Whisper's
prompt is a few hundred characters, so what goes in is the rare words - names,
acronyms, jargon - and not the prose around them.

**After**, as a proof-reader: every word the engine produced is lined up with
the word the text has in that position, and it is corrected *only where the
two are plainly the same word* - a different spelling of it, a dropped accent,
a truncation. Where the audio says something the text does not, the audio wins
and the word stands: that is a speaker who improvised, and overwriting it
would be inventing a recording that does not exist.

Nothing here moves a timing, adds a word or removes one. What comes out is the
engine's own segments with some words spelled the way the text spells them,
which is why everything downstream - the transcript, the subtitle cutter, the
library entry - needs to know nothing about any of it.
"""
import difflib
import re
import unicodedata


class ReferenceError(Exception):
    """The text handed in cannot be used at all - unreadable, most likely."""

#: A word: letters and digits, with an apostrophe kept inside one because
#: "dell'anno" is one word in Italian.
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)

#: How many edits - insertions, deletions, substitutions - may separate two
#: words that are still the same word badly written. One, and the reason is
#: measured rather than felt: on a set of thirty-two pairs drawn from real
#: engine slips and real near-misses, "one edit" put nothing on the wrong
#: side, while a similarity *ratio* of any threshold got between three and
#: fifteen wrong. Ratios throw away the thing that matters here, which is not
#: how alike two words look but how much work it takes to turn one into the
#: other: "premesso" and "permesso" are 87% alike and two different words.
EDITS = 1

#: A word shorter than this is not corrected by edit distance at all. Short
#: words are one edit from each other by accident - "caso" and "corso",
#: "anno" and "hanno", "dati" and "date" - and they are the ones an engine
#: gets right from the audio anyway.
SHORTEST = 6

#: A word this long is worth a prompt even if nothing else marks it out: it is
#: rare enough that the engine may not have it.
LONG_ENOUGH = 9

#: Below this share of the given text turning up in the audio, the two
#: probably do not belong together. Nothing here refuses - a script of the
#: first ten minutes of an hour is a real thing to hand in, and it corrects
#: those ten minutes perfectly well - but the interfaces say so, because
#: "corrected 3 words" reads like a success and a text of another recording
#: is what it usually means.
POOR_MATCH = 0.6

#: Words that are capitalised because they start a sentence and for no other
#: reason. They are not names and are not worth prompt characters.
COMMON = frozenset({"il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
    "e", "ed", "o", "oppure", "ma", "se", "perche", "quando", "come", "dove",
    "chi", "che", "cosa", "non", "ne", "ci", "vi", "si", "mi", "ti", "piu",
    "meno", "molto", "poco", "tutto", "tutti", "questo", "questa", "quello",
    "quella", "noi", "voi", "loro", "io", "tu", "lui", "lei", "sono",
    "siamo", "era", "erano", "ho", "hai", "ha", "abbiamo", "hanno", "essere",
    "avere", "fare", "dire", "adesso", "allora", "dopo", "prima", "poi",
    "anche", "solo", "gia", "ancora", "sempre", "mai", "the", "a", "an",
    "and", "or", "but", "if", "because", "when", "how", "where", "who",
    "what", "not", "no", "we", "you", "they", "he", "she", "it", "is",
    "are", "was", "were", "have", "has", "had", "be", "been", "do", "does",
    "did", "this", "that", "these", "those", "there", "here", "then", "now",
    "also", "only", "just", "still", "always", "never"})


def fold(word):
    """A word reduced to what two spellings of it have in common.

    Case, accents and punctuation differ between something typed and
    something heard, and none of those differences mean the words differ:
    *Perché,* , *perche* and *PERCHÉ* all fold to ``perche``."""
    stripped = unicodedata.normalize("NFKD", word or "")
    stripped = "".join(mark for mark in stripped
                       if not unicodedata.combining(mark))
    return "".join(part.lower() for part in _WORD.findall(stripped))


def words_in(text):
    """The words of a text, as they are written."""
    return (text or "").split()


def distinctive(text, limit=None):
    """The words of ``text`` an engine is unlikely to get right on its own.

    Names, acronyms, compounds and long rare words, in the order they appear
    and without repeats. The prose between them is left out: a prompt is a few
    hundred characters and spending them on "and then we agreed that" buys
    nothing. ``limit`` caps the result in characters, which is how a caller
    stays inside what the backend accepts."""
    found, seen = [], set()
    for raw in words_in(text):
        word = raw.strip("\"'“”«»().,;:!?…-–—")
        folded = fold(word)
        if not folded or folded in seen:
            continue
        if not _worth_prompting(word, folded):
            continue
        seen.add(folded)
        found.append(word)
        if limit is not None and len(" ".join(found)) > limit:
            found.pop()
            break
    return found


def _worth_prompting(word, folded):
    """Whether a word tells the engine something it does not know."""
    return bool(
        any(letter.isupper() for letter in word[1:])        # McCall, iGPU
        or (word.isupper() and len(word) > 1)               # ISO, RAI
        or any(letter.isdigit() for letter in word)         # H.264, 4K
        or "'" in word or "’" in word or "-" in word        # dell'anno
        or len(folded) >= LONG_ENOUGH                       # rare and long
        or (word[:1].isupper() and folded not in COMMON)    # a name
    )


def prompt_from(text, limit=None):
    """The prompt a reference text is worth: its distinctive words, joined.

    Handed to the engine the way a keyword set is, and for the same reason: it
    is the one lever Whisper offers over spelling. What it is *not* is the
    text itself - a prompt long enough to hold the transcript makes the model
    repeat it whether or not it was said, which is the failure this whole
    module is arranged to avoid."""
    return " ".join(distinctive(text, limit=limit))


def levenshtein(first, second):
    """How many edits turn one word into the other.

    The textbook two-row implementation. The words here are a dozen letters
    at most and only the pairs a sequence match already put opposite each
    other ever reach it, so there is nothing to optimise and no reason for a
    dependency."""
    if first == second:
        return 0
    previous = list(range(len(second) + 1))
    for index, letter in enumerate(first, 1):
        current = [index]
        for position, other in enumerate(second, 1):
            current.append(min(previous[position] + 1,      # a deletion
                               current[position - 1] + 1,   # an insertion
                               previous[position - 1] + (letter != other)))
        previous = current
    return previous[-1]


def same_word(heard, given):
    """Whether two folded words are the same word, one of them badly written.

    Three questions, in order, and each of them is there because of a pair it
    gets right and the others get wrong.

    *Is one the beginning of the other?* Then the engine cut a word short -
    "trascriz" for "trascrizioni" - which is the clearest case there is.

    *Is it one edit away, on a word long enough for that to mean something?*
    "rambardi" and "rambaldi", "wisper" and "whisper". Two edits is where
    "premesso" and "permesso" live, and those are two words.

    *Is the edit only the last letter?* Then it is an inflection - a plural, a
    tense, a gender - and inflections are the audio's business, not the
    text's: the speaker said "trascrizione" or "trascrizioni" and the engine
    heard which. This is the question a distance alone cannot answer, and
    without it every singular in a plural text would be quietly rewritten."""
    if not heard or not given:
        return False
    if heard.startswith(given) or given.startswith(heard):
        return True
    if min(len(heard), len(given)) < SHORTEST:
        return False
    if levenshtein(heard, given) > EDITS:
        return False
    return heard[:-1] != given[:-1] or len(heard) != len(given)


def _respell(heard, given, positional=frozenset()):
    """The given word, wearing the punctuation and case the heard one came with.

    Three things are decided separately, by whoever knows.

    The *letters* are the text's: that is the whole point - accents, a name
    spelled right, a word in full where the engine cut it short.

    The *punctuation* is the engine's. Its comma is a decision about the
    sentence it heard, where the speaker paused; the text's comma belongs to a
    sentence that may not have been said in that shape.

    The *first letter's case* is the engine's too, unless the capital is part
    of the word rather than part of a sentence. "Rambaldi" keeps its capital
    wherever it lands; "Poi" only has one because the text starts a sentence
    there, and the engine's own sentence may run straight through it.
    ``positional`` is the set of folded words whose capital is positional -
    see :func:`_positional`."""
    head = re.match(r"^[^\w]*", heard).group(0)
    tail = re.search(r"[^\w]*$", heard).group(0)
    core = given.strip("\"'“”«»().,;:!?…")
    if not core:
        return heard
    bare = heard.strip("\"'“”«»().,;:!?…")
    intrinsic = (core.isupper() and len(core) > 1) \
        or any(letter.isupper() for letter in core[1:])
    if not intrinsic and fold(core) in positional and bare[:1].isalpha():
        core = (core[:1].upper() if bare[:1].isupper()
                else core[:1].lower()) + core[1:]
    return f"{head}{core}{tail}"


def _positional(given_words):
    """Folded words whose capital, in this text, is a sentence's and not theirs.

    A word that also turns up in lower case somewhere in the same text is
    capitalised where it is because of where it is; so is anything in
    :data:`COMMON`. Everything else keeps the case the text gives it, which is
    how a name stays a name."""
    lowercase = {fold(word) for word in given_words
                 if word[:1].islower() or (word[:1] in "\"'“”«»(" and word[1:2].islower())}
    return lowercase | COMMON


def corrections(heard_words, given_words):
    """Which heard words the text can spell better, as ``{index: word}``.

    The two are lined up with :mod:`difflib` on their folded forms, so the
    parts that agree line up even when the middle of the recording went its
    own way. Then:

    * where the two agree on a word, the text's spelling of it is taken - this
      is where an accent or a capital comes back;
    * inside a run where they disagree word for word, a heard word is
      respelled only if :func:`same_word` says the two are one word written
      two ways;
    * a run of words only one side has is skipped entirely. There is nothing
      to correct in a sentence that was never said, and nothing to add to the
      recording because the script expected it.
    """
    heard_folded = [fold(word) for word in heard_words]
    given_folded = [fold(word) for word in given_words]
    positional = _positional(given_words)
    fixes = {}
    matcher = difflib.SequenceMatcher(a=heard_folded, b=given_folded,
                                      autojunk=False)
    for tag, heard_start, heard_end, given_start, _given_end in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(heard_end - heard_start):
                index = heard_start + offset
                if not heard_folded[index]:
                    continue
                _keep(fixes, index, heard_words[index],
                      given_words[given_start + offset], positional)
            continue
        if tag != "replace":
            continue
        pairs = min(heard_end - heard_start, len(given_words) - given_start)
        for offset in range(pairs):
            index = heard_start + offset
            if same_word(heard_folded[index], given_folded[given_start + offset]):
                _keep(fixes, index, heard_words[index],
                      given_words[given_start + offset], positional)
    return fixes


def _keep(fixes, index, heard, given, positional=frozenset()):
    """Record a respelling, unless it changes nothing."""
    respelled = _respell(heard, given, positional)
    if respelled != heard:
        fixes[index] = respelled


def _heard_words(segments):
    """Every word the engine produced, with where to write it back.

    ``(word, segment index, word index)`` - the word index is ``None`` for a
    backend that reported no words of its own, where the segment's text is the
    only thing to rewrite."""
    found = []
    for segment_index, segment in enumerate(segments or []):
        reported = segment.get("words") or []
        if reported:
            for word_index, word in enumerate(reported):
                body = str(word.get("word") or word.get("text") or "").strip()
                if body:
                    found.append((body, segment_index, word_index))
            continue
        for body in (segment.get("text") or "").split():
            found.append((body, segment_index, None))
    return found


def correct(segments, text):
    """Respell what was heard from what ``text`` has, and report what changed.

    Returns ``(segments, report)``, or ``(segments, None)`` when there is
    nothing to work with. The segments are the ones handed in, with some words
    rewritten; nothing is added, removed or re-timed, so a caller that ignores
    the report cannot tell the difference beyond the spelling."""
    given = words_in(text)
    heard = _heard_words(segments)
    if not given or not heard:
        return segments, None

    words = [body for body, _segment, _word in heard]
    fixes = corrections(words, given)

    rebuilt = [dict(segment) for segment in segments or []]
    for segment in rebuilt:
        if segment.get("words"):
            segment["words"] = [dict(word) for word in segment["words"]]
    touched = set()
    for index, replacement in fixes.items():
        _body, segment_index, word_index = heard[index]
        touched.add(segment_index)
        if word_index is None:
            continue
        word = rebuilt[segment_index]["words"][word_index]
        word["word" if "word" in word else "text"] = replacement

    # The text of a segment is rebuilt from its own words, so the transcript
    # and the word list cannot disagree.
    for segment_index in touched:
        pieces = [fixes.get(index, body)
                  for index, (body, owner, _word) in enumerate(heard)
                  if owner == segment_index]
        rebuilt[segment_index]["text"] = " ".join(pieces)

    return rebuilt, {
        "heard": len(words),
        "given": len(given),
        "corrected": len(fixes),
        "matched": _shared(words, given),
        "coverage": round(_shared(words, given) / len(given), 4),
    }


def _shared(heard_words, given_words):
    """How many words the two have in common, in order.

    Says whether the text belongs to this recording at all - which is worth
    reporting, because a text of some other recording corrects nothing and
    should not look as though it did."""
    matcher = difflib.SequenceMatcher(a=[fold(word) for word in heard_words],
                                      b=[fold(word) for word in given_words],
                                      autojunk=False)
    return sum(block.size for block in matcher.get_matching_blocks())
