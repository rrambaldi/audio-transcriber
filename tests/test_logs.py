"""Where the window's and the server's messages go instead of a terminal.

The interesting cases are the ones that only happen on somebody else's
machine: a process started from a shortcut, with no terminal at all; a server
left running until its log is bigger than the disk should hold; a line written
by the queue's worker thread while the main one is writing another. Each has a
test here, because none of them will be noticed in use until it matters.
"""
import os
import sys
import threading

import pytest

from audio_transcriber import logs, paths


@pytest.fixture(autouse=True)
def home(monkeypatch, tmp_path):
    """Everything under a temp folder, and the streams put back afterwards.

    A test that left ``sys.stdout`` replaced would hand its log file to every
    test that ran after it, and pytest's own capture would be the thing that
    broke."""
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv(logs.ENV_CONSOLE, raising=False)
    before = (sys.stdout, sys.stderr)
    yield
    logs.stop()
    sys.stdout, sys.stderr = before


def written():
    """The log as text, straight off the disk."""
    with open(logs.path(), encoding="utf-8") as handle:
        return handle.read()


# --- where it is ----------------------------------------------------------

def test_the_log_is_in_the_cache_and_not_in_the_data(tmp_path):
    """Cache is what may be deleted at any time without losing anything, and
    a log is that: worth reading after a crash, worth nothing a week later."""
    assert logs.path().startswith(paths.cache_dir())
    assert not logs.path().startswith(paths.library_dir())


def test_the_log_can_be_moved_by_the_environment(monkeypatch, tmp_path):
    elsewhere = tmp_path / "somewhere-else"
    monkeypatch.setenv(paths.ENV_LOG_DIR, str(elsewhere))
    assert logs.path() == str(elsewhere / paths.LOG_FILENAME)


def test_the_paths_report_says_where_it_is():
    """``audio-transcriber paths`` is how somebody finds it without this
    docstring, so the row has to be in the report."""
    rows = {label: path for label, path, _exists, _set in paths.describe()}
    assert rows["log"] == logs.path()


# --- what it catches ------------------------------------------------------

def test_what_the_program_prints_lands_in_the_file():
    logs.start("window")
    print("a message")
    print("and one on the error stream", file=sys.stderr)
    logs.stop()

    text = written()
    assert "a message" in text
    assert "and one on the error stream" in text


def test_the_terminal_gets_nothing_unless_it_is_asked_for(capsys):
    """The whole point: a window started from a shortcut has no terminal, and
    one started from a terminal has one nobody is reading."""
    logs.start("window")
    print("into the file only")
    logs.stop()

    assert "into the file only" not in capsys.readouterr().out
    assert "into the file only" in written()


def test_somebody_debugging_can_keep_the_terminal(monkeypatch, capsys):
    monkeypatch.setenv(logs.ENV_CONSOLE, "1")
    logs.start("window")
    print("into both")
    logs.stop()

    assert "into both" in capsys.readouterr().out
    assert "into both" in written()


def test_a_traceback_is_caught_too():
    """The reason this module exists: a window that falls over into a
    terminal that is not there has failed silently."""
    import traceback

    logs.start("window")
    try:
        raise ValueError("something gave way")
    except ValueError:
        traceback.print_exc()
    logs.stop()

    text = written()
    assert "ValueError: something gave way" in text
    assert "test_a_traceback_is_caught_too" in text


def test_every_line_is_stamped_and_the_session_is_announced():
    logs.start("web")
    print("first")
    logs.stop()

    lines = [line for line in written().splitlines() if line.strip()]
    assert "audio-transcriber" in lines[0] and "(web)" in lines[0]
    # "HH:MM:SS  text": the stamp, two spaces, the line as it was written.
    stamp, _, said = lines[-1].partition("  ")
    assert said == "first"
    assert len(stamp) == 8 and stamp.count(":") == 2


def test_a_line_arriving_in_pieces_is_stamped_once():
    """``print`` writes the text and the newline separately, and a library
    writing a progress line writes it in ten pieces."""
    logs.start()
    sys.stdout.write("one ")
    sys.stdout.write("line ")
    sys.stdout.write("in pieces\n")
    logs.stop()

    said = [line for line in written().splitlines() if "pieces" in line]
    assert len(said) == 1
    assert said[0].endswith("one line in pieces")


def test_a_line_with_no_newline_is_not_lost_when_the_process_ends():
    """A crash mid-sentence is still a sentence."""
    logs.start()
    sys.stdout.write("cut off half way")
    logs.stop()
    assert "cut off half way" in written()


def test_starting_twice_is_starting_once():
    first = logs.start("window")
    stream = sys.stdout
    assert logs.start("web") == first
    assert sys.stdout is stream


def test_two_threads_never_land_inside_each_other_s_lines():
    """The queue's worker prints while the thread drawing the window does."""
    logs.start()

    def chatter(name):
        for index in range(50):
            print(f"{name} line {index:02d}")

    threads = [threading.Thread(target=chatter, args=(name,))
               for name in ("alpha", "bravo")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    logs.stop()

    lines = [line for line in written().splitlines() if " line " in line]
    assert len(lines) == 100
    for line in lines:
        _stamp, _, said = line.partition("  ")
        assert said.startswith(("alpha line", "bravo line")), line


# --- not filling the disk -------------------------------------------------

def test_the_log_rolls_over_and_keeps_exactly_one_older_copy(monkeypatch):
    """A server left running for a month must not fill a disk; a log that
    deleted itself would lose the hour before a crash, which is the hour
    worth having."""
    monkeypatch.setattr(logs, "MAX_BYTES", 400)
    logs.start()
    for index in range(200):
        print(f"line {index:03d} " + "x" * 40)
    logs.stop()

    assert os.path.getsize(logs.path()) < 400 * 2
    assert os.path.exists(f"{logs.path()}.1")
    assert not os.path.exists(f"{logs.path()}.2")
    # What is kept is the end, not the beginning.
    assert "line 199" in written()


# --- reading it back ------------------------------------------------------

def test_the_tail_is_the_end_of_the_file_oldest_first():
    logs.start()
    for index in range(20):
        print(f"line {index:02d}")
    lines = logs.tail(5)
    logs.stop()

    assert len(lines) == 5
    assert lines[0].endswith("line 15")
    assert lines[-1].endswith("line 19")


def test_the_tail_of_a_log_that_does_not_exist_is_nothing():
    assert logs.tail() == []
    assert logs.size() == 0


def test_the_tail_does_not_read_the_whole_file(monkeypatch):
    """A viewer refreshing every three seconds must not read two megabytes to
    show thirty lines, so it reads a window off the end — and drops the first
    line of that window, which is half a line."""
    monkeypatch.setattr(logs, "TAIL_BYTES", 200)
    logs.start()
    for index in range(100):
        print(f"line {index:03d}")
    lines = logs.tail()
    logs.stop()

    assert 0 < len(lines) < 100
    assert lines[-1].endswith("line 099")
    assert all(line.count(":") >= 2 for line in lines), "a half line got through"


def test_emptying_it_keeps_the_file_and_the_writing_goes_on():
    logs.start()
    print("before")
    assert logs.clear() is True
    print("after")
    logs.stop()

    text = written()
    assert "before" not in text
    assert "after" in text


def test_it_can_be_emptied_without_this_process_having_started_it():
    """The window may be looking at a log the *server* is writing."""
    paths.ensure(paths.log_dir())
    with open(logs.path(), "w", encoding="utf-8") as handle:
        handle.write("something from another run\n")
    assert logs.clear() is True
    assert written() == ""


def test_an_unwritable_log_is_not_a_reason_not_to_start(monkeypatch, capsys):
    """A program made worse by having a log is a program that should not."""
    def refuse(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(logs.paths, "ensure", refuse)
    before = sys.stdout
    assert logs.start("window") == logs.path()
    assert logs.started() is False
    assert sys.stdout is before
    print("still says things")
    assert "still says things" in capsys.readouterr().out
