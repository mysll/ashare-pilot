@echo off
chcp 65001 >nul
set "VIRTUAL_ENV="
rem set "UV_PROJECT_ENVIRONMENT=.venv-windows"

echo [*] Updating East Money cookie...
uv run --frozen ashare-pilot market-data auth update-cookie "https://quote.eastmoney.com/center/" --cookie-file .cookie --user-data-dir "%LOCALAPPDATA%\Google\Chrome\User Data\CookieProfile"
if %errorlevel% equ 0 (
    echo [*] Done.
) else (
    echo [!] Failed with error code %errorlevel%
)
