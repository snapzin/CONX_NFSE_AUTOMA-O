# Guia: Descobrir seletores CSS do portal NFSe

## Passo a passo

1. **Abra o portal** em modo de teste com um certificado:
   ```
   https://www.nfse.gov.br/EmissorNacional
   ```

2. **Faça login** com seu certificado digital

3. **Abra DevTools** (F12)

4. **Para cada seletor abaixo**, clique na lupa (inspect), depois clique no elemento na tela e copie o seletor CSS:

### Seletores a descobrir

#### `NFSE_SELECTOR_LOGIN_OK` — Elemento que aparece APÓS login bem-sucedido
- Procure por: badge de status, nome do usuário, qualquer elemento único após login
- Exemplo CSS: `span:has-text('Bem-vindo')` ou `.user-badge`

#### `NFSE_SELECTOR_DATA_INICIO` — Campo "Data Início" do filtro
- Procure por: input com name/id contendo "data" ou "inicio"
- Exemplo: `input[name='dataInicio']` ou `#txtDataInicio`

#### `NFSE_SELECTOR_DATA_FIM` — Campo "Data Fim" do filtro
- Procure por: input com name/id contendo "data" ou "fim"
- Exemplo: `input[name='dataFim']` ou `#txtDataFim`

#### `NFSE_SELECTOR_BOTAO_FILTRAR` — Botão "Filtrar" ou "Pesquisar"
- Procure por: `<button>Filtrar</button>` ou similar
- Exemplo: `button:has-text('Filtrar')` ou `#btnFiltrar`

#### `NFSE_SELECTOR_LINHAS_NOTAS` — Linhas da tabela de notas
- Procure por: `<tr>` dentro de `<table>`
- Exemplo: `table tbody tr` ou `.grid-row`

#### `NFSE_SELECTOR_BOTAO_BAIXAR` — Botão da extensão (se houver)
- Se a extensão adiciona um botão na página: procure pelo elemento
- Exemplo: `button.download-nfse` ou `[data-action="download"]`

#### `NFSE_ATALHO_EXTENSAO` — Atalho teclado da extensão (F12 > Extensions)
- Abra DevTools → Extensions (aba)
- Procure por "Keyboard shortcuts"
- Copie o atalho (ex: `Ctrl+Shift+Y`)

## Ferramenta rápida: DevTools Inspect

```javascript
// Cole isso no Console do DevTools (F12) para testar seletores:

// Testar data início
document.querySelectorAll('input[name*="data"], input[id*="data"]')

// Testar linhas da tabela
document.querySelectorAll('table tr')

// Testar botões
document.querySelectorAll('button')
```

## Dica: Usar modo "Usar mês anterior"

Se não conseguir os seletores, configure o app para:
```python
# Em config.py, deixe os seletores VAZIOS:
NFSE_SELECTOR_DATA_INICIO = ""
NFSE_SELECTOR_DATA_FIM = ""
NFSE_SELECTOR_BOTAO_FILTRAR = ""
```

O app vai usar o **mês anterior automaticamente** (padrão seguro).

---

**Depois de descobrir os seletores, atualize config.py e teste!**
