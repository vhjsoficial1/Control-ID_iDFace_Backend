from fastapi import APIRouter, HTTPException, Depends, status
from app.schemas.visitor import (
    VisitorCreate, VisitorUpdate, VisitorResponse, VisitorListResponse,
    VisitorImageUpload, VisitorSyncRequest, VisitorSyncResponse
)
from app.database import get_db
from app.services.visitor_service import VisitorService
from app.utils.idface_client import idface_client, idface_client_2
from typing import Optional
from datetime import datetime, time
import asyncio
import base64

router = APIRouter()


# ==================== CRUD Operations ====================

@router.post("/", response_model=VisitorResponse, status_code=status.HTTP_201_CREATED)
async def create_visitor(visitor: VisitorCreate, db = Depends(get_db)):
    """
    Cria um novo visitante seguindo o fluxo:
    1. Cadastra no banco local
    2. Sincroniza com AMBOS os leitores
    3. Busca o ID correto nos leitores
    4. Atualiza o banco local com o ID do leitor
    5. Envia a imagem se fornecida
    
    O endTime é automaticamente ajustado para 23:59:59 da data fornecida.
    """
    visitor_service = VisitorService(db)
    
    # Guardar imagem temporariamente
    temp_image = visitor.image
    
    # Ajustar endTime para 23:59:59 da data fornecida
    end_time_adjusted = visitor.endTime.replace(hour=23, minute=59, second=59, microsecond=0)
    
    # 1. Criar visitante localmente (SEM imagem inicialmente)
    create_result = await visitor_service.create_visitor(
        name=visitor.name,
        registration=visitor.registration,
        begin_time=visitor.beginTime,
        end_time=end_time_adjusted,
        image=None
    )

    if not create_result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar visitante: {create_result.get('errors', ['Erro desconhecido.'])}"
        )

    new_visitor = create_result["visitor"]
    
    # Preparar dados para envio aos leitores
    idface_data = {
        "name": new_visitor.name,
        "registration": new_visitor.registration,
        "password": "",
        "salt": ""
    }
    
    # 2. Sincronizar com os leitores
    try:
        # ===== LEITOR 1 =====
        idface_id = None
        async with idface_client:
            # Criar visitante no leitor 1
            await idface_client.create_user(idface_data)
            await asyncio.sleep(0.5)
            
            # Buscar visitante no leitor 1
            search_result = await idface_client.load_users(
                where={"users": {
                    "name": new_visitor.name,
                    "registration": new_visitor.registration
                }}
            )
            
            idface_users = search_result.get("users", [])
            if not idface_users:
                raise Exception(f"Visitante não encontrado no LEITOR 1 após criação")
            
            idface_id = idface_users[0]["id"]
            
            # Enviar imagem para leitor 1
            if temp_image:
                try:
                    image_bytes = base64.b64decode(temp_image)
                    await idface_client.update_user_image(
                        user_id=idface_id,
                        image_bytes=image_bytes
                    )
                except Exception as e:
                    print(f"⚠️ Erro ao enviar imagem para LEITOR 1: {str(e)}")
        
        # ===== LEITOR 2 (MESMA LÓGICA) =====
        idface_id_2 = None
        async with idface_client_2:
            # Criar visitante no leitor 2
            await idface_client_2.create_user(idface_data)
            await asyncio.sleep(0.5)
            
            # Buscar visitante no leitor 2
            search_result_2 = await idface_client_2.load_users(
                where={"users": {
                    "name": new_visitor.name,
                    "registration": new_visitor.registration
                }}
            )
            
            idface_users_2 = search_result_2.get("users", [])
            if not idface_users_2:
                raise Exception(f"Visitante não encontrado no LEITOR 2 após criação")
            
            idface_id_2 = idface_users_2[0]["id"]
            
            # Enviar imagem para leitor 2
            if temp_image:
                try:
                    image_bytes = base64.b64decode(temp_image)
                    await idface_client_2.update_user_image(
                        user_id=idface_id_2,
                        image_bytes=image_bytes
                    )
                except Exception as e:
                    print(f"⚠️ Erro ao enviar imagem para LEITOR 2: {str(e)}")
        
        # 3. Atualizar banco local com o ID e a imagem (se tiver sido enviada com sucesso)
        final_idface_id = idface_id or idface_id_2
        image_to_save = temp_image if temp_image else None

        new_visitor = await db.visitor.update(
            where={"id": new_visitor.id},
            data={
                "idFaceId": final_idface_id,
                "image": image_to_save,
                "imageTimestamp": datetime.now() if image_to_save else None
            }
        )
        
        print(f"✅ Visitante {new_visitor.id} sincronizado nos 2 leitores (ID {final_idface_id})")
        
        return new_visitor
        
    except Exception as e:
        # Se algo der errado, deletar o visitante local
        await db.visitor.delete(where={"id": new_visitor.id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar com os leitores: {str(e)}"
        )


@router.get("/", response_model=VisitorListResponse)
async def list_visitors(
    skip: int = 0,
    limit: int = 2000,
    search: Optional[str] = None,
    company: Optional[str] = None,
    active_only: bool = False,
    db = Depends(get_db)
):
    """
    Lista todos os visitantes com filtros opcionais
    """
    visitor_service = VisitorService(db)
    result = await visitor_service.search_visitors(
        query=search,
        company=company,
        active_only=active_only,
        skip=skip,
        limit=limit
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao buscar visitantes: {result.get('errors')}"
        )
        
    return VisitorListResponse(
        total=result["total"],
        visitors=result["visitors"]
    )


@router.get("/{visitor_id}", response_model=VisitorResponse)
async def get_visitor(visitor_id: int, db = Depends(get_db)):
    """
    Busca um visitante por ID
    """
    visitor_service = VisitorService(db)
    result = await visitor_service.get_visitor_full_details(visitor_id)
    
    if not result["success"]:
        error_detail = result.get("errors", ["Erro desconhecido"])[0]
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail
        )
    
    return result["visitor"]


@router.patch("/{visitor_id}", response_model=VisitorResponse)
async def update_visitor(visitor_id: int, visitor_data: VisitorUpdate, db = Depends(get_db)):
    """
    Atualiza um visitante
    """
    visitor_service = VisitorService(db)
    
    update_result = await visitor_service.update_visitor(
        visitor_id=visitor_id,
        name=visitor_data.name,
        registration=visitor_data.registration,
        begin_time=visitor_data.beginTime,
        end_time=visitor_data.endTime
    )
    
    if not update_result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao atualizar visitante: {update_result.get('errors')}"
        )
    
    return update_result["visitor"]


@router.delete("/{visitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visitor(visitor_id: int, db = Depends(get_db)):
    """
    Deleta um visitante de AMBOS os leitores
    """
    visitor_service = VisitorService(db)
    result = await visitor_service.delete_visitor(visitor_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Erro ao deletar visitante: {result.get('errors')}"
        )


# ==================== Image Management ====================

@router.post("/{visitor_id}/image", status_code=status.HTTP_201_CREATED)
async def upload_visitor_image(visitor_id: int, image_data: VisitorImageUpload, db = Depends(get_db)):
    """
    Faz upload da imagem facial do visitante para AMBOS os leitores
    """
    visitor = await db.visitor.find_unique(where={"id": visitor_id})
    if not visitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Visitante {visitor_id} não encontrado"
        )
    
    visitor_service = VisitorService(db)
    
    # Salvar imagem no banco de dados
    set_result = await visitor_service.set_visitor_image(visitor_id, image_data.image)
    
    if not set_result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao salvar imagem: {set_result.get('errors')}"
        )
    
    # Enviar para os leitores se visitante já foi sincronizado
    if visitor.idFaceId:
        image_bytes = base64.b64decode(image_data.image)
        
        # Enviar para LEITOR 1
        try:
            async with idface_client:
                await idface_client.update_user_image(
                    user_id=visitor.idFaceId,
                    image_bytes=image_bytes
                )
        except Exception as e:
            print(f"⚠️ Erro ao enviar imagem para LEITOR 1: {str(e)}")
        
        # Enviar para LEITOR 2
        try:
            async with idface_client_2:
                await idface_client_2.update_user_image(
                    user_id=visitor.idFaceId,
                    image_bytes=image_bytes
                )
        except Exception as e:
            print(f"⚠️ Erro ao enviar imagem para LEITOR 2: {str(e)}")
    
    return {"message": "Imagem salva e enviada para ambos os leitores com sucesso"}


@router.get("/{visitor_id}/image")
async def get_visitor_image(visitor_id: int, db = Depends(get_db)):
    """
    Retorna a imagem do visitante
    """
    visitor = await db.visitor.find_unique(where={"id": visitor_id})
    if not visitor or not visitor.image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Imagem não encontrada para visitante {visitor_id}"
        )
    
    return {
        "visitorId": visitor_id,
        "image": visitor.image,
        "timestamp": visitor.imageTimestamp
    }


@router.delete("/{visitor_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visitor_image(visitor_id: int, db = Depends(get_db)):
    """
    Remove a imagem do visitante de AMBOS os leitores
    """
    visitor_service = VisitorService(db)
    result = await visitor_service.delete_visitor_image(visitor_id)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao deletar imagem: {result.get('errors')}"
        )


# ==================== Sync with iDFace ====================

@router.post("/{visitor_id}/sync-to-idface", response_model=VisitorSyncResponse)
async def sync_visitor_to_idface(visitor_id: int, sync_req: VisitorSyncRequest, db = Depends(get_db)):
    """
    Sincroniza visitante do banco local para AMBOS os leitores iDFace
    """
    visitor = await db.visitor.find_unique(where={"id": visitor_id})
    
    if not visitor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Visitante {visitor_id} não encontrado"
        )
    
    visitor_data = {
        "name": visitor.name,
        "registration": visitor.registration,
        "password": "",
        "salt": ""
    }
    
    try:
        # ===== LEITOR 1 =====
        async with idface_client:
            await idface_client.create_user(visitor_data)
        
        # ===== LEITOR 2 =====
        async with idface_client_2:
            await idface_client_2.create_user(visitor_data)
        
        return VisitorSyncResponse(
            success=True,
            message="Visitante sincronizado com ambos os leitores",
            idFaceId=visitor.idFaceId
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar: {str(e)}"
        )
