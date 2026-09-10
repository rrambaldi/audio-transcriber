"""The icon set, checked as files, and the two names a desktop attaches it by.

Three front ends point at these paths and none of them fails loudly when a
file is missing: a browser draws its default favicon, and Qt draws nothing at
all. So what is checked here is that the files the code names are actually
there, and that a wheel would carry them — the two ways an icon disappears
without anybody noticing.

The desktop entry is checked here too, and for the same reason: on Wayland it
is the *only* thing that decides which icon the dock draws, and a window that
declares an entry nobody installed simply gets the grey default.
"""
import os
import re
import tomllib

from audio_transcriber import branding

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_every_named_file_exists():
    for name in (branding.ICON_SVG, branding.MARK_SVG, branding.FAVICON,
                 "icon-small.svg"):
        assert os.path.exists(branding.path(name)), name


def test_every_rendered_size_is_there():
    """``icon_files()`` comes back short instead of failing, so a size that
    stopped being shipped would only show up as a blurrier title bar."""
    assert [size for size, _ in branding.icon_files()] == list(branding.ICON_SIZES)


def test_the_renders_are_pngs_and_not_empty():
    for _, file in branding.icon_files():
        with open(file, "rb") as handle:
            assert handle.read(4) == b"\x89PNG", file


def test_the_icons_are_declared_as_package_data():
    """They live under data/, which setuptools does not include on its own:
    an editable install works either way, and a wheel does not."""
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as handle:
        config = tomllib.load(handle)
    patterns = config["tool"]["setuptools"]["package-data"]["audio_transcriber"]
    assert "data/brand/*" in patterns
    # A glob does not recurse: the fonts are a directory deeper and would be
    # left out of the wheel by the line above.
    assert "data/brand/fonts/*" in patterns


# --- the typefaces --------------------------------------------------------

def test_both_typefaces_are_there_with_their_licences():
    """Two typefaces, several files - Fraunces ships in four cuts - and both
    are OFL: the licence travels with the font or the redistribution is not
    one. What is *cited* is one line per typeface, which is what an About box
    should say."""
    cited = dict(branding.TYPEFACES)
    assert set(cited) == {branding.SERIF, branding.SANS}
    for family, licence in cited.items():
        assert os.path.exists(branding.font_path(licence)), family
    for _family, path in branding.font_files():
        assert os.path.exists(path)


#: What an sfnt file starts with: TrueType outlines, an Apple-flavoured
#: TrueType, or CFF outlines.
SFNT = (b"\x00\x01\x00\x00", b"true", b"OTTO")


def test_the_faces_are_in_a_format_every_platform_can_read():
    """The regression test for a bug that only showed up on Windows.

    These files were WOFF2, which is the right format for a web page and the
    wrong one for the rest of this: Qt does not read a font itself, it hands
    the bytes to the platform's font engine, and while FreeType takes WOFF2,
    DirectWrite rejects it. So the window came up in a fallback face on the
    platform most of these users are on, and said so twice:

        qt.qpa.fonts: Failed to create DirectWrite face from font data.

    A browser reads TrueType as happily as WOFF2 and both front ends are
    served from the same machine, so one sfnt per face is what ships. A file
    that is not one is this bug coming back."""
    for family, path in branding.font_files():
        with open(path, "rb") as handle:
            start = handle.read(4)
        assert start in SFNT, f"{family} is not an sfnt: {start!r}"
        assert start != b"wOF2"


def test_the_stylesheet_asks_for_the_files_that_are_shipped():
    """The page loads the *variable* file - a browser applies the axes, so one
    file covers a display heading and a row's title - and the window loads the
    static cuts, which is a difference worth pinning down: what the page asks
    for over HTTP has to exist, and it must not be asking for a cut that only
    the window uses."""
    with open(os.path.join(ROOT, "src", "audio_transcriber", "web", "static",
                           "style.css"), encoding="utf-8") as handle:
        css = handle.read()
    asked = re.findall(r'url\("\.\./brand/fonts/([^"]+)"\)', css)

    assert sorted(asked) == ["fraunces.ttf", "karla.ttf"]
    for name in asked:
        assert os.path.exists(branding.font_path(name)), name
    assert "woff2" not in css


def test_every_cut_the_window_asks_for_ships():
    """Three static faces and the variable one, each with an sfnt header and a
    licence beside it."""
    shipped = {name for _family, name, _licence in branding.FONTS}

    assert shipped == {"fraunces.ttf", "fraunces-display.ttf", "fraunces-text.ttf",
                       "fraunces-text-semibold.ttf", "karla.ttf"}
    for _family, name, licence in branding.FONTS:
        path = branding.font_path(name)
        assert os.path.exists(path), name
        with open(path, "rb") as handle:
            assert handle.read(4) in SFNT, name
        assert os.path.exists(branding.font_path(licence)), licence
    # The families the window names by hand have to be among them.
    named = {family for family, _name, _licence in branding.FONTS}
    assert {branding.SERIF, branding.SERIF_DISPLAY, branding.SERIF_TEXT,
            branding.SANS} <= named
