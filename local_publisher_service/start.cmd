@echo off
title Opportunity Radar - Local Publisher (port 19000)
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

set HEADLESS=false
set PORT=19000

echo Starting local publisher at http://localhost:19000
echo Keep this window OPEN. Press Ctrl+C to stop.
echo.
"%NODE_CMD%" index.js
echo.
pause
