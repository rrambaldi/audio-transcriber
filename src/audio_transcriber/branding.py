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

The symbols are a different job from the mark, and the word is kept separate
on purpose: the mark is what a desktop draws for the *program*, a symbol is
the little drawing on a button inside it. Those are not ours — they are two
files out of Microsoft's Fluent set, MIT, with the licence beside them — and
:data:`SYMBOLS` says which and why so few.

The two typefaces are here for the same reason the mark is: the page and the
window are meant to look like one program, and a font in ``web/static`` would
be a file the window has to reach across the package to find. Fraunces carries
the headings and Karla everything read while typing; both are OFL, self-hosted,
and their licences sit next to them. They ship as plain TrueType rather than
as WOFF2, and the window loads static cuts rather than the variable file;
:data:`FONTS` says why for both.

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

#: Where the button symbols are, under :data:`DIR`.
SYMBOL_SUBDIR = "symbols"

#: The symbols that ship, by the job they do, as ``(name, file)``.
#:
#: They are Microsoft's Fluent UI System Icons, the 20 px regular cut, which
#: is the size these are actually drawn at: an icon set has a drawing per
#: size, and scaling the 24 px one down thickens its strokes until it is a
#: blot next to a hairline rule. Two of them, because two is what the window
#: has a use for - a button whose job can be *said* says it, in the interface
#: font, like every other button here. A symbol is for the ones that would
#: otherwise repeat a word three times down the same column.
#:
#: They were glyphs from the text font before this - ✎ and ⎘ - which is the
#: cheap way to have an icon and looks it: the glyph is whatever weight the
#: interface font draws it at, it is missing from some faces entirely, and no
#: two platforms agree on how much of the em it fills.
SYMBOLS = (("copy", "copy.svg"),
           ("edit", "edit.svg"))

#: The set to cite, and the licence that travels with it. MIT asks only that
#: the notice go with the copies; it does, in this file, and ``docs/
#: third-party.md`` is where a reader is pointed at it. That is why the About
#: box names the typefaces and not these: the OFL asks to travel *with the
#: font*, MIT does not ask for a credit screen.
SYMBOL_SET = ("Fluent UI System Icons", "fluent-MIT.txt")

#: The colour Fluent draws its own files in, and therefore the one string that
#: is replaced to put a symbol in this program's ink. The files are kept
#: byte for byte as they are published - a vendored file that has been edited
#: is a file somebody has to diff before they can trust it - so the recolour
#: happens on the way to the renderer, in :mod:`audio_transcriber.gui.symbols`.
SYMBOL_INK = "#212121"

#: Where the typefaces are, under :data:`DIR`. The web page asks for them over
#: HTTP - the app mounts this directory at ``/brand`` - and the window hands
#: the files to Qt.
FONT_SUBDIR = "fonts"

#: Every face that ships, as ``(family, file, licence file)``.
#:
#: The variable file is what the *page* loads: a browser applies
#: ``font-variation-settings``, so one file covers the display cut of a
#: heading and the text cut of a row's title. The window loads the three
#: static cuts instead, and the reason is a trap worth writing down. Qt hands
#: an application font to the platform's font engine, and where that engine
#: does not apply a variable axis it draws the file's *default instance* -
#: which in Fraunces is ``opsz 9, wght 900``, the Black text cut. So the
#: window came out on Windows in a heavy face with the wrong letterforms while
#: looking exactly right on Linux, twice, and no amount of asking for an axis
#: fixed it. A static cut has nothing left to ignore.
#:
#: They are instanced from the variable file with ``fonttools`` and given
#: derived family names, which the OFL allows here: neither licence declares
#: a reserved font name. ``docs/brand.md`` says how to make them again.
FONTS = (
    ("Fraunces", "fraunces.ttf", "fraunces-OFL.txt"),
    ("Fraunces Display", "fraunces-display.ttf", "fraunces-OFL.txt"),
    ("Fraunces Text", "fraunces-text.ttf", "fraunces-OFL.txt"),
    ("Fraunces Text", "fraunces-text-semibold.ttf", "fraunces-OFL.txt"),
    ("Karla", "karla.ttf", "karla-OFL.txt"),
)

#: Which family is which job. ``SERIF`` is the variable file the page uses;
#: the window asks for a cut by name - the display one for a masthead, the
#: text one for anything smaller, where Qt picks Regular or SemiBold by weight.
SERIF = "Fraunces"
SERIF_DISPLAY = "Fraunces Display"
SERIF_TEXT = "Fraunces Text"
SANS = "Karla"

#: The typefaces to *cite*, once each, with the licence that travels with
#: them. Four of the five files above are the same typeface in different cuts,
#: and an About box should say "Fraunces" once.
TYPEFACES = (("Fraunces", "fraunces-OFL.txt"),
             ("Karla", "karla-OFL.txt"))

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


def symbol_path(name):
    """The full path of one symbol file, whether or not it is there."""
    return os.path.join(DIR, SYMBOL_SUBDIR, name)


def symbol_svg(name):
    """The drawing for ``name``, or ``None`` when it did not ship.

    Cosmetic like the rest of this module: a window that cannot find a symbol
    falls back to the glyph it used to draw, rather than refusing to open."""
    for known, file in SYMBOLS:
        if known == name:
            candidate = symbol_path(file)
            return candidate if os.path.exists(candidate) else None
    return None


def font_files():
    """``(family, path)`` for every typeface that is actually present.

    Comes back short rather than failing, like :func:`icon_files`: a build
    without the fonts falls back to the next family in the stack, which is
    what the stylesheet does too."""
    found = []
    for family, name, _licence in FONTS:
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
