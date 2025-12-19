from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ========== Base Schemas ==========

class VisitorBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    registration: str = Field(..., min_length=1, max_length=255, description="Empresa do visitante")
    beginTime: datetime
    endTime: datetime = Field(..., description="Válido até 23:59:59 dessa data")


# ========== Create Schemas ==========

class VisitorCreate(VisitorBase):
    image: Optional[str] = None  # Base64 encoded image


# ========== Update Schemas ==========

class VisitorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    registration: Optional[str] = Field(None, min_length=1, max_length=255)
    beginTime: Optional[datetime] = None
    endTime: Optional[datetime] = None


# ========== Response Schemas ==========

class VisitorResponse(VisitorBase):
    id: int
    idFaceId: Optional[int] = None
    image: Optional[str] = None
    imageTimestamp: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime
    
    class Config:
        from_attributes = True


class VisitorListResponse(BaseModel):
    total: int
    visitors: list[VisitorResponse]


# ========== Image Schemas ==========

class VisitorImageUpload(BaseModel):
    visitorId: int
    image: str = Field(..., description="Base64 encoded image")
    match: bool = Field(True, description="Match face during upload")


# ========== Sync Schemas ==========

class VisitorSyncRequest(BaseModel):
    visitorId: int
    syncImage: bool = True


class VisitorSyncResponse(BaseModel):
    success: bool
    message: str
    idFaceId: Optional[int] = None
