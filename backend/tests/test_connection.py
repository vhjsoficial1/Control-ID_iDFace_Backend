"""
Testes de conexão com o dispositivo iDFace
"""
import pytest
import asyncio
from app.utils.idface_client import idface_client


@pytest.mark.asyncio
async def test_idface_login():
    """Testa login no dispositivo iDFace"""
    try:
        async with idface_client:
            assert idface_client.session is not None
            assert len(idface_client.session) > 0
            print("✅ Login bem-sucedido")
    except Exception as e:
        pytest.fail(f"Falha no login: {str(e)}")


@pytest.mark.asyncio
async def test_idface_system_info():
    """Testa obtenção de informações do sistema"""
    try:
        async with idface_client:
            info = await idface_client.get_system_info()
            
            assert info is not None
            assert isinstance(info, dict)
            
            print(f"✅ Informações obtidas:")
            print(f"   Versão: {info.get('version', 'N/A')}")
            print(f"   Device ID: {info.get('device_id', 'N/A')}")
            
    except Exception as e:
        pytest.fail(f"Falha ao obter informações: {str(e)}")


@pytest.mark.asyncio
async def test_idface_session_persistence():
    """Testa persistência de sessão"""
    try:
        async with idface_client:
            session1 = idface_client.session
            
            # Faz segunda requisição com mesma sessão
            info = await idface_client.get_system_info()
            session2 = idface_client.session
            
            assert session1 == session2
            print("✅ Sessão persistente")
            
    except Exception as e:
        pytest.fail(f"Falha na persistência de sessão: {str(e)}")


@pytest.mark.asyncio
async def test_idface_load_users():
    """Testa carregamento de usuários"""
    try:
        async with idface_client:
            result = await idface_client.load_users()
            
            assert result is not None
            assert isinstance(result, dict)
            
            users = result.get("users", [])
            print(f"✅ {len(users)} usuário(s) encontrado(s)")
            
    except Exception as e:
        pytest.fail(f"Falha ao carregar usuários: {str(e)}")


@pytest.mark.asyncio
async def test_idface_load_access_rules():
    """Testa carregamento de regras de acesso"""
    try:
        async with idface_client:
            result = await idface_client.load_access_rules()
            
            assert result is not None
            assert isinstance(result, dict)
            
            rules = result.get("access_rules", [])
            print(f"✅ {len(rules)} regra(s) encontrada(s)")
            
    except Exception as e:
        pytest.fail(f"Falha ao carregar regras: {str(e)}")


@pytest.mark.asyncio
async def test_idface_logout():
    """Testa logout do dispositivo"""
    try:
        await idface_client.login()
        session = idface_client.session
        
        assert session is not None
        
        await idface_client.logout()
        
        assert idface_client.session is None
        print("✅ Logout bem-sucedido")
        
    except Exception as e:
        pytest.fail(f"Falha no logout: {str(e)}")


def test_idface_client_initialization():
    """Testa inicialização do cliente"""
    assert idface_client is not None
    assert idface_client.base_url is not None
    assert "http://" in idface_client.base_url
    print(f"✅ Cliente inicializado: {idface_client.base_url}")


@pytest.mark.asyncio
async def test_connection_timeout():
    """Testa timeout de conexão"""
    import httpx
    
    # Testa com IP inválido (deve dar timeout ou erro)
    client = httpx.AsyncClient(timeout=2.0)
    
    try:
        response = await client.post(
            "http://192.0.2.1/login.fcgi",  # IP reservado (não existe)
            json={"login": "test", "password": "test"}
        )
        await client.aclose()
    except (httpx.TimeoutException, httpx.ConnectError):
        print("✅ Timeout detectado corretamente")
        await client.aclose()
    except Exception as e:
        await client.aclose()
        print(f"⚠️  Outro erro: {type(e).__name__}")


if __name__ == "__main__":
    print("=" * 60)
    print("  TESTES DE CONEXÃO - iDFace")
    print("=" * 60)
    
    # Executa testes
    pytest.main([__file__, "-v", "-s"])