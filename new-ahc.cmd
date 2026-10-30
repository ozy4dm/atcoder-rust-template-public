@echo off
setlocal
if "%~1"=="" goto usage
python -X utf8 "%~dp0ahc-lab\new_contest.py" %*
exit /b %errorlevel%
:usage
echo Usage: new-ahc.cmd CONTEST_ID
echo Creates a contest workspace without overwriting existing work.
exit /b 1
