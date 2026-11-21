@echo off
REM run.cmd — atajo universal (evita el bloqueo de ExecutionPolicy en .ps1)
REM Uso: .\run auth | .\run sync | .\run report | .\run all | .\run test
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
