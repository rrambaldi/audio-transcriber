#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Roberto Rambaldi
# SPDX-License-Identifier: MIT
# The Gratitude & Random Kindness License: MIT, with a wish. See LICENSE.
# ---------------------------------------------------------------------------
#  audio-transcriber - run it on Linux and macOS, in the right environment
#
#  The window, with no arguments:
#
#      ./run.sh
#
#  Anything else is passed straight through to the program:
#
#      ./run.sh hardware
#      ./run.sh meeting.mp4 --lang it --summary
#      ./run.sh web
#      ./run.sh --help
#
#  Which interpreter, in this order: the environment already active, then the
#  conda environment "srt-ov2" (AT_ENV to name another) where conda has one by
#  that name, then a virtualenv in the checkout - the .venv install.sh makes,
#  or the .venv-cpu a server without an accelerator usually has.
#
#  Falling through rather than failing is the difference from run.cmd, and the
#  platform is the reason: on Windows conda is how this program is installed,
#  so not getting into the environment is an error worth stopping for. Here a
#  machine is as likely to have a plain virtualenv and no conda at all.
# ---------------------------------------------------------------------------
set -u

cd "$(dirname "$0")" || exit 1

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ -f pyproject.toml ] || fail "run this from the audio-transcriber checkout - the
       folder that holds pyproject.toml."

AT_ENV="${AT_ENV:-srt-ov2}"
PYTHON=""

if [ -n "${VIRTUAL_ENV:-}" ] || [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
    # Something is already active and it is not this script's business to
    # overrule it: somebody who activated an environment meant it.
    PYTHON="$(command -v python3 || command -v python || true)"
elif command -v conda >/dev/null 2>&1; then
    # conda's shell function does not exist in a non-interactive shell, so the
    # hook is sourced rather than assumed. A conda that is installed but has
    # no environment by that name is not an error here - the checkout may
    # still hold a virtualenv, and that is the next thing tried.
    CONDA_BASE="$(conda info --base 2>/dev/null)"
    # shellcheck disable=SC1091
    [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ] && . "$CONDA_BASE/etc/profile.d/conda.sh"
    if conda activate "$AT_ENV" 2>/dev/null; then
        PYTHON="$(command -v python3 || command -v python || true)"
    fi
fi

if [ -z "$PYTHON" ]; then
    for candidate in "${AT_VENV:-.venv}/bin/python" .venv-cpu/bin/python; do
        [ -x "$candidate" ] && PYTHON="$candidate" && break
    done
fi
[ -n "$PYTHON" ] || PYTHON="$(command -v python3 || command -v python || true)"

[ -n "$PYTHON" ] || fail "no python found. Install into an environment first:
       ./install.sh"

"$PYTHON" -c 'import audio_transcriber' 2>/dev/null || fail \
    "audio-transcriber is not installed in $("$PYTHON" -c 'import sys; print(sys.prefix)').
       Install it there:
           ./install.sh
       Or name the conda environment it is in:
           AT_ENV=myenv ./run.sh $*"

# No arguments means the window - what somebody who wanted a command line
# would not have left empty. exec so that Ctrl-C and the exit code are the
# program's own and not this script's.
if [ "$#" -eq 0 ]; then
    exec "$PYTHON" -m audio_transcriber.cli gui
fi
exec "$PYTHON" -m audio_transcriber.cli "$@"
