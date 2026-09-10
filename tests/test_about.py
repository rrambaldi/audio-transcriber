"""The facts an About box shows, and where the licence is found.

Two front ends draw that box and neither can reach the licence on its own: a
wheel does not carry the repository, and an installed copy keeps the file in
its ``dist-info``. So the looking-up is one module's job, and what is checked
here is that it looks in both places, that it says so honestly when there is
nothing to read, and that what it reports about the bundled typefaces matches
the files actually on disk.
"""
import os

import pytest

from audio_transcriber import __version__, about, branding


@pytest.fixture(autouse=True)
def uncached():
    """The licence is read once and kept, which is right for a running
    program and wrong between two tests that patch where it lives."""
    about.licence_text.cache_clear()
    yield
    about.licence_text.cache_clear()


def test_the_licence_is_found_in_a_checkout():
    """How anybody working on the program runs it: no dist-info anywhere."""
    path = about.licence_path()

    assert path and os.path.exists(path)
    assert os.path.basename(path) == about.FILENAME


def test_the_installed_copy_is_preferred_over_the_checkout(monkeypatch, tmp_path):
    """A wheel's own file wins, because that is the copy being run - and it
    is the one whose licence the user actually received."""
    installed = tmp_path / "LICENSE"
    installed.write_text("INSTALLED\n\nPermission is hereby granted", encoding="utf-8")
    monkeypatch.setattr(about, "_installed_path", lambda: str(installed))

    assert about.licence_path() == str(installed)
    assert about.licence_text().startswith("INSTALLED")


def test_a_copy_with_no_licence_file_says_so_instead_of_failing(monkeypatch):
    """The licence is data, like the icons: a build that lost it must still
    run, and the front ends have a sentence for the case."""
    monkeypatch.setattr(about, "_installed_path", lambda: None)
    monkeypatch.setattr(about, "_CHECKOUT", "/nowhere/LICENSE")

    assert about.licence_path() is None
    assert about.licence_text() is None
    # And the title falls back to the expression, which is a true answer.
    assert about.licence_title() == about.SPDX
    facts = about.facts()
    assert facts["licence_text"] is None
    assert facts["spdx"] == "MIT"


def test_the_title_is_the_licence_s_own_first_line():
    """Read out of the file, so changing the licence changes one file."""
    text = about.licence_text()

    assert about.licence_title(text) == text.splitlines()[0].strip()
    assert "KINDNESS" in about.licence_title(text).upper()


def test_the_whole_licence_is_offered_not_only_its_name():
    """The wish is the half worth reading, and it is in front of the grant:
    a box that showed a name would show neither."""
    text = about.licence_text()

    assert "Permission is hereby granted" in text
    assert "senseless acts of beauty" in text
    assert text.index("senseless") < text.index("Permission is hereby granted")


def test_the_bundled_typefaces_are_reported_with_their_licences():
    """Somebody else's work ships in here, under OFL, and an About box is
    where that is said out loud."""
    fonts = about.bundled_fonts()

    # One entry per typeface, not per file: Fraunces ships in four cuts.
    assert [font["family"] for font in fonts] == [branding.SERIF, branding.SANS]
    assert len(fonts) < len(branding.FONTS)
    for font in fonts:
        assert font["licence"] == "SIL Open Font License 1.1"
        assert font["licence_file"] and os.path.exists(font["licence_file"])


def test_the_facts_are_what_a_front_end_needs_and_no_prose():
    """What is here is what does not translate. The headings and the sentence
    about the fonts belong to whichever front end is drawing the box, in its
    own language."""
    facts = about.facts()

    assert facts["version"] == __version__
    assert set(facts) == {"version", "spdx", "licence_title", "licence_text",
                          "licence_path", "fonts"}
