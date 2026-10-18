@echo off
setlocal
chcp 65001 >nul
title Ticket Agent - DeepSeek Live
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-TicketAgent.ps1" -Mode live
if errorlevel 1 pause
endlocal
