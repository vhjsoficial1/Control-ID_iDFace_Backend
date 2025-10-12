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
├── requirements.txt               # ✅ Dependencies
├── test_idface_connection.py      # ✅ Standalone connection test
└── README.md
```

---

## ⚙️ Setup do Projeto

### 1️⃣ Criar ambiente virtual
```bash
python -m venv venv
```

### 2️⃣ Ativar ambiente
- **Windows**
  ```bash
  venv\Scripts\activate
  ```
- **Linux/Mac**
  ```bash
  source venv/bin/activate
  ```

### 3️⃣ Instalar dependências
```bash
pip install -r requirements.txt
```

### 4️⃣ Configurar variáveis de ambiente
```bash
cp .env.example .env
```
> Edite o arquivo `.env` com suas credenciais e configurações.

### 5️⃣ Gerar cliente Prisma
```bash
prisma generate
```

### 6️⃣ Criar banco de dados
```bash
prisma db push
```

### 7️⃣ Testar conexão com o dispositivo iDFace
```bash
python test_idface_connection.py
```

### 8️⃣ Iniciar servidor FastAPI
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
- **Python 3.10+** — Linguagem base  
- **Uvicorn** — Servidor ASGI  
- **iDFace API** — Integração para controle de acesso facial  

---

## 📄 Licença
Este projeto é de uso interno e está sob os termos definidos pelo autor.
