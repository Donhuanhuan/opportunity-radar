@echo off
title Opportunity Radar - Local Publisher Installer
cd /d "%~dp0"

rem ---- locate node (fallback to managed node) ----
set "NODE_CMD=node"
where node >nul 2>nul
if not errorlevel 1 goto :have_node
if exist "C:\Users\30689\.workbuddy\binaries\node\versions\22.22.2\node.exe" set "NODE_CMD=C:\Users\30689\.workbuddy\binaries\node\versions\22.22.2\node.exe"
if not exist "%NODE_CMD%" echo [ERROR] node.exe not found. Install Node.js first.
if not exist "%NODE_CMD%" pause
if not exist "%NODE_CMD%" exit /b 1
:have_node

echo ============================================================
echo   [1/1] Installing playwright + express via npm mirror...
echo         Normal network: 1-3 minutes. Please wait.
echo ============================================================
echo.
"%NODE_CMD%" install.js
echo.
echo Done. Press any key to close this window.
pause >nul
