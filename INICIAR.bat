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

set "PROJECT_ROOT=%CD%"
set "SOURCE_ELECTRON=%PROJECT_ROOT%\electron"
set "RUNTIME_ROOT=%LOCALAPPDATA%\NFSE_Automacao"
set "RUNTIME_ELECTRON=%RUNTIME_ROOT%\electron"

if not exist "%RUNTIME_ROOT%" mkdir "%RUNTIME_ROOT%"

echo Preparando aplicativo Electron em pasta local...
robocopy "%SOURCE_ELECTRON%" "%RUNTIME_ELECTRON%" /MIR /XD node_modules node_modules_corrupt_* renderer-dist dist /XF *.log >nul
set "ROBOCOPY_EXIT=%ERRORLEVEL%"
if %ROBOCOPY_EXIT% GEQ 8 (
  echo.
  echo ERRO: Falha ao copiar arquivos do Electron para pasta local.
  pause
  exit /b 1
)
echo.

cd /d "%RUNTIME_ELECTRON%"

set "NPM_READY=1"
if not exist "node_modules\vite\bin\vite.js" set "NPM_READY=0"
if not exist "node_modules\electron\cli.js" set "NPM_READY=0"
if not exist "node_modules\react\package.json" set "NPM_READY=0"
if not exist "node_modules\framer-motion\package.json" set "NPM_READY=0"

if "%NPM_READY%"=="0" (
  echo Instalando/reparando dependencias do Electron/React...
  call npm install --include=dev --no-audit --no-fund
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
set "NFSE_PROJECT_ROOT=%PROJECT_ROOT%"

call node dev-runner.js

if errorlevel 1 (
  echo.
  echo ERRO: O aplicativo encerrou com falha.
  pause
  exit /b 1
)

endlocal
pause
