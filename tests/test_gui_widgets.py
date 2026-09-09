"""The two widgets the left column is built out of.

The whole bet of that column is that a closed row still reports what it
holds; these are the tests that keep that true.
"""
import os

import pytest

pytest.importorskip("PySide6", reason="the desktop window needs Qt")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QModelIndex, QSize
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QStyleOptionViewItem,
        QTableWidget,
        QTableWidgetItem,
    )
except ImportError as exc:      # pragma: no cover - depends on the machine
    pytest.skip(f"PySide6 cannot be loaded here: {exc}", allow_module_level=True)

from audio_transcriber.gui import widgets  # noqa: E402


@pytest.fixture(scope="session")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def section(application):
    return widgets.Disclosure("Keyword sets", QLabel("nineteen of them"))


def test_a_closed_section_says_what_it_holds(section):
    """"Keyword sets" tells you nothing; "Keyword sets — 3 chosen" is the same
    row doing the job the open panel was doing."""
    assert section.is_open() is False
    assert section.button.text() == "Keyword sets"

    section.set_summary("3 chosen")
    assert section.button.text() == "Keyword sets — 3 chosen"


def test_opening_shows_the_content(section):
    section.set_open(True)
    assert section.is_open() is True
    assert section.content.isVisibleTo(section) is True

    section.set_open(False)
    assert section.content.isVisibleTo(section) is False


def test_a_section_that_does_not_apply_stays_and_says_why(section):
    """Taking it out would change the shape of the list under the pointer,
    and the reason is worth more than the line it costs."""
    section.set_open(True)
    section.set_available(False, 'only with "Subtitles"')

    assert section.is_available() is False
    assert section.is_open() is False
    assert section.button.text() == 'Keyword sets — only with "Subtitles"'
    # ...and it cannot be opened by clicking it either
    section.set_open(True)
    assert section.is_open() is False


def test_it_opens_itself_when_it_becomes_applicable(section):
    """A section that has just started to matter should not need a second
    click to be read."""
    section.set_available(False, "not yet")
    section.set_available(True)

    assert section.is_open() is True
    assert section.button.text() == "Keyword sets"


def test_a_long_summary_is_cut_to_the_width_there_is(section):
    """A QToolButton does not elide, so a long summary widened the whole
    column past the window and put a horizontal scrollbar under five rows."""
    section.resize(180, 40)
    section.layout().activate()         # the button now knows how wide it is
    section.set_summary("auto (small on this machine) · Italian (it) · auto")

    assert section.button.text() != section._full
    assert section.button.text().endswith("…")
    assert section.button.toolTip() == section._full


def test_a_queue_row_is_two_lines_only_when_it_has_facts(application):
    """The delegate is what lets a row carry its details without a widget in
    the cell, which would not follow the selection colours."""
    table = QTableWidget(2, 1)
    plain, detailed = QTableWidgetItem("Nota vocale"), QTableWidgetItem("Comitato")
    detailed.setData(widgets.DETAILS_ROLE, "small · 30m · 2650 words")
    table.setItem(0, 0, plain)
    table.setItem(1, 0, detailed)
    delegate = widgets.JobDelegate(table)
    option = QStyleOptionViewItem()
    option.initFrom(table)

    one = delegate.sizeHint(option, table.model().index(0, 0))
    two = delegate.sizeHint(option, table.model().index(1, 0))
    assert isinstance(two, QSize)
    assert two.height() > one.height()


def test_the_delegate_paints_without_a_widget(application):
    """It is asked to paint before the view is shown, so a missing widget on
    the style option must not be an exception."""
    table = QTableWidget(1, 1)
    item = QTableWidgetItem("Comitato")
    item.setData(widgets.DETAILS_ROLE, "small · 30m")
    table.setItem(0, 0, item)
    table.setItemDelegateForColumn(0, widgets.JobDelegate(table))
    table.resize(400, 80)
    table.grab()                # paints every visible cell through the delegate

    assert table.item(0, 0).data(widgets.DETAILS_ROLE) == "small · 30m"


def test_the_index_of_a_row_without_details_is_left_alone(application):
    """QModelIndex() has no data at all: the delegate must fall through to
    the ordinary painting rather than reach into it."""
    delegate = widgets.JobDelegate()
    assert QModelIndex().data(widgets.DETAILS_ROLE) is None
    assert delegate.sizeHint(QStyleOptionViewItem(), QModelIndex()).isValid()


def test_the_row_buttons_actually_draw_their_labels(application):
    """The bug this test exists for: QToolButton's default style is
    "icon only", there is no icon, and the Windows style then draws nothing —
    three invisible buttons in a column of exactly the right width, on the
    only platform it mattered on. So this paints them and looks."""
    buttons = widgets.JobActions("abc")
    buttons.update_for({"action": "Transcribe", "removable": True,
                        "removable_label": "Remove", "play_audio": "Play",
                        "stop_audio": "Stop playing"})
    buttons.resize(buttons.sizeHint())
    image = buttons.grab().toImage()

    assert image.width() > 0 and image.height() > 0
    colours = {image.pixel(x, y)
               for x in range(0, image.width(), 2)
               for y in range(0, image.height(), 2)}
    # A blank widget is one colour; a widget with three labelled buttons on
    # it is not — anti-aliased text alone puts dozens of shades on the image.
    assert len(colours) > 4, "i pulsanti non disegnano niente"


def test_the_row_buttons_do_not_steal_the_default(application):
    """Enter belongs to the one button the tab is for, not to whichever of
    these happens to have the focus."""
    buttons = widgets.JobActions("abc")
    assert [button.autoDefault() for button in
            (buttons.run, buttons.listen, buttons.drop)] == [False] * 3
