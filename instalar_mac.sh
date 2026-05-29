#!/bin/bash
# =============================================================================
# instalar_mac.sh - Setup + build do NFSe Automacao no macOS
# Uso: chmod +x instalar_mac.sh && ./instalar_mac.sh
# Gera: dist/NFSe_Automacao.app
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== NFSe Automacao — Build macOS ==="
echo ""

# ── 1. Localiza Python 3.11+ com Tk 8.6 proprio (nao o do Xcode/sistema) ─────
# O Python 3.9 do Xcode usa Tcl/Tk 8.5 que crasha no macOS 14/15 (Sequoia).
# Python instalado via Homebrew ou python.org vem com Tk 8.6 proprio.

find_python() {
    # Homebrew Intel (/usr/local) e Apple Silicon (/opt/homebrew)
    for candidate in \
        /usr/local/bin/python3.12 \
        /usr/local/bin/python3.11 \
        /opt/homebrew/bin/python3.12 \
        /opt/homebrew/bin/python3.11 \
        /usr/local/opt/python@3.12/bin/python3.12 \
        /usr/local/opt/python@3.11/bin/python3.11 \
        /opt/homebrew/opt/python@3.12/bin/python3.12 \
        /opt/homebrew/opt/python@3.11/bin/python3.11; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    # Python.org installer (coloca em /Library/Frameworks)
    for candidate in \
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN=$(find_python || true)

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERRO] Python 3.11 ou 3.12 nao encontrado."
    echo ""
    echo "  O Python do Xcode (3.9) usa Tcl/Tk 8.5 que crasha no macOS 15."
    echo "  Instale Python 3.11 ou 3.12 via Homebrew:"
    echo ""
    echo "    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo "    brew install python@3.11"
    echo ""
    exit 1
fi

PY_VER=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[OK] Python $PY_VER encontrado em $PYTHON_BIN"

# ── 2. Recria o ambiente virtual com o Python correto ─────────────────────────
# Remove venv antigo se foi criado com Python errado (3.9 do Xcode)
if [ -d ".venv_mac" ]; then
    VENV_PY=$(.venv_mac/bin/python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    if [ "$VENV_PY" = "3.9" ]; then
        echo "[...] Removendo venv antigo (Python 3.9 incompativel)..."
        rm -rf .venv_mac
    fi
fi

if [ ! -d ".venv_mac" ]; then
    echo "[...] Criando ambiente virtual .venv_mac com Python $PY_VER..."
    "$PYTHON_BIN" -m venv .venv_mac
fi

source .venv_mac/bin/activate
echo "[OK] Ambiente virtual ativado: .venv_mac"

# ── 3. Dependencias ───────────────────────────────────────────────────────────
echo ""
echo "[...] Instalando dependencias (requirements_mac.txt)..."
pip install --upgrade pip --quiet
pip install -r requirements_mac.txt --quiet
echo "[OK] Dependencias instaladas"

# ── 4. Playwright (drivers do navegador) ─────────────────────────────────────
echo ""
echo "[...] Instalando driver Playwright (Chromium)..."
python3 -m playwright install chromium
echo "[OK] Playwright pronto"

# ── 5. config.py (usa config_mac.py se config.py nao existir) ─────────────────
if [ ! -f "config.py" ]; then
    echo ""
    echo "[...] config.py nao encontrado — copiando config_mac.py -> config.py"
    cp config_mac.py config.py
    echo "[OK] config.py criado a partir de config_mac.py"
    echo "     EDITE config.py para apontar para suas pastas de certificados."
else
    echo "[OK] config.py ja existe (nao foi sobrescrito)"
fi

# ── 6. Build PyInstaller ──────────────────────────────────────────────────────
echo ""
echo "[...] Gerando NFSe_Automacao.app com PyInstaller..."
pyinstaller --noconfirm NFSE_Automacao_mac.spec

# ── 7. Copia config.py para dentro do bundle ─────────────────────────────────
if [ -d "dist/NFSe_Automacao.app" ]; then
    APP_RESOURCES="dist/NFSe_Automacao.app/Contents/MacOS"
    cp config.py "$APP_RESOURCES/config.py"
    echo "[OK] config.py copiado para $APP_RESOURCES"
fi

echo ""
echo "======================================================"
echo " Build concluido!"
echo " App gerado em: dist/NFSe_Automacao.app"
echo ""
echo " Para rodar:"
echo "   open dist/NFSe_Automacao.app"
echo ""
echo " IMPORTANTE — macOS exige permissoes:"
echo "   Preferencias do Sistema > Privacidade > Acessibilidade"
echo "   Adicione o NFSe_Automacao.app para que pyautogui funcione."
echo "======================================================"
