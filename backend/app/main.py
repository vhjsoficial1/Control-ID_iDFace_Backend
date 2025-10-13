from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import connect_db, disconnect_db
from app.routers import users, access_rules, time_zones, audit, sync, system

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="API para controle e gerenciamento do leitor facial iDFace"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Event handlers
@app.on_event("startup")
async def startup():
    await connect_db()

@app.on_event("shutdown")
async def shutdown():
    await disconnect_db()

# Health check
@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "online",
        "service": "iDFace Control System",
        "version": settings.API_VERSION
    }

# Include routers
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(access_rules.router, prefix="/api/v1/access-rules", tags=["Access Rules"])
app.include_router(time_zones.router, prefix="/api/v1/time-zones", tags=["Time Zones"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["Audit"])
app.include_router(sync.router, prefix="/api/v1/sync", tags=["Synchronization"])
app.include_router(system.router, prefix="/api/v1/system", tags=["System"])