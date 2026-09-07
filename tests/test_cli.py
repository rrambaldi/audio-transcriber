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
