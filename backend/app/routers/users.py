from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas.user import (
    UserCreate, UserUpdate, UserResponse, UserListResponse,
    CardCreate, CardResponse, QRCodeCreate, QRCodeResponse,
    UserImageUpload, BulkImageUpload, UserSyncRequest, UserSyncResponse
)
from app.database import get_db
from app.services.user_service import UserService
from app.services.sync_service import SyncService
from app.utils.idface_client import idface_client, idface_client_2
from typing import Optional
import base64
import asyncio
from datetime import datetime

router = APIRouter()


# ==================== CRUD Operations ====================

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db = Depends(get_db)):
    """
    Cria um novo usuário seguindo o fluxo:
    1. Cadastra no banco local
    2. Sincroniza com AMBOS os leitores
    3. Busca o ID correto nos leitores
    4. Atualiza o banco local com o ID do leitor
    5. Envia a imagem se fornecida
    """
    user_service = UserService(db)
    
    # Guardar imagem temporariamente
    temp_image = user.image
    
    registration_value = user.registration.strip() if user.registration else ""
    
    if not registration_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Matrícula é obrigatória"
        )
    
    # 1. Criar usuário localmente primeiro (SEM imagem inicialmente)
    create_result = await user_service.create_user(
        name=user.name,
        registration=registration_value,
        password=user.password,
        begin_time=user.beginTime,
        end_time=user.endTime,
        image=None
    )

    if not create_result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar usuário: {create_result.get('errors', ['Erro desconhecido.'])}"
        )

    new_user = create_result["user"]
    
    # Preparar dados para envio aos leitores
    idface_data = {
        "name": new_user.name,
        "registration": new_user.registration,
        "password": new_user.password or "",
        "salt": new_user.salt or ""
    }
    
    # 2. Sincronizar com os leitores
    image_sent_successfully = False
    try:
        # ===== LEITOR 1 =====
        idface_id = None
        async with idface_client:
            # Criar usuário no leitor 1
            await idface_client.create_user(idface_data)
            await asyncio.sleep(0.5)
            
            # Buscar usuário no leitor 1
            search_result = await idface_client.load_users(
                where={"users": {
                    "name": new_user.name,
                    "registration": new_user.registration
                }}
            )
            
            idface_users = search_result.get("users", [])
            if not idface_users:
                raise ValueError("Usuário não encontrado no LEITOR 1 após criação")
            
            idface_id = idface_users[0]["id"]
            
            # Enviar imagem para leitor 1
            if temp_image:
                try:
                    image_bytes = base64.b64decode(temp_image)
                    response = await idface_client.set_user_image(
                        idface_id,
                        image_bytes,
                        match=True
                    )
                    if "error" in response:
                        raise ValueError(f"iDFace L1 error: {response['error']}")
                    
                    print(f"✅ Imagem enviada para LEITOR 1 (iDFace ID: {idface_id})")
                    image_sent_successfully = True
                except Exception as img_error:
                    print(f"⚠️ Erro ao enviar imagem para LEITOR 1: {img_error}")
        
        # ===== LEITOR 2 (MESMA LÓGICA) =====
        idface_id_2 = None
        async with idface_client_2:
            # Criar usuário no leitor 2
            await idface_client_2.create_user(idface_data)
            await asyncio.sleep(0.5)
            
            # Buscar usuário no leitor 2
            search_result_2 = await idface_client_2.load_users(
                where={"users": {
                    "name": new_user.name,
                    "registration": new_user.registration
                }}
            )
            
            idface_users_2 = search_result_2.get("users", [])
            if not idface_users_2:
                raise ValueError("Usuário não encontrado no LEITOR 2 após criação")
            
            idface_id_2 = idface_users_2[0]["id"]
            
            # Enviar imagem para leitor 2
            if temp_image:
                try:
                    image_bytes = base64.b64decode(temp_image)
                    response = await idface_client_2.set_user_image(
                        idface_id_2,
                        image_bytes,
                        match=True
                    )
                    if "error" in response:
                        raise ValueError(f"iDFace L2 error: {response['error']}")
                        
                    print(f"✅ Imagem enviada para LEITOR 2 (iDFace ID: {idface_id_2})")
                    image_sent_successfully = True
                except Exception as img_error:
                    print(f"⚠️ Erro ao enviar imagem para LEITOR 2: {img_error}")
        
        # 3. Atualizar banco local com o ID e a imagem (se tiver sido enviada com sucesso)
        final_idface_id = idface_id or idface_id_2
        image_to_save = temp_image if image_sent_successfully else None

        new_user = await db.user.update(
            where={"id": new_user.id},
            data={
                "idFaceId": final_idface_id,
                "image": image_to_save,
                "imageTimestamp": datetime.now() if image_to_save else None
            }
        )
        
        print(f"✅ Usuário {new_user.id} sincronizado nos 2 leitores (ID {final_idface_id})")
        
        return new_user
        
    except Exception as e:
        # Se algo der errado, deletar o usuário local
        await db.user.delete(where={"id": new_user.id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar com os leitores: {str(e)}"
        )


@router.get("/", response_model=UserListResponse)
async def list_users(
    skip: int = 0,
    limit: int = 2000,
    search: Optional[str] = None,
    db = Depends(get_db)
):
    """
    Lista todos os usuários
    """
    user_service = UserService(db)
    result = await user_service.search_users(
        query=search,
        skip=skip,
        limit=limit
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao buscar usuários: {result.get('errors')}"
        )
        
    return UserListResponse(
        total=result["total"],
        users=result["users"]
    )


@router.get("/{user_id}")
async def get_user(user_id: int, db = Depends(get_db)):
    """
    Busca um usuário por ID
    """
    user_service = UserService(db)
    result = await user_service.get_user_full_details(user_id)
    
    if not result["success"]:
        error_detail = result.get("errors", ["Erro desconhecido"])[0]
        status_code = status.HTTP_404_NOT_FOUND if "não encontrado" in error_detail else status.HTTP_500_INTERNAL_SERVER_ERROR
        
        raise HTTPException(
            status_code=status_code,
            detail=error_detail
        )
    
    return result


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_data: UserUpdate, db = Depends(get_db)):
    """
    Atualiza um usuário
    """
    existing = await db.user.find_unique(where={"id": user_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    update_data = user_data.model_dump(exclude_unset=True)
    
    updated_user = await db.user.update(
        where={"id": user_id},
        data=update_data
    )
    
    try:
        sync_service = SyncService(db)
        
        # Sincronizar com leitor 1
        await sync_service.sync_user_to_idface(user_id)
        
        # ⚠️ NOTA: Você precisará adaptar sync_service.py também para usar os 2 leitores
        # Por ora, apenas o leitor 1 será atualizado
        
    except Exception as e:
        print(f"AVISO: Usuário {user_id} atualizado localmente, mas falha ao sincronizar: {str(e)}")

    return updated_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db = Depends(get_db)):
    """
    Deleta um usuário de AMBOS os leitores
    """
    existing = await db.user.find_unique(where={"id": user_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    if existing.idFaceId:
        # Deletar do LEITOR 1
        try:
            async with idface_client:
                await idface_client.delete_user(existing.idFaceId)
                print(f"✅ Usuário deletado do LEITOR 1")
        except Exception as e:
            print(f"⚠️ Erro ao deletar do LEITOR 1: {str(e)}")
        
        # Deletar do LEITOR 2
        try:
            async with idface_client_2:
                await idface_client_2.delete_user(existing.idFaceId)
                print(f"✅ Usuário deletado do LEITOR 2")
        except Exception as e:
            print(f"⚠️ Erro ao deletar do LEITOR 2: {str(e)}")

    # Deletar do banco local
    await db.user.delete(where={"id": user_id})


# ==================== Cards ====================

@router.post("/{user_id}/cards", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
async def add_card(user_id: int, card: CardCreate, db = Depends(get_db)):
    """
    Adiciona um cartão ao usuário em AMBOS os leitores
    """
    # Verificar se usuário existe
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    # Criar cartão no banco local
    new_card = await db.card.create(
        data={
            "value": card.value,
            "userId": user_id
        }
    )
    
    if user.idFaceId:
        # Criar no LEITOR 1
        try:
            async with idface_client:
                await idface_client.create_card(int(card.value), user.idFaceId)
                print(f"✅ Cartão criado no LEITOR 1")
        except Exception as e:
            print(f"⚠️ Erro ao criar cartão no LEITOR 1: {str(e)}")
        
        # Criar no LEITOR 2
        try:
            async with idface_client_2:
                await idface_client_2.create_card(int(card.value), user.idFaceId)
                print(f"✅ Cartão criado no LEITOR 2")
        except Exception as e:
            print(f"⚠️ Erro ao criar cartão no LEITOR 2: {str(e)}")
    
    return new_card


@router.get("/{user_id}/cards", response_model=list[CardResponse])
async def list_user_cards(user_id: int, db = Depends(get_db)):
    """
    Lista todos os cartões de um usuário
    """
    cards = await db.card.find_many(where={"userId": user_id})
    return cards


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(card_id: int, db = Depends(get_db)):
    """
    Remove um cartão de AMBOS os leitores
    """
    card = await db.card.find_unique(
        where={"id": card_id},
        include={"user": True}
    )
    
    if not card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cartão {card_id} não encontrado"
        )
    
    if card.user and card.user.idFaceId:
        # Deletar do LEITOR 1
        try:
            async with idface_client:
                # Buscar cartão no leitor e deletar
                result = await idface_client.request(
                    "POST", "destroy_objects.fcgi",
                    json={
                        "object": "cards",
                        "where": {
                            "cards": {
                                "value": int(card.value),
                                "user_id": card.user.idFaceId
                            }
                        }
                    }
                )
                print(f"✅ Cartão deletado do LEITOR 1")
        except Exception as e:
            print(f"⚠️ Erro ao deletar cartão do LEITOR 1: {str(e)}")
        
        # Deletar do LEITOR 2
        try:
            async with idface_client_2:
                result = await idface_client_2.request(
                    "POST", "destroy_objects.fcgi",
                    json={
                        "object": "cards",
                        "where": {
                            "cards": {
                                "value": int(card.value),
                                "user_id": card.user.idFaceId
                            }
                        }
                    }
                )
                print(f"✅ Cartão deletado do LEITOR 2")
        except Exception as e:
            print(f"⚠️ Erro ao deletar cartão do LEITOR 2: {str(e)}")
    
    # Deletar do banco local
    await db.card.delete(where={"id": card_id})


# ==================== QR Codes ====================

@router.post("/{user_id}/qrcodes", response_model=QRCodeResponse, status_code=status.HTTP_201_CREATED)
async def add_qrcode(user_id: int, qrcode: QRCodeCreate, db = Depends(get_db)):
    """
    Adiciona um QR Code ao usuário
    """
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    new_qrcode = await db.qrcode.create(
        data={
            "value": qrcode.value,
            "userId": user_id
        }
    )
    
    return new_qrcode


@router.get("/{user_id}/qrcodes", response_model=list[QRCodeResponse])
async def list_user_qrcodes(user_id: int, db = Depends(get_db)):
    """
    Lista todos os QR Codes de um usuário
    """
    qrcodes = await db.qrcode.find_many(where={"userId": user_id})
    return qrcodes


@router.delete("/qrcodes/{qrcode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_qrcode(qrcode_id: int, db = Depends(get_db)):
    """
    Remove um QR Code
    """
    await db.qrcode.delete(where={"id": qrcode_id})


# ==================== Image Management ====================

@router.post("/{user_id}/image", status_code=status.HTTP_201_CREATED)
async def upload_user_image(user_id: int, image_data: UserImageUpload, db = Depends(get_db)):
    """
    Faz upload da imagem facial do usuário para AMBOS os leitores
    """
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    # Salvar imagem no banco de dados
    await db.user.update(
        where={"id": user_id},
        data={
            "image": image_data.image,
            "imageTimestamp": datetime.now()
        }
    )
    
    if user.idFaceId:
        image_bytes = base64.b64decode(image_data.image)
        
        # Enviar para LEITOR 1
        try:
            async with idface_client:
                await idface_client.set_user_image(
                    user.idFaceId,
                    image_bytes,
                    match=True
                )
                print(f"✅ Imagem enviada para LEITOR 1")
        except Exception as e:
            print(f"⚠️ Erro ao enviar imagem para LEITOR 1: {str(e)}")
        
        # Enviar para LEITOR 2
        try:
            async with idface_client_2:
                await idface_client_2.set_user_image(
                    user.idFaceId,
                    image_bytes,
                    match=True
                )
                print(f"✅ Imagem enviada para LEITOR 2")
        except Exception as e:
            print(f"⚠️ Erro ao enviar imagem para LEITOR 2: {str(e)}")
    
    return {"message": "Imagem salva e enviada para ambos os leitores com sucesso"}


@router.get("/{user_id}/image")
async def get_user_image(user_id: int, db = Depends(get_db)):
    """
    Retorna a imagem do usuário
    """
    user = await db.user.find_unique(where={"id": user_id})
    if not user or not user.image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Imagem não encontrada para usuário {user_id}"
        )
    
    return {
        "userId": user_id,
        "image": user.image,
        "timestamp": user.imageTimestamp
    }


@router.delete("/{user_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_image(user_id: int, db = Depends(get_db)):
    """
    Remove a imagem do usuário de AMBOS os leitores
    """
    user = await db.user.find_unique(where={"id": user_id})
    
    if user and user.idFaceId:
        # Deletar do LEITOR 1
        try:
            async with idface_client:
                await idface_client.delete_user_images([user.idFaceId])
                print(f"✅ Imagem deletada do LEITOR 1")
        except Exception as e:
            print(f"⚠️ Erro ao deletar imagem do LEITOR 1: {str(e)}")
        
        # Deletar do LEITOR 2
        try:
            async with idface_client_2:
                await idface_client_2.delete_user_images([user.idFaceId])
                print(f"✅ Imagem deletada do LEITOR 2")
        except Exception as e:
            print(f"⚠️ Erro ao deletar imagem do LEITOR 2: {str(e)}")
    
    # Deletar do banco local
    await db.user.update(
        where={"id": user_id},
        data={
            "image": None,
            "imageTimestamp": None
        }
    )


# ==================== Sync with iDFace ====================

@router.post("/{user_id}/sync-to-idface", response_model=UserSyncResponse)
async def sync_user_to_idface(user_id: int, sync_req: UserSyncRequest, db = Depends(get_db)):
    """
    Sincroniza usuário do banco local para AMBOS os leitores iDFace
    """
    user = await db.user.find_unique(
        where={"id": user_id},
        include={"cards": True}
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    user_data = {
        "name": user.name,
        "registration": user.registration or "",
        "password": user.password or "",
        "salt": user.salt or ""
    }
    
    try:
        # ===== LEITOR 1 =====
        async with idface_client:
            result = await idface_client.create_user(user_data)
            
            if sync_req.syncImage and user.image:
                image_bytes = base64.b64decode(user.image)
                await idface_client.set_user_image(user.idFaceId, image_bytes)
        
        # ===== LEITOR 2 =====
        async with idface_client_2:
            result = await idface_client_2.create_user(user_data)
            
            if sync_req.syncImage and user.image:
                image_bytes = base64.b64decode(user.image)
                await idface_client_2.set_user_image(user.idFaceId, image_bytes)
        
        return UserSyncResponse(
            success=True,
            message="Usuário sincronizado com ambos os leitores",
            idFaceId=user.idFaceId
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar: {str(e)}"
        )