@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo      VERDE FINANCEIRO - INICIANDO
 echo ==========================================
py --version >nul 2>&1
if errorlevel 1 (
  echo Python nao encontrado. Instale o Python e marque Add Python to PATH.
  pause
  exit /b 1
)
py -c "import flask" >nul 2>&1
if errorlevel 1 (
  echo Instalando Flask pela primeira vez...
  py -m pip install -r requirements.txt
  if errorlevel 1 (echo Erro ao instalar Flask. Verifique sua internet. & pause & exit /b 1)
)
echo Abrindo o Chrome ou seu navegador padrao...
echo Se nao abrir automaticamente, acesse http://127.0.0.1:5000
py app.py
pause
