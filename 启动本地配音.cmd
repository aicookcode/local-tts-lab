@echo off

cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (

 echo Run: python install_models.py --engine all

 pause

 exit /b 1

)

start "" ".venv\Scripts\pythonw.exe" "voice_gui.py"

