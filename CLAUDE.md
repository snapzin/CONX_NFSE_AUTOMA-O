# NFSe Automacao - Guia de Configuração e Uso

## 📋 Fluxo de Automação (8 passos)

1. **Login com certificado digital** → Acessa o portal NFSe com auto-seleção de cert
2. **Navega para notas emitidas** → Abre a página de consulta
3. **Aplica filtro de período** → Define data início/fim via campos do formulário
4. **Detecta quantas notas** → Conta linhas da tabela ou busca por regex no HTML
5. **Se houver notas** → Aciona extensão "Baixar NFSe" (botão ou atalho teclado)
6. **Aguarda download** → Monitora a pasta de saída por novos arquivos
7. **Repete para todos os certificados** → Em ordem alfabética
8. **Envia relatório por e-mail** → (opcional, conforme config ZOHO_MAIL)

## 🔧 Configuração Obrigatória (config.py)

### Caminhos
```python
PASTA_CERTS = r"G:\Meu Drive\CONX\CERTIFICADO DIGITAL CLIENTES"  # Onde estão os .pfx
PASTA_SAIDA = r"G:\Meu Drive\Automações\NFSE\Downloads"           # Onde salvar XMLs
CHROME_USER_DATA_DIR = r"G:\Meu Drive\Automações\NFSE\chrome-profile"
```

### Portal NFSe
```python
NFSE_LOGIN_URL = "https://www.nfse.gov.br/EmissorNacional/Login?..."
NFSE_EMITIDAS_URL = "https://www.nfse.gov.br/EmissorNacional"
AUTOSELECT_CERTIFICATE_PATTERNS = "https://www.nfse.gov.br/*"
```

### Seletores (obtenha com F12 DevTools no portal)
Abra o portal em modo "Usar mês anterior" e use F12 para inspecionar:

```python
NFSE_SELECTOR_DATA_INICIO = "input[name='DataInicio']"  # Ou similar
NFSE_SELECTOR_DATA_FIM = "input[name='DataFim']"
NFSE_SELECTOR_BOTAO_FILTRAR = "button:has-text('Filtrar')"
NFSE_SELECTOR_LINHAS_NOTAS = "table tbody tr"  # Ou similar
NFSE_SELECTOR_BOTAO_BAIXAR = ""  # Se houver botão direto
NFSE_ATALHO_EXTENSAO = "Control+Shift+Y"  # Teclado da extensão (F12 > Extensions)
```

Para descobrir:
1. Abra portal → Acesse notas emitidas
2. Pressione F12 (DevTools)
3. Clique na lupa (inspecionar)
4. Clique no elemento que quer (data, botão, tabela)
5. Copia o seletor CSS visible no DevTools

### Planilha de Clientes (opcional)
Se tiver `clientes.xlsx` com colunas CNPJ e NOME, mude:
```python
XLSX_PATH = r"G:\Meu Drive\Automações\NFSE\clientes.xlsx"
```

## 🚀 Uso

### Via GUI (recomendado)
```bash
dist/NFSE_Automacao.exe
```
- Clique em **"Contar certificados"** pra validar leitura dos .pfx
- Selecione período (ou "usar mês anterior")
- Clique **"Executar agora"**
- Acompanhe logs em tempo real

### Via Terminal (debug)
```bash
python nfse_automacao.py  # Executa com mês anterior
```

## 📊 Fluxo de Dados

```
Certificados .pfx
    ↓
cert_reader.py → extrai CNPJ, CN, thumbprint
    ↓
gui_app.py (splash → cards → form → logs)
    ↓
nfse_automacao.py
    ├→ NFSePlaywrightRunner (Playwright)
    │  ├→ login com certificado (AutoSelectCertificateForUrls)
    │  ├→ aplica filtros (período)
    │  ├→ conta notas (regex ou seletor)
    │  └→ baixa via extensão (atalho teclado)
    └→ arquivos salvos em PASTA_SAIDA/{CNPJ}/{timestamp}.zip
```

## 🎯 Animações da UI

- **Splash**: fade-in logo na abertura (1s)
- **Sidebar**: barra verde left-slide no ativo, hover fade suave
- **Cards**: lift (bg + border fade) no hover, contador tweenado
- **Botão "Executar"**: glow pulsante verde (1.4s período)
- **Spinner**: círculo rotativo durante execução
- **Transição páginas**: barra cresce+some (560ms total)
- **Toasts**: deslizam do canto inferior direito com feedback (info/success/warning/error)

## 🔐 Segurança

- Certificados: lidos localmente via `cryptography`, nunca enviados
- Senhas: extraídas do nome do arquivo (.pfx), armazenadas apenas em RAM
- Chrome policy: usa `AutoSelectCertificateForUrls` (não prompts)
- Dados: salvos em `Downloads/` local

## ⚠️ Troubleshooting

### "PASTA_CERTS not found"
→ Verifique caminho em `config.py` (use caminhos Windows com `r"..."`)

### "Nao foi possivel detectar notas"
→ Configure `NFSE_SELECTOR_LINHAS_NOTAS` ou `NFSE_SELECTOR_TEXTO_SEM_NOTAS`

### Extension não baixa arquivo
→ Valide `NFSE_ATALHO_EXTENSAO` e `CHROME_EXTENSION_DIR` em config.py

### Timeout no login
→ Aumente `PLAYWRIGHT_LOGIN_TIMEOUT_S` (padrão 45s)

## 📝 Logs

- **GUI**: painel "Logs de execução" (filtro por nível, busca)
- **Arquivo**: `nfse.log` (se habilitado em código)

## 🔄 Atualizar

```bash
git pull  # pega novos códigos
pip install -r requirements.txt --upgrade
pyinstaller --noconfirm NFSE_Automacao.spec  # rebuild .exe
```

---

**Versão**: 2.3 | **Data**: 2026-04-17
