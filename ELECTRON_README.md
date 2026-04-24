# NFSe Automacao — Electron + FastAPI

App desktop profissional com interface moderna, animações fluidas e splash screen animado.

## Arquitetura

```
NFSe_Automacao.exe
├── Electron (janela nativa)
│   └── renderer/ (HTML5 + CSS3 + JavaScript vanilla)
└── Python FastAPI (processo background)
    ├── Port: 17432
    └── Endpoints: /health, /config, /certificados, /executar, etc.
```

## Desenvolvimento

### 1. Instalar dependências

```bash
# Python
pip install -r requirements.txt

# Electron
cd electron
npm install
cd ..
```

### 2. Rodar em desenvolvimento

Terminal 1 (FastAPI backend):
```bash
python api/server.py
```

Terminal 2 (Electron):
```bash
cd electron
npm start
```

A janela abre com splash screen, aguarda backend, e mostra a interface.

## Build para .exe

```bash
cd electron
npm run build
```

Gera: `electron/dist/NFSe Automacao Setup.exe`

## Estrutura de pastas

```
NFSE/
├── electron/
│   ├── main.js                  # Main process (spawn Python, ciclo de vida)
│   ├── preload.js               # Segurança (sandbox)
│   ├── package.json             # Dependências Node
│   └── renderer/
│       ├── index.html           # Shell HTML
│       ├── css/                 # Estilos (base, sidebar, cards, logs, toast, splash)
│       └── js/                  # Lógica (api, app, pages, splash, toasts)
├── api/
│   └── server.py                # FastAPI backend
├── nfse_automacao.py            # Motor original (não modificado)
├── cert_reader.py               # Leitor certs (não modificado)
├── config.py                    # Configuração
└── requirements.txt             # Python deps (+ fastapi, uvicorn)
```

## Recursos

✅ **Splash screen animado** — logo + barra de progresso  
✅ **Interface moderna** — paleta verde/escuro corporativa  
✅ **Animações CSS suaves** — hover lift, glow, transições  
✅ **Sidebar navegável** — Executar, Configurações, Sobre  
✅ **Logs em tempo real** — via polling do backend  
✅ **Responsivo** — grid layout, overflow handling  
✅ **Dark mode** — estilos para tema futuro  

## Endpoints FastAPI

| Método | Path | Descrição |
|--------|------|-----------|
| GET | `/health` | Health check (Electron aguarda) |
| GET | `/config` | Retorna seções + valores de config.py |
| POST | `/config` | Salva valores em config.py |
| GET | `/certificados?incluir_lista=true` | Lista certs + estatísticas |
| POST | `/executar` | Inicia execução assíncrona (`jobId`) |
| GET | `/executar/{jobId}/status` | Status + logs do job |
| POST | `/executar/{jobId}/cancelar` | Cancela execução |

## Paleta de cores

```css
--bg-main:    #0b1220  (azul muito escuro)
--bg-sidebar: #0f1724  (azul escuro)
--bg-panel:   #111c2f  (azul painel)
--bg-card:    #17243a  (azul card)
--accent:     #2aa889  (verde)
--success:    #40cf84  (verde claro)
--warning:    #f1b34f  (laranja)
--danger:     #e86a6a  (vermelho)
--text-1:     #eef4ff  (texto principal)
--text-2:     #9db1ca  (texto secundário)
--border:     #263753  (bordas)
```

## Animações principais

- **Splash barra**: `fillBar` 1.2s cubic-bezier
- **Sidebar nav ativo**: barra verde deslizante
- **Card hover**: lift + box-shadow
- **Botão Executar**: glow pulsante 1.4s
- **Page transition**: fadeSlide 220ms
- **Toast entrada**: spring 300ms cubic-bezier(0.34,1.56,.64,1)

## Troubleshooting

### "Backend não responde"
```bash
# Verificar se FastAPI está rodando
python api/server.py
# Deve exibir: Uvicorn running on http://127.0.0.1:17432
```

### "Erro ao carregar config"
```bash
# Validar config.py
python -c "import config; print(config.PASTA_CERTS)"
```

### Build falha
```bash
# Limpar cache
rm -rf electron/dist electron/node_modules

# Reinstalar
cd electron && npm install && npm run build
```

## Versão

- **NFSe Automacao**: v2.3
- **Electron**: 29.0+
- **Node**: 18.0+
- **Python**: 3.10+

---

**Mantém a lógica Python intacta, adiciona interface moderna via Electron + FastAPI.**
