@echo off
rem SPDX-FileCopyrightText: 2026 Roberto Rambaldi
rem SPDX-License-Identifier: MIT
rem The Gratitude & Random Kindness License: MIT, with a wish. See LICENSE.

rem ---------------------------------------------------------------------------
rem  audio-transcriber - update and install on Windows
rem
rem  Run it from the checkout. It puts itself in the right conda environment,
rem  pulls, installs, checks what actually goes wrong on Windows, and prints
rem  what to run:
rem
rem      install.cmd                       openvino,summarize-ov,gui,record
rem      install.cmd cpu,gui               a machine with no Intel iGPU
rem      install.cmd openvino,gui,record,diarize
rem      install.cmd openvino,gui --base   into whatever is active, base included
rem
rem  The environment it wants is "srt-ov2"; set AT_ENV to use another one. It
rem  activates it for this window too, which is why there is no setlocal here:
rem  the whole point is that "audio-transcriber gui" works when this finishes.
rem
rem  The control flow is flat on purpose - cmd parses the parentheses inside a
rem  "python -c" one-liner as block delimiters.
rem ---------------------------------------------------------------------------

set "AT_EXTRAS=%~1"
rem "summarize-ov" is in the default because without it a machine with an Intel
rem device transcribes but cannot have a summary written for it, and nothing
rem says so: "audio-transcriber hardware" reports three OpenVINO devices and
rem then that no engine is installed. The extra adds openvino-genai on top of
rem what "openvino" already pulls, which is the small half of the download.
if "%AT_EXTRAS%"=="" set "AT_EXTRAS=openvino,summarize-ov,gui,record"
set "AT_MODE=%~2"
if "%AT_ENV%"=="" set "AT_ENV=srt-ov2"

if not exist "pyproject.toml" goto :wrong_folder

rem --- the right environment, before anything is installed into the wrong one
if /i "%AT_MODE%"=="--base" goto :env_ready
where conda >nul 2>nul
if errorlevel 1 goto :env_ready
if /i "%CONDA_DEFAULT_ENV%"=="%AT_ENV%" goto :env_ready
echo Active environment: "%CONDA_DEFAULT_ENV%" - switching to "%AT_ENV%".
call conda activate %AT_ENV%
if /i not "%CONDA_DEFAULT_ENV%"=="%AT_ENV%" goto :no_env
echo.

:env_ready
where python >nul 2>nul
if errorlevel 1 goto :no_python

rem Conda's own environment is almost never the right answer: Anaconda ships
rem its own Qt there and its Library\bin comes first on PATH, so the binding
rem pip installs loads the wrong Qt6Core.dll and dies on QtCore - and that Qt
rem belongs to Navigator and Spyder, so it cannot be removed either.
if /i not "%CONDA_DEFAULT_ENV%"=="base" goto :check_python
if /i "%AT_MODE%"=="--base" goto :check_python
goto :refuse_base

:check_python
for /f "delims=" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set "AT_PYVER=%%v"
for /f "delims=" %%v in ('python -c "import sys;print(sys.executable)"') do set "AT_PYEXE=%%v"
echo Installing into Python %AT_PYVER%
echo   %AT_PYEXE%
if not "%CONDA_DEFAULT_ENV%"=="" echo   conda environment: %CONDA_DEFAULT_ENV%
echo   extras: [%AT_EXTRAS%]
echo.

python -c "import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)"
if errorlevel 1 goto :too_old

rem --- update ---------------------------------------------------------------
if not exist ".git" goto :install
where git >nul 2>nul
if errorlevel 1 goto :no_git
echo Updating the checkout...
git pull --ff-only
if errorlevel 1 goto :pull_failed
echo.
goto :install

:no_git
echo Skipping the update: no "git" on PATH.
echo.

:install
echo Installing...
python -m pip install -e ".[%AT_EXTRAS%]"
if errorlevel 1 goto :install_failed
echo.

python -c "import audio_transcriber;print('audio-transcriber',audio_transcriber.__version__,'installed')"
if errorlevel 1 goto :no_import

rem --- the things that actually break on Windows -----------------------------
echo %AT_EXTRAS% | find /i "gui" >nul
if errorlevel 1 goto :check_record
python -c "from PySide6 import QtCore;print('Qt',QtCore.qVersion(),'loads')" 2>nul
if errorlevel 1 goto :qt_broken
python -c "from PySide6.QtMultimedia import QMediaDevices" 2>nul
if errorlevel 1 goto :no_multimedia
goto :check_record

:qt_broken
echo WARNING: PySide6 will not load here. Almost always two Qt installations in
echo          one environment, conda's ahead of pip's on PATH. These are the
echo          copies it can see:
where Qt6Core.dll 2>nul
echo          One line is healthy, two is the problem - see docs/gui.md.
goto :check_record

:no_multimedia
echo WARNING: QtMultimedia is missing, so the window can neither play nor
echo          record audio. Install the other half of PySide6:
echo              python -m pip install "PySide6-Addons>=6.6"

:check_record
echo %AT_EXTRAS% | find /i "record" >nul
if errorlevel 1 goto :ready
python -c "import audio_transcriber.recording as r;s=r.sources();print('audio sources:',len(s),'-',sum(1 for x in s if x.is_loopback),'of them loopback')" 2>nul
if errorlevel 1 echo WARNING: the audio libraries did not load; the window will record through Qt only.

:ready
echo.
echo ---------------------------------------------------------------------------
echo  Ready, in "%CONDA_DEFAULT_ENV%". Things to run:
echo.
echo    audio-transcriber gui           the desktop window: transcribe, record,
echo                                    browse and annotate the library
echo    audio-transcriber hardware      what this machine can do, and the engine
echo                                    and model that "auto" would pick
echo    audio-transcriber meeting.mp4   transcribe one file to meeting.txt
echo    audio-transcriber web           the same thing in a browser, on localhost
echo    audio-transcriber library list  what has been transcribed so far
echo    audio-transcriber vocab list    the keyword sets, which stop Whisper
echo                                    mangling your technical terms
echo    audio-transcriber paths         where models, recordings and config live
echo    audio-transcriber config init   write a commented config.toml to edit
echo    audio-transcriber --help        everything else; --lang it for Italian
echo.
echo  If "audio-transcriber" is not found, this environment's Scripts folder is
echo  not on PATH. The module form always works:
echo.
echo    python -m audio_transcriber.cli gui
echo ---------------------------------------------------------------------------
goto :end

rem --- what went wrong -------------------------------------------------------

:wrong_folder
echo ERROR: run this from the audio-transcriber checkout - the folder that
echo        holds pyproject.toml.
goto :failed

:no_env
echo ERROR: could not get into the "%AT_ENV%" environment. Either it does not
echo        exist, or this shell has never been initialised for conda - the
echo        Anaconda Prompt is one that has.
echo.
echo        To make it, with conda providing only the interpreter and pip
echo        providing everything else:
echo            conda create -n %AT_ENV% python=3.12 pip
echo            install.cmd %AT_EXTRAS%
echo.
echo        Another name: set AT_ENV=myenv before running this.
goto :failed

:no_python
echo ERROR: no "python" on PATH. Open the Anaconda Prompt and try again, or
echo        activate the environment by hand:
echo            conda activate %AT_ENV%
goto :failed

:too_old
echo ERROR: Python 3.11 or newer is required, this is %AT_PYVER%.
echo        Make an environment where conda provides only the interpreter:
echo            conda create -n %AT_ENV% python=3.12 pip
echo            conda activate %AT_ENV%
goto :failed

:pull_failed
echo ERROR: git pull failed. Sort that out first - your local changes are
echo        untouched, and nothing has been installed.
goto :failed

:install_failed
echo.
echo ERROR: the install failed. Two failures are common here:
echo.
echo   "Cannot uninstall shiboken6 ... no RECORD file was found"
echo       Qt came from conda. Take it out of conda's hands first, in this
echo       order and never the other way round:
echo           conda remove pyside6 shiboken6
echo           install.cmd %AT_EXTRAS%
echo.
echo   a wheel that is missing or will not build for this Python
echo       Try Python 3.12 in a fresh environment: the heavier dependencies
echo       lag a new Python release by months.
goto :failed

:no_import
echo ERROR: installed, but "import audio_transcriber" does not work. Nothing
echo        else will until that is explained - the output above says why.
goto :failed

rem This one refuses rather than warns. It used to pause with "any key to
rem continue", which is what a person presses on autopilot - and the mistake
rem costs an afternoon: gigabytes of PyTorch and OpenVINO in the environment
rem conda itself runs from, and pip's Qt half-replacing Anaconda's, which
rem leaves both broken.
:refuse_base
echo ERROR: this is conda's own "base" environment, and this is almost never
echo        where you want it. Switching to "%AT_ENV%" was not possible, so
echo        nothing has been installed.
echo.
echo        Make it, if it is not there:
echo            conda create -n %AT_ENV% python=3.12 pip
echo            install.cmd %AT_EXTRAS%
echo.
echo        Already installed into base by mistake? docs/gui.md has the way
echo        back: uninstall what pip put there, then "conda install
echo        --force-reinstall pyside6" to give conda its Qt back.
echo.
echo        And if base really is what you mean:
echo            install.cmd %AT_EXTRAS% --base
goto :failed

:failed
set "AT_EXTRAS="
set "AT_MODE="
set "AT_PYVER="
set "AT_PYEXE="
exit /b 1

:end
rem The activated environment stays - that is the point of having no setlocal.
rem AT_ENV is left alone: it may have been set by whoever ran this.
set "AT_EXTRAS="
set "AT_MODE="
set "AT_PYVER="
set "AT_PYEXE="
exit /b 0
