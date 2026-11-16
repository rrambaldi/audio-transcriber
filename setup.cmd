@echo off
rem SPDX-FileCopyrightText: 2026 Roberto Rambaldi
rem SPDX-License-Identifier: MIT
rem The Gratitude & Random Kindness License: MIT, with a wish. See LICENSE.

rem ---------------------------------------------------------------------------
rem  audio-transcriber - install it on Windows, starting from nothing
rem
rem  For somebody with no Python, no conda and no git: this one file is all
rem  they download, and a double-click is all they do. It looks at the PC,
rem  says whether it is suited to summaries, asks one question - transcription
rem  only, or summaries too - then fetches the rest from the internet and
rem  opens the window:
rem
rem    uv                  one program, which brings its own Python 3.12
rem    audio-transcriber   from GitHub, with the window and the engine for
rem                        this PC: CUDA on an NVIDIA card it can use,
rem                        OpenVINO everywhere else
rem    llama.cpp + model   with summaries only: llama-server, and the model
rem                        this PC's memory can hold (about 4 GB on most)
rem
rem  A couple of gigabytes in all before the model, and no question after
rem  the first one, so it can be left to run. Everything goes into
rem  %LOCALAPPDATA%\Programs\audio-transcriber: no administrator rights,
rem  nothing on the PATH, nothing shared with a Python or a conda that is
rem  already there. It adds "Audio Transcriber" to the Start menu, to the
rem  desktop and to Settings, Apps, which is where it is removed from again.
rem
rem      setup.cmd               install, or add summaries later
rem      setup.cmd /uninstall    remove the program; recordings, models and
rem                              settings stay where they are
rem
rem  The copy attached to a release installs that release, and updating is
rem  running the newest one, from the link below; the copy in the repository
rem  installs main. AT_REF picks anything else: a branch or a tag.
rem
rem      https://github.com/rrambaldi/audio-transcriber/releases/latest/download/setup.cmd
rem
rem  Working on the code? install.cmd is the one for a checkout: editable,
rem  into a conda environment.
rem
rem  The control flow is flat on purpose - cmd parses parentheses inside a
rem  quoted one-liner as block delimiters.
rem ---------------------------------------------------------------------------

setlocal
set "AT_HOME=%LOCALAPPDATA%\Programs\audio-transcriber"
set "AT_KEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\audio-transcriber"
set "AT_LNK_NAME=Audio Transcriber.lnk"
set "AT_LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\%AT_LNK_NAME%"
rem The desktop one is a PowerShell expression, not a path: where the desktop
rem is gets asked of Windows, as OneDrive often moves it away from
rem %USERPROFILE%\Desktop.
set "AT_DESKTOP_LINK=(Join-Path ([Environment]::GetFolderPath('Desktop')) $env:AT_LNK_NAME)"
set "CURL=%SystemRoot%\System32\curl.exe"
set "TAR=%SystemRoot%\System32\tar.exe"

rem Double-clicked, from Settings, Apps, or from a prompt? The first two close
rem the console with the script, so an error or a warning waits for a key.
set "AT_CLICKED="
set "AT_WARNED="
echo %cmdcmdline% | findstr /i /c:"/c" >nul 2>nul && set "AT_CLICKED=1"

if /i "%~1"=="/uninstall" goto :uninstall

if "%AT_REF%"=="" set "AT_REF=main"
set "AT_ARCHIVE=https://github.com/rrambaldi/audio-transcriber/archive/%AT_REF%.zip"
set "AT_PACKAGE=audio-transcriber-ov"
rem What is downloaded and run is pinned, and checked against the hash taken
rem when it was pinned: a new release of either cannot reach an installation
rem before somebody has looked at it. Moving one on means both lines.
set "AT_UV_VERSION=0.13.8"
set "AT_UV_SHA256=529e78a9cec6cd7e3e014f7ecd8bda0c113969d4ed0f2efeedb85c30943325b8"
rem Spark-X2.5, the model a PC with 8 GB or more gets, is the architecture
rem "spark2_5", which llama.cpp reads from build 10828 on. The Vulkan build
rem runs on the Intel iGPU where there is one and on the processor where not.
set "AT_LLAMA_BUILD=10828"
set "AT_LLAMA_ZIP=llama-b%AT_LLAMA_BUILD%-bin-win-vulkan-x64.zip"
set "AT_LLAMA_SHA256=c8e8252564713b26ca55902fe1e3dd24d0dd5b8009726f96b773a9f3533d8ec7"

rem uv keeps its Python and its download cache inside the install folder, so
rem removing that one folder removes all of it.
set "UV_PYTHON_INSTALL_DIR=%AT_HOME%\python"
set "UV_CACHE_DIR=%AT_HOME%\cache"
set "UV=%AT_HOME%\uv\uv.exe"
set "PY=%AT_HOME%\venv\Scripts\python.exe"
set "PYW=%AT_HOME%\venv\Scripts\pythonw.exe"
set "AT_LLAMA=%AT_HOME%\venv\llama.cpp"

echo.
echo  audio-transcriber - setup
echo  into %AT_HOME%
echo.

if /i "%PROCESSOR_ARCHITECTURE%"=="AMD64" goto :arch_ok
if /i "%PROCESSOR_ARCHITEW6432%"=="AMD64" goto :arch_ok
goto :not_x64
:arch_ok
if not exist "%CURL%" goto :no_curl
if not exist "%TAR%" goto :no_curl
if not exist "%AT_HOME%" mkdir "%AT_HOME%"

rem --- uv ----------------------------------------------------------------------
echo [1/6] uv
if exist "%UV%" goto :uv_ready
if not exist "%AT_HOME%\uv" mkdir "%AT_HOME%\uv"
"%CURL%" -L --fail --progress-bar -o "%AT_HOME%\uv\uv.zip" "https://github.com/astral-sh/uv/releases/download/%AT_UV_VERSION%/uv-x86_64-pc-windows-msvc.zip"
if errorlevel 1 goto :download_failed
call :verify "%AT_HOME%\uv\uv.zip" %AT_UV_SHA256%
if errorlevel 1 goto :hash_failed
"%TAR%" -xf "%AT_HOME%\uv\uv.zip" -C "%AT_HOME%\uv"
if errorlevel 1 goto :download_failed
del "%AT_HOME%\uv\uv.zip"
if not exist "%UV%" goto :download_failed
:uv_ready

rem --- Python, uv's own ---------------------------------------------------------
rem Never one already on the PC: a conda Python puts its own Qt ahead of the
rem one pip installs, and the window then dies loading QtCore.
rem The environment is whole only with pythonw.exe beside python.exe: an
rem antivirus may take pythonw away - a program with no window, run from
rem AppData - and an environment kept as it is would never get it back. Made
rem again, the packages come from the cache, and llama.cpp inside it from
rem GitHub when summaries are chosen.
echo [2/6] Python 3.12
if not exist "%PY%" goto :venv_make
if exist "%PYW%" goto :venv_ready
echo        pythonw.exe is missing from the environment: making it again
:venv_make
"%UV%" venv --clear --python 3.12 --python-preference only-managed "%AT_HOME%\venv"
if errorlevel 1 goto :python_failed
:venv_ready

rem --- the program, the light part: enough to look at this PC ----------------
echo [3/6] audio-transcriber (%AT_REF%)
"%UV%" pip install --python "%PY%" --refresh-package %AT_PACKAGE% --reinstall-package %AT_PACKAGE% "%AT_PACKAGE% @ %AT_ARCHIVE%"
if errorlevel 1 goto :install_failed

rem --- this PC, and the one question -------------------------------------------
rem Asked by the program, in the PC's own language, after it has said what
rem it thinks of the PC. Exit status 10: transcription only; 11: summaries.
echo.
"%PY%" -m audio_transcriber.cli setup choose
set "AT_CHOICE=%ERRORLEVEL%"
echo.
set "AT_SUMMARY="
if "%AT_CHOICE%"=="11" set "AT_SUMMARY=1"
if "%AT_CHOICE%"=="11" goto :choice_made
if "%AT_CHOICE%"=="10" goto :choice_made
goto :choice_failed
:choice_made

rem --- the engine and the window: the long download ---------------------------
rem Which engine is the program's answer, from what the NVIDIA driver told it:
rem one line, the extras - "cuda,..." for a card it can use, "openvino,..."
rem for every other PC. An NVIDIA card gets no OpenVINO it would never use.
set "AT_EXTRAS="
for /f "delims=" %%e in ('call "%PY%" -m audio_transcriber.cli setup extras') do set "AT_EXTRAS=%%e"
if "%AT_EXTRAS%"=="" goto :extras_failed
echo [4/6] the engine and the window [%AT_EXTRAS%] - a few gigabytes, give it time
"%UV%" pip install --python "%PY%" "%AT_PACKAGE%[%AT_EXTRAS%] @ %AT_ARCHIVE%"
if errorlevel 1 goto :install_failed

rem --- summaries: llama-server beside the environment, and the model ---------
rem The program looks for it in venv\llama.cpp, so it needs no PATH and no
rem configuration, and its DLLs stay out of Python's way.
if not defined AT_SUMMARY goto :register
echo [5/6] llama.cpp b%AT_LLAMA_BUILD%
if exist "%AT_LLAMA%\b%AT_LLAMA_BUILD%.build" goto :llama_ready
"%CURL%" -L --fail --progress-bar -o "%AT_HOME%\llama.zip" "https://github.com/ggml-org/llama.cpp/releases/download/b%AT_LLAMA_BUILD%/%AT_LLAMA_ZIP%"
if errorlevel 1 goto :download_failed
call :verify "%AT_HOME%\llama.zip" %AT_LLAMA_SHA256%
if errorlevel 1 goto :hash_failed
if exist "%AT_LLAMA%" rmdir /s /q "%AT_LLAMA%"
mkdir "%AT_LLAMA%"
"%TAR%" -xf "%AT_HOME%\llama.zip" -C "%AT_LLAMA%"
if errorlevel 1 goto :download_failed
del "%AT_HOME%\llama.zip"
if not exist "%AT_LLAMA%\llama-server.exe" goto :download_failed
type nul > "%AT_LLAMA%\b%AT_LLAMA_BUILD%.build"
:llama_ready
echo [6/6] the summary model
"%PY%" -m audio_transcriber.cli setup summary
if errorlevel 1 goto :model_failed

rem --- Settings, Apps first, then the Start menu and the desktop ------------------
rem In that order so that a shortcut that cannot be made - PowerShell
rem locked down by a policy - still leaves a program that can be removed.
rem A copy of this file stays in the install folder: it is what Settings,
rem Apps runs to remove the program, and what updates it later.
:register
set "AT_ICON=%AT_HOME%\venv\Lib\site-packages\audio_transcriber\data\brand\favicon.ico"
if /i not "%~f0"=="%AT_HOME%\setup.cmd" copy /y "%~f0" "%AT_HOME%\setup.cmd" >nul
set "AT_VERSION="
for /f "delims=" %%v in ('call "%PY%" -c "import audio_transcriber;print(audio_transcriber.__version__)"') do set "AT_VERSION=%%v"
reg add "%AT_KEY%" /v DisplayName /d "Audio Transcriber" /f >nul
reg add "%AT_KEY%" /v DisplayVersion /d "%AT_VERSION%" /f >nul
reg add "%AT_KEY%" /v DisplayIcon /d "%AT_ICON%" /f >nul
reg add "%AT_KEY%" /v Publisher /d "Roberto Rambaldi" /f >nul
reg add "%AT_KEY%" /v InstallLocation /d "%AT_HOME%" /f >nul
reg add "%AT_KEY%" /v UninstallString /d "\"%AT_HOME%\setup.cmd\" /uninstall" /f >nul
reg add "%AT_KEY%" /v NoModify /t REG_DWORD /d 1 /f >nul
reg add "%AT_KEY%" /v NoRepair /t REG_DWORD /d 1 /f >nul

rem pythonw: the window without a console behind it. The working folder is
rem the user's own, never the program's - a whisper-ov-models folder in the
rem working folder would win over the managed models. Still missing here,
rem after step 2 made it, means something removes it: neither the Start menu
rem entry nor the window below could start, so nothing is made or run.
if not exist "%PYW%" goto :pythonw_missing
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $w=New-Object -ComObject WScript.Shell; foreach ($p in @($env:AT_LINK, %AT_DESKTOP_LINK%)) { $s=$w.CreateShortcut($p); $s.TargetPath=$env:PYW; $s.Arguments='-m audio_transcriber.cli gui'; $s.WorkingDirectory=$env:USERPROFILE; $s.IconLocation=$env:AT_ICON; $s.Description='Audio Transcriber'; $s.Save() }"
if errorlevel 1 goto :shortcut_failed

:done
echo.
echo ---------------------------------------------------------------------------
echo  Done: audio-transcriber %AT_VERSION%
echo.
echo  Start menu or desktop  ^>  Audio Transcriber
echo.
echo  The first transcription downloads and converts its Whisper model, once:
echo  a few minutes before the first line appears.
echo  Add summaries later: run this file again.
echo  Update: run the newest setup.cmd, from
echo    https://github.com/rrambaldi/audio-transcriber/releases/latest
echo  Remove: Settings ^> Apps ^> Audio Transcriber.
echo ---------------------------------------------------------------------------

rem The window opens on its own: an installer that ends on a console asking
rem for a key leaves somebody looking for what was installed. The same
rem pythonw and working folder as the Start menu entry.
start "" /d "%USERPROFILE%" "%PYW%" -m audio_transcriber.cli gui
goto :end

rem --- one downloaded file against the hash it was pinned with -------------------
rem certutil prints the hash on a line of its own; find answers whether it
rem is the one expected. A file that does not match is deleted, not kept.
:verify
"%SystemRoot%\System32\certutil.exe" -hashfile "%~1" SHA256 | find /i "%~2" >nul
if not errorlevel 1 exit /b 0
del "%~1"
exit /b 1

rem --- removing it ----------------------------------------------------------------
rem cmd reads a batch file while it runs it, so one cannot delete the folder it
rem is running from: a copy in %TEMP% does the removing, and deletes itself.
:uninstall
if /i "%~2"=="/from-temp" goto :remove
copy /y "%~f0" "%TEMP%\audio-transcriber-uninstall.cmd" >nul
"%TEMP%\audio-transcriber-uninstall.cmd" /uninstall /from-temp

:remove
echo.
echo  Removing audio-transcriber from %AT_HOME%
if exist "%AT_LINK%" del "%AT_LINK%"
powershell -NoProfile -Command "$p=%AT_DESKTOP_LINK%; if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p }"
reg delete "%AT_KEY%" /f >nul 2>nul
if exist "%AT_HOME%" rmdir /s /q "%AT_HOME%"
if exist "%AT_HOME%" goto :remove_failed
echo.
echo  Removed. What is yours stays, to be deleted by hand if it is not wanted:
echo    recordings and models   %LOCALAPPDATA%\audio-transcriber
echo    settings                %APPDATA%\audio-transcriber
if defined AT_CLICKED pause
(goto) 2>nul & del "%~f0"

:remove_failed
echo.
echo ERROR: some files are in use - Audio Transcriber is probably open. Close
echo        it and remove it again from Settings ^> Apps.
if defined AT_CLICKED pause
(goto) 2>nul & del "%~f0"

rem --- what went wrong ------------------------------------------------------------

:not_x64
echo ERROR: this needs 64-bit Windows on an Intel or AMD processor. The
echo        engines it installs are not published for anything else.
goto :failed

:no_curl
echo ERROR: curl.exe and tar.exe are missing from %SystemRoot%\System32. They
echo        come with Windows 10 from version 1803 on: update Windows first.
goto :failed

:download_failed
echo.
echo ERROR: a download did not complete. Check the internet connection - a
echo        company proxy or firewall can block GitHub - and run this again:
echo        what is already installed is not downloaded a second time.
goto :failed

:hash_failed
echo.
echo ERROR: a download is not the file this installer was written for - its
echo        SHA256 does not match - so it was deleted and nothing was run.
echo        Run this again; if it happens again, the release on GitHub has
echo        changed and this installer has to be updated first.
goto :failed

:python_failed
echo.
echo ERROR: uv could not make the Python 3.12 environment. If Audio
echo        Transcriber is open, close it - an environment in use cannot be
echo        made again - and run this again. Otherwise the lines above say
echo        why; it is almost always the connection.
goto :failed

:install_failed
echo.
echo ERROR: the install did not complete. If Audio Transcriber is open, close
echo        it - Windows will not replace a program that is running - and run
echo        this again. Otherwise the lines above say why.
goto :failed

:extras_failed
echo ERROR: the program could not say which engine suits this PC. The lines
echo        above say why.
goto :failed

:choice_failed
echo ERROR: the program installed but did not start (code %AT_CHOICE%). The
echo        lines above say why.
goto :failed

:model_failed
echo.
echo WARNING: transcription is installed, the summary model is not - the
echo          lines above say why. Run this again and choose summaries to
echo          finish; until then the program has summaries switched off.
set "AT_WARNED=1"
goto :register

:shortcut_failed
echo WARNING: the shortcuts, in the Start menu and on the desktop, could not
echo          all be made. The program is there:
echo              "%PYW%" -m audio_transcriber.cli gui
set "AT_WARNED=1"
goto :done

:pythonw_missing
echo.
echo ERROR: everything is installed but pythonw.exe, the file that opens the
echo        window, is missing from %AT_HOME%\venv\Scripts.
echo        An antivirus has most likely removed it. Look in Windows Security
echo        ^> Virus ^& threat protection ^> Protection history, or in the
echo        history of the antivirus this PC uses: restore the file, exclude
echo        %AT_HOME% from scanning, then run this again.
echo        Until then the window opens with a console behind it:
echo          "%PY%" -m audio_transcriber.cli gui
goto :failed

:failed
if defined AT_CLICKED pause
endlocal & exit /b 1

rem After a clean install the open window is the answer and the console may
rem close; after a warning it stays until the warning has been read.
:end
if defined AT_WARNED if defined AT_CLICKED pause
endlocal & exit /b 0
