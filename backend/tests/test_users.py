"""
Testes para operações de usuários
"""
import pytest


# ==================== Testes CRUD Usuários ====================

@pytest.mark.asyncio
async def test_create_user(client):
    """Testa criação de usuário"""
    user_data = {
        "name": "João Silva",
        "registration": "123456",
        "password": "senha123"
    }
    
    response = await client.post("/api/v1/users/", json=user_data)
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == user_data["name"]
    assert data["registration"] == user_data["registration"]
    assert "id" in data
    
    print(f"✅ Usuário criado: ID {data['id']}")
    
    return data["id"]


@pytest.mark.asyncio
async def test_list_users(client):
    """Testa listagem de usuários"""
    response = await client.get("/api/v1/users/")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "total" in data
    assert "users" in data
    assert isinstance(data["users"], list)
    
    print(f"✅ {data['total']} usuário(s) encontrado(s)")


@pytest.mark.asyncio
async def test_get_user(client):
    """Testa busca de usuário específico"""
    # Primeiro cria um usuário
    create_response = await client.post("/api/v1/users/", json={
        "name": "Maria Santos",
        "registration": "654321"
    })
    
    user_id = create_response.json()["id"]
    
    # Busca o usuário
    response = await client.get(f"/api/v1/users/{user_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["id"] == user_id
    assert data["name"] == "Maria Santos"
    
    print(f"✅ Usuário encontrado: {data['name']}")


@pytest.mark.asyncio
async def test_update_user(client):
    """Testa atualização de usuário"""
    # Cria usuário
    create_response = await client.post("/api/v1/users/", json={
        "name": "Pedro Costa",
        "registration": "111222"
    })
    
    user_id = create_response.json()["id"]
    
    # Atualiza
    update_data = {
        "name": "Pedro Costa Silva"
    }
    
    response = await client.patch(f"/api/v1/users/{user_id}", json=update_data)
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["name"] == "Pedro Costa Silva"
    
    print(f"✅ Usuário atualizado: {data['name']}")


@pytest.mark.asyncio
async def test_delete_user(client):
    """Testa deleção de usuário"""
    # Cria usuário
    create_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Teste Deletar",
        "registration": "999888"
    })
    
    user_id = create_response.json()["id"]
    
    # Deleta
    response = await client.delete(f"/api/v1/users/{user_id}")
    
    assert response.status_code == 204
    
    # Verifica se foi deletado
    get_response = await client.get(f"/api/v1/users/{user_id}")
    assert get_response.status_code == 404
    
    print(f"✅ Usuário deletado: ID {user_id}")


# ==================== Testes de Cartões ====================

@pytest.mark.asyncio
async def test_add_card_to_user(client):
    """Testa adição de cartão ao usuário"""
    # Cria usuário
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário com Cartão",
        "registration": "777666"
    })
    
    user_id = user_response.json()["id"]
    
    # Adiciona cartão
    card_data = {
        "value": 123456789,
        "userId": user_id
    }
    
    response = await client.post(f"/api/v1/users/{user_id}/cards", json=card_data)
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["value"] == card_data["value"]
    assert data["userId"] == user_id
    
    print(f"✅ Cartão adicionado: {data['value']}")


@pytest.mark.asyncio
async def test_list_user_cards(client):
    """Testa listagem de cartões do usuário"""
    # Cria usuário com cartão
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Multi Cartões",
        "registration": "555444"
    })
    
    user_id = user_response.json()["id"]
    
    # Adiciona cartões
    await client.post(f"/api/v1/users/{user_id}/cards", json={
        "value": 111111111,
        "userId": user_id
    })
    
    await client.post(f"/api/v1/users/{user_id}/cards", json={
        "value": 222222222,
        "userId": user_id
    })
    
    # Lista cartões
    response = await client.get(f"/api/v1/users/{user_id}/cards")
    
    assert response.status_code == 200
    cards = response.json()
    
    assert len(cards) == 2
    
    print(f"✅ {len(cards)} cartão(ões) encontrado(s)")


@pytest.mark.asyncio
async def test_delete_card(client):
    """Testa deleção de cartão"""
    # Cria usuário e cartão
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Deletar Cartão",
        "registration": "333222"
    })
    
    user_id = user_response.json()["id"]
    
    card_response = await client.post(f"/api/v1/users/{user_id}/cards", json={
        "value": 987654321,
        "userId": user_id
    })
    
    card_id = card_response.json()["id"]
    
    # Deleta cartão
    response = await client.delete(f"/api/v1/users/cards/{card_id}")
    
    assert response.status_code == 204
    
    print(f"✅ Cartão deletado: ID {card_id}")


# ==================== Testes de QR Code ====================

@pytest.mark.asyncio
async def test_add_qrcode_to_user(client):
    """Testa adição de QR Code ao usuário"""
    # Cria usuário
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário com QR",
        "registration": "888777"
    })
    
    user_id = user_response.json()["id"]
    
    # Adiciona QR Code
    qr_data = {
        "value": "QR123456",
        "userId": user_id
    }
    
    response = await client.post(f"/api/v1/users/{user_id}/qrcodes", json=qr_data)
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["value"] == qr_data["value"]
    assert data["userId"] == user_id
    
    print(f"✅ QR Code adicionado: {data['value']}")


# ==================== Testes de Busca ====================

@pytest.mark.asyncio
async def test_search_users(client):
    """Testa busca de usuários"""
    # Cria usuário para buscar
    await client.post("/api/v1/users/", json={
        "name": "Carlos Teste Busca",
        "registration": "BUSCA123"
    })
    
    # Busca por nome
    response = await client.get("/api/v1/users/?search=Carlos")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] > 0
    assert any("Carlos" in user["name"] for user in data["users"])
    
    print(f"✅ Busca encontrou {data['total']} resultado(s)")


# ==================== Testes de Validação ====================

@pytest.mark.asyncio
async def test_create_user_without_name(client):
    """Testa criação de usuário sem nome (deve falhar)"""
    user_data = {
        "registration": "123456"
        # name ausente
    }
    
    response = await client.post("/api/v1/users/", json=user_data)
    
    assert response.status_code == 422  # Validation error
    
    print("✅ Validação funcionando: nome obrigatório")


@pytest.mark.asyncio
async def test_get_nonexistent_user(client):
    """Testa busca de usuário inexistente"""
    response = await client.get("/api/v1/users/999999")
    
    assert response.status_code == 404
    
    print("✅ Retorna 404 para usuário inexistente")


# ==================== Testes de Imagem ====================

@pytest.mark.asyncio
async def test_upload_user_image(client):
    """Testa upload de imagem do usuário"""
    # Cria usuário
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário com Imagem",
        "registration": "IMG123"
    })
    
    user_id = user_response.json()["id"]
    
    # Imagem fake em base64 (1x1 pixel PNG)
    fake_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    
    image_data = {
        "userId": user_id,
        "image": fake_image
    }
    
    response = await client.post(f"/api/v1/users/{user_id}/image", json=image_data)
    
    assert response.status_code == 201
    
    print(f"✅ Imagem salva para usuário {user_id}")


@pytest.mark.asyncio
async def test_get_user_image(client):
    """Testa obtenção de imagem do usuário"""
    # Cria usuário e adiciona imagem
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Get Imagem",
        "registration": "GETIMG123"
    })
    
    user_id = user_response.json()["id"]
    
    fake_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    
    await client.post(f"/api/v1/users/{user_id}/image", json={
        "userId": user_id,
        "image": fake_image
    })
    
    # Busca imagem
    response = await client.get(f"/api/v1/users/{user_id}/image")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "image" in data
    assert data["image"] == fake_image
    
    print(f"✅ Imagem recuperada para usuário {user_id}")


@pytest.mark.asyncio
async def test_delete_user_image(client):
    """Testa deleção de imagem do usuário"""
    # Cria usuário com imagem
    user_response = await client.post("/api/v1/users/", json={
        "name": "Usuário Delete Imagem",
        "registration": "DELIMG123"
    })
    
    user_id = user_response.json()["id"]
    
    fake_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    
    await client.post(f"/api/v1/users/{user_id}/image", json={
        "userId": user_id,
        "image": fake_image
    })
    
    # Deleta imagem
    response = await client.delete(f"/api/v1/users/{user_id}/image")
    
    assert response.status_code == 204
    
    # Verifica se foi deletada
    get_response = await client.get(f"/api/v1/users/{user_id}/image")
    assert get_response.status_code == 404
    
    print(f"✅ Imagem deletada para usuário {user_id}")


if __name__ == "__main__":
    print("=" * 60)
    print("  TESTES DE USUÁRIOS")
    print("=" * 60)
    
    pytest.main([__file__, "-v", "-s"])
