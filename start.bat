@echo off
REM ============================================================
REM  QR Analytics - Inicia o servidor FastAPI
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================
echo   QR Analytics - Iniciando servidor
echo ============================================
echo.

REM 1. Verifica se o venv existe
if not exist "venv\Scripts\activate.bat" (
    echo [ERRO] Ambiente virtual nao encontrado.
    echo Rode primeiro: setup.bat
    pause
    exit /b 1
)

REM 2. Verifica se o .env existe
if not exist ".env" (
    echo [AVISO] Arquivo .env nao encontrado.
    if exist ".env.example" (
        echo Copiando .env.example para .env...
        copy ".env.example" ".env" >nul
        echo [ATENCAO] Edite o .env para trocar a senha do admin.
        pause
    ) else (
        echo [ERRO] Nem .env nem .env.example foram encontrados.
        pause
        exit /b 1
    )
)

REM 3. Ativa o venv
call venv\Scripts\activate.bat

REM 4. Verifica se a pasta data existe
if not exist "data" (
    echo [..] Criando pasta data...
    mkdir data
)

REM 5. Sobe o servidor
echo.
echo Servidor:  http://localhost:8000
echo Dashboard: http://localhost:8000/dashboard/
echo Docs:      http://localhost:8000/docs
echo.
echo Pressione CTRL+C para parar.
echo.

cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

REM Se o uvicorn sair por algum motivo, mantem a janela aberta
echo.
echo Servidor encerrado.
pause