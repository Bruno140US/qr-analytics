@echo off
REM ============================================================
REM  QR Analytics - Cloudflare Tunnel
REM  Exige o cloudflared.exe instalado. Ajuste o caminho abaixo
REM  se voce instalou em outro lugar.
REM ============================================================

set CLOUDFLARED=C:\cloudflared\cloudflared.exe

cd /d "%~dp0"

echo.
echo ============================================
echo   QR Analytics - Cloudflare Tunnel
echo ============================================
echo.

REM 1. Verifica se o cloudflared existe
if not exist "%CLOUDFLARED%" (
    echo [ERRO] cloudflared.exe nao encontrado em:
    echo        %CLOUDFLARED%
    echo.
    echo Baixe em: https://github.com/cloudflare/cloudflared/releases
    echo E ajuste a variavel CLOUDFLARED no inicio deste script.
    pause
    exit /b 1
)

REM 2. Aviso
echo Certifique-se de que o servidor (start.bat) esteja rodando
echo em outra janela antes de continuar.
echo.
echo A URL publica sera exibida abaixo. Copie e compartilhe.
echo Pressione CTRL+C para encerrar o tunel.
echo.

REM 3. Sobe o tunel
"%CLOUDFLARED%" tunnel --url http://localhost:8000

echo.
echo Tunel encerrado.
pause