@echo off
if exist "%~dp0Start-GrokDemo.ps1" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-GrokDemo.ps1" -OpenBrowser
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\grok-property-sample\Start-GrokDemo.ps1" -OpenBrowser
)
if errorlevel 1 pause
