@echo off
setlocal
title NFSe Automacao
cd /d "%~dp0"

echo ================================================
echo   NFSe Automacao - Aplicativo Desktop
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
call npm run dev

if errorlevel 1 (
  echo.
  echo ERRO: O aplicativo encerrou com falha.
  pause
  exit /b 1
)

endlocal
pause
