import asyncio
import pytest
from httpx import AsyncClient

from app.database import connect_db, disconnect_db
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Cria um event loop para a sessão de testes."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Conecta e desconecta do banco de dados para a sessão de testes."""
    await connect_db()
    yield
    await disconnect_db()


@pytest.fixture(scope="module")
async def client():
    """Cria um cliente HTTP assíncrono para os testes do módulo."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
