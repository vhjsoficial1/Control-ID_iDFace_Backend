"""
Testes completos para Access Rules com todas as vinculações
backend/tests/test_access_rules_complete.py
"""
import pytest


# ==================== Setup Helpers ====================

@pytest.fixture
async def test_time_zone(client):
    """Cria e sincroniza um time zone de teste"""
    # Criar time zone
    tz_response = await client.post("/api/v1/time-zones/", json={
        "name": "Horário Comercial Teste",
        "timeSpans": [
            {
                "start": 28800,  # 08:00
                "end": 64800,    # 18:00
                "mon": True,
                "tue": True,
                "wed": True,
                "thu": True,
                "fri": True,
                "sun": False,
                "sat": False,
                "hol1": False,
                "hol2": False,
                "hol3": False
            }
        ]
    })
    
    tz = tz_response.json()
    
    # Sincronizar com iDFace
    sync_response = await client.post(f"/api/v1/time-zones/{tz['id']}/sync-to-idface")
    
    yield tz
    
    # Cleanup
    try:
        await client.delete(f"/api/v1/time-zones/{tz['id']}")
    except:
        pass


@pytest.fixture
async def test_portal(client):
    """Cria um portal de teste"""
    # Assumindo que existe endpoint para criar portal
    # Se não existir, ajustar conforme necessário
    portal_response = await client.post("/api/v1/portals/", json={
        "name": "Porta Principal Teste"
    })
    
    portal = portal_response.json()
    
    yield portal
    
    # Cleanup
    try:
        await client.delete(f"/api/v1/portals/{portal['id']}")
    except:
        pass


# ==================== Teste 1: Criar Regra com Time Zones ====================

@pytest.mark.asyncio
async def test_create_rule_with_time_zones(client, test_time_zone):
    """
    Testa criação de regra com time zones vinculados
    """
    print("\n🧪 Teste 1: Criar regra com time zones")
    
    rule_data = {
        "name": "Regra com TimeZone",
        "type": 1,
        "priority": 10,
        "timeZoneIds": [test_time_zone["id"]]
    }
    
    response = await client.post("/api/v1/access-rules/", json=rule_data)
    
    assert response.status_code == 201, f"Erro: {response.text}"
    data = response.json()
    
    assert data["name"] == rule_data["name"]
    assert data["idFaceId"] is not None, "Regra não foi sincronizada com iDFace"
    
    # Verificar vinculação
    get_response = await client.get(f"/api/v1/access-rules/{data['id']}")
    rule_detail = get_response.json()
    
    assert "timeZones" in rule_detail
    assert len(rule_detail["timeZones"]) > 0
    
    print(f"✅ Regra criada: ID {data['id']}, iDFace ID {data['idFaceId']}")
    print(f"✅ Time zones vinculados: {len(rule_detail['timeZones'])}")
    
    return data["id"]


# ==================== Teste 2: Vincular Portal à Regra ====================

@pytest.mark.asyncio
async def test_link_portal_to_rule(client, test_time_zone, test_portal):
    """
    Testa vinculação de portal a regra
    """
    print("\n🧪 Teste 2: Vincular portal à regra")
    
    # Criar regra
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra para Portal",
        "type": 1,
        "priority": 20,
        "timeZoneIds": [test_time_zone["id"]]
    })
    
    rule = rule_response.json()
    rule_id = rule["id"]
    
    # Vincular portal
    link_response = await client.post(
        f"/api/v1/access-rules/{rule_id}/portals/{test_portal['id']}"
    )
    
    assert link_response.status_code == 200
    link_data = link_response.json()
    
    assert link_data["success"] == True
    
    # Verificar vinculação
    portals_response = await client.get(f"/api/v1/access-rules/{rule_id}/portals")
    portals_data = portals_response.json()
    
    assert len(portals_data["portals"]) == 1
    assert portals_data["portals"][0]["id"] == test_portal["id"]
    
    print(f"✅ Portal '{test_portal['name']}' vinculado à regra")


# ==================== Teste 3: Criar e Gerenciar Grupos ====================

@pytest.mark.asyncio
async def test_create_and_manage_group(client):
    """
    Testa criação de grupo e vinculação a regra
    """
    print("\n🧪 Teste 3: Criar e gerenciar grupo")
    
    # Criar grupo
    group_response = await client.post("/api/v1/access-rules/groups/", json={
        "name": "Grupo Administrativo"
    })
    
    assert group_response.status_code == 201
    group = group_response.json()
    
    assert group["name"] == "Grupo Administrativo"
    print(f"✅ Grupo criado: ID {group['id']}")
    
    # Criar regra
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra para Grupo",
        "type": 1,
        "priority": 30
    })
    
    rule = rule_response.json()
    
    # Vincular grupo à regra
    link_response = await client.post(
        f"/api/v1/access-rules/{rule['id']}/groups/{group['id']}"
    )
    
    assert link_response.status_code == 200
    print(f"✅ Grupo vinculado à regra")
    
    # Criar usuário para adicionar ao grupo
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Teste Grupo",
        "registration": "TESTGROUP001"
    })
    
    user = user_response.json()
    
    # Adicionar usuário ao grupo
    add_user_response = await client.post(
        f"/api/v1/access-rules/groups/{group['id']}/users/{user['id']}"
    )
    
    assert add_user_response.status_code == 200
    print(f"✅ Usuário adicionado ao grupo")
    
    # Listar usuários do grupo
    users_response = await client.get(
        f"/api/v1/access-rules/groups/{group['id']}/users"
    )
    
    users_data = users_response.json()
    assert len(users_data["users"]) == 1
    assert users_data["users"][0]["id"] == user["id"]
    
    print(f"✅ Grupo contém {len(users_data['users'])} usuário(s)")


# ==================== Teste 4: Regra Completa ====================

@pytest.mark.asyncio
async def test_complete_access_rule(client, test_time_zone, test_portal):
    """
    Testa criação de regra com todas as vinculações
    """
    print("\n🧪 Teste 4: Regra completa com todas as vinculações")
    
    # 1. Criar regra com time zones e portais
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Completa",
        "type": 1,
        "priority": 100,
        "timeZoneIds": [test_time_zone["id"]],
        "portalIds": [test_portal["id"]]
    })
    
    assert rule_response.status_code == 201
    rule = rule_response.json()
    
    print(f"✅ Regra criada: ID {rule['id']}")
    
    # 2. Criar grupo
    group_response = await client.post("/api/v1/access-rules/groups/", json={
        "name": "Grupo Teste Completo"
    })
    group = group_response.json()
    
    # 3. Vincular grupo à regra
    await client.post(f"/api/v1/access-rules/{rule['id']}/groups/{group['id']}")
    print(f"✅ Grupo vinculado")
    
    # 4. Criar usuários e adicionar ao grupo
    users = []
    for i in range(3):
        user_response = await client.post("/api/v1/users/", json={
            "name": f"Usuário Completo {i+1}",
            "registration": f"COMPLETE00{i+1}"
        })
        user = user_response.json()
        users.append(user)
        
        # Adicionar ao grupo
        await client.post(
            f"/api/v1/access-rules/groups/{group['id']}/users/{user['id']}"
        )
    
    print(f"✅ {len(users)} usuários criados e adicionados ao grupo")
    
    # 5. Vincular usuários diretamente à regra também
    for user in users[:2]:  # Vincular apenas 2 usuários diretamente
        await client.post(f"/api/v1/access-rules/{rule['id']}/users/{user['id']}")
    
    print(f"✅ 2 usuários vinculados diretamente à regra")
    
    # 6. Buscar regra completa
    detail_response = await client.get(f"/api/v1/access-rules/{rule['id']}")
    rule_detail = detail_response.json()
    
    # Verificações
    assert rule_detail["idFaceId"] is not None, "Não sincronizado com iDFace"
    assert len(rule_detail["timeZones"]) > 0, "Time zones não vinculados"
    assert len(rule_detail.get("portals", [])) > 0, "Portais não vinculados"
    
    print("\n📊 Resumo da Regra Completa:")
    print(f"   - ID Local: {rule_detail['id']}")
    print(f"   - ID iDFace: {rule_detail['idFaceId']}")
    print(f"   - Time Zones: {len(rule_detail['timeZones'])}")
    print(f"   - Usuários diretos: {len(rule_detail.get('userAccessRules', []))}")
    print(f"   - Grupos: {len(rule_detail.get('groupAccessRules', []))}")


# ==================== Teste 5: Sincronização Forçada ====================

@pytest.mark.asyncio
async def test_force_sync_to_idface(client, test_time_zone):
    """
    Testa sincronização forçada de regra
    """
    print("\n🧪 Teste 5: Sincronização forçada")
    
    # Criar regra SEM sincronização automática (simulando)
    # Primeiro criar no banco sem passar pelo endpoint que sincroniza
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Sync Forçado",
        "type": 1,
        "priority": 50,
        "timeZoneIds": [test_time_zone["id"]]
    })
    
    rule = rule_response.json()
    rule_id = rule["id"]
    
    # Forçar sincronização
    sync_response = await client.post(f"/api/v1/access-rules/{rule_id}/sync-to-idface")
    
    assert sync_response.status_code == 200
    sync_data = sync_response.json()
    
    assert sync_data["success"] == True
    assert sync_data["idFaceId"] is not None
    
    print(f"✅ Regra sincronizada forçadamente")
    print(f"   - iDFace ID: {sync_data['idFaceId']}")
    print(f"   - Time Zones sincronizados: {sync_data['syncedTimeZones']}")


# ==================== Teste 6: Prevenir Vínculos Duplicados ====================

@pytest.mark.asyncio
async def test_prevent_duplicate_links(client, test_time_zone, test_portal):
    """
    Testa prevenção de vínculos duplicados
    """
    print("\n🧪 Teste 6: Prevenir vínculos duplicados")
    
    # Criar regra
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Duplicata",
        "type": 1,
        "priority": 60
    })
    
    rule = rule_response.json()
    rule_id = rule["id"]
    
    # Primeiro vínculo com portal (deve funcionar)
    response1 = await client.post(
        f"/api/v1/access-rules/{rule_id}/portals/{test_portal['id']}"
    )
    assert response1.status_code == 200
    print("✅ Primeiro vínculo criado")
    
    # Segundo vínculo com mesmo portal (deve falhar)
    response2 = await client.post(
        f"/api/v1/access-rules/{rule_id}/portals/{test_portal['id']}"
    )
    assert response2.status_code == 400
    print("✅ Vínculo duplicado bloqueado")


# ==================== Teste 7: Deleção em Cascata ====================

@pytest.mark.asyncio
async def test_cascade_delete(client, test_time_zone):
    """
    Testa deleção em cascata de regra com vínculos
    """
    print("\n🧪 Teste 7: Deleção em cascata")
    
    # Criar regra com vinculações
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Deletar Cascata",
        "type": 1,
        "priority": 70,
        "timeZoneIds": [test_time_zone["id"]]
    })
    
    rule = rule_response.json()
    rule_id = rule["id"]
    
    # Criar usuário e vincular
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Deletar Cascata",
        "registration": "CASCADE001"
    })
    user = user_response.json()
    
    await client.post(f"/api/v1/access-rules/{rule_id}/users/{user['id']}")
    
    print(f"✅ Regra criada com vínculos")
    
    # Deletar regra
    delete_response = await client.delete(f"/api/v1/access-rules/{rule_id}")
    
    assert delete_response.status_code == 204
    print("✅ Regra deletada")
    
    # Verificar se foi deletada
    get_response = await client.get(f"/api/v1/access-rules/{rule_id}")
    assert get_response.status_code == 404
    print("✅ Regra não existe mais")
    
    # Usuário deve continuar existindo
    user_check = await client.get(f"/api/v1/users/{user['id']}")
    assert user_check.status_code == 200
    print("✅ Usuário preservado (deleção cascata correta)")


# ==================== Teste 8: Listagem com Detalhes ====================

@pytest.mark.asyncio
async def test_list_rules_with_details(client, test_time_zone):
    """
    Testa listagem de regras com todos os detalhes
    """
    print("\n🧪 Teste 8: Listagem com detalhes")
    
    # Criar algumas regras
    for i in range(3):
        await client.post("/api/v1/access-rules/", json={
            "name": f"Regra Lista {i+1}",
            "type": 1,
            "priority": i * 10,
            "timeZoneIds": [test_time_zone["id"]]
        })
    
    # Listar com detalhes
    response = await client.get("/api/v1/access-rules/?include_details=true")
    
    assert response.status_code == 200
    rules = response.json()
    
    assert len(rules) >= 3
    
    # Verificar se tem detalhes
    for rule in rules[:3]:
        assert "timeZones" in rule or "portals" in rule or "users" in rule
    
    print(f"✅ {len(rules)} regras listadas com detalhes")


# ==================== Teste 9: Validações ====================

@pytest.mark.asyncio
async def test_validations(client):
    """
    Testa validações de dados
    """
    print("\n🧪 Teste 9: Validações")
    
    # Teste 1: Time zone inexistente
    response1 = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Teste Validação",
        "type": 1,
        "priority": 10,
        "timeZoneIds": [999999]  # ID inexistente
    })
    
    assert response1.status_code == 400
    print("✅ Validação: Time zone inexistente bloqueado")
    
    # Teste 2: Time zone não sincronizado
    # Criar time zone sem sincronizar
    # (implementar se possível criar TZ sem sincronizar)
    
    # Teste 3: Portal inexistente
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Válida",
        "type": 1,
        "priority": 10
    })
    rule = rule_response.json()
    
    link_response = await client.post(
        f"/api/v1/access-rules/{rule['id']}/portals/999999"
    )
    
    assert link_response.status_code == 404
    print("✅ Validação: Portal inexistente bloqueado")


# ==================== Teste 10: Performance ====================

@pytest.mark.asyncio
async def test_performance_bulk_operations(client, test_time_zone):
    """
    Testa performance com operações em massa
    """
    print("\n🧪 Teste 10: Performance - Operações em massa")
    
    import time
    
    # Criar 10 regras com vinculações
    start_time = time.time()
    
    created_rules = []
    for i in range(10):
        response = await client.post("/api/v1/access-rules/", json={
            "name": f"Regra Performance {i+1}",
            "type": 1,
            "priority": i,
            "timeZoneIds": [test_time_zone["id"]]
        })
        
        if response.status_code == 201:
            created_rules.append(response.json())
    
    elapsed = time.time() - start_time
    
    print(f"✅ {len(created_rules)} regras criadas em {elapsed:.2f}s")
    print(f"   Média: {elapsed/len(created_rules):.3f}s por regra")
    
    # Verificar se todas foram sincronizadas
    synced = sum(1 for r in created_rules if r.get("idFaceId") is not None)
    print(f"✅ {synced}/{len(created_rules)} sincronizadas com iDFace")


# ==================== Runner ====================

if __name__ == "__main__":
    print("=" * 70)
    print("  TESTES COMPLETOS - ACCESS RULES")
    print("  Incluindo: Time Zones, Portais, Grupos e Sincronização")
    print("=" * 70)
    
    pytest.main([__file__, "-v", "-s", "--tb=short"])