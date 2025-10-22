"""
Rotas para captura facial usando o leitor
"""
from fastapi import APIRouter, HTTPException, Depends, status
from app.database import get_db
from app.schemas.capture import CaptureRequest, CaptureResponse
from app.utils.idface_client import idface_client
from app.services.user_service import UserService
import asyncio
import base64
from datetime import datetime

router = APIRouter()


@router.post("/start", response_model=CaptureResponse)
async def start_face_capture(request: CaptureRequest, db = Depends(get_db)):
    """
    Inicia a captura de face para um usuário específico.
    O leitor iniciará o processo de captura facial.
    """
    # 1. Verificar se usuário existe
    user_service = UserService(db)
    user = await db.user.find_unique(where={"id": request.userId})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {request.userId} não encontrado"
        )
    
    try:
        async with idface_client:
            # 2. Iniciar captura
            await idface_client.start_face_capture(quality=request.quality)
            
            # 3. Aguardar captura (com timeout)
            start_time = datetime.now()
            timeout = request.timeout or 30
            captured = False
            
            while (datetime.now() - start_time).seconds < timeout:
                status_resp = await idface_client.get_capture_status()
                
                if status_resp.get("status") == "captured":
                    captured = True
                    break
                
                await asyncio.sleep(1)  # Esperar 1 segundo antes de verificar novamente
            
            if not captured:
                return CaptureResponse(
                    success=False,
                    message="Tempo limite excedido. Nenhuma face detectada."
                )
            
            # 4. Obter imagem capturada
            image_data = await idface_client.get_captured_face()
            image_base64 = base64.b64encode(image_data).decode()
            
            # 5. Salvar imagem no usuário e sincronizar com iDFace
            update_result = await user_service.set_user_image(
                request.userId,
                image_base64,
                validate=True
            )
            
            if not update_result.get("success"):
                return CaptureResponse(
                    success=False,
                    message=f"Erro ao salvar imagem: {update_result.get('error')}"
                )
            
            return CaptureResponse(
                success=True,
                message="Face capturada com sucesso!",
                imageData=image_base64,
                captureTime=datetime.now()
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro durante captura: {str(e)}"
        )