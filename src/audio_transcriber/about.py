"""What the program says about itself: the facts an About box shows.

The licence is a file at the top of the repository, which is exactly where
neither front end can reach it: a wheel does not carry the repository, and an
installed copy keeps the file somewhere else again - in ``*.dist-info``, under
the ``License-File`` the metadata declares. So the looking-up happens here,
once, and the web page and the window both ask.

Both of them show the whole text rather than a name. The licence is the MIT
license with a wish in front of it, and a box that said "MIT" and stopped
would be showing the half that nobody needs to read: the terms are the ones
everybody already knows, and the part worth a screen is the part that asks for
gratitude and for senseless acts of beauty.

What is bundled is listed as well, because two of the files in here are
somebody else's work under their own licence - the typefaces - and an About
box is where that is said out loud.
"""
import functools
import os

from . import __version__, branding

#: The SPDX expression for this program's own code: what ``pyproject.toml``
#: declares, and what the four travelling files carry in their heads. The
#: wish adds no condition, so the answer to "what may I do with this" is MIT.
SPDX = "MIT"

#: The name of the licence file, as the repository and the metadata have it.
FILENAME = "LICENSE"

#: The distribution's name on PyPI, for looking the file up in an installed
#: copy. Not the import name: those differ here.
DISTRIBUTION = "audio-transcriber-ov"

#: Where a checkout keeps it, relative to this module: src/audio_transcriber
#: -> src -> the repository root.
_CHECKOUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), FILENAME)


def licence_path():
    """The licence file, wherever this copy of the program keeps it.

    An installed copy first: the metadata says which file was the licence, so
    a wheel that renamed or moved it is still found. Then the checkout, which
    is how anybody working on the program runs it. ``None`` if neither is
    there - a licence that cannot be shown is not a reason to fail, so the
    callers say so instead."""
    for candidate in (_installed_path(), _CHECKOUT):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _installed_path():
    """The ``License-File`` of the installed distribution, if there is one."""
    try:
        from importlib import metadata
        distribution = metadata.distribution(DISTRIBUTION)
    except Exception:           # not installed, or a metadata backend that
        return None             # cannot answer: the checkout is next
    try:
        for file in distribution.files or ():
            # Wheels have carried it as LICENSE and, since PEP 639, under a
            # licenses/ directory: match the name, not the path.
            if os.path.basename(str(file)) == FILENAME:
                return str(distribution.locate_file(file))
    except Exception:           # pragma: no cover - a broken installation
        return None
    return None


@functools.lru_cache(maxsize=1)
def licence_text():
    """The whole licence, or ``None`` where this copy has no file to read.

    Cached: both front ends may ask on every About box, and the file does not
    change while the program runs."""
    path = licence_path()
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:             # pragma: no cover - unreadable file
        return None


def licence_title(text=None):
    """The licence's own name: the first line of its file.

    Taken from the text rather than written here, so that changing the licence
    means changing one file. Falls back to the expression when there is no
    file to read - "MIT" is a true answer, just a shorter one."""
    text = licence_text() if text is None else text
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return SPDX


def bundled_fonts():
    """The typefaces that ship with the program, and their licence files.

    They are somebody else's work: OFL, which asks that the licence travel
    with the font. It does - the files sit next to them - and this is where a
    reader is told about it."""
    found = []
    for family, file in branding.FONTS:
        licence = branding.font_path(f"{os.path.splitext(file)[0]}-OFL.txt")
        found.append({
            "family": family,
            "file": os.path.basename(file),
            "licence": "SIL Open Font License 1.1",
            "licence_file": licence if os.path.exists(licence) else None,
        })
    return found


def facts():
    """Everything an About box shows, as plain data.

    The prose around it - the headings, the sentence about the fonts - belongs
    to whichever front end is drawing the box, in its own language. What is
    here is what does not translate: a version, a licence, a list of files."""
    text = licence_text()
    return {
        "version": __version__,
        "spdx": SPDX,
        "licence_title": licence_title(text),
        "licence_text": text,
        "licence_path": licence_path(),
        "fonts": bundled_fonts(),
    }
