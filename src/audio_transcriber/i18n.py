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
            "CPU: {cores} cores | RAM: {ram} free of {total} | OpenVINO: {openvino} | "
            "CUDA: {cuda}",
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
        "openvino.no_vad":
            "  NOTE: this backend has no voice-activity filter, so over a long silence\n"
            "  Whisper can invent a phrase ('Thanks for watching'). Obvious ones are\n"
            "  removed from the transcript afterwards. The faster-whisper backend cuts\n"
            "  the silences out before the model sees them: --backend faster-whisper.",
        "openvino.falling_back_to_long_form":
            "  (single-word timings were refused by this model: {error}\n"
            "   retrying for segment timings - subtitle cuts will be interpolated)",
        "openvino.falling_back_to_windowed":
            "  (this optimum-intel cannot run Whisper's own long-form loop: {error}\n"
            "   falling back to fixed 30 s windows. Where two windows overlap the words\n"
            "   can come out twice; the duplicates are cut from the transcript afterwards,\n"
            "   and the keyword prompt is dropped because it makes the overlap worse.)",
        "openvino.transcription_failed":
            "Backend 'openvino': the transcription did not run.\n  {error}",

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

        # --- stages of one run, shown while it is under way -----------------
        "stage.starting": "starting",
        "stage.decoded": "audio decoded",
        "stage.loading_model": "loading the model",
        "stage.converting_model": "converting the model",
        "stage.compiling_model": "compiling for the device",
        "stage.transcribing": "transcribing",
        "stage.diarizing": "working out who said what",
        "stage.laying_out": "laying out the text",
        "stage.summary_selecting": "choosing what matters",
        "stage.summary_reading": "reading the transcript",
        "stage.summary_writing": "writing the summary",

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
        # The same line the web page opens with: one promise, said once, in
        # both front ends.
        "gui.tagline": "Local transcription. Nothing leaves this machine.",
        # The page's own eyebrow, above the title: same words, same place.
        "gui.eyebrow": "Recordings and transcripts",
        "gui.window_title": "audio-transcriber {version}",
        "gui.ready": "{count} recordings in the library",
        "gui.tab_transcribe": "Transcribe",
        "gui.tab_library": "Library",
        "gui.tab_system": "This machine",
        "gui.tab_transcript": "Transcript",
        "gui.tab_notes": "Notes",
        "gui.tab_summary": "Summary",
        "gui.summary_none": "No summary yet. It is written on this machine; nothing is sent anywhere.",
        "gui.summary_made_by": "written by {engine}, {when}",
        "gui.summary_tier": " (size class {tier})",
        "gui.summary_run": "Summarise",
        "gui.summary_again": "Summarise again",
        "gui.summary_engine": "Written by",
        "gui.summary_length": "How much to keep",
        "gui.summary_short": "short",
        "gui.summary_medium": "medium",
        "gui.summary_long": "long",
        "gui.summary_engine_extractive": "no model: the sentences that carry the transcript",
        "gui.summary_engine_openvino": "a local model, on this machine's Intel device",
        "gui.summary_engine_llamacpp":
            "a local model, on this machine's processor",
        "gui.summary_queued": "Summary of '{title}' queued.",
        "gui.summary_done": "Summary of '{title}' written.",
        "gui.summary_failed": "Could not summarise '{title}': {error}",
        "gui.tab_details": "Details",

        "gui.group_sources": "Recordings to transcribe",
        "gui.group_record": "Record a meeting",
        "gui.add_files": "Add files...",
        "gui.choose_files": "Choose audio or video files",
        "gui.drop_hint": "Drop audio or video files anywhere on this tab.",
        "gui.filter_media": "Audio and video",
        "gui.filter_any": "Every file",
        "gui.filter_text": "Text file",
        "gui.filter_srt": "SubRip subtitles",
        "gui.filter_vtt": "WebVTT subtitles",

        "gui.group_options": "Options",
        "gui.group_output": "What do you want out of it?",
        "gui.output_text": "Just the text",
        "gui.output_text_note":
            "Paragraphs, broken where the speech pauses. No timestamps, nobody named: "
            "the transcript to read or to paste somewhere.",
        "gui.output_speakers": "The text, with who said what",
        "gui.output_speakers_note":
            "The same text arranged as a dialogue, one block per turn. Needs "
            "diarization, which runs on the CPU and takes a while.",
        "gui.output_subtitles": "Subtitles",
        "gui.output_subtitles_note":
            "Cues with times, cut to be readable, saved as .srt or .vtt. Tick "
            "\"who said what\" as well and a change of voice is marked in them.",
        "gui.label_model": "Model",
        "gui.label_language": "Spoken language",
        "gui.label_backend": "Engine",
        "gui.label_speakers": "Speakers",
        "gui.group_subtitles": "Subtitles",
        "gui.label_sub_preset": "Preset",
        "gui.label_sub_chars": "Characters per line",
        "gui.label_sub_words": "Words per subtitle",
        "gui.label_sub_save": "Save as",
        "gui.sub_preset_numbers": "{chars} x {lines}, {cps} CPS",
        "gui.sub_from_preset": "from the preset",
        "gui.sub_preset_tip":
            "The numbers a subtitle is cut by, as a named set. Your own sets go in "
            "srt-presets.json next to config.toml and win over these by name.",
        "gui.sub_chars_tip":
            "Characters on one line, spaces included. Leave it at the preset unless you "
            "know the player: 42 is the professional reference, 32 the narrowest in use.",
        "gui.sub_words_tip":
            "A new subtitle every so many words. Not one of the trade's numbers - they "
            "measure characters and reading speed - but honoured when given.",
        "gui.sub_save_srt": ".srt",
        "gui.sub_save_vtt": ".vtt",
        "gui.sub_save_tip":
            "Keep a subtitle file in the library entry, beside the transcript. The cues "
            "themselves are always there: an entry can be exported later, with other "
            "numbers, from the same transcription.",
        "gui.sub_saved": "{formats} - {cues} cues, cut by '{preset}'",
        "gui.sub_export": "Export the subtitles",
        "gui.sub_exported": "Subtitles written to {path}  ({cues} cues, {problems} remarks)",
        "gui.sub_none": "This entry has no timestamps, so there is nothing to cut into subtitles.",
        "gui.detail_subtitles": "Subtitles",
        "gui.model_auto": "auto ({model} on this machine)",
        "gui.language_auto": "detect it",
        "gui.backend_auto": "auto",
        "gui.diarize": "Who said what",
        "gui.output_speakers_missing":
            "Not on this machine: pyannote is missing. Install it with "
            "pip install \"audio-transcriber-ov[diarize]\"",
        "gui.output_speakers_unconfigured":
            "Not on this machine: pyannote has no model. Set HUGGINGFACE_TOKEN, "
            "or put a local config in {detail}.",
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

        "gui.group_queue": "Transcription queue",
        "gui.start": "Transcribe",
        "gui.cancel": "Cancel",
        "gui.row_transcribe": "Transcribe",
        "gui.row_retry": "Try again",
        "gui.row_stop": "Stop",
        "gui.row_open": "Open",
        "gui.row_remove": "Remove",
        "gui.row_play": "Play",
        "gui.row_summary_of": "summary of the transcript \u00b7 {engine}",
        "gui.row_stop_audio": "Stop playing",
        "gui.col_actions": "",
        "gui.job_dialog_title": "Transcribe \"{title}\"",
        "gui.job_dialog_all": "Transcribe {count} recordings",
        "gui.job_dialog_note":
            "These answers are kept, so the next recording starts from them.",
        "gui.row_no_audio": "The recording is not where it was: nothing to play.",
        "gui.row_no_multimedia":
            "Playing needs QtMultimedia: pip install PySide6-Addons (or the "
            "full PySide6).",
        "gui.start_one": "Transcribe 1 recording",
        "gui.start_many": "Transcribe {count} recordings",
        "gui.step_output": "What do you want out of it?",
        "gui.step_options": "How to transcribe it",
        "gui.only_with_subtitles": "only with \"{answer}\"",
        "gui.sub_chars_short": "{count} characters",
        "gui.sub_words_short": "{count} words",
        "gui.sub_saved_none": "no file kept",
        "gui.tab_files": "Add files",
        "gui.tab_record": "Record",
        "gui.vocab_none": "none",
        "gui.vocab_chosen": "{count} chosen",
        "gui.vocab_chosen_terms": "{count} chosen, plus your own terms",
        "gui.vocab_terms_only": "your own terms",
        "gui.n_words": "{count} words",
        "gui.queue_part_running": "{count} running, at {percent}%",
        "gui.queue_part_waiting": "{count} waiting",
        "gui.queue_part_held": "{count} not started",
        "gui.queue_press_start": "Press Transcribe to start them.",
        "gui.start_tip":
            "Starts every recording that is waiting, with the answers on the left. "
            "To change them for one recording, use Transcribe on its own row.",
        "gui.started": "Started: {count}.",
        "gui.status_held": "not started",
        "gui.queue_hint":
            "Everything you add waits here until you press Transcribe.",
        "gui.cancel_job": "Take out of the queue",
        "gui.cancel_job_tip":
            "Remove a job that has not started yet. Nothing is lost: the file stays "
            "where it is.",
        "gui.stop_job": "Stop",
        "gui.stop_job_tip": "Interrupt the transcription that is running.",
        "gui.stop_job_title": "Stop this transcription",
        "gui.stop_job_confirm":
            "Stop transcribing '{title}'?\n\nWhat has been done so far is discarded - "
            "nothing reaches the library - and the recording stays where it is, so it "
            "can be queued again.\n\nIt stops at the engine's next progress report, "
            "which for faster-whisper is the next segment, a few seconds. The OpenVINO "
            "engine reports none until it has finished the whole file: there the "
            "transcription runs to the end and its result is thrown away.",
        "gui.job_cancelled": "Taken out of the queue: {title}",
        "gui.job_stopping": "Stopping '{title}' at the next checkpoint.",
        "gui.clear_finished": "Clear the finished",
        "gui.forgot_jobs": "Cleared {count} finished from the list.",
        "gui.open_entry": "Open in the library",
        "gui.forget_job": "Remove from the list",
        "gui.col_title": "Title",
        "gui.col_recording": "Recording",
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
        "gui.status_cancelled": "cancelled",
        "gui.queue_empty": "Nothing in the queue.",
        "gui.queue_idle": "Finished: {done} transcribed, {failed} failed, {cancelled} cancelled.",
        "gui.queued": "In the queue: {count}. Press Transcribe to start.",
        "gui.job_finished": "Filed in the library: {entry}",

        "gui.rec_host_api": "Audio system",
        "gui.rec_host_api_tip":
            "How the sound is asked for. On Windows: WASAPI is the native path and the "
            "only one that can record what the speakers are playing, while MME and "
            "DirectSound are older wrappers over the same devices. On Linux: ALSA, JACK "
            "or OSS, with the PulseAudio group holding what the speakers play. On macOS: "
            "Core Audio, which cannot record its own output without a virtual device.",
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
        "gui.rec_level_tip":
            "Input level. If this stays flat while somebody is talking, nothing is "
            "arriving from that source: the wrong device, a muted microphone, or Windows "
            "refusing this application the microphone (Settings, Privacy, Microphone). "
            "The scale is in decibels, so ordinary speech fills about two thirds.",
        "gui.rec_silent":
            "That recording never rose above silence. Check the level meter and the "
            "source before trusting the next one - the file is in the queue anyway.",
        "gui.rec_test": "Test audio",
        "gui.rec_test_stop": "Stop the test",
        "gui.rec_test_tip":
            "Open the chosen source without recording anything: the level bars move, "
            "and after a second and a half this says whether what is arriving behaves "
            "like somebody talking. It is a guess from the level, its dynamics and the "
            "band a voice lives in - not recognition, which is Whisper's job and needs "
            "a model and a file. It stops itself after 30 seconds.",
        "gui.rec_test_listening": "Listening...",
        "gui.rec_test_silence":
            "Nothing is arriving ({level} dB). The wrong source, a muted microphone, or "
            "Windows refusing this application the microphone.",
        "gui.rec_test_sound":
            "Sound, but it does not behave like a voice: {level} dB, {dynamic} dB "
            "between the quiet and the loud moments, {band}% of it in the speech band. "
            "A fan, a tone or music looks like this.",
        "gui.rec_test_speech":
            "This sounds like speech: peaks at {level} dB, {dynamic} dB of dynamics, "
            "{band}% in the speech band.",
        "gui.rec_test_over": "The test stopped itself after 30 seconds.",
        "gui.rec_start": "Record",
        "gui.rec_stop": "Stop",
        "gui.rec_pause": "Pause",
        "gui.rec_resume": "Resume",
        "gui.rec_queued": "The recording is in the queue; press Transcribe to start.",
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
        # --- subtitles ------------------------------------------------------
        "cli.subtitles_written": "Subtitles written to {path}  ({cues} cues)",
        "cli.subtitles_problems": "  {total} remarks on the cues cut by '{preset}':",
        "cli.subtitles_from_speech":
            "    from how fast people spoke - the trade's own remedy is to shorten the\n"
            "    text, and rewriting what somebody said is not something this program does:",
        "cli.subtitles_from_timings":
            "    from the times the engine reported:",
        "cli.subtitles_from_layout":
            "    from how the cues were laid out - these ones are the program's own doing:",
        "cli.subtitles_interpolated":
            "    Note: the engine timed segments but not single words, so every cue's times\n"
            "    were interpolated across its segment by character count. Expect them to\n"
            "    drift from the speech, and read the timing remarks above as approximate.\n"
            "    The faster-whisper backend times every word when subtitles are asked for.",
        "subtitles.empty": "nothing to show",
        "subtitles.backwards": "ends before it starts",
        "subtitles.too_wide": "a line wider than the preset allows",
        "subtitles.too_many_lines": "more lines than the preset allows",
        "subtitles.too_short": "on screen too briefly to be read",
        "subtitles.too_long": "on screen longer than the preset allows",
        "subtitles.too_fast": "more characters a second than the preset allows",
        "subtitles.too_many_words": "more words a minute than the preset allows",
        "subtitles.overlap": "overlaps the cue after it",
        "subtitles.gap_too_small": "too small a gap before the next cue",
        # --- summaries ------------------------------------------------------
        "summary.empty": "Nothing to summarise: the transcript is empty.",
        "summary.unknown_engine": "Unknown summary engine: {name}. Valid values: {valid}",
        "summary.engine_missing": "Summary engine '{name}' is not installed on this machine.",
        "summary.none_installed": "No summary engine is available on this machine.",
        "summary.written": "Summary written to {path}",
        "summary.stats":
            "   kept {kept} of {of} sentences | engine: {engine} | {elapsed:.1f}s",
        "summary.auto_engine": "engine that '--engine auto' would pick: {engine}",
        "summary.plan_line":
            "  plan for this machine: tier {tier}, {model} {quant}, context "
            "{context}, cache {kv}, about {ram} GB",
        "summary.plan_none":
            "  plan for this machine: no model fits ({needed} GB would be "
            "needed), so summaries quote the transcript",
        "summary.npu_warning":
            "  WARNING: the NPU runs LLMs on static shapes, with the prompt capped at\n"
            "  1024 tokens by default and 8K at best. An hour of transcript is about\n"
            "  15000: expect a failure or a truncated summary. '--device GPU' is the\n"
            "  right accelerator for this.",
        "summary.openvino_missing":
            "Summary engine 'openvino': openvino-genai is not installed.\n"
            "  pip install \"audio-transcriber-ov[summarize-ov]\"",
        "summary.openvino_convert_missing":
            "Converting a model needs optimum-intel and transformers.\n"
            "  pip install \"audio-transcriber-ov[summarize-ov]\"",
        "summary.converting":
            "  Converting {model} to OpenVINO at int{bits}. This happens once, and it\n"
            "  downloads several gigabytes.",
        "summary.conversion_failed": "Could not convert {model}: {error}",
        "summary.loading_model": "  Loading {path} on {device}...",
        "summary.load_failed":
            "The model could not be loaded on {device}: {error}",
        "summary.pass": "  Reading part {part} of {total}...",
        "summary.pass_cached":
            "  Part {part} of {total} was already read; reusing it.",
        "summary.pass_echoed":
            "  Part {part} of {total} came back as the question; quoting "
            "that part instead.",
        "summary.still_thinking":
            "  The model was still thinking when its answer ran out; "
            "asking again with {tokens} tokens.",
        "summary.folding": "  Folding {groups} groups (level {level})...",
        "summary.prereducing":
            "  {passes} passes is more than this machine should spend; "
            "choosing what matters and reading {allowed}.",
        "summary.no_room":
            "No model fits in this machine's memory: {needed} GB needed, "
            "{free} GB free. Quoting the transcript instead.",
        "summary.over_budget":
            "  WARNING: {model} is estimated at {needed} GB and this machine "
            "has {free} GB free. Loading it anyway, as asked.",
        "summary.reducing": "  Writing the summary from {total} parts...",
        "summary.llamacpp_missing":
            "llama.cpp is not installed. Run: pip install llama-cpp-python\n"
            "  or put the 'llama-server' binary on the PATH.",
        "summary.no_gguf": "No GGUF is published for {model}.",
        "summary.downloading":
            "Downloading {model} ({quant}) - once, and only this once...",
        "summary.model_ready": "Model ready at: {path}",
        "summary.download_truncated":
            "The download of {model} stopped early: {got} bytes of {expected}.",
        "summary.download_failed": "Could not download {model}: {error}",
        "summary.server_stopped":
            "llama-server stopped before answering (exit {code}).",
        "summary.server_silent": "llama-server did not answer within {seconds}s.",
        "summary.server_failed": "llama-server refused the request: {error}",
        "summary.model_said_nothing":
            "{model} returned nothing usable. Try another model, or "
            "'--engine extractive'.",
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
            "CPU: {cores} core | RAM: {ram} liberi su {total} | OpenVINO: {openvino} | "
            "CUDA: {cuda}",
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
        "openvino.no_vad":
            "  NOTA: questo backend non ha un filtro di attivita' vocale, quindi su un\n"
            "  silenzio lungo Whisper puo' inventare una frase ('Grazie a tutti'). Quelle\n"
            "  evidenti vengono tolte dalla trascrizione dopo. Il backend faster-whisper\n"
            "  taglia i silenzi prima che il modello li veda: --backend faster-whisper.",
        "openvino.falling_back_to_long_form":
            "  (questo modello ha rifiutato i tempi per singola parola: {error}\n"
            "   riprovo con i tempi dei segmenti - i tagli dei sottotitoli saranno interpolati)",
        "openvino.falling_back_to_windowed":
            "  (questo optimum-intel non sa eseguire il ciclo long-form di Whisper: {error}\n"
            "   torno a finestre fisse da 30 s. Dove due finestre si sovrappongono le parole\n"
            "   possono uscire due volte; i doppioni vengono tagliati dalla trascrizione dopo,\n"
            "   e il prompt di parole chiave viene lasciato cadere perche' peggiora la cosa.)",
        "openvino.transcription_failed":
            "Backend 'openvino': la trascrizione non e' partita.\n  {error}",

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

        # --- stages of one run, shown while it is under way -----------------
        "stage.starting": "avvio",
        "stage.decoded": "audio decodificato",
        "stage.loading_model": "caricamento del modello",
        "stage.converting_model": "conversione del modello",
        "stage.compiling_model": "compilazione per il dispositivo",
        "stage.transcribing": "trascrizione",
        "stage.diarizing": "chi ha detto cosa",
        "stage.laying_out": "impaginazione del testo",
        "stage.summary_selecting": "scelta di cosa conta",
        "stage.summary_reading": "lettura della trascrizione",
        "stage.summary_writing": "scrittura del riassunto",

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
        "gui.tagline": "Trascrizione locale. Niente esce da questa macchina.",
        "gui.eyebrow": "Registrazioni e trascrizioni",
        "gui.window_title": "audio-transcriber {version}",
        "gui.ready": "{count} registrazioni in libreria",
        "gui.tab_transcribe": "Trascrivi",
        "gui.tab_library": "Libreria",
        "gui.tab_system": "Questa macchina",
        "gui.tab_transcript": "Trascrizione",
        "gui.tab_notes": "Note",
        "gui.tab_summary": "Riassunto",
        "gui.summary_none": "Nessun riassunto. Viene scritto su questa macchina: non esce niente da qui.",
        "gui.summary_made_by": "scritto da {engine}, {when}",
        "gui.summary_tier": " (classe {tier})",
        "gui.summary_run": "Riassumi",
        "gui.summary_again": "Riassumi di nuovo",
        "gui.summary_engine": "Scritto da",
        "gui.summary_length": "Quanto tenere",
        "gui.summary_short": "corto",
        "gui.summary_medium": "medio",
        "gui.summary_long": "lungo",
        "gui.summary_engine_extractive": "nessun modello: le frasi che reggono la trascrizione",
        "gui.summary_engine_openvino": "un modello locale, sul dispositivo Intel di questa macchina",
        "gui.summary_engine_llamacpp":
            "un modello locale, sul processore di questa macchina",
        "gui.summary_queued": "Riassunto di '{title}' messo in coda.",
        "gui.summary_done": "Riassunto di '{title}' scritto.",
        "gui.summary_failed": "Non ho riassunto '{title}': {error}",
        "gui.tab_details": "Dettagli",

        "gui.group_sources": "Registrazioni da trascrivere",
        "gui.group_record": "Registra una riunione",
        "gui.add_files": "Aggiungi file...",
        "gui.choose_files": "Scegli i file audio o video",
        "gui.drop_hint": "Trascina i file audio o video in un punto qualsiasi di questa scheda.",
        "gui.filter_media": "Audio e video",
        "gui.filter_any": "Tutti i file",
        "gui.filter_text": "File di testo",
        "gui.filter_srt": "Sottotitoli SubRip",
        "gui.filter_vtt": "Sottotitoli WebVTT",

        "gui.group_options": "Opzioni",
        "gui.group_output": "Cosa vuoi ottenere?",
        "gui.output_text": "Solo il testo",
        "gui.output_text_note":
            "Paragrafi, spezzati dove il parlato si interrompe. Nessun timestamp, "
            "nessun nome: la trascrizione da leggere o da incollare altrove.",
        "gui.output_speakers": "Il testo, con chi dice cosa",
        "gui.output_speakers_note":
            "Lo stesso testo disposto come un dialogo, un blocco per battuta. Richiede "
            "la diarizzazione, che gira su CPU e ci mette un po'.",
        "gui.output_subtitles": "Sottotitoli",
        "gui.output_subtitles_note":
            "Battute con i tempi, tagliate per essere leggibili, salvate in .srt o "
            ".vtt. Spunta anche \"chi ha detto cosa\" e il cambio di voce viene "
            "segnato dentro.",
        "gui.label_model": "Modello",
        "gui.label_language": "Lingua parlata",
        "gui.label_backend": "Motore",
        "gui.label_speakers": "Interlocutori",
        "gui.group_subtitles": "Sottotitoli",
        "gui.label_sub_preset": "Preset",
        "gui.label_sub_chars": "Caratteri per riga",
        "gui.label_sub_words": "Parole per sottotitolo",
        "gui.label_sub_save": "Salva come",
        "gui.sub_preset_numbers": "{chars} x {lines}, {cps} CPS",
        "gui.sub_from_preset": "dal preset",
        "gui.sub_preset_tip":
            "I numeri con cui si taglia un sottotitolo, come insieme con un nome. I tuoi "
            "insiemi vanno in srt-presets.json accanto a config.toml e vincono su questi "
            "a parita' di nome.",
        "gui.sub_chars_tip":
            "Caratteri su una riga, spazi compresi. Lascialo al preset se non conosci il "
            "player: 42 e' il riferimento professionale, 32 il piu' stretto in uso.",
        "gui.sub_words_tip":
            "Un sottotitolo nuovo ogni tot parole. Non e' uno dei numeri del mestiere - "
            "quello misura caratteri e velocita' di lettura - ma viene rispettato.",
        "gui.sub_save_srt": ".srt",
        "gui.sub_save_vtt": ".vtt",
        "gui.sub_save_tip":
            "Tiene un file di sottotitoli nella voce di libreria, accanto alla "
            "trascrizione. Le battute ci sono comunque: una voce si puo' esportare dopo, "
            "con altri numeri, dalla stessa trascrizione.",
        "gui.sub_saved": "{formats} - {cues} battute, tagliate con '{preset}'",
        "gui.sub_export": "Esporta i sottotitoli",
        "gui.sub_exported": "Sottotitoli scritti in {path}  ({cues} battute, {problems} rilievi)",
        "gui.sub_none": "Questa voce non ha timestamp, quindi non c'e' nulla da tagliare in sottotitoli.",
        "gui.detail_subtitles": "Sottotitoli",
        "gui.model_auto": "auto ({model} su questa macchina)",
        "gui.language_auto": "riconoscila",
        "gui.backend_auto": "auto",
        "gui.diarize": "Chi ha detto cosa",
        "gui.output_speakers_missing":
            "Non disponibile su questa macchina: manca pyannote. Si installa con "
            "pip install \"audio-transcriber-ov[diarize]\"",
        "gui.output_speakers_unconfigured":
            "Non disponibile su questa macchina: pyannote non ha un modello. "
            "Imposta HUGGINGFACE_TOKEN, oppure metti un config locale in {detail}.",
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

        "gui.group_queue": "Coda di trascrizione",
        "gui.start": "Trascrivi",
        "gui.cancel": "Annulla",
        "gui.row_transcribe": "Trascrivi",
        "gui.row_retry": "Riprova",
        "gui.row_stop": "Interrompi",
        "gui.row_open": "Apri",
        "gui.row_remove": "Togli",
        "gui.row_play": "Ascolta",
        "gui.row_summary_of": "riassunto della trascrizione \u00b7 {engine}",
        "gui.row_stop_audio": "Ferma l'ascolto",
        "gui.col_actions": "",
        "gui.job_dialog_title": "Trascrivi \"{title}\"",
        "gui.job_dialog_all": "Trascrivi {count} registrazioni",
        "gui.job_dialog_note":
            "Le risposte restano, cosi' la prossima registrazione parte da queste.",
        "gui.row_no_audio": "La registrazione non e' piu' dov'era: non c'e' nulla da ascoltare.",
        "gui.row_no_multimedia":
            "Per ascoltare serve QtMultimedia: pip install PySide6-Addons (o "
            "PySide6 completo).",
        "gui.start_one": "Trascrivi 1 registrazione",
        "gui.start_many": "Trascrivi {count} registrazioni",
        "gui.step_output": "Cosa vuoi ottenere?",
        "gui.step_options": "Come trascriverla",
        "gui.only_with_subtitles": "solo con \"{answer}\"",
        "gui.sub_chars_short": "{count} caratteri",
        "gui.sub_words_short": "{count} parole",
        "gui.sub_saved_none": "nessun file salvato",
        "gui.tab_files": "Aggiungi file",
        "gui.tab_record": "Registra",
        "gui.vocab_none": "nessuno",
        "gui.vocab_chosen": "{count} scelti",
        "gui.vocab_chosen_terms": "{count} scelti, piu' i tuoi termini",
        "gui.vocab_terms_only": "i tuoi termini",
        "gui.n_words": "{count} parole",
        "gui.queue_part_running": "{count} in corso, al {percent}%",
        "gui.queue_part_waiting": "{count} in attesa",
        "gui.queue_part_held": "{count} da avviare",
        "gui.queue_press_start": "Premi Trascrivi per avviarle.",
        "gui.start_tip":
            "Avvia tutte le registrazioni in attesa, con le risposte qui a sinistra. "
            "Per cambiarle su una sola, usa Trascrivi sulla sua riga.",
        "gui.started": "Avviate: {count}.",
        "gui.status_held": "da avviare",
        "gui.queue_hint":
            "Quello che aggiungi resta in attesa finche' non premi Trascrivi.",
        "gui.cancel_job": "Togli dalla coda",
        "gui.cancel_job_tip":
            "Togli un lavoro che non e' ancora partito. Non si perde niente: il file "
            "resta dov'e'.",
        "gui.stop_job": "Ferma",
        "gui.stop_job_tip": "Interrompi la trascrizione in corso.",
        "gui.stop_job_title": "Ferma questa trascrizione",
        "gui.stop_job_confirm":
            "Fermo la trascrizione di '{title}'?\n\nQuello che ha fatto finora viene "
            "scartato - in libreria non arriva nulla - e la registrazione resta dov'e', "
            "quindi puoi rimetterla in coda.\n\nSi ferma al prossimo avanzamento "
            "riportato dal motore: con faster-whisper e' il segmento successivo, pochi "
            "secondi. Il motore OpenVINO non ne riporta nessuno finche' non ha finito "
            "tutto il file: in quel caso la trascrizione arriva alla fine e il risultato "
            "viene buttato.",
        "gui.job_cancelled": "Tolto dalla coda: {title}",
        "gui.job_stopping": "Fermo '{title}' al prossimo controllo.",
        "gui.clear_finished": "Svuota i finiti",
        "gui.forgot_jobs": "Tolti {count} lavori finiti dall'elenco.",
        "gui.open_entry": "Apri nella libreria",
        "gui.forget_job": "Togli dall'elenco",
        "gui.col_title": "Titolo",
        "gui.col_recording": "Registrazione",
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
        "gui.status_cancelled": "annullata",
        "gui.queue_empty": "Nessun lavoro in coda.",
        "gui.queue_idle": "Finito: {done} trascritte, {failed} fallite, {cancelled} annullate.",
        "gui.queued": "In coda: {count}. Premi Trascrivi per partire.",
        "gui.job_finished": "Archiviata in libreria: {entry}",

        "gui.rec_host_api": "Sistema audio",
        "gui.rec_host_api_tip":
            "Come si chiede il suono. Su Windows: WASAPI e' la via nativa ed e' la sola "
            "che puo' registrare quello che riproducono gli altoparlanti, mentre MME e "
            "DirectSound sono involucri piu' vecchi sugli stessi dispositivi. Su Linux: "
            "ALSA, JACK o OSS, e il gruppo PulseAudio contiene quello che suona. Su "
            "macOS: Core Audio, che non sa registrare la propria uscita senza un "
            "dispositivo virtuale.",
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
        "gui.rec_level_tip":
            "Livello in ingresso. Se resta piatto mentre qualcuno parla, da quella sorgente "
            "non arriva nulla: dispositivo sbagliato, microfono disattivato, oppure Windows "
            "che nega il microfono a questa applicazione (Impostazioni, Privacy, Microfono). "
            "La scala e' in decibel, percio' il parlato normale ne riempie circa due terzi.",
        "gui.rec_silent":
            "Quella registrazione non e' mai salita sopra il silenzio. Controlla la barra del "
            "livello e la sorgente prima di fidarti della prossima: il file e' comunque in coda.",
        "gui.rec_test": "Prova audio",
        "gui.rec_test_stop": "Ferma la prova",
        "gui.rec_test_tip":
            "Apre la sorgente scelta senza registrare niente: le barre del livello si "
            "muovono e dopo un secondo e mezzo qui viene detto se quello che arriva si "
            "comporta come qualcuno che parla. E' una stima basata sul livello, sulla sua "
            "dinamica e sulla banda in cui vive una voce - non un riconoscimento, che e' "
            "il mestiere di Whisper e richiede un modello e un file. Si ferma da se' dopo "
            "30 secondi.",
        "gui.rec_test_listening": "Ascolto...",
        "gui.rec_test_silence":
            "Non arriva nulla ({level} dB). Sorgente sbagliata, microfono disattivato, "
            "oppure Windows che nega il microfono a questa applicazione.",
        "gui.rec_test_sound":
            "C'e' del suono, ma non si comporta come una voce: {level} dB, {dynamic} dB "
            "fra i momenti piano e quelli forti, {band}% in banda vocale. Una ventola, un "
            "tono o della musica danno questo risultato.",
        "gui.rec_test_speech":
            "Sembra parlato: picchi a {level} dB, {dynamic} dB di dinamica, {band}% in "
            "banda vocale.",
        "gui.rec_test_over": "La prova si e' fermata da se' dopo 30 secondi.",
        "gui.rec_start": "Registra",
        "gui.rec_stop": "Ferma",
        "gui.rec_pause": "Pausa",
        "gui.rec_resume": "Riprendi",
        "gui.rec_queued": "La registrazione e' in coda; premi Trascrivi per partire.",
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
        # --- subtitles ------------------------------------------------------
        "cli.subtitles_written": "Sottotitoli scritti in {path}  ({cues} battute)",
        "cli.subtitles_problems": "  {total} rilievi sulle battute tagliate con '{preset}':",
        "cli.subtitles_from_speech":
            "    da quanto velocemente si e' parlato - il rimedio del mestiere e' accorciare\n"
            "    il testo, e riscrivere quello che uno ha detto questo programma non lo fa:",
        "cli.subtitles_from_timings":
            "    dai tempi riportati dal motore:",
        "cli.subtitles_from_layout":
            "    dall'impaginazione delle battute - questi sono responsabilita' del programma:",
        "cli.subtitles_interpolated":
            "    Nota: il motore ha dato i tempi dei segmenti ma non delle singole parole,\n"
            "    quindi i tempi di ogni battuta sono interpolati sul segmento a conteggio di\n"
            "    caratteri. Aspettati che scivolino rispetto al parlato, e leggi i rilievi sui\n"
            "    tempi qui sopra come approssimativi. Il backend faster-whisper cronometra\n"
            "    ogni parola quando si chiedono i sottotitoli.",
        "subtitles.empty": "senza testo",
        "subtitles.backwards": "finisce prima di iniziare",
        "subtitles.too_wide": "una riga piu' larga di quanto il preset consenta",
        "subtitles.too_many_lines": "piu' righe di quante il preset consenta",
        "subtitles.too_short": "in scena troppo poco per essere letta",
        "subtitles.too_long": "in scena piu' a lungo di quanto il preset consenta",
        "subtitles.too_fast": "piu' caratteri al secondo di quanti il preset consenta",
        "subtitles.too_many_words": "piu' parole al minuto di quante il preset consenta",
        "subtitles.overlap": "si sovrappone alla battuta successiva",
        "subtitles.gap_too_small": "stacco troppo piccolo prima della battuta successiva",
        # --- summaries ------------------------------------------------------
        "summary.empty": "Non c'e' niente da riassumere: la trascrizione e' vuota.",
        "summary.unknown_engine": "Motore di riassunto sconosciuto: {name}. Valori validi: {valid}",
        "summary.engine_missing": "Il motore di riassunto '{name}' non e' installato su questa macchina.",
        "summary.none_installed": "Nessun motore di riassunto disponibile su questa macchina.",
        "summary.written": "Riassunto scritto in {path}",
        "summary.stats":
            "   tenute {kept} frasi su {of} | motore: {engine} | {elapsed:.1f}s",
        "summary.auto_engine": "motore che '--engine auto' sceglierebbe: {engine}",
        "summary.plan_line":
            "  piano per questa macchina: tier {tier}, {model} {quant}, "
            "contesto {context}, cache {kv}, circa {ram} GB",
        "summary.plan_none":
            "  piano per questa macchina: nessun modello entra (ne "
            "servirebbero {needed} GB), quindi i riassunti citano la "
            "trascrizione",
        "summary.npu_warning":
            "  ATTENZIONE: l'NPU esegue gli LLM a forme statiche, con il prompt limitato\n"
            "  a 1024 token di default e 8K al massimo. Un'ora di trascrizione sono circa\n"
            "  15000 token: aspettati un errore o un riassunto troncato. Per questo\n"
            "  lavoro l'acceleratore giusto e' '--device GPU'.",
        "summary.openvino_missing":
            "Motore di riassunto 'openvino': openvino-genai non e' installato.\n"
            "  pip install \"audio-transcriber-ov[summarize-ov]\"",
        "summary.openvino_convert_missing":
            "Per convertire un modello servono optimum-intel e transformers.\n"
            "  pip install \"audio-transcriber-ov[summarize-ov]\"",
        "summary.converting":
            "  Converto {model} in OpenVINO a int{bits}. Succede una volta sola, e\n"
            "  scarica diversi gigabyte.",
        "summary.conversion_failed": "Non sono riuscito a convertire {model}: {error}",
        "summary.loading_model": "  Carico {path} su {device}...",
        "summary.load_failed":
            "Il modello non si e' potuto caricare su {device}: {error}",
        "summary.pass": "  Leggo la parte {part} di {total}...",
        "summary.pass_cached":
            "  La parte {part} di {total} era gia' letta: la riuso.",
        "summary.pass_echoed":
            "  La parte {part} di {total} e' tornata indietro come domanda: "
            "cito quella parte invece.",
        "summary.still_thinking":
            "  Il modello stava ancora ragionando quando la risposta e' "
            "finita: richiedo con {tokens} token.",
        "summary.folding": "  Fondo {groups} gruppi (livello {level})...",
        "summary.prereducing":
            "  {passes} passaggi sono troppi per questa macchina: scelgo "
            "quello che conta e ne leggo {allowed}.",
        "summary.no_room":
            "Nessun modello entra nella memoria di questa macchina: {needed} "
            "GB richiesti, {free} GB liberi. Cito la trascrizione.",
        "summary.over_budget":
            "  ATTENZIONE: {model} e' stimato in {needed} GB e questa "
            "macchina ne ha {free} liberi. Lo carico lo stesso, come chiesto.",
        "summary.reducing": "  Scrivo il riassunto dalle {total} parti...",
        "summary.llamacpp_missing":
            "llama.cpp non e' installato. Esegui: pip install llama-cpp-python\n"
            "  oppure metti l'eseguibile 'llama-server' nel PATH.",
        "summary.no_gguf": "Per {model} non e' pubblicato nessun GGUF.",
        "summary.downloading":
            "Scarico {model} ({quant}): una volta sola, adesso...",
        "summary.model_ready": "Modello pronto in: {path}",
        "summary.download_truncated":
            "Lo scaricamento di {model} si e' interrotto: {got} byte su {expected}.",
        "summary.download_failed": "Non riesco a scaricare {model}: {error}",
        "summary.server_stopped":
            "llama-server si e' fermato prima di rispondere (uscita {code}).",
        "summary.server_silent": "llama-server non ha risposto entro {seconds}s.",
        "summary.server_failed": "llama-server ha rifiutato la richiesta: {error}",
        "summary.model_said_nothing":
            "{model} non ha restituito niente di utilizzabile. Prova un altro modello, "
            "oppure '--engine extractive'.",
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
        "help.cmd_summarize": "summarise a transcript: a library entry, or a text file",
        "help.sum_query": "library entry (id, or part of the title), or the path of a text file",
        "help.sum_engine": "which engine writes the summary (default: auto)",
        "help.sum_length": "how much of the transcript to keep: short | medium | long",
        "help.sum_model": "which model writes it: auto, a Hugging Face id, or a converted directory",
        "help.sum_context":
            "tokens of context to give the model (default: from the plan)",
        "help.sum_kv":
            "KV cache precision: q8_0, or q8_0/q4_0 for key and value apart",
        "help.sum_tier": "force a size class: xs | s | m | l",
        "help.sum_device": "Intel device to run the model on: auto | CPU | GPU | NPU",
        "help.sum_out": "write the summary to this file instead of into the entry",
        "help.sum_print": "print the summary instead of saving it anywhere",
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
        "help.output":
            "what the run is for: text (just the words), speakers (who said "
            "what) or subtitles (cues, saved as .srt unless --vtt says "
            "otherwise). It settles the flags below it.",
        "help.diarize": "work out who said what (pyannote, on CPU)",
        "help.speakers": "number of speakers, if known (improves the result a lot)",
        "help.hf_token": "Hugging Face token for pyannote (or the HUGGINGFACE_TOKEN variable)",
        "help.diar_model": "HF id (online, needs a token) or path to a local config.yaml (offline)",
        "help.library": "file the result in the library instead of writing a .txt next to the input",
        "help.library_store": "how the library keeps the original: copy (default), move, or reference it in place",
        "help.title": "title for the library entry (default: the input file name)",
        "help.json": "also write the segments, with timestamps, as JSON",
        "help.srt": "save subtitles as .srt as well",
        "help.vtt": "save subtitles as .vtt as well",
        "help.subtitle_preset": "numbers to cut the subtitles by: netflix, bbc, ebu_broadcast, fcc_verbatim, social_vertical, social_karaoke, kids_accessible",
        "help.subtitle_chars": "characters per subtitle line, overriding the preset",
        "help.subtitle_lines": "lines per subtitle, overriding the preset",
        "help.subtitle_words": "words per subtitle, if you would rather cap that",
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
        "help.cmd_summarize": "riassumi una trascrizione: una voce di libreria, o un file di testo",
        "help.sum_query": "voce di libreria (id, o parte del titolo), oppure il percorso di un file di testo",
        "help.sum_engine": "quale motore scrive il riassunto (default: auto)",
        "help.sum_length": "quanto tenere della trascrizione: short | medium | long",
        "help.sum_model": "quale modello lo scrive: auto, un id Hugging Face, o una cartella gia' convertita",
        "help.sum_context":
            "token di contesto da dare al modello (default: dal piano)",
        "help.sum_kv":
            "precisione della cache KV: q8_0, oppure q8_0/q4_0 per chiave e valore",
        "help.sum_tier": "forza una classe di dimensione: xs | s | m | l",
        "help.sum_device": "dispositivo Intel su cui eseguire il modello: auto | CPU | GPU | NPU",
        "help.sum_out": "scrivi il riassunto in questo file invece che nella voce",
        "help.sum_print": "stampa il riassunto invece di salvarlo",
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
        "help.output":
            "a cosa serve la trascrizione: text (solo le parole), speakers "
            "(chi dice cosa) o subtitles (battute, salvate in .srt se non si "
            "dice --vtt). Decide le opzioni qui sotto.",
        "help.diarize": "ricostruisci chi dice cosa (pyannote, su CPU)",
        "help.speakers": "numero di speaker, se noto (migliora molto la resa)",
        "help.hf_token": "token Hugging Face per pyannote (o la variabile HUGGINGFACE_TOKEN)",
        "help.diar_model": "id HF (online, con token) o percorso a un config.yaml locale (offline)",
        "help.library": "archivia il risultato in libreria invece di scrivere un .txt accanto al file",
        "help.library_store": "come la libreria conserva l'originale: copy (default), move, oppure reference (lascialo dov'e')",
        "help.title": "titolo della voce di libreria (default: il nome del file)",
        "help.json": "scrivi anche i segmenti, con i timestamp, in formato JSON",
        "help.srt": "salva anche i sottotitoli in .srt",
        "help.vtt": "salva anche i sottotitoli in .vtt",
        "help.subtitle_preset": "i numeri con cui tagliare i sottotitoli: netflix, bbc, ebu_broadcast, fcc_verbatim, social_vertical, social_karaoke, kids_accessible",
        "help.subtitle_chars": "caratteri per riga di sottotitolo, invece di quelli del preset",
        "help.subtitle_lines": "righe per sottotitolo, invece di quelle del preset",
        "help.subtitle_words": "parole per sottotitolo, se preferisci limitare quelle",
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
