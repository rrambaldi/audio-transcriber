@echo off
setlocal

rem ---------------------------------------------------------------------------
rem  audio-transcriber - update and install on Windows
rem
rem  Run it from the checkout, inside the environment you want it installed in:
rem
rem      conda activate srt-ov2
rem      install.cmd                       openvino,gui,record  (the default)
rem      install.cmd cpu,gui               a machine with no Intel iGPU
rem      install.cmd openvino,gui,record,diarize
rem
rem  It pulls, installs into whichever interpreter "python" resolves to, checks
rem  the things that actually go wrong on Windows, and prints what to run.
rem  Every step is in README.md and docs/gui.md as well; this only saves the
rem  typing. The control flow is flat on purpose: parenthesised blocks and the
rem  parentheses inside a python -c one-liner do not get along.
rem ---------------------------------------------------------------------------

set "EXTRAS=%~1"
if "%EXTRAS%"=="" set "EXTRAS=openvino,gui,record"

if not exist "pyproject.toml" goto :wrong_folder

where python >nul 2>nul
if errorlevel 1 goto :no_python

for /f "delims=" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
for /f "delims=" %%v in ('python -c "import sys;print(sys.executable)"') do set "PYEXE=%%v"
echo Installing into Python %PYVER%
echo   %PYEXE%
if not "%CONDA_DEFAULT_ENV%"=="" echo   conda environment: %CONDA_DEFAULT_ENV%
echo   extras: [%EXTRAS%]
echo.

python -c "import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)"
if errorlevel 1 goto :too_old

rem The window cannot work in an environment that also carries conda's own Qt:
rem its Library\bin comes first on PATH, so a 6.11.2 binding loads a 6.11.0
rem Qt6Core.dll and looks for an export that is not there. In a full Anaconda
rem "base" that Qt belongs to Navigator and Spyder and must not be removed, so
rem the only cure is a different environment - said before installing, not
rem after.
if /i "%CONDA_DEFAULT_ENV%"=="base" goto :warn_base
goto :update

:warn_base
echo WARNING: this is the "base" environment.
echo          Anaconda ships its own Qt there, and it shadows the one pip
echo          installs: "audio-transcriber gui" will fail to load QtCore.
echo          A dedicated environment avoids it entirely:
echo              conda create -n srt-ov2 python=3.12 pip
echo              conda activate srt-ov2
echo.
echo          Ctrl-C to stop, or any key to install here anyway.
pause >nul
echo.

:update
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
python -m pip install -e ".[%EXTRAS%]"
if errorlevel 1 goto :install_failed
echo.

python -c "import audio_transcriber;print('audio-transcriber',audio_transcriber.__version__,'installed')"
if errorlevel 1 goto :no_import

rem --- the two things that actually break on Windows -------------------------
echo %EXTRAS% | find /i "gui" >nul
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
echo %EXTRAS% | find /i "record" >nul
if errorlevel 1 goto :ready
python -c "import audio_transcriber.recording as r;s=r.sources();print('audio sources:',len(s),'-',sum(1 for x in s if x.is_loopback),'of them loopback')" 2>nul
if errorlevel 1 echo WARNING: the audio libraries did not load; the window will record through Qt only.

:ready
echo.
echo ---------------------------------------------------------------------------
echo  Ready. Things to run:
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
exit /b 1

:no_python
echo ERROR: no "python" on PATH. Open the Anaconda Prompt and activate the
echo        environment first:
echo            conda activate srt-ov2
exit /b 1

:too_old
echo ERROR: Python 3.11 or newer is required, this is %PYVER%.
echo        Make an environment where conda provides only the interpreter:
echo            conda create -n srt-ov2 python=3.12 pip
echo            conda activate srt-ov2
exit /b 1

:pull_failed
echo ERROR: git pull failed. Sort that out first - your local changes are
echo        untouched, and nothing has been installed.
exit /b 1

:install_failed
echo.
echo ERROR: the install failed. Two failures are common here:
echo.
echo   "Cannot uninstall shiboken6 ... no RECORD file was found"
echo       Qt came from conda. Take it out of conda's hands first, in this
echo       order and never the other way round:
echo           conda remove pyside6 shiboken6
echo           install.cmd %EXTRAS%
echo.
echo   a wheel that is missing or will not build for this Python
echo       Try Python 3.12 in a fresh environment: the heavier dependencies
echo       lag a new Python release by months.
exit /b 1

:no_import
echo ERROR: installed, but "import audio_transcriber" does not work. Nothing
echo        else will until that is explained - the output above says why.
exit /b 1

:end
endlocal
