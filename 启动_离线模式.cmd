@echo off
setlocal
chcp 65001 >nul
title Ticket Agent - Offline
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-TicketAgent.ps1" -Mode offline %*
set "ticket_exit=%errorlevel%"
if not "%ticket_exit%"=="0" pause
exit /b %ticket_exit%
