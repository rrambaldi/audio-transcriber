"""The message catalogue and how the interface language is chosen."""
import pytest

from audio_transcriber import i18n


@pytest.fixture(autouse=True)
def reset_language(monkeypatch):
    monkeypatch.delenv(i18n.ENV_LANGUAGE, raising=False)
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    i18n._current = None
    yield
    i18n._current = None


def test_every_catalogue_defines_the_same_keys():
    """A key present in one language and missing in another is a silent bug."""
    reference = set(i18n.MESSAGES[i18n.DEFAULT_LANGUAGE])
    for language, catalogue in i18n.MESSAGES.items():
        assert set(catalogue) == reference, f"{language} is out of sync"


def test_placeholders_match_across_catalogues():
    """A translation that names a different placeholder would format wrongly."""
    import string

    def placeholders(text):
        return {name for _, name, _, _ in string.Formatter().parse(text) if name}

    for key, english in i18n.MESSAGES[i18n.DEFAULT_LANGUAGE].items():
        expected = placeholders(english)
        for language, catalogue in i18n.MESSAGES.items():
            assert placeholders(catalogue[key]) == expected, f"{language}:{key}"


def test_explicit_language_wins():
    assert i18n.set_language("it") == "it"
    assert "liberi su" in i18n.t("hardware.summary", cores=1, ram="1",
                                 total="2", openvino="-", cuda="-")


def test_locale_style_codes_are_accepted():
    assert i18n.set_language("it_IT.UTF-8") == "it"


def test_an_unknown_language_falls_back_without_raising(capsys):
    assert i18n.set_language("klingon") == i18n.DEFAULT_LANGUAGE
    assert "klingon" in capsys.readouterr().out


def test_the_environment_variable_is_used_when_no_option_is_given(monkeypatch):
    monkeypatch.setenv(i18n.ENV_LANGUAGE, "it")
    assert i18n.set_language(None) == "it"


def test_the_system_locale_is_the_next_fallback(monkeypatch):
    monkeypatch.setenv("LANG", "it_IT.UTF-8")
    assert i18n.set_language(None) == "it"


def test_an_unknown_locale_ends_up_in_english(monkeypatch):
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert i18n.set_language(None) == i18n.DEFAULT_LANGUAGE


def test_an_unknown_key_is_returned_verbatim():
    i18n.set_language("en")
    assert i18n.t("no.such.message") == "no.such.message"


def test_missing_placeholders_do_not_raise():
    i18n.set_language("en")
    assert i18n.t("hardware.summary")  # no kwargs at all
    assert i18n.t("hardware.summary", cores=1)  # only some of them


def test_every_interface_language_is_named_in_its_own_words():
    assert set(i18n.LANGUAGE_NAMES) == set(i18n.AVAILABLE_LANGUAGES)
    assert set(i18n.AVAILABLE_LANGUAGES) == {"en", "it", "fr", "de"}
    assert i18n.LANGUAGE_NAMES["de"] == "Deutsch"


def test_french_and_german_are_spoken():
    assert i18n.set_language("fr_FR.UTF-8") == "fr"
    assert i18n.t("gui.close") == i18n.MESSAGES["fr"]["gui.close"]
    assert i18n.set_language("de") == "de"
    assert i18n.t("gui.close") == i18n.MESSAGES["de"]["gui.close"]
    assert i18n.MESSAGES["de"]["gui.close"] != i18n.MESSAGES["en"]["gui.close"]


def test_a_request_can_speak_another_language_than_the_process():
    """A page read in German, on a server started in Italian: its request and
    its job answer in German, and nothing else does."""
    import threading

    i18n.set_language("it")
    with i18n.speaking("de"):
        assert i18n.language() == "de"
        elsewhere = []
        thread = threading.Thread(target=lambda: elsewhere.append(i18n.language()))
        thread.start()
        thread.join()
        assert elsewhere == ["it"]
    assert i18n.language() == "it"
    with i18n.speaking("xx"):
        assert i18n.language() == "it"
    with i18n.speaking(None):
        assert i18n.language() == "it"
