# 🧠 Backend - Sistema de Controle de Acesso (FastAPI + Prisma)

## 📂 Estrutura do Projeto

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # ✅ FastAPI app entry point
│   ├── config.py                  # ✅ Configuration settings
│   ├── database.py                # ✅ Prisma client setup
│   │
│   ├── schemas/                   # Request/Response schemas
│   │   ├── __init__.py
│   │   ├── user.py                # ✅ User schemas
│   │   ├── access_rule.py         # ✅ Access rule schemas
│   │   ├── time_zone.py           # ✅ Time zone schemas
│   │   ├── audit.py               # ✅ Audit log schemas
│   │   └── sync.py                # ✅ Sync schemas
│   │
│   ├── services/                  # Business logic
│   │   ├── __init__.py
│   │   ├── user_service.py        # ✅ User business logic
│   │   ├── access_service.py      # ✅ Access rules logic
│   │   ├── audit_service.py       # ✅ Audit logs logic
│   │   └── sync_service.py        # ✅ Sync logic
│   │
│   ├── routers/                   # API routes
│   │   ├── __init__.py
│   │   ├── users.py               # ✅ /api/v1/users
│   │   ├── access_rules.py        # ✅ /api/v1/access-rules
│   │   ├── time_zones.py          # ✅ /api/v1/time-zones
│   │   ├── audit.py               # ✅ /api/v1/audit
│   │   ├── sync.py                # ✅ /api/v1/sync
│   │   └── system.py              # ✅ /api/v1/system (device info)
│   │
│   └── utils/
│       ├── __init__.py
│       ├── idface_client.py       # ✅ HTTP client for iDFace API
│       └── helpers.py             # ✅ Helper functions
│
├── prisma/
│   └── schema.prisma              # ✅ Database schema
│
├── tests/
│   ├── __init__.py
│   ├── test_connection.py         # ✅ Test iDFace connection
│   ├── test_users.py
│   └── test_access_rules.py
│
├── .env                           # Environment variables (create from .env.example)
├── .env.example                   # ✅ Template
├── dcoker-compose.yml             # ✅ Docker Compose
├── Dockerfile                     # ✅ Dockerfile
├── requirements.txt               # ✅ Dependencies
├── test_idface_connection.py      # ✅ Standalone connection test
└── README.md
```

---

## 🚀 Começando

Você pode rodar este projeto de duas maneiras: localmente com um ambiente Python ou usando Docker.

### 🐳 Rodando com Docker (Recomendado)

Este método provisiona a API e o banco de dados (PostgreSQL) em containers Docker, simplificando a configuração.

1.  **Pré-requisitos:**
    *   [Docker](https://www.docker.com/get-started)
    *   [Docker Compose](https://docs.docker.com/compose/install/)

2.  **Clone o repositório e navegue até a pasta `backend`:**
    ```bash
    git clone <URL_DO_REPOSITORIO>
    cd Control-ID_iDFace_API/backend
    ```

3.  **Configure as variáveis de ambiente:**
    Copie o arquivo de exemplo `.env.example` para um novo arquivo chamado `.env`.
    ```bash
    cp .env.example .env
    ```
    > **Importante:** Abra o arquivo `.env` e preencha as credenciais do iDFace e outras configurações necessárias. A `DATABASE_URL` já vem pré-configurada para o ambiente Docker.

4.  **Construa e inicie os containers:**
    Execute o comando abaixo para construir as imagens e iniciar os serviços em segundo plano.
    ```bash
    docker-compose up -d --build
    ```

5.  **Verifique os logs (opcional):**
    Para acompanhar os logs da aplicação em tempo real, use:
    ```bash
    docker-compose logs -f api
    ```

6.  **Acessando a API:**
    A API estará disponível em `http://localhost:8000`.
    *   **Swagger UI:** `http://localhost:8000/docs`
    *   **ReDoc:** `http://localhost:8000/redoc`

7.  **Visualizando o Banco de Dados:**
    Para abrir o Prisma Studio e interagir com o banco de dados, execute:
    ```bash
    npx prisma studio
    ```
    > O Prisma Studio estará disponível em `http://localhost:5555`.

8.  **Parando os containers:**
    Para parar todos os serviços, execute:
    ```bash
    docker-compose down
    ```

---

### 🛠️ Setup Local (Sem Docker)

Siga estes passos se preferir rodar a aplicação diretamente na sua máquina.

1.  **Criar ambiente virtual:**
    ```bash
    python -m venv venv
    ```

2.  **Ativar ambiente:**
    *   **Windows:** `venv\Scripts\activate`
    *   **Linux/Mac:** `source venv/bin/activate`

3.  **Instalar dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar variáveis de ambiente:**
    ```bash
    cp .env.example .env
    ```
    > Edite o arquivo `.env` com suas credenciais e a URL do seu banco de dados.

5.  **Gerar cliente Prisma:**
    ```bash
    prisma generate
    ```

6.  **Aplicar schema no banco de dados:**
    Este comando cria as tabelas no banco de dados com base no `schema.prisma`.
    ```bash
    prisma db push
    ```

7.  **Iniciar servidor FastAPI:**
    ```bash
    uvicorn app.main:app --reload --port 8000
    ```

---

## 🌐 Endpoints Disponíveis

| Tipo | Endpoint | Descrição |
|------|-----------|------------|
| `GET` | `/docs` | Interface **Swagger UI** |
| `GET` | `/redoc` | Interface **ReDoc** |
| `GET` | `/api/v1/users` | Gerenciamento de usuários |
| `GET` | `/api/v1/access-rules` | Regras de acesso |
| `GET` | `/api/v1/time-zones` | Configurações de fuso horário |
| `GET` | `/api/v1/audit` | Logs de auditoria |
| `GET` | `/api/v1/sync` | Sincronização de dispositivos |
| `GET` | `/api/v1/system` | Informações do sistema/dispositivo |

---

## 🧩 Tecnologias Principais

- **FastAPI** — Framework web moderno e performático
- **Prisma ORM** — Integração de banco de dados
- **Docker & Docker Compose** — Containerização
- **Python 3.10+** — Linguagem base
- **Uvicorn** — Servidor ASGI
- **iDFace API** — Integração para controle de acesso facial

---

## 📄 Licença
Este projeto é de uso interno e está sob os termos definidos pelo autor.