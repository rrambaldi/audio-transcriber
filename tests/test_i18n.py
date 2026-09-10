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
