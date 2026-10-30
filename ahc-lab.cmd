@echo off
setlocal
cd /d "%~dp0"
python -X utf8 "%~dp0ahc-lab\demo\make_inputs.py"
if errorlevel 1 goto failed
python -X utf8 "%~dp0ahc-lab\lab.py" serve --open %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo AHC Lab could not start. Please check the messages above.
pause
exit /b 1
