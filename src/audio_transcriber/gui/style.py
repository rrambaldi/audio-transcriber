"""The few visual decisions the window makes on purpose.

Qt paints with the palette the desktop hands it, and that is the right
default: a program that repaints itself in its own colours looks foreign on
every machine it runs on. Two things cannot be left to the desktop, though,
because they are correctness rather than taste.

The first is the contrast of text somebody has to read. The web page has had
this checked by a test since it was written; the window had nothing, and a
note rendered as *disabled* text came out at 1.75:1 against its box, where
WCAG 1.4.3 asks for 4.5:1.

The second is the difference between a note and a control. Greying a QLabel
is the cheapest way to make explanatory text look secondary, and it is the
wrong one: the criterion exempts disabled *controls*, not the sentence that
explains what a control does.

So: :func:`readable` mutes a colour as far as it can while still clearing the
ratio, :func:`note` uses it for explanatory text, and :func:`apply` lifts the
whole disabled group of the palette to the same floor — a control this
machine cannot offer stays legible, because reading why is the only thing
left to do with it.
"""
from PySide6.QtGui import QColor, QPalette

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
    """The colour for explanatory text next to a control in ``widget``."""
    palette = widget.palette()
    return readable(palette.color(QPalette.ColorRole.WindowText),
                    palette.color(QPalette.ColorRole.Window))


def note(label):
    """Make ``label`` read as a note without disabling it.

    A stylesheet rather than a palette because some styles ignore a palette
    set on a single widget, and a note that silently stays black is exactly
    the bug this module exists to prevent. Returns the label so it can be
    used inline."""
    label.setStyleSheet(f"color: {note_colour(label).name()};")
    return label


#: Which text colour is read against which background, for the palette below.
_PAIRS = (
    (QPalette.ColorRole.WindowText, QPalette.ColorRole.Window),
    (QPalette.ColorRole.Text, QPalette.ColorRole.Base),
    (QPalette.ColorRole.ButtonText, QPalette.ColorRole.Button),
)


def apply(application, minimum=MIN_CONTRAST):
    """Lift the disabled colours of ``application`` to a readable floor.

    Qt draws disabled text at roughly a quarter of the contrast of enabled
    text, which is a convention rather than a rule and here it costs real
    information: this window disables the answers the machine cannot produce
    — "who said what" without pyannote — and the only useful thing left to do
    with one of them is read it.

    Disabled still looks disabled: the control does not respond, takes no
    focus, and its indicator is drawn grey by the style. What changes is that
    the words survive."""
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
    return palette
