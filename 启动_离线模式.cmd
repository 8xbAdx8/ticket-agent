@echo off
setlocal
chcp 65001 >nul
title Ticket Agent - Offline
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-TicketAgent.ps1" -Mode offline
if errorlevel 1 pause
endlocal
