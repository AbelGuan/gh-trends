@echo off
chcp 65001 >nul
cd /d "%~dp0"
python gh_trends.py --open %*
if errorlevel 1 pause
