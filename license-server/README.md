# Servidor de Licenças NFSe Automação (Vercel + Upstash Redis)

Valida as licenças do app e oferece um **painel admin** para gerenciar clientes:
criar/revogar chaves, limite de máquinas, validade, ver quem está ativo.

- `GET /` → painel admin (protegido por usuario/senha)
- `POST /api/validate` → usado pelo app (`{key, machine_id}` → `{valid, message}`)
- `POST /api/clientes` → clientes salvos por licenca + maquina (`op: "get"|"save"`)
- `POST /api/admin` → API de gerenciamento (headers `x-admin-user` e `x-admin-pass`)

---

## 1. Criar o banco (Upstash Redis — grátis)

No painel do **Vercel** → seu projeto → aba **Storage** → **Create Database** →
**Upstash for Redis** → plano **Free**. Ao conectar ao projeto, o Vercel cria
automaticamente as variáveis:

```
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
```

(Alternativa: criar em upstash.com e copiar as duas variáveis manualmente.)

## 2. Variáveis de ambiente (Vercel → Settings → Environment Variables)

| Variável | Valor |
|---|---|
| `ADMIN_USER` | usuario do painel admin |
| `ADMIN_PASS` | senha forte do painel admin |
| `ADMIN_TOKEN` | legado/opcional: ainda aceito por compatibilidade com integracoes antigas |
| `CLIENT_SECRET` | **mesmo** valor de `DEFAULT_CLIENT_SECRET` em `electron/license-client.js` |
| `VALID_KEYS` | (opcional) chaves antigas separadas por vírgula |
| `ALLOW_LEGACY_KEYS` | defina `1` apenas se precisar aceitar `VALID_KEYS` sem vínculo de máquina |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | criadas no passo 1 |

## 3. Deploy

```bash
cd license-server
npm install
vercel --prod
```

O app aponta por padrão para:

```
https://license-server-sigma-topaz.vercel.app
```

O Electron envia esta configuração para o backend Python via variáveis de
ambiente:

```
NFSE_LICENSE_SERVER_URL
NFSE_LICENSE_VALIDATE_URL
NFSE_LICENSE_ADMIN_URL
NFSE_CLIENTES_URL
NFSE_CLIENT_SECRET
```

Para trocar de domínio, altere `DEFAULT_LICENSE_SERVER_URL` em
`electron/license-client.js` ou defina `NFSE_LICENSE_SERVER_URL` no ambiente
antes de iniciar o app. O backend Python (`api/license.py`) usa a mesma
configuração recebida do Electron.

## 4. Usar o painel

Abra `https://SEU-PROJETO.vercel.app/` → informe usuario e senha → 
crie licenças (gera a chave e copia), defina máquinas/validade, bloqueie/exclua.

O usuario definido em `ADMIN_USER` / `ADMIN_PASS` na Vercel funciona como acesso
root/de recuperacao. Pelo painel, use a secao **Usuarios admin** para criar
outros usuarios; eles ficam salvos no Redis com senha hashada.

---

## Como funciona a validação

- Chave **existe no banco**: confere `status` (ativa/bloqueada), `validade` e
  **vínculo de máquina** (registra até `maxMachines` máquinas ativas; além disso, recusa).
  Máquina bloqueada não se recadastra automaticamente. Atualiza `lastSeen` a cada verificação.
- Chave **não está no banco** mas está em `VALID_KEYS`: só aceita se `ALLOW_LEGACY_KEYS=1`.
- Banco indisponível: só cai no `VALID_KEYS` se `ALLOW_LEGACY_KEYS=1`.

## Modelo de dados (Redis)

- `lic:index` (set) → todas as chaves
- `lic:<CHAVE>` (json) → `{ clientName, status, maxMachines, machines, expiresAt, createdAt, lastSeen, notes }`
- `clientes:<HASH_CHAVE>:<MACHINE_ID>` (json) → `{ clientes, updatedAt }`
