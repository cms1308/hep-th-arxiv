@echo off
rem Double-click to register the weekday 11:07 scheduled task. Logic lives in the .ps1 with the same name.
rem Keep this file ASCII-only: cmd.exe reads batch files in the OEM code page.
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dpn0.ps1"
echo.
pause
