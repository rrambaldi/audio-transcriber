"""Named keyword sets: naming rules, shadowing, and the prompt they produce."""
import pytest

from audio_transcriber import paths, vocabularies
from audio_transcriber.config import ConfigError, read_prompt


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))


def write(directory, name, body):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.txt").write_text(body, encoding="utf-8")
    return directory / f"{name}.txt"


# --- the file format ------------------------------------------------------

def test_comments_are_dropped_and_whitespace_collapsed():
    assert vocabularies.parse("# a comment\nasset,\n  risk\n\n") == "asset, risk"


def test_the_header_carries_the_title_and_the_language():
    data = vocabularies.metadata("# title: ISO 27001\n# language: it\nasset")
    assert data == {"title": "ISO 27001", "language": "it"}


def test_the_header_stops_at_the_first_real_line():
    data = vocabularies.metadata("asset\n# title: too late")
    assert data == {}


def test_terms_separated_by_commas_survive_being_wrapped():
    assert vocabularies.terms("# x\nasset, risk treatment\nplan, threat.") == [
        "asset", "risk treatment plan", "threat"]


def test_one_term_per_line_is_understood_too():
    assert vocabularies.terms("# x\nasset\nrisk treatment plan\n") == [
        "asset", "risk treatment plan"]


# --- names ----------------------------------------------------------------

@pytest.mark.parametrize("name", ["iso27001-it", "my_terms", "a", "x1"])
def test_valid_names(name):
    assert vocabularies.valid_name(name)


@pytest.mark.parametrize("name", ["", "../etc/passwd", "a/b", "Upper", "-lead", ".hidden",
                                  "with space", "x" * 65])
def test_a_name_that_could_walk_out_of_the_directory_is_refused(name):
    assert not vocabularies.valid_name(name)
    with pytest.raises(vocabularies.VocabularyError):
        vocabularies.get(name)


def test_a_title_becomes_a_usable_name():
    assert vocabularies.normalise_name("ISO 27001 (Italiano)!") == "iso-27001-italiano"


# --- discovery ------------------------------------------------------------

def test_the_bundled_set_is_available_out_of_the_box():
    names = [item.name for item in vocabularies.available()]
    assert "iso27001-it" in names
    assert vocabularies.get("iso27001-it").source == vocabularies.SOURCE_BUNDLED


def test_a_user_set_shadows_a_bundled_one_of_the_same_name(tmp_path):
    write(tmp_path / "home" / "config" / "vocabularies", "iso27001-it", "mine only")
    item = vocabularies.get("iso27001-it")
    assert item.source == vocabularies.SOURCE_USER
    assert item.text == "mine only"


def test_an_extra_directory_comes_first(tmp_path):
    extra = tmp_path / "shared"
    write(extra, "iso27001-it", "shared version")
    assert vocabularies.get("iso27001-it", str(extra)).text == "shared version"


def test_files_that_are_not_valid_sets_are_ignored(tmp_path):
    directory = tmp_path / "home" / "config" / "vocabularies"
    write(directory, "Ok", "x")            # capital letter: not a valid name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "notes.md").write_text("x", encoding="utf-8")
    names = [item.name for item in vocabularies.available()]
    assert "Ok" not in names and "notes" not in names
    assert "iso27001-it" in names          # the bundled ones are still there


def test_an_unknown_set_lists_what_is_available():
    with pytest.raises(vocabularies.VocabularyError) as error:
        vocabularies.get("nope")
    assert "iso27001-it" in str(error.value)


# --- selecting several ----------------------------------------------------

def test_names_arrive_as_a_list_a_string_or_a_mix():
    assert vocabularies.split_names("a, b") == ["a", "b"]
    assert vocabularies.split_names(["a", "b,c"]) == ["a", "b", "c"]
    assert vocabularies.split_names(["a", "a"]) == ["a"]
    assert vocabularies.split_names(None) == []


def test_several_sets_are_concatenated_in_order(tmp_path):
    directory = tmp_path / "home" / "config" / "vocabularies"
    write(directory, "one", "alpha")
    write(directory, "two", "beta")
    assert vocabularies.load(["two", "one"]) == "beta alpha"


# --- creating -------------------------------------------------------------

def test_creating_a_set_writes_it_where_the_user_can_find_it():
    path = vocabularies.create("mine", vocabularies.template("mine", "My terms", "it"))
    assert path.startswith(paths.vocabularies_dir())
    assert vocabularies.get("mine").title == "My terms"


def test_creating_refuses_to_overwrite_unless_asked():
    vocabularies.create("mine", "a")
    with pytest.raises(vocabularies.VocabularyError):
        vocabularies.create("mine", "b")
    vocabularies.create("mine", "b", overwrite=True)
    assert vocabularies.get("mine").text == "b"


def test_creating_refuses_an_invalid_name():
    with pytest.raises(vocabularies.VocabularyError):
        vocabularies.create("../escape", "a")


# --- how it reaches the transcription -------------------------------------

def test_the_prompt_is_the_sets_then_the_inline_text(tmp_path):
    directory = tmp_path / "home" / "config" / "vocabularies"
    write(directory, "one", "alpha")
    assert read_prompt("beta", None, ["one"]) == "alpha beta"


def test_a_prompt_file_still_wins_over_an_inline_prompt(tmp_path):
    source = tmp_path / "words.txt"
    source.write_text("# comment\nfrom the file\n", encoding="utf-8")
    assert read_prompt("inline", str(source)) == "from the file"


def test_an_unknown_set_stops_the_run_with_a_configuration_error():
    with pytest.raises(ConfigError):
        read_prompt("", None, ["nope"])


def test_no_vocabulary_at_all_is_the_empty_prompt():
    assert read_prompt("", None, None) == ""


# --- the sets shipped with the package ------------------------------------

def bundled():
    import os

    from audio_transcriber.vocabularies import BUNDLED_DIR, Vocabulary

    return [Vocabulary(name[:-4], os.path.join(BUNDLED_DIR, name), "bundled")
            for name in sorted(os.listdir(BUNDLED_DIR)) if name.endswith(".txt")]


def test_the_bundled_sets_are_well_formed():
    """They are data, so nothing but a test keeps them honest."""
    for item in bundled():
        assert vocabularies.valid_name(item.name), item.name
        assert vocabularies.metadata(item.raw).get("title"), f"{item.name}: no title"
        assert item.language, f"{item.name}: no language"
        assert len(vocabularies.terms(item.text)) >= 10, f"{item.name}: too few terms"
        assert len(item.text) <= vocabularies.MAX_PROMPT_CHARS // 2, (
            f"{item.name}: {len(item.text)} characters leaves no room for a second set")


def test_the_general_set_can_be_combined_with_any_other():
    """The point of a general set is to be added to a subject one; the pair has
    to fit in the prompt Whisper actually reads."""
    general = "riunione-generale-it"
    assert vocabularies.get(general)
    for item in bundled():
        if item.name == general:
            continue
        combined = vocabularies.load([general, item.name])
        assert len(combined) <= vocabularies.MAX_PROMPT_CHARS, item.name


def test_no_two_bundled_sets_share_a_title():
    titles = [item.title for item in bundled()]
    assert len(set(titles)) == len(titles)
