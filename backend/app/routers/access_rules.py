from fastapi import APIRouter, HTTPException, Depends, status
from app.database import get_db
from app.utils.idface_client import idface_client
from typing import Optional

router = APIRouter()


# ==================== Schemas ====================

from pydantic import BaseModel, Field
from typing import Optional

class AccessRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: int = Field(1, ge=0, le=10)
    priority: int = Field(0, ge=0)

class AccessRuleUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[int] = None
    priority: Optional[int] = None

class AccessRuleResponse(BaseModel):
    id: int
    name: str
    type: int
    priority: int
    idFaceId: Optional[int] = None
    
    class Config:
        from_attributes = True


# ==================== CRUD Operations ====================

@router.post("/", response_model=AccessRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_access_rule(rule: AccessRuleCreate, db = Depends(get_db)):
    """
    Cria regra de acesso no banco local
    """
    try:
        new_rule = await db.accessrule.create(
            data={
                "name": rule.name,
                "type": rule.type,
                "priority": rule.priority
            }
        )
        return new_rule
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar regra: {str(e)}"
        )


@router.get("/", response_model=list[AccessRuleResponse])
async def list_access_rules(
    skip: int = 0,
    limit: int = 100,
    db = Depends(get_db)
):
    """
    Lista todas as regras de acesso
    """
    rules = await db.accessrule.find_many(
        skip=skip,
        take=limit,
        order_by={"priority": "asc"}
    )
    return rules


@router.get("/{rule_id}", response_model=AccessRuleResponse)
async def get_access_rule(rule_id: int, db = Depends(get_db)):
    """
    Busca regra de acesso por ID
    """
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    return rule


@router.patch("/{rule_id}", response_model=AccessRuleResponse)
async def update_access_rule(
    rule_id: int, 
    rule_data: AccessRuleUpdate, 
    db = Depends(get_db)
):
    """
    Atualiza regra de acesso
    """
    existing = await db.accessrule.find_unique(where={"id": rule_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    update_data = rule_data.model_dump(exclude_unset=True)
    
    updated_rule = await db.accessrule.update(
        where={"id": rule_id},
        data=update_data
    )
    
    return updated_rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_access_rule(rule_id: int, db = Depends(get_db)):
    """
    Deleta regra de acesso
    """
    existing = await db.accessrule.find_unique(where={"id": rule_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    await db.accessrule.delete(where={"id": rule_id})


# ==================== Sync with iDFace ====================

@router.post("/{rule_id}/sync-to-idface")
async def sync_access_rule_to_idface(rule_id: int, db = Depends(get_db)):
    """
    Sincroniza regra de acesso para o iDFace
    """
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    try:
        async with idface_client:
            result = await idface_client.create_access_rule({
                "name": rule.name,
                "type": rule.type,
                "priority": rule.priority
            })
            
            return {
                "success": True,
                "message": "Regra sincronizada com sucesso",
                "result": result
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar: {str(e)}"
        )


@router.post("/sync-from-idface")
async def sync_access_rules_from_idface(db = Depends(get_db)):
    """
    Importa regras de acesso do iDFace para o banco local
    """
    try:
        async with idface_client:
            result = await idface_client.load_access_rules()
            
            # TODO: Processar e salvar no banco local
            # rules = result.get("access_rules", [])
            
            return {
                "success": True,
                "message": "Regras importadas com sucesso",
                "count": 0  # TODO: len(rules)
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao importar: {str(e)}"
        )


# ==================== Link User to Access Rule ====================

@router.post("/{rule_id}/users/{user_id}")
async def link_user_to_access_rule(
    rule_id: int,
    user_id: int,
    db = Depends(get_db)
):
    """
    Vincula usuário a uma regra de acesso
    """
    # Verificar se regra existe
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    # Verificar se usuário existe
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    # Criar vínculo
    try:
        link = await db.useraccessrule.create(
            data={
                "userId": user_id,
                "accessRuleId": rule_id
            }
        )
        
        return {
            "success": True,
            "message": "Usuário vinculado à regra com sucesso"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao vincular: {str(e)}"
        )


@router.delete("/{rule_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_user_from_access_rule(
    rule_id: int,
    user_id: int,
    db = Depends(get_db)
):
    """
    Remove vínculo entre usuário e regra de acesso
    """
    link = await db.useraccessrule.find_first(
        where={
            "userId": user_id,
            "accessRuleId": rule_id
        }
    )
    
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vínculo não encontrado"
        )
    
    await db.useraccessrule.delete(where={"id": link.id})


@router.get("/{rule_id}/users")
async def list_users_in_access_rule(rule_id: int, db = Depends(get_db)):
    """
    Lista usuários vinculados a uma regra de acesso
    """
    links = await db.useraccessrule.find_many(
        where={"accessRuleId": rule_id},
        include={"user": True}
    )
    
    return {
        "ruleId": rule_id,
        "users": [link.user for link in links]
    }