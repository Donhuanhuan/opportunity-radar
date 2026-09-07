@echo off
chcp 65001 >nul
cd /d "D:\WorkBuddy\Make monney\Make monney\opportunity-radar\local_publisher_service"

REM 首次启动建议有窗口，确认登录态正常。稳定后可改为 set HEADLESS=true
set HEADLESS=false
set PORT=19000

echo 启动本地发布服务...
echo 地址: http://localhost:%PORT%
echo 按 Ctrl+C 停止
echo.
node index.js

pause
