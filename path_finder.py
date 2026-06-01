"""Auto-descoberta de pastas usadas pela automacao NFSe.

Objetivo: o app deve funcionar em qualquer maquina (instalador), sem depender
de letra de unidade fixa nem caminho codificado.

- Certificados: ficam no Google Drive ("Meu Drive"/"My Drive") em
  CONX\\CERTIFICADO DIGITAL CLIENTES. A letra do drive muda por maquina.
- DOMINIO WEB: pasta local no disco do sistema (C:). A pasta "Simples Nacional"
  e criada dentro dela e usada como destino (PASTA_SAIDA).

Estrategia: cache -> deteccao automatica -> perguntar ao usuario (seletor de
pasta) na 1a execucao. A escolha do usuario fica salva no cache.
"""
from __future__ import annotations

import json
import os
import string
from pathlib import Path

# Nomes-alvo (constantes do cliente CONX / Google Drive)
GOOGLE_DRIVE_NAMES = ("Meu Drive", "My Drive")
CERT_PARENT_HINT = "CONX"
CERT_FOLDER_NAME = "CERTIFICADO DIGITAL CLIENTES"
DOMINIO_WEB_NAME = "DOMINIO WEB"
SIMPLES_NACIONAL_NAME = "Simples Nacional"

# Perfil Chrome isolado da automacao (criado por CONFIGURAR_EXTENSAO.bat) e a
# extensao 'Baixar NFSe' instalada nele. O perfil fica em %LOCALAPPDATA%.
CHROME_PROFILE_DIRNAME = "Chrome NFSe Automacao"
NFSE_EXTENSION_ID = "enehmclajcndmgefbmjhecccoegbdgea"


# ---------------------------------------------------------------------------
# Cache (persiste deteccao e escolhas do usuario entre execucoes)
# ---------------------------------------------------------------------------
def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "NFSE_Automacao"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def _cache_file() -> Path:
    return _cache_dir() / "paths.json"


def _load_cache() -> dict:
    try:
        return json.loads(_cache_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    try:
        _cache_file().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Deteccao de unidades / pastas
# ---------------------------------------------------------------------------
def _drive_roots() -> list[Path]:
    roots: list[Path] = []
    for letter in string.ascii_uppercase:
        p = Path(f"{letter}:\\")
        try:
            if p.exists():
                roots.append(p)
        except OSError:
            pass
    return roots


def _has_pfx(folder: Path) -> bool:
    try:
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() == ".pfx":
                return True
    except OSError:
        pass
    return False


def _shallow_find(base: Path, target_name: str, max_depth: int = 3) -> Path | None:
    """Procura uma subpasta com o nome alvo ate `max_depth` niveis."""
    target = target_name.casefold()
    frontier = [(base, 0)]
    while frontier:
        current, depth = frontier.pop(0)
        try:
            entries = [e for e in current.iterdir() if e.is_dir()]
        except OSError:
            continue
        for entry in entries:
            if entry.name.casefold() == target:
                return entry
        if depth + 1 <= max_depth:
            frontier.extend((e, depth + 1) for e in entries)
    return None


def find_google_drive_root() -> Path | None:
    """Acha a raiz do Google Drive ('Meu Drive'/'My Drive') em qualquer unidade."""
    for root in _drive_roots():
        for name in GOOGLE_DRIVE_NAMES:
            cand = root / name
            try:
                if cand.is_dir():
                    return cand
            except OSError:
                pass
    return None


def find_certs_folder() -> Path | None:
    """Acha a pasta de certificados dentro do Google Drive."""
    drive = find_google_drive_root()
    if not drive:
        return None
    direct = drive / CERT_PARENT_HINT / CERT_FOLDER_NAME
    try:
        if direct.is_dir():
            return direct
    except OSError:
        pass
    return _shallow_find(drive, CERT_FOLDER_NAME, max_depth=3)


def _extension_installed_in(profile: Path) -> bool:
    """True se a extensao 'Baixar NFSe' esta instalada no perfil Chrome."""
    try:
        return (profile / "Default" / "Extensions" / NFSE_EXTENSION_ID).is_dir()
    except OSError:
        return False


def find_extension_dir(profile: Path | None = None) -> Path | None:
    """Pasta da versao instalada da extensao 'Baixar NFSe' (com os icon*.png).

    Ex.: <profile>/Default/Extensions/<id>/<versao>/ — escolhe a versao mais
    recente disponivel. Usada para reconhecimento de imagem do icone.
    """
    profile = profile or find_chrome_profile()
    if not profile:
        return None
    base = profile / "Default" / "Extensions" / NFSE_EXTENSION_ID
    try:
        versoes = [d for d in base.iterdir() if d.is_dir()]
    except OSError:
        return None
    if not versoes:
        return None
    # Ordena por nome de versao (string) — a mais recente fica por ultimo.
    versoes.sort(key=lambda p: p.name)
    return versoes[-1]


def find_chrome_profile() -> Path | None:
    """Acha o perfil Chrome isolado da automacao em %LOCALAPPDATA%.

    Prioriza um perfil que ja tenha a extensao 'Baixar NFSe' instalada.
    """
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    profile = Path(base) / "Google" / CHROME_PROFILE_DIRNAME
    try:
        if profile.is_dir():
            return profile
    except OSError:
        pass
    return None


def find_dominio_web_folder() -> Path | None:
    """Acha a pasta 'DOMINIO WEB' em disco local (nunca no Google Drive)."""
    drive_gdrive = find_google_drive_root()
    gdrive_root = drive_gdrive.anchor if drive_gdrive else None

    candidates = [Path("C:/") / DOMINIO_WEB_NAME, Path.home() / DOMINIO_WEB_NAME]
    for c in candidates:
        try:
            if c.is_dir():
                return c
        except OSError:
            pass

    for root in _drive_roots():
        if gdrive_root and root.anchor == gdrive_root:
            continue  # pula a unidade do Google Drive
        cand = root / DOMINIO_WEB_NAME
        try:
            if cand.is_dir():
                return cand
        except OSError:
            pass
    return None


# ---------------------------------------------------------------------------
# Fallback interativo: seletor de pasta nativo (1a execucao)
# ---------------------------------------------------------------------------
def ask_folder(title: str) -> Path | None:
    """Abre um seletor de pasta nativo. Retorna None se cancelado/indisponivel."""
    if os.environ.get("NFSE_NO_PROMPT") == "1":
        return None
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        selecionado = filedialog.askdirectory(title=title)
        root.destroy()
        return Path(selecionado) if selecionado else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# API publica: resolve cada pasta (cache -> auto -> perguntar)
# ---------------------------------------------------------------------------
def resolve_certs_folder(interactive: bool = True) -> str | None:
    cache = _load_cache()
    cached = cache.get("pasta_certs")
    if cached and Path(cached).is_dir() and _has_pfx(Path(cached)):
        return cached

    found = find_certs_folder()
    if (not found or not _has_pfx(found)) and interactive:
        escolhido = ask_folder("Selecione a pasta de certificados digitais (.pfx)")
        if escolhido and escolhido.is_dir():
            found = escolhido

    if found and Path(found).is_dir():
        cache["pasta_certs"] = str(found)
        _save_cache(cache)
        return str(found)
    return None


def resolve_dominio_web_folder(interactive: bool = True) -> str | None:
    cache = _load_cache()
    cached = cache.get("dominio_web")
    if cached and Path(cached).is_dir():
        return cached

    found = find_dominio_web_folder()
    if not found and interactive:
        escolhido = ask_folder("Selecione a pasta DOMINIO WEB (no disco C:)")
        if escolhido and escolhido.is_dir():
            found = escolhido

    if found and Path(found).is_dir():
        cache["dominio_web"] = str(found)
        _save_cache(cache)
        return str(found)
    return None


def resolve_saida_folder(interactive: bool = True) -> str | None:
    """Pasta de saida = <DOMINIO WEB>/Simples Nacional (criada se nao existir)."""
    cache = _load_cache()
    cached = cache.get("pasta_saida")
    if cached and Path(cached).is_dir():
        return cached

    dominio = resolve_dominio_web_folder(interactive=interactive)
    if not dominio:
        return None

    saida = Path(dominio) / SIMPLES_NACIONAL_NAME
    try:
        saida.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    cache["pasta_saida"] = str(saida)
    _save_cache(cache)
    return str(saida)


# ---------------------------------------------------------------------------
# Integracao com config (preenche apenas quando necessario)
# ---------------------------------------------------------------------------
def _certs_value_needs_discovery(raw: str) -> bool:
    raw = (raw or "").strip()
    if not raw or raw == "Certificados":  # vazio ou placeholder padrao
        return True
    p = Path(raw)
    return not (p.is_dir() and _has_pfx(p))


def _saida_value_needs_discovery(raw: str) -> bool:
    raw = (raw or "").strip()
    if not raw or raw == "Downloads":  # vazio ou placeholder padrao
        return True
    return not Path(raw).is_dir()


def _profile_value_needs_discovery(raw: str) -> bool:
    raw = (raw or "").strip()
    if not raw or raw == "chrome-profile":  # vazio ou placeholder padrao
        return True
    p = Path(raw)
    if not p.is_dir():
        return True
    # Se aponta para um perfil sem a extensao, tenta achar um melhor.
    return not _extension_installed_in(p)


def auto_discover_into(config_module, interactive: bool = True) -> dict:
    """Preenche PASTA_CERTS e PASTA_SAIDA no modulo de config quando faltam.

    Nao sobrescreve um caminho valido configurado manualmente pelo usuario.
    Retorna um dict com o que foi resolvido (para log).
    """
    resultado: dict[str, str | None] = {}

    raw_certs = str(getattr(config_module, "PASTA_CERTS", "") or "")
    if _certs_value_needs_discovery(raw_certs):
        achado = resolve_certs_folder(interactive=interactive)
        if achado:
            setattr(config_module, "PASTA_CERTS", achado)
            resultado["PASTA_CERTS"] = achado

    raw_saida = str(getattr(config_module, "PASTA_SAIDA", "") or "")
    if _saida_value_needs_discovery(raw_saida):
        achado = resolve_saida_folder(interactive=interactive)
        if achado:
            setattr(config_module, "PASTA_SAIDA", achado)
            resultado["PASTA_SAIDA"] = achado

    # Perfil Chrome com a extensao 'Baixar NFSe' instalada.
    raw_prof = str(getattr(config_module, "CHROME_USER_DATA_DIR", "") or "")
    if _profile_value_needs_discovery(raw_prof):
        prof = find_chrome_profile()
        if prof:
            setattr(config_module, "CHROME_USER_DATA_DIR", str(prof))
            resultado["CHROME_USER_DATA_DIR"] = str(prof)

    # ID da extensao (constante do Web Store) — garante deteccao confiavel.
    if not str(getattr(config_module, "CHROME_EXTENSION_ID", "") or "").strip():
        setattr(config_module, "CHROME_EXTENSION_ID", NFSE_EXTENSION_ID)
        resultado["CHROME_EXTENSION_ID"] = NFSE_EXTENSION_ID

    # Pasta da extensao (com icon*.png) p/ reconhecimento de imagem do icone.
    raw_extdir = str(getattr(config_module, "CHROME_EXTENSION_DIR", "") or "").strip()
    if not raw_extdir or not Path(raw_extdir).is_dir():
        extdir = find_extension_dir()
        if extdir:
            setattr(config_module, "CHROME_EXTENSION_DIR", str(extdir))
            resultado["CHROME_EXTENSION_DIR"] = str(extdir)

    return resultado
