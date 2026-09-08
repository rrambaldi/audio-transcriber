"""Minimal message catalogue for user-facing strings.

The code, its comments and its docstrings are English; only the text the user
actually reads is translated. English is the source of truth: a key missing
from another catalogue falls back to English, and a key missing everywhere is
returned verbatim so a typo is loud instead of silent.

Language resolution order: :func:`set_language` (the ``--lang`` option), the
``AUDIO_TRANSCRIBER_LANG`` environment variable, the system locale, English.
"""
import locale
import os

DEFAULT_LANGUAGE = "en"
ENV_LANGUAGE = "AUDIO_TRANSCRIBER_LANG"

MESSAGES = {
    "en": {
        # --- audio decoding -------------------------------------------------
        "audio.no_bundled_ffmpeg":
            "  WARNING: 'imageio-ffmpeg' is not installed, falling back to the system ffmpeg.\n"
            "  If you see DLL errors (libintl/fontconfig) run: pip install imageio-ffmpeg",
        "audio.ffmpeg_not_found": "ffmpeg not found. Run: pip install imageio-ffmpeg",
        "audio.decode_failed": "ffmpeg failed to decode the audio:\n{details}",

        # --- hardware -------------------------------------------------------
        "hardware.summary":
            "CPU: {cores} cores | free RAM: {ram} | OpenVINO: {openvino} | CUDA: {cuda}",
        "hardware.unknown": "unknown",
        "hardware.not_installed": "not installed",
        "hardware.yes": "yes",
        "hardware.no": "no",
        "hardware.auto_backend": "backend that '--backend auto' would pick: {backend}",
        "hardware.auto_model": "model that '--model auto' would pick: {model}",
        "hardware.diarize_ready": "diarization ('who said what'): available ({detail})",
        "hardware.diarize_missing":
            "diarization ('who said what'): not installed\n"
            "  pip install \"audio-transcriber-ov[diarize]\"  (pulls in PyTorch, about 2 GB)",
        "hardware.diarize_unconfigured":
            "diarization ('who said what'): installed, but no model\n"
            "  set HUGGINGFACE_TOKEN, or put a local config at {detail}",

        # --- backend selection ----------------------------------------------
        "backend.unknown": "Unknown backend: {name}. Valid values: {valid}",
        "backend.none_installed":
            "No transcription backend is installed.\n"
            "  Server or machine without a GPU:  pip install \"audio-transcriber-ov[cpu]\"\n"
            "  PC with an Intel iGPU/NPU:        pip install \"audio-transcriber-ov[openvino]\"",
        "backend.low_ram":
            "  WARNING: '{model}' needs about {needed:.1f} GiB but only {free:.1f} GiB are free.\n"
            "  You risk swapping or an out-of-memory kill: consider --model medium/small{hint}.",
        "backend.low_ram_hint": " or --backend faster-whisper (int8, half the memory)",
        "backend.few_cores":
            "  WARNING: only {cores} cores available: '{model}' on CPU can take far longer\n"
            "  than the recording itself. On a machine like this '--model small' is much\n"
            "  more practical (roughly 0.6x realtime).",

        # --- OpenVINO backend -----------------------------------------------
        "openvino.missing":
            "Backend 'openvino': optimum-intel is not installed.\n"
            "  pip install \"audio-transcriber-ov[openvino]\"\n"
            "  (or: pip install \"optimum-intel[openvino]\" transformers)",
        "openvino.device_unavailable":
            "  WARNING: device '{requested}' is not available (found: {found}); using {fallback}.",
        "openvino.reusing_model": "Reusing the already converted OpenVINO model: {path}",
        "openvino.converting": "Downloading and converting '{model}' to OpenVINO (first run only)...",
        "openvino.model_saved": "Model saved to: {path}",
        "openvino.compiling": "Compiling for device '{device}'...",
        "openvino.compile_warning": "  (compile: {error})",
        "openvino.prompt_failed":
            "  (initial prompt not applied: {error}\n   retrying without it)",

        # --- faster-whisper backend -----------------------------------------
        "faster_whisper.missing":
            "Backend 'faster-whisper': the package is not installed.\n"
            "  pip install \"audio-transcriber-ov[cpu]\"\n"
            "  (or: pip install faster-whisper)",
        "faster_whisper.no_cuda":
            "  WARNING: no CUDA GPU available for faster-whisper; using the CPU.",
        "faster_whisper.unknown_size":
            "  WARNING: '{model}' is not a size faster-whisper knows; trying to load it anyway.",
        "faster_whisper.loading":
            "Loading Whisper '{model}' with faster-whisper "
            "(device: {device}, precision: {compute_type}, threads: {threads})...",
        "faster_whisper.cache": "  (model cache: {path} — downloaded on first run only)",
        "faster_whisper.compute_type_unsupported":
            "  (precision '{compute_type}' is not supported: {error}\n"
            "   falling back to '{fallback}')",
        "faster_whisper.load_failed": "faster-whisper: could not load the model: {error}",
        "faster_whisper.detected_language":
            "  detected language: {language} (confidence {probability:.2f})",

        # --- transcription --------------------------------------------------
        "model.auto": "Model 'auto': using '{model}' ({cores} cores, {ram} GiB free).",
        "transcribe.running": "Transcribing...",
        "transcribe.progress": "  progress: {percent:3d}%",
        "transcribe.empty": "Nothing was transcribed (empty or silent audio?).",

        # --- diarization ----------------------------------------------------
        "diarize.missing": "Diarization: pyannote is not installed. Run: pip install pyannote.audio",
        "diarize.local_config_missing":
            "  Pre-flight: local config not found ({path}); the HF repo would be used instead.",
        "diarize.no_config_no_token":
            "Diarization: neither a local config nor a Hugging Face token was found.\n"
            "  Provide offline model files (pyannote-diar/config.yaml) or set HF_TOKEN\n"
            "  with the 'Read access to public gated repos' permission.",
        "diarize.online_ok": "  Pre-flight: using the online HF repo, token present.",
        "diarize.config_unreadable": "Diarization: cannot read the config {path}: {error}",
        "diarize.missing_files":
            "Diarization: the config references local files that do not exist:\n{files}\n"
            "  Check the paths in {path}",
        "diarize.relative_path_warning":
            "  WARNING: '{key}' ({value}) exists relative to the config but pyannote resolves it\n"
            "  against the working directory: run from that folder or use an absolute path.",
        "diarize.preflight_ok":
            "  Diarization pre-flight OK: local config and models are in place ({path}).",
        "diarize.config_fallback":
            "  (local config not found: {path} --> using the HF repo {fallback})",
        "diarize.token_required":
            "--diarize needs a Hugging Face token (or a local config.yaml via --diar-model).\n"
            "  - Pass --hf-token TOKEN or set HUGGINGFACE_TOKEN.\n"
            "  - The token needs the 'Read access to public gated repos' permission.\n"
            "  - Accept the terms on huggingface.co for these models:\n"
            "      pyannote/speaker-diarization-3.1, pyannote/segmentation-3.0,\n"
            "      pyannote/wespeaker-voxceleb-resnet34-LM",
        "diarize.loading": "Loading the pyannote diarization pipeline (CPU) from: {model}",
        "diarize.not_initialised":
            "Diarization was not initialised: invalid token, or the model terms were not accepted.",
        "diarize.running": "Diarizing (this can take a few minutes)...",
        "diarize.result": "   turns detected: {turns} | speakers: {speakers}",
        "diarize.no_turns":
            "  WARNING: diarization produced no turns or no segments: writing plain text instead.",

        # --- library --------------------------------------------------------
        "library.created": "Library entry created: {path}",
        "library.not_found": "No library entry matches '{query}'.",
        "library.ambiguous": "'{query}' matches several entries: {matches}",
        "library.empty": "The library is empty ({path}).",
        "library.removed": "Removed: {path}",
        "library.no_match": "No entry matches '{query}'.",
        "library.header_id": "ID",
        "library.header_date": "DATE",
        "library.header_duration": "LENGTH",
        "library.header_words": "WORDS",
        "library.header_title": "TITLE",
        "library.corrupt_metadata": "  WARNING: unreadable metadata, entry skipped: {path}",

        # --- keyword sets ---------------------------------------------------
        "vocab.none":
            "No keyword set is available.\n"
            "  Create one with: audio-transcriber vocab new my-terms\n"
            "  They live in {path}",
        "vocab.created": "Keyword set created: {path}",
        "vocab.header_name": "NAME",
        "vocab.header_source": "SOURCE",
        "vocab.header_language": "LANG",
        "vocab.header_terms": "TERMS",
        "vocab.header_title": "TITLE",
        "vocab.prompt_too_long":
            "  WARNING: the vocabulary is {chars} characters, over the {limit} that Whisper\n"
            "  reliably takes: the end will be ignored. Use fewer, more specific terms.",
        "vocab.unknown": "Unknown keyword set '{name}'.",
        "vocab.show_stats": "{source}  {language}  {terms} terms  {chars} characters",

        # --- web interface ----------------------------------------------------
        "web.starting": "Web interface: http://{host}:{port}  (Ctrl-C to stop)",
        "web.exposed":
            "  WARNING: bound to a public address and there is no authentication.\n"
            "  Anyone who can reach this port can read and delete your recordings.",
        "web.missing":
            "The web interface needs FastAPI and Uvicorn.\n"
            "  pip install \"audio-transcriber-ov[web]\"",
        "web.job_queued": "queued",
        "web.job_running": "running",
        "web.job_done": "done",
        "web.job_failed": "failed",

        # --- desktop interface ------------------------------------------------
        "gui.missing":
            "The desktop interface needs Qt (PySide6).\n"
            "  pip install \"audio-transcriber-ov[gui]\"",
        "gui.broken":
            "PySide6 is installed but cannot be loaded: {error}\n"
            "  A DLL or shared-library failure here almost always means two Qt\n"
            "  installations in one environment - conda's Qt found on PATH before the\n"
            "  one pip bundles - or, on a headless machine, missing system libraries.\n"
            "  See docs/gui.md. The web interface needs none of this: try 'web'.",
        "gui.app_name": "Audio Transcriber",
        "gui.window_title": "audio-transcriber {version}",
        "gui.ready": "Library: {path}",
        "gui.tab_transcribe": "Transcribe",
        "gui.tab_library": "Library",
        "gui.tab_system": "This machine",
        "gui.tab_transcript": "Transcript",
        "gui.tab_notes": "Notes",
        "gui.tab_details": "Details",

        "gui.group_sources": "Recordings to transcribe",
        "gui.group_record": "Record a meeting",
        "gui.add_files": "Add files...",
        "gui.remove_files": "Remove",
        "gui.clear_files": "Clear",
        "gui.choose_files": "Choose audio or video files",
        "gui.drop_hint": "Drop audio or video files here.",
        "gui.filter_media": "Audio and video",
        "gui.filter_any": "Every file",
        "gui.filter_text": "Text file",

        "gui.group_options": "Options",
        "gui.label_model": "Model",
        "gui.label_language": "Spoken language",
        "gui.label_backend": "Engine",
        "gui.label_speakers": "Speakers",
        "gui.model_auto": "auto ({model} on this machine)",
        "gui.language_auto": "detect it",
        "gui.backend_auto": "auto",
        "gui.diarize": "Who said what",
        "gui.diarize_unavailable":
            "Not available on this machine: {detail}\n"
            "See the 'This machine' tab.",
        "gui.speakers_unknown": "unknown",

        "gui.group_vocabulary": "Keyword sets",
        "gui.vocab_hint": "Tick the sets whose terms turn up in these recordings.",
        "gui.vocab_label": "{title}  [{name}]  {terms} terms",
        "gui.vocab_custom": "Your own terms, kept on this machine only:",
        "gui.vocab_custom_hint":
            "One term per line, or separated by commas: the names, products and acronyms "
            "Whisper keeps getting wrong.",
        "gui.vocab_chars": "prompt: {chars} characters (Whisper reliably takes about {limit})",
        "gui.vocab_too_long": "The terms typed here are limited to {limit} characters.",

        "gui.start": "Transcribe",
        "gui.open_entry": "Open in the library",
        "gui.forget_job": "Remove from the list",
        "gui.col_title": "Title",
        "gui.col_status": "Status",
        "gui.col_progress": "Progress",
        "gui.col_model": "Model",
        "gui.col_duration": "Length",
        "gui.col_words": "Words",
        "gui.col_date": "Date",
        "gui.col_notes": "Notes",
        "gui.notes_yes": "yes",
        "gui.status_queued": "queued",
        "gui.status_running": "running",
        "gui.status_done": "done",
        "gui.status_failed": "failed",
        "gui.queue_empty": "Nothing in the queue.",
        "gui.queue_busy":
            "{running} running, {waiting} waiting: one at a time, because two "
            "transcriptions at once finish no sooner.",
        "gui.queue_idle": "Finished: {done} transcribed, {failed} failed.",
        "gui.queued": "Queued: {count}.",
        "gui.nothing_to_do": "Add a file, or record one, first.",
        "gui.job_finished": "Filed in the library: {entry}",

        "gui.rec_host_api": "Audio system",
        "gui.rec_host_api_tip":
            "How Windows is asked for the sound: WASAPI is the native path and the only "
            "one that can record what the speakers are playing. MME and DirectSound are "
            "older wrappers over the same devices, kept for drivers that need them.",
        "gui.rec_host_api_summary": "{count} sources, {loopbacks} of them loopback",
        "gui.rec_source": "Source",
        "gui.rec_reload_tip":
            "Look for devices again. PortAudio reads them once, when it starts, so a\n"
            "microphone connected after this window did needs asking.",
        "gui.rec_source_tip": "The device to record from, among those this audio system offers.",
        "gui.rec_loopback_label": "[loopback] {name}",
        "gui.rec_mix": "Together with",
        "gui.rec_mix_tip":
            "Record a second source into the same file. A microphone plus the loopback "
            "of the speakers are the two halves of a call: your voice and everyone "
            "else's. The two sound cards keep their own time, so the first source sets "
            "the pace and the second is held alongside it.",
        "gui.rec_basic":
            "This engine records from a microphone only. Choosing the audio system, and "
            "recording what the speakers play, need: pip install \"audio-transcriber-ov[record]\"",
        "gui.rec_device": "Microphone",
        "gui.rec_device_tip": "Where the recording comes from; the list follows what the system offers.",
        "gui.rec_start": "Record",
        "gui.rec_stop": "Stop",
        "gui.rec_pause": "Pause",
        "gui.rec_resume": "Resume",
        "gui.rec_queued": "Recording queued for transcription.",
        "gui.rec_empty": "Nothing was recorded: the microphone produced no sound.",
        "gui.rec_failed": "Recording failed.",
        "gui.rec_no_device": "No microphone found. Connect one — the menu notices by itself.",
        "gui.rec_no_multimedia":
            "Recording needs QtMultimedia: pip install PySide6-Addons (or the full PySide6).",
        "gui.recording_title": "Recording {when}",

        "gui.search_hint": "Search the transcripts and the notes",
        "gui.reload": "Reload",
        "gui.library_count": "{count} recordings.",
        "gui.library_matches": "{count} recordings contain '{query}'.",
        "gui.no_transcript": "This entry holds no transcript.",
        "gui.play": "Play",
        "gui.pause": "Pause",
        "gui.player_no_audio": "This entry does not hold its recording: there is nothing to play.",
        "gui.player_no_multimedia":
            "Playback needs QtMultimedia: pip install PySide6-Addons (or the full PySide6).",
        "gui.detail_created": "Recorded",
        "gui.detail_duration": "Length",
        "gui.detail_size": "Recording",
        "gui.detail_model": "Model",
        "gui.detail_language": "Language",
        "gui.detail_elapsed": "Transcribed in",
        "gui.detail_speakers": "Speakers",
        "gui.detail_detected": "detected",
        "gui.detail_vocabulary": "Keyword sets",
        "gui.detail_folder": "Folder",
        "gui.notes_hint": "Yours to write; saved as notes.md inside the entry.",
        "gui.notes_save": "Save the notes",
        "gui.notes_saved": "Notes saved.",
        "gui.notes_too_long": "Notes are limited to {limit} characters.",
        "gui.notes_unsaved_title": "Unsaved notes",
        "gui.notes_unsaved": "The notes on '{title}' have not been saved.",
        "gui.rename": "Rename",
        "gui.rename_title": "Rename",
        "gui.rename_prompt": "New title:",
        "gui.export": "Export the transcript",
        "gui.exported": "Transcript written to {path}",
        "gui.open_folder": "Open the folder",
        "gui.delete": "Delete",
        "gui.delete_title": "Delete this recording",
        "gui.delete_confirm":
            "Delete '{title}' with its transcript, its notes and its recording?\n\n{path}",
        "gui.deleted": "Deleted: {title}",

        "gui.group_hardware": "What this machine can do",
        "gui.group_paths": "Directories in use",
        "gui.row_machine": "Hardware",
        "gui.row_backend": "Engine 'auto' picks",
        "gui.row_model": "Model 'auto' picks",
        "gui.row_diarization": "Who said what",
        "gui.diar_ready": "available ({detail})",
        "gui.diar_missing": "not installed: pip install \"audio-transcriber-ov[diarize]\"",
        "gui.diar_unconfigured":
            "installed, but no model: set HUGGINGFACE_TOKEN, or put a local config at {detail}",
        "gui.path_missing": "not created yet",
        "gui.path_configured": "from config.toml",
        "gui.open_config": "Open config.toml",
        "gui.open_library": "Open the library folder",

        "gui.quit_title": "Quit",
        "gui.quit_pending":
            "{count} transcriptions are still running or waiting, and closing the window "
            "abandons them. Quit anyway?",

        # --- CLI ------------------------------------------------------------
        "cli.description":
            "Audio and video to text (Whisper on an Intel iGPU via OpenVINO, or on the "
            "CPU via faster-whisper), with optional speaker diarization.",
        "cli.done": "\nOK: transcript -> {path}",
        "cli.summary":
            "   words: {words} | backend: {backend} | device: {device} | language: {language}",
        "cli.summary_diarized": " | diarization: ON",
        "cli.file_not_found": "File not found: {path}",
        "cli.input_required": "an audio or video file is required",
        "cli.elapsed": "   elapsed: {elapsed} ({speed})",
        "cli.speed_realtime": "{factor:.1f}x realtime",
        "cli.speed_unknown": "speed unknown",
        "cli.config_loaded": "  (defaults loaded from {path})",
        "cli.config_invalid": "Invalid configuration file {path}: {error}",
        "cli.paths_header": "Directories used by audio-transcriber:",
        "cli.paths_missing": "(not created yet)",
        "cli.paths_configured": "(from config.toml)",
        "cli.unknown_language": "Unknown interface language '{lang}'; using {fallback}.",
    },
    "it": {
        # --- audio decoding -------------------------------------------------
        "audio.no_bundled_ffmpeg":
            "  ATTENZIONE: 'imageio-ffmpeg' non e' installato: uso il ffmpeg di sistema.\n"
            "  Se vedi errori di DLL (libintl/fontconfig) esegui: pip install imageio-ffmpeg",
        "audio.ffmpeg_not_found": "ffmpeg non trovato. Esegui: pip install imageio-ffmpeg",
        "audio.decode_failed": "Errore ffmpeg nel decodificare l'audio:\n{details}",

        # --- hardware -------------------------------------------------------
        "hardware.summary":
            "CPU: {cores} core | RAM libera: {ram} | OpenVINO: {openvino} | CUDA: {cuda}",
        "hardware.unknown": "n/d",
        "hardware.not_installed": "non installato",
        "hardware.yes": "si",
        "hardware.no": "no",
        "hardware.auto_backend": "backend che '--backend auto' userebbe: {backend}",
        "hardware.auto_model": "modello che '--model auto' userebbe: {model}",
        "hardware.diarize_ready": "diarizzazione ('chi dice cosa'): disponibile ({detail})",
        "hardware.diarize_missing":
            "diarizzazione ('chi dice cosa'): non installata\n"
            "  pip install \"audio-transcriber-ov[diarize]\"  (si porta dietro PyTorch, circa 2 GB)",
        "hardware.diarize_unconfigured":
            "diarizzazione ('chi dice cosa'): installata, ma senza modello\n"
            "  imposta HUGGINGFACE_TOKEN, oppure metti un config locale in {detail}",

        # --- backend selection ----------------------------------------------
        "backend.unknown": "Backend sconosciuto: {name}. Valori validi: {valid}",
        "backend.none_installed":
            "Nessun backend di trascrizione installato.\n"
            "  Server o macchina senza GPU:  pip install \"audio-transcriber-ov[cpu]\"\n"
            "  PC con iGPU/NPU Intel:        pip install \"audio-transcriber-ov[openvino]\"",
        "backend.low_ram":
            "  ATTENZIONE: '{model}' richiede circa {needed:.1f} GiB ma ne risultano liberi {free:.1f}.\n"
            "  Rischi swap o OOM: valuta --model medium/small{hint}.",
        "backend.low_ram_hint": " oppure --backend faster-whisper (int8, meta' memoria)",
        "backend.few_cores":
            "  ATTENZIONE: solo {cores} core disponibili: '{model}' su CPU puo' richiedere\n"
            "  molto piu' tempo della durata dell'audio. Su una macchina cosi' '--model small'\n"
            "  e' molto piu' pratico (circa 0.6x realtime).",

        # --- OpenVINO backend -----------------------------------------------
        "openvino.missing":
            "Backend 'openvino': manca optimum-intel.\n"
            "  pip install \"audio-transcriber-ov[openvino]\"\n"
            "  (oppure: pip install \"optimum-intel[openvino]\" transformers)",
        "openvino.device_unavailable":
            "  ATTENZIONE: device '{requested}' non disponibile (visti: {found}); uso {fallback}.",
        "openvino.reusing_model": "Uso il modello OpenVINO gia' convertito: {path}",
        "openvino.converting": "Scarico e converto '{model}' in OpenVINO (solo la prima volta)...",
        "openvino.model_saved": "Modello salvato in: {path}",
        "openvino.compiling": "Compilazione per il device '{device}'...",
        "openvino.compile_warning": "  (compile: {error})",
        "openvino.prompt_failed":
            "  (prompt iniziale non applicato: {error}\n   riprovo senza)",

        # --- faster-whisper backend -----------------------------------------
        "faster_whisper.missing":
            "Backend 'faster-whisper': manca il pacchetto.\n"
            "  pip install \"audio-transcriber-ov[cpu]\"\n"
            "  (oppure: pip install faster-whisper)",
        "faster_whisper.no_cuda":
            "  ATTENZIONE: nessuna GPU CUDA disponibile per faster-whisper; uso la CPU.",
        "faster_whisper.unknown_size":
            "  ATTENZIONE: '{model}' non e' una taglia nota a faster-whisper; provo comunque a caricarlo.",
        "faster_whisper.loading":
            "Carico Whisper '{model}' con faster-whisper "
            "(device: {device}, precisione: {compute_type}, thread: {threads})...",
        "faster_whisper.cache": "  (cache dei modelli: {path} — il download avviene solo la prima volta)",
        "faster_whisper.compute_type_unsupported":
            "  (precisione '{compute_type}' non supportata: {error}\n"
            "   ripiego su '{fallback}')",
        "faster_whisper.load_failed": "faster-whisper: impossibile caricare il modello: {error}",
        "faster_whisper.detected_language":
            "  lingua rilevata: {language} (confidenza {probability:.2f})",

        # --- transcription --------------------------------------------------
        "model.auto": "Modello 'auto': uso '{model}' ({cores} core, {ram} GiB liberi).",
        "transcribe.running": "Trascrizione in corso...",
        "transcribe.progress": "  avanzamento: {percent:3d}%",
        "transcribe.empty": "Nessun testo trascritto (audio vuoto o silenzioso?).",

        # --- diarization ----------------------------------------------------
        "diarize.missing": "Diarizzazione: manca pyannote. Esegui: pip install pyannote.audio",
        "diarize.local_config_missing":
            "  Pre-flight: config locale non trovato ({path}); userei il repo HF.",
        "diarize.no_config_no_token":
            "Diarizzazione: manca sia un config locale sia un token Hugging Face.\n"
            "  Metti i file offline (pyannote-diar/config.yaml) oppure imposta HF_TOKEN\n"
            "  con il permesso 'Read access to public gated repos'.",
        "diarize.online_ok": "  Pre-flight: uso online (repo HF) con token presente.",
        "diarize.config_unreadable": "Diarizzazione: impossibile leggere il config {path}: {error}",
        "diarize.missing_files":
            "Diarizzazione: nel config mancano file locali (non trovati):\n{files}\n"
            "  Controlla i percorsi in {path}",
        "diarize.relative_path_warning":
            "  ATTENZIONE: '{key}' ({value}) esiste relativo al config ma pyannote lo risolve\n"
            "  rispetto alla cartella di lancio: lancia dallo stesso folder o usa un percorso assoluto.",
        "diarize.preflight_ok":
            "  Pre-flight diarizzazione OK: config e modelli locali presenti ({path}).",
        "diarize.config_fallback":
            "  (config locale non trovato: {path} --> uso il repo HF {fallback})",
        "diarize.token_required":
            "Per --diarize serve un token Hugging Face (o un config.yaml locale via --diar-model).\n"
            "  - Passa --hf-token TOKEN oppure imposta HUGGINGFACE_TOKEN.\n"
            "  - Il token deve avere il permesso 'Read access to public gated repos'.\n"
            "  - Accetta le condizioni su huggingface.co dei modelli:\n"
            "      pyannote/speaker-diarization-3.1, pyannote/segmentation-3.0,\n"
            "      pyannote/wespeaker-voxceleb-resnet34-LM",
        "diarize.loading": "Carico la pipeline di diarizzazione pyannote (CPU) da: {model}",
        "diarize.not_initialised":
            "Diarizzazione non inizializzata: token non valido o condizioni dei modelli non accettate.",
        "diarize.running": "Diarizzazione in corso (puo' richiedere qualche minuto)...",
        "diarize.result": "   turni rilevati: {turns} | speaker: {speakers}",
        "diarize.no_turns":
            "  ATTENZIONE: diarizzazione senza turni o senza segmenti: scrivo il testo semplice.",

        # --- library --------------------------------------------------------
        "library.created": "Voce di libreria creata: {path}",
        "library.not_found": "Nessuna voce di libreria corrisponde a '{query}'.",
        "library.ambiguous": "'{query}' corrisponde a piu' voci: {matches}",
        "library.empty": "La libreria e' vuota ({path}).",
        "library.removed": "Rimossa: {path}",
        "library.no_match": "Nessuna voce corrisponde a '{query}'.",
        "library.header_id": "ID",
        "library.header_date": "DATA",
        "library.header_duration": "DURATA",
        "library.header_words": "PAROLE",
        "library.header_title": "TITOLO",
        "library.corrupt_metadata": "  ATTENZIONE: metadati illeggibili, voce ignorata: {path}",

        # --- keyword sets ---------------------------------------------------
        "vocab.none":
            "Nessun set di parole chiave disponibile.\n"
            "  Creane uno con: audio-transcriber vocab new mie-parole\n"
            "  Stanno in {path}",
        "vocab.created": "Set di parole chiave creato: {path}",
        "vocab.header_name": "NOME",
        "vocab.header_source": "ORIGINE",
        "vocab.header_language": "LINGUA",
        "vocab.header_terms": "TERMINI",
        "vocab.header_title": "TITOLO",
        "vocab.prompt_too_long":
            "  ATTENZIONE: il vocabolario e' di {chars} caratteri, oltre i {limit} che Whisper\n"
            "  considera davvero: la parte finale viene ignorata. Usa meno termini, piu' mirati.",
        "vocab.unknown": "Set di parole chiave '{name}' sconosciuto.",
        "vocab.show_stats": "{source}  {language}  {terms} termini  {chars} caratteri",

        # --- web interface ----------------------------------------------------
        "web.starting": "Interfaccia web: http://{host}:{port}  (Ctrl-C per fermarla)",
        "web.exposed":
            "  ATTENZIONE: in ascolto su un indirizzo pubblico e senza autenticazione.\n"
            "  Chi raggiunge questa porta puo' leggere e cancellare le tue registrazioni.",
        "web.missing":
            "L'interfaccia web richiede FastAPI e Uvicorn.\n"
            "  pip install \"audio-transcriber-ov[web]\"",
        "web.job_queued": "in coda",
        "web.job_running": "in corso",
        "web.job_done": "completato",
        "web.job_failed": "fallito",

        # --- desktop interface ------------------------------------------------
        "gui.missing":
            "L'interfaccia desktop richiede Qt (PySide6).\n"
            "  pip install \"audio-transcriber-ov[gui]\"",
        "gui.broken":
            "PySide6 e' installato ma non si carica: {error}\n"
            "  Un errore di DLL o di libreria condivisa qui vuol dire quasi sempre due Qt\n"
            "  nello stesso ambiente - quello di conda trovato nel PATH prima di quello\n"
            "  che pip si porta dietro - oppure, su una macchina senza ambiente grafico,\n"
            "  librerie di sistema mancanti. Vedi docs/gui.md. L'interfaccia web non ha\n"
            "  bisogno di niente di tutto questo: prova 'web'.",
        "gui.app_name": "Audio Transcriber",
        "gui.window_title": "audio-transcriber {version}",
        "gui.ready": "Libreria: {path}",
        "gui.tab_transcribe": "Trascrivi",
        "gui.tab_library": "Libreria",
        "gui.tab_system": "Questa macchina",
        "gui.tab_transcript": "Trascrizione",
        "gui.tab_notes": "Note",
        "gui.tab_details": "Dettagli",

        "gui.group_sources": "Registrazioni da trascrivere",
        "gui.group_record": "Registra una riunione",
        "gui.add_files": "Aggiungi file...",
        "gui.remove_files": "Togli",
        "gui.clear_files": "Svuota",
        "gui.choose_files": "Scegli i file audio o video",
        "gui.drop_hint": "Trascina qui i file audio o video.",
        "gui.filter_media": "Audio e video",
        "gui.filter_any": "Tutti i file",
        "gui.filter_text": "File di testo",

        "gui.group_options": "Opzioni",
        "gui.label_model": "Modello",
        "gui.label_language": "Lingua parlata",
        "gui.label_backend": "Motore",
        "gui.label_speakers": "Interlocutori",
        "gui.model_auto": "auto ({model} su questa macchina)",
        "gui.language_auto": "riconoscila",
        "gui.backend_auto": "auto",
        "gui.diarize": "Chi ha detto cosa",
        "gui.diarize_unavailable":
            "Non disponibile su questa macchina: {detail}\n"
            "Vedi la scheda 'Questa macchina'.",
        "gui.speakers_unknown": "non so",

        "gui.group_vocabulary": "Set di parole chiave",
        "gui.vocab_hint": "Spunta i set con i termini che compaiono in queste registrazioni.",
        "gui.vocab_label": "{title}  [{name}]  {terms} termini",
        "gui.vocab_custom": "I tuoi termini, solo su questa macchina:",
        "gui.vocab_custom_hint":
            "Un termine per riga, o separati da virgole: i nomi, i prodotti e le sigle "
            "che Whisper continua a storpiare.",
        "gui.vocab_chars": "prompt: {chars} caratteri (Whisper ne considera davvero circa {limit})",
        "gui.vocab_too_long": "I termini scritti qui sono limitati a {limit} caratteri.",

        "gui.start": "Trascrivi",
        "gui.open_entry": "Apri nella libreria",
        "gui.forget_job": "Togli dall'elenco",
        "gui.col_title": "Titolo",
        "gui.col_status": "Stato",
        "gui.col_progress": "Avanzamento",
        "gui.col_model": "Modello",
        "gui.col_duration": "Durata",
        "gui.col_words": "Parole",
        "gui.col_date": "Data",
        "gui.col_notes": "Note",
        "gui.notes_yes": "si'",
        "gui.status_queued": "in coda",
        "gui.status_running": "in corso",
        "gui.status_done": "completata",
        "gui.status_failed": "fallita",
        "gui.queue_empty": "Nessun lavoro in coda.",
        "gui.queue_busy":
            "{running} in corso, {waiting} in attesa: una alla volta, perche' due "
            "trascrizioni insieme non finiscono prima.",
        "gui.queue_idle": "Finito: {done} trascritte, {failed} fallite.",
        "gui.queued": "In coda: {count}.",
        "gui.nothing_to_do": "Prima aggiungi un file, o registrane uno.",
        "gui.job_finished": "Archiviata in libreria: {entry}",

        "gui.rec_host_api": "Sistema audio",
        "gui.rec_host_api_tip":
            "Come si chiede il suono a Windows: WASAPI e' la via nativa ed e' la sola che "
            "puo' registrare quello che gli altoparlanti stanno riproducendo. MME e "
            "DirectSound sono involucri piu' vecchi sugli stessi dispositivi, utili per i "
            "driver che li richiedono.",
        "gui.rec_host_api_summary": "{count} sorgenti, di cui {loopbacks} in loopback",
        "gui.rec_source": "Sorgente",
        "gui.rec_reload_tip":
            "Cerca di nuovo i dispositivi. PortAudio li legge una volta sola, all'avvio,\n"
            "percio' un microfono collegato dopo questa finestra va chiesto.",
        "gui.rec_source_tip": "Il dispositivo da cui registrare, fra quelli che offre questo sistema audio.",
        "gui.rec_loopback_label": "[loopback] {name}",
        "gui.rec_mix": "Insieme a",
        "gui.rec_mix_tip":
            "Registra una seconda sorgente nello stesso file. Un microfono piu' il loopback "
            "degli altoparlanti sono le due meta' di una call: la tua voce e quella degli "
            "altri. Le due schede audio hanno ciascuna il proprio tempo, percio' la prima "
            "sorgente da' il ritmo e la seconda le viene tenuta accanto.",
        "gui.rec_basic":
            "Questo motore registra solo da microfono. Per scegliere il sistema audio, e per "
            "registrare quello che riproducono gli altoparlanti: pip install \"audio-transcriber-ov[record]\"",
        "gui.rec_device": "Microfono",
        "gui.rec_device_tip": "Da dove arriva la registrazione; l'elenco segue quello che offre il sistema.",
        "gui.rec_start": "Registra",
        "gui.rec_stop": "Ferma",
        "gui.rec_pause": "Pausa",
        "gui.rec_resume": "Riprendi",
        "gui.rec_queued": "Registrazione messa in coda per la trascrizione.",
        "gui.rec_empty": "Non e' stato registrato nulla: dal microfono non arrivava suono.",
        "gui.rec_failed": "Registrazione fallita.",
        "gui.rec_no_device": "Nessun microfono trovato. Collegane uno: l'elenco se ne accorge da solo.",
        "gui.rec_no_multimedia":
            "Per registrare serve QtMultimedia: pip install PySide6-Addons (o PySide6 completo).",
        "gui.recording_title": "Registrazione {when}",

        "gui.search_hint": "Cerca nelle trascrizioni e nelle note",
        "gui.reload": "Ricarica",
        "gui.library_count": "{count} registrazioni.",
        "gui.library_matches": "{count} registrazioni contengono '{query}'.",
        "gui.no_transcript": "Questa voce non contiene una trascrizione.",
        "gui.play": "Riproduci",
        "gui.pause": "Pausa",
        "gui.player_no_audio": "Questa voce non contiene la registrazione: non c'e' nulla da riprodurre.",
        "gui.player_no_multimedia":
            "Per riprodurre serve QtMultimedia: pip install PySide6-Addons (o PySide6 completo).",
        "gui.detail_created": "Registrata il",
        "gui.detail_duration": "Durata",
        "gui.detail_size": "Registrazione",
        "gui.detail_model": "Modello",
        "gui.detail_language": "Lingua",
        "gui.detail_elapsed": "Trascritta in",
        "gui.detail_speakers": "Interlocutori",
        "gui.detail_detected": "riconosciuti",
        "gui.detail_vocabulary": "Set di parole chiave",
        "gui.detail_folder": "Cartella",
        "gui.notes_hint": "Queste le scrivi tu; finiscono in notes.md dentro la voce.",
        "gui.notes_save": "Salva le note",
        "gui.notes_saved": "Note salvate.",
        "gui.notes_too_long": "Le note sono limitate a {limit} caratteri.",
        "gui.notes_unsaved_title": "Note non salvate",
        "gui.notes_unsaved": "Le note di '{title}' non sono state salvate.",
        "gui.rename": "Rinomina",
        "gui.rename_title": "Rinomina",
        "gui.rename_prompt": "Nuovo titolo:",
        "gui.export": "Esporta la trascrizione",
        "gui.exported": "Trascrizione scritta in {path}",
        "gui.open_folder": "Apri la cartella",
        "gui.delete": "Elimina",
        "gui.delete_title": "Elimina questa registrazione",
        "gui.delete_confirm":
            "Elimino '{title}' con la sua trascrizione, le note e la registrazione?\n\n{path}",
        "gui.deleted": "Eliminata: {title}",

        "gui.group_hardware": "Cosa puo' fare questa macchina",
        "gui.group_paths": "Cartelle in uso",
        "gui.row_machine": "Hardware",
        "gui.row_backend": "Il motore che 'auto' sceglie",
        "gui.row_model": "Il modello che 'auto' sceglie",
        "gui.row_diarization": "Chi ha detto cosa",
        "gui.diar_ready": "disponibile ({detail})",
        "gui.diar_missing": "non installata: pip install \"audio-transcriber-ov[diarize]\"",
        "gui.diar_unconfigured":
            "installata, ma senza modello: imposta HUGGINGFACE_TOKEN, oppure metti un config locale in {detail}",
        "gui.path_missing": "non creata ancora",
        "gui.path_configured": "da config.toml",
        "gui.open_config": "Apri config.toml",
        "gui.open_library": "Apri la cartella della libreria",

        "gui.quit_title": "Esci",
        "gui.quit_pending":
            "{count} trascrizioni sono ancora in corso o in attesa, e chiudere la finestra "
            "le abbandona. Esco comunque?",

        # --- CLI ------------------------------------------------------------
        "cli.description":
            "Da audio/video a testo (Whisper su iGPU Intel via OpenVINO o su CPU via "
            "faster-whisper) con diarizzazione opzionale.",
        "cli.done": "\nOK: trascrizione -> {path}",
        "cli.summary":
            "   parole: {words} | backend: {backend} | device: {device} | lingua: {language}",
        "cli.summary_diarized": " | diarizzazione: ON",
        "cli.file_not_found": "File non trovato: {path}",
        "cli.input_required": "serve un file audio o video",
        "cli.elapsed": "   tempo impiegato: {elapsed} ({speed})",
        "cli.speed_realtime": "{factor:.1f}x realtime",
        "cli.speed_unknown": "velocita' non nota",
        "cli.config_loaded": "  (default letti da {path})",
        "cli.config_invalid": "File di configurazione non valido {path}: {error}",
        "cli.paths_header": "Cartelle usate da audio-transcriber:",
        "cli.paths_missing": "(non ancora creata)",
        "cli.paths_configured": "(da config.toml)",
        "cli.unknown_language": "Lingua dell'interfaccia '{lang}' sconosciuta; uso {fallback}.",
    },
}

# Command-line help. Kept apart from the runtime messages because it is read
# once, when learning the tool, rather than during a run.
HELP = {
    "en": {
        "help.epilog": """Examples:
  # plain transcription, backend and device picked automatically
  audio-transcriber meeting.wav

  # "who said what" with 3 known speakers
  audio-transcriber meeting.wav --diarize --speakers 3

  # GPU-less server: CPU engine and a lighter model
  audio-transcriber meeting.wav --backend faster-whisper --model small

  # force the Intel iGPU
  audio-transcriber meeting.wav --backend openvino --device GPU

  # file it in the library instead of writing a .txt next to the input
  audio-transcriber meeting.mp4 --library --title "Weekly sync"

  # use a named keyword set so technical terms survive
  audio-transcriber meeting.wav --vocab iso27001-it
  audio-transcriber vocab list

  # browse what has been transcribed so far
  audio-transcriber library list
  audio-transcriber library search "risk assessment"

  # the same thing from a browser, on this machine only
  audio-transcriber web

  # what can this machine do, and where do files go?
  audio-transcriber hardware
  audio-transcriber paths""",
        "help.lang": "interface language ({choices}); default: $AUDIO_TRANSCRIBER_LANG or the system locale",
        "help.version": "print the version and exit",
        "help.command": "command to run (default: transcribe)",
        "help.cmd_transcribe": "turn an audio or video file into text",
        "help.cmd_library": "browse the library of transcribed recordings",
        "help.cmd_hardware": "show the detected hardware and the backend that would be used",
        "help.cmd_paths": "show where configuration, models and the library live",
        "help.cmd_config": "inspect or create the configuration file",
        "help.input": "audio or video file",
        "help.out": "output .txt file (default: alongside the input)",
        "help.model": "auto|tiny|base|small|medium|large-v3-turbo|large-v3; 'auto' fits the model to this machine (default: {default})",
        "help.language": "spoken language, e.g. it, en (default: {default}; '' to auto-detect)",
        "help.backend": "transcription engine (default: auto - faster-whisper on CPU, openvino with an Intel iGPU/NPU)",
        "help.device": "auto (default) | CPU | GPU (Intel iGPU) | NPU | CUDA",
        "help.compute_type": "faster-whisper only: int8 (CPU default), int8_float16, float16 (CUDA default), float32",
        "help.threads": "faster-whisper only: CPU threads (default: every available core)",
        "help.no_vad": "faster-whisper only: do NOT filter silence with the VAD (the filter cuts hallucinations a lot)",
        "help.model_dir": "model directory (default: the managed one, see 'audio-transcriber paths')",
        "help.prompt": "domain vocabulary that keeps technical terms from being mangled",
        "help.prompt_file": "read the domain vocabulary from a text file",
        "help.para_gap": "pause in seconds that starts a new paragraph (without --diarize)",
        "help.para_max_chars": "maximum paragraph length (without --diarize)",
        "help.keep_fillers": "do NOT drop the phrases Whisper hallucinates over silence",
        "help.diarize": "work out who said what (pyannote, on CPU)",
        "help.speakers": "number of speakers, if known (improves the result a lot)",
        "help.hf_token": "Hugging Face token for pyannote (or the HUGGINGFACE_TOKEN variable)",
        "help.diar_model": "HF id (online, needs a token) or path to a local config.yaml (offline)",
        "help.library": "file the result in the library instead of writing a .txt next to the input",
        "help.library_store": "how the library keeps the original: copy (default), move, or reference it in place",
        "help.title": "title for the library entry (default: the input file name)",
        "help.json": "also write the segments, with timestamps, as JSON",
        "help.lib_list": "list the entries, newest first",
        "help.lib_show": "show one entry and its transcript",
        "help.lib_search": "find entries whose transcript or notes contain some text",
        "help.lib_remove": "delete an entry and everything in it",
        "help.lib_path": "print the path of an entry, or of the library itself",
        "help.lib_query": "entry id (a prefix is enough) or part of its title",
        "help.lib_text": "text to look for",
        "help.lib_yes": "do not ask for confirmation",
        "help.lib_root": "use this library directory instead of the configured one",
        "help.cmd_vocab": "list, inspect and create the named keyword sets",
        "help.cmd_web": "serve the local web interface",
        "help.cmd_gui": "open the desktop window",
        "help.vocab": "keyword set to use, by name (repeatable, or comma-separated); see 'vocab list'",
        "help.vocab_dir": "look for keyword sets in this directory as well, first",
        "help.vocab_list": "list the keyword sets that can be selected",
        "help.vocab_show": "show one set and the prompt it produces",
        "help.vocab_path": "print the path of a set, or of the directory holding them",
        "help.vocab_new": "create a new set in the user directory",
        "help.vocab_name": "name of the keyword set",
        "help.vocab_title": "human-readable title, shown in the listings and in the web interface",
        "help.vocab_language": "language of the terms, e.g. it, en",
        "help.vocab_from": "start from an existing text file instead of an empty template",
        "help.vocab_force": "overwrite the set if it already exists",
        "help.web_host": "address to listen on (default: 127.0.0.1, this machine only)",
        "help.web_port": "port to listen on (default: 8765)",
        "help.web_root_path": "prefix a reverse proxy strips, e.g. /transcriber (only the API docs need it)",
        "help.cfg_show": "show the settings currently in effect",
        "help.cfg_path": "print the path of the configuration file",
        "help.cfg_init": "write a commented configuration file to fill in",
        "help.cfg_force": "overwrite the configuration file if it already exists",
    },
    "it": {
        "help.epilog": """Esempi:
  # trascrizione semplice, backend e device scelti automaticamente
  audio-transcriber riunione.wav

  # "chi dice cosa" con 3 speaker noti
  audio-transcriber riunione.wav --diarize --speakers 3

  # server senza GPU: motore CPU e modello piu' leggero
  audio-transcriber riunione.wav --backend faster-whisper --model small

  # forza la iGPU Intel
  audio-transcriber riunione.wav --backend openvino --device GPU

  # archivia in libreria invece di scrivere un .txt accanto al file
  audio-transcriber riunione.mp4 --library --title "Riunione settimanale"

  # usa un set di parole chiave perche' i termini tecnici sopravvivano
  audio-transcriber riunione.wav --vocab iso27001-it
  audio-transcriber vocab list

  # sfoglia quello che hai gia' trascritto
  audio-transcriber library list
  audio-transcriber library search "analisi dei rischi"

  # le stesse cose dal browser, solo su questa macchina
  audio-transcriber web

  # cosa sa fare questa macchina, e dove finiscono i file?
  audio-transcriber hardware
  audio-transcriber paths""",
        "help.lang": "lingua dell'interfaccia ({choices}); default: $AUDIO_TRANSCRIBER_LANG o il locale di sistema",
        "help.version": "stampa la versione ed esci",
        "help.command": "comando da eseguire (default: transcribe)",
        "help.cmd_transcribe": "trasforma un file audio o video in testo",
        "help.cmd_library": "sfoglia la libreria delle registrazioni trascritte",
        "help.cmd_hardware": "mostra l'hardware rilevato e il backend che verrebbe usato",
        "help.cmd_paths": "mostra dove stanno configurazione, modelli e libreria",
        "help.cmd_config": "ispeziona o crea il file di configurazione",
        "help.input": "file audio o video",
        "help.out": "file .txt di uscita (default: accanto al file di ingresso)",
        "help.model": "auto|tiny|base|small|medium|large-v3-turbo|large-v3; con 'auto' il modello si adatta a questa macchina (default: {default})",
        "help.language": "lingua parlata, es. it, en (default: {default}; '' per auto-rilevarla)",
        "help.backend": "motore di trascrizione (default: auto - faster-whisper su CPU, openvino con iGPU/NPU Intel)",
        "help.device": "auto (default) | CPU | GPU (iGPU Intel) | NPU | CUDA",
        "help.compute_type": "solo faster-whisper: int8 (default su CPU), int8_float16, float16 (default su CUDA), float32",
        "help.threads": "solo faster-whisper: thread CPU (default: tutti i core disponibili)",
        "help.no_vad": "solo faster-whisper: NON filtrare il silenzio col VAD (il filtro riduce molto le allucinazioni)",
        "help.model_dir": "cartella dei modelli (default: quella gestita, vedi 'audio-transcriber paths')",
        "help.prompt": "vocabolario di dominio che evita che i termini tecnici vengano storpiati",
        "help.prompt_file": "leggi il vocabolario di dominio da un file di testo",
        "help.para_gap": "pausa in secondi oltre la quale iniziare un nuovo paragrafo (senza --diarize)",
        "help.para_max_chars": "lunghezza massima di un paragrafo (senza --diarize)",
        "help.keep_fillers": "NON rimuovere le frasi che Whisper alluccina sul silenzio",
        "help.diarize": "ricostruisci chi dice cosa (pyannote, su CPU)",
        "help.speakers": "numero di speaker, se noto (migliora molto la resa)",
        "help.hf_token": "token Hugging Face per pyannote (o la variabile HUGGINGFACE_TOKEN)",
        "help.diar_model": "id HF (online, con token) o percorso a un config.yaml locale (offline)",
        "help.library": "archivia il risultato in libreria invece di scrivere un .txt accanto al file",
        "help.library_store": "come la libreria conserva l'originale: copy (default), move, oppure reference (lascialo dov'e')",
        "help.title": "titolo della voce di libreria (default: il nome del file)",
        "help.json": "scrivi anche i segmenti, con i timestamp, in formato JSON",
        "help.lib_list": "elenca le voci, dalla piu' recente",
        "help.lib_show": "mostra una voce e la sua trascrizione",
        "help.lib_search": "cerca le voci il cui testo o le cui note contengono qualcosa",
        "help.lib_remove": "elimina una voce e tutto il suo contenuto",
        "help.lib_path": "stampa il percorso di una voce, o della libreria stessa",
        "help.lib_query": "id della voce (basta un prefisso) o parte del titolo",
        "help.lib_text": "testo da cercare",
        "help.lib_yes": "non chiedere conferma",
        "help.lib_root": "usa questa cartella di libreria invece di quella configurata",
        "help.cmd_vocab": "elenca, ispeziona e crea i set di parole chiave",
        "help.cmd_web": "avvia l'interfaccia web locale",
        "help.cmd_gui": "apri la finestra desktop",
        "help.vocab": "set di parole chiave da usare, per nome (ripetibile, o separati da virgola); vedi 'vocab list'",
        "help.vocab_dir": "cerca i set anche in questa cartella, per prima",
        "help.vocab_list": "elenca i set di parole chiave selezionabili",
        "help.vocab_show": "mostra un set e il prompt che produce",
        "help.vocab_path": "stampa il percorso di un set, o della cartella che li contiene",
        "help.vocab_new": "crea un nuovo set nella cartella dell'utente",
        "help.vocab_name": "nome del set di parole chiave",
        "help.vocab_title": "titolo leggibile, mostrato negli elenchi e nell'interfaccia web",
        "help.vocab_language": "lingua dei termini, es. it, en",
        "help.vocab_from": "parti da un file di testo esistente invece che da un modello vuoto",
        "help.vocab_force": "sovrascrivi il set se esiste gia'",
        "help.web_host": "indirizzo su cui ascoltare (default: 127.0.0.1, solo questa macchina)",
        "help.web_port": "porta su cui ascoltare (default: 8765)",
        "help.web_root_path": "prefisso che un reverse proxy toglie, es. /transcriber (serve solo alla documentazione API)",
        "help.cfg_show": "mostra le impostazioni attualmente in vigore",
        "help.cfg_path": "stampa il percorso del file di configurazione",
        "help.cfg_init": "scrivi un file di configurazione commentato da completare",
        "help.cfg_force": "sovrascrivi il file di configurazione se esiste gia'",
    },
}

for _language, _entries in HELP.items():
    MESSAGES[_language].update(_entries)


AVAILABLE_LANGUAGES = tuple(sorted(MESSAGES))

_current = None


def _from_locale():
    """Best-effort language code from the system locale."""
    for getter in (lambda: os.environ.get("LC_ALL"),
                   lambda: os.environ.get("LC_MESSAGES"),
                   lambda: os.environ.get("LANG"),
                   lambda: (locale.getlocale()[0] or "")):
        try:
            value = getter() or ""
        except Exception:
            continue
        code = value.split(".")[0].split("_")[0].strip().lower()
        if code in MESSAGES:
            return code
    return None


def set_language(lang=None):
    """Set the interface language and return the code actually in use.

    An unknown code is not fatal: it warns and keeps the default, so a typo in
    ``--lang`` never stops a long transcription."""
    global _current
    if lang:
        code = str(lang).split(".")[0].split("_")[0].strip().lower()
        if code in MESSAGES:
            _current = code
            return _current
        _current = DEFAULT_LANGUAGE
        print(t("cli.unknown_language", lang=lang, fallback=DEFAULT_LANGUAGE))
        return _current
    _current = (os.environ.get(ENV_LANGUAGE) or "").strip().lower() or None
    if _current not in MESSAGES:
        _current = _from_locale() or DEFAULT_LANGUAGE
    return _current


def language():
    """Current language code, resolving it on first use."""
    return _current if _current in MESSAGES else set_language(None)


def t(key, **kwargs):
    """Translate ``key`` and interpolate ``kwargs``.

    Falls back to English, then to the key itself: a missing translation must
    never raise in the middle of a transcription."""
    catalogue = MESSAGES.get(language(), MESSAGES[DEFAULT_LANGUAGE])
    text = catalogue.get(key)
    if text is None:
        text = MESSAGES[DEFAULT_LANGUAGE].get(key, key)
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text
