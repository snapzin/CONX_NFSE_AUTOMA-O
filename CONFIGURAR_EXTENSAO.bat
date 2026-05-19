@echo off
setlocal
title NFSe Automacao - Configurar Extensao no Perfil Isolado

echo ================================================================
echo   Setup unico: instalar extensao 'Baixar NFSe' no perfil
echo   isolado da automacao
echo ================================================================
echo.
echo  Este script abre o Chrome usando o perfil isolado da automacao
echo  ja na pagina da extensao 'Baixar NFSe' na Chrome Web Store.
echo.
echo  Voce precisa apenas:
echo    1. Clicar em 'Usar no Chrome' (instalar)
echo    2. Confirmar
echo    3. Fechar o Chrome
echo.
echo  Depois disso, a automacao vai funcionar normalmente.
echo.
pause

REM Caminho do perfil isolado (mesmo de config.py)
set "PROFILE_DIR=%LOCALAPPDATA%\Google\Chrome NFSe Automacao"

REM Caminho do Chrome
set "CHROME_EXE=%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" set "CHROME_EXE=%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME_EXE%" (
    echo ERRO: Chrome nao encontrado em Program Files.
    echo Instale o Google Chrome e tente novamente.
    pause
    exit /b 1
)

echo Abrindo Chrome com perfil isolado...
echo.
echo  Perfil: %PROFILE_DIR%
echo  URL:    Chrome Web Store - Baixar NFSe
echo.

start "" "%CHROME_EXE%" ^
    --user-data-dir="%PROFILE_DIR%" ^
    --no-first-run ^
    --no-default-browser-check ^
    "https://chromewebstore.google.com/detail/enehmclajcndmgefbmjhecccoegbdgea"

echo.
echo  Aguardando o Chrome ser fechado para finalizar...
echo  (Quando terminar de instalar a extensao, feche o Chrome)
echo.
pause
