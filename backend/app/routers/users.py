from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas.user import (
    UserCreate, UserUpdate, UserResponse, UserListResponse,
    CardCreate, CardResponse, QRCodeCreate, QRCodeResponse,
    UserImageUpload, BulkImageUpload, UserSyncRequest, UserSyncResponse
)
from app.database import get_db
from app.utils.idface_client import idface_client
from typing import Optional
import base64

router = APIRouter()


# ==================== CRUD Operations ====================

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db = Depends(get_db)):
    """
    Cria um novo usuário no banco de dados local
    """
    try:
        new_user = await db.user.create(
            data={
                "name": user.name,
                "registration": user.registration,
                "beginTime": user.beginTime,
                "endTime": user.endTime,
                "password": user.password  # TODO: Hash password
            }
        )
        return new_user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar usuário: {str(e)}"
        )


@router.get("/", response_model=UserListResponse)
async def list_users(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    db = Depends(get_db)
):
    """
    Lista todos os usuários
    """
    where = {}
    if search:
        where = {
            "OR": [
                {"name": {"contains": search, "mode": "insensitive"}},
                {"registration": {"contains": search, "mode": "insensitive"}}
            ]
        }
    
    users = await db.user.find_many(
        where=where,
        skip=skip,
        take=limit,
        include={
            "cards": True,
            "qrcodes": True
        }
    )
    
    total = await db.user.count(where=where)
    
    return UserListResponse(total=total, users=users)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db = Depends(get_db)):
    """
    Busca um usuário por ID
    """
    user = await db.user.find_unique(
        where={"id": user_id},
        include={
            "cards": True,
            "qrcodes": True
        }
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    return user


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
    
    return updated_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db = Depends(get_db)):
    """
    Deleta um usuário
    """
    existing = await db.user.find_unique(where={"id": user_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    await db.user.delete(where={"id": user_id})


# ==================== Cards ====================

@router.post("/{user_id}/cards", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
async def add_card(user_id: int, card: CardCreate, db = Depends(get_db)):
    """
    Adiciona um cartão ao usuário
    """
    # Verificar se usuário existe
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    # Criar cartão
    new_card = await db.card.create(
        data={
            "value": card.value,
            "userId": user_id
        }
    )
    
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
    Remove um cartão
    """
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
    Faz upload da imagem facial do usuário
    """
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    # Salvar imagem no banco de dados
    from datetime import datetime
    await db.user.update(
        where={"id": user_id},
        data={
            "image": image_data.image,
            "imageTimestamp": datetime.now()
        }
    )
    
    return {"message": "Imagem salva com sucesso"}


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
    Remove a imagem do usuário
    """
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
    Sincroniza usuário do banco local para o iDFace
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
    
    try:
        async with idface_client:
            # Criar usuário no iDFace
            user_data = {
                "name": user.name,
                "registration": user.registration or "",
                "password": user.password or "",
                "salt": user.salt or ""
            }
            
            result = await idface_client.create_user(user_data)
            
            # TODO: Extrair ID do iDFace e salvar
            # idface_id = result.get("id")
            
            # Sync image if requested
            if sync_req.syncImage and user.image:
                # Converter base64 para bytes
                image_bytes = base64.b64decode(user.image)
                # await idface_client.set_user_image(idface_id, image_bytes)
            
            return UserSyncResponse(
                success=True,
                message="Usuário sincronizado com sucesso",
                idFaceId=None  # TODO: Pegar do result
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar: {str(e)}"
        )