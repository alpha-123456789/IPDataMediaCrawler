@echo off
chcp 65001 >nul
setlocal

set "PROJECT_DIR=D:\PythonProject\IPDataMediaCrawler"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "PID_FILE=%LOG_DIR%\keyword_report_runner.pid"

if not exist "%PID_FILE%" (
    echo 未找到运行中的关键词报告执行器 PID 文件。
    exit /b 0
)

set /p RUNNER_PID=<"%PID_FILE%"

if not defined RUNNER_PID (
    echo PID 文件为空，正在清理。
    del /q "%PID_FILE%" >nul 2>&1
    exit /b 0
)

echo 正在检查关键词报告执行器 PID=%RUNNER_PID% ...

tasklist /FI "PID eq %RUNNER_PID%"

echo.
echo 正在结束关键词报告执行器 PID=%RUNNER_PID% ...

taskkill /PID %RUNNER_PID% /T /F

if errorlevel 1 (
    echo.
    echo 进程结束失败。
    exit /b 1
)

echo.
echo 关键词报告执行器及其子进程已结束。

del /q "%PID_FILE%" >nul 2>&1

exit /b 0