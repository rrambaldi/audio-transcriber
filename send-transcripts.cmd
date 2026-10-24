@echo off
rem SPDX-FileCopyrightText: 2026 Roberto Rambaldi
rem SPDX-License-Identifier: MIT
rem The Gratitude & Random Kindness License: MIT, with a wish. See LICENSE.

rem ---------------------------------------------------------------------------
rem  audio-transcriber - send a folder of transcripts kept for measuring to
rem  the server
rem
rem      send-transcripts.cmd
rem      send-transcripts.cmd .local\another-folder
rem
rem  The folder - by default .local\new-summary: transcripts, each with the
rem  summary it should come close to - goes whole into .local of the checkout
rem  on the server, where the measurements are worked out. Under .local git
rem  never sees it, here or there. Sending it again replaces what is there.
rem
rem  The server is the one diagnose.cmd sends its rounds to, and the same
rem  variables move it:
rem
rem      set AT_SERVER=me@another.host
rem      set AT_PORT=22
rem      set AT_SERVER_DIR=/where/it/goes
rem
rem  If ssh asks for a password, or for a first "yes" to a host it has not
rem  met, answer it here.
rem ---------------------------------------------------------------------------

cd /d "%~dp0"
setlocal

set "AT_CLICKED="
echo %cmdcmdline% | findstr /i /c:"/c" >nul 2>nul && set "AT_CLICKED=1"

if not exist "pyproject.toml" goto :wrong_folder

set "AT_FOLDER=%~1"
if "%AT_FOLDER%"=="" set "AT_FOLDER=.local\new-summary"
if not exist "%AT_FOLDER%" goto :no_folder

if "%AT_SERVER%"=="" set "AT_SERVER=rrambaldi@www.progettazionisoftware.it"
if "%AT_PORT%"=="" set "AT_PORT=3722"
if "%AT_SERVER_DIR%"=="" set "AT_SERVER_DIR=/home/rrambaldi/progetti/audio-transcriber/audio-transcriber/.local"

echo.
echo === sending %AT_FOLDER% to %AT_SERVER%
"%SystemRoot%\System32\OpenSSH\scp.exe" -r -P %AT_PORT% "%AT_FOLDER%" "%AT_SERVER%:%AT_SERVER_DIR%/"
if errorlevel 1 goto :send_failed
echo   sent: on the server it is under %AT_SERVER_DIR%
goto :done

:send_failed
echo   WARNING: it did not get there - the lines above say why.
goto :failed

:wrong_folder
echo ERROR: run this from the audio-transcriber checkout - the folder that
echo        holds pyproject.toml.
goto :failed

:no_folder
echo ERROR: no folder at "%AT_FOLDER%".
echo.
echo        Name one: send-transcripts.cmd path\to\folder
goto :failed

:done
if not defined AT_CLICKED goto :quit
echo.
pause
:quit
endlocal & exit /b 0

:failed
if not defined AT_CLICKED goto :quit_failed
echo.
pause
:quit_failed
endlocal & exit /b 1
