# NFSe Automação

Solução desktop para automação de download de Notas Fiscais de Serviço Eletrônicas (NFSe) do portal nacional [nfse.gov.br](https://www.nfse.gov.br), desenvolvida para escritórios de contabilidade que gerenciam múltiplos CNPJs.

---

## O que faz

O sistema acessa o portal NFSe de forma automatizada usando certificados digitais A1 (`.pfx`), aplica filtros de período, detecta e baixa as notas de cada cliente em sequência — sem intervenção manual em nenhuma etapa.

**Fluxo de execução:**

1. Lê todos os certificados digitais da pasta configurada
2. Abre o navegador via Playwright e faz login com cada certificado
3. Aplica o filtro de período (mês anterior ou intervalo personalizado)
4. Detecta a existência de notas emitidas
5. Aciona o download via extensão do Chrome
6. Aguarda e organiza os arquivos por CNPJ
7. Repete para todos os clientes em sequência
8. Envia relatório por e-mail ao final (opcional)

---

## Interface

App desktop cross-platform (Windows e macOS) com UI construída em **Electron + React + Framer Motion**.

- Painel de execução com progresso em tempo real por cliente
- Cards de status (total processado, erros, período)
- Logs técnicos com filtro por nível e busca
- Gerenciamento de lista de clientes (CNPJ/CPF + nome)
- Editor de configurações integrado
- Toasts de feedback, animações de transição entre páginas

---

## Stack

| Camada | Tecnologia |
|---|---|
| Interface | Electron + React 18 + Framer Motion |
| Build frontend | Vite |
| Backend local | FastAPI + Python |
| Automação web | Playwright (Chromium) |
| Certificados | cryptography (PKCS#12) |
| Planilhas | openpyxl |
| Empacotamento | electron-builder (NSIS / DMG) + PyInstaller |

---

## Status

Produto em uso ativo na **CONX Contabilidade**.

Esta automação é **proprietária** — desenvolvida exclusivamente para uso interno ou mediante contratação. O código está disponível aqui como portfólio técnico.

> Para licenciamento ou interesse em uso: entre em contato.

---

*v2.3 — 2025*
