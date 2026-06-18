# Evolution API — servidor de WhatsApp do Nuviie

O Evolution API é um **servidor open-source** que você roda você mesmo. É dele
que saem a `EVOLUTION_API_URL` e a `EVOLUTION_API_KEY` que vão no `.env` do Nuviie.

## Caminho recomendado: rodar localmente com Docker (grátis)

### 1. Instale o Docker Desktop
- Windows/Mac: https://www.docker.com/products/docker-desktop/
- Abra o Docker Desktop e espere ficar "Running".

### 2. Configure as variáveis
```bash
cd deploy/evolution
copy .env.example .env        # Windows  (cp no Linux/Mac)
```
Edite o `.env` e defina:
- `AUTHENTICATION_API_KEY` → uma chave forte (será a sua `EVOLUTION_API_KEY`)
- `POSTGRES_PASSWORD` → qualquer senha forte

Gere uma chave forte:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Suba o servidor
```bash
docker compose up -d
```
Verifique: abra http://localhost:8080 — deve responder (JSON do Evolution).
Logs: `docker compose logs -f evolution`

### 4. Preencha o `.env` do Nuviie (na raiz `Nuviie/`)
```env
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=<o mesmo AUTHENTICATION_API_KEY que você definiu>

# Para RECEBER mensagens no CRM (webhook):
WHATSAPP_WEBHOOK_TOKEN=<gere outro token forte>
NUVIIE_PUBLIC_BASE_URL=<URL pública do CRM, ex.: https://crm.seudominio.com>
```

### 5. Conecte um número
1. Reinicie o Nuviie (`python manage.py runserver`).
2. Acesse **WhatsApp** no menu → **Adicionar número** → **Conectar**.
3. Leia o QR Code no celular: WhatsApp → Aparelhos conectados → Conectar um aparelho.

Pronto. Repita para um segundo número quando quiser.

---

## Sobre o RECEBIMENTO de mensagens (webhook)

Para o Evolution **entregar** as mensagens recebidas ao Nuviie, ele precisa
conseguir acessar a URL pública do CRM (`NUVIIE_PUBLIC_BASE_URL`).

- **Tudo local (mesmo PC):** se o Nuviie roda em `http://localhost:8000`, troque
  no `.env` do Nuviie `NUVIIE_PUBLIC_BASE_URL=http://host.docker.internal:8000`
  para o container do Evolution conseguir alcançar o Django no host.
- **Acesso remoto / produção:** use o **Cloudflare Tunnel** (veja o README
  principal) e aponte `NUVIIE_PUBLIC_BASE_URL` para `https://crm.seudominio.com`.

> Só **enviar** mensagens funciona sem webhook — basta `EVOLUTION_API_URL` + `EVOLUTION_API_KEY`.

---

## Alternativa: Evolution hospedado (pago, sem Docker)

Se não quiser manter o servidor, há provedores que vendem Evolution API "pronto"
(você procura por "Evolution API hospedada"). Eles te dão a **URL** e a **API key**
já prontas — é só colar no `.env` do Nuviie. Custa uma mensalidade, mas dispensa
Docker/manutenção.

---

## Comandos úteis

```bash
docker compose up -d        # subir
docker compose logs -f evolution   # ver logs
docker compose restart evolution   # reiniciar
docker compose down         # parar (mantém dados/sessões)
docker compose down -v      # parar e APAGAR tudo (vai precisar reconectar o QR)
```
