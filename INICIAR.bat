@echo off
setlocal
title NFSe Automacao

REM ============================================================
REM  Auto-elevacao: necessario para escrever a politica do
REM  Chrome em HKCU\SOFTWARE\Policies (auto-selecao de cert).
REM ============================================================
net session >nul 2>&1
if errorlevel 1 (
  echo Solicitando permissao de administrador para auto-selecao do certificado...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

cd /d "%~dp0"

echo ================================================
echo   NFSe Automacao - Aplicativo Desktop ^(ADMIN^)
echo ================================================
echo.

if not exist "electron\package.json" (
  echo ERRO: Nao encontrei a pasta electron deste projeto.
  echo Caminho atual: %CD%
  echo.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo ERRO: Node.js/NPM nao esta instalado ou nao esta no PATH.
  echo Instale o Node.js LTS e abra este arquivo novamente.
  echo.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo ERRO: Python nao esta instalado ou nao esta no PATH.
  echo Instale o Python 3.10+ e abra este arquivo novamente.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual Python...
  python -m venv .venv
  if errorlevel 1 (
    echo.
    echo ERRO: Falha ao criar ambiente virtual Python.
    pause
    exit /b 1
  )
  echo.
)

if not exist ".venv\Scripts\pip.exe" (
  echo Preparando pip no ambiente virtual...
  call ".venv\Scripts\python.exe" -m ensurepip --upgrade --default-pip
  if errorlevel 1 (
    echo.
    echo ERRO: Falha ao preparar pip no ambiente virtual.
    pause
    exit /b 1
  )
  echo.
)

echo Instalando/verificando dependencias Python...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERRO: Falha ao instalar dependencias Python.
  pause
  exit /b 1
)
echo.

cd /d "%~dp0electron"

if not exist "node_modules" (
  echo Instalando dependencias do Electron/React...
  call npm install
  if errorlevel 1 (
    echo.
    echo ERRO: Falha ao instalar dependencias.
    pause
    exit /b 1
  )
  echo.
)

echo Abrindo aplicativo desktop...
echo.

REM Garante que Electron rode como app grafico, nao como Node.js
set ELECTRON_RUN_AS_NODE=

call npm run dev

if errorlevel 1 (
  echo.
  echo ERRO: O aplicativo encerrou com falha.
  pause
  exit /b 1
)

endlocal
pause
