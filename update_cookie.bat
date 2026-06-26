@echo off
chcp 65001 >nul
echo [*] Updating East Money cookie...
python .opencode/scripts/get_cookie.py "https://quote.eastmoney.com/center/" --cookie-file .cookie --user-data-dir "%LOCALAPPDATA%\Google\Chrome\User Data\CookieProfile"
if %errorlevel% equ 0 (
    echo [*] Done.
) else (
    echo [!] Failed with error code %errorlevel%
)
