#!/usr/bin/env python3
"""
discover_selectors.py - Utilitario para descobrir seletores CSS/XPath no portal NFSe.

Abre o portal em modo headless e permite inspecionar elementos.
Use F12 DevTools no navegador para copiar seletores CSS.
"""

from playwright.sync_api import sync_playwright
import config

def discover():
    """Abre o portal NFSe com Playwright para inspeção manual."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"\n{'='*60}")
        print("Abrindo Portal NFSe para descoberta de seletores...")
        print(f"{'='*60}\n")

        print(f"URL de login: {config.NFSE_LOGIN_URL}")
        print(f"URL de notas: {config.NFSE_EMITIDAS_URL}")

        print("\nPassos:")
        print("1. Faça login com certificado (será auto-selecionado)")
        print("2. Acesse a página de 'Notas Emitidas'")
        print("3. Pressione F12 para abrir DevTools")
        print("4. Clique no ícone 'inspecionar' (seta/lupa)")
        print("5. Clique no elemento que quer (campo data, botão, tabela)")
        print("6. Copie o seletor CSS que aparece no DevTools")
        print("\nExemplos de seletores:")
        print("  - Campo de data: input[name='DataInicio'], #dataInicio, etc.")
        print("  - Botão: button:has-text('Filtrar'), #btnFiltrar, etc.")
        print("  - Tabela: table tbody tr, #tabNotas > tr, etc.")
        print("\nEscreva os seletores encontrados em config.py")
        print(f"{'='*60}\n")

        page.goto(config.NFSE_LOGIN_URL, wait_until="domcontentloaded")

        print("Portal aberto. Inspeção iniciada.")
        print("Janela se fechará quando você fechar o navegador.\n")

        # Aguarda o usuário fechar manualmente
        page.wait_for_url("**/EmissorNacional**", timeout=300000)

        browser.close()
        print("\n✓ Descoberta concluída!")

if __name__ == "__main__":
    discover()
