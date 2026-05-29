@echo off
setlocal enabledelayedexpansion
title NFSe Automacao - Construir Instalador
cd /d "%~dp0"

echo.
echo ================================================================
echo   NFSe Automacao - Construir Instalador de Distribuicao
echo ================================================================
echo.
echo  Este script vai:
echo   1. Compilar o backend Python em server.exe (PyInstaller)
echo   2. Compilar a interface Electron (Vite)
echo   3. Gerar o instalador .exe (electron-builder / NSIS)
echo.
echo  Duracao estimada: 5-10 minutos
echo.
pause

REM ════════════════════════════════════════════════════════════════
REM  Verificacoes
REM ════════════════════════════════════════════════════════════════

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo        Instale o Python 3.10+ em https://python.org
    pause & exit /b 1
)

npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Node.js/npm nao encontrado no PATH.
    echo        Instale o Node.js LTS em https://nodejs.org
    pause & exit /b 1
)

REM ════════════════════════════════════════════════════════════════
REM  [1/5] Dependencias Python
REM ════════════════════════════════════════════════════════════════
echo [1/5] Instalando dependencias Python...
python -m pip install --quiet --upgrade pyinstaller
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias Python.
    pause & exit /b 1
)
echo       OK
echo.

REM ════════════════════════════════════════════════════════════════
REM  [2/5] Limpeza de builds anteriores
REM ════════════════════════════════════════════════════════════════
echo [2/5] Limpando builds anteriores...
if exist "dist\server"         rmdir /s /q "dist\server"
if exist "build\server"        rmdir /s /q "build\server"
if exist "electron\renderer-dist" rmdir /s /q "electron\renderer-dist"
echo       OK
echo.

REM ════════════════════════════════════════════════════════════════
REM  [3/5] Compilar backend Python -> dist\server\server.exe
REM ════════════════════════════════════════════════════════════════
echo [3/5] Compilando backend Python (pode levar 3-5 minutos)...
python -m PyInstaller api\server.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao compilar o backend Python. Veja mensagens acima.
    pause & exit /b 1
)

REM Copiar config.py para dentro da pasta do server.exe
copy /y "config.py" "dist\server\config.py" >nul
if errorlevel 1 (
    echo [AVISO] Nao foi possivel copiar config.py para dist\server\
)
echo       OK - dist\server\server.exe gerado
echo.

REM ════════════════════════════════════════════════════════════════
REM  [4/5] Compilar interface Electron (Vite)
REM ════════════════════════════════════════════════════════════════
echo [4/5] Compilando interface (Vite)...
cd /d "%~dp0electron"

if not exist "node_modules" (
    echo       Instalando dependencias npm...
    call npm install
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar dependencias npm.
        pause & exit /b 1
    )
)

call npm run build:renderer
if errorlevel 1 (
    echo [ERRO] Falha ao compilar a interface Vite.
    pause & exit /b 1
)
echo       OK
echo.

REM ════════════════════════════════════════════════════════════════
REM  [5/5] Gerar instalador Windows (.exe) com electron-builder
REM ════════════════════════════════════════════════════════════════
echo [5/5] Gerando instalador Windows...

set ELECTRON_RUN_AS_NODE=
call npx electron-builder --win nsis
if errorlevel 1 (
    echo [ERRO] Falha ao gerar instalador. Veja mensagens acima.
    pause & exit /b 1
)

cd /d "%~dp0"

echo.
echo ================================================================
echo   PRONTO!
echo.

REM Encontra o instalador gerado
for /f "delims=" %%f in ('dir /b /s "electron\dist\NFSe Automacao Setup*.exe" 2^>nul') do (
    echo   Instalador: %%f
)

echo.
echo   Para distribuir: envie apenas o arquivo .exe acima.
echo   O usuario executa e instala normalmente (sem precisar
echo   de Python, Node.js ou qualquer outro programa).
echo.
echo   IMPORTANTE: apos instalar, o usuario precisa configurar
echo   os caminhos pelo menu "Configuracoes" no app.
echo ================================================================
echo.
pause
