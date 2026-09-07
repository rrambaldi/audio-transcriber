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
    done: "done",
    failed: "failed",
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
    done: "completata",
    failed: "fallita",
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
$("diarize").addEventListener("change", (event) => {
  $("speakers-field").hidden = !event.target.checked;
});

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
    chooseFile(new File([blob], name, { type }),
               t("recording_ready", { duration: duration(seconds) }));
    const preview = $("record-preview");
    preview.src = URL.createObjectURL(blob);
    preview.hidden = false;
  });
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

function renderJobs(jobs) {
  const box = $("jobs");
  box.textContent = "";
  if (!jobs.length) {
    box.append(el("p", { className: "note", textContent: t("no_jobs") }));
    return;
  }
  for (const job of jobs) {
    const facts = [job.model, job.language, job.vocabularies.join(", "),
      job.words ? t("words", { n: job.words }) : "",
      job.elapsed_seconds ? duration(job.elapsed_seconds) : ""].filter(Boolean).join(" · ");
    const state = el("span", { className: `state${job.status === "failed" ? " failed" : ""}`,
                               textContent: t(job.status) });
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
    if (job.status === "done" || job.status === "failed") {
      const remove = el("button", { type: "button", className: "link",
                                    textContent: t("remove_from_list") });
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
  renderJobs(data.jobs);
  const busy = data.jobs.some((job) => job.status === "queued" || job.status === "running");
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

function showViewerTab(which) {
  for (const [name, tab, pane] of [
    ["transcript", "tab-transcript", "viewer-text"],
    ["segments", "tab-segments", "viewer-segments"],
    ["notes", "tab-notes", "viewer-notes"],
  ]) {
    $(tab).classList.toggle("on", name === which);
    $(tab).setAttribute("aria-selected", String(name === which));
    $(pane).hidden = name !== which;
  }
  $("notes-save").hidden = which !== "notes";
}

$("tab-transcript").addEventListener("click", () => showViewerTab("transcript"));
$("tab-segments").addEventListener("click", () => showViewerTab("segments"));
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
  const player = $("viewer-audio");
  player.hidden = !entry.has_audio;
  player.src = entry.has_audio ? api(`library/${encodeURIComponent(entry.id)}/audio`) : "";
  $("viewer-download").href = api(`library/${encodeURIComponent(entry.id)}/transcript.txt`);
  $("viewer-download-json").href = api(`library/${encodeURIComponent(entry.id)}/transcript.json`);
  $("viewer-download-json").hidden = !(entry.segments || []).length;
  showViewerTab("transcript");
  $("viewer").showModal();
}

function closeViewer() {
  const player = $("viewer-audio");
  player.pause();
  player.removeAttribute("src");
  $("viewer").close();
}

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
  body.append("diarize", $("diarize").checked ? "true" : "false");
  if ($("diarize").checked && $("speakers").value) {
    body.append("speakers", $("speakers").value);
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
    button.disabled = false;
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
  $("diarize").checked = diarization.available && status.defaults.diarize;
  $("speakers-field").hidden = !$("diarize").checked;
  if (!diarization.available) {
    $("diarize").disabled = true;
    $("diarize-note").textContent = t(`diarize_${diarization.reason}`);
    $("diarize-note").hidden = false;
    $("diarize").closest(".field").classList.add("unavailable");
  }

  installed = (await fetch(api("vocabularies")).then((r) => r.json())).vocabularies;
  $("colophon").textContent = t("colophon", { version: status.version, sets: installed.length });
  renderInstalled();
  renderMine();
  updatePromptSize();
  refreshJobs();
  refreshLibrary();
}

start();
