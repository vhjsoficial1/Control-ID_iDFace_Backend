"""
Testes para operações de regras de acesso
"""
import pytest
from httpx import AsyncClient
from app.main import app
from app.database import connect_db, disconnect_db
import asyncio


@pytest.fixture(scope="module")
def event_loop():
    """Cria event loop para testes"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module", autouse=True)
async def setup_database():
    """Setup e teardown do banco de dados"""
    await connect_db()
    yield
    await disconnect_db()


@pytest.fixture
async def client():
    """Cliente HTTP para testes"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


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