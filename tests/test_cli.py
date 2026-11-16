"""Command-line plumbing: argument shims, formatting, and command dispatch."""
import pytest

from audio_transcriber import cli, paths
from audio_transcriber.config import DEFAULTS


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv("AUDIO_TRANSCRIBER_LANG", raising=False)


# --- the backwards-compatible one-argument form ---------------------------

def test_a_bare_file_becomes_a_transcribe_command():
    assert cli.insert_default_command(["meeting.wav"]) == ["transcribe", "meeting.wav"]


def test_a_file_with_options_becomes_a_transcribe_command():
    assert cli.insert_default_command(["a.wav", "--model", "small"]) == [
        "transcribe", "a.wav", "--model", "small"]


def test_a_known_command_is_left_alone():
    for command in cli.COMMANDS:
        assert cli.insert_default_command([command, "x"]) == [command, "x"]


def test_help_and_version_are_left_alone():
    assert cli.insert_default_command(["--help"]) == ["--help"]
    assert cli.insert_default_command(["--version"]) == ["--version"]


def test_a_global_language_option_is_stepped_over():
    assert cli.insert_default_command(["--lang", "it", "a.wav"]) == [
        "--lang", "it", "transcribe", "a.wav"]
    assert cli.insert_default_command(["--lang=it", "library", "list"]) == [
        "--lang=it", "library", "list"]


def test_language_is_read_before_argparse_runs():
    assert cli.preparse_language(["--lang", "it", "x.wav"]) == "it"
    assert cli.preparse_language(["--lang=en", "x.wav"]) == "en"
    assert cli.preparse_language(["x.wav"]) is None


# --- formatting -----------------------------------------------------------

@pytest.mark.parametrize("seconds,expected", [
    (0, "-"), (None, "-"), (45, "45s"), (200, "3m 20s"), (6000, "1h 40m"),
])
def test_duration_formatting(seconds, expected):
    assert cli.format_duration(seconds) == expected


def test_table_sizes_columns_to_the_content(capsys):
    cli.print_table([["a", "long value"], ["bbbb", "x"]], headers=["ID", "VALUE"])
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("ID")
    assert lines[2].startswith("a     long value")


def test_an_empty_table_prints_nothing(capsys):
    cli.print_table([], headers=["ID"])
    assert capsys.readouterr().out == ""


# --- dispatch -------------------------------------------------------------

def test_no_arguments_prints_help_and_fails():
    assert cli.main([]) == 1


def test_diarize_init_writes_a_config_for_the_files_that_are_there(tmp_path, capsys,
                                                                  monkeypatch):
    """A folder of weights downloaded by hand has no config.yaml in it, and
    pyannote will not start without one. Writing that file by hand — the right
    keys, the published thresholds — is the step people give up at."""
    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    folder = tmp_path / "diarization"
    for name in ("wespeaker-voxceleb-resnet34-LM/pytorch_model.bin",
                 "segmentation-3.0/pytorch_model.bin"):
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"weights")

    assert cli.main(["diarize", "init", str(folder)]) == 0
    written = (folder / "config.yaml").read_text(encoding="utf-8")
    assert "wespeaker-voxceleb-resnet34-LM/pytorch_model.bin" in written
    assert "SpeakerDiarization" in written
    assert "Written" in capsys.readouterr().out


def test_diarize_init_on_an_empty_folder_says_what_it_found(tmp_path, capsys,
                                                            monkeypatch):
    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    folder = tmp_path / "diarization"
    folder.mkdir()

    with pytest.raises(SystemExit) as stopped:
        cli.main(["diarize", "init", str(folder)])
    assert "No pyannote model files" in str(stopped.value)


def test_diarize_init_defaults_to_the_folder_the_program_looks_in(tmp_path, capsys,
                                                                 monkeypatch):
    """Which is the folder somebody was told to put the models in."""
    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    managed = tmp_path / "home" / "data" / "diarization"
    for name in ("wespeaker/pytorch_model.bin", "segmentation/pytorch_model.bin"):
        target = managed / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"weights")

    assert cli.main(["diarize", "init"]) == 0
    assert (managed / "config.yaml").exists()


def test_diarize_check_tries_the_token_instead_of_noting_that_it_exists(
        tmp_path, capsys, monkeypatch):
    """With no local files the models are downloaded, so the download is what
    the check has to test: "a token is set" was never the question."""
    import sys
    import types

    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_xxx")
    from audio_transcriber import diarization

    monkeypatch.setattr(diarization, "module_available", lambda name: True)
    monkeypatch.setitem(sys.modules, "pyannote", types.ModuleType("pyannote"))
    monkeypatch.setitem(sys.modules, "pyannote.audio",
                        types.ModuleType("pyannote.audio"))
    monkeypatch.setattr(diarization, "hub_check", lambda repo, token: [
        (repo, None),
        ("pyannote/segmentation-3.0", RuntimeError("403 Forbidden: gated")),
    ])

    with pytest.raises(SystemExit) as stopped:
        cli.main(["diarize", "check"])

    printed = capsys.readouterr().out
    assert "OK  pyannote/speaker-diarization-3.1" in printed
    assert "NO  pyannote/segmentation-3.0" in printed
    assert "gated repos" in str(stopped.value)     # and which setting it is


def test_a_hub_that_cannot_be_reached_is_not_reported_as_a_licence(monkeypatch):
    """Offline mode is what one sets to get past a refused file; a wall of
    text about accepting licences is then exactly the wrong page to read."""
    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")

    help_text = cli.hub_failure_help(OSError(
        "we cannot find the requested files in the local cache"))

    assert "HF_HUB_OFFLINE" in help_text
    assert ".env" in help_text                     # where it was probably set
    assert "gated repos" not in help_text


def test_a_refusal_is_still_reported_as_one(monkeypatch):
    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    assert "gated repos" in cli.hub_failure_help(RuntimeError("403 Forbidden"))


def test_hardware_reports_the_machine(capsys, monkeypatch):
    from audio_transcriber import backends

    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    monkeypatch.setattr(backends, "is_installed",
                        lambda name: name == backends.FASTER_WHISPER)
    assert cli.main(["hardware"]) == 0
    output = capsys.readouterr().out
    assert "CPU" in output and "faster-whisper" in output


def test_hardware_still_reports_when_no_engine_is_installed(capsys, monkeypatch):
    """This is the command people run *because* something is missing, so it has
    to say so instead of exiting on the first question it cannot answer."""
    from audio_transcriber import backends

    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    monkeypatch.setattr(backends, "is_installed", lambda name: False)
    assert cli.main(["hardware"]) == 1
    output = capsys.readouterr().out
    assert "CPU" in output                       # the hardware summary survived
    assert "No transcription backend is installed" in output
    assert "diarization" in output               # and the report carried on


def test_paths_lists_the_managed_directories(capsys, tmp_path):
    cli.main(["paths"])
    output = capsys.readouterr().out
    assert str(tmp_path / "home" / "data") in output


def test_config_init_then_show(capsys):
    cli.main(["config", "init"])
    created = capsys.readouterr().out.strip()
    assert created == paths.config_file()
    cli.main(["config", "show"])
    assert "backend" in capsys.readouterr().out


def test_config_init_refuses_to_overwrite_without_force(capsys):
    cli.main(["config", "init"])
    capsys.readouterr()
    with pytest.raises(SystemExit):
        cli.main(["config", "init"])


def test_config_init_backs_up_the_previous_file(capsys):
    import os
    cli.main(["config", "init"])
    capsys.readouterr()
    cli.main(["config", "init", "--force"])
    assert os.path.exists(paths.config_file() + ".bak")


def test_the_config_file_sets_the_interface_language(monkeypatch):
    """It was written down in config.toml and never read."""
    from audio_transcriber import i18n

    monkeypatch.setattr(i18n, "_current", None)
    paths.ensure(paths.config_dir())
    with open(paths.config_file(), "w", encoding="utf-8") as handle:
        handle.write('[general]\ninterface_language = "fr"\n')
    cli.main(["paths"])
    assert i18n.language() == "fr"
    # --lang still wins over it.
    cli.main(["paths", "--lang", "de"])
    assert i18n.language() == "de"
    i18n.set_language("en")


def test_a_broken_config_still_lets_you_repair_it(capsys):
    paths.ensure(paths.config_dir())
    with open(paths.config_file(), "w", encoding="utf-8") as handle:
        handle.write("this is not [[[ toml\n")
    cli.main(["config", "init", "--force"])   # must not raise
    assert "Invalid configuration" in capsys.readouterr().err


def test_a_broken_config_stops_a_transcription(capsys):
    paths.ensure(paths.config_dir())
    with open(paths.config_file(), "w", encoding="utf-8") as handle:
        handle.write("this is not [[[ toml\n")
    with pytest.raises(SystemExit):
        cli.main(["library", "list"])


def test_a_missing_input_file_is_reported():
    with pytest.raises(SystemExit) as error:
        cli.main(["/nonexistent/recording.wav"])
    assert "nonexistent" in str(error.value)


def test_library_list_on_an_empty_library(capsys):
    cli.main(["library", "list"])
    assert "empty" in capsys.readouterr().out.lower()


def test_the_language_option_switches_the_messages(capsys):
    cli.main(["--lang", "it", "paths"])
    assert "Cartelle" in capsys.readouterr().out


def test_config_file_settings_reach_the_defaults(capsys):
    paths.ensure(paths.config_dir())
    with open(paths.config_file(), "w", encoding="utf-8") as handle:
        handle.write('[transcription]\nmodel = "small"\n')
    cli.main(["config", "show"])
    assert "small" in capsys.readouterr().out


def test_cli_settings_collect_the_inverted_vad_flag():
    parser = cli.build_parser(dict(DEFAULTS))
    args = parser.parse_args(["transcribe", "a.wav", "--no-vad"])
    assert cli.collect_cli_settings(args)["vad"] is False
    args = parser.parse_args(["transcribe", "a.wav"])
    assert cli.collect_cli_settings(args)["vad"] is None


def test_a_summary_can_be_read_back_from_the_command_line():
    parser = cli.build_parser(dict(DEFAULTS))
    args = parser.parse_args(["summarize", "riunione", "--review"])
    assert cli.collect_cli_settings(args)["summary_review"] is True
    args = parser.parse_args(["summarize", "riunione"])
    assert cli.collect_cli_settings(args)["summary_review"] is None


def test_the_output_option_settles_the_flags_under_it():
    """One option that says what the run is for, as in the two graphical
    front ends, instead of a command line that lists the flags adding up to
    it."""
    from audio_transcriber.config import resolve

    parser = cli.build_parser(dict(DEFAULTS))
    args = parser.parse_args(["transcribe", "a.wav", "--output", "speakers"])
    settings = resolve(cli.collect_cli_settings(args), {})
    assert settings["diarize"] is True
    assert settings["subtitles"] is None

    args = parser.parse_args(["transcribe", "a.wav", "--output", "text",
                              "--diarize", "--srt"])
    settings = resolve(cli.collect_cli_settings(args), {})
    assert settings["diarize"] is False
    assert settings["subtitles"] is None


def test_an_unknown_output_is_refused_by_the_parser(capsys):
    parser = cli.build_parser(dict(DEFAULTS))
    with pytest.raises(SystemExit):
        parser.parse_args(["transcribe", "a.wav", "--output", "karaoke"])
    assert "karaoke" in capsys.readouterr().err


# --- transcribing, with the engine stubbed out ----------------------------

@pytest.fixture
def fake_engine(monkeypatch):
    """Replace the transcription engine: the CLI plumbing is what is tested.

    The prompt the backend receives is recorded, because that is how the
    keyword sets are supposed to reach it."""
    from audio_transcriber import pipeline

    seen = {}

    def transcribe(audio, model, language, device, **options):
        seen.update(options, model=model, language=language)
        return ([{"text": "buongiorno a tutti", "start": 0.0, "end": 2.0}],
                "buongiorno a tutti",
                {"backend": "fake", "device": "CPU", "model": model, "model_dir": ""})

    monkeypatch.setattr(pipeline, "load_audio", lambda source: object())
    monkeypatch.setattr(pipeline, "duration_seconds", lambda audio: 12.0)
    monkeypatch.setattr(pipeline, "transcribe", transcribe)
    return seen


def test_a_transcription_writes_a_text_file_next_to_the_input(fake_engine, tmp_path):
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"x")
    cli.main([str(source)])
    assert (tmp_path / "meeting.txt").read_text(encoding="utf-8").strip() == "buongiorno a tutti"


def test_a_keyword_set_reaches_the_engine_as_the_prompt(fake_engine, tmp_path):
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"x")
    cli.main([str(source), "--vocab", "iso27001-it"])
    assert "piano di trattamento dei rischi" in fake_engine["prompt"]


def test_several_sets_and_an_inline_prompt_are_combined(fake_engine, tmp_path):
    directory = paths.ensure(paths.vocabularies_dir())
    for name, body in (("one", "alpha"), ("two", "beta")):
        with open(f"{directory}/{name}.txt", "w", encoding="utf-8") as handle:
            handle.write(body)
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"x")
    cli.main([str(source), "--vocab", "one,two", "--prompt", "gamma"])
    assert fake_engine["prompt"] == "alpha beta gamma"


def test_an_unknown_keyword_set_stops_the_run(fake_engine, tmp_path):
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"x")
    with pytest.raises(SystemExit) as error:
        cli.main([str(source), "--vocab", "nope"])
    assert "nope" in str(error.value)


def test_the_library_entry_records_the_sets_that_were_used(fake_engine, tmp_path):
    source = tmp_path / "meeting.wav"
    source.write_bytes(b"x")
    cli.main([str(source), "--library", "--vocab", "iso27001-it", "--title", "Weekly"])

    from audio_transcriber.library import Library
    entry = Library().entries()[0]
    assert entry.metadata["title"] == "Weekly"
    assert entry.metadata["transcription"]["vocabulary"] == ["iso27001-it"]
    assert entry.read_transcript().strip() == "buongiorno a tutti"


# --- the vocab command ----------------------------------------------------

def test_vocab_list_shows_the_bundled_set(capsys):
    cli.main(["vocab", "list"])
    output = capsys.readouterr().out
    assert "iso27001-it" in output and "bundled" in output


def test_vocab_new_then_show(capsys):
    cli.main(["vocab", "new", "my-terms", "--title", "My terms"])
    created = capsys.readouterr().out
    assert "my-terms.txt" in created
    cli.main(["vocab", "show", "my-terms"])
    assert "My terms" in capsys.readouterr().out


def test_vocab_new_can_start_from_an_existing_file(capsys, tmp_path):
    source = tmp_path / "terms.txt"
    source.write_text("alpha, beta\n", encoding="utf-8")
    cli.main(["vocab", "new", "client-x", "--from", str(source)])
    capsys.readouterr()
    cli.main(["vocab", "show", "client-x"])
    assert "alpha, beta" in capsys.readouterr().out


def test_vocab_path_without_a_name_prints_the_directory(capsys):
    cli.main(["vocab", "path"])
    assert capsys.readouterr().out.strip() == paths.vocabularies_dir()


def test_an_unknown_vocab_is_reported_not_traced():
    with pytest.raises(SystemExit) as error:
        cli.main(["vocab", "show", "nope"])
    assert "nope" in str(error.value)


# --- what the subtitle report says ----------------------------------------

def report(counts, measured=True, language="en"):
    from audio_transcriber.i18n import set_language
    set_language(language)
    from audio_transcriber.subtitles import preset
    cli.report_subtitle_problems(counts, preset("bbc"), measured=measured)


def test_the_report_is_written_out_not_left_as_message_keys(capsys):
    """Every remark has a sentence in the catalogue; a raw key on screen means
    one is missing."""
    report({"subtitles.too_fast": 38, "subtitles.too_short": 3})
    printed = capsys.readouterr().err
    assert "subtitles." not in printed
    assert "cli." not in printed
    assert "x38" in printed


def test_the_report_separates_the_speech_from_the_clock(capsys):
    report({"subtitles.too_fast": 38, "subtitles.too_short": 3,
            "subtitles.too_wide": 1})
    printed = capsys.readouterr().err
    assert "how fast people spoke" in printed
    assert "the times the engine reported" in printed
    assert "the program's own doing" in printed


def test_only_the_groups_with_something_in_them_are_printed(capsys):
    report({"subtitles.too_fast": 2})
    printed = capsys.readouterr().err
    assert "how fast people spoke" in printed
    assert "the times the engine reported" not in printed


def test_an_interpolated_clock_is_admitted_to(capsys):
    """Half the timing remarks rest on times nobody measured, and saying so is
    the difference between a report and a number."""
    report({"subtitles.too_short": 3}, measured=False)
    assert "interpolated" in capsys.readouterr().err


def test_nothing_is_said_about_the_clock_when_no_remark_depends_on_it(capsys):
    report({"subtitles.too_fast": 3}, measured=False)
    assert "interpolated" not in capsys.readouterr().err


def test_no_remarks_means_no_report(capsys):
    report({})
    assert capsys.readouterr().err == ""


def test_hardware_says_what_the_summary_would_load(capsys, monkeypatch):
    """The policy is arithmetic nobody can see; this makes it say so."""
    from audio_transcriber.summarizers import plan

    plan.forget()
    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    monkeypatch.setattr(plan, "available_ram_gb", lambda: 32.0)
    monkeypatch.setattr(plan, "total_ram_gb", lambda: 64.0)
    monkeypatch.setattr(plan, "physical_cores", lambda: 8)

    cli.main(["hardware"])
    output = capsys.readouterr().out
    assert "plan for this machine" in output
    assert "tier l" in output
    assert "context 16384" in output
    assert "cache f16/f16" in output
    plan.forget()


def test_hardware_says_when_no_model_would_fit(capsys, monkeypatch):
    from audio_transcriber.summarizers import plan

    plan.forget()
    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    monkeypatch.setattr(plan, "available_ram_gb", lambda: 0.8)
    monkeypatch.setattr(plan, "total_ram_gb", lambda: 2.0)
    monkeypatch.setattr(plan, "physical_cores", lambda: 2)

    cli.main(["hardware"])
    output = capsys.readouterr().out
    assert "no model fits" in output
    assert "quote the transcript" in output
    plan.forget()


# --- setup: what the installer asks --------------------------------------


@pytest.fixture
def a_machine(monkeypatch):
    """Set the installed RAM, the cores and AVX2 of the machine being asked."""
    from audio_transcriber import hardware

    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")

    def machine(ram, cores=8, avx2=True):
        monkeypatch.setattr(hardware, "total_ram_gb", lambda: ram)
        monkeypatch.setattr(hardware, "physical_cores", lambda: cores)
        monkeypatch.setattr(hardware, "has_avx2", lambda: avx2)
    return machine


def test_setup_check_passes_a_machine_suited_to_summaries(a_machine, capsys):
    a_machine(32.0)
    assert cli.main(["setup", "check"]) == cli.CHECK_OK
    said = capsys.readouterr().out
    assert "suitable" in said and "Spark-X2.5-4B" in said


def test_setup_check_warns_that_little_memory_means_a_small_model(a_machine, capsys):
    from audio_transcriber.summarizers import plan

    a_machine(4.0)
    assert cli.main(["setup", "check"]) == cli.CHECK_WARN
    said = capsys.readouterr().out
    assert "small one" in said
    assert f"{plan.ram_for('l', plan.LLAMACPP)} GB" in said


def test_setup_check_refuses_a_machine_no_model_fits_in(a_machine, capsys):
    a_machine(1.0)
    assert cli.main(["setup", "check"]) == cli.CHECK_NO
    assert "not suitable" in capsys.readouterr().out


def test_setup_check_warns_about_a_slow_processor(a_machine, capsys):
    a_machine(32.0, cores=2, avx2=False)
    assert cli.main(["setup", "check"]) == cli.CHECK_WARN
    said = capsys.readouterr().out
    assert "2 cores" in said and "no AVX2" in said
    assert "suitable" not in said


def test_setup_summary_needs_the_engine_first(a_machine, monkeypatch):
    from audio_transcriber import summarizers

    a_machine(32.0)
    monkeypatch.setattr(summarizers, "is_installed", lambda name, settings=None: False)
    with pytest.raises(SystemExit) as raised:
        cli.main(["setup", "summary"])
    assert "llamacpp" in str(raised.value)


def test_setup_summary_fetches_the_model_for_the_whole_machine(a_machine, monkeypatch):
    """Chosen from the installed memory, not from what is open right now."""
    from audio_transcriber import summarizers
    from audio_transcriber.summarizers import llamacpp, plan

    a_machine(32.0)
    monkeypatch.setattr(plan, "available_ram_gb", lambda: 1.0)
    monkeypatch.setattr(summarizers, "is_installed", lambda name, settings=None: True)
    fetched = []
    monkeypatch.setattr(llamacpp, "fetch",
                        lambda model, quant, models_dir=None: fetched.append((model.name, quant)))
    assert cli.main(["setup", "summary"]) == 0
    assert fetched == [("Spark-X2.5-4B", "Q8_0")]


def test_setup_choose_answers_with_what_was_chosen(a_machine, monkeypatch, capsys):
    a_machine(32.0)
    answers = iter(["", "3", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert cli.main(["setup", "choose"]) == cli.CHOSE_SUMMARY
    said = capsys.readouterr().out
    assert "1  transcription only" in said and "2  transcription and summaries" in said


def test_setup_choose_does_not_offer_summaries_where_no_model_fits(
        a_machine, monkeypatch, capsys):
    """Nothing to choose: llama.cpp for a model that cannot be downloaded."""
    a_machine(1.0)
    monkeypatch.setattr("builtins.input",
                        lambda prompt="": pytest.fail("it asked anyway"))
    assert cli.main(["setup", "choose"]) == cli.CHOSE_TRANSCRIPTION
    assert "only transcription is installed" in capsys.readouterr().out


def test_setup_choose_without_a_keyboard_installs_the_light_one(a_machine, monkeypatch):
    a_machine(32.0)

    def no_keyboard(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", no_keyboard)
    assert cli.main(["setup", "choose"]) == cli.CHOSE_TRANSCRIPTION


# --- the NVIDIA card, for the installer and the report --------------------


@pytest.mark.parametrize(("state", "extras"), [
    ("usable", "cuda,gui,record"),
    ("old_driver", "openvino,gui,record"),
    ("old_gpu", "openvino,gui,record"),
    ("absent", "openvino,gui,record"),
])
def test_setup_extras_installs_cuda_only_for_a_card_it_can_use(state, extras):
    from audio_transcriber import hardware

    assert cli.setup_extras(hardware.CudaProbe(state)) == extras


def test_setup_extras_prints_one_line_for_the_installer(capsys, monkeypatch):
    from audio_transcriber import hardware

    assert cli.main(["setup", "extras"]) == 0
    assert capsys.readouterr().out == cli.EXTRAS_DEFAULT + "\n"
    monkeypatch.setattr(hardware, "cuda_probe",
                        lambda: hardware.CudaProbe(hardware.CUDA_USABLE))
    assert cli.main(["setup", "extras"]) == 0
    assert capsys.readouterr().out == cli.EXTRAS_NVIDIA + "\n"


@pytest.fixture
def a_card(monkeypatch):
    from audio_transcriber import hardware

    monkeypatch.setenv("AUDIO_TRANSCRIBER_LANG", "en")
    monkeypatch.setattr(hardware, "opencl_too_old", lambda: True)

    def card(state, **found):
        monkeypatch.setattr(hardware, "cuda_probe",
                            lambda: hardware.CudaProbe(state, **found))
    return card


def test_a_usable_card_is_reported_and_an_old_opencl_is_beside_the_point(a_card, capsys):
    a_card("usable", name="RTX 3060", vram_gb=12.0, capability=(8, 6), driver=12080)
    cli.print_graphics()
    said = capsys.readouterr().out
    assert "RTX 3060, 12.0 GB" in said and "CUDA 12.8" in said
    assert "OpenCL" not in said


def test_an_old_driver_says_what_to_update(a_card, capsys):
    a_card("old_driver", name="RTX 5070", capability=(12, 0), driver=12040)
    cli.print_graphics()
    said = capsys.readouterr().out
    assert "CUDA 12.4" in said and "CUDA 12.8" in said and "setup.cmd" in said
    assert "OpenCL" in said


def test_an_old_card_says_where_the_build_starts(a_card, capsys):
    a_card("old_gpu", name="GTX 780", capability=(3, 5), driver=12020)
    cli.print_graphics()
    said = capsys.readouterr().out
    assert "3.5" in said and "5.3" in said


def test_no_card_says_nothing_about_nvidia(a_card, capsys):
    a_card("absent")
    cli.print_graphics()
    assert "NVIDIA" not in capsys.readouterr().out
