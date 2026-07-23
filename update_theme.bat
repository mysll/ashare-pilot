@echo off
chcp 65001 >nul
set "VIRTUAL_ENV="

echo ============================================
echo  Theme Library Update
echo ============================================

echo.
echo [1/4] Updating East Money cookie...
call update_cookie.bat
if %errorlevel% neq 0 (
    echo [!] Cookie update failed. Continuing with existing cookie...
)

echo.
echo [2/4] Fetching concept board list...
uv run --frozen ashare-pilot themes concepts fetch -q -v
if %errorlevel% neq 0 (
    echo [!] Failed to fetch concept list. Aborting.
    pause
    exit /b 1
)

@echo sleep 60s
timeout /T 60 > NUL
echo.
echo [1/4] Updating East Money cookie...
call update_cookie.bat
if %errorlevel% neq 0 (
    echo [!] Cookie update failed. Continuing with existing cookie...
)

echo.
echo [3/4] Fetching concept stocks (this may take a while)...
uv run --frozen ashare-pilot themes concepts fetch-stocks --reset
if %errorlevel% neq 0 (
    echo [!] Failed to fetch concept stocks. Aborting.
    pause
    exit /b 1
)

echo.
echo [4/4] Building theme library (v5)...
uv run --frozen ashare-pilot themes library build --clean
if %errorlevel% equ 0 (
    echo.
    echo [*] Theme library update complete.
) else (
    echo [!] Build failed with error code %errorlevel%
)

pause
