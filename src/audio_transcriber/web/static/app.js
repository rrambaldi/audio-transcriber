// SPDX-FileCopyrightText: 2026 Roberto Rambaldi
// SPDX-License-Identifier: MIT
// The Gratitude & Random Kindness License: MIT, with a wish. See LICENSE.

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
    log_show: "messages",
    log_hide: "hide the messages",
    log_refresh: "refresh",
    log_clear: "empty it",
    log_empty: "Nothing yet. This is what the server would otherwise have printed into the terminal it was started from.",
    log_where: "Written to {path}",
    confirm_clear_log: "Empty the log",
    confirm_clear_log_body: "What is in it now is gone. What happens next is written from scratch; nothing else is touched.",
    speakers_name: "name the speakers",
    speakers_title: "Who is speaking",
    speakers_intro: "The machine heard the voices apart but cannot know whose they are. Give them names and the transcript is rewritten to use them; leave one blank and it keeps the label it has.",
    speakers_same: "Two of them with the same name means one person: their turns are run together.",
    speakers_hint: "a name",
    speakers_ok: "Name them",
    speakers_named: "The speakers are now: {speakers}",
    speakers_failed: "Not renamed: {error}",
    colophon: "audio-transcriber {version} — {sets} keyword sets installed. Everything runs on this machine.",
    reference_label: "A text you already have",
    reference_note: "A script, a press release, a transcript from elsewhere. Its rare words are given to the engine so it spells them right, and afterwards it corrects the words it misheard or cut short. What was actually said still wins: nothing is added because the text expected it.",
    about_open: "About this program",
    about_title: "About audio-transcriber",
    about_version: "Version {version}",
    about_licence: "License",
    about_licence_missing: "This copy has no licence file to show. The terms are the MIT license.",
    about_bundled: "What is bundled",
    about_fonts: "Two typefaces, each under its own licence:",
    about_dependencies: "Built on Qt through PySide6, under the LGPL v3, and it reads audio with ffmpeg, under the LGPL 2.1. Everything else it uses is installed separately and keeps its own licence: docs/third-party.md lists them.",

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
    output_legend: "What do you want out of it?",
    output_text: "Just the text",
    output_text_note: "Paragraphs, broken where the speech pauses. No timestamps, nobody named: the transcript to read or to paste somewhere.",
    output_speakers: "The text, with who said what",
    output_speakers_note: "The same text arranged as a dialogue, one block per turn. Needs diarization, which runs on the CPU and takes a while.",
    output_subtitles: "Subtitles",
    output_subtitles_note: "Cues with times, cut to be readable, saved with the entry as .srt or .vtt. Nobody named: the speech, in the order it was spoken.",
    auto_title: "Name it after what was said in it",
    auto_title_note: "Instead of the file name. Taken from the transcript when it is done \u2014 nothing is sent anywhere and no model is loaded.",
    summary_after: "Write a summary as well, when it is done",
    summary_after_note: "A second job, queued behind this one: the transcript first, the summary after it, on this machine.",
    output_subtitles_speakers: "Subtitles, with who said what",
    output_subtitles_speakers_note: "The same cues, with a change of voice marked in them. Needs diarization, which runs on the CPU and takes a while.",
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
    took: "took {time}",
    cpu: "CPU",
    ram: "RAM",
    cpu_reading: "{percent}% of {cores} cores",
    cpu_reading_load: "{percent}% of {cores} cores \u00b7 run queue {load}",
    ram_reading: "{used} GiB of {total} in use",
    engine_on: "Engine: {engine} \u00b7 device: {device}",
    engine_only: "Engine: {engine}",
    engine_missing: "No transcription engine is installed on this machine.",
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
    summary_style: "Written as",
    summary_style_combined: "one request",
    summary_style_split: "one per section",
    summary_template: "Which sections",
    summary_template_auto: "whatever the recording was about",
    summary_template_own: "My sections",
    summary_template_mine: "my own sections\u2026",
    summary_template_help: "One section a line: the heading, a colon, and what belongs under it. Two at least, twelve at most. Restricting the sections restricts the reading as well as the page \u2014 a pass not asked for opinions does not write them down.",
    summary_run: "Summarise",
    summary_again: "Summarise again",
    summary_delete: "delete the summary",
    download_summary: "summary (.md)",
    copy: "Copy",
    copied: "Copied to the clipboard.",
    copy_failed: "Not copied: the browser refused.",
    summary_queued: "In the queue, behind whatever is already running.",
    summary_running: "Being written\u2026 {stage}",
    summary_failed: "Could not summarise: {error}",
    summary_engine_extractive: "no model: the sentences that carry the transcript",
    summary_engine_openvino: "a local model, on this machine's Intel device",
    summary_engine_llamacpp: "a local model, on this machine's processor",
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
    held: "waiting to start",
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
    start_job: "start",
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
    trace_label: "The last five seconds",
    wave_label: "How loud the recording is, from start to end",
    recording_silent: "That recording never rose above silence: check that the right microphone is being used before trusting the next one.",
    no_file: "Choose a file, or record something, first.",
    uploading: "Uploading...",
    terms: "{n} terms",
    words: "{n} words",
    row_summary_title: "Summary: {title}",
    row_summary_of: "summary of the transcript",
    upload_failed: "Upload failed: {error}",
    server_unreachable: "The server is not answering. Nothing is lost: this page reconnects on its own.",
    retry_now: "try again now",
    jobs_status_idle: "Nothing running.",
    jobs_status: "{running} running, at {percent}% \u00b7 {waiting} waiting",
    jobs_status_waiting: "{waiting} waiting.",
    library_results: "{count} recordings.",
    library_results_query: "{count} recordings match \"{query}\".",
    source_tabs: "What to transcribe",
    view_tabs: "What to show of this recording",
    interface_language: "Language",
    language_reload_title: "Change the language?",
    language_reload_body: "The page reloads in the new language, and the recording or upload under way here would be lost.",
    language_reload_ok: "Reload",
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
    log_show: "messaggi",
    log_hide: "nascondi i messaggi",
    log_refresh: "aggiorna",
    log_clear: "svuotalo",
    log_empty: "Ancora niente. Qui finisce quello che il server avrebbe scritto nel terminale da cui e' stato avviato.",
    log_where: "Scritto in {path}",
    confirm_clear_log: "Svuota il log",
    confirm_clear_log_body: "Quello che c'e' adesso sparisce. Quello che succede dopo viene scritto da zero; nient'altro viene toccato.",
    speakers_name: "dai un nome agli interlocutori",
    speakers_title: "Chi parla",
    speakers_intro: "La macchina ha distinto le voci ma non può sapere di chi sono. Dai loro un nome e la trascrizione viene riscritta con quello; lascia vuoto e resta l'etichetta che ha adesso.",
    speakers_same: "Due con lo stesso nome vuol dire una persona sola: i loro turni vengono uniti.",
    speakers_hint: "un nome",
    speakers_ok: "Assegna i nomi",
    speakers_named: "Adesso gli interlocutori sono: {speakers}",
    speakers_failed: "Non rinominati: {error}",
    colophon: "audio-transcriber {version} — {sets} set di parole chiave installati. Tutto gira su questa macchina.",
    reference_label: "Un testo che hai gia'",
    reference_note: "Un copione, un comunicato, una trascrizione presa altrove. Le sue parole rare vengono passate al motore perche' le scriva giuste, e dopo correggono quelle che ha sentito male o troncato. Quello che e' stato detto davvero vince comunque: niente viene aggiunto perche' il testo se lo aspettava.",
    about_open: "Informazioni su questo programma",
    about_title: "Informazioni su audio-transcriber",
    about_version: "Versione {version}",
    about_licence: "Licenza",
    about_licence_missing: "Questa copia non ha un file di licenza da mostrare. I termini sono quelli della licenza MIT.",
    about_bundled: "Cosa è incluso",
    about_fonts: "Due caratteri tipografici, ognuno con la sua licenza:",
    about_dependencies: "Costruito su Qt tramite PySide6, sotto LGPL v3, e legge l'audio con ffmpeg, sotto LGPL 2.1. Tutto il resto si installa a parte e mantiene la propria licenza: l'elenco e' in docs/third-party.md.",

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
    output_legend: "Cosa vuoi ottenere?",
    output_text: "Solo il testo",
    output_text_note: "Paragrafi, spezzati dove il parlato si interrompe. Nessun timestamp, nessun nome: la trascrizione da leggere o da incollare altrove.",
    output_speakers: "Il testo, con chi dice cosa",
    output_speakers_note: "Lo stesso testo disposto come un dialogo, un blocco per battuta. Richiede la diarizzazione, che gira su CPU e ci mette un po'.",
    output_subtitles: "Sottotitoli",
    output_subtitles_note: "Battute con i tempi, tagliate per essere leggibili, salvate con la voce in .srt o .vtt. Nessun nome: il parlato, nell'ordine in cui \u00e8 stato detto.",
    auto_title: "Intitolala con quello che ci si dice dentro",
    auto_title_note: "Invece che con il nome del file. Presa dalla trascrizione quando ha finito: niente esce da questa macchina e nessun modello viene caricato.",
    summary_after: "Scrivi anche il riassunto, quando ha finito",
    summary_after_note: "Un secondo lavoro, in coda dietro a questo: prima la trascrizione, poi il riassunto, su questa macchina.",
    output_subtitles_speakers: "Sottotitoli, con chi dice cosa",
    output_subtitles_speakers_note: "Le stesse battute, con il cambio di voce segnato dentro. Richiede la diarizzazione, che gira su CPU e ci mette un po'.",
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
    took: "ci ha messo {time}",
    cpu: "CPU",
    ram: "RAM",
    cpu_reading: "{percent}% di {cores} core",
    cpu_reading_load: "{percent}% di {cores} core \u00b7 coda {load}",
    ram_reading: "{used} GiB usati su {total}",
    engine_on: "Motore: {engine} \u00b7 dispositivo: {device}",
    engine_only: "Motore: {engine}",
    engine_missing: "Su questa macchina non \u00e8 installato nessun motore di trascrizione.",
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
    summary_style: "Scritto come",
    summary_style_combined: "una richiesta",
    summary_style_split: "una per sezione",
    summary_template: "Quali sezioni",
    summary_template_auto: "quelle di cui si e' parlato",
    summary_template_own: "Le mie sezioni",
    summary_template_mine: "le mie sezioni\u2026",
    summary_template_help: "Una sezione per riga: l'intestazione, due punti, e cosa ci va sotto. Due come minimo, dodici come massimo. Restringere le sezioni restringe anche la lettura \u2014 un passaggio a cui non si chiedono le opinioni non le scrive.",
    summary_run: "Riassumi",
    summary_again: "Riassumi di nuovo",
    summary_delete: "elimina il riassunto",
    download_summary: "riassunto (.md)",
    copy: "Copia",
    copied: "Copiato negli appunti.",
    copy_failed: "Non copiato: il browser ha rifiutato.",
    summary_queued: "In coda, dietro a quello che sta gia' girando.",
    summary_running: "Lo sto scrivendo\u2026 {stage}",
    summary_failed: "Non riassunto: {error}",
    summary_engine_extractive: "nessun modello: le frasi che reggono la trascrizione",
    summary_engine_openvino: "un modello locale, sul dispositivo Intel di questa macchina",
    summary_engine_llamacpp: "un modello locale, sul processore di questa macchina",
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
    held: "in attesa di partire",
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
    start_job: "avvia",
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
    trace_label: "Gli ultimi cinque secondi",
    wave_label: "Quanto è forte la registrazione, dall'inizio alla fine",
    recording_silent: "Quella registrazione non e' mai salita sopra il silenzio: controlla che sia il microfono giusto prima di fidarti della prossima.",
    no_file: "Scegli prima un file, o registra qualcosa.",
    uploading: "Caricamento...",
    terms: "{n} termini",
    words: "{n} parole",
    row_summary_title: "Riassunto: {title}",
    row_summary_of: "riassunto della trascrizione",
    upload_failed: "Caricamento fallito: {error}",
    server_unreachable: "Il server non risponde. Non si perde niente: la pagina si ricollega da sola.",
    retry_now: "riprova adesso",
    jobs_status_idle: "Niente in esecuzione.",
    jobs_status: "{running} in corso, al {percent}% \u00b7 {waiting} in attesa",
    jobs_status_waiting: "{waiting} in attesa.",
    library_results: "{count} registrazioni.",
    library_results_query: "{count} registrazioni contengono \"{query}\".",
    source_tabs: "Cosa trascrivere",
    view_tabs: "Cosa mostrare di questa registrazione",
    interface_language: "Lingua",
    language_reload_title: "Cambiare lingua?",
    language_reload_body: "La pagina si ricarica nella nuova lingua, e la registrazione o il caricamento in corso qui andrebbero persi.",
    language_reload_ok: "Ricarica",
  },
  fr: {
    tagline: "Transcription locale. Rien ne quitte cette machine.",
    eyebrow: "Enregistrements et transcriptions",
    new_transcription_note: "Chargez un enregistrement ou enregistrez-en un ici. Il est transcrit sur cette machine, en arri\u00e8re-plan : rien n'est envoy\u00e9 nulle part.",
    jobs_note: "Une transcription \u00e0 la fois. Quitter cette page n'arr\u00eate rien.",
    library_note: "Chaque transcription termin\u00e9e, avec son enregistrement, son texte et vos notes.",
    search_label: "Rechercher dans les transcriptions",
    notes_label: "Notes sur cet enregistrement",
    remove_from_list: "retirer de la liste",
    confirm_remove_job: "Retirer ce travail de la liste ?",
    confirm_remove_job_body: "\"{title}\" dispara\u00eet de Travaux.",
    confirm_remove_job_kept: "La transcription reste dans la biblioth\u00e8que : rien n'est supprim\u00e9.",
    confirm_remove_job_failed: "Ce travail n'a produit aucune transcription, il n'y a donc rien \u00e0 garder.",
    confirm_remove_job_ok: "Retirer de la liste",
    confirm_delete_entry: "Supprimer cet enregistrement ?",
    confirm_delete_entry_body: "\"{title}\" est supprim\u00e9e : la transcription, les timestamps, vos notes et l'enregistrement lui-m\u00eame.",
    confirm_delete_entry_detail: "Cette action est irr\u00e9versible.",
    confirm_delete_entry_ok: "Supprimer d\u00e9finitivement",
    confirm_delete_set: "Supprimer ce jeu de mots-cl\u00e9s ?",
    confirm_delete_set_body: "\"{name}\" est retir\u00e9 de ce navigateur.",
    confirm_delete_set_ok: "Supprimer le jeu",
    rename_title: "Renommer",
    rename_label: "Titre",
    rename_ok: "Renommer",
    log_show: "messages",
    log_hide: "masquer les messages",
    log_refresh: "actualiser",
    log_clear: "vider",
    log_empty: "Rien pour l'instant. C'est ce que le serveur aurait sinon affich\u00e9 dans le terminal depuis lequel il a \u00e9t\u00e9 lanc\u00e9.",
    log_where: "\u00c9crit dans {path}",
    confirm_clear_log: "Vider le journal",
    confirm_clear_log_body: "Ce qu'il contient maintenant dispara\u00eet. Ce qui se passe ensuite est \u00e9crit depuis le d\u00e9but ; rien d'autre n'est touch\u00e9.",
    speakers_name: "nommer les locuteurs",
    speakers_title: "Qui parle",
    speakers_intro: "La machine a distingu\u00e9 les voix mais ne peut pas savoir \u00e0 qui elles appartiennent. Donnez-leur un nom et la transcription est r\u00e9\u00e9crite pour l'utiliser ; laissez-en un vide et il garde l'\u00e9tiquette qu'il a.",
    speakers_same: "Deux avec le m\u00eame nom signifie une seule personne : leurs tours sont r\u00e9unis.",
    speakers_hint: "un nom",
    speakers_ok: "Attribuer les noms",
    speakers_named: "Les locuteurs sont maintenant : {speakers}",
    speakers_failed: "Non renomm\u00e9s : {error}",
    colophon: "audio-transcriber {version} \u2014 {sets} jeux de mots-cl\u00e9s install\u00e9s. Tout tourne sur cette machine.",
    reference_label: "Un texte que vous avez d\u00e9j\u00e0",
    reference_note: "Un script, un communiqu\u00e9, une transcription venue d'ailleurs. Ses mots rares sont donn\u00e9s au moteur pour qu'il les orthographie correctement, et ensuite il corrige les mots mal entendus ou coup\u00e9s. Ce qui a vraiment \u00e9t\u00e9 dit l'emporte quand m\u00eame : rien n'est ajout\u00e9 parce que le texte s'y attendait.",
    about_open: "\u00c0 propos de ce programme",
    about_title: "\u00c0 propos d'audio-transcriber",
    about_version: "Version {version}",
    about_licence: "Licence",
    about_licence_missing: "Cette copie n'a pas de fichier de licence \u00e0 montrer. Les termes sont ceux de la licence MIT.",
    about_bundled: "Ce qui est inclus",
    about_fonts: "Deux polices de caract\u00e8res, chacune sous sa propre licence :",
    about_dependencies: "Construit sur Qt via PySide6, sous LGPL v3, et lit l'audio avec ffmpeg, sous LGPL 2.1. Tout le reste s'installe \u00e0 part et garde sa propre licence : docs/third-party.md en donne la liste.",
    new_transcription: "Nouvelle transcription",
    tab_file: "Charger un fichier",
    tab_record: "Enregistrer",
    choose_file: "Choisir un fichier",
    or_drop: "ou d\u00e9posez-le ici (audio ou vid\u00e9o).",
    record_start: "Enregistrer",
    record_stop: "Arr\u00eater",
    record_hint: "Enregistre depuis votre microphone, dans ce navigateur. Rien n'est envoy\u00e9 avant que vous ne d\u00e9marriez la transcription.",
    recording_ready: "Enregistrement pr\u00eat : {duration}. D\u00e9marrez la transcription, ou enregistrez \u00e0 nouveau.",
    mic_unavailable: "Ce navigateur ne donne le microphone \u00e0 une page que si elle est locale ou servie en HTTPS. Chargez un fichier \u00e0 la place, ou atteignez ce serveur via un tunnel SSH.",
    mic_denied: "Le microphone a \u00e9t\u00e9 refus\u00e9 : {error}",
    title: "Titre",
    model: "Mod\u00e8le",
    language: "Langue parl\u00e9e",
    auto: "la d\u00e9tecter",
    auto_model: "automatique ({model})",
    output_legend: "Que voulez-vous en tirer ?",
    output_text: "Juste le texte",
    output_text_note: "Des paragraphes, coup\u00e9s o\u00f9 le parl\u00e9 marque une pause. Aucun timestamp, personne nomm\u00e9 : la transcription \u00e0 lire ou \u00e0 coller ailleurs.",
    output_speakers: "Le texte, avec qui dit quoi",
    output_speakers_note: "Le m\u00eame texte pr\u00e9sent\u00e9 comme un dialogue, un bloc par tour de parole. N\u00e9cessite la diarisation, qui tourne sur le CPU et prend un moment.",
    output_subtitles: "Sous-titres",
    output_subtitles_note: "Des r\u00e9pliques avec les temps, coup\u00e9es pour \u00eatre lisibles, enregistr\u00e9es avec la fiche en .srt ou .vtt. Personne nomm\u00e9 : le parl\u00e9, dans l'ordre o\u00f9 il a \u00e9t\u00e9 dit.",
    auto_title: "L'intituler avec ce qui y est dit",
    auto_title_note: "Au lieu du nom du fichier. Tir\u00e9e de la transcription une fois termin\u00e9e \u2014 rien ne quitte cette machine et aucun mod\u00e8le n'est charg\u00e9.",
    summary_after: "\u00c9crire aussi un r\u00e9sum\u00e9, une fois termin\u00e9",
    summary_after_note: "Un second travail, en attente derri\u00e8re celui-ci : d'abord la transcription, ensuite le r\u00e9sum\u00e9, sur cette machine.",
    output_subtitles_speakers: "Sous-titres, avec qui dit quoi",
    output_subtitles_speakers_note: "Les m\u00eames r\u00e9pliques, avec un changement de voix marqu\u00e9 dedans. N\u00e9cessite la diarisation, qui tourne sur le CPU et prend un moment.",
    sub_legend: "Comment les sous-titres sont coup\u00e9s",
    sub_preset: "Sous-titres",
    sub_note: "Comment les sous-titres sont coup\u00e9s, si vous les voulez. Les r\u00e9pliques existent de toute fa\u00e7on : une fiche peut \u00eatre t\u00e9l\u00e9charg\u00e9e en .srt ou .vtt plus tard, avec d'autres chiffres.",
    sub_chars: "Caract\u00e8res par ligne de sous-titre",
    sub_words: "Mots par sous-titre",
    sub_save_srt: "Garder un .srt dans la fiche",
    sub_save_vtt: "Garder un .vtt dans la fiche",
    sub_preset_numbers: "{chars} x {lines}, {cps} CPS",
    sub_from_preset: "du preset",
    download_srt: "sous-titres (.srt)",
    download_vtt: "sous-titres (.vtt)",
    diarize_not_installed: "N\u00e9cessite pyannote, qui n'est pas install\u00e9 sur cette machine : pip install \"audio-transcriber-ov[diarize]\"",
    diarize_no_model: "pyannote est install\u00e9 mais n'a pas de mod\u00e8le : d\u00e9finissez HUGGINGFACE_TOKEN sur le serveur, ou placez une configuration locale.",
    speakers: "Locuteurs, si connus",
    keywords: "Jeux de mots-cl\u00e9s",
    keywords_help: "Les termes que la transcription doit bien reconna\u00eetre : noms, sigles, jargon. Choisissez les jeux adapt\u00e9s \u00e0 cet enregistrement.",
    installed_sets: "Install\u00e9s sur cette machine",
    filter_sets: "Filtrer les jeux",
    sets_total: "{total} jeux install\u00e9s",
    sets_selected: "{total} jeux install\u00e9s \u00b7 s\u00e9lectionn\u00e9s : {selected}",
    sets_filtered: "{shown} sur {total} jeux \u00b7 s\u00e9lectionn\u00e9s : {selected}",
    no_matching_sets: "Aucun jeu ne correspond \u00e0 \"{query}\". Ceux que vous avez coch\u00e9s restent visibles.",
    my_sets: "Mes jeux",
    new_set: "nouveau jeu",
    my_sets_help: "Vos jeux restent dans ce navigateur et ne voyagent qu'avec les enregistrements qui les utilisent.",
    no_installed: "Aucun jeu install\u00e9. La personne qui a configur\u00e9 cette machine peut en ajouter avec 'audio-transcriber vocab new'.",
    no_mine: "Vous n'avez encore \u00e9crit aucun jeu.",
    prompt_size: "{chars} caract\u00e8res sur {limit} utilis\u00e9s.",
    prompt_too_long: "Trop long : {chars} caract\u00e8res, {limit} au maximum. Whisper ignore le reste.",
    start: "D\u00e9marrer la transcription",
    jobs: "Travaux",
    busy_note: "Une transcription est en cours : tout le reste est suspendu jusqu'\u00e0 ce qu'elle se termine, ou que vous l'arr\u00eatiez.",
    busy_note_summary: "Un r\u00e9sum\u00e9 est en cours d'\u00e9criture : tout le reste est suspendu jusqu'\u00e0 ce qu'il se termine, ou que vous l'arr\u00eatiez.",
    busy_why: "Pas pendant qu'une transcription est en cours.",
    no_jobs: "Rien en cours.",
    took: "a pris {time}",
    cpu: "CPU",
    ram: "RAM",
    cpu_reading: "{percent}% de {cores} c\u0153urs",
    cpu_reading_load: "{percent}% de {cores} c\u0153urs \u00b7 file d'ex\u00e9cution {load}",
    ram_reading: "{used} Gio utilis\u00e9s sur {total}",
    engine_on: "Moteur : {engine} \u00b7 dispositif : {device}",
    engine_only: "Moteur : {engine}",
    engine_missing: "Aucun moteur de transcription n'est install\u00e9 sur cette machine.",
    library: "Biblioth\u00e8que",
    library_empty: "Aucun enregistrement transcrit pour l'instant.",
    search_placeholder: "rechercher dans les transcriptions",
    no_results: "Rien ne correspond \u00e0 \"{query}\".",
    edit_set: "Jeu de mots-cl\u00e9s",
    set_title: "Nom",
    set_terms: "Termes",
    set_help: "Une liste de termes, s\u00e9par\u00e9s par des virgules ou des retours \u00e0 la ligne. Quelques dizaines au maximum.",
    set_placeholder: "analyse des risques, actif, plan de rem\u00e9diation, CMDB",
    cancel: "Annuler",
    save: "Enregistrer",
    edit: "modifier",
    remove: "supprimer",
    preview: "aper\u00e7u",
    hide: "masquer",
    download: "Transcription",
    download_json: "Timestamps",
    close: "Fermer",
    open: "Ouvrir",
    view: "voir",
    transcript: "Transcription",
    segments: "Timestamps",
    notes: "Notes",
    summary: "R\u00e9sum\u00e9",
    summary_none: "Pas encore de r\u00e9sum\u00e9. La transcription est r\u00e9sum\u00e9e sur cette machine \u2014 rien n'est envoy\u00e9 nulle part.",
    summary_engine: "\u00c9crit par",
    summary_length: "Combien garder",
    summary_short: "court",
    summary_medium: "moyen",
    summary_long: "long",
    summary_style: "\u00c9crit comme",
    summary_style_combined: "une requ\u00eate",
    summary_style_split: "une par section",
    summary_template: "Quelles sections",
    summary_template_auto: "celles dont il a \u00e9t\u00e9 question",
    summary_template_own: "Mes sections",
    summary_template_mine: "mes propres sections\u2026",
    summary_template_help: "Une section par ligne : le titre, deux points, et ce qui va dessous. Deux au minimum, douze au maximum. Restreindre les sections restreint aussi la lecture \u2014 une passe \u00e0 qui on ne demande pas d'avis ne les \u00e9crit pas.",
    summary_run: "R\u00e9sumer",
    summary_again: "R\u00e9sumer \u00e0 nouveau",
    summary_delete: "supprimer le r\u00e9sum\u00e9",
    download_summary: "r\u00e9sum\u00e9 (.md)",
    copy: "Copier",
    copied: "Copi\u00e9 dans le presse-papiers.",
    copy_failed: "Non copi\u00e9 : le navigateur a refus\u00e9.",
    summary_queued: "En attente, derri\u00e8re ce qui tourne d\u00e9j\u00e0.",
    summary_running: "En cours d'\u00e9criture\u2026 {stage}",
    summary_failed: "R\u00e9sum\u00e9 impossible : {error}",
    summary_engine_extractive: "aucun mod\u00e8le : les phrases qui portent la transcription",
    summary_engine_openvino: "un mod\u00e8le local, sur le dispositif Intel de cette machine",
    summary_engine_llamacpp: "un mod\u00e8le local, sur le processeur de cette machine",
    confirm_delete_summary: "Supprimer ce r\u00e9sum\u00e9 ?",
    confirm_delete_summary_body: "Le r\u00e9sum\u00e9 de \"{title}\" est supprim\u00e9.",
    confirm_delete_summary_detail: "La transcription reste intacte : vous pouvez en demander un autre quand vous voulez.",
    confirm_delete_summary_ok: "Supprimer le r\u00e9sum\u00e9",
    no_segments: "Cette fiche n'a pas de timestamps.",
    notes_placeholder: "Ce qui a \u00e9t\u00e9 d\u00e9cid\u00e9, ce qu'il reste \u00e0 faire, qui doit quoi.",
    save_notes: "Enregistrer les notes",
    notes_saved: "Enregistr\u00e9es.",
    notes_failed: "Non enregistr\u00e9es : {error}",
    rename: "renommer",
    delete_entry: "supprimer",
    has_notes: "notes",
    held: "en attente de d\u00e9marrer",
    queued: "en attente",
    running: "en cours",
    stage_summary_selecting: "choix de ce qui compte",
    stage_summary_reading: "lecture de la transcription",
    stage_summary_writing: "\u00e9criture du r\u00e9sum\u00e9",
    done: "termin\u00e9e",
    failed: "\u00e9chou\u00e9e",
    cancelled: "annul\u00e9e",
    stage_starting: "d\u00e9marrage",
    stage_decoded: "audio d\u00e9cod\u00e9",
    stage_loading_model: "chargement du mod\u00e8le",
    stage_converting_model: "conversion du mod\u00e8le",
    stage_compiling_model: "compilation pour le dispositif",
    stage_transcribing: "transcription",
    stage_diarizing: "d\u00e9termination de qui a dit quoi",
    stage_laying_out: "mise en page du texte",
    take_out_of_queue: "retirer de la file d'attente",
    start_job: "d\u00e9marrer",
    stop_job: "arr\u00eater",
    confirm_stop_job: "Arr\u00eater cette transcription ?",
    confirm_stop_job_body: "\"{title}\" s'arr\u00eate et rien n'arrive dans la biblioth\u00e8que.",
    confirm_stop_job_detail: "Elle s'arr\u00eate au prochain avancement signal\u00e9 par le moteur : quelques secondes avec faster-whisper, et pas avant la fin du fichier avec OpenVINO, qui n'en signale aucun. L'enregistrement reste sur le serveur dans les deux cas, il peut donc \u00eatre remis en attente.",
    confirm_stop_job_ok: "Arr\u00eater",
    clear_finished: "vider les termin\u00e9s",
    confirm_clear_finished: "Vider les travaux termin\u00e9s ?",
    confirm_clear_finished_body: "{count} lignes disparaissent de Travaux.",
    confirm_clear_finished_detail: "Les transcriptions restent dans la biblioth\u00e8que : rien n'est supprim\u00e9.",
    confirm_clear_finished_ok: "Vider la liste",
    level_label: "Niveau d'entr\u00e9e",
    trace_label: "Les cinq derni\u00e8res secondes",
    wave_label: "L'intensit\u00e9 de l'enregistrement, du d\u00e9but \u00e0 la fin",
    recording_silent: "Cet enregistrement n'est jamais sorti du silence : v\u00e9rifiez que c'est le bon microphone avant de faire confiance au suivant.",
    no_file: "Choisissez d'abord un fichier, ou enregistrez quelque chose.",
    uploading: "Chargement...",
    terms: "{n} termes",
    words: "{n} mots",
    row_summary_title: "R\u00e9sum\u00e9 : {title}",
    row_summary_of: "r\u00e9sum\u00e9 de la transcription",
    upload_failed: "\u00c9chec du chargement : {error}",
    server_unreachable: "Le serveur ne r\u00e9pond pas. Rien n'est perdu : cette page se reconnecte toute seule.",
    retry_now: "r\u00e9essayer maintenant",
    jobs_status_idle: "Rien en cours.",
    jobs_status: "{running} en cours, \u00e0 {percent}% \u00b7 {waiting} en attente",
    jobs_status_waiting: "{waiting} en attente.",
    library_results: "{count} enregistrements.",
    library_results_query: "{count} enregistrements correspondent \u00e0 \"{query}\".",
    source_tabs: "Quoi transcrire",
    view_tabs: "Que montrer de cet enregistrement",
    interface_language: "Langue",
    language_reload_title: "Changer de langue ?",
    language_reload_body: "La page se recharge dans la nouvelle langue, et l'enregistrement ou l'envoi en cours ici serait perdu.",
    language_reload_ok: "Recharger",
  },
  de: {
    tagline: "Lokale Transkription. Nichts verl\u00e4sst diese Maschine.",
    eyebrow: "Aufnahmen und Transkriptionen",
    new_transcription_note: "Eine Aufnahme hochladen oder hier aufnehmen. Sie wird auf dieser Maschine im Hintergrund transkribiert: Nichts wird irgendwohin gesendet.",
    jobs_note: "Jeweils eine Transkription. Das Verlassen dieser Seite stoppt nichts.",
    library_note: "Jede fertige Transkription, mit Aufnahme, Text und Ihren Notizen.",
    search_label: "Transkriptionen durchsuchen",
    notes_label: "Notizen zu dieser Aufnahme",
    remove_from_list: "aus der Liste entfernen",
    confirm_remove_job: "Diesen Auftrag aus der Liste entfernen?",
    confirm_remove_job_body: "\"{title}\" verschwindet aus Auftr\u00e4ge.",
    confirm_remove_job_kept: "Die Transkription bleibt in der Bibliothek: Nichts wird gel\u00f6scht.",
    confirm_remove_job_failed: "Dieser Auftrag hat keine Transkription erzeugt, es gibt also nichts zu behalten.",
    confirm_remove_job_ok: "Aus der Liste entfernen",
    confirm_delete_entry: "Diese Aufnahme l\u00f6schen?",
    confirm_delete_entry_body: "\"{title}\" wird gel\u00f6scht: die Transkription, die Zeitstempel, Ihre Notizen und die Aufnahme selbst.",
    confirm_delete_entry_detail: "Das kann nicht r\u00fcckg\u00e4ngig gemacht werden.",
    confirm_delete_entry_ok: "Endg\u00fcltig l\u00f6schen",
    confirm_delete_set: "Dieses Schl\u00fcsselwort-Set l\u00f6schen?",
    confirm_delete_set_body: "\"{name}\" wird aus diesem Browser entfernt.",
    confirm_delete_set_ok: "Set l\u00f6schen",
    rename_title: "Umbenennen",
    rename_label: "Titel",
    rename_ok: "Umbenennen",
    log_show: "Meldungen",
    log_hide: "Meldungen ausblenden",
    log_refresh: "aktualisieren",
    log_clear: "leeren",
    log_empty: "Noch nichts. Hier landet, was der Server sonst in das Terminal geschrieben h\u00e4tte, von dem aus er gestartet wurde.",
    log_where: "Geschrieben nach {path}",
    confirm_clear_log: "Protokoll leeren",
    confirm_clear_log_body: "Was jetzt darin steht, ist weg. Was als N\u00e4chstes passiert, wird neu geschrieben; sonst wird nichts anger\u00fchrt.",
    speakers_name: "Sprecher benennen",
    speakers_title: "Wer spricht",
    speakers_intro: "Die Maschine hat die Stimmen unterschieden, kann aber nicht wissen, wem sie geh\u00f6ren. Geben Sie ihnen Namen, und die Transkription wird damit neu geschrieben; lassen Sie ein Feld leer, beh\u00e4lt es seine aktuelle Bezeichnung.",
    speakers_same: "Zwei mit demselben Namen bedeuten eine Person: Ihre Redebeitr\u00e4ge werden zusammengef\u00fchrt.",
    speakers_hint: "ein Name",
    speakers_ok: "Benennen",
    speakers_named: "Die Sprecher sind jetzt: {speakers}",
    speakers_failed: "Nicht umbenannt: {error}",
    colophon: "audio-transcriber {version} \u2014 {sets} Schl\u00fcsselwort-Sets installiert. Alles l\u00e4uft auf dieser Maschine.",
    reference_label: "Ein Text, den Sie bereits haben",
    reference_note: "Ein Skript, eine Pressemitteilung, eine Transkription von anderswo. Seine seltenen W\u00f6rter werden der Engine \u00fcbergeben, damit sie sie richtig schreibt, und danach korrigiert er die W\u00f6rter, die falsch verstanden oder abgeschnitten wurden. Was tats\u00e4chlich gesagt wurde, gewinnt trotzdem: Nichts wird hinzugef\u00fcgt, nur weil der Text es erwartet hat.",
    about_open: "\u00dcber dieses Programm",
    about_title: "\u00dcber audio-transcriber",
    about_version: "Version {version}",
    about_licence: "Lizenz",
    about_licence_missing: "Diese Kopie hat keine Lizenzdatei zum Anzeigen. Es gelten die Bedingungen der MIT-Lizenz.",
    about_bundled: "Was mitgeliefert wird",
    about_fonts: "Zwei Schriftarten, jede unter eigener Lizenz:",
    about_dependencies: "Aufgebaut auf Qt \u00fcber PySide6, unter der LGPL v3, und liest Audio mit ffmpeg, unter der LGPL 2.1. Alles andere, was verwendet wird, wird separat installiert und beh\u00e4lt seine eigene Lizenz: docs/third-party.md listet sie auf.",
    new_transcription: "Neue Transkription",
    tab_file: "Datei hochladen",
    tab_record: "Aufnehmen",
    choose_file: "Datei ausw\u00e4hlen",
    or_drop: "oder hier ablegen (Audio oder Video).",
    record_start: "Aufnehmen",
    record_stop: "Stopp",
    record_hint: "Nimmt \u00fcber Ihr Mikrofon in diesem Browser auf. Es wird nichts gesendet, bis Sie die Transkription starten.",
    recording_ready: "Aufnahme bereit: {duration}. Transkription starten, oder erneut aufnehmen.",
    mic_unavailable: "Dieser Browser gibt einer Seite das Mikrofon nur frei, wenn sie lokal oder \u00fcber HTTPS bereitgestellt wird. Laden Sie stattdessen eine Datei hoch, oder erreichen Sie diesen Server \u00fcber einen SSH-Tunnel.",
    mic_denied: "Das Mikrofon wurde verweigert: {error}",
    title: "Titel",
    model: "Modell",
    language: "Gesprochene Sprache",
    auto: "erkennen",
    auto_model: "automatisch ({model})",
    output_legend: "Was m\u00f6chten Sie daraus erhalten?",
    output_text: "Nur der Text",
    output_text_note: "Abs\u00e4tze, unterbrochen, wo das Gesprochene pausiert. Keine Zeitstempel, niemand benannt: die Transkription zum Lesen oder Einf\u00fcgen.",
    output_speakers: "Der Text, mit wer was gesagt hat",
    output_speakers_note: "Derselbe Text als Dialog angeordnet, ein Block pro Redebeitrag. Erfordert Diarisierung, die auf der CPU l\u00e4uft und eine Weile dauert.",
    output_subtitles: "Untertitel",
    output_subtitles_note: "Einblendungen mit Zeiten, lesbar geschnitten, mit dem Eintrag als .srt oder .vtt gespeichert. Niemand benannt: das Gesprochene, in der Reihenfolge, in der es gesagt wurde.",
    auto_title: "Nach dem Gesagten benennen",
    auto_title_note: "Statt des Dateinamens. Wird der Transkription entnommen, sobald sie fertig ist \u2014 nichts wird irgendwohin gesendet, und kein Modell wird geladen.",
    summary_after: "Nach Abschluss auch eine Zusammenfassung schreiben",
    summary_after_note: "Ein zweiter Auftrag, hinter diesem eingereiht: erst die Transkription, dann die Zusammenfassung, auf dieser Maschine.",
    output_subtitles_speakers: "Untertitel, mit wer was gesagt hat",
    output_subtitles_speakers_note: "Dieselben Einblendungen, mit markiertem Stimmwechsel. Erfordert Diarisierung, die auf der CPU l\u00e4uft und eine Weile dauert.",
    sub_legend: "Wie die Untertitel geschnitten werden",
    sub_preset: "Untertitel",
    sub_note: "Wie Untertitel geschnitten werden, falls Sie sie m\u00f6chten. Die Einblendungen existieren so oder so: Ein Eintrag kann sp\u00e4ter mit anderen Werten als .srt oder .vtt heruntergeladen werden.",
    sub_chars: "Zeichen pro Untertitelzeile",
    sub_words: "W\u00f6rter pro Untertitel",
    sub_save_srt: "Eine .srt beim Eintrag behalten",
    sub_save_vtt: "Eine .vtt beim Eintrag behalten",
    sub_preset_numbers: "{chars} x {lines}, {cps} CPS",
    sub_from_preset: "aus dem Preset",
    download_srt: "Untertitel (.srt)",
    download_vtt: "Untertitel (.vtt)",
    diarize_not_installed: "Erfordert pyannote, das auf dieser Maschine nicht installiert ist: pip install \"audio-transcriber-ov[diarize]\"",
    diarize_no_model: "pyannote ist installiert, hat aber kein Modell: HUGGINGFACE_TOKEN auf dem Server setzen, oder eine lokale Konfiguration bereitstellen.",
    speakers: "Sprecher, falls bekannt",
    keywords: "Schl\u00fcsselwort-Sets",
    keywords_help: "Begriffe, die die Transkription richtig erfassen soll: Namen, Abk\u00fcrzungen, Fachjargon. W\u00e4hlen Sie die zu dieser Aufnahme passenden Sets.",
    installed_sets: "Auf dieser Maschine installiert",
    filter_sets: "Sets filtern",
    sets_total: "{total} Sets installiert",
    sets_selected: "{total} Sets installiert \u00b7 ausgew\u00e4hlt: {selected}",
    sets_filtered: "{shown} von {total} Sets \u00b7 ausgew\u00e4hlt: {selected}",
    no_matching_sets: "Kein Set passt zu \"{query}\". Die von Ihnen angehakten bleiben sichtbar.",
    my_sets: "Meine Sets",
    new_set: "neues Set",
    my_sets_help: "Ihre Sets bleiben in diesem Browser und werden nur mit den Aufnahmen gesendet, die sie verwenden.",
    no_installed: "Kein Set installiert. Wer diese Maschine eingerichtet hat, kann welche mit 'audio-transcriber vocab new' hinzuf\u00fcgen.",
    no_mine: "Sie haben noch kein Set geschrieben.",
    prompt_size: "{chars} von {limit} Zeichen verwendet.",
    prompt_too_long: "Zu lang: {chars} Zeichen, maximal {limit}. Whisper ignoriert den Rest.",
    start: "Transkription starten",
    jobs: "Auftr\u00e4ge",
    busy_note: "Eine Transkription l\u00e4uft: Alles andere ist gesperrt, bis sie fertig ist oder Sie sie stoppen.",
    busy_note_summary: "Eine Zusammenfassung wird geschrieben: Alles andere ist gesperrt, bis sie fertig ist oder Sie sie stoppen.",
    busy_why: "Nicht w\u00e4hrend eine Transkription l\u00e4uft.",
    no_jobs: "Nichts l\u00e4uft.",
    took: "hat {time} gedauert",
    cpu: "CPU",
    ram: "RAM",
    cpu_reading: "{percent}% von {cores} Kernen",
    cpu_reading_load: "{percent}% von {cores} Kernen \u00b7 Run-Queue {load}",
    ram_reading: "{used} GiB von {total} in Verwendung",
    engine_on: "Engine: {engine} \u00b7 Ger\u00e4t: {device}",
    engine_only: "Engine: {engine}",
    engine_missing: "Auf dieser Maschine ist keine Transkriptions-Engine installiert.",
    library: "Bibliothek",
    library_empty: "Bisher wurde keine Aufnahme transkribiert.",
    search_placeholder: "Transkriptionen durchsuchen",
    no_results: "Nichts passt zu \"{query}\".",
    edit_set: "Schl\u00fcsselwort-Set",
    set_title: "Name",
    set_terms: "Begriffe",
    set_help: "Eine Liste von Begriffen, getrennt durch Kommas oder Zeilenumbr\u00fcche. H\u00f6chstens ein paar Dutzend.",
    set_placeholder: "Risikobewertung, Asset, Ma\u00dfnahmenplan, CMDB",
    cancel: "Abbrechen",
    save: "Speichern",
    edit: "bearbeiten",
    remove: "l\u00f6schen",
    preview: "Vorschau",
    hide: "ausblenden",
    download: "Transkription",
    download_json: "Zeitstempel",
    close: "Schlie\u00dfen",
    open: "\u00d6ffnen",
    view: "ansehen",
    transcript: "Transkription",
    segments: "Zeitstempel",
    notes: "Notizen",
    summary: "Zusammenfassung",
    summary_none: "Noch keine Zusammenfassung. Die Transkription wird auf dieser Maschine zusammengefasst \u2014 nichts wird irgendwohin gesendet.",
    summary_engine: "Geschrieben von",
    summary_length: "Wie viel behalten wird",
    summary_short: "kurz",
    summary_medium: "mittel",
    summary_long: "lang",
    summary_style: "Geschrieben als",
    summary_style_combined: "eine Anfrage",
    summary_style_split: "eine pro Abschnitt",
    summary_template: "Welche Abschnitte",
    summary_template_auto: "was auch immer in der Aufnahme besprochen wurde",
    summary_template_own: "Meine Abschnitte",
    summary_template_mine: "meine eigenen Abschnitte\u2026",
    summary_template_help: "Ein Abschnitt pro Zeile: die \u00dcberschrift, ein Doppelpunkt, und was darunter geh\u00f6rt. Mindestens zwei, h\u00f6chstens zw\u00f6lf. Das Einschr\u00e4nken der Abschnitte schr\u00e4nkt auch das Lesen ein wie die Seite \u2014 ein Durchgang, der nicht nach Meinungen gefragt wird, schreibt sie nicht auf.",
    summary_run: "Zusammenfassen",
    summary_again: "Erneut zusammenfassen",
    summary_delete: "Zusammenfassung l\u00f6schen",
    download_summary: "Zusammenfassung (.md)",
    copy: "Kopieren",
    copied: "In die Zwischenablage kopiert.",
    copy_failed: "Nicht kopiert: Der Browser hat abgelehnt.",
    summary_queued: "In der Warteschlange, hinter dem, was bereits l\u00e4uft.",
    summary_running: "Wird geschrieben\u2026 {stage}",
    summary_failed: "Konnte nicht zusammengefasst werden: {error}",
    summary_engine_extractive: "kein Modell: die S\u00e4tze, die die Transkription tragen",
    summary_engine_openvino: "ein lokales Modell, auf dem Intel-Ger\u00e4t dieser Maschine",
    summary_engine_llamacpp: "ein lokales Modell, auf dem Prozessor dieser Maschine",
    confirm_delete_summary: "Diese Zusammenfassung l\u00f6schen?",
    confirm_delete_summary_body: "Die Zusammenfassung von \"{title}\" wird gel\u00f6scht.",
    confirm_delete_summary_detail: "Die Transkription bleibt unangetastet, Sie k\u00f6nnen also eine neue anfordern.",
    confirm_delete_summary_ok: "Zusammenfassung l\u00f6schen",
    no_segments: "Dieser Eintrag hat keine Zeitstempel.",
    notes_placeholder: "Was entschieden wurde, was als N\u00e4chstes zu tun ist, wer was schuldet.",
    save_notes: "Notizen speichern",
    notes_saved: "Gespeichert.",
    notes_failed: "Konnte nicht gespeichert werden: {error}",
    rename: "umbenennen",
    delete_entry: "l\u00f6schen",
    has_notes: "Notizen",
    held: "wartet auf Start",
    queued: "in Warteschlange",
    running: "wird transkribiert",
    stage_summary_selecting: "Auswahl, was z\u00e4hlt",
    stage_summary_reading: "Lesen der Transkription",
    stage_summary_writing: "Schreiben der Zusammenfassung",
    done: "fertig",
    failed: "fehlgeschlagen",
    cancelled: "abgebrochen",
    stage_starting: "Start",
    stage_decoded: "Audio dekodiert",
    stage_loading_model: "Laden des Modells",
    stage_converting_model: "Konvertieren des Modells",
    stage_compiling_model: "Kompilieren f\u00fcr das Ger\u00e4t",
    stage_transcribing: "Transkription",
    stage_diarizing: "Ermitteln, wer was gesagt hat",
    stage_laying_out: "Formatieren des Texts",
    take_out_of_queue: "aus der Warteschlange nehmen",
    start_job: "starten",
    stop_job: "stoppen",
    confirm_stop_job: "Diese Transkription stoppen?",
    confirm_stop_job_body: "\"{title}\" stoppt, und nichts erreicht die Bibliothek.",
    confirm_stop_job_detail: "Es stoppt beim n\u00e4chsten Fortschrittsbericht der Engine - Sekunden bei faster-whisper, und bei OpenVINO, das keinen liefert, erst wenn die ganze Datei fertig ist. Die Aufnahme bleibt so oder so auf dem Server, sie kann also erneut eingereiht werden.",
    confirm_stop_job_ok: "Stoppen",
    clear_finished: "fertige leeren",
    confirm_clear_finished: "Fertige Auftr\u00e4ge leeren?",
    confirm_clear_finished_body: "{count} Zeilen verschwinden aus Auftr\u00e4ge.",
    confirm_clear_finished_detail: "Die Transkriptionen bleiben in der Bibliothek: Nichts wird gel\u00f6scht.",
    confirm_clear_finished_ok: "Liste leeren",
    level_label: "Eingangspegel",
    trace_label: "Die letzten f\u00fcnf Sekunden",
    wave_label: "Wie laut die Aufnahme ist, von Anfang bis Ende",
    recording_silent: "Diese Aufnahme ist nie \u00fcber Stille hinausgekommen: Pr\u00fcfen Sie, ob das richtige Mikrofon verwendet wird, bevor Sie der n\u00e4chsten vertrauen.",
    no_file: "W\u00e4hlen Sie zuerst eine Datei, oder nehmen Sie etwas auf.",
    uploading: "Wird hochgeladen...",
    terms: "{n} Begriffe",
    words: "{n} W\u00f6rter",
    row_summary_title: "Zusammenfassung: {title}",
    row_summary_of: "Zusammenfassung der Transkription",
    upload_failed: "Hochladen fehlgeschlagen: {error}",
    server_unreachable: "Der Server antwortet nicht. Nichts geht verloren: Diese Seite verbindet sich von selbst neu.",
    retry_now: "jetzt erneut versuchen",
    jobs_status_idle: "Nichts l\u00e4uft.",
    jobs_status: "{running} laufend, bei {percent}% \u00b7 {waiting} wartend",
    jobs_status_waiting: "{waiting} wartend.",
    library_results: "{count} Aufnahmen.",
    library_results_query: "{count} Aufnahmen passen zu \"{query}\".",
    source_tabs: "Was transkribiert werden soll",
    view_tabs: "Was von dieser Aufnahme angezeigt wird",
    interface_language: "Sprache",
    language_reload_title: "Sprache wechseln?",
    language_reload_body: "Die Seite wird in der neuen Sprache neu geladen, und die laufende Aufnahme oder der laufende Upload hier ginge verloren.",
    language_reload_ok: "Neu laden",
  },
};

let lang = "en";
/* Each language by its own name: the menu is read by somebody who may not
   read the one the page is in. The same list as i18n.LANGUAGE_NAMES. */
const LANGUAGE_NAMES = { en: "English", it: "Italiano", fr: "Fran\u00e7ais", de: "Deutsch" };
/* Written by the menu and read by the server, which is why it is a cookie
   and not localStorage: the status call, the errors and the jobs this page
   asks for come back in the language it is read in. */
const LANGUAGE_COOKIE = "interface_language";
let uploading = false;
let status = null;
let installed = [];
let selectedFile = null;
let polling = null;
let openEntryId = null;
/* Who the open entry says is talking, and the first thing each of them says:
   both read once when the entry opens, because the dialog that names them is
   built from the labels and a label is not a reminder of anything. */
let openSpeakers = [];
let openSamples = {};

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, children = []) => {
  const node = Object.assign(document.createElement(tag), props);
  for (const child of [].concat(children)) {
    if (child) node.append(child);
  }
  return node;
};

/* SVG nodes are not HTML nodes: el() above builds them in the wrong namespace
   and they draw nothing, and viewBox is not a property you can assign. Hence a
   second, smaller helper rather than a flag on the first. */
const SVG_NS = "http://www.w3.org/2000/svg";
const svg = (tag, attributes = {}) => {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attributes)) {
    node.setAttribute(name, value);
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

/* --- what the server would have printed --------------------------------- */

/* Folded away by default and polled only while it is open: a panel nobody has
   asked for must not fetch a tail of the log every three seconds for the
   whole time the page is left on a screen. */
let logWatch = null;

async function loadLog() {
  let data;
  try {
    data = await fetch(api("log")).then((r) => r.json());
  } catch {
    return;                        /* offline() already says so, once */
  }
  const box = $("log-text");
  const lines = data.lines || [];
  /* Follow the end unless the reader has scrolled up to look at something:
     a view that jumps back every three seconds cannot be read. */
  const atEnd = box.scrollTop >= box.scrollHeight - box.clientHeight - 4;
  box.textContent = lines.length ? lines.join("\n") : t("log_empty");
  if (atEnd) box.scrollTop = box.scrollHeight;
  $("log-path").textContent = t("log_where", { path: data.path || "" });
}

function showLog(open) {
  $("log-panel").hidden = !open;
  $("log-toggle").textContent = t(open ? "log_hide" : "log_show");
  $("log-toggle").setAttribute("aria-expanded", open ? "true" : "false");
  clearInterval(logWatch);
  logWatch = null;
  if (!open) return;
  loadLog();
  logWatch = setInterval(loadLog, 3000);
}

/* --- who is speaking ---------------------------------------------------- */

/* A diarized transcript arrives addressed to SPEAKER_00: the machine can hear
   that two people are talking and not who they are. One field per voice, each
   with the first thing that voice says under it, because "which one was
   SPEAKER_01" is a question this dialog should answer rather than ask.
   Resolves to {label: name} for the fields that were filled in, or to false.
   The blanks are left out, so naming one person does not rename the rest. */
function askSpeakers(speakers, samples = {}) {
  const dialog = $("speakers");
  const box = $("speakers-fields");
  box.textContent = "";
  const fields = {};
  speakers.forEach((label, index) => {
    const id = `speaker-name-${index}`;
    const input = el("input", { type: "text", id,
                                placeholder: t("speakers_hint") });
    fields[label] = input;
    box.append(el("div", { className: "field" }, [
      el("label", { htmlFor: id, textContent: label }),
      samples[label]
        ? el("p", { className: "note", textContent: shorten(samples[label]) })
        : null,
      input,
    ]));
  });

  return new Promise((resolve) => {
    const finish = (answer) => {
      $("speakers-ok").removeEventListener("click", onOk);
      $("speakers-cancel").removeEventListener("click", onCancel);
      dialog.removeEventListener("close", onCancel);
      dialog.close();
      resolve(answer);
    };
    const onOk = () => {
      const names = {};
      for (const [label, input] of Object.entries(fields)) {
        if (input.value.trim()) names[label] = input.value.trim();
      }
      finish(Object.keys(names).length ? names : false);
    };
    const onCancel = () => finish(false);
    $("speakers-ok").addEventListener("click", onOk);
    $("speakers-cancel").addEventListener("click", onCancel);
    dialog.addEventListener("close", onCancel);
    dialog.showModal();
    const first = speakers.length ? fields[speakers[0]] : null;
    (first || $("speakers-cancel")).focus();
  });
}

/* One line of what somebody said, cut at a word if it has to be cut. */
function shorten(text, limit = 60) {
  const line = String(text || "").split(/\s+/).filter(Boolean).join(" ");
  return line.length <= limit
    ? line
    : `${line.slice(0, limit).replace(/\s\S*$/, "")}…`;
}

/* The first thing each speaker says, by label. From the segments rather than
   the transcript: that has already had its turns merged. */
function firstLines(segments) {
  const said = {};
  for (const segment of segments) {
    const label = segment.speaker;
    const text = (segment.text || "").trim();
    if (label && text && !(label in said)) said[label] = text;
  }
  return said;
}

/* --- when the server stops answering ----------------------------------- */

/* The page polls, so a server that goes away is invisible: the last state
   sits there looking alive. One banner, and every periodic fetch reports
   through it. */
function offline(down, retry = null) {
  const banner = $("offline");
  if (!down) {
    banner.hidden = true;
    banner.textContent = "";
    return;
  }
  if (banner.hidden) {
    banner.textContent = `${t("server_unreachable")} `;
    if (retry) {
      const again = el("button", { type: "button", className: "link",
                                   textContent: t("retry_now") });
      again.addEventListener("click", retry);
      banner.append(again);
    }
    banner.hidden = false;
  }
}

function translatePage() {
  document.documentElement.lang = lang;
  for (const node of document.querySelectorAll("[data-t]")) {
    node.textContent = t(node.dataset.t);
  }
  /* Written here rather than in the markup: an aria-label typed into the HTML
     is a string that never reaches the catalogue, and the page then announces
     one language while it shows another. */
  $("source-tabs").setAttribute("aria-label", t("source_tabs"));
  $("view-tabs").setAttribute("aria-label", t("view_tabs"));
  $("record-level").setAttribute("aria-label", t("level_label"));
  $("record-trace").setAttribute("aria-label", t("trace_label"));
  /* Zero is not a value here, it is "whatever the preset says" - which is what
     the window's spin boxes write in the same place. */
  for (const id of ["subtitle-chars", "subtitle-words"]) {
    $(id).placeholder = t("sub_from_preset");
  }
  $("set-text").placeholder = t("set_placeholder");
  $("set-search").placeholder = "";
  $("notes-text").placeholder = t("notes_placeholder");
  /* The three copy buttons carry a drawing and no words, so their name is an
     attribute: without it a screen reader announces "button" and nothing. */
  for (const id of ["copy-transcript", "copy-summary", "copy-notes"]) {
    $(id).title = t("copy");
    $(id).setAttribute("aria-label", t("copy"));
  }
  $("search").placeholder = t("search_placeholder");
  /* The log's toggle says one of two things and the pass above knows only
     the first: left alone it would offer to show a panel that is open. */
  $("log-toggle").textContent = t($("log-panel").hidden ? "log_show"
                                                        : "log_hide");
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

/* The same two the window shows in its queue, formatted the same way. */
const UNITS = ["B", "KiB", "MiB", "GiB", "TiB"];

function bytes(size) {
  if (!size) return "";
  let value = Number(size);
  for (const unit of UNITS) {
    if (value < 1024 || unit === UNITS[UNITS.length - 1]) {
      return unit === "B" ? `${Math.round(value)} ${unit}`
                          : `${value.toFixed(1)} ${unit}`;
    }
    value /= 1024;
  }
  return "";
}

function when(timestamp) {
  /* ISO with a zone is right for a file and wrong for a row: the seconds and
     the offset are noise next to a dozen recordings to tell apart. */
  const text = String(timestamp || "");
  return text.length >= 16 ? text.slice(0, 16).replace("T", " ") : "";
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
    // Roving tabindex: Tab reaches the tab strip once and lands on the tab
    // that is open; the arrows move between them, as role="tab" promises.
    $(tab).tabIndex = name === which ? 0 : -1;
    $(pane).hidden = name !== which;
  }
}

/* A tab strip that announces itself as one has to behave like one: a screen
   reader tells its user to press the arrows, and until now nothing happened. */
function wireTabs(tablist, ids, show) {
  const tabs = ids.map((id) => $(id));
  tablist.addEventListener("keydown", (event) => {
    const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 1, ArrowUp: -1 }[event.key];
    const jump = { Home: 0, End: tabs.length - 1 }[event.key];
    if (step === undefined && jump === undefined) return;
    event.preventDefault();
    const here = Math.max(0, tabs.indexOf(document.activeElement));
    const next = jump !== undefined
      ? jump : (here + step + tabs.length) % tabs.length;
    show(next);
    tabs[next].focus();
  });
}

$("tab-file").addEventListener("click", () => showPane("file"));
$("tab-record").addEventListener("click", () => showPane("record"));
wireTabs($("source-tabs"), ["tab-file", "tab-record"],
         (index) => showPane(["file", "record"][index]));

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

/* --- what the run is for ---------------------------------------------- */

function chosenOutput() {
  const picked = document.querySelector('input[name="output"]:checked');
  return picked ? picked.value : "text";
}

/* Put away the controls the chosen answer does not use: a subtitle preset
   next to "just the text" is a control that does nothing, and a control that
   does nothing is a question the form cannot answer. */
/* The two answers that ask who was speaking. They are what the count of
   voices belongs to, and what a machine without pyannote cannot offer. */
const DIARIZING = ["speakers", "subtitles_speakers"];
const SUBTITLING = ["subtitles", "subtitles_speakers"];

function applyOutput() {
  const output = chosenOutput();
  const subtitling = SUBTITLING.includes(output);
  $("output-note").textContent = t(`output_${output}_note`);
  $("subtitle-fields").hidden = !subtitling;
  /* Disabled, not hidden: it sits on the line of the answer it belongs to,
     and a line that appears and disappears moves the answers underneath it
     out from under the pointer. */
  const asked = DIARIZING.includes(output) && !$("output-speakers").disabled;
  $("speakers").disabled = !asked;
  $("speakers-field").classList.toggle("unavailable", !asked);
  if (subtitling && !$("save-srt").checked && !$("save-vtt").checked) {
    // The chosen output is the files, so one is written either way: showing
    // it ticked is more honest than saving an .srt behind an empty box.
    $("save-srt").checked = true;
  }
}

for (const name of ["text", "speakers", "subtitles", "subtitles-speakers"]) {
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

/* Levels arrive as whole numbers out of this, the same figure the server
   writes into an entry's waveform.json. */
const LOUDNESS_SCALE = 1000;

/* How many columns the live trace holds: one every tenth of a second, which
   is how often the level is read, so five seconds is fifty of them. */
const TRACE_COLUMNS = 50;

let trace = [];

function drawTrace() {
  /* Fifty spans whose heights change, not fifty spans rebuilt: this runs ten
     times a second for as long as the recording lasts. */
  const box = $("record-trace");
  if (box.childElementCount !== TRACE_COLUMNS) {
    box.textContent = "";
    for (let column = 0; column < TRACE_COLUMNS; column += 1) {
      box.append(el("span"));
    }
  }
  const columns = box.children;
  for (let column = 0; column < TRACE_COLUMNS; column += 1) {
    /* Oldest on the left, so the trace runs the way the clock beside it does
       and the newest column is the one the level meter is showing. */
    const behind = TRACE_COLUMNS - 1 - column;
    const peak = trace[trace.length - 1 - behind];
    const height = peak === undefined ? 0 : levelPercent(peak);
    columns[column].style.height = `${Math.max(height, 2)}%`;
  }
}

function clearTrace() {
  trace = [];
  const box = $("record-trace");
  box.textContent = "";
  box.hidden = true;
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
  trace = [];
  $("record-trace").hidden = false;
  levelTimer = setInterval(() => {
    analyser.getFloatTimeDomainData(samples);
    let peak = 0;
    for (const sample of samples) peak = Math.max(peak, Math.abs(sample));
    loudest = Math.max(loudest, peak);
    const percent = levelPercent(peak);
    meter.firstElementChild.style.width = `${percent}%`;
    meter.setAttribute("aria-valuenow", percent);
    /* And the same reading, kept. The meter says how loud it is now; five
       seconds of it say whether that is a voice or a fan. */
    trace.push(peak);
    if (trace.length > TRACE_COLUMNS) trace.shift();
    drawTrace();
  }, 100);
}

function stopWatchingLevel() {
  clearInterval(levelTimer);
  levelTimer = null;
  const meter = $("record-level");
  meter.firstElementChild.style.width = "0%";
  meter.setAttribute("aria-valuenow", 0);
  meter.hidden = true;
  clearTrace();
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
  const label = stage ? `${t(job.status)}: ${stage}` : t(job.status);
  /* And how long it has been at it. A diarization step can take twenty
     minutes, and inside one the bar does not move at all: something on the
     row has to be going up, or a job that is working looks like a job that
     has hung. */
  const running = job.status === "running" ? duration(job.running_seconds) : "";
  return running ? `${label} · ${running}` : label;
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

/* What the list amounts to, in one line.
   It is this line that is announced, not the list: the list is rewritten on
   every poll, and a live region around it makes a screen reader read every
   job again every three seconds for the length of a transcription. */
function announceJobs(jobs) {
  const running = jobs.filter((job) => job.status === "running");
  const waiting = jobs.filter((job) => job.status === "queued").length;
  const line = running.length
    ? t("jobs_status", { running: running.length, percent: running[0].progress,
                         waiting })
    : waiting ? t("jobs_status_waiting", { waiting }) : t("jobs_status_idle");
  const box = $("jobs-status");
  // Only when it actually changed: an unchanged live region that is rewritten
  // is still announced.
  if (box.textContent !== line) box.textContent = line;
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
  // The controls that belong to an answer rather than to the queue go back
  // to what the answer says, not to enabled: the count of voices is asked by
  // two of the four answers and by none of the others.
  if (!pageBusy) applyOutput();
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
  announceJobs(jobs);
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
    /* What the recording is, before anything has been done to it - how big,
       and when it was made - because a queue of a dozen files named by date
       is told apart by those two before it is told apart by anything else.
       A summary has none of them: no recording of its own, and the title of
       the entry it reads, which made it the twin of the transcription that
       produced that entry. It says what it is instead. */
    const isSummary = job.kind === "summary";
    const facts = [isSummary ? t("row_summary_of") : "",
      duration(job.audio_duration), bytes(job.size_bytes),
      when(job.source_created_at), job.model, job.language,
      job.vocabularies.join(", "),
      job.words ? t("words", { n: job.words }) : "",
      job.elapsed_seconds ? t("took", { time: duration(job.elapsed_seconds) }) : ""]
      .filter(Boolean).join(" · ");
    const state = el("span", { className: `state${job.status === "failed" ? " failed" : ""}`,
                               textContent: stateText(job) });
    const meta = el("div", { className: "meta" }, [state]);
    if (facts) meta.append(` · ${facts}`);
    const actions = el("div", { className: "actions" });
    const row = el("div", { className: "row" }, [
      el("div", {}, [
        el("div", { className: "title",
                    textContent: isSummary
                      ? t("row_summary_title", { title: job.title })
                      : job.title }),
        // Measured in the background while the row waits its turn, so a queue
        // of half a dozen files named by date is told apart before any of
        // them has been transcribed.
        job.loudness && job.loudness.length ? waveDrawing(job.loudness) : null,
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
    if (job.status === "held") {
      const start = el("button", { type: "button", className: "link", textContent: t("start_job") });
      start.addEventListener("click", async () => {
        try {
          await fetch(api(`jobs/${job.id}/start`), { method: "POST" });
          refreshJobs();
        } catch (error) {
          console.error("Failed to start job:", error);
        }
      });
      actions.append(start);
    }
    if (job.status === "queued" || job.status === "running") {
      const stop = el("button", { type: "button", className: "link",
                                  textContent: job.status === "running"
                                    ? t("stop_job") : t("take_out_of_queue") });
      stop.addEventListener("click", () => cancelJob(job));
      actions.append(stop);
    }
    if (["done", "failed", "cancelled", "held"].includes(job.status)) {
      const remove = el("button", { type: "button", className: "link",
                                    textContent: t("remove_from_list"),
                                    disabled: pageBusy && job.status !== "held",
                                    title: (pageBusy && job.status !== "held") ? t("busy_why") : "" });
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
                             "aria-label": stateText(job),
                             "aria-valuemin": 0, "aria-valuemax": 100,
                             "aria-valuenow": job.progress }, [
        el("span", { style: `width:${job.progress}%` }),
      ]));
    }
    box.append(row);
  }
}

async function refreshJobs() {
  let data;
  try {
    data = await fetch(api("jobs")).then((r) => r.json());
    offline(false);
  } catch (error) {
    offline(true, refreshJobs);
    return;                     // the list keeps the last state, and says so
  }
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

/* --- what the machine is doing ----------------------------------------- */

/* The meters under the job list, on their own timer: slower than the job
   poll, and stopped while the page is not on screen. This server has two
   cores and a tab left open in the background must not spend them answering
   how busy they are. */

const MACHINE_MS = 2500;
let machineTimer = null;

/* A figure in GiB the way this language writes it: "1,6" and not "1.6" in
   Italian, which is the difference between a number and a typo. */
const gib = (value) => value.toLocaleString(lang, { maximumFractionDigits: 1 });

function drawMeter(name, percent, text) {
  const line = $(`${name}-meter`);
  line.hidden = percent === null;
  if (percent === null) return;     // nothing measured: no bar, not a zero
  const bar = $(`${name}-level`);
  bar.firstElementChild.style.width = `${Math.min(100, percent)}%`;
  bar.setAttribute("aria-valuenow", Math.round(percent));
  $(`${name}-note`).textContent = text;
}

async function refreshMachine() {
  let data;
  try {
    data = await fetch(api("machine")).then((r) => r.json());
  } catch (error) {
    /* Silent on purpose: refreshJobs() owns the offline banner, and a second
       one shouting the same thing every two seconds helps nobody. */
    $("machine").hidden = true;
    return;
  }
  const cpu = typeof data.cpu_percent === "number" ? data.cpu_percent : null;
  const ram = typeof data.ram_percent === "number" ? data.ram_percent : null;
  drawMeter("cpu", cpu, cpu === null ? "" : t(
    data.load ? "cpu_reading_load" : "cpu_reading",
    { percent: Math.round(cpu), cores: data.cores, load: data.load?.[0] }));
  drawMeter("ram", ram, ram === null ? "" : t("ram_reading", {
    used: gib(data.ram_used_gb), total: gib(data.ram_total_gb) }));
  /* The percentage says how hard something is working, never at what: on a
     machine with an iGPU that is the whole question. */
  $("machine-engine").textContent = data.engine
    ? t(data.device ? "engine_on" : "engine_only",
        { engine: data.engine, device: data.device })
    : t("engine_missing");
  // A machine that measures neither shows no panel rather than two empty rows.
  $("machine").hidden = cpu === null && ram === null;
  // Memory is the figure worth a colour here: a full disk is an error
  // message, a full memory is a job killed halfway through.
  $("ram-level").classList.toggle("tight", ram !== null && ram >= 90);
}

function watchMachine() {
  clearInterval(machineTimer);
  machineTimer = null;
  if (document.hidden) return;
  refreshMachine();
  machineTimer = setInterval(refreshMachine, MACHINE_MS);
}

document.addEventListener("visibilitychange", watchMachine);

/* --- what a recording looks like ---------------------------------------- */

/* The same reading as the level meter, at the length of a whole recording:
   decibels with the floor at -60 dBFS. Drawn linearly, a row of speech would be
   a flat line with four bumps in it. What arrives is the loudness of each
   slice rather than its loudest instant, because over three seconds of
   anything there is always one bang: see waveform.py. */
function wavePath(loudness, width = 400, height = 100) {
  const columns = loudness.length;
  if (!columns) return "";
  const step = width / columns;
  const middle = height / 2;
  /* Never quite nothing: a silent passage should read as a thin line through
     the middle, which is a statement, and not as a gap, which looks broken. */
  const arms = loudness.map((level) =>
    Math.max(0.6, (levelPercent(level / LOUDNESS_SCALE) / 100) * middle));
  const points = [];
  for (let column = 0; column < columns; column += 1) {
    const x = column * step;
    const y = (middle - arms[column]).toFixed(2);
    points.push(`${x.toFixed(2)} ${y}`, `${(x + step).toFixed(2)} ${y}`);
  }
  for (let column = columns - 1; column >= 0; column -= 1) {
    const x = column * step;
    const y = (middle + arms[column]).toFixed(2);
    points.push(`${(x + step).toFixed(2)} ${y}`, `${x.toFixed(2)} ${y}`);
  }
  return `M${points.join("L")}Z`;
}

function waveDrawing(loudness) {
  /* preserveAspectRatio="none" on purpose: stretching the picture sideways to
     whatever the row is wide is exactly what is wanted of it. */
  const box = svg("svg", { class: "wave", viewBox: "0 0 400 100",
                           preserveAspectRatio: "none", focusable: "false",
                           role: "img", "aria-label": t("wave_label") });
  box.append(svg("path", { d: wavePath(loudness) }));
  return box;
}

/* Entries filed before this program could draw them have no measurement yet,
   and making one is a pass of ffmpeg over the whole recording. So they are
   asked for one at a time, and only for the rows somebody has actually
   scrolled to: a library of forty would otherwise spend a quarter of an hour
   of a two-core server drawing pictures nobody looked at. */
const waveWanted = [];
let waveBusy = false;

const waveWatcher = window.IntersectionObserver
  ? new IntersectionObserver((seen, watcher) => {
      for (const row of seen) {
        if (!row.isIntersecting) continue;
        watcher.unobserve(row.target);
        waveWanted.push(row.target);
        drawNextWave();
      }
    }, { rootMargin: "200px" })
  : null;

function waveSlot(entryId) {
  /* Empty, but the height of the drawing that will replace it: a list that
     reflows under the pointer as the pictures arrive is worse than one that
     waits a moment for them. */
  const slot = el("span", { className: "wave-slot" });
  slot.dataset.entry = entryId;
  if (waveWatcher) waveWatcher.observe(slot);
  else waveWanted.push(slot);
  return slot;
}

async function drawNextWave() {
  if (waveBusy) return;
  const slot = waveWanted.shift();
  if (!slot) return;
  waveBusy = true;
  try {
    if (slot.isConnected) {
      const found = await fetch(api(`library/${encodeURIComponent(slot.dataset.entry)}/waveform`))
        .then((answer) => (answer.ok ? answer.json() : null));
      if (found && found.loudness && found.loudness.length && slot.isConnected) {
        slot.replaceWith(waveDrawing(found.loudness));
      }
    }
  } catch (error) {
    /* No drawing, and the row is still a row. An entry whose recording lives
       elsewhere on disk never gets one, and that is not an error either. */
  }
  waveBusy = false;
  if (waveWanted.length) drawNextWave();
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
  let data;
  try {
    data = await fetch(url).then((r) => r.json());
    offline(false);
  } catch (error) {
    offline(true, refreshLibrary);
    return;
  }
  const box = $("library");
  box.textContent = "";
  // The rows about to go are the ones those were waiting for. disconnect()
  // also lets go of the slots the watcher is still holding, which a list
  // re-read on every keystroke would otherwise accumulate.
  waveWanted.length = 0;
  if (waveWatcher) waveWatcher.disconnect();
  // The count is announced, and is also worth having on screen: a search that
  // returns nothing and a search that returns forty looked the same.
  $("library-status").textContent = query
    ? t("library_results_query", { count: data.entries.length, query })
    : t("library_results", { count: data.entries.length });
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
        // Under the name, because it says what the recording is in a way the
        // facts under it cannot: an hour of meeting and an hour of empty room
        // have the same date, the same length and the same model.
        entry.loudness && entry.loudness.length ? waveDrawing(entry.loudness)
                                          : waveSlot(entry.id),
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
  await loadSummaryTemplates();
}

/* The value the "my own sections" entry of the menu carries. Not a template
   name: names are slugs, and this one has to be impossible to collide with. */
const OWN_TEMPLATE = "__own__";

async function loadSummaryTemplates() {
  /* Which pages this machine offers, plus the two that are not files: the
     one the recording decides, and the one typed into the box below. */
  let found = [];
  try {
    ({ templates: found } =
      await fetch(api(`summary/templates?language=${encodeURIComponent(lang)}`))
        .then((r) => r.json()));
  } catch {
    found = [];
  }
  const select = $("summary-template");
  select.textContent = "";
  select.append(el("option", { value: "", textContent: t("summary_template_auto") }));
  for (const item of found) {
    select.append(el("option", { value: item.name, textContent: item.title }));
  }
  select.append(el("option", { value: OWN_TEMPLATE,
                               textContent: t("summary_template_mine") }));
  select.value = "";
  showOwnTemplate();
}

function showOwnTemplate() {
  $("summary-template-own").hidden = $("summary-template").value !== OWN_TEMPLATE;
}

$("summary-template").addEventListener("change", showOwnTemplate);

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
    ["transcript", "tab-transcript", "viewer-transcript"],
    ["segments", "tab-segments", "viewer-segments"],
    ["summary", "tab-summary", "viewer-summary"],
    ["notes", "tab-notes", "viewer-notes"],
  ]) {
    $(tab).classList.toggle("on", name === which);
    $(tab).setAttribute("aria-selected", String(name === which));
    $(tab).tabIndex = name === which ? 0 : -1;
    $(pane).hidden = name !== which;
  }
  /* Each tab owns its own buttons in the shared footer, so the row never
     offers an action that belongs to a panel nobody is looking at. */
  $("notes-save").hidden = which !== "notes";
  $("summary-run").hidden = which !== "summary";
  $("summary-delete").hidden = which !== "summary" || !summaryPresent;
  $("viewer-download-summary").hidden = which !== "summary" || !summaryPresent;
  $("copy-summary").hidden = which !== "summary" || !summaryPresent;
}

$("tab-transcript").addEventListener("click", () => showViewerTab("transcript"));
$("tab-segments").addEventListener("click", () => showViewerTab("segments"));
$("tab-summary").addEventListener("click", () => showViewerTab("summary"));
$("tab-notes").addEventListener("click", () => showViewerTab("notes"));
wireTabs($("view-tabs"), ["tab-transcript", "tab-segments", "tab-notes"],
         (index) => showViewerTab(["transcript", "segments", "notes"][index]));

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
  openSpeakers = entry.speakers || [];
  openSamples = firstLines(entry.segments || []);
  /* Hidden rather than disabled on a run that was not diarized: there is
     nobody to name, and a dead button is a question about a feature that does
     not apply to what is being read. */
  $("viewer-speakers").hidden = openSpeakers.length === 0;
  $("notes-text").value = entry.notes || "";
  $("notes-status").textContent = "";
  $("viewer-status").textContent = "";
  $("viewer-status").className = "note";
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
  showSummaryProgress(null);
  $("summary-run").disabled = pageBusy;
  $("viewer").close();
}

async function reloadOpenEntry() {
  const entry = await fetch(api(`library/${encodeURIComponent(openEntryId)}`))
    .then((r) => r.json());
  showSummary(entry);
  showViewerTab("summary");
}

function showSummaryProgress(job) {
  /* The same bar a job row has. A summary reads an hour of transcript through
     a model: "being written" on its own says nothing about where it is. */
  const bar = $("summary-progress");
  bar.hidden = job === null;
  if (job === null) return;
  bar.firstElementChild.style.width = `${job.progress || 0}%`;
  bar.setAttribute("aria-valuenow", job.progress || 0);
  bar.setAttribute("aria-label", t("summary_running",
                                   { stage: stageLabel(job.stage) }));
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
      showSummaryProgress(null);
    } else if (job.status === "running") {
      const clock = duration(job.running_seconds);
      $("summary-status").textContent = t("summary_running",
                                          { stage: stageLabel(job.stage) })
        + ` · ${job.progress}%` + (clock ? ` · ${clock}` : "");
      showSummaryProgress(job);
    } else {
      clearInterval(summaryWatch);
      summaryWatch = null;
      showSummaryProgress(null);
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
                           length: $("summary-length").value || "",
                           style: $("summary-style").value || "",
                           template: chosenTemplate(),
                           template_text: chosenTemplateText() }),
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

function chosenTemplate() {
  const picked = $("summary-template").value;
  return picked === OWN_TEMPLATE ? "" : picked;
}

function chosenTemplateText() {
  return $("summary-template").value === OWN_TEMPLATE
    ? $("summary-template-text").value.trim() : "";
}

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

/* One button per pane, each saying so where that pane says things: the
   transcript has no line of its own, the summary and the notes do. */
function copyPane(text, statusId) {
  return async () => {
    const said = $(statusId);
    try {
      if (navigator.clipboard) await navigator.clipboard.writeText(text());
      else copyWithFallback(text());
      said.textContent = t("copied");
      said.className = "note";
    } catch {
      said.textContent = t("copy_failed");
      said.className = "error";
    }
  };
}

$("copy-transcript").addEventListener(
  "click", copyPane(() => $("viewer-text").textContent || "", "viewer-status"));
$("copy-summary").addEventListener(
  "click", copyPane(() => $("summary-text").textContent || "", "summary-status"));
$("copy-notes").addEventListener(
  "click", copyPane(() => $("notes-text").value || "", "notes-status"));

function copyWithFallback(text) {
  /* navigator.clipboard needs a secure context (https, or localhost): the
     same boundary the recorder already runs into. A hidden textarea and the
     legacy command still work over a plain http tunnel. */
  const area = el("textarea", { value: text });
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  document.execCommand("copy");
  area.remove();
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

$("log-toggle").addEventListener("click", () => showLog($("log-panel").hidden));
$("log-refresh").addEventListener("click", loadLog);
$("log-clear").addEventListener("click", async () => {
  /* Small as it is, it destroys something: the rule on this page is that
     nothing goes without being asked, and a log emptied by a mis-click is the
     hour before a crash gone. */
  const sure = await ask({
    title: t("confirm_clear_log"),
    body: t("confirm_clear_log_body"),
    confirmLabel: t("log_clear"),
  });
  if (!sure) return;
  await fetch(api("log"), { method: "DELETE" });
  loadLog();
});

$("viewer-speakers").addEventListener("click", async () => {
  const names = await askSpeakers(openSpeakers, openSamples);
  if (!names) return;
  const response = await fetch(
    api(`library/${encodeURIComponent(openEntryId)}/speakers`),
    { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ names }) });
  const box = $("viewer-status");
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    box.textContent = t("speakers_failed",
                        { error: detail.detail || response.statusText });
    box.className = "error";
    return;
  }
  /* The whole entry again rather than the transcript alone: two labels given
     the same name have had their turns run together, so the segments on
     screen are no longer the segments on disk. */
  const named = (await response.json()).speakers || [];
  await openEntry(openEntryId);
  refreshLibrary();
  box.textContent = t("speakers_named", { speakers: named.join(", ") });
  box.className = "note";
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
  /* The answer, and nothing it implies: diarization and the subtitle format
     are settled by the server (config.resolve_output), in the one place all
     three interfaces go through. */
  body.append("output", chosenOutput());
  if ($("auto-title").checked) body.append("auto_title", "true");
  if ($("summary-after").checked) body.append("summary_after", "true");
  if ($("speakers").value && !$("speakers").disabled) {
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
  // A text somebody already has: it helps the engine spell and then
  // proof-reads it. Empty means "just transcribe".
  body.append("reference", $("reference").value.trim());

  const button = $("submit");
  button.disabled = true;
  button.textContent = t("uploading");
  uploading = true;
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
    uploading = false;
    // Not simply "false": the upload has just made the page busy, and the
    // button it was clicked on is one of the things that goes off.
    button.disabled = pageBusy;
    button.textContent = t("start");
  }
});

/* --- about ------------------------------------------------------------- */

/* Fetched once and kept: neither the version nor the licence changes while
   the page is open. */
let aboutFacts = null;

async function openAbout() {
  if (!aboutFacts) {
    try {
      aboutFacts = await fetch(api("about")).then((r) => r.json());
    } catch (error) {
      /* The page is talking to a server that has stopped answering. The
         banner already says so; opening an empty dialog on top of it would
         only say it worse. */
      offline(true, openAbout);
      return;
    }
  }
  $("about-version").textContent = t("about_version", {
    version: aboutFacts.version,
  });
  $("about-licence-name").textContent =
    aboutFacts.licence_title || aboutFacts.spdx;
  /* textContent, not innerHTML: a licence is text, and this one is the only
     screen in the program that shows a whole file. */
  $("about-licence").textContent =
    aboutFacts.licence_text || t("about_licence_missing");

  const fonts = $("about-fonts");
  fonts.textContent = `${t("about_fonts")} `;
  (aboutFacts.fonts || []).forEach((font, index) => {
    if (index) fonts.append(document.createTextNode(", "));
    const label = `${font.family} (${font.licence})`;
    fonts.append(font.licence_url
      ? el("a", { className: "link", href: font.licence_url, textContent: label,
                  target: "_blank", rel: "noopener" })
      : document.createTextNode(label));
  });
  fonts.append(document.createTextNode("."));
  $("about").showModal();
}

$("about-open").addEventListener("click", openAbout);
$("about-close").addEventListener("click", () => $("about").close());

/* --- the language of the page ------------------------------------------ */

function fillLanguages() {
  const menu = $("interface-language");
  menu.textContent = "";
  for (const code of Object.keys(I18N)) {
    menu.append(el("option", { value: code, textContent: LANGUAGE_NAMES[code] || code,
      selected: code === lang }));
  }
}

/* The page is loaded again in the new language: every label written since it
   opened was written in the old one. A recording, one not sent yet or an
   upload under way would not survive that, so it asks first. The cookie is
   scoped to the page's own folder, which behind a proxy is its prefix. */
$("interface-language").addEventListener("change", async (event) => {
  const chosen = event.target.value;
  const recording = recorder && recorder.state !== "inactive";
  if (recording || uploading || !$("record-preview").hidden) {
    const go = await ask({ title: t("language_reload_title"),
                           body: t("language_reload_body"),
                           confirmLabel: t("language_reload_ok") });
    if (!go) {
      event.target.value = lang;
      return;
    }
  }
  const folder = location.pathname.replace(/[^/]*$/, "");
  document.cookie = `${LANGUAGE_COOKIE}=${chosen}; path=${folder}; max-age=31536000; SameSite=Strict`;
  location.reload();
});

/* --- start ------------------------------------------------------------- */

async function start() {
  try {
    status = await fetch(api("status")).then((r) => r.json());
  } catch (error) {
    /* Every label on this page is filled in by translatePage(), so a status
       call that fails used to leave the titles and the buttons literally
       empty. The English text is in the markup; leave it there and say what
       happened. */
    offline(true, start);
    return;
  }
  offline(false);
  lang = I18N[status.interface_language] ? status.interface_language : "en";
  translatePage();
  fillLanguages();

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
  $("auto-title").checked = Boolean(status.defaults.auto_title);
  $("summary-after").checked = Boolean(status.defaults.summary_after);
  const chosen = $(`output-${(status.defaults.output || "text").replace(/_/g, "-")}`);
  if (chosen) chosen.checked = true;
  if (!diarization.available) {
    // An answer this machine cannot produce is not offered: a job that fails
    // after the wait is a worse way to find that out.
    for (const output of DIARIZING) {
      const id = `output-${output.replace(/_/g, "-")}`;
      $(id).disabled = true;
      $(id).dataset.locked = "1";
      $(id).closest(".field").classList.add("unavailable");
      if ($(id).checked) $("output-text").checked = true;
    }
    $("diarize-note").textContent = t(`diarize_${diarization.reason}`);
    $("diarize-note").hidden = false;
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
  watchMachine();
}

start();
