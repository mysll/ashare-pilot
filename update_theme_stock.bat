@echo off
chcp 65001 >nul
set "VIRTUAL_ENV="
echo ============================================
echo  Theme Library Update
echo ============================================

echo.
echo [1/3] Updating East Money cookie...
call update_cookie.bat
if %errorlevel% neq 0 (
    echo [!] Cookie update failed. Continuing with existing cookie...
)

echo.
echo [2/3] Fetching concept stocks (this may take a while)...
if exist ".cache\theme-library\concept_stocks_progress.json" goto resume_existing
if exist ".cache\theme-library\concept-stock-checkpoints" goto resume_existing

echo [*] Starting a new full concept stock refresh...
uv run --frozen ashare-pilot themes concepts fetch-stocks -q --reset
if %errorlevel% equ 0 goto fetch_complete
goto retry_fetch

:resume_existing
echo [*] Existing checkpoint detected. Resuming without reset...
uv run --frozen ashare-pilot themes concepts fetch-stocks -q
if %errorlevel% equ 0 goto fetch_complete
goto retry_fetch

:retry_fetch
echo.
echo [!] Concept stock fetch interrupted or failed.
echo [*] Waiting 5 seconds before refreshing the East Money cookie...
timeout /T 5 /NOBREAK >nul

echo [*] Refreshing East Money cookie...
call update_cookie.bat
if %errorlevel% neq 0 (
    echo [!] Cookie update failed. Retrying from checkpoint with the existing cookie...
)

echo [*] Resuming concept stock fetch from checkpoint...
uv run --frozen ashare-pilot themes concepts fetch-stocks -q
if %errorlevel% neq 0 goto retry_fetch

:fetch_complete
echo [*] All concept stocks fetched successfully.

echo.
echo [3/3] Building theme library (v5)...
uv run --frozen ashare-pilot themes library build --clean
if %errorlevel% equ 0 (
    echo.
    echo [*] Theme library update complete.
) else (
    echo [!] Build failed with error code %errorlevel%
)

pause
