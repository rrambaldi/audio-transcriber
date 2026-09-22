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
rem  one what it can see, and summarises the same transcript on each: the
rem  graphics card through Vulkan, the OpenVINO runtime, and the processor on
rem  its own. Three runs of the same recording are the only way to say which
rem  device is worth using, because a summary is not faster or slower in a
rem  straight line - a bigger context changes what the model is asked, not
rem  only how long it takes.
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

rem --- the three runs --------------------------------------------------------
rem The same transcript, the same shape, three devices. Anything else that
rem differed between them would make the numbers incomparable, which is the
rem one thing a comparison cannot survive.
call :measure "G-vulkan" "%AT_LLAMA_VULKAN%" ""
call :measure "H-openvino" "%AT_LLAMA_OPENVINO%" ""
call :measure "I-cpu" "%AT_LLAMA_VULKAN%" "--device cpu"

echo.
echo === done. These carry no meeting in them and can be sent as they are:
dir /b "%AT_OUT%\*.numbers.json"

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
