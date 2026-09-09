/* The whole interface: no framework, no build step, one file.

   Two kinds of keyword set live side by side here. The ones the server
   installed are fetched from /api/vocabularies and only ever selected by name;
   the ones a visitor writes stay in this browser's localStorage and are sent,
   as text, with the job that uses them. Nothing a visitor writes is stored on
   the server, so two people sharing an instance never see each other's sets. */

const STORE_KEY = "audio-transcriber.vocabularies";
const POLL_MS = 3000;

//: Below this many installed sets the list is short enough to read; the filter
//: and the count would be furniture.
const FILTER_FROM = 6;

/* Every URL is built relative to the page, never rooted at "/", so the same
   files work whether the app is served at the root or under a prefix by a
   reverse proxy (https://example.org/transcriber/). The proxy only has to
   redirect the prefix without its trailing slash to the one with it. */
const api = (path) => new URL(`api/${path}`, document.baseURI).href;

const I18N = {
  en: {
    tagline: "Local transcription. Nothing leaves this machine.",
    eyebrow: "Recordings and transcripts",
    new_transcription_note: "Upload a recording or record one here. It is transcribed on this machine, in the background: nothing is sent anywhere.",
    jobs_note: "One transcription at a time. Leaving this page does not stop anything.",
    library_note: "Every finished transcription, with its recording, its text and your notes.",
    search_label: "Search the transcripts",
    notes_label: "Notes on this recording",
    remove_from_list: "remove from the list",
    confirm_remove_job: "Remove this job from the list?",
    confirm_remove_job_body: "\"{title}\" disappears from Jobs.",
    confirm_remove_job_kept: "The transcription stays in the library: nothing is deleted.",
    confirm_remove_job_failed: "This job produced no transcription, so there is nothing to keep.",
    confirm_remove_job_ok: "Remove from the list",
    confirm_delete_entry: "Delete this recording?",
    confirm_delete_entry_body: "\"{title}\" is deleted: the transcript, the timestamps, your notes and the recording itself.",
    confirm_delete_entry_detail: "This cannot be undone.",
    confirm_delete_entry_ok: "Delete for good",
    confirm_delete_set: "Delete this keyword set?",
    confirm_delete_set_body: "\"{name}\" is removed from this browser.",
    confirm_delete_set_ok: "Delete the set",
    rename_title: "Rename",
    rename_label: "Title",
    rename_ok: "Rename",
    colophon: "audio-transcriber {version} — {sets} keyword sets installed. Everything runs on this machine.",

    new_transcription: "New transcription",
    tab_file: "Upload a file",
    tab_record: "Record",
    choose_file: "Choose a file",
    or_drop: "or drop it here (audio or video).",
    record_start: "Record",
    record_stop: "Stop",
    record_hint: "Records from your microphone, in this browser. Nothing is sent until you start the transcription.",
    recording_ready: "Recording ready: {duration}. Start the transcription, or record again.",
    mic_unavailable: "This browser will not give a page the microphone unless the page is local or served over HTTPS. Upload a file instead, or reach this server through an SSH tunnel.",
    mic_denied: "The microphone was refused: {error}",
    title: "Title",
    model: "Model",
    language: "Spoken language",
    auto: "detect it",
    auto_model: "automatic ({model})",
    diarize: "Who said what",
    output_legend: "What do you want out of it?",
    output_text: "Just the text",
    output_text_note: "Paragraphs, broken where the speech pauses. No timestamps, nobody named: the transcript to read or to paste somewhere.",
    output_speakers: "The text, with who said what",
    output_speakers_note: "The same text arranged as a dialogue, one block per turn. Needs diarization, which runs on the CPU and takes a while.",
    output_subtitles: "Subtitles",
    output_subtitles_note: "Cues with times, cut to be readable, saved with the entry as .srt or .vtt. Tick \"who said what\" as well and a change of voice is marked in them.",
    sub_legend: "How the subtitles are cut",
    sub_preset: "Subtitles",
    sub_note: "How subtitles are cut, if you want them. The cues exist either way: an entry can be downloaded as .srt or .vtt later, with other numbers.",
    sub_chars: "Characters per subtitle line",
    sub_words: "Words per subtitle",
    sub_save_srt: "Keep an .srt with the entry",
    sub_save_vtt: "Keep a .vtt with the entry",
    sub_preset_numbers: "{chars} x {lines}, {cps} CPS",
    sub_from_preset: "from the preset",
    download_srt: "subtitles (.srt)",
    download_vtt: "subtitles (.vtt)",
    diarize_not_installed: "Needs pyannote, which is not installed on this machine: pip install \"audio-transcriber-ov[diarize]\"",
    diarize_no_model: "pyannote is installed but has no model: set HUGGINGFACE_TOKEN on the server, or put a local config in place.",
    speakers: "Speakers, if known",
    keywords: "Keyword sets",
    keywords_help: "Terms the transcription should get right: names, acronyms, jargon. " +
      "Pick the sets that fit this recording.",
    installed_sets: "Installed on this machine",
    filter_sets: "Filter the sets",
    sets_total: "{total} sets installed",
    sets_selected: "{total} sets installed · selected: {selected}",
    sets_filtered: "{shown} of {total} sets · selected: {selected}",
    no_matching_sets: "No set matches \"{query}\". The ones you have ticked stay visible.",
    my_sets: "My sets",
    new_set: "new set",
    my_sets_help: "Your sets stay in this browser and are sent only with the recordings that use them.",
    no_installed: "No set is installed. Whoever set this machine up can add some with 'audio-transcriber vocab new'.",
    no_mine: "You have not written any set yet.",
    prompt_size: "{chars} of {limit} characters used.",
    prompt_too_long: "Too long: {chars} characters, {limit} at most. Whisper ignores the rest.",
    start: "Start transcribing",
    jobs: "Jobs",
    busy_note: "A transcription is running: everything else is off until it finishes, or you stop it.",
    busy_note_summary: "A summary is being written: everything else is off until it finishes, or you stop it.",
    busy_why: "Not while a transcription is running.",
    no_jobs: "Nothing running.",
    library: "Library",
    library_empty: "No recording has been transcribed yet.",
    search_placeholder: "search the transcripts",
    no_results: "Nothing matches \"{query}\".",
    edit_set: "Keyword set",
    set_title: "Name",
    set_terms: "Terms",
    set_help: "One list of terms, separated by commas or newlines. A few dozen at most.",
    set_placeholder: "risk assessment, asset, remediation plan, CMDB",
    cancel: "Cancel",
    save: "Save",
    edit: "edit",
    remove: "delete",
    preview: "preview",
    hide: "hide",
    download: "Transcript",
    download_json: "Timestamps",
    close: "Close",
    open: "Open",
    view: "view",
    transcript: "Transcript",
    segments: "Timestamps",
    notes: "Notes",
    summary: "Summary",
    summary_none: "No summary yet. The transcript is summarised on this machine \u2014 nothing is sent anywhere.",
    summary_engine: "Written by",
    summary_length: "How much to keep",
    summary_short: "short",
    summary_medium: "medium",
    summary_long: "long",
    summary_run: "Summarise",
    summary_again: "Summarise again",
    summary_delete: "delete the summary",
    download_summary: "summary (.md)",
    summary_queued: "In the queue, behind whatever is already running.",
    summary_running: "Being written\u2026 {stage}",
    summary_failed: "Could not summarise: {error}",
    summary_engine_extractive: "no model: the sentences that carry the transcript",
    summary_engine_openvino: "a local model, on this machine's Intel device",
    confirm_delete_summary: "Delete this summary?",
    confirm_delete_summary_body: "The summary of \"{title}\" is deleted.",
    confirm_delete_summary_detail: "The transcript is untouched, so you can ask for another one.",
    confirm_delete_summary_ok: "Delete the summary",
    no_segments: "This entry has no timestamps.",
    notes_placeholder: "What was decided, what to do next, who owes what.",
    save_notes: "Save the notes",
    notes_saved: "Saved.",
    notes_failed: "Could not save: {error}",
    rename: "rename",
    delete_entry: "delete",
    has_notes: "notes",
    queued: "queued",
    running: "transcribing",
    stage_summary_selecting: "choosing what matters",
    stage_summary_reading: "reading the transcript",
    stage_summary_writing: "writing the summary",
    done: "done",
    failed: "failed",
    cancelled: "cancelled",
    stage_starting: "starting",
    stage_decoded: "audio decoded",
    stage_loading_model: "loading the model",
    stage_converting_model: "converting the model",
    stage_compiling_model: "compiling for the device",
    stage_transcribing: "transcribing",
    stage_diarizing: "working out who said what",
    stage_laying_out: "laying out the text",
    take_out_of_queue: "take out of the queue",
    stop_job: "stop",
    confirm_stop_job: "Stop this transcription?",
    confirm_stop_job_body: "\"{title}\" stops and nothing reaches the library.",
    confirm_stop_job_detail: "It stops at the engine's next progress report - seconds with faster-whisper, and not until the whole file is done with OpenVINO, which reports none. The recording stays on the server either way, so it can be queued again.",
    confirm_stop_job_ok: "Stop it",
    clear_finished: "clear the finished",
    confirm_clear_finished: "Clear the finished jobs?",
    confirm_clear_finished_body: "{count} rows disappear from Jobs.",
    confirm_clear_finished_detail: "The transcriptions stay in the library: nothing is deleted.",
    confirm_clear_finished_ok: "Clear the list",
    level_label: "Input level",
    recording_silent: "That recording never rose above silence: check that the right microphone is being used before trusting the next one.",
    no_file: "Choose a file, or record something, first.",
    uploading: "Uploading...",
    terms: "{n} terms",
    words: "{n} words",
    upload_failed: "Upload failed: {error}",
  },
  it: {
    tagline: "Trascrizione locale. Niente esce da questa macchina.",
    eyebrow: "Registrazioni e trascrizioni",
    new_transcription_note: "Carica una registrazione o registrala qui. Viene trascritta su questa macchina, in background: non viene inviata da nessuna parte.",
    jobs_note: "Una trascrizione alla volta. Se lasci la pagina non si ferma niente.",
    library_note: "Tutte le trascrizioni fatte, con la registrazione, il testo e le tue note.",
    search_label: "Cerca nelle trascrizioni",
    notes_label: "Note su questa registrazione",
    remove_from_list: "togli dalla lista",
    confirm_remove_job: "Togliere questo lavoro dalla lista?",
    confirm_remove_job_body: "\"{title}\" sparisce dall'elenco dei lavori.",
    confirm_remove_job_kept: "La trascrizione resta in libreria: non viene cancellato niente.",
    confirm_remove_job_failed: "Questo lavoro non ha prodotto nessuna trascrizione, quindi non c'e' niente da conservare.",
    confirm_remove_job_ok: "Togli dalla lista",
    confirm_delete_entry: "Eliminare questa registrazione?",
    confirm_delete_entry_body: "Viene eliminata \"{title}\": la trascrizione, i timestamp, le tue note e la registrazione stessa.",
    confirm_delete_entry_detail: "L'operazione non e' reversibile.",
    confirm_delete_entry_ok: "Elimina definitivamente",
    confirm_delete_set: "Eliminare questo set di parole chiave?",
    confirm_delete_set_body: "\"{name}\" viene rimosso da questo browser.",
    confirm_delete_set_ok: "Elimina il set",
    rename_title: "Rinomina",
    rename_label: "Titolo",
    rename_ok: "Rinomina",
    colophon: "audio-transcriber {version} — {sets} set di parole chiave installati. Tutto gira su questa macchina.",

    new_transcription: "Nuova trascrizione",
    tab_file: "Carica un file",
    tab_record: "Registra",
    choose_file: "Scegli un file",
    or_drop: "oppure trascinalo qui (audio o video).",
    record_start: "Registra",
    record_stop: "Ferma",
    record_hint: "Registra dal tuo microfono, in questo browser. Niente viene inviato finche' non avvii la trascrizione.",
    recording_ready: "Registrazione pronta: {duration}. Avvia la trascrizione, o registra di nuovo.",
    mic_unavailable: "Questo browser non da' il microfono a una pagina che non sia locale o servita in HTTPS. Carica un file, oppure raggiungi il server con un tunnel SSH.",
    mic_denied: "Microfono negato: {error}",
    title: "Titolo",
    model: "Modello",
    language: "Lingua parlata",
    auto: "rilevala",
    auto_model: "automatico ({model})",
    diarize: "Chi dice cosa",
    output_legend: "Cosa vuoi ottenere?",
    output_text: "Solo il testo",
    output_text_note: "Paragrafi, spezzati dove il parlato si interrompe. Nessun timestamp, nessun nome: la trascrizione da leggere o da incollare altrove.",
    output_speakers: "Il testo, con chi dice cosa",
    output_speakers_note: "Lo stesso testo disposto come un dialogo, un blocco per battuta. Richiede la diarizzazione, che gira su CPU e ci mette un po'.",
    output_subtitles: "Sottotitoli",
    output_subtitles_note: "Battute con i tempi, tagliate per essere leggibili, salvate con la voce in .srt o .vtt. Spunta anche \"chi dice cosa\" e il cambio di voce viene segnato dentro.",
    sub_legend: "Come vengono tagliati i sottotitoli",
    sub_preset: "Sottotitoli",
    sub_note: "Come vengono tagliati i sottotitoli, se li vuoi. Le battute ci sono comunque: una voce si puo' scaricare in .srt o .vtt anche dopo, con altri numeri.",
    sub_chars: "Caratteri per riga di sottotitolo",
    sub_words: "Parole per sottotitolo",
    sub_save_srt: "Tieni un .srt nella voce",
    sub_save_vtt: "Tieni un .vtt nella voce",
    sub_preset_numbers: "{chars} x {lines}, {cps} CPS",
    sub_from_preset: "dal preset",
    download_srt: "sottotitoli (.srt)",
    download_vtt: "sottotitoli (.vtt)",
    diarize_not_installed: "Richiede pyannote, che su questa macchina non e' installato: pip install \"audio-transcriber-ov[diarize]\"",
    diarize_no_model: "pyannote c'e' ma manca il modello: imposta HUGGINGFACE_TOKEN sul server, oppure metti un config locale.",
    speakers: "Speaker, se noti",
    keywords: "Set di parole chiave",
    keywords_help: "I termini che la trascrizione deve azzeccare: nomi, sigle, gergo. " +
      "Scegli i set adatti a questa registrazione.",
    installed_sets: "Installati su questa macchina",
    filter_sets: "Filtra i set",
    sets_total: "{total} set installati",
    sets_selected: "{total} set installati · selezionati: {selected}",
    sets_filtered: "{shown} set su {total} · selezionati: {selected}",
    no_matching_sets: "Nessun set corrisponde a \"{query}\". Quelli che hai spuntato restano visibili.",
    my_sets: "I miei set",
    new_set: "nuovo set",
    my_sets_help: "I tuoi set restano in questo browser e viaggiano solo con le registrazioni che li usano.",
    no_installed: "Nessun set installato. Chi ha configurato la macchina puo' aggiungerne con 'audio-transcriber vocab new'.",
    no_mine: "Non hai ancora scritto nessun set.",
    prompt_size: "{chars} caratteri su {limit}.",
    prompt_too_long: "Troppo lungo: {chars} caratteri, il massimo e' {limit}. Whisper ignora il resto.",
    start: "Avvia la trascrizione",
    jobs: "Lavori",
    busy_note: "C'\u00e8 una trascrizione in corso: tutto il resto \u00e8 sospeso finch\u00e9 non finisce, o finch\u00e9 non la interrompi.",
    busy_note_summary: "Si sta scrivendo un riassunto: tutto il resto \u00e8 sospeso finch\u00e9 non finisce, o finch\u00e9 non lo interrompi.",
    busy_why: "Non mentre una trascrizione \u00e8 in corso.",
    no_jobs: "Niente in corso.",
    library: "Libreria",
    library_empty: "Nessuna registrazione trascritta finora.",
    search_placeholder: "cerca nelle trascrizioni",
    no_results: "Nessun risultato per \"{query}\".",
    edit_set: "Set di parole chiave",
    set_title: "Nome",
    set_terms: "Termini",
    set_help: "Un elenco di termini, separati da virgole o a capo. Qualche decina al massimo.",
    set_placeholder: "analisi dei rischi, asset, piano di remediation, CMDB",
    cancel: "Annulla",
    save: "Salva",
    edit: "modifica",
    remove: "elimina",
    preview: "anteprima",
    hide: "nascondi",
    download: "Trascrizione",
    download_json: "Timestamp",
    close: "Chiudi",
    open: "Apri",
    view: "vedi",
    transcript: "Trascrizione",
    segments: "Timestamp",
    notes: "Note",
    summary: "Riassunto",
    summary_none: "Nessun riassunto. La trascrizione viene riassunta su questa macchina: non esce niente da qui.",
    summary_engine: "Scritto da",
    summary_length: "Quanto tenere",
    summary_short: "corto",
    summary_medium: "medio",
    summary_long: "lungo",
    summary_run: "Riassumi",
    summary_again: "Riassumi di nuovo",
    summary_delete: "elimina il riassunto",
    download_summary: "riassunto (.md)",
    summary_queued: "In coda, dietro a quello che sta gia' girando.",
    summary_running: "Lo sto scrivendo\u2026 {stage}",
    summary_failed: "Non riassunto: {error}",
    summary_engine_extractive: "nessun modello: le frasi che reggono la trascrizione",
    summary_engine_openvino: "un modello locale, sul dispositivo Intel di questa macchina",
    confirm_delete_summary: "Eliminare questo riassunto?",
    confirm_delete_summary_body: "Il riassunto di \"{title}\" viene eliminato.",
    confirm_delete_summary_detail: "La trascrizione resta intatta: puoi chiederne un altro quando vuoi.",
    confirm_delete_summary_ok: "Elimina il riassunto",
    no_segments: "Questa voce non ha timestamp.",
    notes_placeholder: "Cosa e' stato deciso, cosa fare, chi deve cosa.",
    save_notes: "Salva le note",
    notes_saved: "Salvate.",
    notes_failed: "Non salvate: {error}",
    rename: "rinomina",
    delete_entry: "elimina",
    has_notes: "note",
    queued: "in coda",
    running: "in corso",
    stage_summary_selecting: "scelta di cosa conta",
    stage_summary_reading: "lettura della trascrizione",
    stage_summary_writing: "scrittura del riassunto",
    done: "completata",
    failed: "fallita",
    cancelled: "annullata",
    stage_starting: "avvio",
    stage_decoded: "audio decodificato",
    stage_loading_model: "caricamento del modello",
    stage_converting_model: "conversione del modello",
    stage_compiling_model: "compilazione per il dispositivo",
    stage_transcribing: "trascrizione",
    stage_diarizing: "chi ha detto cosa",
    stage_laying_out: "impaginazione del testo",
    take_out_of_queue: "togli dalla coda",
    stop_job: "ferma",
    confirm_stop_job: "Fermo questa trascrizione?",
    confirm_stop_job_body: "\"{title}\" si ferma e in libreria non arriva nulla.",
    confirm_stop_job_detail: "Si ferma al prossimo avanzamento riportato dal motore: pochi secondi con faster-whisper, e non prima della fine del file con OpenVINO, che non ne riporta nessuno. La registrazione resta sul server in entrambi i casi, quindi si puo' rimettere in coda.",
    confirm_stop_job_ok: "Ferma",
    clear_finished: "svuota i finiti",
    confirm_clear_finished: "Svuoto i lavori finiti?",
    confirm_clear_finished_body: "{count} righe spariscono da Lavori.",
    confirm_clear_finished_detail: "Le trascrizioni restano in libreria: non si cancella nulla.",
    confirm_clear_finished_ok: "Svuota l'elenco",
    level_label: "Livello in ingresso",
    recording_silent: "Quella registrazione non e' mai salita sopra il silenzio: controlla che sia il microfono giusto prima di fidarti della prossima.",
    no_file: "Scegli prima un file, o registra qualcosa.",
    uploading: "Caricamento...",
    terms: "{n} termini",
    words: "{n} parole",
    upload_failed: "Caricamento fallito: {error}",
  },
};

let lang = "en";
let status = null;
let installed = [];
let selectedFile = null;
let polling = null;
let openEntryId = null;

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  for (const child of [].concat(children)) {
    if (child) node.append(child);
  }
  return node;
};

function t(key, values = {}) {
  const text = (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
  return text.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "");
}

/* Every destructive action goes through here: a dialog that names what will
   happen, in this page's own type rather than the browser's alert box, and
   says plainly what is NOT touched — "forget this job" once read as "delete
   the transcription", which is exactly the confusion worth spelling out.
   Resolves to false when refused, to the typed string when it asks for one. */
function ask({ title, body, detail = "", confirmLabel, danger = true, input = null }) {
  const dialog = $("ask");
  $("ask-title").textContent = title;
  $("ask-body").textContent = body;
  $("ask-detail").textContent = detail;
  $("ask-detail").hidden = !detail;
  $("ask-cancel").textContent = t("cancel");
  const okButton = $("ask-ok");
  okButton.textContent = confirmLabel;
  okButton.classList.toggle("danger", danger);
  okButton.classList.toggle("send", !danger);

  const field = $("ask-field");
  field.hidden = !input;
  if (input) {
    $("ask-input-label").textContent = input.label;
    $("ask-input").value = input.value || "";
  }

  return new Promise((resolve) => {
    const finish = (answer) => {
      okButton.removeEventListener("click", onOk);
      $("ask-cancel").removeEventListener("click", onCancel);
      dialog.removeEventListener("close", onCancel);
      dialog.close();
      resolve(answer);
    };
    const onOk = () => finish(input ? $("ask-input").value.trim() || false : true);
    const onCancel = () => finish(false);
    okButton.addEventListener("click", onOk);
    $("ask-cancel").addEventListener("click", onCancel);
    dialog.addEventListener("close", onCancel);
    dialog.showModal();
    (input ? $("ask-input") : $("ask-cancel")).focus();
  });
}

function translatePage() {
  document.documentElement.lang = lang;
  for (const node of document.querySelectorAll("[data-t]")) {
    node.textContent = t(node.dataset.t);
  }
  $("set-text").placeholder = t("set_placeholder");
  $("set-search").placeholder = "";
  $("notes-text").placeholder = t("notes_placeholder");
  $("search").placeholder = t("search_placeholder");
}

function duration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes) return `${minutes}m ${String(total % 60).padStart(2, "0")}s`;
  return `${total}s`;
}

function clock(seconds) {
  const total = Math.max(0, Math.round(seconds || 0));
  const minutes = Math.floor(total / 60);
  return `${String(minutes).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

/* --- the visitor's own sets, kept in this browser --------------------- */

function mySets() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((item) => item && item.title) : [];
  } catch (error) {
    return [];
  }
}

function saveMySets(sets) {
  localStorage.setItem(STORE_KEY, JSON.stringify(sets));
  renderMine();
  updatePromptSize();
}

/* Same rule as vocabularies.terms() on the server: commas win when there are
   any, because such a file wraps mid-term. */
function termCount(text) {
  const lines = (text || "").split("\n").filter((line) => !line.trim().startsWith("#"));
  const prompt = lines.join(" ").replace(/\s+/g, " ").trim();
  const chunks = prompt.includes(",") ? prompt.split(",") : lines;
  return chunks.map((chunk) => chunk.trim().replace(/^[.;\s]+|[.;\s]+$/g, "")).filter(Boolean).length;
}

/* --- the keyword pickers ---------------------------------------------- */

/* One set as a compact cell: the ticked box and its name, then everything
   secondary — what it holds, and the links — on a second, quieter line. The
   cells are laid out in columns, so nineteen of them are a block to scan
   rather than a column to scroll. */
function setRow(key, label, meta, actions, text) {
  const id = `pick-${key.replace(/[^a-z0-9]+/gi, "-")}`;
  const checkbox = el("input", { type: "checkbox", value: key, className: "pick", id });
  checkbox.addEventListener("change", () => {
    updatePromptSize();
    updateSetsCount();
  });
  const preview = el("p", { hidden: true, textContent: text, className: "set-preview" });

  const line = el("span", { className: "meta", textContent: `${meta} · ` });
  const toggle = el("button", { type: "button", className: "link", textContent: t("preview") });
  toggle.addEventListener("click", () => {
    preview.hidden = !preview.hidden;
    toggle.textContent = preview.hidden ? t("preview") : t("hide");
  });
  line.append(toggle);
  for (const action of actions) {
    const button = el("button", { type: "button", className: "link", textContent: action.label });
    button.addEventListener("click", action.run);
    line.append(" · ", button);
  }

  const cell = el("div", { className: "set" }, [
    el("div", { className: "set-head" }, [checkbox, el("label", { htmlFor: id, textContent: label })]),
    line,
    preview,
  ]);
  cell.dataset.search = `${key} ${label} ${meta} ${text}`.toLowerCase();
  return cell;
}

function renderInstalled() {
  const box = $("installed");
  box.textContent = "";
  $("set-search").parentElement.hidden = installed.length < FILTER_FROM;
  if (!installed.length) {
    box.append(el("p", { className: "note", textContent: t("no_installed") }));
    $("sets-count").textContent = "";
    return;
  }
  const preselected = (status && status.defaults.vocabulary) || [];
  for (const item of installed) {
    const meta = [item.name, item.language || "", t("terms", { n: item.terms })]
      .filter(Boolean).join(" · ");
    const node = setRow(item.name, item.title, meta, [], item.text);
    box.append(node);
    if (preselected.includes(item.name)) node.querySelector(".pick").checked = true;
  }
  filterSets();
}

/* Filtering never hides a set you have ticked: a list that quietly drops your
   own selection is how you end up transcribing with a vocabulary you thought
   you had removed. */
function filterSets() {
  const query = $("set-search").value.trim().toLowerCase();
  const cells = [...document.querySelectorAll("#installed .set")];
  let shown = 0;
  for (const cell of cells) {
    const checked = cell.querySelector(".pick").checked;
    const matches = !query || cell.dataset.search.includes(query);
    cell.hidden = !(matches || checked);
    if (!cell.hidden) shown += 1;
  }
  const empty = $("installed").querySelector(".no-match");
  if (empty) empty.remove();
  if (query && !cells.some((cell) => cell.dataset.search.includes(query))) {
    $("installed").append(el("p", { className: "note no-match",
                                    textContent: t("no_matching_sets", { query }) }));
  }
  updateSetsCount(shown);
}

function updateSetsCount(shown = null) {
  const cells = [...document.querySelectorAll("#installed .set")];
  const line = $("sets-count");
  if (cells.length < FILTER_FROM) {
    line.textContent = "";      // a handful of sets counts itself
    return;
  }
  const total = cells.length;
  const selected = cells.filter((cell) => cell.querySelector(".pick").checked).length;
  const visible = shown === null ? cells.filter((cell) => !cell.hidden).length : shown;
  if (visible !== total) line.textContent = t("sets_filtered", { shown: visible, total, selected });
  else if (selected) line.textContent = t("sets_selected", { total, selected });
  else line.textContent = t("sets_total", { total });
}

function renderMine() {
  const box = $("mine");
  const checked = new Set(selectedMine());
  box.textContent = "";
  const sets = mySets();
  if (!sets.length) {
    box.append(el("p", { className: "note", textContent: t("no_mine") }));
    return;
  }
  sets.forEach((item, index) => {
    const node = setRow(`mine:${index}`, item.title, t("terms", { n: termCount(item.text) }), [
      { label: t("edit"), run: () => openEditor(index) },
      {
        label: t("remove"),
        run: async () => {
          const sure = await ask({
            title: t("confirm_delete_set"),
            body: t("confirm_delete_set_body", { name: item.title }),
            confirmLabel: t("confirm_delete_set_ok"),
          });
          if (!sure) return;
          const kept = mySets();
          kept.splice(index, 1);
          saveMySets(kept);
        },
      },
    ], item.text);
    box.append(node);
    if (checked.has(`mine:${index}`)) node.querySelector(".pick").checked = true;
  });
}

function selectedInstalled() {
  return [...document.querySelectorAll("#installed .pick:checked")].map((box) => box.value);
}

function selectedMine() {
  return [...document.querySelectorAll("#mine .pick:checked")].map((box) => box.value);
}

function customText() {
  const sets = mySets();
  return selectedMine()
    .map((key) => sets[Number(key.split(":")[1])])
    .filter(Boolean)
    .map((item) => item.text.trim())
    .filter(Boolean)
    .join("\n");
}

function updatePromptSize() {
  if (!status) return;
  const chosen = new Set(selectedInstalled());
  const installedChars = installed
    .filter((item) => chosen.has(item.name))
    .reduce((total, item) => total + item.chars + 1, 0);
  const chars = installedChars + customText().replace(/\s+/g, " ").trim().length;
  const limit = status.max_prompt_chars;
  const node = $("prompt-size");
  node.textContent = chars > limit
    ? t("prompt_too_long", { chars, limit })
    : t("prompt_size", { chars, limit });
  node.className = chars > limit ? "budget over" : "budget";
}

/* --- the editor dialog ------------------------------------------------ */

let editing = null;

function openEditor(index) {
  const sets = mySets();
  editing = index;
  $("set-title").value = index === null ? "" : sets[index].title;
  $("set-text").value = index === null ? "" : sets[index].text;
  $("set-editor").showModal();
}

$("new-set").addEventListener("click", () => openEditor(null));
$("set-search").addEventListener("input", filterSets);

$("set-form").addEventListener("submit", (event) => {
  if (event.submitter && event.submitter.value === "cancel") return;
  const title = $("set-title").value.trim();
  if (!title) {
    event.preventDefault();
    return;
  }
  const sets = mySets();
  const record = { title, text: $("set-text").value, updated_at: new Date().toISOString() };
  if (editing === null) sets.push(record);
  else sets[editing] = record;
  saveMySets(sets);
});

/* --- choosing what to transcribe: a file, or the microphone ----------- */

function showPane(which) {
  for (const [name, tab, pane] of [["file", "tab-file", "pane-file"],
                                   ["record", "tab-record", "pane-record"]]) {
    $(tab).classList.toggle("on", name === which);
    $(tab).setAttribute("aria-selected", String(name === which));
    $(pane).hidden = name !== which;
  }
}

$("tab-file").addEventListener("click", () => showPane("file"));
$("tab-record").addEventListener("click", () => showPane("record"));

function chooseFile(file, note) {
  selectedFile = file || null;
  $("file-name").textContent = file && !note
    ? `${file.name} (${Math.round(file.size / 1e6)} MB)` : "";
  if (note) $("record-hint").textContent = note;
  if (file && !$("title").value.trim()) {
    $("title").value = file.name.replace(/\.[^.]+$/, "");
  }
}

$("file").addEventListener("change", (event) => chooseFile(event.target.files[0]));
$("diarize").addEventListener("change", () => applyOutput());

/* --- what the run is for ---------------------------------------------- */

function chosenOutput() {
  const picked = document.querySelector('input[name="output"]:checked');
  return picked ? picked.value : "text";
}

/* Put away the controls the chosen answer does not use: a subtitle preset
   next to "just the text" is a control that does nothing, and a control that
   does nothing is a question the form cannot answer. */
function applyOutput() {
  const output = chosenOutput();
  const diarizing = output === "speakers"
    || (output === "subtitles" && $("diarize").checked);
  $("output-note").textContent = t(`output_${output}_note`);
  $("subtitle-fields").hidden = output !== "subtitles";
  $("speakers-field").hidden = !diarizing;
  if (output === "subtitles" && !$("save-srt").checked && !$("save-vtt").checked) {
    // The chosen output is the files, so one is written either way: showing
    // it ticked is more honest than saving an .srt behind an empty box.
    $("save-srt").checked = true;
  }
}

for (const name of ["text", "speakers", "subtitles"]) {
  $(`output-${name}`).addEventListener("change", () => applyOutput());
}

const drop = $("drop");
for (const name of ["dragenter", "dragover"]) {
  drop.addEventListener(name, (event) => {
    event.preventDefault();
    drop.classList.add("over");
  });
}
for (const name of ["dragleave", "drop"]) {
  drop.addEventListener(name, () => drop.classList.remove("over"));
}
drop.addEventListener("drop", (event) => {
  event.preventDefault();
  if (pageBusy) return;      // the zone is a div: it cannot be disabled
  showPane("file");
  chooseFile(event.dataTransfer.files[0]);
});

/* The recorder. getUserMedia only works in a secure context, which for this
   tool means localhost or an SSH tunnel; the button says so rather than
   failing silently. */
let recorder = null;
let recordedChunks = [];
let recordStarted = 0;
let recordTimer = null;
let levelContext = null;
let levelTimer = null;
let loudest = 0;

/* Below this, in the peak of a whole recording, nothing but the noise floor
   ever arrived - the same figure the desktop window uses. */
const SILENCE_PEAK = 0.001;

/* Quietest peak the meter shows. A linear bar is a useless meter: ordinary
   speech peaks at about a tenth of full scale and would barely leave the left
   edge, so a working microphone would look broken. */
const LEVEL_FLOOR_DB = -60;

function levelPercent(peak) {
  if (!peak || peak <= 0) return 0;
  const decibels = 20 * Math.log10(Math.min(1, peak));
  if (decibels <= LEVEL_FLOOR_DB) return 0;
  return Math.round(((decibels - LEVEL_FLOOR_DB) / -LEVEL_FLOOR_DB) * 100);
}

function watchLevel(stream) {
  /* A timer counting up says the browser is recording; it does not say
     anything is arriving. The classic failure is an hour of digital silence
     because the wrong input was picked or the microphone is muted. */
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return;
  loudest = 0;
  levelContext = new AudioCtx();
  const analyser = levelContext.createAnalyser();
  analyser.fftSize = 2048;
  levelContext.createMediaStreamSource(stream).connect(analyser);
  const samples = new Float32Array(analyser.fftSize);
  const meter = $("record-level");
  meter.hidden = false;
  levelTimer = setInterval(() => {
    analyser.getFloatTimeDomainData(samples);
    let peak = 0;
    for (const sample of samples) peak = Math.max(peak, Math.abs(sample));
    loudest = Math.max(loudest, peak);
    const percent = levelPercent(peak);
    meter.firstElementChild.style.width = `${percent}%`;
    meter.setAttribute("aria-valuenow", percent);
  }, 100);
}

function stopWatchingLevel() {
  clearInterval(levelTimer);
  levelTimer = null;
  const meter = $("record-level");
  meter.firstElementChild.style.width = "0%";
  meter.setAttribute("aria-valuenow", 0);
  meter.hidden = true;
  if (levelContext) {
    levelContext.close();
    levelContext = null;
  }
}

function recorderMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  return candidates.find((type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || "";
}

function extensionFor(mimeType) {
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("mp4")) return "m4a";
  return "webm";
}

async function startRecording() {
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    $("record-hint").textContent = t("mic_unavailable");
    $("record-hint").className = "error";
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (failure) {
    $("record-hint").textContent = t("mic_denied", { error: failure.message });
    $("record-hint").className = "error";
    return;
  }
  const mimeType = recorderMimeType();
  recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  recordedChunks = [];
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size) recordedChunks.push(event.data);
  });
  recorder.addEventListener("stop", () => {
    for (const track of stream.getTracks()) track.stop();
    const type = recorder.mimeType || mimeType || "audio/webm";
    const blob = new Blob(recordedChunks, { type });
    const stamp = new Date().toISOString().slice(0, 16).replace(/[-:]/g, "").replace("T", "-");
    const name = `recording-${stamp}.${extensionFor(type)}`;
    const seconds = (Date.now() - recordStarted) / 1000;
    const silent = loudest > 0 && loudest < SILENCE_PEAK;
    chooseFile(new File([blob], name, { type }),
               t("recording_ready", { duration: duration(seconds) }));
    if (silent) {
      /* The file is real and can still be transcribed; it is just very
         probably an hour of nothing. */
      $("record-hint").textContent = t("recording_silent");
      $("record-hint").className = "error";
    }
    const preview = $("record-preview");
    preview.src = URL.createObjectURL(blob);
    preview.hidden = false;
  });
  watchLevel(stream);
  recorder.start();
  recordStarted = Date.now();
  $("record").textContent = t("record_stop");
  $("record").classList.add("recording");
  $("record-hint").className = "note";
  $("record-preview").hidden = true;
  recordTimer = setInterval(() => {
    $("record-time").textContent = clock((Date.now() - recordStarted) / 1000);
  }, 500);
}

function stopRecording() {
  clearInterval(recordTimer);
  recordTimer = null;
  stopWatchingLevel();
  if (recorder && recorder.state !== "inactive") recorder.stop();
  recorder = null;
  $("record").textContent = t("record_start");
  $("record").classList.remove("recording");
}

$("record").addEventListener("click", () => {
  if (recorder) stopRecording();
  else startRecording();
});

/* --- jobs -------------------------------------------------------------- */

function stageLabel(stage) {
  /* The queue reports a message key, e.g. "stage.loading_model". The
     percentage stands still for the whole of a long transcription on an
     engine that cannot report its own progress; the stage does not. */
  if (!stage) return "";
  const key = stage.replace(".", "_");
  return I18N[lang][key] ? t(key) : "";
}

function stateText(job) {
  const stage = job.status === "running" ? stageLabel(job.stage) : "";
  return stage ? `${t(job.status)}: ${stage}` : t(job.status);
}

async function cancelJob(job) {
  /* Waiting jobs go without a question - nothing has happened to them. The
     one that is running is worth asking about: it may be forty minutes in. */
  if (job.status === "running") {
    const sure = await ask({
      title: t("confirm_stop_job"),
      body: t("confirm_stop_job_body", { title: job.title }),
      detail: t("confirm_stop_job_detail"),
      confirmLabel: t("confirm_stop_job_ok"),
    });
    if (!sure) return;
  }
  await fetch(api(`jobs/${job.id}/cancel`), { method: "POST" });
  refreshJobs();
}

/* While a transcription is under way the page offers exactly one action: stop
   it. Everything else -- starting another, recording, summarising, renaming,
   deleting, even clearing the finished rows -- is off until it ends.

   The reason is the machine, not tidiness. This runs on two cores; the queue
   already refuses to transcribe two things at once, and anything else asked
   for meanwhile either waits pointlessly or competes for the same cores and
   makes the transcription slower. Reading stays available: opening an entry
   and downloading its transcript cost nothing and are the obvious thing to do
   while waiting. */
let pageBusy = false;

function applyBusy() {
  const why = pageBusy ? t("busy_why") : "";
  for (const control of $("job-form").querySelectorAll("input, select, textarea, button")) {
    // Something this machine cannot do at all -- "who said what" without
    // pyannote -- is off for good; the end of a transcription must not hand
    // it back.
    if (control.dataset.locked) continue;
    control.disabled = pageBusy;
    control.title = why;
  }
  // The drop zone is a div: it cannot be disabled, so it is dimmed and its
  // handler refuses.
  $("drop").classList.toggle("blocked", pageBusy);
  $("busy-note").hidden = !pageBusy;
  for (const id of ["summary-run", "summary-delete", "notes-save",
                    "viewer-rename", "viewer-delete"]) {
    $(id).disabled = pageBusy;
    $(id).title = why;
  }
}

function setBusy(busy, kind) {
  $("busy-note").textContent = t(kind === "summary" ? "busy_note_summary" : "busy_note");
  if (busy === pageBusy) return;
  pageBusy = busy;
  applyBusy();
}

function renderJobs(jobs) {
  const box = $("jobs");
  box.textContent = "";
  if (!jobs.length) {
    box.append(el("p", { className: "note", textContent: t("no_jobs") }));
    return;
  }
  const finished = jobs.filter((job) => ["done", "failed", "cancelled"].includes(job.status));
  if (finished.length > 1) {
    const clear = el("button", { type: "button", className: "link",
                                 textContent: t("clear_finished"),
                                 disabled: pageBusy, title: pageBusy ? t("busy_why") : "" });
    clear.addEventListener("click", async () => {
      const sure = await ask({
        title: t("confirm_clear_finished"),
        body: t("confirm_clear_finished_body", { count: finished.length }),
        detail: t("confirm_clear_finished_detail"),
        confirmLabel: t("confirm_clear_finished_ok"),
        danger: false,
      });
      if (!sure) return;
      await Promise.all(finished.map((job) =>
        fetch(api(`jobs/${job.id}`), { method: "DELETE" })));
      refreshJobs();
    });
    box.append(el("p", { className: "meta" }, [clear]));
  }
  for (const job of jobs) {
    const facts = [job.model, job.language, job.vocabularies.join(", "),
      job.words ? t("words", { n: job.words }) : "",
      job.elapsed_seconds ? duration(job.elapsed_seconds) : ""].filter(Boolean).join(" · ");
    const state = el("span", { className: `state${job.status === "failed" ? " failed" : ""}`,
                               textContent: stateText(job) });
    const meta = el("div", { className: "meta" }, [state]);
    if (facts) meta.append(` · ${facts}`);
    const actions = el("div", { className: "actions" });
    const row = el("div", { className: "row" }, [
      el("div", {}, [
        el("div", { className: "title", textContent: job.title }),
        meta,
        job.error ? el("div", { className: "error", textContent: job.error }) : null,
      ]),
      actions,
    ]);
    if (job.status === "done" && job.entry_id) {
      const open = el("button", { type: "button", className: "link", textContent: t("view") });
      open.addEventListener("click", () => openEntry(job.entry_id));
      actions.append(open);
    }
    if (job.status === "queued" || job.status === "running") {
      const stop = el("button", { type: "button", className: "link",
                                  textContent: job.status === "running"
                                    ? t("stop_job") : t("take_out_of_queue") });
      stop.addEventListener("click", () => cancelJob(job));
      actions.append(stop);
    }
    if (["done", "failed", "cancelled"].includes(job.status)) {
      const remove = el("button", { type: "button", className: "link",
                                    textContent: t("remove_from_list"),
                                    disabled: pageBusy,
                                    title: pageBusy ? t("busy_why") : "" });
      remove.addEventListener("click", async () => {
        const sure = await ask({
          title: t("confirm_remove_job"),
          body: t("confirm_remove_job_body", { title: job.title }),
          detail: job.entry_id ? t("confirm_remove_job_kept") : t("confirm_remove_job_failed"),
          confirmLabel: t("confirm_remove_job_ok"),
          danger: false,
        });
        if (!sure) return;
        await fetch(api(`jobs/${job.id}`), { method: "DELETE" });
        refreshJobs();
      });
      actions.append(remove);
    }
    if (job.status === "running") {
      row.append(el("div", { className: "bar", role: "progressbar",
                             "aria-valuenow": job.progress }, [
        el("span", { style: `width:${job.progress}%` }),
      ]));
    }
    box.append(row);
  }
}

async function refreshJobs() {
  const data = await fetch(api("jobs")).then((r) => r.json());
  const working = data.jobs.filter((job) => job.status === "queued"
                                            || job.status === "running");
  const busy = working.length > 0;
  // Before the rows are drawn, so they are drawn in the right state.
  setBusy(busy, working.length ? working[working.length - 1].kind : null);
  renderJobs(data.jobs);
  if (busy && !polling) polling = setInterval(refreshJobs, POLL_MS);
  if (!busy && polling) {
    clearInterval(polling);
    polling = null;
    refreshLibrary();
  }
}

/* --- the library ------------------------------------------------------- */

let searchTimer = null;

$("search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refreshLibrary, 250);
});

async function refreshLibrary() {
  const query = $("search").value.trim();
  const url = query ? api(`library?q=${encodeURIComponent(query)}`) : api("library");
  const data = await fetch(url).then((r) => r.json());
  const box = $("library");
  box.textContent = "";
  if (!data.entries.length) {
    box.append(el("p", { className: "note",
      textContent: query ? t("no_results", { query }) : t("library_empty") }));
    return;
  }
  for (const entry of data.entries) {
    const facts = [(entry.created_at || "").slice(0, 16).replace("T", " "),
      duration(entry.duration_seconds), entry.words ? t("words", { n: entry.words }) : "",
      entry.model, (entry.vocabulary || []).join(", "),
      entry.has_notes ? t("has_notes") : ""].filter(Boolean).join(" · ");
    const open = el("button", { type: "button", className: "link", textContent: t("open") });
    open.addEventListener("click", () => openEntry(entry.id));
    box.append(el("div", { className: "row" }, [
      el("div", {}, [
        el("div", { className: "title", textContent: entry.title }),
        el("div", { className: "meta", textContent: facts }),
      ]),
      open,
    ]));
  }
}

/* --- one entry --------------------------------------------------------- */

/* Whether the entry on screen already has a summary. The footer buttons are
   shared between the tabs, so this is what tells "delete the summary" and the
   download link whether they have anything to act on. */
let summaryPresent = false;
let summaryWatch = null;

async function loadSummaryEngines() {
  /* Which engines this machine can actually run. A server with no accelerator
     has only the extractive one, and offering a menu of one would be
     furniture -- so the row is hidden rather than shown half-empty. */
  let engines = [];
  let auto = null;
  try {
    ({ engines, auto } = await fetch(api("summary/engines")).then((r) => r.json()));
  } catch {
    engines = [];
  }
  const select = $("summary-engine");
  select.textContent = "";
  for (const name of engines) {
    const described = I18N[lang][`summary_engine_${name}`];
    select.append(el("option", {
      value: name,
      textContent: described ? `${name} \u2014 ${described}` : name,
    }));
  }
  select.value = auto || (engines[0] || "");
  $("summary-engine").closest(".field").hidden = engines.length < 2;
}

function showSummary(entry) {
  summaryPresent = Boolean((entry.summary || "").trim());
  /* The summary is markdown, and markdown is readable as it stands: rendering
     it would mean shipping a parser to show four headings and a list. */
  $("summary-text").textContent = entry.summary || "";
  $("summary-text").hidden = !summaryPresent;
  $("summary-empty").hidden = summaryPresent;
  $("summary-status").textContent = "";
  $("summary-run").textContent = t(summaryPresent ? "summary_again" : "summary_run");
  $("viewer-download-summary").href =
    api(`library/${encodeURIComponent(entry.id)}/summary.md`);
}

function showViewerTab(which) {
  for (const [name, tab, pane] of [
    ["transcript", "tab-transcript", "viewer-text"],
    ["segments", "tab-segments", "viewer-segments"],
    ["summary", "tab-summary", "viewer-summary"],
    ["notes", "tab-notes", "viewer-notes"],
  ]) {
    $(tab).classList.toggle("on", name === which);
    $(tab).setAttribute("aria-selected", String(name === which));
    $(pane).hidden = name !== which;
  }
  /* Each tab owns its own buttons in the shared footer, so the row never
     offers an action that belongs to a panel nobody is looking at. */
  $("notes-save").hidden = which !== "notes";
  $("summary-run").hidden = which !== "summary";
  $("summary-delete").hidden = which !== "summary" || !summaryPresent;
  $("viewer-download-summary").hidden = which !== "summary" || !summaryPresent;
}

$("tab-transcript").addEventListener("click", () => showViewerTab("transcript"));
$("tab-segments").addEventListener("click", () => showViewerTab("segments"));
$("tab-summary").addEventListener("click", () => showViewerTab("summary"));
$("tab-notes").addEventListener("click", () => showViewerTab("notes"));

function renderSegments(segments) {
  const box = $("viewer-segments");
  box.textContent = "";
  if (!segments.length) {
    box.append(el("p", { className: "note", textContent: t("no_segments") }));
    return;
  }
  const audio = $("viewer-audio");
  for (const segment of segments) {
    const stamp = el("button", { type: "button", className: "stamp",
      textContent: clock(segment.start) });
    stamp.addEventListener("click", () => {
      if (audio.hidden) return;
      audio.currentTime = segment.start || 0;
      audio.play();
    });
    box.append(el("div", { className: "segment" }, [
      stamp,
      el("div", {}, [
        segment.speaker ? el("span", { className: "speaker", textContent: segment.speaker }) : null,
        el("span", { textContent: segment.text }),
      ]),
    ]));
  }
}

async function openEntry(id) {
  const entry = await fetch(api(`library/${encodeURIComponent(id)}`)).then((r) => r.json());
  openEntryId = entry.id;
  const transcription = entry.transcription || {};
  const audio = entry.audio || {};
  $("viewer-title").textContent = entry.title || entry.id;
  $("viewer-meta").textContent = [entry.id, duration(audio.duration_seconds),
    transcription.model, transcription.backend,
    (transcription.vocabulary || []).join(", ")].filter(Boolean).join(" · ");
  $("viewer-text").textContent = entry.transcript || "";
  renderSegments(entry.segments || []);
  $("notes-text").value = entry.notes || "";
  $("notes-status").textContent = "";
  showSummary(entry);
  const player = $("viewer-audio");
  player.hidden = !entry.has_audio;
  player.src = entry.has_audio ? api(`library/${encodeURIComponent(entry.id)}/audio`) : "";
  $("viewer-download").href = api(`library/${encodeURIComponent(entry.id)}/transcript.txt`);
  $("viewer-download-json").href = api(`library/${encodeURIComponent(entry.id)}/transcript.json`);
  $("viewer-download-json").hidden = !(entry.segments || []).length;
  /* Cut on request from the segments, with the preset chosen in the form, so
     an entry transcribed months ago can be cut again with today's numbers. */
  const timed = (entry.segments || []).length > 0;
  const preset = $("subtitle-preset").value;
  for (const kind of ["srt", "vtt"]) {
    const link = $(`viewer-download-${kind}`);
    const query = preset ? `?preset=${encodeURIComponent(preset)}` : "";
    link.href = api(`library/${encodeURIComponent(entry.id)}/subtitles.${kind}${query}`);
    link.hidden = !timed;
  }
  showViewerTab("transcript");
  applyBusy();
  $("viewer").showModal();
}

function closeViewer() {
  const player = $("viewer-audio");
  player.pause();
  player.removeAttribute("src");
  clearInterval(summaryWatch);
  summaryWatch = null;
  $("summary-run").disabled = pageBusy;
  $("viewer").close();
}

async function reloadOpenEntry() {
  const entry = await fetch(api(`library/${encodeURIComponent(openEntryId)}`))
    .then((r) => r.json());
  showSummary(entry);
  showViewerTab("summary");
}

function watchSummaryJob(jobId) {
  /* The summary shares the queue with the transcriptions, so it may sit behind
     an hour of audio: the panel says where it is rather than spinning. The
     watch is dropped when the viewer closes -- nobody is reading it then. */
  clearInterval(summaryWatch);
  summaryWatch = setInterval(async () => {
    let job;
    try {
      job = await fetch(api(`jobs/${jobId}`)).then((r) => r.json());
    } catch {
      return;
    }
    if (job.status === "queued") {
      $("summary-status").textContent = t("summary_queued");
    } else if (job.status === "running") {
      $("summary-status").textContent = t("summary_running",
                                          { stage: stageLabel(job.stage) });
    } else {
      clearInterval(summaryWatch);
      summaryWatch = null;
      $("summary-run").disabled = pageBusy;
      if (job.status === "done") reloadOpenEntry();
      else $("summary-status").textContent = t("summary_failed",
                                                { error: job.error || job.status });
    }
  }, POLL_MS);
}

$("summary-run").addEventListener("click", async () => {
  $("summary-run").disabled = true;
  $("summary-status").textContent = t("summary_queued");
  const response = await fetch(api(`library/${encodeURIComponent(openEntryId)}/summary`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ engine: $("summary-engine").value || "",
                           length: $("summary-length").value || "" }),
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    $("summary-status").textContent = t("summary_failed",
                                        { error: problem.detail || response.status });
    $("summary-run").disabled = pageBusy;
    return;
  }
  const job = await response.json();
  refreshJobs();
  watchSummaryJob(job.id);
});

$("summary-delete").addEventListener("click", async () => {
  const sure = await ask({
    title: t("confirm_delete_summary"),
    body: t("confirm_delete_summary_body", { title: $("viewer-title").textContent }),
    detail: t("confirm_delete_summary_detail"),
    confirmLabel: t("confirm_delete_summary_ok"),
  });
  if (!sure) return;
  await fetch(api(`library/${encodeURIComponent(openEntryId)}/summary`),
              { method: "DELETE" });
  reloadOpenEntry();
});

$("viewer-close").addEventListener("click", closeViewer);
$("viewer").addEventListener("close", () => $("viewer-audio").pause());

$("notes-save").addEventListener("click", async () => {
  const response = await fetch(api(`library/${encodeURIComponent(openEntryId)}/notes`), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes: $("notes-text").value }),
  });
  const box = $("notes-status");
  if (response.ok) {
    box.textContent = t("notes_saved");
    box.className = "ok";
    refreshLibrary();
  } else {
    const detail = await response.json().catch(() => ({}));
    box.textContent = t("notes_failed", { error: detail.detail || response.statusText });
    box.className = "error";
  }
});

$("viewer-rename").addEventListener("click", async () => {
  const title = await ask({
    title: t("rename_title"),
    body: "",
    confirmLabel: t("rename_ok"),
    danger: false,
    input: { label: t("rename_label"), value: $("viewer-title").textContent },
  });
  if (!title) return;
  const response = await fetch(api(`library/${encodeURIComponent(openEntryId)}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (response.ok) {
    $("viewer-title").textContent = (await response.json()).title;
    refreshLibrary();
  }
});

$("viewer-delete").addEventListener("click", async () => {
  const sure = await ask({
    title: t("confirm_delete_entry"),
    body: t("confirm_delete_entry_body", { title: $("viewer-title").textContent }),
    detail: t("confirm_delete_entry_detail"),
    confirmLabel: t("confirm_delete_entry_ok"),
  });
  if (!sure) return;
  const response = await fetch(api(`library/${encodeURIComponent(openEntryId)}`),
                               { method: "DELETE" });
  if (response.ok) {
    closeViewer();
    refreshLibrary();
  }
});

/* --- the upload form --------------------------------------------------- */

$("job-form").addEventListener("submit", async (event) => {
  if (pageBusy) return event.preventDefault();   // Enter, with the button off
  event.preventDefault();
  const error = $("form-error");
  error.hidden = true;
  if (recorder) stopRecording();
  if (!selectedFile) {
    error.textContent = t("no_file");
    error.hidden = false;
    return;
  }
  const body = new FormData();
  body.append("file", selectedFile);
  body.append("title", $("title").value);
  body.append("model", $("model").value);
  body.append("language", $("language").value);
  const output = chosenOutput();
  body.append("output", output);
  /* The server settles what the answer implies (config.resolve_output), so
     the form sends the choice and only the extra it leaves open. */
  body.append("diarize", output === "subtitles" && $("diarize").checked
    ? "true" : "false");
  if ($("speakers").value && !$("speakers-field").hidden) {
    body.append("speakers", $("speakers").value);
  }
  const formats = [];
  if ($("save-srt").checked) formats.push("srt");
  if ($("save-vtt").checked) formats.push("vtt");
  body.append("subtitles_save", formats.join(","));
  body.append("subtitle_preset", $("subtitle-preset").value);
  /* Zero and empty both mean "whatever the preset says", so neither is sent. */
  if (Number($("subtitle-chars").value) > 0) {
    body.append("subtitle_chars", $("subtitle-chars").value);
  }
  if (Number($("subtitle-words").value) > 0) {
    body.append("subtitle_words", $("subtitle-words").value);
  }
  for (const name of selectedInstalled()) body.append("vocabulary", name);
  body.append("custom_vocabulary", customText());

  const button = $("submit");
  button.disabled = true;
  button.textContent = t("uploading");
  try {
    const response = await fetch(api("jobs"), { method: "POST", body });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || response.statusText);
    }
    chooseFile(null);
    $("file").value = "";
    $("title").value = "";
    $("record-preview").hidden = true;
    $("record-time").textContent = "";
    $("record-hint").textContent = t("record_hint");
    refreshJobs();
  } catch (failure) {
    error.textContent = t("upload_failed", { error: failure.message });
    error.hidden = false;
  } finally {
    // Not simply "false": the upload has just made the page busy, and the
    // button it was clicked on is one of the things that goes off.
    button.disabled = pageBusy;
    button.textContent = t("start");
  }
});

/* --- start ------------------------------------------------------------- */

async function start() {
  status = await fetch(api("status")).then((r) => r.json());
  lang = I18N[status.interface_language] ? status.interface_language : "en";
  translatePage();

  for (const name of status.models) {
    // "auto" says out loud what it resolves to here, so nobody has to guess
    // which model a two-core server is about to spend an hour on.
    const label = name === "auto"
      ? t("auto_model", { model: status.recommended_model })
      : name;
    $("model").append(el("option", { value: name, textContent: label,
      selected: name === status.defaults.model }));
  }
  for (const code of status.languages) {
    $("language").append(el("option", { value: code, textContent: code || t("auto"),
      selected: code === status.defaults.language }));
  }
  const diarization = status.diarization || { available: true };
  const subtitle = status.subtitles || { presets: [], default: "", save: "" };
  const presets = $("subtitle-preset");
  presets.textContent = "";
  for (const item of subtitle.presets) {
    const numbers = t("sub_preset_numbers", {
      chars: item.max_chars_per_line, lines: item.max_lines,
      cps: item.max_chars_per_second,
    });
    presets.append(el("option", { value: item.name,
                                  textContent: `${item.name} - ${numbers}` }));
  }
  presets.value = subtitle.default || "";
  $("save-srt").checked = subtitle.save.includes("srt");
  $("save-vtt").checked = subtitle.save.includes("vtt");
  $("diarize").checked = diarization.available && status.defaults.diarize;
  const chosen = $(`output-${status.defaults.output || "text"}`);
  if (chosen) chosen.checked = true;
  if (!diarization.available) {
    // An output this machine cannot produce is not offered: a job that fails
    // after the wait is a worse way to find that out.
    $("diarize").checked = false;
    for (const id of ["diarize", "output-speakers"]) {
      $(id).disabled = true;
      $(id).dataset.locked = "1";
    }
    if ($("output-speakers").checked) $("output-text").checked = true;
    $("diarize-note").textContent = t(`diarize_${diarization.reason}`);
    $("diarize-note").hidden = false;
    for (const id of ["diarize", "output-speakers"]) {
      $(id).closest(".field").classList.add("unavailable");
    }
  }
  applyOutput();

  installed = (await fetch(api("vocabularies")).then((r) => r.json())).vocabularies;
  $("colophon").textContent = t("colophon", { version: status.version, sets: installed.length });
  renderInstalled();
  renderMine();
  updatePromptSize();
  await loadSummaryEngines();
  refreshJobs();
  refreshLibrary();
}

start();
