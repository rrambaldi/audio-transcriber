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

def test_both_faces_are_there_with_their_licences():
    """Two front ends are set in them, and both are OFL: the licence travels
    with the file or the redistribution is not one."""
    families = dict(branding.font_files())
    assert set(families) == {branding.SERIF, branding.SANS}
    for family, path in families.items():
        assert os.path.exists(path), family
        with open(path, "rb") as handle:
            assert handle.read(4) == b"wOF2", family
    for licence in ("fraunces-OFL.txt", "karla-OFL.txt"):
        assert os.path.exists(branding.font_path(licence)), licence


def test_the_faces_sit_with_the_icons_not_in_the_web_package():
    """Shared data, for the same reason the icons are shared: the window must
    not reach across the package into web/static to be painted."""
    for _, path in branding.font_files():
        assert os.path.dirname(path) == os.path.join(branding.DIR,
                                                     branding.FONT_SUBDIR)
    assert not os.path.exists(os.path.join(
        os.path.dirname(branding.DIR), "..", "web", "static", "fonts"))


# --- the Linux desktop entry ----------------------------------------------

DESKTOP_FILE = os.path.join(ROOT, "packaging", "audio-transcriber.desktop")


def desktop_entry():
    """The entry's keys, comments and the group header dropped."""
    keys = {}
    with open(DESKTOP_FILE, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith(("#", "[")):
                continue
            name, _, value = line.partition("=")
            keys[name] = value
    return keys


def test_the_window_declares_the_entry_that_is_shipped():
    """``setDesktopFileName`` names a basename, and a compositor looks that
    name up: the two have to be the same string or the icon is the default."""
    assert os.path.basename(DESKTOP_FILE) == f"{branding.DESKTOP_ENTRY}.desktop"


def test_the_entry_names_an_icon_theme_name_not_a_path():
    """A path would work in the menu and not in the dock. What the entry names
    is an icon-theme name, which install.sh puts into hicolor under exactly
    that name — so it must not look like a file."""
    icon = desktop_entry()["Icon"]
    assert icon == branding.DESKTOP_ENTRY
    assert not os.path.isabs(icon) and not icon.endswith(".png")


def test_the_entry_starts_the_window_and_says_it_is_one():
    keys = desktop_entry()
    assert keys["Type"] == "Application"
    assert keys["Exec"].endswith("audio-transcriber gui")
    assert keys["Terminal"] == "false"
    # How a compositor ties an X11 window back to this entry; Qt sets
    # WM_CLASS from the application name, which is the same string.
    assert keys["StartupWMClass"] == branding.DESKTOP_ENTRY


def test_install_sh_installs_the_entry_and_the_themed_icons():
    """The entry is only useful once it is in ~/.local/share: an entry left in
    the checkout is an entry no desktop ever reads."""
    with open(os.path.join(ROOT, "install.sh"), encoding="utf-8") as handle:
        script = handle.read()
    assert "packaging/audio-transcriber.desktop" in script
    assert "applications" in script and "icons/hicolor" in script
