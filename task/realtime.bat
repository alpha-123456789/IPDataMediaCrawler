@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
forfiles /p "logs" /m "realtime_*.log" /d -7 /c "cmd /c del /q @path" 2>nul
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "LOG_TIMESTAMP=%%i"
cd /d D:\PythonProject\IPDataMediaCrawler && (uv run crawl_all_keywords.py --mode realtime && uv run main.py --platform xhs --lt qrcode --type creator && uv run main.py --platform bili --lt qrcode --type creator && uv run main.py --platform dy --lt qrcode --type creator && uv run main.py --platform wb --lt qrcode --type creator)
 rem 写日志文件 > "logs\realtime_%LOG_TIMESTAMP%.log" 2>&1