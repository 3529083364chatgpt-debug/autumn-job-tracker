@echo off
chcp 65001 >nul
title 秋招信息一键抓取
echo.
echo 正在启动...
echo.
cd /d "%~dp0"
python -m scraper.run_local
pause