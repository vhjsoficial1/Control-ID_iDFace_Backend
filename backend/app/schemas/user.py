from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ========== Base Schemas ==========

class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    registration: Optional[str] = Field(None, max_length=100)
    beginTime: Optional[datetime] = None
    endTime: Optional[datetime] = None


# ========== Create Schemas ==========

class UserCreate(UserBase):
    password: Optional[str] = None
    image: Optional[str] = None  # Base64 encoded image


class CardCreate(BaseModel):
    value: int = Field(..., description="Card number")
    userId: int


class QRCodeCreate(BaseModel):
    value: str = Field(..., min_length=1)
    userId: int


# ========== Update Schemas ==========

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    registration: Optional[str] = None
    beginTime: Optional[datetime] = None
    endTime: Optional[datetime] = None
    password: Optional[str] = None


# ========== Response Schemas ==========

class CardResponse(BaseModel):
    id: int
    value: int
    userId: int
    createdAt: datetime
    
    class Config:
        from_attributes = True


class QRCodeResponse(BaseModel):
    id: int
    value: str
    userId: int
    createdAt: datetime
    
    class Config:
        from_attributes = True


class UserResponse(UserBase):
    id: int
    idFaceId: Optional[int] = None
    imageTimestamp: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime
    
    # Optional relationships
    cards: Optional[list[CardResponse]] = None
    qrcodes: Optional[list[QRCodeResponse]] = None
    
    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    total: int
    users: list[UserResponse]


# ========== Image Schemas ==========

class UserImageUpload(BaseModel):
    userId: int
    image: str = Field(..., description="Base64 encoded image")
    match: bool = Field(True, description="Match face during upload")


class BulkImageUpload(BaseModel):
    userImages: list[dict] = Field(..., description="List of {user_id, timestamp, image}")
    match: bool = True


# ========== Sync Schemas ==========

class UserSyncRequest(BaseModel):
    userId: int
    syncImage: bool = True
    syncCards: bool = True
    syncAccessRules: bool = True


class UserSyncResponse(BaseModel):
    success: bool
    message: str
    idFaceId: Optional[int] = None