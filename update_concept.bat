@echo off
chcp 65001 >nul
set "VIRTUAL_ENV="
echo ============================================
echo  Theme Concept Update
echo ============================================

echo.
echo [1/2] Updating East Money cookie...
call update_cookie.bat
if %errorlevel% neq 0 (
    echo [!] Cookie update failed. Continuing with existing cookie...
)

echo.
echo [2/2] Fetching concept board list...
:fetch_concepts
uv run --frozen ashare-pilot themes concepts fetch -q -v
if %errorlevel% equ 0 goto concept_fetch_complete

echo [!] Concept board fetch interrupted or failed.
echo [*] Waiting 5 seconds before refreshing the East Money cookie...
timeout /T 5 /NOBREAK >nul
call update_cookie.bat
if %errorlevel% neq 0 (
    echo [!] Cookie update failed. Retrying from checkpoint with the existing cookie...
)
echo [*] Resuming concept board fetch from checkpoint...
goto fetch_concepts

:concept_fetch_complete
echo [*] All concept boards fetched successfully.