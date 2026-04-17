# ✅ NFSe Automação - Setup Checklist

Complete os passos abaixo para ter a automação 100% funcional.

## 📦 Instalação Base
- [x] Python 3.10+ instalado
- [x] Dependências em `requirements.txt` instaladas (`pip install -r requirements.txt`)
- [x] `dist/NFSE_Automacao.exe` compilado

## 🔐 Certificados Digitais
- [ ] Pasta de certificados (.pfx) existe em: `G:\Meu Drive\CONX\CERTIFICADO DIGITAL CLIENTES`
- [ ] Cada arquivo segue padrão: `<NOME> senha <SENHA>.pfx`
  - ✓ Exemplo válido: `EMPRESA ABC senha MinhaSenha123.pfx`
  - ✓ Exemplo válido: `Empresa XYZ_senha 987654.pfx`
- [ ] Pelo menos 1 certificado válido na pasta
- [ ] Abra `dist/NFSE_Automacao.exe` → clique "Contar certificados"
  - Deve mostrar quantidade total, válidos e com erro

## 📋 Planilha de Clientes
- [ ] Arquivo `clientes.xlsx` criado (já incluído como exemplo)
- [ ] Contém colunas: `CNPJ` | `NOME`
- [ ] Tem pelo menos 1 linha de dados

## 🌐 Portal NFSe
- [ ] Você tem acesso a: https://www.nfse.gov.br/EmissorNacional
- [ ] Consegue fazer login com certificado manualmente (teste)
- [ ] Consegue acessar "Notas Emitidas"
- [ ] Consegue ver a tabela de notas ou mensagem "Sem resultados"

## 🎮 Descobrir Seletores CSS (Essencial!)

**Passo 1:** Abra o script descobridor
```bash
python discover_selectors.py
```

**Passo 2:** No portal aberto, pressione F12 para DevTools

**Passo 3:** Inspecione cada elemento e copie o seletor CSS:

### Seletor: Data Início
1. Clique no ícone inspecionar (lupa no DevTools)
2. Clique no campo "Data Início" da página
3. Copie o `<input>` completo do DevTools
4. Procure por atributos como `name=`, `id=`, `class=`
5. Seletor típico: `input[name='DataInicio']` ou `#dataInicio`

Coloque em `config.py`:
```python
NFSE_SELECTOR_DATA_INICIO = "input[name='DataInicio']"  # seu seletor aqui
```

### Seletor: Data Fim
Repita o processo acima para o campo "Data Fim"
```python
NFSE_SELECTOR_DATA_FIM = "input[name='DataFim']"  # seu seletor aqui
```

### Seletor: Botão Filtrar
Inspecione o botão "Filtrar" ou "Pesquisar"
```python
NFSE_SELECTOR_BOTAO_FILTRAR = "button:has-text('Filtrar')"  # ou seu seletor
```

### Seletor: Linhas da Tabela
Inspecione uma `<tr>` (linha) da tabela de notas
```python
NFSE_SELECTOR_LINHAS_NOTAS = "table tbody tr"  # ou seu seletor
```

### Atalho da Extensão
1. Na mesma janela, abra DevTools Extensions (F12 → Extensions)
2. Procure por "Baixar NFSe" ou similar
3. Olhe no painel de controle da extensão pelo atalho teclado exibido
4. Típico: `Control+Shift+Y`, `Ctrl+Alt+D`, etc.

```python
NFSE_ATALHO_EXTENSAO = "Control+Shift+Y"  # seu atalho aqui
```

## 📝 Editar config.py

Abra `config.py` com um editor de texto e preencha:

```python
# Seus seletores descobertos acima
NFSE_SELECTOR_DATA_INICIO = "..."  # Cole aqui
NFSE_SELECTOR_DATA_FIM = "..."
NFSE_SELECTOR_BOTAO_FILTRAR = "..."
NFSE_SELECTOR_LINHAS_NOTAS = "..."
NFSE_ATALHO_EXTENSAO = "..."
```

Salve o arquivo.

## 🧪 Teste Completo

1. Abra `dist/NFSE_Automacao.exe`
2. Clique em "Contar certificados"
   - [ ] Deve listar quantidade sem erros
3. Verifique "Período": "Usar mês anterior"
4. Clique "Executar agora"
   - [ ] Navegador abre automaticamente
   - [ ] Faz login com certificado (sem prompts)
   - [ ] Acessa página de notas
   - [ ] Spinner rotativo aparece ao lado do botão
   - [ ] Logs mostram progresso
5. Após terminar:
   - [ ] Status muda para "Concluído" (verde)
   - [ ] Toast de sucesso aparece (canto inferior direito)
   - [ ] Arquivos baixados em `G:\Meu Drive\Automações\NFSE\Downloads\{CNPJ}\`

## 🚨 Se Der Erro

### Erro: "Nao foi possivel detectar notas"
→ Seletor `NFSE_SELECTOR_LINHAS_NOTAS` incorreto
→ Volte a DevTools, inspecione uma linha da tabela novamente

### Erro: "Botao de download nao encontrado"
→ Faltou `NFSE_ATALHO_EXTENSAO` em config.py
→ Ou seletor do botão está errado

### Erro: "Timeout no login"
→ Aumentar `PLAYWRIGHT_LOGIN_TIMEOUT_S` em config.py (padrão 45s)

### Navegador não abre / Arquivo não baixa
→ Verificar `CHROME_EXTENSION_DIR` se usando extensão customizada
→ Ou testar manualmente fazer login + download no portal

## 📊 Resultado Final

Se tudo passar:
- [ ] Arquivos .zip baixados em `Downloads/{CNPJ}/` com timestamps
- [ ] Logs mostram "Deteccao de notas" → "Download detectado"
- [ ] Para cada CNPJ: 1 arquivo com data/hora

---

**Checklist Complete! ✓** Automação pronta para uso.

Próximas execuções: basta clicar "Executar agora" na GUI.
