"""
Script para testar conexão com o leitor iDFace
Execute: python test_idface_connection.py
"""
import asyncio
import httpx
from datetime import datetime


# Configurações do leitor
IDFACE_IP = "169.254.111.129"
IDFACE_LOGIN = "admin"
IDFACE_PASSWORD = "admin"


async def test_connection():
    """Testa conexão básica com o leitor iDFace"""
    base_url = f"http://{IDFACE_IP}"
    
    print("🔌 Testando conexão com iDFace...")
    print(f"📍 IP: {IDFACE_IP}")
    print("-" * 50)
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Teste 1: Login
            print("\n1️⃣ Tentando fazer login...")
            login_url = f"{base_url}/login.fcgi"
            login_data = {
                "login": IDFACE_LOGIN,
                "password": IDFACE_PASSWORD
            }
            
            response = await client.post(login_url, json=login_data)
            
            if response.status_code == 200:
                session_data = response.json()
                session = session_data.get("session")
                print(f"✅ Login bem-sucedido!")
                print(f"🔑 Session ID: {session}")
            else:
                print(f"❌ Erro no login: {response.status_code}")
                print(f"Resposta: {response.text}")
                return
            
            # Teste 2: Informações do Sistema
            print("\n2️⃣ Obtendo informações do sistema...")
            info_url = f"{base_url}/system_information.fcgi"
            response = await client.post(
                info_url,
                params={"session": session}
            )
            
            if response.status_code == 200:
                info = response.json()
                print("✅ Informações do sistema obtidas:")
                print(f"   📱 Versão: {info.get('version', 'N/A')}")
                print(f"   🆔 Device ID: {info.get('device_id', 'N/A')}")
                print(f"   🌐 IP: {info.get('network', {}).get('ip', 'N/A')}")
                print(f"   🔌 Online: {info.get('online', False)}")
                
                # Uptime
                uptime = info.get('uptime', {})
                print(f"   ⏱️  Uptime: {uptime.get('days', 0)}d {uptime.get('hours', 0)}h {uptime.get('minutes', 0)}m")
            else:
                print(f"⚠️  Erro ao obter informações: {response.status_code}")
            
            # Teste 3: Verificar sessão
            print("\n3️⃣ Verificando validade da sessão...")
            check_url = f"{base_url}/session_is_valid.fcgi"
            response = await client.post(
                check_url,
                params={"session": session}
            )
            
            if response.status_code == 200:
                valid = response.json().get("session_is_valid", False)
                if valid:
                    print("✅ Sessão válida!")
                else:
                    print("⚠️  Sessão inválida")
            
            # Teste 4: Logout
            print("\n4️⃣ Fazendo logout...")
            logout_url = f"{base_url}/logout.fcgi"
            response = await client.post(
                logout_url,
                params={"session": session}
            )
            
            if response.status_code == 200:
                print("✅ Logout realizado com sucesso!")
            
            print("\n" + "=" * 50)
            print("✅ TODOS OS TESTES PASSARAM!")
            print("=" * 50)
            
    except httpx.ConnectError:
        print("\n❌ ERRO DE CONEXÃO!")
        print(f"Não foi possível conectar ao leitor em {IDFACE_IP}")
        print("\n🔧 Verifique:")
        print("   1. O leitor está ligado?")
        print("   2. O cabo de rede está conectado?")
        print("   3. O IP está correto? (169.254.111.129)")
        print("   4. Seu PC está na mesma rede?")
        print("      - Configure IP manual: 169.254.111.x")
        print("      - Máscara: 255.255.255.0")
        print("      - Gateway: 169.254.111.254")
        
    except httpx.TimeoutException:
        print("\n⏱️ TIMEOUT!")
        print("O leitor não respondeu em 10 segundos")
        
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("   TESTE DE CONEXÃO - iDFace Control ID")
    print("=" * 50)
    print(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    asyncio.run(test_connection())