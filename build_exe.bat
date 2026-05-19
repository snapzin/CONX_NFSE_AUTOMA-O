@echo off
setlocal enabledelayedexpansion
title NFSe Automacao - Build EXE
cd /d "%~dp0"

echo.
echo ================================================================
echo   NFSe Automacao - Gerando executavel (.exe)
echo ================================================================
echo.

REM ── Verifica Python ──────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo        Instale o Python 3.10+ e tente novamente.
    pause & exit /b 1
)

REM ── Instala dependencias necessarias ─────────────────────────────
echo [1/4] Instalando dependencias...
python -m pip install --quiet --upgrade pyinstaller
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause & exit /b 1
)
echo       OK
echo.

REM ── Limpa builds anteriores ───────────────────────────────────────
echo [2/4] Limpando build anterior...
if exist "dist\NFSe_Automacao" rmdir /s /q "dist\NFSe_Automacao"
if exist "build\NFSe_Automacao"  rmdir /s /q "build\NFSe_Automacao"
echo       OK
echo.

REM ── Compila com PyInstaller ───────────────────────────────────────
echo [3/4] Compilando... (pode levar 2-5 minutos)
python -m PyInstaller NFSE_Automacao.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [ERRO] Falha na compilacao. Veja as mensagens acima.
    pause & exit /b 1
)
echo       OK
echo.

REM ── Copia arquivos externos necessarios ───────────────────────────
echo [4/4] Copiando arquivos de configuracao...

REM config.py fica fora do exe para poder ser editado sem rebuild
copy /y "config.py" "dist\NFSe_Automacao\config.py" >nul
if errorlevel 1 (
    echo [AVISO] Nao foi possivel copiar config.py
)

REM runtime_settings.json (estatisticas persistidas)
if exist "runtime_settings.json" (
    copy /y "runtime_settings.json" "dist\NFSe_Automacao\runtime_settings.json" >nul
)

echo       OK
echo.

echo ================================================================
echo   PRONTO!
echo.
echo   Pasta gerada: dist\NFSe_Automacao\
echo   Executavel:   dist\NFSe_Automacao\NFSe_Automacao.exe
echo.
echo   Para distribuir: compacte a pasta inteira em ZIP
echo   e envie para o usuario. Ele so precisa extrair
echo   e dar duplo clique em NFSe_Automacao.exe
echo.
echo   IMPORTANTE: o arquivo config.py dentro da pasta
echo   contem as configuracoes (caminhos, extensao, etc.)
echo   e pode ser editado com o Bloco de Notas.
echo ================================================================
echo.
pause
