@echo off
chcp 65001 >nul

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
python .opencode/skills/theme-library/scripts/fetch_concept_stocks.py -q --reset
if %errorlevel% neq 0 (
    echo [!] Failed to fetch concept stocks. Aborting.
    pause
    exit /b 1
)

echo.
echo [3/3] Building theme library (v5)...
python .opencode/skills/theme-library/scripts/build_library.py --clean
if %errorlevel% equ 0 (
    echo.
    echo [*] Theme library update complete.
) else (
    echo [!] Build failed with error code %errorlevel%
)

pause
