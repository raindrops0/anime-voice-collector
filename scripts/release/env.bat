@echo off
rem Used by start.bat and terminal.bat in the Windows download (made by make_zip.ps1).
rem Python, the uv cache and the downloaded models all stay inside the download's folder, so
rem deleting that folder removes everything. The Hugging Face token stays in its usual place in
rem the user's own folder, so a token made for other programs is found too.

for %%I in ("%~dp0..\..") do set "AVOC_ROOT=%%~fI"

rem The uv.exe shipped next to start.bat comes first, so no uv needs to be installed.
set "PATH=%AVOC_ROOT%;%PATH%"
set "UV_PYTHON_INSTALL_DIR=%AVOC_ROOT%\.runtime\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_CACHE_DIR=%AVOC_ROOT%\.runtime\uv-cache"
set "UV_LOCKED=1"
set "UV_NO_DEV=1"
set "TORCH_HOME=%AVOC_ROOT%\.runtime\torch"
set "HF_HUB_CACHE=%AVOC_ROOT%\.runtime\huggingface"
