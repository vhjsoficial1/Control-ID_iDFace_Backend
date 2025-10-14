"""
Testes para operações de regras de acesso
"""
import pytest


# ==================== Testes CRUD Regras de Acesso ====================

@pytest.mark.asyncio
async def test_create_access_rule(client):
    """Testa criação de regra de acesso"""
    rule_data = {
        "name": "Acesso Diurno",
        "type": 1,
        "priority": 10
    }
    
    response = await client.post("/api/v1/access-rules/", json=rule_data)
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == rule_data["name"]
    assert data["type"] == rule_data["type"]
    assert data["priority"] == rule_data["priority"]
    assert "id" in data
    
    print(f"✅ Regra criada: ID {data['id']} - {data['name']}")
    
    return data["id"]


@pytest.mark.asyncio
async def test_list_access_rules(client):
    """Testa listagem de regras de acesso"""
    response = await client.get("/api/v1/access-rules/")
    
    assert response.status_code == 200
    rules = response.json()
    
    assert isinstance(rules, list)
    
    print(f"✅ {len(rules)} regra(s) encontrada(s)")


@pytest.mark.asyncio
async def test_get_access_rule(client):
    """Testa busca de regra específica"""
    # Cria regra
    create_response = await client.post("/api/v1/access-rules/", json={
        "name": "Acesso Noturno",
        "type": 2,
        "priority": 20
    })
    
    rule_id = create_response.json()["id"]
    
    # Busca a regra
    response = await client.get(f"/api/v1/access-rules/{rule_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == rule_id
    assert data["name"] == "Acesso Noturno"
    
    print(f"✅ Regra encontrada: {data['name']}")


@pytest.mark.asyncio
async def test_update_access_rule(client):
    """Testa atualização de regra de acesso"""
    # Cria regra
    create_response = await client.post("/api/v1/access-rules/", json={
        "name": "Acesso Temporário",
        "type": 3,
        "priority": 5
    })
    
    rule_id = create_response.json()["id"]
    
    # Atualiza
    update_data = {
        "name": "Acesso Temporário Atualizado",
        "priority": 15
    }
    
    response = await client.patch(f"/api/v1/access-rules/{rule_id}", json=update_data)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["name"] == "Acesso Temporário Atualizado"
    assert data["priority"] == 15
    
    print(f"✅ Regra atualizada: {data['name']}")


@pytest.mark.asyncio
async def test_delete_access_rule(client):
    """Testa deleção de regra de acesso"""
    # Cria regra
    create_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Teste Deletar",
        "type": 4,
        "priority": 25
    })
    
    rule_id = create_response.json()["id"]
    
    # Deleta
    response = await client.delete(f"/api/v1/access-rules/{rule_id}")
    
    assert response.status_code == 204
    
    # Verifica se foi deletada
    get_response = await client.get(f"/api/v1/access-rules/{rule_id}")
    assert get_response.status_code == 404
    
    print(f"✅ Regra deletada: ID {rule_id}")


# ==================== Testes de Vínculo Usuário-Regra ====================

@pytest.mark.asyncio
async def test_link_user_to_rule(client):
    """Testa vinculação de usuário a regra"""
    # Cria usuário
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Teste Regra",
        "registration": "RULE123"
    })
    user_id = user_response.json()["id"]
    
    # Cria regra
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Teste Vínculo",
        "type": 1,
        "priority": 10
    })
    rule_id = rule_response.json()["id"]
    
    # Vincula usuário à regra
    response = await client.post(f"/api/v1/access-rules/{rule_id}/users/{user_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success"] == True
    
    print(f"✅ Usuário {user_id} vinculado à regra {rule_id}")


@pytest.mark.asyncio
async def test_list_users_in_rule(client):
    """Testa listagem de usuários em uma regra"""
    # Cria usuário e regra
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Lista Regra",
        "registration": "LISTRULE123"
    })
    user_id = user_response.json()["id"]
    
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Lista Usuários",
        "type": 1,
        "priority": 10
    })
    rule_id = rule_response.json()["id"]
    
    # Vincula
    await client.post(f"/api/v1/access-rules/{rule_id}/users/{user_id}")
    
    # Lista usuários
    response = await client.get(f"/api/v1/access-rules/{rule_id}/users")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "users" in data
    assert len(data["users"]) > 0
    
    print(f"✅ {len(data['users'])} usuário(s) na regra")


@pytest.mark.asyncio
async def test_unlink_user_from_rule(client):
    """Testa remoção de vínculo usuário-regra"""
    # Cria e vincula
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Desvincular",
        "registration": "UNLINK123"
    })
    user_id = user_response.json()["id"]
    
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Desvincular",
        "type": 1,
        "priority": 10
    })
    rule_id = rule_response.json()["id"]
    
    await client.post(f"/api/v1/access-rules/{rule_id}/users/{user_id}")
    
    # Desvincula
    response = await client.delete(f"/api/v1/access-rules/{rule_id}/users/{user_id}")
    
    assert response.status_code == 204
    
    print(f"✅ Vínculo removido: Usuário {user_id} <-> Regra {rule_id}")


# ==================== Testes de Prioridade ====================

@pytest.mark.asyncio
async def test_rules_ordered_by_priority(client):
    """Testa ordenação de regras por prioridade"""
    # Cria regras com diferentes prioridades
    await client.post("/api/v1/access-rules/", json={
        "name": "Prioridade Alta",
        "type": 1,
        "priority": 100
    })
    
    await client.post("/api/v1/access-rules/", json={
        "name": "Prioridade Baixa",
        "type": 1,
        "priority": 10
    })
    
    await client.post("/api/v1/access-rules/", json={
        "name": "Prioridade Média",
        "type": 1,
        "priority": 50
    })
    
    # Lista regras
    response = await client.get("/api/v1/access-rules/")
    
    assert response.status_code == 200
    rules = response.json()
    
    # Verifica se está ordenado por prioridade
    priorities = [rule["priority"] for rule in rules]
    assert priorities == sorted(priorities)
    
    print(f"✅ Regras ordenadas por prioridade: {priorities[:5]}")


# ==================== Testes de Validação ====================

@pytest.mark.asyncio
async def test_create_rule_without_name(client):
    """Testa criação de regra sem nome (deve falhar)"""
    rule_data = {
        "type": 1,
        "priority": 10
        # name ausente
    }
    
    response = await client.post("/api/v1/access-rules/", json=rule_data)
    
    assert response.status_code == 422  # Validation error
    
    print("✅ Validação funcionando: nome obrigatório")


@pytest.mark.asyncio
async def test_create_rule_invalid_type(client):
    """Testa criação de regra com tipo inválido"""
    rule_data = {
        "name": "Regra Tipo Inválido",
        "type": 99,  # Tipo inválido (deve ser 0-10)
        "priority": 10
    }
    
    response = await client.post("/api/v1/access-rules/", json=rule_data)
    
    assert response.status_code == 422
    
    print("✅ Validação funcionando: tipo deve estar entre 0-10")


@pytest.mark.asyncio
async def test_create_rule_negative_priority(client):
    """Testa criação de regra com prioridade negativa"""
    rule_data = {
        "name": "Regra Prioridade Negativa",
        "type": 1,
        "priority": -5  # Prioridade negativa inválida
    }
    
    response = await client.post("/api/v1/access-rules/", json=rule_data)
    
    assert response.status_code == 422
    
    print("✅ Validação funcionando: prioridade não pode ser negativa")


@pytest.mark.asyncio
async def test_get_nonexistent_rule(client):
    """Testa busca de regra inexistente"""
    response = await client.get("/api/v1/access-rules/999999")
    
    assert response.status_code == 404
    
    print("✅ Retorna 404 para regra inexistente")


# ==================== Testes de Regras de Tipos Diferentes ====================

@pytest.mark.asyncio
async def test_create_rules_different_types(client):
    """Testa criação de regras com diferentes tipos"""
    types = [
        ("Tipo 0 - Livre", 0),
        ("Tipo 1 - Padrão", 1),
        ("Tipo 2 - Controlado", 2),
        ("Tipo 3 - Restrito", 3)
    ]
    
    created_rules = []
    
    for name, rule_type in types:
        response = await client.post("/api/v1/access-rules/", json={
            "name": name,
            "type": rule_type,
            "priority": rule_type * 10
        })
        
        assert response.status_code == 201
        created_rules.append(response.json())
    
    print(f"✅ {len(created_rules)} regras de tipos diferentes criadas")


# ==================== Testes de Vínculo com Usuário Inexistente ====================

@pytest.mark.asyncio
async def test_link_nonexistent_user_to_rule(client):
    """Testa vinculação de usuário inexistente"""
    # Cria regra
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Teste User Inexistente",
        "type": 1,
        "priority": 10
    })
    rule_id = rule_response.json()["id"]
    
    # Tenta vincular usuário inexistente
    response = await client.post(f"/api/v1/access-rules/{rule_id}/users/999999")
    
    assert response.status_code == 404
    
    print("✅ Retorna 404 ao vincular usuário inexistente")


@pytest.mark.asyncio
async def test_link_user_to_nonexistent_rule(client):
    """Testa vinculação de usuário a regra inexistente"""
    # Cria usuário
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Teste Regra Inexistente",
        "registration": "NORULE123"
    })
    user_id = user_response.json()["id"]
    
    # Tenta vincular a regra inexistente
    response = await client.post(f"/api/v1/access-rules/999999/users/{user_id}")
    
    assert response.status_code == 404
    
    print("✅ Retorna 404 ao vincular a regra inexistente")


# ==================== Testes de Duplicate Link ====================

@pytest.mark.asyncio
async def test_duplicate_user_rule_link(client):
    """Testa criação de vínculo duplicado (deve falhar)"""
    # Cria usuário e regra
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Duplicate Link",
        "registration": "DUPLINK123"
    })
    user_id = user_response.json()["id"]
    
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Duplicate Link",
        "type": 1,
        "priority": 10
    })
    rule_id = rule_response.json()["id"]
    
    # Primeiro vínculo (deve funcionar)
    response1 = await client.post(f"/api/v1/access-rules/{rule_id}/users/{user_id}")
    assert response1.status_code == 200
    
    # Segundo vínculo (deve falhar)
    response2 = await client.post(f"/api/v1/access-rules/{rule_id}/users/{user_id}")
    assert response2.status_code == 400
    
    print("✅ Previne vínculos duplicados")


# ==================== Testes de Paginação ====================

@pytest.mark.asyncio
async def test_pagination_access_rules(client):
    """Testa paginação de regras de acesso"""
    # Cria várias regras
    for i in range(15):
        await client.post("/api/v1/access-rules/", json={
            "name": f"Regra Paginação {i}",
            "type": 1,
            "priority": i
        })
    
    # Primeira página
    response1 = await client.get("/api/v1/access-rules/?skip=0&limit=10")
    assert response1.status_code == 200
    page1 = response1.json()
    assert len(page1) <= 10
    
    # Segunda página
    response2 = await client.get("/api/v1/access-rules/?skip=10&limit=10")
    assert response2.status_code == 200
    page2 = response2.json()
    
    print(f"✅ Paginação funcionando: Página 1 ({len(page1)} itens), Página 2 ({len(page2)} itens)")


# ==================== Testes de Integridade ====================

@pytest.mark.asyncio
async def test_delete_rule_with_linked_users(client):
    """Testa deleção de regra com usuários vinculados"""
    # Cria usuário e regra
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Integridade",
        "registration": "INTEGRITY123"
    })
    user_id = user_response.json()["id"]
    
    rule_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Com Vínculos",
        "type": 1,
        "priority": 10
    })
    rule_id = rule_response.json()["id"]
    
    # Vincula
    await client.post(f"/api/v1/access-rules/{rule_id}/users/{user_id}")
    
    # Tenta deletar regra (deve funcionar com cascade)
    response = await client.delete(f"/api/v1/access-rules/{rule_id}")
    
    # Verifica comportamento (pode ser 204 com cascade ou 400 com proteção)
    assert response.status_code in [204, 400]
    
    if response.status_code == 204:
        print("✅ Regra deletada com cascade")
    else:
        print("✅ Regra protegida contra deleção com vínculos")


# ==================== Testes de Performance ====================

@pytest.mark.asyncio
async def test_bulk_create_rules(client):
    """Testa criação em massa de regras"""
    import time
    
    start_time = time.time()
    
    # Cria 20 regras
    for i in range(20):
        await client.post("/api/v1/access-rules/", json={
            "name": f"Regra Bulk {i}",
            "type": i % 10,
            "priority": i
        })
    
    elapsed_time = time.time() - start_time
    
    print(f"✅ 20 regras criadas em {elapsed_time:.2f}s")
    
    # Verifica se foram criadas
    response = await client.get("/api/v1/access-rules/")
    rules = response.json()
    
    bulk_rules = [r for r in rules if "Bulk" in r["name"]]
    assert len(bulk_rules) >= 20


# ==================== Testes de Atualização Parcial ====================

@pytest.mark.asyncio
async def test_partial_update_rule(client):
    """Testa atualização parcial de regra"""
    # Cria regra
    create_response = await client.post("/api/v1/access-rules/", json={
        "name": "Regra Update Parcial",
        "type": 1,
        "priority": 10
    })
    
    rule_id = create_response.json()["id"]
    original_type = create_response.json()["type"]
    
    # Atualiza apenas prioridade
    update_response = await client.patch(f"/api/v1/access-rules/{rule_id}", json={
        "priority": 50
    })
    
    assert update_response.status_code == 200
    updated_rule = update_response.json()
    
    # Verifica que apenas prioridade mudou
    assert updated_rule["priority"] == 50
    assert updated_rule["type"] == original_type
    assert updated_rule["name"] == "Regra Update Parcial"
    
    print("✅ Atualização parcial funcionando corretamente")


if __name__ == "__main__":
    print("=" * 60)
    print("  TESTES DE REGRAS DE ACESSO")
    print("=" * 60)
    
    pytest.main([__file__, "-v", "-s"])
