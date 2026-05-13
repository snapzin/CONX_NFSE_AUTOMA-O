@echo off
setlocal

echo ============================================================
echo  NFSe Automacao - Gerando executavel com PyInstaller
echo ============================================================
echo.

REM Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao encontrado no PATH.
    pause
    exit /b 1
)

REM Instala dependencias
echo Instalando dependencias...
python -m pip install --quiet --upgrade ^
    pyinstaller ^
    requests ^
    schedule ^
    flask ^
    selenium ^
    webdriver-manager ^
    cryptography

if errorlevel 1 (
    echo ERRO: Falha ao instalar dependencias.
    pause
    exit /b 1
)

echo.
echo Compilando...
python -m PyInstaller NFSeAutomacao.spec --noconfirm

if errorlevel 1 (
    echo.
    echo ERRO: Falha na compilacao! Verifique as mensagens acima.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  EXE gerado: dist\NFSeAutomacao.exe
echo  Copie o runtime_settings.json junto com o .exe.
echo ============================================================
echo.
pause
