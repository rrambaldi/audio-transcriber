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
from ..summary import (
    DEFAULT_LENGTH,
    HEADINGS,
    Point,
    Sections,
    estimate_tokens,
    language_of,
)
from ..summary import (
    reduce as reduce_sentences,
)

#: Tokens of transcript handed to the model in one pass. Deliberately well
#: under the context of any model worth using for this: the prompt, the
#: instructions and the answer all have to fit alongside it, and a model given
#: exactly its context window spends the last of it forgetting the beginning.
CHUNK_TOKENS = 6000

#: How many partial summaries one reduce pass may fold together. Above this,
#: the partials are reduced in groups and the groups reduced again: a star
#: reduce grows its prompt with the length of the recording, which is the one
#: thing a small model cannot absorb.
REDUCE_FANIN = 6

#: The deepest the whole tree may go, counting the map pass as the first
#: level: three means map, then two reduce passes at most. Beyond that the
#: fan-in is widened instead, because a meeting does not deserve four levels
#: of summary and every level loses information.
MAX_REDUCE_DEPTH = 3

#: Tokens a map answer may spend. A chunk summary is a bulleted list, not a
#: document, and every token here is a token the reduce prompt has to carry.
#: Intermediate reduce passes answer under the same ceiling, for the same
#: reason; only the root writes at length.
MAP_ANSWER_TOKENS = 500

#: Tokens the final answer may spend.
REDUCE_ANSWER_TOKENS = 1400

#: Tokens of original transcript handed to a reduce pass alongside the
#: partials. Merging summaries recursively amplifies whatever the model
#: invented at the level below, because from the second level on it is
#: reading its own writing with no way back to the source; a small extract of
#: what was actually said is the cheapest thing that gives it one.
EVIDENCE_TOKENS = 400

#: Bumped whenever a prompt here changes. It is part of the cache key of a
#: partial answer, and a cache that survives a prompt change is a bug that
#: accumulates rather than a saving.
PROMPT_VERSION = 2

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

#: A markdown heading, at any level — or a line that is nothing but bold text,
#: or square brackets, which is how a model asked for "## Punti chiave" very
#: often answers instead. Left unrecognised, every section it wrote lands in
#: the abstract and the page is one paragraph where it should be four.
#:
#: The bracket form excludes a leading digit and a nested bracket on purpose:
#: without that guard, a garbled line such as "[18:11] pulizia necessaria]"
#: (a clock the model never closed) reads as a heading too, and everything
#: after it is silently dropped rather than merely misplaced.
_HEADING = re.compile(r"^\s{0,3}(?:#{1,6}\s*(.+?)\s*#*"
                      r"|\*\*(.+?)\*\*:?|__(.+?)__:?"
                      r"|\[(?!\d)([^\[\]]{1,40})\])\s*$")

#: A heading and its content on the same line — "Decisioni: rinnovare il
#: contratto" — which is what a small model does with the scaffold instead of
#: writing a heading of its own. The colon must be followed by a space, not a
#: digit, so a clock such as "1:02:03 ..." is never read as one: the whole
#: label is checked against the known headings below, so this cannot turn an
#: ordinary sentence with a colon in it into a section switch.
_LABELLED = re.compile(r"^\s{0,3}([^\n:]{1,40}):\s+(\S.*)$")

#: A bullet: a dash, a star, or a number.
_BULLET = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+(.*)$")

#: The clock the transcript was handed over with, coming back in an answer —
#: with or without the backticks the page puts around it.
_CLOCK = re.compile(r"^`?\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?`?[\s:—-]*")

#: The same clock, wherever on the line it sits. A model told to put the
#: minute on every row is not told where, and puts it at the end as often as
#: at the front. Measuring coverage with the strict one above counted a whole
#: reading pass as carrying no minute at all, which read as a pass that had
#: failed rather than one that had answered in the other order.
_ANY_CLOCK = re.compile(r"`?\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?`?")

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
            "Questa e' la parte {part} di {total} della trascrizione "
            "automatica di una registrazione parlata: parlato com'e' stato "
            "detto, con frasi incomplete, ripetizioni ed errori di "
            "riconoscimento.\n\n"
            "Prendi APPUNTI su quello che compare in QUESTA parte. Appunti, "
            "non citazioni.\n\n"
            "1. RISCRIVI. Ogni appunto e' una frase completa e comprensibile "
            "da sola, da chi non era presente. Non copiare le parole del "
            "parlato.\n"
            "2. Un appunto, una informazione. Se una frase ne contiene tre, "
            "scrivi tre appunti.\n"
            "3. Non inventare. Quello che non e' stato detto non lo scrivi; "
            "quello che non si capisce lo salti.\n"
            "4. Salta convenevoli, saluti, digressioni personali e problemi "
            "audio.\n"
            "5. Usa esattamente le intestazioni qui sotto, in quest'ordine. "
            "Salta un'intestazione se non hai nulla da metterci, e non "
            "aggiungerne altre.\n"
            "6. OGNI riga finisce con il minuto fra parentesi quadre, copiato "
            "dalla riga della trascrizione da cui viene.{speaker_rule}\n\n"
            "{sections_block}\n\n{examples}\n"
            "Ora la parte {part} di {total}:\n\n"
            "{fence_start}\n{transcript}\n{fence_end}",
        "map_speaker_rule":
            " Dopo il minuto, fra parentesi tonde, l'etichetta di chi parla.",
        "label":
            "Questi sono appunti che riguardano tutti lo stesso argomento.\n\n"
            "{notes}\n\n"
            "Rispondi SOLO con un titolo da tre a otto parole che dica qual e' "
            "l'argomento. Niente punteggiatura finale, niente numerazione, "
            "niente spiegazioni, niente virgolette.",
        "section":
            "Scrivi una sezione di un resoconto, in italiano, a partire da "
            "questi appunti, che riguardano tutti lo stesso argomento.\n\n"
            "{notes}\n\n"
            "Struttura:\n{shape}\n\n"
            "Regole:\n"
            "- usa solo quello che c'e' negli appunti, non aggiungere nulla;\n"
            "{rules}"
            "- non scrivere il titolo della sezione, lo mette qualcun "
            "altro;\n"
            "- niente minuti, niente nomi di chi parla, nessun riferimento al "
            "fatto che si tratti di una trascrizione.",
        "abstract_from":
            "Questi sono gli argomenti di cui si e' parlato in una "
            "registrazione, nell'ordine.\n\n"
            "{titles}\n\n"
            "Scrivi in italiano il paragrafo di apertura del resoconto, "
            "{span}: di cosa si e' parlato nel complesso e quali "
            "sono stati i temi principali. NON elencarli uno per uno, quelli "
            "vengono subito dopo. Prosa continua, non un elenco travestito.",
        "map_example":
            "Esempio. Da questo estratto:\n\n"
            "{fence_start}\n"
            "[0:27] eh allora io vorrei cioe' monitorare tutti gli utenti a "
            "cui e' stata inviata la mail no e poi vedere se sono entrati\n"
            "[0:35] e poi veder nel momento in cui partito la campagna gli "
            "vengono assegnati i ticket agli utenti se loro entrano\n"
            "[14:02] ma si' allora scusa un attimo che ho il cane che abbaia\n"
            "[14:11] dicevo ho provato a fare una checklist fornitore vera "
            "con la vecchia interfaccia ci ho messo ventidue minuti con "
            "quella nuova quattro minuti e dodici secondi\n"
            "{fence_end}\n\n"
            "si scrive:\n\n"
            "## Requisiti\n"
            "- Serve poter monitorare gli utenti a cui e' stata inviata la "
            "mail di invito e verificare se hanno fatto il primo accesso. "
            "[0:27]\n"
            "- Dopo l'avvio di una campagna occorre sapere se gli utenti a "
            "cui sono stati assegnati i ticket hanno fatto il login per "
            "vederli. [0:35]\n"
            "## Fatti\n"
            "- Creare una checklist fornitore reale ha richiesto 22 minuti "
            "con la vecchia interfaccia e 4 minuti e 12 secondi con la "
            "nuova. [14:11]\n\n"
            "Il cane che abbaia non e' un appunto, e le due frasi sulla "
            "checklist sono un appunto solo.\n",
        "evidence":
            "Questi sono passaggi della trascrizione originale, per "
            "controllo.\n\n{fence_start}\n{evidence}\n{fence_end}\n\n"
            "Verifica i riassunti qui sopra contro questi passaggi: togli "
            "quello che non ci trovi, e copia i minuti come sono scritti "
            "qui.\n\n",
        "reduce_partial":
            "Questi sono riassunti parziali consecutivi della stessa "
            "registrazione, in ordine.\n\n{partials}\n\n{evidence}"
            "Fondili in un solo elenco puntato in italiano, in ordine di "
            "tempo: togli le ripetizioni, tieni ogni riga con il suo minuto, "
            "e non scrivere ancora il documento finale con le intestazioni.",
        "reduce":
            "Questi sono i riassunti parziali di una registrazione, in "
            "ordine.\n\n{partials}\n\n{evidence}"
            "Scrivi ora il riassunto finale in italiano, con esattamente "
            "queste intestazioni e in quest'ordine, saltando quelle che non "
            "hanno contenuto:\n\n"
            "## {abstract}\n{abstract_detail}\n\n"
            "## {points}\n{points_detail}\n\n"
            "## {decisions}\nSolo le decisioni effettivamente prese.\n\n"
            "## {actions}\nChi si e' impegnato a fare cosa, ed entro quando "
            "se e' stato detto.",
        "single":
            "Questa e' la trascrizione di una registrazione.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}\n\n"
            "Scrivi il riassunto in italiano, con esattamente queste "
            "intestazioni e in quest'ordine, saltando quelle che non hanno "
            "contenuto:\n\n"
            "## {abstract}\n{abstract_detail}\n\n"
            "## {points}\n{points_detail}\n\n"
            "## {decisions}\nSolo le decisioni effettivamente prese.\n\n"
            "## {actions}\nChi si e' impegnato a fare cosa, ed entro quando "
            "se e' stato detto.",
        "section_single":
            "Questa e' la trascrizione di una registrazione.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}\n\n"
            "{instruction} Se non c'e' nulla da scrivere per questa sezione, "
            "rispondi esattamente con {empty} e nient'altro.",
        "section_reduce":
            "Questi sono i riassunti parziali di una registrazione, in "
            "ordine.\n\n{partials}\n\n{evidence}"
            "{instruction} Se non c'e' nulla da scrivere per questa sezione, "
            "rispondi esattamente con {empty} e nient'altro.",
        "merge":
            "Queste sono quattro sezioni scritte una alla volta sulla stessa "
            "registrazione: la stessa cosa puo' comparire in piu' di "
            "una.\n\n{draft}\n\n"
            "Riscrivi il documento finale in italiano, con esattamente "
            "queste intestazioni e in quest'ordine, saltando quelle che non "
            "hanno contenuto:\n\n"
            "## {abstract}\n\n## {points}\n\n## {decisions}\n\n## "
            "{actions}\n\n"
            "Se la stessa cosa compare in piu' di una sezione, tienila solo "
            "in quella piu' specifica (Decisioni o Azioni valgono su Punti "
            "chiave) e non ripeterla altrove. Non aggiungere nulla che non "
            "sia gia' scritto qui sopra.",
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
            "This is part {part} of {total} of the automatic transcript of a "
            "spoken recording: speech as it was said, with unfinished "
            "sentences, repetitions and recognition errors.\n\n"
            "Take NOTES on what appears in THIS part. Notes, not quotations."
            "\n\n"
            "1. REWRITE. Every note is a complete sentence, understandable on "
            "its own by somebody who was not there. Do not copy the words of "
            "the speech.\n"
            "2. One note, one piece of information. If a sentence holds "
            "three, write three notes.\n"
            "3. Do not invent. What was not said you do not write; what "
            "cannot be understood you skip.\n"
            "4. Skip pleasantries, greetings, personal digressions and audio "
            "trouble.\n"
            "5. Use exactly the headings below, in this order. Skip a heading "
            "with nothing to put under it, and add none of your own.\n"
            "6. EVERY line ends with the minute in square brackets, copied "
            "from the transcript line it came from.{speaker_rule}\n\n"
            "{sections_block}\n\n{examples}\n"
            "Now part {part} of {total}:\n\n"
            "{fence_start}\n{transcript}\n{fence_end}",
        "map_speaker_rule":
            " After the minute, in round brackets, the label of whoever is "
            "speaking.",
        "label":
            "These are notes that are all about one subject.\n\n"
            "{notes}\n\n"
            "Answer with NOTHING but a title of three to eight words saying "
            "what the subject is. No full stop, no numbering, no explanation, "
            "no quotation marks.",
        "section":
            "Write a section of a written record, in English, from these "
            "notes, which are all about one subject.\n\n"
            "{notes}\n\n"
            "The shape:\n{shape}\n\n"
            "Rules:\n"
            "- use only what is in the notes, add nothing;\n"
            "{rules}"
            "- do not write the section's title, somebody else puts it "
            "there;\n"
            "- no minutes, no names of speakers, no reference to this being a "
            "transcript.",
        "abstract_from":
            "These are the subjects a recording covered, in order.\n\n"
            "{titles}\n\n"
            "Write, in English, the opening paragraph of the record, "
            "{span}: what was discussed overall and what the main "
            "themes were. Do NOT list them one by one, those follow straight "
            "after. Continuous prose, not a list in disguise.",
        "map_example":
            "An example. From this extract:\n\n"
            "{fence_start}\n"
            "[0:27] right so what I want is to keep an eye on all the users "
            "the mail went out to you know and then see whether they came in\n"
            "[0:35] and then see once the campaign has started they get the "
            "tickets assigned do they actually log in\n"
            "[14:02] hang on sorry a second the dog is barking\n"
            "[14:11] anyway I tried building a real supplier checklist it "
            "took me twenty-two minutes on the old interface four minutes and "
            "twelve seconds on the new one\n"
            "{fence_end}\n\n"
            "one writes:\n\n"
            "## Requirements\n"
            "- There has to be a way to see which users the invitation mail "
            "went to and whether they have signed in for the first time. "
            "[0:27]\n"
            "- Once a campaign has started, it has to be possible to tell "
            "whether the users its tickets were assigned to have logged in to "
            "see them. [0:35]\n"
            "## Facts\n"
            "- Building a real supplier checklist took 22 minutes on the old "
            "interface and 4 minutes 12 seconds on the new one. [14:11]\n\n"
            "The barking dog is not a note, and the two sentences about the "
            "checklist are one note.\n",
        "evidence":
            "These are passages of the original transcript, to check "
            "against.\n\n{fence_start}\n{evidence}\n{fence_end}\n\n"
            "Check the summaries above against these passages: drop whatever "
            "you cannot find in them, and copy the minutes as written "
            "here.\n\n",
        "reduce_partial":
            "These are consecutive partial summaries of one recording, in "
            "order.\n\n{partials}\n\n{evidence}"
            "Merge them into a single bulleted list in English, in time "
            "order: drop the repetitions, keep every line's minute, and do "
            "not write the final document with its headings yet.",
        "reduce":
            "These are the partial summaries of one recording, in order.\n\n"
            "{partials}\n\n{evidence}"
            "Now write the final summary in English, under exactly these "
            "headings and in this order, leaving out any that would be "
            "empty:\n\n"
            "## {abstract}\n{abstract_detail}\n\n"
            "## {points}\n{points_detail}\n\n"
            "## {decisions}\nOnly decisions actually taken.\n\n"
            "## {actions}\nWho committed to what, and by when if it was "
            "said.",
        "single":
            "This is the transcript of a recording.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}\n\n"
            "Write the summary in English, under exactly these headings and "
            "in this order, leaving out any that would be empty:\n\n"
            "## {abstract}\n{abstract_detail}\n\n"
            "## {points}\n{points_detail}\n\n"
            "## {decisions}\nOnly decisions actually taken.\n\n"
            "## {actions}\nWho committed to what, and by when if it was "
            "said.",
        "section_single":
            "This is the transcript of a recording.\n\n"
            "{fence_start}\n{transcript}\n{fence_end}\n\n"
            "{instruction} If there is nothing to write for this section, "
            "answer with exactly {empty} and nothing else.",
        "section_reduce":
            "These are the partial summaries of one recording, in order.\n\n"
            "{partials}\n\n{evidence}"
            "{instruction} If there is nothing to write for this section, "
            "answer with exactly {empty} and nothing else.",
        "merge":
            "These are four sections written one at a time about the same "
            "recording: the same thing may appear in more than one.\n\n"
            "{draft}\n\n"
            "Rewrite the final document in English, under exactly these "
            "headings and in this order, leaving out any that would be "
            "empty:\n\n"
            "## {abstract}\n\n## {points}\n\n## {decisions}\n\n## "
            "{actions}\n\n"
            "Where the same thing appears in more than one section, keep it "
            "only in the more specific one (Decisions or Actions over Key "
            "points) and do not repeat it elsewhere. Add nothing that is not "
            "already written above.",
    },
}


#: What the asked length changes in the questions, per language.
#:
#: It changes the question and never the answer, and that is the whole of the
#: design. A page is not made short by cutting its prose off at a word count —
#: that produces a broken section, not a brief one — so a short page asks for
#: a paragraph and no list, and a long one asks for a bullet per note. The
#: notes themselves are the same notes at every length: what was read is read
#: once and kept, and only how much of it is written down moves.
#:
#: ``shape`` and ``rules`` go into the section prompt of the page written in
#: sections, ``span`` into its opening paragraph, and ``abstract``/``points``
#: into the two headings of the old shape that can honestly be longer or
#: shorter. Decisions and actions are not here on purpose: there were as many
#: of them as there were, and a "short" page that leaves two of them out is
#: not shorter, it is wrong.
PAGE_DETAIL = {
    "it": {
        "short": {
            "shape":
                "- UN SOLO paragrafo di UNA O DUE frasi, non di piu';\n"
                "- dice cosa si e' chiesto o deciso su questo argomento, "
                "non come ci si e' arrivati;\n"
                "- niente elenchi puntati, niente elenchi numerati, niente "
                "titoli: quello che non sta in due frasi resta fuori.",
            "rules":
                "- e' un riassunto breve: tieni solo quello che un lettore "
                "deve sapere per forza, e lascia fuori il resto;\n"
                "- non elencare i dettagli nemmeno dentro la frase;\n",
            "span": "una o due frasi",
            "abstract": "Un paragrafo di due o tre righe.",
            "points":
                "Un elenco puntato dei punti principali, non piu' di cinque "
                "righe, ogni riga con il minuto.",
        },
        "medium": {
            "shape":
                "- un paragrafo iniziale di una o tre frasi che inquadra "
                "l'argomento e dice cosa e' stato chiesto o deciso nel "
                "complesso;\n"
                "- sotto, un elenco puntato con i dettagli;\n"
                "- se gli appunti descrivono casi, alternative o fasi "
                "distinte, usa un elenco numerato con sotto-punti annidati "
                "invece di una lista piatta.",
            "rules":
                "- il paragrafo inquadra e i punti dettagliano: non ripetere "
                "nei punti quello che hai gia' scritto nel paragrafo;\n",
            "span": "da due a quattro frasi",
            "abstract": "Un paragrafo di tre o quattro righe.",
            "points": "Un elenco puntato, ogni riga con il minuto.",
        },
        "long": {
            "shape":
                "- un paragrafo iniziale di due o tre frasi che inquadra "
                "l'argomento e dice cosa e' stato chiesto o deciso nel "
                "complesso;\n"
                "- sotto, un elenco puntato con i dettagli: un punto per "
                "ogni appunto, senza lasciarne fuori nessuno;\n"
                "- se gli appunti descrivono casi, alternative o fasi "
                "distinte, usa un elenco numerato con sotto-punti annidati "
                "invece di una lista piatta.",
            "rules":
                "- il paragrafo inquadra e i punti dettagliano: non ripetere "
                "nei punti quello che hai gia' scritto nel paragrafo;\n"
                "- dove gli appunti danno numeri, date, nomi o condizioni, "
                "riportali per intero;\n",
            "span": "da quattro a sei frasi",
            "abstract": "Un paragrafo di cinque o sei righe.",
            "points":
                "Un elenco puntato esteso, senza lasciare fuori nulla di "
                "quello che c'e' nei riassunti parziali, ogni riga con il "
                "minuto.",
        },
    },
    "en": {
        "short": {
            "shape":
                "- ONE paragraph of ONE OR TWO sentences, no more;\n"
                "- it says what was asked or decided about this subject, "
                "not how it was arrived at;\n"
                "- no bulleted lists, no numbered lists, no headings: "
                "whatever does not fit in two sentences stays out.",
            "rules":
                "- this is a short summary: keep only what a reader has to "
                "know, and leave the rest out;\n"
                "- do not list the detail inside the sentence either;\n",
            "span": "one or two sentences",
            "abstract": "One paragraph of two or three lines.",
            "points":
                "A bulleted list of the main points, no more than five "
                "lines, every line carrying its minute.",
        },
        "medium": {
            "shape":
                "- an opening paragraph of one to three sentences framing "
                "the subject and saying what was asked or decided "
                "overall;\n"
                "- under it, a bulleted list of the detail;\n"
                "- where the notes describe cases, alternatives or distinct "
                "stages, use a numbered list with nested sub-points rather "
                "than a flat one.",
            "rules":
                "- the paragraph frames and the bullets detail: do not "
                "repeat in the bullets what the paragraph already said;\n",
            "span": "two to four sentences",
            "abstract": "One paragraph of three or four lines.",
            "points": "A bulleted list, every line carrying its minute.",
        },
        "long": {
            "shape":
                "- an opening paragraph of two or three sentences framing "
                "the subject and saying what was asked or decided "
                "overall;\n"
                "- under it, a bulleted list of the detail: one bullet per "
                "note, leaving none of them out;\n"
                "- where the notes describe cases, alternatives or distinct "
                "stages, use a numbered list with nested sub-points rather "
                "than a flat one.",
            "rules":
                "- the paragraph frames and the bullets detail: do not "
                "repeat in the bullets what the paragraph already said;\n"
                "- where the notes give figures, dates, names or "
                "conditions, carry them over in full;\n",
            "span": "four to six sentences",
            "abstract": "One paragraph of five or six lines.",
            "points":
                "A long bulleted list, leaving out nothing that is in the "
                "partial summaries, every line carrying its minute.",
        },
    },
}


def detail_for(language, length=None):
    """How much the page is asked to say, in the language that was spoken."""
    catalogue = PAGE_DETAIL.get(language_of(language), PAGE_DETAIL["en"])
    return catalogue.get(str(length or DEFAULT_LENGTH).strip().lower(),
                         catalogue[DEFAULT_LENGTH])


#: The four fields a model can be asked to write, in page order. ``keywords``
#: is not here: no engine that writes prose fills it, so there is nothing for
#: a single-section request to ask for.
SECTION_FIELDS = ("abstract", "points", "decisions", "actions")

#: What a single-section request answers when it has nothing to write, in
#: place of simply leaving a heading out — there is no heading to leave out
#: here, since the question already said which one this is. Not translated,
#: the same way FENCE_START/FENCE_END are not: a fixed marker is easier to
#: recognise coming back than a word that could arrive capitalised,
#: translated, or wrapped in emphasis.
EMPTY_SECTION = "__NESSUNA__"

#: How long an answer can be and still be read as "there is nothing here".
#: A model with nothing to say says so in a few words; one with something to
#: say writes bullets with minutes in them. The bound is what keeps a real
#: finding that happens to open with a negation — "Nessuna decisione sulle
#: assunzioni, ma il budget è stato approvato" — from being thrown away.
EMPTY_SECTION_CHARS = 90

#: The marker above, tolerant of three things a model does to it.
#:
#: The emphasis and punctuation it gets wrapped in — "**__NESSUNA__**",
#: "_Nessuna._" — and the underscores being dropped, which is what a model
#: that renders markdown does with them. That much was always allowed.
#:
#: And then the paraphrase, which is what this was widened for: an xs-tier
#: model asked for a fixed marker writes "nessuna informazione disponibile"
#: instead, and meaning it is not the same as being able to obey. Taken as
#: content, that one line became the only non-empty draft of a summary and
#: the whole merge pass was skipped for it. So a short answer opening on a
#: negation counts as the marker, in either language the prompts are written
#: in — the length is what makes it safe, not the wording.
_EMPTY_SECTION = re.compile(
    r"^(nessun[ao]?|non\s+(ci\s+sono|risultano?|sono\s+stat[ei])"
    r"|none|nothing|no\s+\w+)(?![a-z])",
    re.IGNORECASE)

#: What a model wraps the marker in, and what is taken off both ends before
#: it is looked at: emphasis, quotes, the bullet it arrived as, and the full
#: stop it was given. The underscores are in here twice over — they are the
#: marker's own, and they are why the match cannot end on ``\b``, since a
#: regex counts an underscore as part of a word.
_DECORATION = "\t\n\r *_\"'`.:;-—–•"


def is_empty_section(text):
    """Whether a single-section answer means "there was nothing to say".

    Short *and* opening on a negation: either alone would be wrong. A long
    answer that starts with "no" is a finding about something that did not
    happen — "Nessuna decisione sulle assunzioni, ma il budget è passato" —
    and a short answer that denies nothing is simply a short finding."""
    text = " ".join(str(text or "").split()).strip(_DECORATION)
    if not text:
        return True
    return (len(text) <= EMPTY_SECTION_CHARS
            and bool(_EMPTY_SECTION.match(text)))

#: The one line each single-section request adds to the shared prompt body,
#: per field. In the language that was spoken, like every other prompt here.
SECTION_INSTRUCTIONS = {
    "it": {
        "abstract":
            "Scrivi in italiano SOLO un paragrafo di tre o quattro righe che "
            "riassume la registrazione, senza titolo e senza elenco.",
        "points":
            "Scrivi in italiano SOLO i punti chiave discussi, come elenco "
            "puntato, ogni riga con il minuto.",
        "decisions":
            "Scrivi in italiano SOLO le decisioni effettivamente prese (non "
            "proposte, non ipotesi), come elenco puntato, ogni riga con il "
            "minuto.",
        "actions":
            "Scrivi in italiano SOLO chi si e' impegnato a fare cosa, con la "
            "scadenza se e' stata detta, come elenco puntato, ogni riga con "
            "il minuto.",
    },
    "en": {
        "abstract":
            "Write, in English, ONLY a paragraph of three or four lines "
            "summarising the recording, with no title and no list.",
        "points":
            "Write, in English, ONLY the key points discussed, as a "
            "bulleted list, every line carrying its minute.",
        "decisions":
            "Write, in English, ONLY decisions actually taken (not "
            "proposals, not hypotheses), as a bulleted list, every line "
            "carrying its minute.",
        "actions":
            "Write, in English, ONLY who committed to what, and by when if "
            "it was said, as a bulleted list, every line carrying its "
            "minute.",
    },
}


def prompts_for(language):
    """The prompt set for a spoken language, falling back to English."""
    return PROMPTS.get(language_of(language), PROMPTS["en"])


#: Built once per language, on demand: the prompts are constants.
_SCAFFOLDS = {}


def scaffold(language, types=None):
    """Every line this program's own prompts are made of, as literal text.

    What it is for is recognising those lines coming back: a model that
    reproduces the shape it was given has not written anything, and the shape
    is known exactly because this module wrote it.

    Two things have to be in here that are not in the templates, and both are
    easy to miss. The headings block is generated, so its lines never appear
    in a template value; and the worked example in the reading prompt is a
    model answer, which is exactly what a model that has understood nothing
    hands back. Neither would be recognised, and both would reach the page.

    Kept per language *and per set of kinds*, because the block depends on
    both: memoised on the language alone, two runs in one process with
    different kinds would share the wrong scaffold."""
    code = language_of(language)
    from . import notes

    kinds = tuple(types or notes.DEFAULT_TYPES)
    if (code, kinds) not in _SCAFFOLDS:
        lines = set()
        written = list(prompts_for(code).values())
        written.append(note_headings(code, kinds))
        for template in written:
            for line in re.sub(r"\{[^}]*\}", "", template).splitlines():
                line = line.strip()
                if len(line) > 3:
                    lines.add(line)
        _SCAFFOLDS[(code, kinds)] = frozenset(lines)
    return _SCAFFOLDS[(code, kinds)]


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


def _cost(sentence, language=None):
    """What one sentence costs in a prompt: its words, its minute, its name."""
    return estimate_tokens(sentence.text, language) + 8


def _carried(chunk, tokens, language=None):
    """The tail of a chunk to repeat at the head of the next one.

    Never the whole chunk, however small the budget: a chunk made only of
    repeated sentences would make no progress through the transcript."""
    if tokens <= 0 or len(chunk) < 2:
        return []
    kept, size = [], 0
    for sentence in reversed(chunk[1:]):
        cost = _cost(sentence, language)
        if size + cost > tokens:
            break
        kept.append(sentence)
        size += cost
    kept.reverse()
    return kept


def chunks(sentences, budget=CHUNK_TOKENS, overlap=0.0, language=None):
    """Cut the transcript into passes that each fit, on sentence boundaries.

    A sentence longer than the whole budget still gets its own chunk: cutting
    it would produce two halves of a thought, and a model handed a truncated
    sentence summarises the truncation.

    ``overlap`` repeats a share of each chunk at the head of the next one.
    What it buys is the seam: a decision taken across a chunk boundary is
    otherwise half in one pass and half in another, and neither pass sees it
    whole. It costs that share of the reading again, so it stays off unless a
    caller asks — the plan does."""
    if not sentences:
        return []
    carry = max(0.0, min(0.5, float(overlap or 0.0))) * budget
    made, current, size = [], [], 0
    for sentence in sentences:
        cost = _cost(sentence, language)
        if current and size + cost > budget:
            made.append(current)
            current = _carried(current, carry, language)
            size = sum(_cost(item, language) for item in current)
        current.append(sentence)
        size += cost
    if current:
        made.append(current)
    return made


def budget_for(context_tokens, answer_tokens=REDUCE_ANSWER_TOKENS, overhead=400):
    """How much transcript fits in one pass, given the model's context.

    The default :data:`CHUNK_TOKENS` is a guess made without knowing which
    model would run; this is the same question answered by arithmetic once the
    plan has chosen one. ``overhead`` is the instructions around the material —
    measured generously, because the failure it prevents is an overflow."""
    return max(0, int(context_tokens) - int(answer_tokens) - int(overhead))


def fanin_for(count, context_tokens, partial_tokens,
              answer_tokens=REDUCE_ANSWER_TOKENS,
              evidence_tokens=EVIDENCE_TOKENS, overhead=400):
    """The widest fan-in whose reduce prompt still fits this model's context.

    Two below it and the tree is a chain; :data:`REDUCE_FANIN` above it and a
    single prompt carries more of the recording than any model chosen for a
    small machine can hold."""
    room = (budget_for(context_tokens, answer_tokens, overhead)
            - max(0, int(evidence_tokens)))
    fits = room // max(1, int(partial_tokens))
    widest = min(REDUCE_FANIN, max(2, int(count)))
    return max(2, min(widest, int(fits)))


def _depth(count, fanin):
    """How many reduce passes folding ``count`` partials this fan-in needs."""
    levels = 0
    while count > 1:
        count = -(-count // fanin)
        levels += 1
    return max(1, levels)


def reduce_tree(partials, fanin=REDUCE_FANIN, max_depth=MAX_REDUCE_DEPTH,
                max_fanin=None):
    """Group the partials into the reduce passes to run, level by level.

    Returns one list per level, each a list of groups, each group the indices
    a single prompt folds together — indices into the partials at the first
    level, and into the previous level's results after that. Indices rather
    than texts because the levels above the first fold answers that do not
    exist yet when the shape is decided.

    Pure: no model and no I/O, so the shape of the tree is testable without
    one, which is the whole reason it lives here.

    Depth counts the map pass as the first level, so the default allows two
    reduce passes. When more would be needed the fan-in is widened instead —
    a meeting does not deserve four levels of summary, and every level loses
    information. ``max_fanin`` stops that widening: on a model whose context
    cannot hold a wider prompt, an extra level is the lesser harm, and that is
    a judgement only the caller with the plan in hand can make."""
    items = list(partials)
    if not items:
        return []

    width = max(2, int(fanin))
    ceiling = max(width, int(max_fanin)) if max_fanin else None
    while _depth(len(items), width) > max(1, int(max_depth) - 1):
        if ceiling is not None and width >= ceiling:
            break
        width += 1

    levels, indices = [], list(range(len(items)))
    while True:
        if len(indices) <= width:
            levels.append([list(indices)])
            break
        levels.append([indices[at:at + width]
                       for at in range(0, len(indices), width)])
        indices = list(range(len(levels[-1])))
    return levels


def evidence_for(sentences, budget=EVIDENCE_TOKENS, language="it"):
    """A small extract of what was actually said, for a reduce pass to read.

    From the second level of the tree on, the model is summarising its own
    writing and has no way back to the recording; handing it the highest-
    weighted sentences of the material underneath that group is the cheapest
    way to give it one. It is the same selection the extractive engine makes,
    at a much smaller budget."""
    if not sentences or budget <= 0:
        return ""
    return transcript_for(reduce_sentences(list(sentences), int(budget),
                                           language_of(language)))


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


def points_in(text):
    """The bullet lines of an answer, in order.

    How many notes a reading pass produced, which is the number that says
    whether a chunk contributed anything. Counting them is not parsing them:
    this is deliberately cheaper and looser than :func:`parse`, because it is
    asked of every pass including the ones that went wrong."""
    return [line for line in str(text or "").splitlines()
            if _BULLET.match(line)]


def point_starts(text):
    """The minute each bullet of an answer carries, in seconds; None when a
    bullet carries none.

    What a reading pass covered, which is a different question from what the
    finished page covers: between the two sits every fold, and the difference
    is where a recording goes missing."""
    found = []
    for line in points_in(text):
        stripped = _BULLET.match(line).group(1)
        clock = _CLOCK.match(stripped) or _ANY_CLOCK.search(stripped)
        found.append(_clock_seconds(clock.group(1)) if clock else None)
    return found


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


def has_written_headings(answer, language="it"):
    """Whether the answer carries at least one heading :func:`parse`
    recognises for this language.

    The difference between a document in the right shape and text
    :func:`parse` only kept because keeping it beats discarding it: the merge
    pass trusts its own answer no further than this, because accepting a
    degenerate one there would throw away drafts that were each individually
    fine."""
    language = language_of(language)
    for line in without_thinking(answer).splitlines():
        heading = _HEADING.match(line)
        if heading:
            written = next((group for group in heading.groups()
                            if group is not None), None)
            if written is not None and _field_of(written, language) is not None:
                return True
            continue
        labelled = _LABELLED.match(line)
        if labelled and _field_of(labelled.group(1), language) is not None:
            return True
    return False


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
    text = without_thinking(answer)
    if not text:
        return Sections()

    collected = {"abstract": [], "points": [], "decisions": [], "actions": [],
                 "keywords": []}
    field, matched = None, False
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            written = next(group for group in heading.groups()
                           if group is not None)
            found = _field_of(written, language)
            field = found
            matched = matched or found is not None
            continue
        if not line.strip():
            continue
        labelled = _LABELLED.match(line)
        if labelled:
            found = _field_of(labelled.group(1), language)
            if found is not None:
                # The heading and its first line arrived together: taken as a
                # heading alone, the content after the colon would need a
                # bullet of its own to survive into a list field, and it has
                # none — this is the one place a list field accepts an
                # unbulleted line, because the label just proved what it is.
                field, matched = found, True
                content = labelled.group(2).strip()
                if content and content not in scaffold(language):
                    collected[field].append(content)
                continue
        if field is None:
            continue
        bullet = _BULLET.match(line)
        content = bullet.group(1) if bullet else line.strip()
        # A line the model copied out of the instructions is not something it
        # wrote about the recording. Small models reproduce the scaffold they
        # were given, and "one paragraph of three or four lines" arriving as
        # the abstract is a page that looks finished and says nothing. It is
        # the instructions that are checked against, not the whole prompt: a
        # reduce prompt carries the partial summaries too, and those are
        # exactly the content that is supposed to come back.
        if content in scaffold(language):
            continue
        if field == "abstract":
            collected["abstract"].append(content)
        elif bullet:
            collected[field].append(content)

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


def _section_lines(text, language):
    """One entry per line, a bullet marker stripped where there is one.

    Unlike :func:`parse`, an unbulleted line is kept: with only one field
    possible there is nowhere else for it to be mistaken for, which is the
    ambiguity a bullet marker exists to resolve in the combined answer."""
    lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        bullet = _BULLET.match(line)
        content = bullet.group(1) if bullet else line.strip()
        if content and content not in scaffold(language):
            lines.append(content)
    return lines


def parse_section(field, answer, language="it", prompt=None):
    """Read back one single-section answer: the empty marker, a paragraph, or
    a list, depending on ``field``.

    There is no heading to recognise here — the question already said which
    field this is — so this is simpler than :func:`parse` on purpose, and
    cannot lose a section into the wrong one: that failure needs two fields to
    confuse, and a single-section answer only ever has one."""
    language = language_of(language)
    usable = usable_answer(answer, prompt)
    if not usable or is_empty_section(usable):
        return "" if field == "abstract" else []
    lines = _section_lines(usable, language)
    return " ".join(lines).strip() if field == "abstract" else lines


def sections_from_drafts(drafts):
    """The four single-section drafts, taken as the answer with no merge
    pass: used when there is at most one to check for overlap, where asking a
    model to compare a section against itself would only add a chance to go
    wrong for nothing."""
    return Sections(
        abstract=drafts.get("abstract") or "",
        points=[_point(line) for line in drafts.get("points") or []],
        decisions=[_point(line) for line in drafts.get("decisions") or []],
        actions=[_point(line) for line in drafts.get("actions") or []],
    )


def draft_text(drafts, language):
    """The drafts as one block, each under its own heading: the input to the
    merge pass, and — when a merge was skipped or failed — what a diagnostic
    message shows for "what the model answered"."""
    words = HEADINGS.get(language_of(language), HEADINGS["en"])
    parts = []
    for field in SECTION_FIELDS:
        content = drafts.get(field)
        if not content:
            continue
        body = content if field == "abstract" else "\n".join(
            f"- {line}" for line in content)
        parts.append(f"## {words[field]}\n{body}")
    return "\n\n".join(parts)


#: An opening narration with no end: the model was still thinking when the
#: budget ran out.
_UNFINISHED_THOUGHT = re.compile(r"<think>(?!.*</think>)", re.DOTALL | re.IGNORECASE)


def thought_without_answering(answer):
    """Whether the model spent its whole allowance narrating.

    The budget is the *whole* budget, so a model that reasons for all of it is
    cut off before the answer begins — and what comes back parses to nothing,
    which looks exactly like a model too small for the job. It is worth
    telling the two apart: one of them is fixed by asking again with room."""
    return bool(_UNFINISHED_THOUGHT.search(str(answer or "")))


def usable_answer(answer, prompt=None):
    """What is left of an answer once the model's echo of the question is gone.

    Applied to every answer, not only to the ones that arrive in an
    unrecognisable shape. A small model very often opens by restating what it
    was asked — sometimes that is all it does — and in a map/reduce that
    matters twice over: the echo is charged against the answer budget, so the
    real content is what gets truncated, and whatever survives is fed to the
    level above as if it were a summary."""
    return _not_an_echo(without_thinking(answer), prompt)


def without_thinking(text):
    """The answer with the model's narration gone, finished or not.

    A narration with no end is not a preamble to an answer: it is the whole of
    what there was room for, and everything from it on is thinking aloud."""
    text = _THINK.sub("", str(text or ""))
    unfinished = _UNFINISHED_THOUGHT.search(text)
    return (text[:unfinished.start()] if unfinished else text).strip()


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
    # The marker as it was sent, and as a model that dropped the dashes writes
    # it back. Recognising only the exact spelling would miss most echoes.
    marker = next((found for found in (FENCE_START, FENCE_START.strip("-"))
                   if found in text), None)
    echoed = marker is not None
    if echoed:
        text = text.split(marker, 1)[0].strip()
    if prompt:
        # Compared with the whitespace flattened out of both, because a model
        # reflows what it copies: two lines of the question come back as one,
        # and matched literally that would read as an original sentence.
        flat = " ".join(prompt.split())
        kept, dropping = [], True
        for line in text.splitlines():
            packed = " ".join(line.split())
            if dropping and (not packed or packed in flat):
                echoed = echoed or bool(packed)
                continue
            dropping = False
            kept.append(line)
        text = "\n".join(kept).strip()
    return "" if echoed and len(text) < MIN_ANSWER else text


def single_prompt(sentences, language, length=None):
    """The one-pass prompt: the whole transcript, and what to write about it."""
    words = HEADINGS.get(language_of(language), HEADINGS["en"])
    detail = detail_for(language, length)
    return prompts_for(language)["single"].format(
        transcript=transcript_for(sentences),
        fence_start=FENCE_START, fence_end=FENCE_END,
        abstract=words["abstract"], points=words["points"],
        decisions=words["decisions"], actions=words["actions"],
        abstract_detail=detail["abstract"], points_detail=detail["points"])


def note_headings(language, types=None):
    """The headings a reading pass is asked for, each with what belongs there.

    Generated rather than written into the template, because which kinds are
    asked for is a setting: the block is the only part of the prompt that
    changes between two runs over the same recording, and :func:`scaffold`
    has to be told so."""
    from . import notes

    language = language_of(language)
    lines = []
    for kind in (types or notes.DEFAULT_TYPES):
        lines.append(f"## {notes.heading_of(kind, language)}")
        lines.append(notes.INSTRUCTIONS.get(language, notes.INSTRUCTIONS["en"])
                     .get(kind, ""))
    return "\n".join(lines)


def map_overhead(language, types=None):
    """How many tokens of a reading prompt are not the transcript.

    Measured rather than assumed. The default guess of four hundred was right
    for a prompt of four lines; with the headings and a worked example it is
    more than twice that, and a chunk sized against the old figure overflows
    the window by the difference — silently, because what overflows is the end
    of the transcript and nothing counts it."""
    empty = map_prompt([], language, 1, 1, types)
    return estimate_tokens(empty, language)


def map_prompt(sentences, language, part, total, types=None):
    """The prompt for one chunk of a transcript too long to read at once.

    It carries a worked example, and that is not decoration. Told to put the
    minute on every row, the first reading pass of every measured run put it
    on none: eight notes, none of them placed, whatever the chunk held and
    however much room it was given. A small model copies the shape of an
    example far more reliably than it obeys a sentence describing one.

    The example shows two of the headings, and it is fixed text. While every
    kind is asked for that is a sample; the day a caller asks for a subset
    that leaves one of the two out, the example will be showing a heading the
    rules above forbid, and it will have to be built from the kinds like the
    block is."""
    prompts = prompts_for(language)
    speakers = any(getattr(line, "speaker", None) for line in sentences)
    return prompts["map"].format(
        part=part, total=total, transcript=transcript_for(sentences),
        sections_block=note_headings(language, types),
        examples=prompts["map_example"].format(fence_start=FENCE_START,
                                               fence_end=FENCE_END),
        speaker_rule=prompts["map_speaker_rule"] if speakers else "",
        fence_start=FENCE_START, fence_end=FENCE_END)


def _numbered(partials):
    """The partial summaries as one block, each under its own marker."""
    return "\n\n".join(f"--- {index} ---\n{part.strip()}"
                       for index, part in enumerate(partials, start=1))


def _evidence_block(evidence, language):
    """The extract of the transcript a reduce pass checks itself against."""
    if not evidence:
        return ""
    return prompts_for(language)["evidence"].format(
        evidence=evidence, fence_start=FENCE_START, fence_end=FENCE_END)


def reduce_partial_prompt(partials, language, evidence=None):
    """The prompt for a reduce pass that is not the last one.

    An intermediate level merges and deduplicates; it must not write the
    finished document, because a level above it still has to fold what comes
    out with the answers of its siblings, and headings would arrive there as
    material to summarise rather than as an answer."""
    return prompts_for(language)["reduce_partial"].format(
        partials=_numbered(partials),
        evidence=_evidence_block(evidence, language))


def reduce_prompt(partials, language, evidence=None, length=None):
    """The prompt that turns the chunk summaries into one summary.

    The root of the tree, and the only level that writes the page — which is
    why the asked length arrives here and nowhere below it: the levels
    underneath are merging notes, and a merge that keeps less than it was
    given loses the recording rather than shortening the page."""
    words = HEADINGS.get(language_of(language), HEADINGS["en"])
    detail = detail_for(language, length)
    return prompts_for(language)["reduce"].format(
        partials=_numbered(partials),
        evidence=_evidence_block(evidence, language),
        abstract=words["abstract"], points=words["points"],
        decisions=words["decisions"], actions=words["actions"],
        abstract_detail=detail["abstract"], points_detail=detail["points"])


def _section_instruction(field, language):
    return SECTION_INSTRUCTIONS.get(
        language_of(language), SECTION_INSTRUCTIONS["en"])[field]


def section_prompt(field, sentences, language):
    """The one-pass prompt for a single section, asked on its own.

    Everything else about the one-pass path is unchanged: the same
    transcript, the same fence. Only the question at the end differs from one
    field to the next, which is what lets a sequence of these calls reuse the
    transcript's own share of the prompt from the model's own cache instead of
    reading it four times over."""
    return prompts_for(language)["section_single"].format(
        transcript=transcript_for(sentences),
        fence_start=FENCE_START, fence_end=FENCE_END,
        instruction=_section_instruction(field, language), empty=EMPTY_SECTION)


def section_reduce_prompt(field, partials, language, evidence=None):
    """The reduce-root prompt for a single section, asked on its own."""
    return prompts_for(language)["section_reduce"].format(
        partials=_numbered(partials),
        evidence=_evidence_block(evidence, language),
        instruction=_section_instruction(field, language), empty=EMPTY_SECTION)


def merge_prompt(drafts, language):
    """The prompt that checks the four single-section drafts against each
    other, and writes the one document a reader sees.

    It reuses the combined heading format on purpose: whatever comes back is
    read with the same :func:`parse` the combined path uses, headings
    misplaced by a weak model included — a merge pass gets no fewer
    protections than a first draft would have."""
    words = HEADINGS.get(language_of(language), HEADINGS["en"])
    return prompts_for(language)["merge"].format(
        draft=draft_text(drafts, language),
        abstract=words["abstract"], points=words["points"],
        decisions=words["decisions"], actions=words["actions"])
