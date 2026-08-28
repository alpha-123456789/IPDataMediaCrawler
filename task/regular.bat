@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d D:\PythonProject\IPDataMediaCrawler && (uv run crawl_all_keywords.py --mode regular && uv run main.py --platform wb --lt qrcode --type creator && uv run main.py --platform bili --lt qrcode --type creator && uv run main.py --platform dy --lt qrcode --type creator && uv run main.py --platform xhs --lt qrcode --type creator)
