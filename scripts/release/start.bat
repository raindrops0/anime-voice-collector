@echo off
rem Start anime-voice-collector from the Windows download: double-click this file.
rem The first start downloads Python and the libraries, about 5 GB, into this folder.
rem The workspace is the folder "workspace" here. To use another, drag that folder onto this file,
rem or run: start.bat D:\my-workspace. What follows the folder goes to "avoc app", such as --port.
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0scripts\release\env.bat"

if not exist ".venv\Scripts\python.exe" (
    echo First start: downloading Python and the libraries, about 5 GB. This takes a while.
    echo.
)
uv sync
if errorlevel 1 goto failed

echo.
echo The app opens in your browser. Keep this window open while you use it; close it to stop.
echo.
if "%~1"=="" (uv run avoc app workspace) else (uv run avoc app %*)
if errorlevel 1 goto failed
goto :eof

:failed
echo.
echo It stopped with an error; see the lines above. Run terminal.bat, then "uv run avoc doctor",
echo and include its output when you report the problem:
echo https://github.com/raindrops0/anime-voice-collector/issues
pause
exit /b 1
