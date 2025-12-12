"""
Rotas completas para Access Rules com sincronização iDFace (Fila Indiana / Sequencial)
backend/app/routers/access_rules.py
"""
from fastapi import APIRouter, HTTPException, Depends, status
from app.database import get_db
# Importando ambos os clientes
from app.utils.idface_client import idface_client, idface_client_2
from typing import Optional, List
from pydantic import BaseModel, Field
import asyncio

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

# ==================== Helpers ====================

async def _safe_request(client, method, endpoint, **kwargs):
    """Executa requisição sem travar o fluxo em caso de erro"""
    try:
        async with client:
            return await client.request(method, endpoint, **kwargs)
    except Exception as e:
        print(f"⚠️ Erro silencioso no {client.base_url} ({endpoint}): {e}")
        return None

# ==================== CRUD Access Rules ====================

@router.post("/", response_model=AccessRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_access_rule(rule: AccessRuleCreate, db = Depends(get_db)):
    """
    Cria regra de acesso no banco local E nos leitores (Sequencialmente)
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
        
        # Dados para envio
        payload = {
            "name": rule.name,
            "type": rule.type,
            "priority": rule.priority
        }

        # Variáveis para armazenar IDs retornados
        id_leitor_1 = None
        id_leitor_2 = None

        # ---------------- LEITOR 1 ----------------
        try:
            async with idface_client:
                # Criar regra
                res1 = await idface_client.create_access_rule(payload)
                if res1.get("ids"):
                    id_leitor_1 = res1["ids"][0]
                    
                    # Sincronizar vínculos (TimeZones e Portais) no Leitor 1
                    await _sync_rule_relationships(idface_client, id_leitor_1, rule, db)
                    print(f"✅ Regra criada no Leitor 1 (ID: {id_leitor_1})")
        except Exception as e:
            print(f"❌ Erro Leitor 1: {e}")

        # ---------------- LEITOR 2 ----------------
        try:
            async with idface_client_2:
                # Criar regra
                res2 = await idface_client_2.create_access_rule(payload)
                if res2.get("ids"):
                    id_leitor_2 = res2["ids"][0]
                    
                    # Sincronizar vínculos (TimeZones e Portais) no Leitor 2
                    await _sync_rule_relationships(idface_client_2, id_leitor_2, rule, db)
                    print(f"✅ Regra criada no Leitor 2 (ID: {id_leitor_2})")
        except Exception as e:
            print(f"❌ Erro Leitor 2: {e}")

        # 3. Atualizar banco local com idFaceId (Prioridade Leitor 1)
        final_id = id_leitor_1 or id_leitor_2
        
        if final_id:
            new_rule = await db.accessrule.update(
                where={"id": new_rule.id},
                data={"idFaceId": final_id}
            )
            
            # Criar vínculos no banco LOCAL
            if rule.timeZoneIds:
                for tz_id in rule.timeZoneIds:
                     await db.accessruletimezone.create(data={"accessRuleId": new_rule.id, "timeZoneId": tz_id})
            
            if rule.portalIds:
                for portal_id in rule.portalIds:
                    await db.portalaccessrule.create(data={"portalId": portal_id, "accessRuleId": new_rule.id})
        else:
            # Se falhou nos dois, deleta local
            await db.accessrule.delete(where={"id": new_rule.id})
            raise HTTPException(status_code=502, detail="Falha ao criar regra nos leitores")
        
        # 6. Recarregar com relacionamentos
        result = await db.accessrule.find_unique(
            where={"id": new_rule.id},
            include={
                "timeZones": {"include": {"timeZone": True}},
                "portalAccessRules": {"include": {"portal": True}}
            }
        )
        
        return result
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar regra: {str(e)}"
        )

async def _sync_rule_relationships(client, rule_id_device, rule_data, db):
    """Auxiliar para vincular TimeZones e Portais dentro do contexto do cliente"""
    # Time Zones
    if rule_data.timeZoneIds:
        for tz_id in rule_data.timeZoneIds:
            tz = await db.timezone.find_unique(where={"id": tz_id})
            if tz and tz.idFaceId:
                await client.request("POST", "create_objects.fcgi", json={
                    "object": "access_rule_time_zones",
                    "values": [{"access_rule_id": rule_id_device, "time_zone_id": tz.idFaceId}]
                })

    # Portais
    if rule_data.portalIds:
        for portal_id in rule_data.portalIds:
            portal = await db.portal.find_unique(where={"id": portal_id})
            if portal and portal.idFaceId:
                await client.request("POST", "create_objects.fcgi", json={
                    "object": "portal_access_rules",
                    "values": [{"portal_id": portal.idFaceId, "access_rule_id": rule_id_device}]
                })


@router.get("/", response_model=List[AccessRuleResponse])
async def list_access_rules(
    skip: int = 0,
    limit: int = 1000,
    include_details: bool = True,
    db = Depends(get_db)
):
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
            if hasattr(rule, 'userAccessRules') and rule.userAccessRules:
                for uar in rule.userAccessRules:
                    if uar.user: all_users[uar.user.id] = uar.user
            
            if hasattr(rule, 'groupAccessRules') and rule.groupAccessRules:
                for gar in rule.groupAccessRules:
                    if gar.group and hasattr(gar.group, 'userGroups') and gar.group.userGroups:
                        for ug in gar.group.userGroups:
                            if ug.user: all_users[ug.user.id] = ug.user

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
        raise HTTPException(status_code=404, detail=f"Regra {rule_id} não encontrada")
    
    all_users = {}
    if hasattr(rule, 'userAccessRules') and rule.userAccessRules:
        for uar in rule.userAccessRules:
            if uar.user: all_users[uar.user.id] = uar.user

    if hasattr(rule, 'groupAccessRules') and rule.groupAccessRules:
        for gar in rule.groupAccessRules:
            if gar.group and hasattr(gar.group, 'userGroups'):
                for ug in gar.group.userGroups:
                    if ug.user: all_users[ug.user.id] = ug.user

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
    existing = await db.accessrule.find_unique(where={"id": rule_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    
    update_data = rule_data.model_dump(exclude_unset=True)
    
    updated_rule = await db.accessrule.update(
        where={"id": rule_id},
        data=update_data
    )
    
    if existing.idFaceId and update_data:
        req_data = {
            "object": "access_rules",
            "values": update_data,
            "where": {"access_rules": {"id": existing.idFaceId}}
        }
        
        # Leitor 1
        await _safe_request(idface_client, "POST", "modify_objects.fcgi", json=req_data)
        
        # Leitor 2
        await _safe_request(idface_client_2, "POST", "modify_objects.fcgi", json=req_data)
    
    return updated_rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_access_rule(rule_id: int, db = Depends(get_db)):
    existing = await db.accessrule.find_unique(where={"id": rule_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    
    if existing.idFaceId:
        req_data = {
            "object": "access_rules",
            "where": {"access_rules": {"id": existing.idFaceId}}
        }
        
        # Leitor 1
        await _safe_request(idface_client, "POST", "destroy_objects.fcgi", json=req_data)
        
        # Leitor 2
        await _safe_request(idface_client_2, "POST", "destroy_objects.fcgi", json=req_data)
    
    await db.accessrule.delete(where={"id": rule_id})


# ==================== Portal Management ====================

@router.post("/{rule_id}/portals/{portal_id}")
async def link_portal_to_rule(
    rule_id: int,
    portal_id: int,
    db = Depends(get_db)
):
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    portal = await db.portal.find_unique(where={"id": portal_id})
    
    if not rule or not portal:
        raise HTTPException(status_code=404, detail="Regra ou Portal não encontrado")
    
    existing = await db.portalaccessrule.find_first(
        where={"portalId": portal_id, "accessRuleId": rule_id}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Vínculo já existe")
    
    await db.portalaccessrule.create(
        data={"portalId": portal_id, "accessRuleId": rule_id}
    )
    
    if rule.idFaceId and portal.idFaceId:
        req_data = {
            "object": "portal_access_rules",
            "values": [{"portal_id": portal.idFaceId, "access_rule_id": rule.idFaceId}]
        }
        
        # Leitor 1
        await _safe_request(idface_client, "POST", "create_objects.fcgi", json=req_data)
        
        # Leitor 2
        await _safe_request(idface_client_2, "POST", "create_objects.fcgi", json=req_data)
    
    return {"success": True, "message": "Portal vinculado com sucesso"}


@router.delete("/{rule_id}/portals/{portal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_portal_from_rule(
    rule_id: int,
    portal_id: int,
    db = Depends(get_db)
):
    link = await db.portalaccessrule.find_first(
        where={"portalId": portal_id, "accessRuleId": rule_id}
    )
    
    if not link:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    
    await db.portalaccessrule.delete(where={"id": link.id})


@router.get("/{rule_id}/portals")
async def list_portals_in_rule(rule_id: int, db = Depends(get_db)):
    links = await db.portalaccessrule.find_many(
        where={"accessRuleId": rule_id},
        include={"portal": True}
    )
    return {"ruleId": rule_id, "portals": [link.portal for link in links]}


# ==================== Group Management ====================

@router.post("/groups/", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(group: GroupCreate, db = Depends(get_db)):
    """
    Cria grupo e associa a regras e portais. 
    Lógica de Fila Indiana aplicada: 
    Executa fluxo completo no L1, salva DB, executa fluxo completo no L2.
    """
    # 1. Criar grupo no banco local
    new_group = await db.group.create(data={"name": group.name})
    
    # Prepara dados para a função de fluxo
    access_rule_name = f"Access Rule for Group: {new_group.name}"
    
    # Variáveis para armazenar IDs
    l1_group_id = None
    l2_group_id = None
    
    # ---------------- LEITOR 1 ----------------
    try:
        async with idface_client:
            # A) Criar Grupo
            res_g = await idface_client.request("POST", "create_objects.fcgi", json={
                "object": "groups", "values": [{"name": group.name}]
            })
            if res_g.get("ids"):
                l1_group_id = res_g["ids"][0]
                
                # B) Criar Regra
                res_ar = await idface_client.create_access_rule({
                    "name": access_rule_name, "type": 1, "priority": 10
                })
                l1_ar_id = res_ar["ids"][0]
                
                # C) Vincular Grupo-Regra
                await idface_client.request("POST", "create_objects.fcgi", json={
                    "object": "group_access_rules",
                    "values": [{"group_id": l1_group_id, "access_rule_id": l1_ar_id}]
                })
                
                # D) Vincular Portais (Todos)
                all_portals = await db.portal.find_many()
                for portal in all_portals:
                    if portal.idFaceId:
                        # Portal -> Regra
                        await idface_client.request("POST", "create_objects.fcgi", json={
                            "object": "portal_access_rules",
                            "values": [{"portal_id": portal.idFaceId, "access_rule_id": l1_ar_id}]
                        })
                        # Portal -> Grupo (Opcional, mas feito no original)
                        await idface_client.request("POST", "create_objects.fcgi", json={
                            "object": "portal_groups",
                            "values": [{"portal_id": portal.idFaceId, "group_id": l1_group_id}]
                        })
                
                print(f"✅ Fluxo de grupo completo no Leitor 1 (ID: {l1_group_id})")

    except Exception as e:
        print(f"❌ Erro Leitor 1 ao criar grupo: {e}")

    # ---------------- LEITOR 2 ----------------
    try:
        async with idface_client_2:
            # A) Criar Grupo
            res_g = await idface_client_2.request("POST", "create_objects.fcgi", json={
                "object": "groups", "values": [{"name": group.name}]
            })
            if res_g.get("ids"):
                l2_group_id = res_g["ids"][0]
                
                # B) Criar Regra
                res_ar = await idface_client_2.create_access_rule({
                    "name": access_rule_name, "type": 1, "priority": 10
                })
                l2_ar_id = res_ar["ids"][0]
                
                # C) Vincular Grupo-Regra
                await idface_client_2.request("POST", "create_objects.fcgi", json={
                    "object": "group_access_rules",
                    "values": [{"group_id": l2_group_id, "access_rule_id": l2_ar_id}]
                })
                
                # D) Vincular Portais (Todos)
                all_portals = await db.portal.find_many()
                for portal in all_portals:
                    if portal.idFaceId:
                         # Portal -> Regra
                        await idface_client_2.request("POST", "create_objects.fcgi", json={
                            "object": "portal_access_rules",
                            "values": [{"portal_id": portal.idFaceId, "access_rule_id": l2_ar_id}]
                        })
                        # Portal -> Grupo
                        await idface_client_2.request("POST", "create_objects.fcgi", json={
                            "object": "portal_groups",
                            "values": [{"portal_id": portal.idFaceId, "group_id": l2_group_id}]
                        })
                
                print(f"✅ Fluxo de grupo completo no Leitor 2 (ID: {l2_group_id})")

    except Exception as e:
        print(f"❌ Erro Leitor 2 ao criar grupo: {e}")

    # 3. Atualizar Local e Criar Relacionamentos Locais
    final_group_id = l1_group_id or l2_group_id
    
    if final_group_id:
        # Atualiza Grupo
        new_group = await db.group.update(
            where={"id": new_group.id},
            data={"idFaceId": final_group_id}
        )
        
        # Cria e atualiza Regra Local
        new_access_rule = await db.accessrule.create(
            data={"name": access_rule_name, "type": 1, "priority": 10, "idFaceId": l1_ar_id if l1_group_id else l2_ar_id}
        )
        
        # Vínculo Grupo-Regra Local
        await db.groupaccessrule.create(
            data={"groupId": new_group.id, "accessRuleId": new_access_rule.id}
        )
        
        # Vínculo Portal-Regra Local
        all_portals = await db.portal.find_many()
        for portal in all_portals:
            await db.portalaccessrule.create(
                 data={"portalId": portal.id, "accessRuleId": new_access_rule.id}
            )

        # Adicionar usuários
        if group.userIds:
            for user_id in group.userIds:
                user = await db.user.find_unique(where={"id": user_id})
                if user:
                    await db.usergroup.create(data={"userId": user.id, "groupId": new_group.id})
                    if user.idFaceId:
                        req_data = {
                            "object": "user_groups",
                            "values": [{"user_id": user.idFaceId, "group_id": final_group_id}]
                        }
                        await _safe_request(idface_client, "POST", "create_objects.fcgi", json=req_data)
                        await _safe_request(idface_client_2, "POST", "create_objects.fcgi", json=req_data)
                        
        # Adicionar TimeZone
        if group.timeZoneId:
            tz = await db.timezone.find_unique(where={"id": group.timeZoneId})
            if tz:
                await db.accessruletimezone.create(data={"accessRuleId": new_access_rule.id, "timeZoneId": tz.id})
                if tz.idFaceId:
                    req_data = {
                        "object": "access_rule_time_zones",
                        "values": [{"access_rule_id": new_access_rule.idFaceId, "time_zone_id": tz.idFaceId}]
                    }
                    await _safe_request(idface_client, "POST", "create_objects.fcgi", json=req_data)
                    await _safe_request(idface_client_2, "POST", "create_objects.fcgi", json=req_data)

        return new_group
    else:
        await db.group.delete(where={"id": new_group.id})
        raise HTTPException(status_code=500, detail="Falha ao criar grupo nos leitores")

@router.get("/groups/", response_model=List[GroupResponse])
async def list_groups(db = Depends(get_db)):
    return await db.group.find_many(order={"name": "asc"})


@router.post("/{rule_id}/groups/{group_id}")
async def link_group_to_rule(rule_id: int, group_id: int, db = Depends(get_db)):
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    group = await db.group.find_unique(where={"id": group_id})
    
    if not rule or not group:
        raise HTTPException(status_code=404, detail="Regra ou Grupo não encontrado")
    
    existing = await db.groupaccessrule.find_first(where={"groupId": group_id, "accessRuleId": rule_id})
    if existing:
        raise HTTPException(status_code=400, detail="Vínculo já existe")
    
    await db.groupaccessrule.create(data={"groupId": group_id, "accessRuleId": rule_id})
    
    if rule.idFaceId and group.idFaceId:
        req_data = {
            "object": "group_access_rules",
            "values": [{"group_id": group.idFaceId, "access_rule_id": rule.idFaceId}]
        }
        # L1
        await _safe_request(idface_client, "POST", "create_objects.fcgi", json=req_data)
        # L2
        await _safe_request(idface_client_2, "POST", "create_objects.fcgi", json=req_data)
    
    return {"success": True, "message": "Grupo vinculado com sucesso"}


@router.delete("/{rule_id}/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_group_from_rule(rule_id: int, group_id: int, db = Depends(get_db)):
    link = await db.groupaccessrule.find_first(
        where={"groupId": group_id, "accessRuleId": rule_id}
    )
    if not link:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    
    await db.groupaccessrule.delete(where={"id": link.id})


# ==================== User-Group Management ====================

@router.post("/groups/{group_id}/users/{user_id}")
async def add_user_to_group(group_id: int, user_id: int, db = Depends(get_db)):
    group = await db.group.find_unique(where={"id": group_id})
    user = await db.user.find_unique(where={"id": user_id})
    
    if not group or not user:
        raise HTTPException(status_code=404, detail="Grupo ou Usuário não encontrado")
    
    existing = await db.usergroup.find_first(where={"userId": user_id, "groupId": group_id})
    if existing:
        raise HTTPException(status_code=400, detail="Usuário já pertence ao grupo")
    
    await db.usergroup.create(data={"userId": user_id, "groupId": group_id})

    if group.idFaceId and user.idFaceId:
        req_data = {
            "object": "user_groups",
            "values": [{"user_id": user.idFaceId, "group_id": group.idFaceId}]
        }
        # L1
        await _safe_request(idface_client, "POST", "create_objects.fcgi", json=req_data)
        # L2
        await _safe_request(idface_client_2, "POST", "create_objects.fcgi", json=req_data)
    
    return {"success": True, "message": "Usuário adicionado ao grupo"}


@router.delete("/groups/{group_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_from_group(group_id: int, user_id: int, db = Depends(get_db)):
    link = await db.usergroup.find_first(
        where={"userId": user_id, "groupId": group_id},
        include={"user": True, "group": True}
    )
    
    if not link:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")

    if link.group.idFaceId and link.user.idFaceId:
        req_data = {
            "object": "user_groups",
            "where": {"user_groups": {"user_id": link.user.idFaceId, "group_id": link.group.idFaceId}}
        }
        # L1
        await _safe_request(idface_client, "POST", "destroy_objects.fcgi", json=req_data)
        # L2
        await _safe_request(idface_client_2, "POST", "destroy_objects.fcgi", json=req_data)
    
    await db.usergroup.delete(where={"id": link.id})


@router.get("/groups/{group_id}/users")
async def list_users_in_group(group_id: int, db = Depends(get_db)):
    links = await db.usergroup.find_many(
        where={"groupId": group_id},
        include={"user": True}
    )
    return {"groupId": group_id, "users": [link.user for link in links]}


# ==================== Sync Operations ====================

@router.post("/{rule_id}/sync-to-idface")
async def sync_rule_to_idface(rule_id: int, db = Depends(get_db)):
    """Força sincronização completa em ambos os leitores"""
    rule = await db.accessrule.find_unique(
        where={"id": rule_id},
        include={
            "timeZones": {"include": {"timeZone": True}},
            "portalAccessRules": {"include": {"portal": True}}
        }
    )
    
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    
    rule_payload = {
        "name": rule.name,
        "type": rule.type,
        "priority": rule.priority
    }

    # Leitor 1
    try:
        async with idface_client:
            # Tenta criar se não tiver ID, ou atualizar se tiver (simplificado para Create aqui)
            res = await idface_client.create_access_rule(rule_payload)
            if res.get('ids'):
                # Sincroniza relacionamentos
                await _sync_rule_relationships(idface_client, res['ids'][0], rule, db)
                # Atualiza ID local se necessário
                if not rule.idFaceId:
                    await db.accessrule.update(where={"id": rule_id}, data={"idFaceId": res['ids'][0]})
    except Exception as e:
        print(f"Sync L1 Error: {e}")

    # Leitor 2
    try:
        async with idface_client_2:
            res = await idface_client_2.create_access_rule(rule_payload)
            if res.get('ids'):
                await _sync_rule_relationships(idface_client_2, res['ids'][0], rule, db)
    except Exception as e:
        print(f"Sync L2 Error: {e}")
    
    return {"success": True, "message": "Sincronização disparada para ambos os leitores"}


# ==================== User-Rule Management ====================

@router.post("/{rule_id}/users/{user_id}", status_code=status.HTTP_201_CREATED)
async def link_user_to_rule(rule_id: int, user_id: int, db = Depends(get_db)):
    rule = await db.accessrule.find_unique(where={"id": rule_id})
    user = await db.user.find_unique(where={"id": user_id})
    
    if not rule or not user:
        raise HTTPException(status_code=404, detail="Regra ou Usuário não encontrado")

    existing = await db.useraccessrule.find_first(where={"userId": user_id, "accessRuleId": rule_id})
    if existing:
        raise HTTPException(status_code=400, detail="Vínculo já existe")

    await db.useraccessrule.create(data={"userId": user_id, "accessRuleId": rule_id})

    if rule.idFaceId and user.idFaceId:
        req_data = {
            "object": "user_access_rules",
            "values": [{"user_id": user.idFaceId, "access_rule_id": rule.idFaceId}]
        }
        # L1
        await _safe_request(idface_client, "POST", "create_objects.fcgi", json=req_data)
        # L2
        await _safe_request(idface_client_2, "POST", "create_objects.fcgi", json=req_data)

    return {"success": True, "message": "Usuário vinculado com sucesso"}


@router.delete("/{rule_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_user_from_rule(rule_id: int, user_id: int, db = Depends(get_db)):
    link = await db.useraccessrule.find_first(
        where={"userId": user_id, "accessRuleId": rule_id},
        include={"user": True, "accessRule": True}
    )
    
    if not link:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")

    if link.accessRule.idFaceId and link.user.idFaceId:
        req_data = {
            "object": "user_access_rules",
            "where": {"user_access_rules": {"user_id": link.user.idFaceId, "access_rule_id": link.accessRule.idFaceId}}
        }
        # L1
        await _safe_request(idface_client, "POST", "destroy_objects.fcgi", json=req_data)
        # L2
        await _safe_request(idface_client_2, "POST", "destroy_objects.fcgi", json=req_data)

    await db.useraccessrule.delete(where={"id": link.id})