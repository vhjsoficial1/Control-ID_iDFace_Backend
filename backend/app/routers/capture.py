"""
Rotas para captura facial usando o leitor
"""
from fastapi import APIRouter, HTTPException, Depends, status
from app.database import get_db
from app.schemas.capture import CaptureRequest, CaptureResponse
from app.utils.idface_client import idface_client
from app.services.user_service import UserService
from app.services.sync_service import SyncService
import asyncio
import base64
from datetime import datetime

router = APIRouter()


@router.post("/start", response_model=CaptureResponse)
async def start_face_capture(request: CaptureRequest, db = Depends(get_db)):
    """
    Inicia a captura de face para um usuário específico e sincroniza com o banco local.
    Prioriza o cadastro no leitor e garante a sincronização.
    """
    # 1. Verificar se usuário existe no banco local
    user = await db.user.find_unique(where={"id": request.userId})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {request.userId} não encontrado no banco local"
        )
    
    try:
        async with idface_client:
            # 2. Se não tiver idFaceId, sincronizar primeiro com o leitor
            if not user.idFaceId:
                # Criar usuário no leitor
                sync_service = SyncService(db)
                sync_result = await sync_service.sync_user_to_idface(user.id)
                
                if not sync_result.get("success"):
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Erro ao sincronizar com leitor: {sync_result.get('error')}"
                    )
                
                # Recarregar usuário para ter o idFaceId atualizado
                user = await db.user.find_unique(where={"id": request.userId})
            
            # 3. Iniciar captura facial no leitor
            capture_result = await idface_client.start_face_capture(
                user_id=user.idFaceId,
                quality=request.quality
            )
            
            if capture_result.get("status") == "error":
                return CaptureResponse(
                    success=False,
                    message=f"Erro na captura: {capture_result.get('message', 'Erro desconhecido')}"
                )
            
            # 4. Tentar obter a imagem para o banco local
            try:
                user_service = UserService(db)
                image_data = await idface_client.get_user_image(user.idFaceId)
                image_base64 = base64.b64encode(image_data).decode()
                
                # Atualizar imagem no banco local
                await user_service.set_user_image(
                    request.userId,
                    image_base64,
                    validate=False  # Não validar novamente pois já foi validado pelo leitor
                )
            except Exception as e:
                # Se não conseguir obter a imagem, não é erro crítico
                # A face já está cadastrada no leitor
                print(f"Aviso: Não foi possível obter a imagem do leitor: {e}")
                image_base64 = None
            
            return CaptureResponse(
                success=True,
                message="Face cadastrada com sucesso no leitor e sincronizada com o banco local!",
                imageData=image_base64,
                captureTime=datetime.now()
            )
            # Vamos tentar obter a imagem para salvar no banco local
            try:
                image_data = await idface_client.get_user_image(user.idFaceId or user.id)
                image_base64 = base64.b64encode(image_data).decode()
            except Exception as e:
                # Se não conseguir obter a imagem, não é um erro crítico
                # A face já foi registrada no dispositivo
                image_base64 = None
            
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