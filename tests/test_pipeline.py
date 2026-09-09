"""One run end to end, with the engine replaced.

The point of these is the *shape* of a run: which stages are reported, in what
order, and that the percentage only ever goes forwards. A transcription is one
long blocking call on a machine with a model on it; none of that is needed to
check that the bar and the stage names behave, and this suite has to stay a
few seconds long."""
import numpy as np
import pytest

from audio_transcriber import pipeline

SETTINGS = {"model": "small", "language": "it", "backend": "faster-whisper",
            "device": "auto", "para_gap": 1.2, "para_max_chars": 600,
            "prompt": "", "prompt_file": None, "vocabulary": None,
            "vocab_dir": None, "keep_fillers": False, "diarize": False}

# Not a greeting: cleaning.py drops the phrases Whisper hallucinates over
# silence, and "buongiorno a tutti" is one of them - correctly.
SEGMENTS = [{"text": "Primo punto all'ordine del giorno.", "start": 0.0, "end": 2.0},
            {"text": "Il budget e' approvato.", "start": 61.5, "end": 65.0}]


@pytest.fixture
def engine(monkeypatch):
    """A transcribe() that reports its own progress like faster-whisper does."""
    calls = {}

    def fake_transcribe(audio, model, language, device, progress=None, **kwargs):
        calls["kwargs"] = kwargs
        if progress:
            progress(0, "stage.loading_model")
            for percent in (10, 50, 100):
                progress(percent)
        return SEGMENTS, "Primo punto all'ordine del giorno.", {
            "backend": "faster-whisper", "device": "CPU", "model": model}

    monkeypatch.setattr(pipeline, "load_audio",
                        lambda source: np.zeros(16000, dtype=np.float32))
    monkeypatch.setattr(pipeline, "duration_seconds", lambda audio: 1.0)
    monkeypatch.setattr(pipeline, "transcribe", fake_transcribe)
    return calls


def collect(**settings):
    """Run, and return the ``(percent, stage)`` pairs reported."""
    reported = []
    result = pipeline.run("meeting.wav", dict(SETTINGS, **settings),
                          progress=lambda percent, stage=None:
                          reported.append((percent, stage)))
    return result, reported


# --- the bar and the stages -----------------------------------------------

def test_the_stages_before_the_engine_are_reported(engine):
    """Decoding a two-gigabyte video and loading a model are minutes in which
    the bar used to sit at nothing."""
    _result, reported = collect()
    stages = [stage for _percent, stage in reported]
    assert stages[:3] == ["stage.starting", "stage.decoded", "stage.transcribing"]
    assert "stage.loading_model" in stages
    assert stages[-1] == "stage.laying_out"


def test_the_percentage_only_goes_forwards(engine):
    """The engine counts its own audio from zero. Passed straight through, that
    would send the bar back to the start the moment the model was up."""
    _result, reported = collect()
    percentages = [percent for percent, _stage in reported]
    assert percentages == sorted(percentages)
    assert percentages[0] >= 1
    assert percentages[-1] == pipeline.ENGINE_BAND[1]


def test_the_engines_progress_lands_inside_its_own_band(engine):
    """Half of the transcription is halfway between the band's ends, not
    halfway across the bar: there is work before it and after it."""
    _result, reported = collect()
    low, high = pipeline.ENGINE_BAND
    middle = next(percent for percent, stage in reported
                  if stage == "stage.transcribing" and percent > low)
    assert middle == pytest.approx(low + (high - low) * 0.10, abs=1)


def test_diarization_gets_a_band_of_its_own(engine, monkeypatch):
    """It runs after the transcription and takes about as long again, so the
    engine cannot be allowed to fill the whole bar first."""
    monkeypatch.setattr(pipeline, "diarization_assets", lambda settings: (None, None))
    monkeypatch.setattr(pipeline, "diarize",
                        lambda *args, **kwargs: [(0.0, 2.0, "SPEAKER_00")])
    monkeypatch.setattr(pipeline, "assign_speakers", lambda segments, turns: segments)
    monkeypatch.setattr(pipeline, "format_dialogue", lambda segments: "SPEAKER_00: hi")

    _result, reported = collect(diarize=True)
    stages = [stage for _percent, stage in reported]
    assert "stage.diarizing" in stages
    engine_top = max(percent for percent, stage in reported
                     if stage == "stage.transcribing")
    assert engine_top <= pipeline.ENGINE_BAND_WITH_DIARIZATION[1]
    assert max(percent for percent, _stage in reported) == pipeline.DIARIZATION_BAND[1]


# --- subtitles ------------------------------------------------------------

def test_which_subtitle_formats_were_asked_for():
    assert pipeline.subtitle_formats({}) == []
    assert pipeline.subtitle_formats({"subtitles": "srt"}) == ["srt"]
    assert pipeline.subtitle_formats({"subtitles": "srt,vtt"}) == ["srt", "vtt"]
    assert pipeline.subtitle_formats({"subtitles": " .SRT  vtt "}) == ["srt", "vtt"]
    assert pipeline.subtitle_formats({"subtitles": ["vtt"]}) == ["vtt"]


def test_an_unknown_subtitle_format_is_refused():
    from audio_transcriber.subtitles import SubtitleError

    with pytest.raises(SubtitleError):
        pipeline.subtitle_formats({"subtitles": "ass"})


def test_the_settings_numbers_are_applied_over_the_preset():
    spec = pipeline.subtitle_spec({"subtitle_preset": "bbc",
                                   "subtitle_chars": 30,
                                   "subtitle_words": 8})
    assert spec["name"] == "bbc"
    assert spec["max_chars_per_line"] == 30          # overridden
    assert spec["max_chars_per_second"] == 14        # the preset's own
    assert spec["max_words_per_cue"] == 8


def test_the_engine_is_asked_for_word_timings_only_when_subtitles_are_wanted(engine):
    """They make a cut fall where the speaker paused instead of being
    interpolated, and they cost time, so they are not asked for otherwise."""
    pipeline.run("meeting.wav", dict(SETTINGS))
    assert engine["kwargs"]["word_timestamps"] is False
    pipeline.run("meeting.wav", dict(SETTINGS, subtitles="srt"))
    assert engine["kwargs"]["word_timestamps"] is True


def test_subtitles_are_written_into_the_entry_when_asked(engine, tmp_path):
    from audio_transcriber.library import Library

    library = Library(str(tmp_path / "library"))
    result = pipeline.run("meeting.wav", dict(SETTINGS, subtitles="srt,vtt"))
    entry = library.create(title="Comitato")
    written, cues, problems = pipeline.write_subtitles(
        entry, result, dict(SETTINGS, subtitles="srt,vtt"))
    assert written == ["srt", "vtt"]
    assert cues and entry.subtitles() == ["srt", "vtt"]
    with open(entry.subtitle_path("srt"), encoding="utf-8") as handle:
        assert " --> " in handle.read()
    assert isinstance(problems, list)


def test_nothing_is_written_when_no_format_was_asked_for(engine, tmp_path):
    """The cues are always available; saving them is the option."""
    from audio_transcriber.library import Library

    library = Library(str(tmp_path / "library"))
    result = pipeline.run("meeting.wav", dict(SETTINGS))
    entry = library.create(title="Comitato")
    assert pipeline.write_subtitles(entry, result, dict(SETTINGS)) == ([], [], [])
    assert entry.subtitles() == []
    assert pipeline.subtitles_of(result, dict(SETTINGS))       # still computable


# --- the callback contract ------------------------------------------------

def test_a_callback_that_only_wants_the_number_still_works(engine):
    """The web interface asks for a percentage and nothing else."""
    seen = []
    pipeline.run("meeting.wav", dict(SETTINGS), progress=seen.append)
    assert seen and all(isinstance(percent, int) for percent in seen)


def test_no_callback_at_all_is_fine(engine):
    """The command line prints its own progress and passes none."""
    result = pipeline.run("meeting.wav", dict(SETTINGS))
    assert result.text.startswith("Primo punto")


def test_scaling_maps_a_band_and_keeps_the_stage():
    reported = []
    scaled = pipeline.scale((10, 20), lambda percent, stage=None:
                            reported.append((percent, stage)), "stage.transcribing")
    scaled(0)
    scaled(50)
    scaled(100)
    scaled(140)                     # a backend that overshoots is clamped
    assert [percent for percent, _stage in reported] == [10, 15, 20, 20]
    assert {stage for _percent, stage in reported} == {"stage.transcribing"}


def test_an_empty_transcription_is_still_an_error(engine, monkeypatch):
    monkeypatch.setattr(pipeline, "transcribe",
                        lambda *args, **kwargs: ([], "   ", {"backend": "x",
                                                             "device": "CPU",
                                                             "model": "small"}))
    with pytest.raises(pipeline.EmptyTranscription):
        pipeline.run("meeting.wav", dict(SETTINGS))
