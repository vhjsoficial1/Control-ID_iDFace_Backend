"""
Schemas para captura facial
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CaptureResponse(BaseModel):
    """Resposta da captura facial"""
    success: bool
    message: str
    imageData: Optional[str] = None  # Base64 da imagem quando capturada
    captureTime: Optional[datetime] = None


class CaptureRequest(BaseModel):
    """Requisição de captura facial"""
    userId: int
    timeout: Optional[int] = 30  # Timeout em segundos
    quality: Optional[int] = 70  # Qualidade mínima da imagem (0-100)