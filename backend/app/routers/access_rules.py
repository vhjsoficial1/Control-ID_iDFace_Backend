"""
Rotas completas para Access Rules com sincronização iDFace
backend/app/routers/access_rules.py
"""
from fastapi import APIRouter, HTTPException, Depends, status
from app.database import get_db
from app.utils.idface_client import idface_client
from typing import Optional, List
from pydantic import BaseModel, Field

router = APIRouter()


# ==================== Schemas ====================

class AccessRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: int = Field(1, ge=0, le=10)
    priority: int = Field(0, ge=0)
    timeZoneIds: Optional[List[int]] = Field(None, description="IDs dos time zones")
    portalIds: Optional[List[int]] = Field(None, description="IDs dos portais")


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
    timeZones: Optional[List[dict]] = None
    portals: Optional[List[dict]] = None
    users: Optional[List[dict]] = None
    
    class Config:
        from_attributes = True


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    userIds: Optional[List[int]] = Field(None, description="IDs dos usuários a serem adicionados ao grupo")
    timeZoneId: Optional[int] = Field(None, description="ID do time zone a ser associado ao grupo")


class GroupResponse(BaseModel):
    id: int
    name: str
    idFaceId: Optional[int] = None
    
    class Config:
        from_attributes = True


# ==================== CRUD Access Rules ====================

@router.post("/", response_model=AccessRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_access_rule(rule: AccessRuleCreate, db = Depends(get_db)):
    """
    Cria regra de acesso no banco local E no iDFace simultaneamente
    """
    try:
        # 1. Criar no banco local primeiro
        new_rule = await db.accessrule.create(
            data={
                "name": rule.name,
                "type": rule.type,
                "priority": rule.priority
            }
        )
        
        try:
            # 2. Sincronizar com iDFace
            async with idface_client:
                # Criar regra no iDFace
                idface_result = await idface_client.create_access_rule({
                    "name": rule.name,
                    "type": rule.type,
                    "priority": rule.priority
                })
                
                # Extrair ID do iDFace
                idface_ids = idface_result.get("ids", [])
                if not idface_ids:
                    raise ValueError("iDFace não retornou IDs da regra criada")
                
                idface_rule_id = idface_ids[0]
                
                # 3. Atualizar banco local com idFaceId
                new_rule = await db.accessrule.update(
                    where={"id": new_rule.id},
                    data={"idFaceId": idface_rule_id}
                )
                
                # 4. Vincular Time Zones se fornecidos
                if rule.timeZoneIds:
                    for tz_id in rule.timeZoneIds:
                        # Verificar se time zone existe e está sincronizado
                        tz = await db.timezone.find_unique(where={"id": tz_id})
                        if not tz:
                            raise ValueError(f"Time zone {tz_id} não encontrado")
                        
                        if not tz.idFaceId:
                            raise ValueError(f"Time zone '{tz.name}' não está sincronizado com iDFace")
                        
                        # Criar vínculo no banco local
                        await db.accessruletimezone.create(
                            data={
                                "accessRuleId": new_rule.id,
                                "timeZoneId": tz_id
                            }
                        )
                        
                        # Criar vínculo no iDFace
                        await idface_client.request(
                            "POST",
                            "create_objects.fcgi",
                            json={
                                "object": "access_rule_time_zones",
                                "values": [{
                                    "access_rule_id": idface_rule_id,
                                    "time_zone_id": tz.idFaceId
                                }]
                            }
                        )
                
                # 5. Vincular Portais se fornecidos
                if rule.portalIds:
                    for portal_id in rule.portalIds:
                        portal = await db.portal.find_unique(where={"id": portal_id})
                        if not portal:
                            raise ValueError(f"Portal {portal_id} não encontrado")
                        
                        # Criar vínculo no banco local
                        await db.portalaccessrule.create(
                            data={
                                "portalId": portal_id,
                                "accessRuleId": new_rule.id
                            }
                        )
                        
                        # Vincular no iDFace (se portal tiver idFaceId)
                        if portal.idFaceId:
                            await idface_client.request(
                                "POST",
                                "create_objects.fcgi",
                                json={
                                    "object": "portal_access_rules",
                                    "values": [{
                                        "portal_id": portal.idFaceId,
                                        "access_rule_id": idface_rule_id
                                    }]
                                }
                            )
        
        except Exception as sync_error:
            # Se falhar a sincronização, deletar do banco local
            await db.accessrule.delete(where={"id": new_rule.id})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao sincronizar com iDFace: {str(sync_error)}"
            )
        
        # 6. Recarregar com relacionamentos
        result = await db.accessrule.find_unique(
            where={"id": new_rule.id},
            include={
                "timeZones": {"include": {"timeZone": True}},
                "portalAccessRules": {"include": {"portal": True}}
            }
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar regra: {str(e)}"
        )


@router.get("/", response_model=List[AccessRuleResponse])
async def list_access_rules(
    skip: int = 0,
    limit: int = 100,
    include_details: bool = True,
    db = Depends(get_db)
):
    """
    Lista todas as regras de acesso com detalhes, incluindo usuários de grupos.
    """
    include_config = {}
    if include_details:
        include_config = {
            "timeZones": {"include": {"timeZone": True}},
            "portalAccessRules": {"include": {"portal": True}},
            "userAccessRules": {"include": {"user": True}},
            "groupAccessRules": {
                "include": {
                    "group": {
                        "include": {
                            "userGroups": {"include": {"user": True}}
                        }
                    }
                }
            }
        }

    rules_from_db = await db.accessrule.find_many(
        skip=skip,
        take=limit,
        order={"priority": "asc"},
        include=include_config
    )

    response_rules = []
    for rule in rules_from_db:
        all_users = {}
        if include_details:
            # Adiciona usuários diretamente ligados à regra
            if hasattr(rule, 'userAccessRules') and rule.userAccessRules:
                for uar in rule.userAccessRules:
                    if uar.user:
                        all_users[uar.user.id] = uar.user
            
            # Adiciona usuários de grupos ligados à regra
            if hasattr(rule, 'groupAccessRules') and rule.groupAccessRules:
                for gar in rule.groupAccessRules:
                    if gar.group and hasattr(gar.group, 'userGroups') and gar.group.userGroups:
                        for ug in gar.group.userGroups:
                            if ug.user:
                                all_users[ug.user.id] = ug.user

        rule_dict = {
            "id": rule.id,
            "name": rule.name,
            "type": rule.type,
            "priority": rule.priority,
            "idFaceId": rule.idFaceId,
            "timeZones": [art.timeZone.model_dump() for art in rule.timeZones if art.timeZone] if include_details and hasattr(rule, 'timeZones') else [],
            "portals": [par.portal.model_dump() for par in rule.portalAccessRules if par.portal] if include_details and hasattr(rule, 'portalAccessRules') else [],
            "users": [user.model_dump() for user in all_users.values()]
        }
        response_rules.append(rule_dict)
        
    return response_rules


@router.get("/{rule_id}", response_model=AccessRuleResponse)
async def get_access_rule(rule_id: int, db = Depends(get_db)):
    """
    Busca regra de acesso por ID com todos os relacionamentos, incluindo usuários de grupos.
    """
    rule = await db.accessrule.find_unique(
        where={"id": rule_id},
        include={
            "timeZones": {"include": {"timeZone": True}},
            "portalAccessRules": {"include": {"portal": True}},
            "userAccessRules": {"include": {"user": True}},
            "groupAccessRules": {
                "include": {
                    "group": {
                        "include": {
                            "userGroups": {"include": {"user": True}}
                        }
                    }
                }
            }
        }
    )
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    all_users = {}

    # Adiciona usuários diretamente ligados à regra
    if hasattr(rule, 'userAccessRules') and rule.userAccessRules:
        for uar in rule.userAccessRules:
            if uar.user:
                all_users[uar.user.id] = uar.user

    # Adiciona usuários de grupos ligados à regra
    if hasattr(rule, 'groupAccessRules') and rule.groupAccessRules:
        for gar in rule.groupAccessRules:
            if gar.group and hasattr(gar.group, 'userGroups'):
                for ug in gar.group.userGroups:
                    if ug.user:
                        all_users[ug.user.id] = ug.user

    rule_dict = {
        "id": rule.id,
        "name": rule.name,
        "type": rule.type,
        "priority": rule.priority,
        "idFaceId": rule.idFaceId,
        "timeZones": [art.timeZone.model_dump() for art in rule.timeZones if art.timeZone] if hasattr(rule, 'timeZones') else [],
        "portals": [par.portal.model_dump() for par in rule.portalAccessRules if par.portal] if hasattr(rule, 'portalAccessRules') else [],
        "users": [user.model_dump() for user in all_users.values()]
    }
        
    return rule_dict


@router.patch("/{rule_id}", response_model=AccessRuleResponse)
async def update_access_rule(
    rule_id: int, 
    rule_data: AccessRuleUpdate, 
    db = Depends(get_db)
):
    """
    Atualiza regra de acesso (local e iDFace)
    """
    existing = await db.accessrule.find_unique(where={"id": rule_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    update_data = rule_data.model_dump(exclude_unset=True)
    
    # Atualizar localmente
    updated_rule = await db.accessrule.update(
        where={"id": rule_id},
        data=update_data
    )
    
    # Se estiver sincronizado, atualizar no iDFace
    if existing.idFaceId and update_data:
        try:
            async with idface_client:
                await idface_client.request(
                    "POST",
                    "modify_objects.fcgi",
                    json={
                        "object": "access_rules",
                        "values": update_data,
                        "where": {
                            "access_rules": {"id": existing.idFaceId}
                        }
                    }
                )
        except Exception as e:
            print(f"Aviso: Erro ao atualizar no iDFace: {e}")
    
    return updated_rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_access_rule(rule_id: int, db = Depends(get_db)):
    """
    Deleta regra de acesso (local e iDFace)
    """
    existing = await db.accessrule.find_unique(where={"id": rule_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    # Deletar do iDFace primeiro (se sincronizado)
    if existing.idFaceId:
        try:
            async with idface_client:
                await idface_client.request(
                    "POST",
                    "destroy_objects.fcgi",
                    json={
                        "object": "access_rules",
                        "where": {
                            "access_rules": {"id": existing.idFaceId}
                        }
                    }
                )
        except Exception as e:
            print(f"Aviso: Erro ao deletar do iDFace: {e}")
    
    # Deletar localmente (cascade automático)
    await db.accessrule.delete(where={"id": rule_id})


# ==================== Portal Management ====================

@router.post("/{rule_id}/portals/{portal_id}")
async def link_portal_to_rule(
    rule_id: int,
    portal_id: int,
    db = Depends(get_db)
):
    """
    Vincula portal a regra de acesso
    """
    # Verificar se regra existe
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {rule_id} não encontrada"
        )
    
    # Verificar se portal existe
    portal = await db.portal.find_unique(where={"id": portal_id})
    if not portal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portal {portal_id} não encontrado"
        )
    
    # Verificar duplicata
    existing = await db.portalaccessrule.find_first(
        where={
            "portalId": portal_id,
            "accessRuleId": rule_id
        }
    )
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portal já vinculado a esta regra"
        )
    
    # Criar vínculo local
    link = await db.portalaccessrule.create(
        data={
            "portalId": portal_id,
            "accessRuleId": rule_id
        }
    )
    
    # Sincronizar com iDFace (se ambos estiverem sincronizados)
    if rule.idFaceId and portal.idFaceId:
        try:
            async with idface_client:
                await idface_client.request(
                    "POST",
                    "create_objects.fcgi",
                    json={
                        "object": "portal_access_rules",
                        "values": [{
                            "portal_id": portal.idFaceId,
                            "access_rule_id": rule.idFaceId
                        }]
                    }
                )
        except Exception as e:
            print(f"Aviso: Erro ao sincronizar vínculo com iDFace: {e}")
    
    return {
        "success": True,
        "message": f"Portal '{portal.name}' vinculado à regra '{rule.name}'"
    }


@router.delete("/{rule_id}/portals/{portal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_portal_from_rule(
    rule_id: int,
    portal_id: int,
    db = Depends(get_db)
):
    """
    Remove vínculo entre portal e regra
    """
    link = await db.portalaccessrule.find_first(
        where={
            "portalId": portal_id,
            "accessRuleId": rule_id
        }
    )
    
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vínculo não encontrado"
        )
    
    await db.portalaccessrule.delete(where={"id": link.id})


@router.get("/{rule_id}/portals")
async def list_portals_in_rule(rule_id: int, db = Depends(get_db)):
    """
    Lista portais vinculados a uma regra
    """
    links = await db.portalaccessrule.find_many(
        where={"accessRuleId": rule_id},
        include={"portal": True}
    )
    
    return {
        "ruleId": rule_id,
        "portals": [link.portal for link in links]
    }


# ==================== Group Management ====================

@router.post("/groups/", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(group: GroupCreate, db = Depends(get_db)):
    """
    Cria grupo de usuários, opcionalmente os associa e vincula a um time zone via AccessRule.
    """
    try:
        # 1. Criar grupo no banco local
        new_group = await db.group.create(
            data={"name": group.name}
        )
        
        # 2. Sincronizar grupo com iDFace
        try:
            async with idface_client:
                result = await idface_client.request(
                    "POST",
                    "create_objects.fcgi",
                    json={
                        "object": "groups",
                        "values": [{"name": group.name}]
                    }
                )
                
                idface_ids = result.get("ids", [])
                if idface_ids:
                    new_group = await db.group.update(
                        where={"id": new_group.id},
                        data={"idFaceId": idface_ids[0]}
                    )
        except Exception as e:
            print(f"Aviso: Erro ao sincronizar grupo com iDFace: {e}")
            # Não falhar a criação do grupo local se a sincronização falhar
        
        # 3. Associar usuários se fornecidos
        if group.userIds:
            for user_id in group.userIds:
                user = await db.user.find_unique(where={"id": user_id})
                if not user:
                    print(f"Aviso: Usuário {user_id} não encontrado, pulando associação.")
                    continue
                
                # Criar vínculo local
                await db.usergroup.create(
                    data={"userId": user.id, "groupId": new_group.id}
                )
                
                # Sincronizar vínculo com iDFace (se ambos estiverem sincronizados)
                if new_group.idFaceId and user.idFaceId:
                    try:
                        async with idface_client:
                            await idface_client.request(
                                "POST",
                                "create_objects.fcgi",
                                json={
                                    "object": "user_groups", # Assumindo que 'user_groups' é um objeto válido para criação
                                    "values": [{
                                        "user_id": user.idFaceId,
                                        "group_id": new_group.idFaceId
                                    }]
                                }
                            )
                    except Exception as e:
                        print(f"Aviso: Erro ao sincronizar vínculo de usuário {user.id} com grupo {new_group.id} no iDFace: {e}")
        
        # 4. Vincular a um TimeZone via AccessRule se fornecido
        if group.timeZoneId:
            time_zone = await db.timezone.find_unique(where={"id": group.timeZoneId})
            if not time_zone:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Time Zone {group.timeZoneId} não encontrado."
                )
            
            # Criar uma nova AccessRule para este grupo e TimeZone
            access_rule_name = f"Access Rule for Group: {new_group.name}"
            new_access_rule = await db.accessrule.create(
                data={
                    "name": access_rule_name,
                    "type": 1, # Default type
                    "priority": 0 # Default priority
                }
            )
            
            # Sincronizar AccessRule com iDFace
            try:
                async with idface_client:
                    idface_ar_result = await idface_client.create_access_rule({
                        "name": access_rule_name,
                        "type": 1,
                        "priority": 0
                    })
                    idface_ar_ids = idface_ar_result.get("ids", [])
                    if idface_ar_ids:
                        new_access_rule = await db.accessrule.update(
                            where={"id": new_access_rule.id},
                            data={"idFaceId": idface_ar_ids[0]}
                        )
            except Exception as e:
                print(f"Aviso: Erro ao sincronizar AccessRule para grupo com iDFace: {e}")
            
            # Vincular TimeZone à nova AccessRule localmente
            await db.accessruletimezone.create(
                data={
                    "accessRuleId": new_access_rule.id,
                    "timeZoneId": time_zone.id
                }
            )
            
            # Sincronizar vínculo TimeZone-AccessRule com iDFace
            if new_access_rule.idFaceId and time_zone.idFaceId:
                try:
                    async with idface_client:
                        await idface_client.request(
                            "POST",
                            "create_objects.fcgi",
                            json={
                                "object": "access_rule_time_zones",
                                "values": [{
                                    "access_rule_id": new_access_rule.idFaceId,
                                    "time_zone_id": time_zone.idFaceId
                                }]
                            }
                        )
                except Exception as e:
                    print(f"Aviso: Erro ao sincronizar vínculo TimeZone-AccessRule com iDFace: {e}")
            
            # Vincular o novo grupo à nova AccessRule localmente
            await db.groupaccessrule.create(
                data={
                    "groupId": new_group.id,
                    "accessRuleId": new_access_rule.id
                }
            )
            
            # Sincronizar vínculo Group-AccessRule com iDFace
            if new_group.idFaceId and new_access_rule.idFaceId:
                try:
                    async with idface_client:
                        await idface_client.request(
                            "POST",
                            "create_objects.fcgi",
                            json={
                                "object": "group_access_rules",
                                "values": [{
                                    "group_id": new_group.idFaceId,
                                    "access_rule_id": new_access_rule.idFaceId
                                }]
                            }
                        )
                except Exception as e:
                    print(f"Aviso: Erro ao sincronizar vínculo Group-AccessRule com iDFace: {e}")
        
        return new_group
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar grupo: {str(e)}"
        )


@router.get("/groups/", response_model=List[GroupResponse])
async def list_groups(db = Depends(get_db)):
    """
    Lista todos os grupos
    """
    groups = await db.group.find_many(order={"name": "asc"})
    return groups


@router.post("/{rule_id}/groups/{group_id}")
async def link_group_to_rule(
    rule_id: int,
    group_id: int,
    db = Depends(get_db)
):
    """
    Vincula grupo a regra de acesso
    """
    # Verificações
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    
    group = await db.group.find_unique(where={"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    # Verificar duplicata
    existing = await db.groupaccessrule.find_first(
        where={"groupId": group_id, "accessRuleId": rule_id}
    )
    
    if existing:
        raise HTTPException(status_code=400, detail="Grupo já vinculado a esta regra")
    
    # Criar vínculo
    await db.groupaccessrule.create(
        data={"groupId": group_id, "accessRuleId": rule_id}
    )
    
    # Sincronizar com iDFace
    if rule.idFaceId and group.idFaceId:
        try:
            async with idface_client:
                await idface_client.request(
                    "POST",
                    "create_objects.fcgi",
                    json={
                        "object": "group_access_rules",
                        "values": [{
                            "group_id": group.idFaceId,
                            "access_rule_id": rule.idFaceId
                        }]
                    }
                )
        except Exception as e:
            print(f"Aviso: {e}")
    
    return {"success": True, "message": f"Grupo '{group.name}' vinculado à regra '{rule.name}'"}


@router.delete("/{rule_id}/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_group_from_rule(rule_id: int, group_id: int, db = Depends(get_db)):
    """
    Remove vínculo entre grupo e regra
    """
    link = await db.groupaccessrule.find_first(
        where={"groupId": group_id, "accessRuleId": rule_id}
    )
    
    if not link:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    
    await db.groupaccessrule.delete(where={"id": link.id})


# ==================== User-Group Management ====================

@router.post("/groups/{group_id}/users/{user_id}")
async def add_user_to_group(group_id: int, user_id: int, db = Depends(get_db)):
    """
    Adiciona usuário a um grupo
    """
    # Verificações
    group = await db.group.find_unique(where={"id": group_id})
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    
    # Verificar duplicata
    existing = await db.usergroup.find_first(
        where={"userId": user_id, "groupId": group_id}
    )
    
    if existing:
        raise HTTPException(status_code=400, detail="Usuário já pertence a este grupo")
    
    # Criar vínculo
    await db.usergroup.create(
        data={"userId": user_id, "groupId": group_id}
    )

    # Sincronizar com iDFace
    if group.idFaceId and user.idFaceId:
        try:
            async with idface_client:
                await idface_client.request(
                    "POST",
                    "create_objects.fcgi",
                    json={
                        "object": "user_groups",
                        "values": [{
                            "user_id": user.idFaceId,
                            "group_id": group.idFaceId
                        }]
                    }
                )
        except Exception as e:
            print(f"Aviso: Erro ao sincronizar vínculo de usuário com grupo no iDFace: {e}")
    
    return {"success": True, "message": f"Usuário '{user.name}' adicionado ao grupo '{group.name}'"}


@router.delete("/groups/{group_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_group(group_id: int, user_id: int, db = Depends(get_db)):
    """
    Remove usuário de um grupo
    """
    link = await db.usergroup.find_first(
        where={"userId": user_id, "groupId": group_id},
        include={"user": True, "group": True}
    )
    
    if not link:
        raise HTTPException(status_code=404, detail="Usuário não pertence a este grupo")

    # Deletar do iDFace primeiro
    if link.group and link.group.idFaceId and link.user and link.user.idFaceId:
        try:
            async with idface_client:
                await idface_client.request(
                    "POST",
                    "destroy_objects.fcgi",
                    json={
                        "object": "user_groups",
                        "where": {
                            "user_groups": {
                                "user_id": link.user.idFaceId,
                                "group_id": link.group.idFaceId
                            }
                        }
                    }
                )
        except Exception as e:
            # Log o erro mas não impede a deleção local
            print(f"Aviso: Erro ao remover vínculo de usuário do grupo no iDFace: {e}")
    
    # Deletar do banco local
    await db.usergroup.delete(where={"id": link.id})


@router.get("/groups/{group_id}/users")
async def list_users_in_group(group_id: int, db = Depends(get_db)):
    """
    Lista usuários de um grupo
    """
    links = await db.usergroup.find_many(
        where={"groupId": group_id},
        include={"user": True}
    )
    
    return {
        "groupId": group_id,
        "users": [link.user for link in links]
    }


# ==================== Sync Operations ====================

@router.post("/{rule_id}/sync-to-idface")
async def sync_rule_to_idface(rule_id: int, db = Depends(get_db)):
    """
    Força sincronização completa de uma regra com o iDFace
    """
    rule = await db.accessrule.find_unique(
        where={"id": rule_id},
        include={
            "timeZones": {"include": {"timeZone": True}},
            "portalAccessRules": {"include": {"portal": True}}
        }
    )
    
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    
    try:
        async with idface_client:
            # Se não tem idFaceId, criar
            if not rule.idFaceId:
                result = await idface_client.create_access_rule({
                    "name": rule.name,
                    "type": rule.type,
                    "priority": rule.priority
                })
                
                idface_ids = result.get("ids", [])
                if not idface_ids:
                    raise ValueError("iDFace não retornou IDs")
                
                idface_rule_id = idface_ids[0]
                
                await db.accessrule.update(
                    where={"id": rule_id},
                    data={"idFaceId": idface_rule_id}
                )
            else:
                idface_rule_id = rule.idFaceId
            
            # Sincronizar time zones
            synced_zones = 0
            for art in rule.timeZones:
                if art.timeZone.idFaceId:
                    try:
                        await idface_client.request(
                            "POST",
                            "create_objects.fcgi",
                            json={
                                "object": "access_rule_time_zones",
                                "values": [{
                                    "access_rule_id": idface_rule_id,
                                    "time_zone_id": art.timeZone.idFaceId
                                }]
                            }
                        )
                        synced_zones += 1
                    except Exception as e:
                        print(f"Erro ao vincular time zone: {e}")
            
            # Sincronizar portais
            synced_portals = 0
            for par in rule.portalAccessRules:
                if par.portal.idFaceId:
                    try:
                        await idface_client.request(
                            "POST",
                            "create_objects.fcgi",
                            json={
                                "object": "portal_access_rules",
                                "values": [{
                                    "portal_id": par.portal.idFaceId,
                                    "access_rule_id": idface_rule_id
                                }]
                            }
                        )
                        synced_portals += 1
                    except Exception as e:
                        print(f"Erro ao vincular portal: {e}")
            
            return {
                "success": True,
                "message": "Regra sincronizada com sucesso",
                "idFaceId": idface_rule_id,
                "syncedTimeZones": synced_zones,
                "syncedPortals": synced_portals
            }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar: {str(e)}"
        )

# ==================== Direct Time Zone Association ====================

@router.post("/groups/{group_id}/time-zones/{tz_id}", status_code=status.HTTP_201_CREATED)
async def link_time_zone_to_group(group_id: int, tz_id: int, db = Depends(get_db)):
    """
    Associa um Time Zone (horário) a um Group (departamento).
    Internamente, encontra ou cria uma regra de acesso para o grupo e a vincula ao time zone.
    """
    group = await db.group.find_unique(where={"id": group_id})
    if not group or not group.idFaceId:
        raise HTTPException(status_code=404, detail="Grupo não encontrado ou não sincronizado.")

    time_zone = await db.timezone.find_unique(where={"id": tz_id})
    if not time_zone or not time_zone.idFaceId:
        raise HTTPException(status_code=404, detail="Time Zone não encontrado ou não sincronizado.")

    # Encontrar ou criar a regra de acesso para o grupo
    rule_name = f"Regra para Grupo: {group.name}"
    group_rule_link = await db.groupaccessrule.find_first(
        where={"groupId": group_id},
        include={"accessRule": True}
    )

    access_rule = None
    if group_rule_link:
        access_rule = group_rule_link.accessRule
    else:
        try:
            # Cria a regra de acesso
            access_rule = await db.accessrule.create(data={"name": rule_name, "type": 1, "priority": 10}) # Prioridade alta para grupos
            async with idface_client:
                # Sincroniza
                res = await idface_client.create_access_rule({"name": rule_name, "type": 1, "priority": 10})
                rule_idface_id = res['ids'][0]
                access_rule = await db.accessrule.update(where={"id": access_rule.id}, data={"idFaceId": rule_idface_id})
                
                # Vincula grupo à regra
                await db.groupaccessrule.create(data={"groupId": group.id, "accessRuleId": access_rule.id})
                await idface_client.request("POST", "create_objects.fcgi", json={
                    "object": "group_access_rules", "values": [{"group_id": group.idFaceId, "access_rule_id": rule_idface_id}]
                })
        except Exception as e:
            if access_rule and access_rule.id:
                await db.accessrule.delete(where={"id": access_rule.id})
            raise HTTPException(status_code=500, detail=f"Erro ao criar/sincronizar regra para grupo: {e}")

    # Vincular o time zone à regra de acesso
    existing_link = await db.accessruletimezone.find_first(where={"accessRuleId": access_rule.id, "timeZoneId": tz_id})
    if existing_link:
        return {"success": True, "message": "Associação já existe."}

    await db.accessruletimezone.create(data={"accessRuleId": access_rule.id, "timeZoneId": tz_id})
    try:
        async with idface_client:
            await idface_client.request("POST", "create_objects.fcgi", json={
                "object": "access_rule_time_zones", "values": [{"access_rule_id": access_rule.idFaceId, "time_zone_id": time_zone.idFaceId}]
            })
    except Exception as e:
        # Idealmente, faria rollback do accessruletimezone.create
        raise HTTPException(status_code=500, detail=f"Erro ao sincronizar time zone com regra: {e}")

    return {"success": True, "message": f"Time Zone '{time_zone.name}' associado ao Grupo '{group.name}'."}


@router.delete("/groups/{group_id}/time-zones/{tz_id}", status_code=status.HTTP_200_OK)
async def unlink_time_zone_from_group(group_id: int, tz_id: int, db = Depends(get_db)):
    """
    Desassocia um Time Zone de um Group, procurando em todas as regras do grupo.
    """
    group_rule_links = await db.groupaccessrule.find_many(where={"groupId": group_id})
    if not group_rule_links:
        raise HTTPException(status_code=404, detail="Nenhuma regra de acesso encontrada para este grupo.")

    rule_ids = [link.accessRuleId for link in group_rule_links]

    tz_links_to_delete = await db.accessruletimezone.find_many(
        where={"timeZoneId": tz_id, "accessRuleId": {"in": rule_ids}},
        include={"accessRule": True, "timeZone": True}
    )

    if not tz_links_to_delete:
        raise HTTPException(status_code=404, detail="Associação entre este grupo e time zone não encontrada.")

    deleted_count = 0
    for link in tz_links_to_delete:
        if link.accessRule.idFaceId and link.timeZone.idFaceId:
            try:
                async with idface_client:
                    await idface_client.request("POST", "destroy_objects.fcgi", json={
                        "object": "access_rule_time_zones",
                        "where": {"access_rule_time_zones": {"access_rule_id": link.accessRule.idFaceId, "time_zone_id": link.timeZone.idFaceId}}
                    })
            except Exception as e:
                print(f"Aviso: Falha ao deletar vínculo no iDFace: {e}")
        
        await db.accessruletimezone.delete(where={"id": link.id})
        deleted_count += 1
    
    return {"success": True, "message": f"{deleted_count} associação(ões) removida(s)."}


@router.post("/users/{user_id}/time-zones/{tz_id}", status_code=status.HTTP_201_CREATED)
async def link_time_zone_to_user(user_id: int, tz_id: int, db = Depends(get_db)):
    """
    Associa um Time Zone diretamente a um User.
    Cria uma regra de acesso individual para o usuário se necessário.
    """
    user = await db.user.find_unique(where={"id": user_id})
    if not user or not user.idFaceId:
        raise HTTPException(status_code=404, detail="Usuário não encontrado ou não sincronizado.")

    time_zone = await db.timezone.find_unique(where={"id": tz_id})
    if not time_zone or not time_zone.idFaceId:
        raise HTTPException(status_code=404, detail="Time Zone não encontrado ou não sincronizado.")

    # Encontrar ou criar a regra de acesso para o usuário
    rule_name = f"Regra Individual para: {user.name} (id: {user.id})"
    user_rule_link = await db.useraccessrule.find_first(
        where={"userId": user_id, "accessRule": {"name": rule_name}},
        include={"accessRule": True}
    )

    access_rule = None
    if user_rule_link:
        access_rule = user_rule_link.accessRule
    else:
        try:
            access_rule = await db.accessrule.create(data={"name": rule_name, "type": 1, "priority": 5}) # Prioridade média
            async with idface_client:
                res = await idface_client.create_access_rule({"name": rule_name, "type": 1, "priority": 5})
                rule_idface_id = res['ids'][0]
                access_rule = await db.accessrule.update(where={"id": access_rule.id}, data={"idFaceId": rule_idface_id})
                
                await db.useraccessrule.create(data={"userId": user.id, "accessRuleId": access_rule.id})
                await idface_client.request("POST", "create_objects.fcgi", json={
                    "object": "user_access_rules", "values": [{"user_id": user.idFaceId, "access_rule_id": rule_idface_id}]
                })
        except Exception as e:
            if access_rule and access_rule.id:
                await db.accessrule.delete(where={"id": access_rule.id})
            raise HTTPException(status_code=500, detail=f"Erro ao criar/sincronizar regra para usuário: {e}")

    # Vincular o time zone à regra
    existing_link = await db.accessruletimezone.find_first(where={"accessRuleId": access_rule.id, "timeZoneId": tz_id})
    if existing_link:
        return {"success": True, "message": "Associação já existe."}

    await db.accessruletimezone.create(data={"accessRuleId": access_rule.id, "timeZoneId": tz_id})
    try:
        async with idface_client:
            await idface_client.request("POST", "create_objects.fcgi", json={
                "object": "access_rule_time_zones", "values": [{"access_rule_id": access_rule.idFaceId, "time_zone_id": time_zone.idFaceId}]
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao sincronizar time zone com regra: {e}")

    return {"success": True, "message": f"Time Zone '{time_zone.name}' associado ao Usuário '{user.name}'."}


@router.delete("/users/{user_id}/time-zones/{tz_id}", status_code=status.HTTP_200_OK)
async def unlink_time_zone_from_user(user_id: int, tz_id: int, db = Depends(get_db)):
    """
    Desassocia um Time Zone de um User, procurando em todas as regras vinculadas ao usuário.
    """
    user_rule_links = await db.useraccessrule.find_many(where={"userId": user_id})
    if not user_rule_links:
        raise HTTPException(status_code=404, detail="Usuário não vinculado a nenhuma regra de acesso.")

    rule_ids = [link.accessRuleId for link in user_rule_links]
    
    tz_links_to_delete = await db.accessruletimezone.find_many(
        where={"timeZoneId": tz_id, "accessRuleId": {"in": rule_ids}},
        include={"accessRule": True, "timeZone": True}
    )

    if not tz_links_to_delete:
        raise HTTPException(status_code=404, detail="Associação entre este usuário e time zone não encontrada.")

    deleted_count = 0
    for link in tz_links_to_delete:
        if link.accessRule.idFaceId and link.timeZone.idFaceId:
            try:
                async with idface_client:
                    await idface_client.request("POST", "destroy_objects.fcgi", json={
                        "object": "access_rule_time_zones",
                        "where": {"access_rule_time_zones": {"access_rule_id": link.accessRule.idFaceId, "time_zone_id": link.timeZone.idFaceId}}
                    })
            except Exception as e:
                print(f"Aviso: Falha ao deletar vínculo no iDFace: {e}")
        
        await db.accessruletimezone.delete(where={"id": link.id})
        deleted_count += 1
    
    return {"success": True, "message": f"{deleted_count} associação(ões) removida(s)."}


# ==================== User-Rule Management ====================

@router.post("/{rule_id}/users/{user_id}", status_code=status.HTTP_201_CREATED)
async def link_user_to_rule(
    rule_id: int,
    user_id: int,
    db = Depends(get_db)
):
    """
    Vincula um usuário diretamente a uma regra de acesso.
    """
    # Verificações
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    if not rule:
        raise HTTPException(status_code=404, detail="Regra de acesso não encontrada")

    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Verificar duplicata
    existing = await db.useraccessrule.find_first(
        where={"userId": user_id, "accessRuleId": rule_id}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Usuário já vinculado diretamente a esta regra")

    # Criar vínculo local
    await db.useraccessrule.create(
        data={"userId": user_id, "accessRuleId": rule_id}
    )

    # Sincronizar com iDFace
    if rule.idFaceId and user.idFaceId:
        try:
            async with idface_client:
                await idface_client.request(
                    "POST",
                    "create_objects.fcgi",
                    json={
                        "object": "user_access_rules",
                        "values": [{
                            "user_id": user.idFaceId,
                            "access_rule_id": rule.idFaceId
                        }]
                    }
                )
        except Exception as e:
            print(f"Aviso: Erro ao sincronizar vínculo de usuário com iDFace: {e}")

    return {"success": True, "message": f"Usuário '{user.name}' vinculado à regra '{rule.name}'"}


@router.delete("/{rule_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_user_from_rule(rule_id: int, user_id: int, db = Depends(get_db)):
    """
    Remove o vínculo direto entre um usuário e uma regra de acesso.
    """
    # Encontrar o vínculo no banco local
    link = await db.useraccessrule.find_first(
        where={"userId": user_id, "accessRuleId": rule_id},
        include={"user": True, "accessRule": True}
    )
    
    if not link:
        raise HTTPException(status_code=404, detail="Vínculo entre usuário e regra não encontrado")

    # Deletar do iDFace primeiro
    if link.accessRule and link.accessRule.idFaceId and link.user and link.user.idFaceId:
        try:
            async with idface_client:
                await idface_client.request(
                    "POST",
                    "destroy_objects.fcgi",
                    json={
                        "object": "user_access_rules",
                        "where": {
                            "user_access_rules": {
                                "user_id": link.user.idFaceId,
                                "access_rule_id": link.accessRule.idFaceId
                            }
                        }
                    }
                )
        except Exception as e:
            print(f"Aviso: Erro ao remover vínculo de usuário no iDFace: {e}")

    # Deletar do banco local
    await db.useraccessrule.delete(where={"id": link.id})
