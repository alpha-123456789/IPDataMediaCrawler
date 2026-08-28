@echo off
chcp 65001 >nul
setlocal
set "PROJECT_DIR=D:\PythonProject\IPDataMediaCrawler"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "LOG_FILE=%LOG_DIR%\keyword_report_runner_console.log"
set "PYTHON_EXE=D:\PythonProject\IPDataMediaCrawler\.venv\Scripts\python.exe"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

>> "%LOG_FILE%" echo [%DATE% %TIME%] Starting keyword report runner.
cd /d "%PROJECT_DIR%"
if not exist "%PYTHON_EXE%" (
    >> "%LOG_FILE%" echo [%DATE% %TIME%] ERROR: Python not found: %PYTHON_EXE%
    exit /b 1
)

call "%PYTHON_EXE%" -m custom.keyword_insight.keyword_report_runner --llm >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
>> "%LOG_FILE%" echo [%DATE% %TIME%] Keyword report runner stopped. ExitCode=%EXIT_CODE%
exit /b %EXIT_CODE%