@echo off
setlocal enabledelayedexpansion
REM AI SDLC 安全闸门 . Windows 启动器 (cmd)
REM 由 hooks.json 的 beforeMCPExecution 调用；把 stdin 原样透传给 guard_atlassian.py。
REM python 解释器选择顺序：AI-SDLC 绿色运行时 -> 系统 python -> 系统 py 启动器。
REM 说明：本 hook 只用到 Python 标准库，任何 3.8+ 解释器都可运行。

set "SCRIPT_DIR=%~dp0"
set "GUARD_PY=%SCRIPT_DIR%guard_atlassian.py"

set "PY="

REM 1) 绿色运行时：AI_SDLC_RUNTIME 或默认 C:\AI-SDLC\runtime 下的 python-*\python.exe（取最新）
set "RT=%AI_SDLC_RUNTIME%"
if "%RT%"=="" set "RT=C:\AI-SDLC\runtime"
if exist "%RT%\" (
  for /f "delims=" %%D in ('dir /b /ad /o-n "%RT%\python-*" 2^>nul') do (
    if not defined PY (
      if exist "%RT%\%%D\python.exe" set "PY=%RT%\%%D\python.exe"
    )
  )
)

REM 2) 系统 PATH 上的 python.exe
if not defined PY (
  for %%P in (python.exe) do (
    if not defined PY (
      if not "%%~$PATH:P"=="" set "PY=%%~$PATH:P"
    )
  )
)

REM 3) py 启动器
if not defined PY (
  where py >nul 2>nul && set "PY=py"
)

if not defined PY (
  REM 找不到任何 python：fail-safe。退出码 2 = deny（Cursor 约定），
  REM 避免在 cmd 里手拼含大量特殊字符的 JSON 出错。hooks.json 里 failClosed=true 亦为双保险。
  echo AI SDLC guard: no Python interpreter found; blocking this Atlassian write (fail-safe). 1>&2
  echo Install Python 3 or the AI-SDLC runtime, then retry. 1>&2
  exit /b 2
)

"%PY%" "%GUARD_PY%"
exit /b %ERRORLEVEL%
