from fastapi import APIRouter, HTTPException, Depends, status
from app.database import get_db
from app.utils.idface_client import idface_client
from typing import Optional, List

router = APIRouter()


# ==================== Schemas ====================

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, time

class TimeSpanCreate(BaseModel):
    """Intervalo de tempo dentro de um Time Zone"""
    start: int = Field(..., ge=0, le=86400, description="Segundos desde meia-noite (0-86400)")
    end: int = Field(..., ge=0, le=86400, description="Segundos desde meia-noite (0-86400)")
    
    # Dias da semana
    sun: bool = Field(False, description="Domingo")
    mon: bool = Field(False, description="Segunda-feira")
    tue: bool = Field(False, description="Terça-feira")
    wed: bool = Field(False, description="Quarta-feira")
    thu: bool = Field(False, description="Quinta-feira")
    fri: bool = Field(False, description="Sexta-feira")
    sat: bool = Field(False, description="Sábado")
    
    # Feriados
    hol1: bool = Field(False, description="Feriado tipo 1")
    hol2: bool = Field(False, description="Feriado tipo 2")
    hol3: bool = Field(False, description="Feriado tipo 3")


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


class TimeSpanResponse(BaseModel):
    id: int
    timeZoneId: int
    start: int
    end: int
    sun: bool
    mon: bool
    tue: bool
    wed: bool
    thu: bool
    fri: bool
    sat: bool
    hol1: bool
    hol2: bool
    hol3: bool
    createdAt: datetime
    
    class Config:
        from_attributes = True


class TimeZoneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    timeSpans: Optional[List[TimeSpanCreate]] = None


class TimeZoneUpdate(BaseModel):
    name: Optional[str] = None


class TimeZoneResponse(BaseModel):
    id: int
    name: str
    idFaceId: Optional[int] = None
    timeSpans: Optional[List[TimeSpanResponse]] = None
    createdAt: datetime
    updatedAt: datetime
    
    class Config:
        from_attributes = True


# ==================== Helper Functions ====================

def seconds_to_time(seconds: int) -> str:
    """Converte segundos em formato HH:MM"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours:02d}:{minutes:02d}"


def time_to_seconds(time_str: str) -> int:
    """Converte HH:MM em segundos"""
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours * 3600 + minutes * 60
    except:
        raise ValueError("Formato inválido. Use HH:MM")


# ==================== CRUD Time Zones ====================

@router.post("/", response_model=TimeZoneResponse, status_code=status.HTTP_201_CREATED)
async def create_time_zone(
    time_zone: TimeZoneCreate,
    db = Depends(get_db)
):
    """
    Cria um novo time zone no banco local
    """
    try:
        # Criar time zone
        new_tz = await db.timezone.create(
            data={
                "name": time_zone.name
            }
        )
        
        # Se houver time spans, criar também
        if time_zone.timeSpans:
            for span in time_zone.timeSpans:
                await db.timespan.create(
                    data={
                        "timeZoneId": new_tz.id,
                        "start": span.start,
                        "end": span.end,
                        "sun": span.sun,
                        "mon": span.mon,
                        "tue": span.tue,
                        "wed": span.wed,
                        "thu": span.thu,
                        "fri": span.fri,
                        "sat": span.sat,
                        "hol1": span.hol1,
                        "hol2": span.hol2,
                        "hol3": span.hol3
                    }
                )
        
        # Recarregar com time spans
        result = await db.timezone.find_unique(
            where={"id": new_tz.id},
            include={"timeSpans": True}
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar time zone: {str(e)}"
        )


@router.get("/", response_model=List[TimeZoneResponse])
async def list_time_zones(
    skip: int = 0,
    limit: int = 100,
    include_spans: bool = True,
    db = Depends(get_db)
):
    """
    Lista todos os time zones
    """
    time_zones = await db.timezone.find_many(
        skip=skip,
        take=limit,
        include={"timeSpans": include_spans}
    )
    return time_zones


@router.get("/{tz_id}", response_model=TimeZoneResponse)
async def get_time_zone(tz_id: int, db = Depends(get_db)):
    """
    Busca time zone por ID
    """
    tz = await db.timezone.find_unique(
        where={"id": tz_id},
        include={"timeSpans": True}
    )
    
    if not tz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time zone {tz_id} não encontrado"
        )
    
    return tz


@router.patch("/{tz_id}", response_model=TimeZoneResponse)
async def update_time_zone(
    tz_id: int,
    tz_data: TimeZoneUpdate,
    db = Depends(get_db)
):
    """
    Atualiza time zone
    """
    existing = await db.timezone.find_unique(where={"id": tz_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time zone {tz_id} não encontrado"
        )
    
    update_data = tz_data.model_dump(exclude_unset=True)
    
    updated_tz = await db.timezone.update(
        where={"id": tz_id},
        data=update_data,
        include={"timeSpans": True}
    )
    
    return updated_tz


@router.delete("/{tz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_time_zone(tz_id: int, db = Depends(get_db)):
    """
    Deleta time zone (e seus time spans em cascata)
    """
    existing = await db.timezone.find_unique(where={"id": tz_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time zone {tz_id} não encontrado"
        )
    
    await db.timezone.delete(where={"id": tz_id})


# ==================== CRUD Time Spans ====================

@router.post("/{tz_id}/spans", response_model=TimeSpanResponse, status_code=status.HTTP_201_CREATED)
async def create_time_span(
    tz_id: int,
    span: TimeSpanCreate,
    db = Depends(get_db)
):
    """
    Adiciona um intervalo de tempo a um time zone
    """
    # Verificar se time zone existe
    tz = await db.timezone.find_unique(where={"id": tz_id})
    if not tz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time zone {tz_id} não encontrado"
        )
    
    # Validar intervalo
    if span.start >= span.end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Horário de início deve ser menor que horário de fim"
        )
    
    new_span = await db.timespan.create(
        data={
            "timeZoneId": tz_id,
            "start": span.start,
            "end": span.end,
            "sun": span.sun,
            "mon": span.mon,
            "tue": span.tue,
            "wed": span.wed,
            "thu": span.thu,
            "fri": span.fri,
            "sat": span.sat,
            "hol1": span.hol1,
            "hol2": span.hol2,
            "hol3": span.hol3
        }
    )
    
    return new_span


@router.get("/{tz_id}/spans", response_model=List[TimeSpanResponse])
async def list_time_spans(tz_id: int, db = Depends(get_db)):
    """
    Lista todos os intervalos de um time zone
    """
    spans = await db.timespan.find_many(
        where={"timeZoneId": tz_id},
        order_by={"start": "asc"}
    )
    return spans


@router.get("/spans/{span_id}", response_model=TimeSpanResponse)
async def get_time_span(span_id: int, db = Depends(get_db)):
    """
    Busca um time span por ID
    """
    span = await db.timespan.find_unique(where={"id": span_id})
    
    if not span:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time span {span_id} não encontrado"
        )
    
    return span


@router.patch("/spans/{span_id}", response_model=TimeSpanResponse)
async def update_time_span(
    span_id: int,
    span_data: TimeSpanUpdate,
    db = Depends(get_db)
):
    """
    Atualiza um time span
    """
    existing = await db.timespan.find_unique(where={"id": span_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time span {span_id} não encontrado"
        )
    
    update_data = span_data.model_dump(exclude_unset=True)
    
    # Validar se há start e end
    start = update_data.get("start", existing.start)
    end = update_data.get("end", existing.end)
    
    if start >= end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Horário de início deve ser menor que horário de fim"
        )
    
    updated_span = await db.timespan.update(
        where={"id": span_id},
        data=update_data
    )
    
    return updated_span


@router.delete("/spans/{span_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_time_span(span_id: int, db = Depends(get_db)):
    """
    Remove um time span
    """
    existing = await db.timespan.find_unique(where={"id": span_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time span {span_id} não encontrado"
        )
    
    await db.timespan.delete(where={"id": span_id})


# ==================== Sync with iDFace ====================

@router.post("/{tz_id}/sync-to-idface")
async def sync_time_zone_to_idface(tz_id: int, db = Depends(get_db)):
    """
    Sincroniza time zone e seus spans para o iDFace
    """
    tz = await db.timezone.find_unique(
        where={"id": tz_id},
        include={"timeSpans": True}
    )
    
    if not tz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time zone {tz_id} não encontrado"
        )
    
    try:
        async with idface_client:
            # Criar time zone no iDFace
            result_tz = await idface_client.create_time_zone({
                "name": tz.name
            })
            
            # Sincronizar time spans
            if tz.timeSpans:
                for span in tz.timeSpans:
                    await idface_client.create_time_span({
                        "time_zone_id": tz.idFaceId,  # Usar ID do iDFace
                        "start": span.start,
                        "end": span.end,
                        "sun": 1 if span.sun else 0,
                        "mon": 1 if span.mon else 0,
                        "tue": 1 if span.tue else 0,
                        "wed": 1 if span.wed else 0,
                        "thu": 1 if span.thu else 0,
                        "fri": 1 if span.fri else 0,
                        "sat": 1 if span.sat else 0,
                        "hol1": 1 if span.hol1 else 0,
                        "hol2": 1 if span.hol2 else 0,
                        "hol3": 1 if span.hol3 else 0
                    })
            
            return {
                "success": True,
                "message": "Time zone sincronizado com sucesso",
                "timeSpansCount": len(tz.timeSpans) if tz.timeSpans else 0
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar: {str(e)}"
        )


# ==================== Link Time Zone to Access Rule ====================

@router.post("/{tz_id}/access-rules/{rule_id}")
async def link_time_zone_to_access_rule(
    tz_id: int,
    rule_id: int,
    db = Depends(get_db)
):
    """
    Vincula time zone a uma regra de acesso
    """
    # Verificar se time zone existe
    tz = await db.timezone.find_unique(where={"id": tz_id})
    if not tz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time zone {tz_id} não encontrado"
        )
    
    # Verificar se regra existe
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    # Criar vínculo
    try:
        link = await db.accessruletimezone.create(
            data={
                "timeZoneId": tz_id,
                "accessRuleId": rule_id
            }
        )
        
        return {
            "success": True,
            "message": "Time zone vinculado à regra com sucesso"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao vincular: {str(e)}"
        )


@router.delete("/{tz_id}/access-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_time_zone_from_access_rule(
    tz_id: int,
    rule_id: int,
    db = Depends(get_db)
):
    """
    Remove vínculo entre time zone e regra de acesso
    """
    link = await db.accessruletimezone.find_first(
        where={
            "timeZoneId": tz_id,
            "accessRuleId": rule_id
        }
    )
    
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vínculo não encontrado"
        )
    
    await db.accessruletimezone.delete(where={"id": link.id})


# ==================== Utilities ====================

@router.get("/utils/seconds-to-time/{seconds}")
async def convert_seconds_to_time(seconds: int):
    """
    Utilitário: Converte segundos em formato HH:MM
    """
    if seconds < 0 or seconds > 86400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Segundos deve estar entre 0 e 86400"
        )
    
    return {
        "seconds": seconds,
        "time": seconds_to_time(seconds)
    }


@router.get("/utils/time-to-seconds")
async def convert_time_to_seconds(time: str):
    """
    Utilitário: Converte HH:MM em segundos
    Exemplo: /utils/time-to-seconds?time=08:30
    """
    try:
        seconds = time_to_seconds(time)
        return {
            "time": time,
            "seconds": seconds
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ==================== Templates / Presets ====================

@router.get("/presets/work-hours")
async def get_work_hours_preset():
    """
    Retorna preset para horário comercial (08:00-18:00, Seg-Sex)
    """
    return {
        "name": "Horário Comercial",
        "timeSpans": [
            {
                "start": time_to_seconds("08:00"),
                "end": time_to_seconds("18:00"),
                "sun": False,
                "mon": True,
                "tue": True,
                "wed": True,
                "thu": True,
                "fri": True,
                "sat": False,
                "hol1": False,
                "hol2": False,
                "hol3": False
            }
        ]
    }


@router.get("/presets/24-7")
async def get_24_7_preset():
    """
    Retorna preset para acesso 24/7
    """
    return {
        "name": "Acesso 24/7",
        "timeSpans": [
            {
                "start": 0,
                "end": 86400,
                "sun": True,
                "mon": True,
                "tue": True,
                "wed": True,
                "thu": True,
                "fri": True,
                "sat": True,
                "hol1": True,
                "hol2": True,
                "hol3": True
            }
        ]
    }