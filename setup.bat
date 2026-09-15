@echo off
REM ============================================================
REM  QR Analytics - Setup inicial
REM  Cria o venv, instala dependencias e prepara o .env
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================
echo   QR Analytics - Setup
echo ============================================
echo.

REM 1. Verifica se o Python esta instalado
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale o Python 3.12+ em https://www.python.org/downloads/
    echo Durante a instalacao, marque "Add Python to PATH".
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VERSION=%%v
echo [OK] Python %PY_VERSION% encontrado.
echo.

REM 2. Cria o venv se nao existir
if exist "venv\Scripts\activate.bat" (
    echo [OK] Ambiente virtual ja existe.
) else (
    echo [..] Criando ambiente virtual...
    python -m venv venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o venv.
        pause
        exit /b 1
    )
    echo [OK] Ambiente virtual criado.
)
echo.

REM 3. Instala dependencias
echo [..] Instalando dependencias (pode demorar alguns minutos)...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r backend\requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.
echo.

REM 4. Cria o .env a partir do .env.example
if exist ".env" (
    echo [OK] Arquivo .env ja existe, mantendo o atual.
) else (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] Arquivo .env criado a partir de .env.example.
        echo.
        echo [ATENCAO] Edite o arquivo .env e troque a senha do admin
        echo           ANTES de usar o sistema em producao.
    ) else (
        echo [AVISO] .env.example nao encontrado. Crie o .env manualmente.
    )
)

echo.
echo ============================================
echo   Setup concluido!
echo ============================================
echo.
echo Para iniciar o servidor, execute: start.bat
echo.
pause