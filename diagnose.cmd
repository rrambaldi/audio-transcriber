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
rem  A Vulkan build older than the round needs (AT_NEED_BUILD, below) is not
rem  replaced: the one that is needed is fetched once from the llama.cpp
rem  releases on GitHub into %AT_LLAMA_DIR%\vulkan-bNNNNN, and used instead.
rem
rem  At the end the files of the round - numbers and pages - go to the server,
rem  into the same folder of the checkout there, with the scp that ships with
rem  Windows. When the round has been measured here already, it asks first:
rem  R runs it again, S only sends what there is.
rem
rem      set AT_SERVER=me@another.host
rem      set AT_PORT=22
rem      set AT_SERVER_DIR=/where/they/go
rem      set AT_SERVER=none              keep them here
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
set "AT_SENT="
set "AT_FOUND="
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

rem --- a round that has been measured already --------------------------------
rem Measuring is the better part of an hour and sending is seconds, so when the
rem files of this round are here already the choice is asked for, not made.
set "AT_MODE=check"
call :round
if not defined AT_FOUND goto :measuring
echo.
echo === this round has been measured here already:%AT_FOUND%
echo     R  run it again - those files are replaced
echo     S  only send them to the server
choice /c RS /n /m "  R or S? "
if errorlevel 2 goto :sending_only

:measuring
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

rem --- a build new enough for this round --------------------------------------
rem Spark-X2.5 is the architecture "spark2_5", which llama.cpp reads from build
rem 10828 on; an older build refuses the file when it loads it. Every run of
rem the round then uses the newer build, the control included - two runs on two
rem builds would be two things changed.
rem
rem curl and tar are named in System32 because conda puts its own on PATH, and
rem conda's tar does not open a zip.
set "AT_NEED_BUILD=10828"
if "%AT_LLAMA_VULKAN%"=="" goto :build_ok
call :build_of "%AT_LLAMA_VULKAN%"
echo.
echo === the Vulkan build is %AT_BUILD%; this round needs %AT_NEED_BUILD% or later
if %AT_BUILD% GEQ %AT_NEED_BUILD% goto :build_ok
set "AT_NEWER=%AT_LLAMA_DIR%\vulkan-b%AT_NEED_BUILD%"
if exist "%AT_NEWER%\llama-server.exe" goto :build_newer
set "AT_ZIP=llama-b%AT_NEED_BUILD%-bin-win-vulkan-x64.zip"
echo   fetching %AT_ZIP% into %AT_NEWER%
if not exist "%AT_NEWER%" mkdir "%AT_NEWER%"
"%SystemRoot%\System32\curl.exe" -L --fail -o "%AT_NEWER%\%AT_ZIP%" "https://github.com/ggml-org/llama.cpp/releases/download/b%AT_NEED_BUILD%/%AT_ZIP%"
if errorlevel 1 goto :fetch_failed
"%SystemRoot%\System32\tar.exe" -xf "%AT_NEWER%\%AT_ZIP%" -C "%AT_NEWER%"
if errorlevel 1 goto :fetch_failed
del "%AT_NEWER%\%AT_ZIP%"
if not exist "%AT_NEWER%\llama-server.exe" goto :fetch_failed
:build_newer
set "AT_LLAMA_VULKAN=%AT_NEWER%\llama-server.exe"
echo   using %AT_LLAMA_VULKAN%
:build_ok

echo.
echo === what each build can see
call :devices "vulkan" "%AT_LLAMA_VULKAN%"
call :devices "openvino" "%AT_LLAMA_OPENVINO%"

set "AT_MODE=run"
call :round

echo.
echo === done. These are this round's, and carry no meeting in them:
echo  %AT_MADE%
goto :send

:sending_only
set "AT_MODE=send"
call :round

rem --- the files of the round, to the server ---------------------------------
rem Both files of each run, pages included: they go to the machine the
rem recording came from and to no other. If ssh asks for a password, or for a
rem first "yes" to a host it has not met, answer it here.
:send
if "%AT_SERVER%"=="" set "AT_SERVER=rrambaldi@www.progettazionisoftware.it"
if "%AT_PORT%"=="" set "AT_PORT=3722"
if "%AT_SERVER_DIR%"=="" set "AT_SERVER_DIR=/home/rrambaldi/progetti/audio-transcriber/audio-transcriber/.local/summary"
if /i "%AT_SERVER%"=="none" goto :done
if not defined AT_SENT goto :done
echo.
echo === sending them to %AT_SERVER%
"%SystemRoot%\System32\OpenSSH\scp.exe" -P %AT_PORT% %AT_SENT% "%AT_SERVER%:%AT_SERVER_DIR%/"
if errorlevel 1 goto :send_failed
echo   sent: on the server they are in %AT_SERVER_DIR%
goto :done

:send_failed
echo   WARNING: they did not get there - the lines above say why. They are
echo   still here, in %AT_OUT%. To try again without measuring: run this
echo   again and answer S.

:done
if not defined AT_CLICKED goto :quit
echo.
pause
:quit
endlocal & exit /b 0

rem --- the routines -----------------------------------------------------------

rem --- the runs this round ---------------------------------------------------
rem What the last two rounds settled, on the same recording:
rem
rem   Granite 4.0 H-Tiny Q4   240 s   coverage 95%   18 of 21 facts, one invented
rem   Spark-X2.5-4B Q4        415 s   coverage 91%   17 of 21, verbose, garbled
rem   Spark, 800 per pass     556 s   coverage 91%   17 of 21, only longer
rem   Spark-X2.5-4B Q8   1990 s   coverage 95%   20 of 21, nothing invented
rem
rem Spark at Q4 is out. Spark at Q8 wrote the best page of all, and is now
rem what the plan chooses on llama.cpp: slower, and worth it.
rem
rem This round measures the read-back, "--review": once the page is written
rem the model reads every section again beside its notes and lists at the
rem foot, under "Da ricontrollare", the lines it doubts - one the notes do
rem not say, one that repeats another, one that does not read as a sentence.
rem What to look at: how many minutes it adds, and whether what it lists is
rem right. The pages of Z3 are the same pages without it, to compare.
rem
rem  Z4-spark-review     Spark-X2.5-4B at Q8_0, read back by itself
rem  Z4-granite-review   Granite 4.0 H-Tiny at Q4_K_M, read back by itself
rem
rem Both in the largest size class, "--tier l", whatever memory is free.
rem
rem Before each run, if more free memory would change it - a better model
rem for a run left to the plan, or room for a named one that does not fit -
rem the run stops, says how much, and asks: close things and press Enter to
rem check again, or type G to go on as it is. A machine that swaps measures
rem the swapping.
rem
rem Each run clears the cached passes first, so each one reads the recording.
rem
rem To ask a new question, edit these lines. Everything else stays as it is.
:round
call :measure "Z4-spark-review" "%AT_LLAMA_VULKAN%" "--tier l --model Spark-X2.5-4B --quant Q8_0 --review"
call :measure "Z4-granite-review" "%AT_LLAMA_VULKAN%" "--tier l --model ibm-granite/granite-4.0-h-tiny --review"
goto :eof

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
rem
rem Nothing is asked for here that the program would not do on its own, bar
rem the engine and the binary - a run whose every setting is spelled out on
rem the command line measures the command line. "--shape headings" and the
rem rest go in the third argument, per run.
if "%AT_MODE%"=="check" goto :measure_check
if "%AT_MODE%"=="send" goto :measure_keep
if "%~2"=="" goto :measure_skipped
echo.
echo === %~1 - starting at %TIME%
rem The files of an earlier run of the same name go first: a run that stops
rem before writing must not leave them behind to be sent as its own.
if exist "%AT_OUT%\%~1.numbers.json" del "%AT_OUT%\%~1.numbers.json"
if exist "%AT_OUT%\%~1.page.md" del "%AT_OUT%\%~1.page.md"
python tools\diagnose_summary.py "%AT_SRT%" --out "%AT_OUT%\%~1" --engine llamacpp --llama-server "%~2" %~3
if errorlevel 1 echo   %~1: this run did not finish - the lines above say why.
echo === %~1 - finished at %TIME%

:measure_keep
rem What there is of one run, for the server.
if not exist "%AT_OUT%\%~1.numbers.json" goto :measure_page
set "AT_MADE=%AT_MADE% %AT_OUT%\%~1.numbers.json"
set AT_SENT=%AT_SENT% "%AT_OUT%\%~1.numbers.json"
:measure_page
if exist "%AT_OUT%\%~1.page.md" set AT_SENT=%AT_SENT% "%AT_OUT%\%~1.page.md"
goto :eof

:measure_check
if exist "%AT_OUT%\%~1.numbers.json" set "AT_FOUND=%AT_FOUND% %~1"
goto :eof

:measure_skipped
echo.
echo === %~1: skipped, that build is not installed.
goto :eof

:build_of
rem The build number of one llama-server. A recent one says
rem "version: 0.4.0-dev (build 10828, commit 3ad1ba733)", an older one
rem "version: 6123 (abc1234)"; both come out as the number. Through a file,
rem because a quoted path inside for /f's command is where cmd's quoting breaks.
set "AT_BUILD="
"%~1" --version > "%TEMP%\at-llama-version.txt" 2>&1
findstr /b /c:"version:" "%TEMP%\at-llama-version.txt" > "%TEMP%\at-llama-build.txt"
for /f "usebackq tokens=2,3,4 delims=(), " %%A in ("%TEMP%\at-llama-build.txt") do call :build_words %%A %%B %%C
if "%AT_BUILD%"=="" set "AT_BUILD=0"
goto :eof

:build_words
set "AT_BUILD=%~1"
if "%~2"=="build" set "AT_BUILD=%~3"
goto :eof

rem --- what went wrong --------------------------------------------------------

:fetch_failed
echo ERROR: could not fetch llama.cpp build %AT_NEED_BUILD% into
echo        %AT_NEWER%. The lines above say why; nothing was measured.
echo.
echo        By hand: download llama-b%AT_NEED_BUILD%-bin-win-vulkan-x64.zip from
echo        https://github.com/ggml-org/llama.cpp/releases, unzip it into that
echo        folder, and run this again.
goto :failed

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
