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


# --- showing a file where the system shows files ---------------------------

@pytest.fixture
def file_manager(monkeypatch):
    """What reveal() asks of the system, without asking the system."""
    calls = {"commands": [], "urls": []}

    class Desktop:
        @staticmethod
        def openUrl(url):
            calls["urls"].append(url.toLocalFile())
            return True

    monkeypatch.setattr(widgets, "QDesktopServices", Desktop)
    monkeypatch.setattr(widgets.subprocess, "run",
                        lambda command, **kwargs: calls["commands"].append(command))
    return calls


def test_windows_is_asked_to_select_the_file_not_only_its_folder(
        tmp_path, file_manager, monkeypatch):
    """A folder of recordings named by date, opened after the tenth one, is
    a folder you then have to search."""
    monkeypatch.setattr(widgets.sys, "platform", "win32")
    recording = tmp_path / "2026-09-15_1010_colloquio.wav"
    recording.write_bytes(b"RIFF")

    assert widgets.reveal(str(recording)) == str(recording)
    assert file_manager["commands"] == [["explorer", f"/select,{recording}"]]
    assert file_manager["urls"] == []


def test_macos_reveals_it_in_the_finder(tmp_path, file_manager, monkeypatch):
    monkeypatch.setattr(widgets.sys, "platform", "darwin")
    recording = tmp_path / "a.wav"
    recording.write_bytes(b"RIFF")

    widgets.reveal(str(recording))
    assert file_manager["commands"] == [["open", "-R", str(recording)]]


def test_elsewhere_the_folder_around_it_is_opened(tmp_path, file_manager, monkeypatch):
    """No portable way to ask for the file to be selected, and a folder that
    opens is worth more than a feature that does not."""
    monkeypatch.setattr(widgets.sys, "platform", "linux")
    recording = tmp_path / "a.wav"
    recording.write_bytes(b"RIFF")

    assert widgets.reveal(str(recording)) == str(tmp_path)
    assert file_manager["urls"] == [str(tmp_path)]
    assert file_manager["commands"] == []


def test_a_recording_that_has_moved_on_opens_the_folder_it_was_in(
        tmp_path, file_manager, monkeypatch):
    """Which is what a recording does the moment its transcription files it."""
    monkeypatch.setattr(widgets.sys, "platform", "win32")
    gone = tmp_path / "filed-elsewhere.wav"

    assert widgets.reveal(str(gone)) == str(tmp_path)
    assert file_manager["commands"] == []          # nothing to select
    assert file_manager["urls"] == [str(tmp_path)]


def test_nothing_at_all_opens_nothing(tmp_path, file_manager):
    assert widgets.reveal(str(tmp_path / "no" / "such" / "file.wav")) is None
    assert widgets.reveal("") is None
    assert file_manager["urls"] == []


# --- what a recording looks like ------------------------------------------

def test_a_queue_row_keeps_room_for_the_drawing_before_it_arrives(application):
    """The measuring happens on its own thread and lands some polls after the
    row does. If the row grew then, it would grow under the pointer."""
    table = QTableWidget(2, 1)
    waiting, drawn = QTableWidgetItem("Comitato"), QTableWidgetItem("Riunione")
    for item in (waiting, drawn):
        item.setData(widgets.DETAILS_ROLE, "small · 30m")
    drawn.setData(widgets.LOUDNESS_ROLE, [0, 500, 1000] * 40)
    table.setItem(0, 0, waiting)
    table.setItem(1, 0, drawn)
    delegate = widgets.JobDelegate(table)
    option = QStyleOptionViewItem()
    option.initFrom(table)

    assert (delegate.sizeHint(option, table.model().index(0, 0)).height()
            == delegate.sizeHint(option, table.model().index(1, 0)).height())


def test_a_queue_row_with_a_drawing_paints(application):
    table = QTableWidget(1, 1)
    item = QTableWidgetItem("Comitato")
    item.setData(widgets.DETAILS_ROLE, "small · 30m")
    item.setData(widgets.LOUDNESS_ROLE, [0, 250, 1000] * 40)
    table.setItem(0, 0, item)
    table.setItemDelegateForColumn(0, widgets.JobDelegate(table))
    table.resize(400, 120)
    table.resizeRowsToContents()
    table.grab()

    assert table.rowHeight(0) >= widgets.JobDelegate.WAVE_PX


def test_a_library_title_makes_room_for_the_recording_under_it(application):
    """The library is a table of columns, so the drawing goes in the one
    column wide enough to hold a picture: the one with the name in it."""
    table = QTableWidget(1, 2)
    title = QTableWidgetItem("Comitato")
    title.setData(widgets.LOUDNESS_ROLE, [0, 700, 1000] * 40)
    table.setItem(0, 0, QTableWidgetItem("2026-09-22 10:00"))
    table.setItem(0, 1, title)
    delegate = widgets.WaveTitleDelegate(table)
    table.setItemDelegateForColumn(1, delegate)
    option = QStyleOptionViewItem()
    option.initFrom(table)
    plain = QTableWidgetItem("Comitato")
    table.setItem(0, 0, plain)

    tall = delegate.sizeHint(option, table.model().index(0, 1))
    short = table.itemDelegate().sizeHint(option, table.model().index(0, 0))
    assert tall.height() == short.height() + widgets.WaveTitleDelegate.WAVE_PX
    table.resize(400, 120)
    table.resizeRowsToContents()
    table.grab()                # the delegate paints the name and the drawing


def test_a_library_row_nobody_has_measured_is_still_a_row(application):
    delegate = widgets.WaveTitleDelegate()
    assert QModelIndex().data(widgets.LOUDNESS_ROLE) is None
    assert delegate.sizeHint(QStyleOptionViewItem(), QModelIndex()).isValid()


def test_the_trace_draws_what_it_is_given_and_nothing_before_that(application):
    """Silence has to be a line somebody can see: drawn true to scale it
    rounds away to nothing, and a quiet room then looks like a dead one."""
    meter = widgets.TraceMeter()
    meter.grab()                                    # empty: nothing to draw
    meter.show_trail([0.0] * 50)
    meter.grab()
    meter.show_trail([0.0] * 49 + [0.9])
    meter.grab()

    assert meter.width() == widgets.TraceMeter.WIDTH_PX
    assert meter.accessibleName()
