@echo off
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0plancia" %*
) else (
  py -3 "%~dp0plancia" %*
)
exit /b %errorlevel%
