# Servidor de Licenças NFSe Automação (Vercel + Upstash Redis)

Valida as licenças do app e oferece um **painel admin** para gerenciar clientes:
criar/revogar chaves, limite de máquinas, validade, ver quem está ativo.

- `GET /` → painel admin (protegido por token)
- `POST /api/validate` → usado pelo app (`{key, machine_id}` → `{valid, message}`)
- `POST /api/admin` → API de gerenciamento (header `x-admin-token`)

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
| `ADMIN_TOKEN` | uma senha forte só sua (acesso ao painel) |
| `CLIENT_SECRET` | **mesmo** valor de `_CLIENT_SECRET` em `api/license.py` do app |
| `VALID_KEYS` | (opcional) chaves antigas separadas por vírgula — compatibilidade |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | criadas no passo 1 |

## 3. Deploy

```bash
cd license-server
npm install
vercel --prod
```

O app já aponta para `https://nfse-license.vercel.app/api/validate`
(veja `VALIDATION_URL` em `api/license.py`). Se o domínio do projeto for outro,
ajuste lá.

## 4. Usar o painel

Abra `https://SEU-PROJETO.vercel.app/` → informe o `ADMIN_TOKEN` → 
crie licenças (gera a chave e copia), defina máquinas/validade, bloqueie/exclua.

---

## Como funciona a validação

- Chave **existe no banco**: confere `status` (ativa/bloqueada), `validade` e
  **vínculo de máquina** (registra até `maxMachines` máquinas; além disso, recusa).
  Atualiza `lastSeen` a cada verificação.
- Chave **não está no banco** mas está em `VALID_KEYS`: aceita (modo legado).
- Banco indisponível: cai no `VALID_KEYS` para não derrubar clientes.

## Modelo de dados (Redis)

- `lic:index` (set) → todas as chaves
- `lic:<CHAVE>` (json) → `{ clientName, status, maxMachines, machines, expiresAt, createdAt, lastSeen, notes }`
