"""
iniciar.py - Inicia o servidor Flask e o ngrok em um só comando.

Uso:
    python iniciar.py

O script:
  1. Inicia o api_server.py em background
  2. Inicia o ngrok na porta 5000
  3. Lê a URL pública do ngrok automaticamente
  4. Atualiza o config.py com a nova URL
  5. Mantém tudo rodando até Ctrl+C
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.py"
PYTHON = sys.executable


def iniciar_flask() -> subprocess.Popen:
    print("[1/3] Iniciando servidor Flask na porta 5000...")
    proc = subprocess.Popen(
        [PYTHON, str(BASE_DIR / "api_server.py")],
        cwd=str(BASE_DIR),
    )
    time.sleep(2)
    print("      Flask iniciado.")
    return proc


def iniciar_ngrok() -> subprocess.Popen:
    print("[2/3] Iniciando ngrok na porta 5000...")
    proc = subprocess.Popen(
        ["ngrok", "http", "5000"],
        cwd=str(BASE_DIR),
    )
    time.sleep(3)
    print("      Ngrok iniciado.")
    return proc


def obter_url_ngrok(tentativas: int = 10) -> str:
    print("[3/3] Obtendo URL pública do ngrok...")
    for i in range(tentativas):
        try:
            resp = requests.get("http://localhost:4040/api/tunnels", timeout=5)
            tunnels = resp.json().get("tunnels", [])
            for tunnel in tunnels:
                url = tunnel.get("public_url", "")
                if url.startswith("https://"):
                    return url
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("Não foi possível obter a URL do ngrok após várias tentativas.")


def atualizar_config(url: str) -> None:
    texto = CONFIG_PATH.read_text(encoding="utf-8")
    novo = re.sub(
        r'(API_URL\s*=\s*")[^"]*(")',
        rf'\g<1>{url}\g<2>',
        texto,
    )
    CONFIG_PATH.write_text(novo, encoding="utf-8")
    print(f"      config.py atualizado: API_URL = \"{url}\"")


def main() -> None:
    print("=" * 50)
    print("  NFSe Automação - Inicializando")
    print("=" * 50)

    flask_proc = iniciar_flask()
    ngrok_proc = iniciar_ngrok()

    try:
        url = obter_url_ngrok()
        atualizar_config(url)
    except RuntimeError as exc:
        print(f"ERRO: {exc}")
        flask_proc.terminate()
        ngrok_proc.terminate()
        sys.exit(1)

    print()
    print("=" * 50)
    print(f"  Tudo pronto!")
    print(f"  URL pública: {url}")
    print(f"  Pressione Ctrl+C para encerrar.")
    print("=" * 50)

    try:
        flask_proc.wait()
    except KeyboardInterrupt:
        print("\nEncerrando...")
        flask_proc.terminate()
        ngrok_proc.terminate()


if __name__ == "__main__":
    main()
