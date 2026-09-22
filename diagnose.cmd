@echo off
rem SPDX-FileCopyrightText: 2026 Roberto Rambaldi
rem SPDX-License-Identifier: MIT
rem The Gratitude & Random Kindness License: MIT, with a wish. See LICENSE.

rem ---------------------------------------------------------------------------
rem  audio-transcriber - measure the same recording on every device this
rem  machine has, in one go
rem
rem      diagnose.cmd
rem      diagnose.cmd .local\summary\gold.srt
rem      diagnose.cmd .local\summary\gold.srt .local\summary
rem
rem  It pulls, finds whichever builds of llama-server are installed, asks each
rem  one what it can see, and then makes the measurements of the round: the
rem  same recording, summarised once per thing being tried.
rem
rem  The list of runs is the block marked "the runs this round", and it is
rem  meant to be edited between rounds. The rule it exists to enforce: between
rem  two runs exactly one thing changes, or the two cannot be compared.
rem
rem  Each run leaves two files. "<name>.numbers.json" is numbers and nothing
rem  else, safe to send to anybody; "<name>.page.md" is the summary itself and
rem  stays with the transcript it was made from.
rem
rem  Where the builds are looked for: C:\llama\*vulkan*\llama-server.exe and
rem  C:\llama\*openvino*\llama-server.exe. Somewhere else:
rem
rem      set AT_LLAMA_DIR=D:\tools\llama
rem      set AT_LLAMA_VULKAN=D:\tools\llama\b1234\llama-server.exe
rem
rem  A build that is not there is reported and skipped rather than failing the
rem  run: one device measured is worth more than three not measured.
rem
rem  The control flow is flat and the runs go through a subroutine, because
rem  cmd parses the parentheses in a device description as block delimiters.
rem ---------------------------------------------------------------------------

cd /d "%~dp0"
setlocal
if "%AT_ENV%"=="" set "AT_ENV=srt-ov2"

set "AT_CLICKED="
echo %cmdcmdline% | findstr /i /c:"/c" >nul 2>nul && set "AT_CLICKED=1"

if not exist "pyproject.toml" goto :wrong_folder

rem --- what to summarise, and where the answers go ---------------------------
set "AT_SRT=%~1"
if "%AT_SRT%"=="" set "AT_SRT=.local\summary\gold.srt"
if not exist "%AT_SRT%" goto :no_transcript

set "AT_MADE="
set "AT_OUT=%~2"
if "%AT_OUT%"=="" set "AT_OUT=.local\summary"
if not exist "%AT_OUT%" mkdir "%AT_OUT%"

rem --- the environment -------------------------------------------------------
if /i "%CONDA_DEFAULT_ENV%"=="%AT_ENV%" goto :env_ready
where conda >nul 2>nul
if errorlevel 1 goto :no_conda
call conda activate %AT_ENV%
if /i not "%CONDA_DEFAULT_ENV%"=="%AT_ENV%" goto :no_env

:env_ready
where python >nul 2>nul
if errorlevel 1 goto :no_python

rem --- the code --------------------------------------------------------------
echo.
echo === bringing the checkout up to date
git pull --ff-only
if errorlevel 1 echo   WARNING: the pull failed. Measuring the code as it is here.

rem --- which builds of llama.cpp are on this machine -------------------------
if "%AT_LLAMA_DIR%"=="" set "AT_LLAMA_DIR=C:\llama"

if not "%AT_LLAMA_VULKAN%"=="" goto :vulkan_known
for /d %%D in ("%AT_LLAMA_DIR%\*vulkan*") do set "AT_LLAMA_VULKAN=%%~fD\llama-server.exe"
:vulkan_known
if not exist "%AT_LLAMA_VULKAN%" set "AT_LLAMA_VULKAN="

if not "%AT_LLAMA_OPENVINO%"=="" goto :openvino_known
for /d %%D in ("%AT_LLAMA_DIR%\*openvino*") do set "AT_LLAMA_OPENVINO=%%~fD\llama-server.exe"
:openvino_known
if not exist "%AT_LLAMA_OPENVINO%" set "AT_LLAMA_OPENVINO="

echo.
echo === what each build can see
call :devices "vulkan" "%AT_LLAMA_VULKAN%"
call :devices "openvino" "%AT_LLAMA_OPENVINO%"

rem --- the runs this round ---------------------------------------------------
rem What was settled in the round before: how much a pass is given to read
rem is the whole game. Halving it, from 4500 tokens to 2000, took the share
rem of the meeting that reaches the page from 36% to 68% - twenty-one notes
rem became fifty-eight - and cost eighty seconds. Nothing else changed.
rem
rem What is being asked now: where that stops paying. 2000 is measured and is
rem the number these two are compared against; each of them halves again, and
rem the last one is a pass reading about two minutes of meeting at a time.
rem Somewhere down here the notes start repeating each other instead of
rem covering more, and the point of the round is to find out where.
call :measure "N-vulkan-1200" "%AT_LLAMA_VULKAN%" "--chunk-tokens 1200"
call :measure "O-vulkan-700" "%AT_LLAMA_VULKAN%" "--chunk-tokens 700"

echo.
echo === done. These are this round's, and carry no meeting in them:
echo  %AT_MADE%

:done
if not defined AT_CLICKED goto :quit
echo.
pause
:quit
endlocal & exit /b 0

rem --- the routines -----------------------------------------------------------

:devices
rem What one build says it can run on, which is the thing to read before the
rem numbers: a build with no backend sees nothing and runs on the cores.
if "%~2"=="" goto :devices_missing
echo   %~1: %~2
"%~2" --list-devices 2>&1 | findstr /v /c:"llama_server"
goto :eof

:devices_missing
echo   %~1: not installed under %AT_LLAMA_DIR%
goto :eof

:measure
rem One run: a name for the files, the binary to run it with, and anything
rem else to say on the command line.
if "%~2"=="" goto :measure_skipped
echo.
echo === %~1 - starting at %TIME%
set "AT_MADE=%AT_MADE% %AT_OUT%\%~1.numbers.json"
python tools\diagnose_summary.py "%AT_SRT%" --out "%AT_OUT%\%~1" --shape sections --engine llamacpp --llama-server "%~2" %~3
if errorlevel 1 echo   %~1: this run did not finish - the lines above say why.
echo === %~1 - finished at %TIME%
goto :eof

:measure_skipped
echo.
echo === %~1: skipped, that build is not installed.
goto :eof

rem --- what went wrong --------------------------------------------------------

:wrong_folder
echo ERROR: run this from the audio-transcriber checkout - the folder that
echo        holds pyproject.toml.
goto :failed

:no_transcript
echo ERROR: no transcript at "%AT_SRT%".
echo.
echo        Name one: diagnose.cmd path\to\meeting.srt
echo        An .srt or .vtt with the minutes in it; a plain transcript works
echo        too, but then nothing can measure how much of the recording the
echo        summary covers, which is half of what this prints.
goto :failed

:no_conda
echo ERROR: no "conda" on PATH, so the "%AT_ENV%" environment cannot be
echo        entered. The Anaconda Prompt is a shell that has it; a plain
echo        Command Prompt usually does not.
goto :failed

:no_env
echo ERROR: could not get into the "%AT_ENV%" environment. Either it does not
echo        exist, or this shell has never been initialised for conda.
echo.
echo        Another name: set AT_ENV=myenv before running this.
goto :failed

:no_python
echo ERROR: no "python" on PATH, even in "%CONDA_DEFAULT_ENV%". That
echo        environment is broken; making it again is faster than repairing it.
goto :failed

:failed
if not defined AT_CLICKED goto :quit_failed
echo.
pause
:quit_failed
endlocal & exit /b 1
