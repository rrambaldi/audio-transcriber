"""The contrast floor, and the muted ink that explanatory text is written in.

This module used to open by arguing that the window should be painted by the
desktop and not by the program. That is no longer what this program does:
:mod:`audio_transcriber.gui.theme` paints it in the brand's own palette and
typefaces, so that the window and the web page read as one program rather than
as two that share a name. The argument is not wrong - a repainted window does
look foreign next to native ones - it was simply outweighed by having one
identity, and the reversal is written down in docs/gui.md rather than left as
two contradicting docstrings.

What stays here is the half that was never taste, and it matters more now than
it did: a palette this program chose has no desktop to blame if its greys
cannot be read.

The first thing is the contrast of text somebody has to read. The web page has had
this checked by a test since it was written; the window had nothing, and a
note rendered as *disabled* text came out at 1.75:1 against its box, where
WCAG 1.4.3 asks for 4.5:1.

The second is the difference between a note and a control. Greying a QLabel
is the cheapest way to make explanatory text look secondary, and it is the
wrong one: the criterion exempts disabled *controls*, not the sentence that
explains what a control does.

So: :func:`readable` mutes a colour as far as it can while still clearing the
ratio, :func:`note` writes explanatory text in the brand's muted ink and
checks it against the same floor, and :func:`apply` installs the theme and
then lifts the whole disabled group of the palette — a control this machine
cannot offer stays legible, because reading why is the only thing left to do
with it.
"""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget

from . import theme

#: WCAG 2.1 AA for text below 18pt: the floor everything here is measured
#: against, including the text Qt would otherwise draw as disabled.
MIN_CONTRAST = 4.5

#: How far towards the background a muted colour starts. It is walked back
#: from here until the ratio clears, so this is the *most* muting allowed
#: rather than the amount applied: on black-on-white it lands at 4.7:1.
MUTED_BLEND = 0.45


def luminance(colour):
    """Relative luminance of a QColor, as WCAG 2.1 defines it."""
    channels = []
    for value in (colour.redF(), colour.greenF(), colour.blueF()):
        channels.append(value / 12.92 if value <= 0.03928
                        else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(one, other):
    """The WCAG contrast ratio between two colours, 1.0 to 21.0."""
    first, second = luminance(one), luminance(other)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def mix(ink, ground, amount):
    """``ink`` moved ``amount`` of the way towards ``ground``."""
    return QColor.fromRgbF(
        ink.redF() + (ground.redF() - ink.redF()) * amount,
        ink.greenF() + (ground.greenF() - ink.greenF()) * amount,
        ink.blueF() + (ground.blueF() - ink.blueF()) * amount,
    )


def readable(ink, ground, minimum=MIN_CONTRAST, blend=MUTED_BLEND):
    """The most muted version of ``ink`` that still reads on ``ground``.

    Muting is done by mixing towards the background rather than by picking a
    grey, so it works whatever the desktop theme is: on a dark palette the
    text moves towards the dark, on a light one towards the light. The mix is
    then walked back until the ratio clears ``minimum``, which is why a theme
    with little contrast to spare simply gets less muting instead of an
    unreadable label."""
    if contrast(ink, ground) < minimum:
        # The theme itself does not clear the floor: muting would only make it
        # worse, and second-guessing the desktop's own text colour is not this
        # function's job.
        return ink
    steps = max(1, int(round(blend * 20)))
    for step in range(steps, -1, -1):
        muted = mix(ink, ground, step / 20)
        if contrast(muted, ground) >= minimum:
            return muted
    return ink


def note_colour(widget):
    """The colour for explanatory text next to a control in ``widget``.

    The brand's own ``--muted``, which is the colour the page writes its notes
    in, whenever it clears the floor against the background this particular
    widget sits on. It does on both of the program's schemes; on somebody
    else's palette - a window opened inside another Qt application, a test
    that installed the desktop's own colours - it may not, and then the ink is
    muted from that palette's own text colour instead."""
    palette = widget.palette()
    ground = palette.color(QPalette.ColorRole.Window)
    which = "dark" if ground.lightnessF() < 0.5 else "light"
    muted = theme.colour("muted", which)
    if contrast(muted, ground) >= MIN_CONTRAST:
        return muted
    return readable(palette.color(QPalette.ColorRole.WindowText), ground)


#: Marks a label whose ink was computed by :func:`note`, so that
#: :func:`renote` can find it again when the palette changes underneath.
NOTED = "audio_transcriber_note"


def note(label):
    """Make ``label`` read as a note without disabling it.

    A stylesheet rather than a palette because some styles ignore a palette
    set on a single widget, and a note that silently stays black is exactly
    the bug this module exists to prevent. Returns the label so it can be
    used inline."""
    label.setStyleSheet(f"color: {note_colour(label).name()};")
    label.setProperty(NOTED, True)
    return label


def renote(root):
    """Recompute every note under ``root`` for the palette in force now.

    A note's ink is a colour worked out once and written into the widget's own
    style sheet, which is what makes it survive a style that ignores palettes
    - and what makes it stale when the desktop switches to dark. Rather than
    have every panel remember which of its labels are notes, they are marked
    when they are made and found again here. Answers how many it repainted."""
    done = 0
    for label in root.findChildren(QWidget):
        if label.property(NOTED):
            note(label)
            done += 1
    return done


#: Where the stylesheet this module installs begins, so it can be replaced
#: without touching whatever else the application had set.
MARKER = "/* audio-transcriber: readable disabled text */"

#: Which text colour is read against which background, for the palette below.
_PAIRS = (
    (QPalette.ColorRole.WindowText, QPalette.ColorRole.Window),
    (QPalette.ColorRole.Text, QPalette.ColorRole.Base),
    (QPalette.ColorRole.ButtonText, QPalette.ColorRole.Button),
)


def apply(application, minimum=MIN_CONTRAST, which=None):
    """Paint the application in the brand, then lift its disabled colours.

    The painting is :func:`audio_transcriber.gui.theme.apply`; what is left
    here is the floor under it. Returns the palette actually installed.

    Qt draws disabled text at roughly a quarter of the contrast of enabled
    text, which is a convention rather than a rule and here it costs real
    information: this window disables the answers the machine cannot produce
    — "who said what" without pyannote — and the only useful thing left to do
    with one of them is read it.

    Disabled still looks disabled: the control does not respond, takes no
    focus, and its indicator is drawn grey by the style. What changes is that
    the words survive."""
    theme.apply(application, which)
    palette = application.palette()
    for role, ground_role in _PAIRS:
        # The ink starts from the enabled colour and is muted from there, but
        # it is measured against the *disabled* background, which is not the
        # same one: Qt draws a disabled field on a grey base, and mixing
        # against the white one lands four tenths short of the floor.
        ink = palette.color(QPalette.ColorGroup.Active, role)
        ground = palette.color(QPalette.ColorGroup.Disabled, ground_role)
        palette.setColor(QPalette.ColorGroup.Disabled, role,
                         readable(ink, ground, minimum))
    application.setPalette(palette)
    # Ours always goes last and is replaced rather than appended, so applying
    # twice — a second window, a test — does not pile the rules up.
    kept = application.styleSheet().split(MARKER)[0].rstrip()
    application.setStyleSheet(
        f"{kept}\n{MARKER}\n{_disabled_qss(palette)}".strip())
    return palette


def _disabled_qss(palette):
    """The same floor again, as a stylesheet, because Windows ignores the palette.

    The native Windows style draws disabled text through the system theme and
    never looks at ``QPalette.Disabled``, so the palette above is honoured on
    Linux and macOS and quietly dropped on the one platform most of this
    program's users are on. A stylesheet is the only thing that style obeys.

    Only the text colour is set, and only for the widgets that carry words:
    the indicator of a disabled checkbox, the border of a disabled field and
    everything else the theme draws stay exactly as the desktop draws them."""
    text = palette.color(QPalette.ColorGroup.Disabled,
                         QPalette.ColorRole.WindowText).name()
    button = palette.color(QPalette.ColorGroup.Disabled,
                           QPalette.ColorRole.ButtonText).name()
    field = palette.color(QPalette.ColorGroup.Disabled,
                          QPalette.ColorRole.Text).name()
    return (f"QLabel:disabled, QRadioButton:disabled, QCheckBox:disabled, "
            f"QGroupBox:disabled {{ color: {text}; }}\n"
            f"QPushButton:disabled, QToolButton:disabled {{ color: {button}; }}\n"
            f"QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled, "
            f"QPlainTextEdit:disabled, QTextEdit:disabled {{ color: {field}; }}")
