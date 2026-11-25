@echo off
setlocal EnableDelayedExpansion

:: =============================================================================
:: run_trader.bat - Automated Daily Pipeline Execution Wrapper
:: =============================================================================
:: Requirements:
::   - Activates virtual environment (.venv or venv)
::   - Runs: python -m src.pipeline.scheduler --force
::   - Logs stdout and stderr to logs/daily_run_YYYY-MM-DD.log
::   - If pipeline crashes, logs "PIPELINE FAILED" + error
::   - Works regardless of invocation directory (uses %~dp0)
::   - Missed-run detection: checks if yesterday's log exists
::   - Automatically deletes log files older than 30 days
:: =============================================================================

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "LOGS_DIR=%PROJECT_DIR%logs"
if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"

:: Determine current date in YYYY-MM-DD format using powershell
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"
for /f %%i in ('powershell -NoProfile -Command "(Get-Date).AddDays(-1).ToString('yyyy-MM-dd')"') do set "YESTERDAY=%%i"

set "TODAY_LOG=%LOGS_DIR%\daily_run_%TODAY%.log"
set "YESTERDAY_LOG=%LOGS_DIR%\daily_run_%YESTERDAY%.log"

echo ============================================================================= >> "%TODAY_LOG%"
echo  AI STOCK TRADER - AUTOMATED DAILY RUN: %TODAY% >> "%TODAY_LOG%"
echo Started at: %TIME% on %DATE% >> "%TODAY_LOG%"
echo Project root: %PROJECT_DIR% >> "%TODAY_LOG%"
echo =============================================================================== >> "%TODAY_LOG%"

:: 1. Activate Python Virtual Environment
set "PYTHON_CMD="
if exist "%PROJECT_DIR%.venv\Scripts\activate.bat" (
    call "%PROJECT_DIR%.venv\Scripts\activate.bat"
    set "PYTHON_CMD=python"
    echo [INFO] Activated virtual environment from %PROJECT_DIR%.venv >> "%TODAY_LOG%"
) else if exist "%PROJECT_DIR%venv\Scripts\activate.bat" (
    call "%PROJECT_DIR%venv\Scripts\activate.bat"
    set "PYTHON_CMD=python"
    echo [INFO] Activated virtual environment from %PROJECT_DIR%venv >> "%TODAY_LOG%"
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_CMD=python"
        echo [INFO] Virtual environment not found. Using system python from PATH. >> "%TODAY_LOG%"
    ) else (
        echo [ERROR] PIPELINE FAILED: Neither Python virtual environment nor system python.exe was found! >> "%TODAY_LOG%"
        echo [ERROR] Please install Python 3.11+ or create a virtual environment with 'python -m venv .venv'. >> "%TODAY_LOG%"
        echo PIPELINE FAILED: Python environment not found. >> "%TODAY_LOG%"
        echo [ERROR] Python environment not found. See %TODAY_LOG%
        exit /b 1
    )
)

:: 2. Missed Run Recovery Check (Part 3, Item 6)
if not exist "%YESTERDAY_LOG%" (
    echo [WARNING] MISSED RUN DETECTED: %YESTERDAY% - Yesterday's log file does not exist. >> "%TODAY_LOG%"
    echo [WARNING] The computer was likely powered off or Task Scheduler was skipped. >> "%TODAY_LOG%"
    echo [WARNING] Proceeding with today's scheduled run without backfilling. >> "%TODAY_LOG%"
    echo [WARNING] MISSED RUN DETECTED: %YESTERDAY%
) else (
    echo [INFO] Yesterday's run verified: %YESTERDAY_LOG% found. >> "%TODAY_LOG%"
)

:: 2.0 Heartbeat: tell the outside watchdog (healthchecks.io) the run has started. Does nothing unless you set
::     HEALTHCHECK_PING_URL, and a failure here never stops the run.
%PYTHON_CMD% -m src.alerts.heartbeat start >> "%TODAY_LOG%" 2>&1

:: 2a. Pre-flight check: is this machine fit to run? Stops the run (and alerts you) instead of crashing halfway,
::     or worse, trading on a changed environment.
%PYTHON_CMD% -m src.ops.envcheck >> "%TODAY_LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] PIPELINE FAILED: the environment check failed, so nothing was run. See the [FAIL] lines above. >> "%TODAY_LOG%"
    echo PIPELINE FAILED: environment check failed >> "%TODAY_LOG%"
    %PYTHON_CMD% -m src.alerts.heartbeat fail --message "environment check failed" >> "%TODAY_LOG%" 2>&1
    call :ALERT_ENV
    exit /b 1
)

:: 2b. Back up the database BEFORE the run changes it, and verify the copy. A failed backup alerts you
::     but does not block the run.
%PYTHON_CMD% -m src.ops.backup create >> "%TODAY_LOG%" 2>&1
if errorlevel 1 call :ALERT_BACKUP

:: 3. Execute Pipeline Cycle
echo [INFO] Executing: %PYTHON_CMD% -m src.pipeline.scheduler --force >> "%TODAY_LOG%"
echo. >> "%TODAY_LOG%"

%PYTHON_CMD% -m src.pipeline.scheduler --force >> "%TODAY_LOG%" 2>&1
set "PIPELINE_EXIT=%ERRORLEVEL%"

echo. >> "%TODAY_LOG%"
:: Exit codes (src/pipeline/scheduler.py EXIT_CODES): 0 success/skipped, 2 degraded, 3 halted, else failed.
if %PIPELINE_EXIT% equ 0 (
    echo [SUCCESS] Pipeline execution finished successfully at %TIME% >> "%TODAY_LOG%"
    echo [SUCCESS] Daily pipeline run complete for %TODAY%.
) else if %PIPELINE_EXIT% equ 2 (
    echo [DEGRADED] Pipeline completed and committed on partial inputs ^(exit code 2^) at %TIME% >> "%TODAY_LOG%"
    echo [DEGRADED] Daily pipeline completed with degraded inputs. Check log: %TODAY_LOG%
) else if %PIPELINE_EXIT% equ 3 (
    echo [HALTED] Pipeline deliberately not run: kill switch or run in progress ^(exit code 3^) at %TIME% >> "%TODAY_LOG%"
    echo [HALTED] Daily pipeline halted. Check log: %TODAY_LOG%
) else (
    echo [ERROR] PIPELINE FAILED with exit code %PIPELINE_EXIT% at %TIME% >> "%TODAY_LOG%"
    echo PIPELINE FAILED: Execution exited with error code %PIPELINE_EXIT% >> "%TODAY_LOG%"
    echo [ERROR] PIPELINE FAILED with exit code %PIPELINE_EXIT%. Check log: %TODAY_LOG%
)

:: 3a. Heartbeat: success (0) and degraded (2) count as "ran"; anything else is reported as a failure.
if %PIPELINE_EXIT% equ 0 (%PYTHON_CMD% -m src.alerts.heartbeat ok --message "exit code 0" >> "%TODAY_LOG%" 2>&1) else if %PIPELINE_EXIT% equ 2 (%PYTHON_CMD% -m src.alerts.heartbeat ok --message "exit code 2 degraded" >> "%TODAY_LOG%" 2>&1) else (%PYTHON_CMD% -m src.alerts.heartbeat fail --message "exit code %PIPELINE_EXIT%" >> "%TODAY_LOG%" 2>&1)

:: 3b. Push a notification for a crash (any code except 0 and 2) or a halt (3). 0 and 2 are normal.
if %PIPELINE_EXIT% neq 0 if %PIPELINE_EXIT% neq 2 call :ALERT_RUN

:: 4. Automatic Log Cleanup (>30 days old) (Part 2, Item 5)
echo. >> "%TODAY_LOG%"
echo [INFO] Cleaning up logs older than 30 days... >> "%TODAY_LOG%"
powershell -NoProfile -Command "$cut = (Get-Date).AddDays(-30); Get-ChildItem -Path '%LOGS_DIR%' -Filter '*.log' | Where-Object { $_.LastWriteTime -lt $cut } | ForEach-Object { Remove-Item $_.FullName -Force; Write-Output ('Purged old log: ' + $_.Name) }" >> "%TODAY_LOG%" 2>&1
echo [INFO] Log maintenance complete. >> "%TODAY_LOG%"

exit /b %PIPELINE_EXIT%

:ALERT_RUN
:: Try the project's Python first. If it cannot send (for example the environment itself is what broke),
:: retry once with the system Python so a broken .venv can never silence the alert.
%PYTHON_CMD% -m src.alerts.watchdog run --exit-code %PIPELINE_EXIT% --log "%TODAY_LOG%" >> "%TODAY_LOG%" 2>&1
if errorlevel 1 (
    echo [WARNING] Alert could not be sent with the project Python; retrying with the system Python. >> "%TODAY_LOG%"
    py -3 -m src.alerts.watchdog run --exit-code %PIPELINE_EXIT% --log "%TODAY_LOG%" >> "%TODAY_LOG%" 2>&1
)
exit /b 0

:ALERT_BACKUP
%PYTHON_CMD% -m src.alerts.watchdog backup --problem "The pre-run backup or its verification failed. See the run log." >> "%TODAY_LOG%" 2>&1
if errorlevel 1 py -3 -m src.alerts.watchdog backup --problem "The pre-run backup or its verification failed. See the run log." >> "%TODAY_LOG%" 2>&1
exit /b 0

:ALERT_ENV
%PYTHON_CMD% -m src.alerts.watchdog env --log "%TODAY_LOG%" >> "%TODAY_LOG%" 2>&1
if errorlevel 1 py -3 -m src.alerts.watchdog env --log "%TODAY_LOG%" >> "%TODAY_LOG%" 2>&1
exit /b 0
