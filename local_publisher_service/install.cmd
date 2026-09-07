@echo off
chcp 65001 >nul
cd /d "D:\WorkBuddy\Make monney\Make monney\opportunity-radar\local_publisher_service"
echo [1/2] 设置 npm 国内镜像...
npm config set registry https://registry.npmmirror.com
npm config set playwright_download_host https://npmmirror.com/mirrors/playwright

echo [2/2] 安装依赖（playwright + express）...
node install.js

echo.
echo 安装完成。按任意键退出。
pause >nul
