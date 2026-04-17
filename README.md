# 🚀 NFSe Automacao v2.3

Automação completa de downloads de Notas Fiscais Eletrônicas via portal NFSe com UI animada em customtkinter.

## ⚡ Quick Start

### 1. Executar (interface gráfica)
```bash
dist/NFSE_Automacao.exe
```

### 2. Configurar (primeira vez)
Abra `SETUP_CHECKLIST.md` e siga o guia passo-a-passo.

### 3. Usar
- Escolha período (ou "mês anterior")
- Clique "Executar agora"
- Acompanhe os logs
- Arquivos salvos em `Downloads/`

## 📁 Estrutura

```
NFSe_Automacao/
├── dist/
│   └── NFSE_Automacao.exe          ← Execute isto!
├── config.py                        ← Configure seletores aqui
├── SETUP_CHECKLIST.md              ← Guia de setup
├── CLAUDE.md                        ← Documentação técnica
├── gui_app.py                       ← Interface gráfica
├── ui_widgets.py                    ← Widgets animados
├── ui_animations.py                 ← Motor de animações
├── nfse_automacao.py               ← Motor Playwright
├── cert_reader.py                   ← Leitor de certificados
├── discover_selectors.py            ← Ajudante para achar seletores
└── clientes.xlsx                    ← Lista de CNPJs (opcional)
```

## ✨ Features

- ✅ **UI Animada**: splash, cards, botões com glow, toasts, spinners
- ✅ **Login automático**: certificado digital com auto-seleção
- ✅ **Detecção de notas**: regex + seletores CSS customizáveis
- ✅ **Download via extensão**: atalho teclado ou botão
- ✅ **Logs em tempo real**: painel filtrado e pesquisável
- ✅ **Múltiplos certs**: processados em paralelo ou sequencial
- ✅ **Configuração visual**: editor integrado de config.py
- ✅ **Relatório de certs**: conta total, válidos, com erro

## 🔧 Configuração

### Obrigatório (primeiro uso)
1. Abra `SETUP_CHECKLIST.md`
2. Execute `python discover_selectors.py`
3. Inspecione elementos no portal (F12 DevTools)
4. Copie seletores CSS em `config.py`

### Caminhos (padrão já configurado)
- **Certificados**: `G:\Meu Drive\CONX\CERTIFICADO DIGITAL CLIENTES`
- **Saída**: `G:\Meu Drive\Automações\NFSE\Downloads`
- **Perfil Chrome**: `G:\Meu Drive\Automações\NFSE\chrome-profile`

### Portal
- **URL Login**: `https://www.nfse.gov.br/EmissorNacional/Login`
- **URL Notas**: `https://www.nfse.gov.br/EmissorNacional`

## 🎯 Fluxo (O que acontece ao executar)

```
1. Lê todos os certificados .pfx (paralelo)
   ↓
2. Abre navegador via Playwright
   ↓
3. Faz login automático (certificado digital)
   ↓
4. Navega para "Notas Emitidas"
   ↓
5. Aplica filtro de período (via seletores CSS)
   ↓
6. Detecta quantas notas (conta ou regex)
   ↓
7. Se houver notas: aciona extensão (atalho teclado)
   ↓
8. Aguarda arquivo .zip na pasta Downloads/{CNPJ}/
   ↓
9. Repete para próximo CNPJ
   ↓
10. Envia relatório por e-mail (opcional, via Zoho SMTP)
```

## 📊 Logs

- **GUI**: painel integrado com filtro por nível + busca
- **Arquivo**: configure em `nfse_automacao.py` se precisar

## ⚙️ Tech Stack

- **Frontend**: customtkinter (dark theme, animações nativas)
- **Browser**: Playwright + Chromium
- **Certs**: cryptography (PKCS#12 parsing)
- **Excel**: openpyxl (leitura de clientes)
- **Email**: smtplib + Zoho SMTP

## 🐛 Troubleshooting

**"Nao foi possivel detectar notas"**
→ Seletor CSS errado → revise em `discover_selectors.py`

**"Extensao acionada, mas nenhum arquivo novo foi detectado"**
→ Atalho errado ou extensão não respondeu → verifique em DevTools

**"Timeout no login"**
→ Aumentar `PLAYWRIGHT_LOGIN_TIMEOUT_S` em config.py

Mais detalhes: veja `CLAUDE.md`

## 📜 Licença

Uso interno CONX Contabilidade.

---

**Versão**: 2.3 | **Status**: Production Ready ✓
