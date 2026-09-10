"""Configuration file, .env loading, and the option precedence rules."""
import pytest

from audio_transcriber import config, paths

VALID = """
[general]
language = "en"

[transcription]
model = "small"
threads = 4
vad = false

[output]
paragraph_gap = 2
"""


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)


def write_config(text):
    target = paths.config_file()
    paths.ensure(paths.config_dir())
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(text)
    return target


def test_a_missing_config_file_is_not_an_error():
    settings, path, warnings = config.load_config()
    assert (settings, path, warnings) == ({}, None, [])


def test_values_are_read_and_mapped_to_internal_names():
    write_config(VALID)
    settings, path, warnings = config.load_config()
    assert settings["language"] == "en"
    assert settings["model"] == "small"
    assert settings["threads"] == 4
    assert settings["vad"] is False
    assert settings["para_gap"] == 2.0        # an int is accepted where a float is due
    assert warnings == []
    assert path is not None


def test_an_unknown_option_warns_but_does_not_stop():
    write_config('[transcription]\nmodel = "small"\nnonsense = 1\n')
    settings, _, warnings = config.load_config()
    assert settings["model"] == "small"
    assert any("nonsense" in w for w in warnings)


def test_a_wrong_type_is_rejected_with_the_offending_key():
    write_config('[output]\nparagraph_gap = "slow"\n')
    with pytest.raises(config.ConfigError) as error:
        config.load_config()
    assert "paragraph_gap" in str(error.value)


def test_malformed_toml_is_rejected():
    write_config("this is not [[[ toml\n")
    with pytest.raises(config.ConfigError):
        config.load_config()


def test_precedence_is_cli_then_file_then_default():
    merged = config.resolve({"model": "tiny"}, {"model": "small", "language": "en"})
    assert merged["model"] == "tiny"          # command line wins
    assert merged["language"] == "en"         # file beats the default
    assert merged["para_gap"] == config.DEFAULTS["para_gap"]


def test_absent_cli_options_do_not_override_the_file():
    merged = config.resolve({"model": None}, {"model": "small"})
    assert merged["model"] == "small"


def test_dotenv_does_not_override_the_real_environment(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('HF_TOKEN="from-file"\nOTHER=from-file\n')
    monkeypatch.setenv("HF_TOKEN", "from-environment")
    monkeypatch.delenv("OTHER", raising=False)
    config.load_dotenv([str(env_file)])
    import os
    assert os.environ["HF_TOKEN"] == "from-environment"
    assert os.environ["OTHER"] == "from-file"


def test_prompt_file_is_read_with_comments_stripped(tmp_path):
    prompt = tmp_path / "vocab.txt"
    prompt.write_text("# a comment\nasset, control,\nthreat\n")
    assert config.read_prompt("", str(prompt)) == "asset, control, threat"


def test_prompt_file_beats_an_inline_prompt(tmp_path):
    prompt = tmp_path / "vocab.txt"
    prompt.write_text("from the file")
    assert config.read_prompt("inline", str(prompt)) == "from the file"


def test_a_missing_prompt_file_is_reported():
    with pytest.raises(config.ConfigError):
        config.read_prompt("", "/nonexistent/vocabulary.txt")


def test_every_schema_entry_has_a_default():
    for _, (name, _) in config.SCHEMA.items():
        assert name in config.DEFAULTS


def test_the_default_model_is_worked_out_from_the_machine():
    """Shipping 'large-v3' as the default hands a 3 GB server a model that does
    not fit; the machine decides instead."""
    from audio_transcriber.transcription import AUTO
    assert config.DEFAULTS["model"] == AUTO


# --- what the run is for --------------------------------------------------

def test_the_chosen_output_settles_the_flags_that_produce_it():
    """The three interfaces have to agree on what "subtitles" means, so the
    choice is turned into flags in one place."""
    text = config.resolve_output({"output": "text", "diarize": True,
                                  "subtitles": "srt"})
    assert text["diarize"] is False and text["subtitles"] is None

    speakers = config.resolve_output({"output": "speakers", "diarize": False,
                                      "subtitles": "srt"})
    assert speakers["diarize"] is True and speakers["subtitles"] is None

    subs = config.resolve_output({"output": "subtitles"})
    assert subs["subtitles"] == "srt"        # an unsaved subtitle is not an output


def test_marking_the_speakers_stays_optional_in_subtitles():
    """It is a second decision, not part of choosing subtitles."""
    plain = config.resolve_output({"output": "subtitles", "diarize": False})
    marked = config.resolve_output({"output": "subtitles", "diarize": True,
                                    "subtitles": "srt,vtt"})
    assert plain["diarize"] is False
    assert marked["diarize"] is True and marked["subtitles"] == "srt,vtt"


def test_no_output_chosen_leaves_every_flag_alone():
    """A config.toml written before this existed has to keep working."""
    before = {"diarize": True, "subtitles": "vtt"}
    assert config.resolve_output(dict(before)) == before
    assert config.resolve_output({"output": "nonsense", **before}) == \
        {"output": "nonsense", **before}


def test_resolve_settles_the_output_as_well():
    settings = config.resolve({"output": "speakers"}, {"diarize": False})
    assert settings["diarize"] is True


def test_the_summary_plan_can_be_pinned_from_the_file():
    """For a controlled deployment, or to reproduce somebody else's result."""
    write_config('[summary]\n'
                 'tier = "s"\n'
                 'context_tokens = 4096\n'
                 'kv_type = "q8_0/q4_0"\n'
                 'reduce_fanin = 4\n'
                 'llama_server = "/opt/llama.cpp/llama-server"\n')
    settings, _, warnings = config.load_config()
    assert settings["summary_tier"] == "s"
    assert settings["summary_context_tokens"] == 4096
    assert settings["summary_kv_type"] == "q8_0/q4_0"
    assert settings["summary_reduce_fanin"] == 4
    assert settings["summary_llama_server"].endswith("llama-server")
    assert warnings == []


def test_a_summary_key_of_the_wrong_type_is_refused():
    write_config('[summary]\ncontext_tokens = "big"\n')
    with pytest.raises(config.ConfigError) as raised:
        config.load_config()
    assert "context_tokens" in str(raised.value)


def test_a_misspelled_summary_key_warns_like_any_other():
    write_config('[summary]\nkv_typo = "q8_0"\n')
    _, _, warnings = config.load_config()
    assert any("kv_typo" in warning for warning in warnings)


def test_every_summary_default_has_a_place_in_the_file():
    """A setting nobody can write in config.toml is a setting nobody has."""
    written = {name for (_, _), (name, _) in config.SCHEMA.items()}
    for name in config.DEFAULTS:
        if name.startswith("summary"):
            assert name in written, name
