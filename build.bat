@echo off
REM ============================================================
REM  build.bat — Package firefox_session_editor.py → .exe
REM  Requirements: pip install pyinstaller pillow lz4
REM ============================================================

setlocal EnableDelayedExpansion

set SCRIPT=firefox_session_editor.py
set ICON=icon.png
set APPNAME=BrowserSessionEditor
set DIST=dist
set BUILD=build

echo.
echo  +----------------------------------------------+
echo  ^|   Browser Session Editor - PyInstaller Build ^|
echo  +----------------------------------------------+
echo.

REM ── Check Python ────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH. Install Python 3.9+ first.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [INFO] Using %%v

REM ── Check / install PyInstaller ─────────────────────────────
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] PyInstaller not found -- installing...
    pip install pyinstaller
    if errorlevel 1 ( echo [ERROR] pip install failed. & pause & exit /b 1 )
)

REM ── Check / install Pillow ──────────────────────────────────
python -c "from PIL import Image" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Pillow not found -- installing...
    pip install pillow
    if errorlevel 1 ( echo [ERROR] pip install failed. & pause & exit /b 1 )
)

REM ── Check lz4 ───────────────────────────────────────────────
python -c "import lz4" >nul 2>&1
if errorlevel 1 (
    echo [INFO] lz4 not found -- installing...
    pip install lz4
    if errorlevel 1 ( echo [ERROR] pip install failed. & pause & exit /b 1 )
)

REM ── Convert icon.png → icon.ico ─────────────────────────────
if exist "%ICON%" (
    echo [INFO] Converting icon.png to icon.ico...
    python -c "from PIL import Image; img=Image.open('icon.png'); img.save('icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
    if errorlevel 1 (
        echo [WARN] Icon conversion failed -- building without custom icon.
        set ICO_ARG=
    ) else (
        echo [INFO] icon.ico created.
        set ICO_ARG=--icon=icon.ico
    )
) else (
    echo [WARN] icon.png not found -- building without custom icon.
    set ICO_ARG=
)

REM ── Clean previous build ────────────────────────────────────
echo [INFO] Cleaning previous build artifacts...
if exist "%BUILD%"         rmdir /s /q "%BUILD%"
if exist "%DIST%"          rmdir /s /q "%DIST%"
if exist "%APPNAME%.spec"  del /q "%APPNAME%.spec"

REM ── Run PyInstaller via python -m (works regardless of PATH) ─
echo [INFO] Running PyInstaller...
echo.

python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "%APPNAME%" ^
    %ICO_ARG% ^
    --add-data "icon.png;." ^
    --hidden-import=lz4.block ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.ttk ^
    --hidden-import=tkinter.scrolledtext ^
    --hidden-import=tkinter.filedialog ^
    --hidden-import=tkinter.messagebox ^
    --hidden-import=tkinter.font ^
    --collect-all lz4 ^
    --noconfirm ^
    "%SCRIPT%"

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. See output above.
    pause & exit /b 1
)

REM ── Result ──────────────────────────────────────────────────
echo.
echo  +----------------------------------------------+
echo  ^|   Build complete!                            ^|
echo  +----------------------------------------------+
echo.
echo  EXE: %DIST%\%APPNAME%.exe
echo.

set /p OPEN="Open dist folder? [Y/n]: "
if /i "!OPEN!" neq "n" explorer "%DIST%"

endlocal
pause
