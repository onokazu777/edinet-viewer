@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Adding changes ===
git add -A
git status
echo.
echo === Committing ===
git commit -m "Fix: remove dl_status/parse_status references for minimal DB compatibility"
echo.
echo === Pushing ===
git push -u origin main
echo.
echo === Done ===
pause
