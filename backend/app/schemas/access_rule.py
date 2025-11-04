from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AccessRuleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: int = Field(1, ge=0, le=10)
    priority: int = Field(0, ge=0)


class AccessRuleCreate(AccessRuleBase):
    pass


class AccessRuleUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[int] = None
    priority: Optional[int] = None


class AccessRuleResponse(AccessRuleBase):
    id: int
    idFaceId: Optional[int] = None
    createdAt: datetime
    updatedAt: datetime
    
    class Config:
        from_attributes = True


class AccessRuleListResponse(BaseModel):
    total: int
    rules: list[AccessRuleResponse]


class AccessRuleSyncRequest(BaseModel):
    ruleId: int
    syncTimeZones: bool = True


class AccessRuleSyncResponse(BaseModel):
    success: bool
    message: str
    idFaceId: Optional[int] = None