#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  audio-transcriber - update and install on Linux and macOS
#
#  Run it from the checkout:
#
#      ./install.sh                     cpu,gui,record  (the default)
#      ./install.sh cpu,web             a headless server
#      ./install.sh openvino,gui,record a Linux box with an Intel iGPU
#      ./install.sh cpu,gui,record,diarize
#
#  It uses the environment that is already active, or a .venv in the checkout
#  which it creates if needed, then pulls, installs, and checks the things
#  that actually go wrong on these two platforms: Qt's system libraries on
#  Linux, and PortAudio for the recorder. install.cmd is the Windows twin.
# ---------------------------------------------------------------------------
set -u

EXTRAS="${1:-cpu,gui,record}"
VENV="${AT_VENV:-.venv}"

say() { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ -f pyproject.toml ] || fail "run this from the audio-transcriber checkout - the
       folder that holds pyproject.toml."

# --- which interpreter, and never conda's own base -------------------------
if [ "${CONDA_DEFAULT_ENV:-}" = "base" ]; then
    fail "this is conda's own \"base\" environment, and installing gigabytes of
       PyTorch and OpenVINO into the environment conda runs from is how conda
       stops working. Make one of its own, or leave conda out of it:
           conda create -n audio-transcriber python=3.12 pip
           conda activate audio-transcriber
       Or just unset CONDA_DEFAULT_ENV and let this script use $VENV."
fi

if [ -n "${VIRTUAL_ENV:-}" ] || [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
    PYTHON=python3
    command -v python3 >/dev/null 2>&1 || PYTHON=python
    say "Using the active environment: ${VIRTUAL_ENV:-$CONDA_DEFAULT_ENV}"
else
    if [ ! -x "$VENV/bin/python" ]; then
        say "No environment active; making one in $VENV ..."
        command -v python3 >/dev/null 2>&1 || fail "no python3 on PATH."
        python3 -m venv "$VENV" || fail "could not create $VENV. On Debian and
       Ubuntu the venv module is a separate package: apt install python3-venv"
    fi
    PYTHON="$VENV/bin/python"
    say "Using $VENV"
fi

"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || fail \
    "Python 3.11 or newer is required ($("$PYTHON" -V 2>&1)). Point AT_VENV at an
       environment built on a newer one, or make one:
           python3.12 -m venv .venv && ./install.sh $EXTRAS"

say "  $("$PYTHON" -c 'import sys; print(sys.executable)')"
say "  Python $("$PYTHON" -c 'import sys; print(sys.version.split()[0])')"
say "  extras: [$EXTRAS]"
say ""

# --- update ----------------------------------------------------------------
if [ -d .git ]; then
    if command -v git >/dev/null 2>&1; then
        say "Updating the checkout..."
        git pull --ff-only || fail "git pull failed. Sort that out first - your
       local changes are untouched, and nothing has been installed."
        say ""
    else
        say "Skipping the update: no git on PATH."
        say ""
    fi
fi

# --- install ---------------------------------------------------------------
say "Installing..."
"$PYTHON" -m pip install -e ".[$EXTRAS]" || fail "the install failed; the output
       above says why. A wheel missing for this Python is the usual reason -
       the heavier dependencies lag a new release by months, and 3.12 is a
       safe bet."
say ""

"$PYTHON" -c 'import audio_transcriber as a; print("audio-transcriber", a.__version__, "installed")' \
    || fail "installed, but the package does not import. Nothing else will work
       until that is explained."

# --- the things that actually break here -----------------------------------
case "$EXTRAS" in
*gui*)
    if ! "$PYTHON" -c 'from PySide6 import QtCore; print("Qt", QtCore.qVersion(), "loads")' 2>/dev/null
    then
        say "WARNING: PySide6 will not load. On Linux that is almost always the"
        say "         system libraries Qt links against, which the wheel does not"
        say "         carry. Usually these, under the names your distribution"
        say "         happens to use:"
        say "             Debian/Ubuntu: apt install libgl1 libegl1 libxkbcommon-x11-0 \\"
        say "                                        libxcb-cursor0 libxcb-icccm4 \\"
        say "                                        libxcb-keysyms1 libdbus-1-3"
        say "             Fedora:        dnf install mesa-libGL libxkbcommon-x11 \\"
        say "                                        xcb-util-cursor xcb-util-wm \\"
        say "                                        xcb-util-keysyms dbus-libs"
        say "         The message from the import above names the missing one."
        say "         The web interface needs none of this: try 'web'."
    elif ! "$PYTHON" -c 'from PySide6.QtMultimedia import QMediaDevices' 2>/dev/null
    then
        say "WARNING: QtMultimedia is missing, so the window can neither play nor"
        say "         record audio. Install the other half of PySide6:"
        say "             $PYTHON -m pip install \"PySide6-Addons>=6.6\""
    fi
    ;;
esac

case "$EXTRAS" in
*record*)
    if ! "$PYTHON" -c 'import audio_transcriber.recording as r; s = r.sources(); print("audio sources:", len(s), "-", sum(1 for x in s if x.is_loopback), "of them loopback")' 2>/dev/null
    then
        say "WARNING: the audio libraries did not load, so the window will record"
        say "         through Qt only - one flat list of microphones, no choice of"
        say "         audio system and no recording of what the speakers play."
        say "             Debian/Ubuntu: apt install libportaudio2"
        say "             Fedora:        dnf install portaudio"
        say "             macOS:         the wheel carries PortAudio; nothing to do"
    fi
    ;;
esac

BIN="$(dirname "$("$PYTHON" -c 'import sys; print(sys.executable)')")"

# --- the menu entry, and with it the icon in the dock ----------------------
#  Linux only, and only when the window was installed. Wayland draws the icon
#  of the .desktop file a window names, not one the window hands it, so
#  without this the dock and the alt-tab list show a grey default however many
#  renders the package carries. The icon has to go through the icon theme, so
#  the PNGs are copied into hicolor under the entry's own name.
case "$(uname -s):$EXTRAS" in
Linux:*gui*)
    APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
    BRAND="$("$PYTHON" -c 'from audio_transcriber import branding; print(branding.DIR)' 2>/dev/null)"
    if [ -n "$BRAND" ] && [ -d "$BRAND" ] && mkdir -p "$APPS" 2>/dev/null; then
        # Exec is rewritten: a virtualenv is not on the PATH of the session
        # that starts a menu entry, so the entry has to name the interpreter's
        # own bin directory.
        sed "s|^Exec=audio-transcriber gui$|Exec=$BIN/audio-transcriber gui|" \
            packaging/audio-transcriber.desktop \
            > "$APPS/audio-transcriber.desktop" 2>/dev/null
        for SIZE in 16 32 48 64 128 256 512; do
            [ -f "$BRAND/icon-$SIZE.png" ] || continue
            mkdir -p "$ICONS/${SIZE}x${SIZE}/apps" 2>/dev/null &&
                cp "$BRAND/icon-$SIZE.png" \
                   "$ICONS/${SIZE}x${SIZE}/apps/audio-transcriber.png" 2>/dev/null
        done
        [ -f "$BRAND/icon.svg" ] &&
            mkdir -p "$ICONS/scalable/apps" 2>/dev/null &&
            cp "$BRAND/icon.svg" "$ICONS/scalable/apps/audio-transcriber.svg" 2>/dev/null
        command -v update-desktop-database >/dev/null 2>&1 &&
            update-desktop-database "$APPS" 2>/dev/null
        command -v gtk-update-icon-cache >/dev/null 2>&1 &&
            gtk-update-icon-cache -q -t -f "$ICONS" 2>/dev/null
        say "menu entry: $APPS/audio-transcriber.desktop"
        say "            (delete it, and $ICONS/*/apps/audio-transcriber.*,"
        say "             to undo this)"
    fi
    ;;
esac

# --- what to run -----------------------------------------------------------
cat <<EOF

---------------------------------------------------------------------------
 Ready. Things to run (from $BIN, or with that on your PATH):

   audio-transcriber gui           the desktop window: transcribe, record,
                                   browse and annotate the library
   audio-transcriber hardware      what this machine can do, and the engine
                                   and model that "auto" would pick
   audio-transcriber meeting.mp4   transcribe one file to meeting.txt
   audio-transcriber web           the same thing in a browser, on localhost
   audio-transcriber library list  what has been transcribed so far
   audio-transcriber vocab list    the keyword sets, which stop Whisper
                                   mangling your technical terms
   audio-transcriber paths         where models, recordings and config live
   audio-transcriber config init   write a commented config.toml to edit
   audio-transcriber --help        everything else; --lang it for Italian

 If the command is not found, this environment is not on your PATH:

   $PYTHON -m audio_transcriber.cli gui

 On a machine with no display there is nothing for Qt to draw on: use
 'audio-transcriber web' there, or run the window on your own machine
 against a library on a mounted volume ([paths] library in config.toml).
---------------------------------------------------------------------------
EOF
