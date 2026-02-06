@echo off
cd /d %~dp0
if not exist venv (
  echo Criando venv...
  py -m venv venv
)
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Iniciando o sistema...
echo Acesse: http://127.0.0.1:5001
echo Para parar: CTRL+C
echo.
py app.py
pause
