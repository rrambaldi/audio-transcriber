"""The program's mark and typefaces, and where the copies of them live.

Three front ends want the same icon — the browser wants a favicon, the window
wants something for the task bar and the alt-tab list, and the packagers want
a file to point a shortcut at — so the files sit in one place,
``data/brand/``, and every front end asks here for them rather than reaching
into the other one's directory.

The mark is a padlock cut through by a waveform: the two things this program
is, in one shape. It comes in three drawings and a set of renders. ``icon.svg``
is the master, on its rounded plate; ``icon-small.svg`` is the same lock with
three fat bars instead of five, because five stop being separate below about
32 px; ``icon-mark.svg`` is the lock with no plate, for putting on a
background that is already dark. The PNGs are renders of the first two — the
small drawing below 48 px, the master above it — and ``favicon.ico`` carries
six of them for browsers that still ask for one file.

The two typefaces are here for the same reason the icons are: the page and the
window are meant to look like one program, and a font in ``web/static`` would
be a file the window has to reach across the package to find. Fraunces carries
the headings and Karla everything read while typing; both are OFL, self-hosted,
and their licences sit next to them. They are shipped as variable TrueType
rather than as WOFF2, and :data:`FONTS` says why.

Nothing here is required for the program to run: a build that lost its data
files should transcribe anyway, so the callers treat a missing icon or font as
cosmetic (:func:`icon_files` and :func:`font_files` simply come back short)
instead of failing.
"""
import os

#: Where the files are: package data, so a wheel carries them.
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "brand")

#: The master drawing, and the one to hand anything that can render SVG.
ICON_SVG = "icon.svg"

#: The lock without its plate, for a dark background of someone else's.
MARK_SVG = "icon-mark.svg"

#: What a browser asks for at ``/favicon.ico`` if it ignores the SVG.
FAVICON = "favicon.ico"

#: Where the typefaces are, under :data:`DIR`. The web page asks for them over
#: HTTP - the app mounts this directory at ``/brand`` - and the window hands
#: the files to Qt.
FONT_SUBDIR = "fonts"

#: The typefaces, as ``(family, file)``. The family is what both front ends
#: name first in their font stack, so the same string has to be right for
#: ``font-family`` in the stylesheet and for ``QFont`` in the window.
#:
#: They are plain sfnt - variable TrueType - and not WOFF2, which is the
#: better format for a web page and unreadable to half of what has to read
#: these files. Qt hands an application font to the platform's font engine,
#: and on Windows that is DirectWrite, which rejects WOFF2 outright: the
#: window came up in a fallback face and Qt said so twice, on the platform
#: most of this program's users are on. A browser reads TrueType as happily
#: as WOFF2, and both front ends here are served from the same machine, so
#: the compression the page loses is not worth a second copy of every face.
FONTS = (("Fraunces", "fraunces.ttf"), ("Karla", "karla.ttf"))

#: Which of them is which job: headings and titles in the serif, everything
#: else in the sans. Both front ends make the same split.
SERIF, SANS = FONTS[0][0], FONTS[1][0]

#: The rendered sizes, smallest first. Below 48 px these come from the
#: simplified drawing; above it from the master.
ICON_SIZES = (16, 32, 48, 64, 128, 256, 512)

#: The two names by which a desktop attaches the mark to this program, rather
#: than to the interpreter that happens to be running it. They are here, with
#: the files, because they are part of the same job: on both platforms the
#: window can set its icon and still not be the thing whose icon is drawn.
#:
#: On Linux it is the basename of the desktop entry the window declares
#: (``packaging/audio-transcriber.desktop``, installed by ``install.sh``):
#: Wayland has no counterpart to X11's ``_NET_WM_ICON``, so what the dock and
#: the alt-tab list draw is that file's ``Icon=``, resolved through the icon
#: theme, and never a picture the window hands over.
DESKTOP_ENTRY = "audio-transcriber"

#: On Windows it is the Application User Model ID, which is what Explorer
#: groups task-bar buttons by and takes their icon from. Its default is the
#: interpreter's, so a ``pip install`` run of this program shows the Python
#: logo on the task bar however many renders the package carries. The
#: ``Company.Product`` form is the one Explorer expects, and a pinned shortcut
#: has to carry the same string to pin to the same button.
WINDOWS_APP_ID = "Digithera.AudioTranscriber"


def path(name):
    """The full path of one brand file, whether or not it is there."""
    return os.path.join(DIR, name)


def icon_png(size):
    """The path of the rendered icon at ``size`` pixels."""
    return path(f"icon-{size}.png")


def font_path(name):
    """The full path of one font file, whether or not it is there."""
    return os.path.join(DIR, FONT_SUBDIR, name)


def font_files():
    """``(family, path)`` for every typeface that is actually present.

    Comes back short rather than failing, like :func:`icon_files`: a build
    without the fonts falls back to the next family in the stack, which is
    what the stylesheet does too."""
    found = []
    for family, name in FONTS:
        candidate = font_path(name)
        if os.path.exists(candidate):
            found.append((family, candidate))
    return found


def icon_files():
    """``(size, path)`` for every rendered icon that is actually present.

    A window builds its icon from all of them, so that the desktop picks the
    size it wants instead of scaling one render: 16 px in a title bar and 256
    in the alt-tab list are different drawings here, not the same one twice.
    """
    found = []
    for size in ICON_SIZES:
        candidate = icon_png(size)
        if os.path.exists(candidate):
            found.append((size, candidate))
    return found
