from fastapi import APIRouter

from . import access_rules, users, time_zones, system, sync, audit

router = APIRouter()

router.include_router(access_rules.router, prefix="/access_rules", tags=["Access Rules"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(time_zones.router, prefix="/time_zones", tags=["Time Zones"])
router.include_router(system.router, prefix="/system", tags=["System"])
router.include_router(sync.router, prefix="/sync", tags=["Sync"])
router.include_router(audit.router, prefix="/audit", tags=["Audit"])
