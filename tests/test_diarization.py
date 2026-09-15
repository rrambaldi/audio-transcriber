"""Finding the diarization models, and saying so when they cannot be found.

pyannote is a heavy optional extra and is not installed here, so what is
checked is everything that happens *before* it: which file or folder is going
to be used, whether the paths written inside a config lead anywhere, and what
is printed when they do not. The pipeline itself is a fake module, which is
enough to check that a hub failure comes out as one sentence rather than a
page of traceback.
"""
import os
import sys
import types

import pytest

from audio_transcriber import diarization, i18n, paths


@pytest.fixture(autouse=True)
def english(monkeypatch):
    monkeypatch.setenv(i18n.ENV_LANGUAGE, "en")
    i18n._current = None
    yield
    i18n._current = None


@pytest.fixture
def pyannote(monkeypatch):
    """A pyannote that imports, and whose Pipeline does what a test says."""
    loaded = {}

    class Pipeline:
        @staticmethod
        def from_pretrained(model, **kwargs):
            loaded["model"], loaded["kwargs"] = model, kwargs
            if isinstance(loaded.get("raises"), Exception):
                raise loaded["raises"]
            return "a pipeline"

    module = types.ModuleType("pyannote")
    audio = types.ModuleType("pyannote.audio")
    audio.Pipeline = Pipeline
    module.audio = audio
    monkeypatch.setitem(sys.modules, "pyannote", module)
    monkeypatch.setitem(sys.modules, "pyannote.audio", audio)
    return loaded


def write_config(directory, embedding, segmentation):
    """A pyannote 3.x config, the shape people write by hand."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "config.yaml")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("version: 3.1.0\n\npipeline:\n"
                     "  name: pyannote.audio.pipelines.SpeakerDiarization\n"
                     "  params:\n"
                     "    clustering: AgglomerativeClustering\n"
                     f"    embedding: {embedding}\n"
                     f"    segmentation: {segmentation}\n")
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def weights(directory, *names):
    """Model files, as heavy as the test needs them to be."""
    made = []
    for name in names:
        path = os.path.join(directory, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"weights")
        made.append(path)
    return made


# --- which file is the config ---------------------------------------------

def test_a_cloned_repository_is_named_by_its_directory(tmp_path):
    """pyannote 4 keeps the pipeline and its weights in one repository, and
    that folder is what the documentation says to hand over."""
    folder = tmp_path / "speaker-diarization-community-1"
    folder.mkdir()
    (folder / "config.yaml").write_text("version: 4.0.0\n")
    assert diarization.config_in(str(folder)) == str(folder / "config.yaml")


def test_a_config_file_is_itself(tmp_path):
    config = write_config(str(tmp_path / "diar"), "a/b.bin", "c/d.bin")
    assert diarization.config_in(config) == config


# --- where the paths inside it lead ---------------------------------------

def test_a_path_is_looked_for_beside_the_config_as_well(tmp_path):
    """pyannote reads them against the working directory, which is why a
    folder that is plainly there stops being found the moment the program is
    started from somewhere else."""
    folder = tmp_path / "pyannote-diar"
    weights(str(folder), "segmentation/pytorch_model.bin")
    found = diarization.resolve_reference("segmentation/pytorch_model.bin", str(folder))
    assert found == os.path.abspath(str(folder / "segmentation" / "pytorch_model.bin"))


def test_a_config_that_names_its_own_folder_is_understood(tmp_path):
    """The shape the tutorials produce: the paths include the folder itself,
    so they only work from the directory above it."""
    folder = tmp_path / "pyannote-diar"
    weights(str(folder), "embedding/pytorch_model.bin")
    found = diarization.resolve_reference("pyannote-diar/embedding/pytorch_model.bin",
                                          str(folder))
    assert found == os.path.abspath(str(folder / "embedding" / "pytorch_model.bin"))


def test_a_path_that_leads_nowhere_is_not_invented(tmp_path):
    assert diarization.resolve_reference("nothing/here.bin", str(tmp_path)) is None


def test_a_repo_id_is_left_for_pyannote_to_fetch(tmp_path):
    """'pyannote/segmentation-3.0' is not a folder that is missing."""
    content = "    embedding: pyannote/wespeaker-voxceleb-resnet34-LM\n"
    settled, missing = diarization.localise(content, str(tmp_path))
    assert missing == [] and settled == content


def test_relative_paths_are_settled_absolutely(tmp_path):
    folder = tmp_path / "pyannote-diar"
    weights(str(folder), "embedding/pytorch_model.bin", "segmentation/pytorch_model.bin")
    content = ("    embedding: pyannote-diar/embedding/pytorch_model.bin\n"
               "    segmentation: pyannote-diar/segmentation/pytorch_model.bin\n")
    settled, missing = diarization.localise(content, str(folder))

    assert missing == []
    assert str(folder / "embedding" / "pytorch_model.bin") in settled
    # the relative spelling is gone: every value now starts at the root
    assert "embedding: pyannote-diar/" not in settled


def test_what_is_really_missing_is_reported(tmp_path):
    content = "    embedding: gone/pytorch_model.bin\n"
    _settled, missing = diarization.localise(content, str(tmp_path))
    assert missing == [("embedding", "gone/pytorch_model.bin")]


# --- the pre-flight -------------------------------------------------------

def test_a_folder_of_models_passes_the_pre_flight(tmp_path, pyannote, capsys):
    """The case this exists for: everything downloaded by hand, in one folder,
    and the program started from anywhere at all."""
    folder = tmp_path / "pyannote-diar"
    weights(str(folder), "embedding/pytorch_model.bin", "segmentation/pytorch_model.bin")
    write_config(str(folder), "pyannote-diar/embedding/pytorch_model.bin",
                 "pyannote-diar/segmentation/pytorch_model.bin")

    diarization.check_diar_assets(str(folder), token=None)
    assert "pre-flight ok" in capsys.readouterr().out.lower()


def test_a_config_whose_files_are_gone_stops_before_the_long_wait(tmp_path, pyannote):
    config = write_config(str(tmp_path / "diar"), "gone/embedding.bin", "gone/seg.bin")
    with pytest.raises(SystemExit) as stopped:
        diarization.check_diar_assets(config, token=None)
    assert "gone/embedding.bin" in str(stopped.value)


def test_going_online_says_which_repository(tmp_path, pyannote, capsys):
    """The line that answers "why is it downloading anything at all?"."""
    diarization.check_diar_assets("pyannote/speaker-diarization-community-1",
                                  token="hf_xxx")
    assert "pyannote/speaker-diarization-community-1" in capsys.readouterr().out


def test_no_local_files_and_no_token_is_not_a_download(tmp_path, pyannote):
    with pytest.raises(SystemExit):
        diarization.check_diar_assets(str(tmp_path / "nothing" / "config.yaml"),
                                      token=None)


# --- loading it -----------------------------------------------------------

def test_a_local_folder_is_loaded_without_a_token(tmp_path, pyannote):
    folder = tmp_path / "community-1"
    folder.mkdir()
    (folder / "config.yaml").write_text("version: 4.0.0\n")

    assert diarization.load_pipeline(str(folder), token="hf_xxx") == "a pipeline"
    assert pyannote["model"] == str(folder)      # the directory, as it stands
    assert pyannote["kwargs"] == {}              # and nothing sent to the hub


def test_a_relative_config_is_handed_over_settled(tmp_path, pyannote, monkeypatch):
    """What pyannote receives has absolute paths in it, so where the program
    was started from stops mattering. The user's own file is not touched."""
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    folder = tmp_path / "pyannote-diar"
    weights(str(folder), "embedding/pytorch_model.bin", "segmentation/pytorch_model.bin")
    config = write_config(str(folder), "pyannote-diar/embedding/pytorch_model.bin",
                          "pyannote-diar/segmentation/pytorch_model.bin")
    original = read(config)

    diarization.load_pipeline(config, token=None)
    handed = read(pyannote["model"])

    assert pyannote["model"] != config
    assert str(folder / "embedding" / "pytorch_model.bin") in handed
    assert read(config) == original            # the user's own file, untouched


def test_a_config_that_is_already_absolute_is_handed_over_as_it_is(tmp_path, pyannote):
    folder = tmp_path / "diar"
    embedding, segmentation = weights(str(folder), "embedding.bin", "seg.bin")
    config = write_config(str(folder), embedding, segmentation)

    diarization.load_pipeline(config, token=None)
    assert pyannote["model"] == config


def test_a_refused_download_is_one_sentence_not_a_traceback(tmp_path, pyannote):
    """403 from the hub says "enable access to public gated repositories" and
    nothing about which of the two settings that is."""
    pyannote["raises"] = RuntimeError("403 Forbidden: gated repository")

    with pytest.raises(SystemExit) as stopped:
        diarization.load_pipeline("pyannote/speaker-diarization-community-1", "hf_x")

    message = str(stopped.value)
    assert "403 Forbidden" in message                      # what the hub said
    assert "gated repos" in message                        # and what to do
    assert "--diar-model" in message                       # or how to avoid it


# --- telling a repository from a folder -----------------------------------

@pytest.mark.parametrize("value", [
    "pyannote/speaker-diarization-community-1",
    "pyannote/speaker-diarization-3.1",
    "pyannote/wespeaker-voxceleb-resnet34-LM",
])
def test_a_repo_id_is_not_a_missing_file(value):
    """It has a slash in it, and for a while that was enough to have it
    treated as a path that did not exist - and silently replaced by the
    default pipeline, which is not the model that was asked for."""
    assert diarization.looks_like_path(value) is False


@pytest.mark.parametrize("value", [
    "pyannote-diar/config.yaml",
    "pyannote-diar/embedding/pytorch_model.bin",
    "C:\\Users\\someone\\pyannote-diar",
    "/opt/models/pyannote-diar",
    "./pyannote-diar",
    "pyannote-diar",
])
def test_a_path_is_recognised_however_it_is_written(value):
    assert diarization.looks_like_path(value) is True


def test_the_model_asked_for_is_the_model_used(capsys):
    """A repo id that is not on this disk is not a missing file: it goes to
    the hub as it stands, rather than being swapped for the default."""
    asked = "pyannote/speaker-diarization-community-1"
    assert diarization.resolve_model(asked) == asked
    assert capsys.readouterr().out == ""


def test_a_local_config_that_is_not_there_falls_back_out_loud(tmp_path, capsys):
    gone = str(tmp_path / "pyannote-diar" / "config.yaml")
    assert diarization.resolve_model(gone) == diarization.DEFAULT_PIPELINE
    assert gone in capsys.readouterr().out


# --- the shapes a real config comes in ------------------------------------

REAL_CONFIG = """version: 3.1.0

pipeline:
  name: pyannote.audio.pipelines.SpeakerDiarization
  params:
    clustering: AgglomerativeClustering
    embedding: pyannote-diar/wespeaker-voxceleb-resnet34-LM/pytorch_model.bin
    embedding_batch_size: 32
    embedding_exclude_overlap: true
    segmentation: pyannote-diar/segmentation-3.0/pytorch_model.bin
    segmentation_batch_size: 32

params:
  clustering:
    method: centroid
    min_cluster_size: 12
    threshold: 0.7045654963945799
  segmentation:
    min_duration_off: 0.0
"""


def test_a_tuning_block_is_not_a_missing_model(tmp_path):
    """'segmentation:' appears twice in a real config: once as a model and
    once as a block of numbers. A pattern that let whitespace cross a line
    read the number below it as the file name and stopped the run."""
    folder = tmp_path / "pyannote-diar"
    weights(str(folder), "wespeaker-voxceleb-resnet34-LM/pytorch_model.bin",
            "segmentation-3.0/pytorch_model.bin")
    _settled, missing = diarization.localise(REAL_CONFIG, str(folder))

    assert missing == []
    keys = [key for key, _value in diarization.config_references(REAL_CONFIG)]
    assert keys == ["embedding", "segmentation"]        # and not the numbers


def test_a_cloned_repository_keeps_its_own_way_of_reading_itself(tmp_path, pyannote):
    """Everything beside the config: that is the 4.x layout, and pyannote
    resolves it on its own - it may refer to more than the two keys read
    here, so the folder is handed over untouched."""
    folder = tmp_path / "community-1"
    weights(str(folder), "embedding/pytorch_model.bin", "segmentation/pytorch_model.bin")
    write_config(str(folder), "embedding/pytorch_model.bin",
                 "segmentation/pytorch_model.bin")

    assert diarization.localised_config(str(folder)) == str(folder)


def test_a_folder_whose_config_points_elsewhere_is_settled(tmp_path, pyannote, monkeypatch):
    """The hand-made case: paths written as 'pyannote-diar/...', which only
    resolve from the directory above. Handed to pyannote as they are, from
    anywhere else, they find nothing."""
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    folder = tmp_path / "pyannote-diar"
    weights(str(folder), "wespeaker-voxceleb-resnet34-LM/pytorch_model.bin",
            "segmentation-3.0/pytorch_model.bin")
    with open(os.path.join(str(folder), "config.yaml"), "w", encoding="utf-8") as handle:
        handle.write(REAL_CONFIG)

    handed = diarization.localised_config(str(folder))
    assert handed != str(folder)
    assert str(folder / "segmentation-3.0" / "pytorch_model.bin") in read(handed)


# --- a folder that has been moved or renamed ------------------------------

def test_a_folder_renamed_since_its_config_was_written_still_resolves(tmp_path):
    """Dropped into the managed 'diarization' directory, say, while the
    config still calls it 'pyannote-diar'. The tail is what identifies the
    file; the folders in front of it are where it used to live."""
    folder = tmp_path / "diarization"
    weights(str(folder), "segmentation-3.0/pytorch_model.bin")
    found = diarization.resolve_reference(
        "pyannote-diar/segmentation-3.0/pytorch_model.bin", str(folder))
    assert found == os.path.abspath(
        str(folder / "segmentation-3.0" / "pytorch_model.bin"))


def test_a_windows_path_in_a_config_read_on_linux_is_still_a_path(tmp_path):
    folder = tmp_path / "diarization"
    weights(str(folder), "embedding/pytorch_model.bin")
    found = diarization.resolve_reference(
        "pyannote-diar\\embedding\\pytorch_model.bin", str(folder))
    assert found == os.path.abspath(str(folder / "embedding" / "pytorch_model.bin"))


def test_the_tail_has_to_match_and_is_not_guessed_at(tmp_path):
    """A file that was meant, or nothing: never the nearest thing to hand."""
    folder = tmp_path / "diarization"
    weights(str(folder), "segmentation-3.0/pytorch_model.bin")
    assert diarization.resolve_reference(
        "pyannote-diar/segmentation-3.0/model.safetensors", str(folder)) is None


def test_what_is_missing_is_named_next_to_what_is_there(tmp_path, pyannote):
    """"The config references files that do not exist" is a dead end on its
    own: the names that *are* in that folder are the half that says what to
    do about it."""
    folder = tmp_path / "diar"
    weights(str(folder), "segmentation/pytorch_model.bin")
    config = write_config(str(folder), "elsewhere/embedding.bin",
                          "elsewhere/segmentation.bin")

    with pytest.raises(SystemExit) as stopped:
        diarization.check_diar_assets(config, token=None)

    message = str(stopped.value)
    assert "elsewhere/embedding.bin" in message           # what it asked for
    assert os.path.join("segmentation", "pytorch_model.bin") in message   # what is there


def test_a_folder_with_no_models_in_it_says_that_much(tmp_path, pyannote):
    folder = tmp_path / "diar"
    config = write_config(str(folder), "a/b.bin", "c/d.bin")

    with pytest.raises(SystemExit) as stopped:
        diarization.check_diar_assets(config, token=None)
    assert "not in that folder at all" in str(stopped.value)
