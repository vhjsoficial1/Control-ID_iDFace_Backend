from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ==================== Time Span Schemas ====================

class TimeSpanBase(BaseModel):
    start: int = Field(..., ge=0, le=86400, description="Segundos desde meia-noite")
    end: int = Field(..., ge=0, le=86400, description="Segundos desde meia-noite")
    sun: bool = False
    mon: bool = False
    tue: bool = False
    wed: bool = False
    thu: bool = False
    fri: bool = False
    sat: bool = False
    hol1: bool = False
    hol2: bool = False
    hol3: bool = False


class TimeSpanCreate(TimeSpanBase):
    pass


class TimeSpanUpdate(BaseModel):
    start: Optional[int] = Field(None, ge=0, le=86400)
    end: Optional[int] = Field(None, ge=0, le=86400)
    sun: Optional[bool] = None
    mon: Optional[bool] = None
    tue: Optional[bool] = None
    wed: Optional[bool] = None
    thu: Optional[bool] = None
    fri: Optional[bool] = None
    sat: Optional[bool] = None
    hol1: Optional[bool] = None
    hol2: Optional[bool] = None
    hol3: Optional[bool] = None


class TimeSpanResponse(TimeSpanBase):
    id: int
    timeZoneId: int
    createdAt: datetime
    
    class Config:
        from_attributes = True


# ==================== Time Zone Schemas ====================

class TimeZoneBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class TimeZoneCreate(TimeZoneBase):
    timeSpans: Optional[List[TimeSpanCreate]] = None


class TimeZoneUpdate(BaseModel):
    name: Optional[str] = None


class TimeZoneResponse(TimeZoneBase):
    id: int
    idFaceId: Optional[int] = None
    timeSpans: Optional[List[TimeSpanResponse]] = None
    createdAt: datetime
    updatedAt: datetime
    
    class Config:
        from_attributes = True


class TimeZoneListResponse(BaseModel):
    total: int
    timeZones: List[TimeZoneResponse]