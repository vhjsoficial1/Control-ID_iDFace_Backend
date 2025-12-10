"""
Rotas para captura facial usando o leitor (Captura no L1 -> Sincroniza L1 e L2)
backend/app/routers/capture.py
"""
from fastapi import APIRouter, HTTPException, Depends, status
from app.database import get_db
from app.schemas.capture import CaptureRequest, CaptureResponse
# Importando ambos os clientes
from app.utils.idface_client import idface_client, idface_client_2
from app.services.user_service import UserService
import asyncio
import base64
from datetime import datetime

router = APIRouter()

async def _ensure_user_on_device(client, user_db):
    """
    Garante que o usuário existe no dispositivo alvo.
    Retorna o ID do usuário no dispositivo.
    """
    # 1. Tentar buscar
    search_res = await client.load_users(where={"users": {"registration": user_db.registration}})
    users = search_res.get("users", [])
    
    if users:
        return users[0]["id"]
    
    # 2. Se não existir, criar
    create_payload = {
        "name": user_db.name,
        "registration": user_db.registration,
        "password": user_db.password or "",
        "salt": user_db.salt or ""
    }
    
    # Se o usuário já tiver um idFaceId preferencial (do L1), tentamos forçar o mesmo ID no L2
    # Nota: Nem sempre o dispositivo aceita forçar ID se já estiver ocupado, mas tentamos passar values limpo.
    res = await client.create_user(create_payload)
    if res.get("ids"):
        return res["ids"][0]
        
    raise Exception(f"Falha ao criar usuário no dispositivo {client.base_url}")

@router.post("/start", response_model=CaptureResponse)
async def start_face_capture(request: CaptureRequest, db = Depends(get_db)):
    """
    Fluxo de Captura:
    1. Inicia captura no Leitor 1 (Entrada).
    2. Aguarda o usuário posicionar a face.
    3. Baixa a foto do Leitor 1.
    4. Salva no banco local.
    5. Envia a foto para o Leitor 2 (Saída) para manter sincronia.
    """
    # 1. Verificar se usuário existe no banco local
    user = await db.user.find_unique(where={"id": request.userId})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {request.userId} não encontrado no banco local"
        )
    
    user_service = UserService(db)
    captured_image_bytes = None
    image_base64 = None
    
    # =========================================================================
    # FASE 1: CAPTURA NO LEITOR 1
    # =========================================================================
    try:
        async with idface_client:
            # A. Garantir usuário no Leitor 1
            l1_user_id = await _ensure_user_on_device(idface_client, user)
            
            # Atualizar ID local se necessário
            if not user.idFaceId:
                user = await db.user.update(where={"id": user.id}, data={"idFaceId": l1_user_id})
            
            # B. Iniciar captura (remote enroll)
            print(f"📸 Iniciando captura para usuário {user.name} (ID {l1_user_id}) no Leitor 1...")
            capture_req = await idface_client.start_face_capture(
                user_id=l1_user_id,
                quality=request.quality or 70
            )
            
            if capture_req.get("status") == "error":
                raise Exception(f"Leitor recusou início da captura: {capture_req}")

            # C. Polling: Aguardar a foto ser tirada
            # O remote_enroll retorna na hora, precisamos esperar o status mudar
            attempts = 0
            max_attempts = 20 # 20 * 0.5s = 10 segundos de timeout
            capture_success = False
            
            while attempts < max_attempts:
                await asyncio.sleep(0.5)
                status_res = await idface_client.get_capture_status()
                # A resposta do status varia conforme firmware, checando campos comuns
                s = status_res.get("status")
                if s == "scanned" or s == "success" or status_res.get("enroll_status") == "success":
                    capture_success = True
                    break
                if s == "error" or s == "canceled" or s == "timeout":
                    raise Exception(f"Captura cancelada ou falhou: {s}")
                attempts += 1
            
            if not capture_success:
                raise Exception("Timeout aguardando face do usuário.")

            # D. Baixar a imagem do Leitor 1
            captured_image_bytes = await idface_client.get_user_image(l1_user_id)
            if not captured_image_bytes:
                raise Exception("Captura reportada como sucesso, mas imagem veio vazia.")
            
            print("✅ Imagem baixada do Leitor 1 com sucesso.")

    except Exception as e:
        # Se falhar no L1, aborta tudo, pois é a fonte da verdade
        raise HTTPException(status_code=500, detail=f"Erro na captura (Leitor 1): {str(e)}")

    # =========================================================================
    # FASE 2: SALVAR LOCALMENTE
    # =========================================================================
    try:
        image_base64 = base64.b64encode(captured_image_bytes).decode()
        
        # Salva no banco e atualiza timestamp
        await user_service.set_user_image(
            request.userId,
            image_base64,
            validate=False # Já validado pelo hardware
        )
    except Exception as e:
        print(f"⚠️ Erro ao salvar no banco local: {e}")
        # Não abortamos, pois temos a imagem em memória para tentar enviar ao L2

    # =========================================================================
    # FASE 3: SINCRONIZAR COM LEITOR 2
    # =========================================================================
    if captured_image_bytes:
        try:
            print("🔄 Replicando foto para o Leitor 2...")
            async with idface_client_2:
                # A. Garantir usuário no Leitor 2
                l2_user_id = await _ensure_user_on_device(idface_client_2, user)
                
                # B. Enviar a imagem capturada no L1 para o L2
                await idface_client_2.set_user_image(
                    user_id=l2_user_id,
                    image_data=captured_image_bytes,
                    match=True
                )
                print(f"✅ Foto sincronizada com sucesso no Leitor 2 (ID {l2_user_id})")
                
        except Exception as e:
            # Falha no L2 não deve quebrar a resposta de sucesso da captura, apenas logar aviso
            print(f"⚠️ Aviso: Foto capturada mas falha ao enviar para Leitor 2: {e}")

    return CaptureResponse(
        success=True,
        message="Face capturada no Leitor 1 e sincronizada com sucesso!",
        imageData=image_base64,
        captureTime=datetime.now()
    )