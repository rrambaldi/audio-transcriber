@echo off
rem SPDX-FileCopyrightText: 2026 Roberto Rambaldi
rem SPDX-License-Identifier: MIT
rem The Gratitude & Random Kindness License: MIT, with a wish. See LICENSE.

rem ---------------------------------------------------------------------------
rem  audio-transcriber - run it on Windows, in the right environment
rem
rem  The window, with no arguments - which is also what a double-click from
rem  Explorer does:
rem
rem      run.cmd
rem
rem  Anything else is passed straight through to the program:
rem
rem      run.cmd hardware
rem      run.cmd meeting.mp4 --lang it --summary
rem      run.cmd web
rem      run.cmd --help
rem
rem  Two things it saves doing by hand every time: getting into the conda
rem  environment ("srt-ov2", or AT_ENV), and finding the program when this
rem  environment's Scripts folder is not on PATH - the module form is used
rem  then, which always works.
rem
rem  Unlike install.cmd there is a setlocal here, and the difference is the
rem  point: an installer is meant to leave the window in the environment it
rem  installed into, a launcher is meant to leave the window as it found it.
rem
rem  The control flow is flat because cmd parses parentheses inside a quoted
rem  argument as block delimiters, and the arguments here are the user's.
rem ---------------------------------------------------------------------------

cd /d "%~dp0"
setlocal
if "%AT_ENV%"=="" set "AT_ENV=srt-ov2"

rem Double-clicked from Explorer, or run from a prompt? The console closes with
rem the script in the first case, so an error would flash past unread. This is
rem the only thing that answer is used for.
set "AT_CLICKED="
echo %cmdcmdline% | findstr /i /c:"/c" >nul 2>nul && set "AT_CLICKED=1"

if not exist "pyproject.toml" goto :wrong_folder

rem --- the environment -------------------------------------------------------
if /i "%CONDA_DEFAULT_ENV%"=="%AT_ENV%" goto :env_ready
where conda >nul 2>nul
if errorlevel 1 goto :no_conda
call conda activate %AT_ENV%
if /i not "%CONDA_DEFAULT_ENV%"=="%AT_ENV%" goto :no_env

:env_ready
where python >nul 2>nul
if errorlevel 1 goto :no_python

rem --- the program ------------------------------------------------------------
rem The console entry point when pip put it somewhere on PATH, the module when
rem it did not. They are the same program; only the spelling differs.
set "AT_RUN=python -m audio_transcriber.cli"
where audio-transcriber >nul 2>nul
if not errorlevel 1 set "AT_RUN=audio-transcriber"

if "%~1"=="" goto :window
%AT_RUN% %*
goto :done

:window
rem No arguments means the window. It is what a double-click should do, and
rem what somebody who wanted a command line would not have left empty.
%AT_RUN% gui

:done
set "AT_CODE=%ERRORLEVEL%"
if not "%AT_CODE%"=="0" if defined AT_CLICKED echo. & pause
endlocal & exit /b %AT_CODE%

rem --- what went wrong --------------------------------------------------------

:wrong_folder
echo ERROR: run this from the audio-transcriber checkout - the folder that
echo        holds pyproject.toml.
goto :failed

:no_conda
echo ERROR: no "conda" on PATH, so the "%AT_ENV%" environment cannot be
echo        entered. The Anaconda Prompt is a shell that has it; a plain
echo        Command Prompt usually does not.
echo.
echo        Already in an environment with audio-transcriber installed? Then
echo        this script is not needed: run "audio-transcriber gui" directly.
goto :failed

:no_env
echo ERROR: could not get into the "%AT_ENV%" environment. Either it does not
echo        exist, or this shell has never been initialised for conda.
echo.
echo        To make it and install into it:
echo            conda create -n %AT_ENV% python=3.12 pip
echo            install.cmd
echo.
echo        Another name: set AT_ENV=myenv before running this.
goto :failed

:no_python
echo ERROR: no "python" on PATH, even in "%CONDA_DEFAULT_ENV%". That
echo        environment is broken; making it again is faster than repairing it.
goto :failed

:failed
if defined AT_CLICKED echo. & pause
endlocal & exit /b 1
