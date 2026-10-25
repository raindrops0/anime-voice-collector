@echo off
rem Open a command prompt in the Windows download where the commands in the docs work as written,
rem such as "uv run avoc doctor" and "uv run hf auth login".
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0scripts\release\env.bat"
echo Commands in the docs work here, for example:
echo   uv run avoc doctor
echo   uv run hf auth login
echo   uv run avoc --help
echo.
cmd /k
