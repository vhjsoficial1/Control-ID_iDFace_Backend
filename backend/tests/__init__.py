"""
Configuração e fixtures para testes do iDFace Control System
"""
import asyncio
import pytest
from httpx import AsyncClient
from typing import Generator, AsyncGenerator

from app.database import connect_db, disconnect_db
from app.main import app


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Cria um event loop para a sessão de testes.
    Necessário para testes assíncronos com pytest-asyncio.
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """
    Conecta e desconecta do banco de dados para a sessão de testes.
    Executado automaticamente uma vez por sessão.
    """
    print("\n🔧 Conectando ao banco de dados de teste...")
    await connect_db()
    
    yield
    
    print("\n🔧 Desconectando do banco de dados de teste...")
    await disconnect_db()


@pytest.fixture(scope="function")
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Cria um cliente HTTP assíncrono para os testes.
    Um novo cliente é criado para cada função de teste.
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# ==================== Fixtures Auxiliares ====================

@pytest.fixture
async def test_user(client: AsyncClient):
    """
    Cria um usuário de teste e retorna seus dados.
    O usuário é deletado automaticamente após o teste (cleanup).
    """
    user_data = {
        "name": "Usuário Teste Fixture",
        "registration": "FIXTURE001"
    }
    
    response = await client.post("/api/v1/users/", json=user_data)
    user = response.json()
    
    yield user
    
    # Cleanup: deleta usuário após teste
    try:
        await client.delete(f"/api/v1/users/{user['id']}")
    except Exception:
        pass  # Ignora se já foi deletado


@pytest.fixture
async def test_access_rule(client: AsyncClient):
    """
    Cria uma regra de acesso de teste.
    A regra é deletada automaticamente após o teste (cleanup).
    """
    rule_data = {
        "name": "Regra Teste Fixture",
        "type": 1,
        "priority": 10
    }
    
    response = await client.post("/api/v1/access-rules/", json=rule_data)
    rule = response.json()
    
    yield rule
    
    # Cleanup: deleta regra após teste
    try:
        await client.delete(f"/api/v1/access-rules/{rule['id']}")
    except Exception:
        pass


@pytest.fixture
def sample_base64_image() -> str:
    """
    Retorna uma imagem de exemplo em base64 (1x1 pixel PNG).
    Útil para testes de upload de imagem.
    """
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


# ==================== Hooks do Pytest ====================

def pytest_configure(config):
    """
    Executado antes dos testes começarem.
    Configuração customizada do pytest.
    """
    print("\n" + "=" * 70)
    print("  🧪 INICIANDO TESTES - iDFace Control System")
    print("=" * 70)


def pytest_sessionfinish(session, exitstatus):
    """
    Executado após todos os testes terminarem.
    Exibe resumo dos resultados.
    """
    print("\n" + "=" * 70)
    print("  📊 TESTES FINALIZADOS")
    print("=" * 70)
    
    if exitstatus == 0:
        print("  ✅ Todos os testes passaram com sucesso!")
    else:
        print(f"  ❌ Alguns testes falharam (código: {exitstatus})")
    print("=" * 70 + "\n")


# ==================== Markers Automáticos ====================

def pytest_collection_modifyitems(config, items):
    """
    Modifica items coletados para adicionar markers automaticamente.
    """
    for item in items:
        # Adiciona marker 'asyncio' automaticamente para funções async
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
        
        # Adiciona marker 'integration' para testes que usam o client
        if "client" in item.fixturenames:
            item.add_marker(pytest.mark.integration)


# ==================== Classe Helper ====================

class TestHelpers:
    """
    Classe com métodos auxiliares para testes.
    Facilita a criação de dados de teste comuns.
    """
    
    @staticmethod
    async def create_test_user(
        client: AsyncClient,
        name: str = "Test User",
        registration: str = "TEST001"
    ):
        """Cria um usuário de teste"""
        response = await client.post("/api/v1/users/", json={
            "name": name,
            "registration": registration
        })
        return response.json()
    
    @staticmethod
    async def create_test_rule(
        client: AsyncClient,
        name: str = "Test Rule",
        rule_type: int = 1,
        priority: int = 10
    ):
        """Cria uma regra de teste"""
        response = await client.post("/api/v1/access-rules/", json={
            "name": name,
            "type": rule_type,
            "priority": priority
        })
        return response.json()
    
    @staticmethod
    async def link_user_to_rule(
        client: AsyncClient,
        user_id: int,
        rule_id: int
    ):
        """Vincula usuário a regra"""
        response = await client.post(
            f"/api/v1/access-rules/{rule_id}/users/{user_id}"
        )
        return response.json()


@pytest.fixture
def helpers() -> TestHelpers:
    """
    Fixture que fornece acesso aos helpers de teste.
    
    Uso:
        async def test_example(client, helpers):
            user = await helpers.create_test_user(client, "João", "123")
    """
    return TestHelpers()