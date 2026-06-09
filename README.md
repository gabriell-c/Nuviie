# Nuviie SaaS Tools Hub

## 📖 Visão Geral

O **Nuviie Hub de Ferramentas SaaS** é uma plataforma completa para agências digitais, desenvolvida com **Python + Django + Django REST Framework** no backend e **Django Templates + Tailwind CSS** no frontend. Foi projetada para ser **modular, escalável e de alta performance**, pronta para evoluir rumo a uma arquitetura de micro‑services.

---

## 🚀 Como Instalar

1. **Pré‑requisitos**
   - Python 3.10+ (recomendado 3.13)
   - PostgreSQL (ou SQLite para testes rápidos)
   - Git (para clonar o repositório)

2. **Clonar o repositório**
   ```bash
   git clone https://github.com/yourorg/nuviie.git
   cd nuviie
   ```

3. **Criar e ativar o ambiente virtual**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   ```

4. **Instalar dependências**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configurar o banco de dados**
   - Crie um banco PostgreSQL e um usuário.
   - Copie o arquivo `.env.example` para `.env` e ajuste as variáveis:
     ```text
     DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/nuviie
     SECRET_KEY=uma_chave_secreta_aleatoria
     DEBUG=True
     ```

6. **Aplicar migrações**
   ```bash
   python manage.py migrate
   ```

7. **Criar super‑usuário (admin)**
   ```bash
   python manage.py createsuperuser
   ```

8. **Iniciar o servidor**

### Desenvolvimento
```bash
python manage.py runserver 0.0.0.0:8000
```
Abra o navegador em `http://127.0.0.1:8000/`.

### Produção (Windows)
Instale um servidor WSGI nativo, como **waitress**:

```bash
pip install waitress
python manage.py collectstatic --noinput   # opcional, mas recomendado
waitress-serve --listen=0.0.0.0:8000 nuviie.wsgi:application
```

> `gunicorn` não funciona no Windows pois depende do módulo `fcntl`. Use `waitress` (ou `uvicorn`/`daphne` para ASGI) em produção.

---

## 🛠️ Como Usar

A aplicação está organizada em três módulos principais:

### 1. **Leads**
- **Coleta**: Scrapers (Google Maps, Instagram) usando *dorks* e fallback determinístico.
- **Qualidade**: Scoring automático com deduplicação e normalização de telefones.
- **Interface**: Dashboard com gráficos animados (Tailwind + Alpine.js) e visualização em Kanban (SortableJS).

### 2. **CRM (Kanban Pipeline)**
- Gestão de oportunidades por estágio (Lead → Qualificado → Proposta → Fechado).
- Modal de criação/edição rápido, arrastar‑e‑soltar de cards.
- API RESTful para integração externa.

### 3. **Contratos**
- **Geração**: PDFs customizados via ReportLab a partir de templates com placeholders `{{variavel}}`.
- **Leitura**: Extração de dados com pdfplumber.
- Histórico de documentos vinculados ao lead.

Acesse cada módulo pelo menu superior após fazer login.

---

## 🧰 Ferramentas Utilizadas

| Camada | Tecnologia |
|--------|------------|
| Backend | Python 3.13, Django 4.x, Django‑REST‑Framework |
| Banco de Dados | PostgreSQL (ou SQLite) |
| Frontend | Django Templates, Tailwind CSS, Alpine.js, SortableJS |
| Scraping | requests, beautifulsoup4, duckduckgo‑html‑dorks |
| PDF | reportlab, pdfplumber |
| Deploy | gunicorn, whitenoise (static files) |

---

## ⚠️ Limitações Conhecidas

- **Scrapers baseados em dorks** podem ser bloqueados por rate‑limit ou CAPTCHAs; o fallback simulado garante funcionalidade de teste, mas não substitui scraping real em produção.
- **Tailwind CSS** está configurado para *just‑in‑time* compilation; mudanças de estilo podem exigir recompilação do CSS.
- O módulo de **autenticação por WhatsApp** depende de uma API externa; disponibilidade da API afeta a verificação de números.
- O projeto atualmente roda como **monólito**; embora a estrutura modular facilite a extração para micro‑services, isso ainda não foi implementado.

---

## 🏗️ Arquitetura

```
Nuviie/
├─ core/                # Configurações globais (settings, urls)
├─ authentication/      # Login, WhatsApp verification, JWT
├─ leads/               # Scrapers, modelo Lead, API & UI
├─ crm/                 # Kanban pipeline, cards, API
├─ contracts/           # PDF generator/reader, modelo Contract
├─ static/ & templates/ # Tailwind, Alpine, UI components
└─ manage.py            # CLI do Django
```

- Cada app segue a **filosofia “thin models, fat services”**: lógica de negócio encapsulada em `services.py`.
- As APIs são versionadas (`/api/v1/…`) para facilitar a evolução.
- **Segurança**: CSRF, CORS configurados; senhas e chaves nunca são versionadas (arquivo `.env`).

---

## 🎨 Design & Experiência

- Tema escuro/premium com paleta de cores azul‑cobalto e acentos neon.
- Micro‑interações: transições suaves, animações de carregamento “skeleton” nos dashboards.
- Responsivo: mobile‑first, utilizando Tailwind utilities.

---

## 📚 Contribuindo

1. Fork o repositório
2. Crie uma branch `feature/SEU_TEMA`
3. Submeta um Pull Request
4. Siga o padrão de linting (`flake8`, `black`)

---

## 📄 Licença

Este projeto está licenciado sob a **MIT License** – sinta‑se livre para usar, modificar e distribuir.

---

*Feito com ❤️ pela equipe Nuviie*
