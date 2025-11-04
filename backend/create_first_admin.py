"""
Script para criar o primeiro admin do sistema
Salve como: backend/create_first_admin.py
Execute: python create_first_admin.py
"""
import asyncio
from app.database import db, connect_db, disconnect_db
import hashlib
import secrets
from datetime import datetime


def hash_password(password: str, salt: str) -> str:
    """Cria hash SHA256 da senha com salt"""
    combined = f"{password}{salt}"
    return hashlib.sha256(combined.encode()).hexdigest()


async def create_first_admin():
    """Cria o primeiro admin do sistema"""
    print("=" * 60)
    print("  🔐 CRIAR PRIMEIRO ADMINISTRADOR - iDFace Control System")
    print("=" * 60)
    
    # Conectar ao banco
    print("\n🔌 Conectando ao banco de dados...")
    try:
        await connect_db()
        print("✅ Conectado ao banco de dados")
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        return
    
    # Verificar se já existe algum admin
    print("\n🔍 Verificando admins existentes...")
    existing_admins = await db.admin.find_many()
    
    if existing_admins:
        print(f"\n⚠️  Encontrados {len(existing_admins)} admin(s) cadastrado(s):")
        for admin in existing_admins:
            status = "🟢 Ativo" if admin.active else "🔴 Inativo"
            print(f"   - {admin.username} (ID: {admin.id}) - {status}")
        
        print("\n" + "-" * 60)
        resposta = input("Deseja criar outro admin? (s/n): ").strip().lower()
        
        if resposta != 's':
            print("\n❌ Operação cancelada")
            await disconnect_db()
            return
    else:
        print("✅ Nenhum admin encontrado. Este será o primeiro!")
    
    # Solicitar dados
    print("\n" + "=" * 60)
    print("📝 DADOS DO NOVO ADMINISTRADOR")
    print("=" * 60)
    
    # Username
    while True:
        username = input("\n👤 Username (min 3 caracteres): ").strip()
        
        if len(username) < 3:
            print("❌ Username deve ter no mínimo 3 caracteres")
            continue
        
        # Verificar se username já existe
        check_user = await db.admin.find_first(where={"username": username})
        if check_user:
            print(f"❌ Já existe um admin com username '{username}'")
            continue
        
        break
    
    # Senha
    while True:
        password = input("🔑 Senha (min 6 caracteres): ").strip()
        
        if len(password) < 6:
            print("❌ Senha deve ter no mínimo 6 caracteres")
            continue
        
        # Confirmar senha
        password_confirm = input("🔑 Confirme a senha: ").strip()
        
        if password != password_confirm:
            print("❌ Senhas não conferem! Tente novamente.")
            continue
        
        break
    
    # Criar admin
    print("\n⏳ Criando administrador...")
    
    salt = secrets.token_hex(16)
    hashed_password = hash_password(password, salt)
    
    try:
        admin = await db.admin.create(
            data={
                "username": username,
                "password": hashed_password,
                "salt": salt,
                "active": True
            }
        )
        
        print("\n" + "=" * 60)
        print("✅ ADMIN CRIADO COM SUCESSO!")
        print("=" * 60)
        print(f"   🆔 ID: {admin.id}")
        print(f"   👤 Username: {admin.username}")
        print(f"   📊 Status: {'🟢 Ativo' if admin.active else '🔴 Inativo'}")
        print(f"   📅 Criado em: {admin.createdAt.strftime('%d/%m/%Y %H:%M:%S')}")
        print("=" * 60)
        
        print("\n💡 PRÓXIMOS PASSOS:")
        print("   1. Acesse: http://localhost:8000/docs")
        print("   2. Use o endpoint POST /api/v1/auth/login")
        print(f"   3. Credenciais: {username} / [sua senha]")
        print("\n   Ou teste via curl:")
        print(f"""
   curl -X POST http://localhost:8000/api/v1/auth/login \\
     -H "Content-Type: application/json" \\
     -d '{{"username": "{username}", "password": "[sua_senha]"}}'
        """)
        
    except Exception as e:
        print(f"\n❌ Erro ao criar admin: {e}")
    
    # Desconectar
    print("\n🔌 Desconectando do banco de dados...")
    await disconnect_db()
    print("✅ Desconectado\n")


async def list_admins():
    """Lista todos os admins cadastrados"""
    print("=" * 60)
    print("  📋 LISTA DE ADMINISTRADORES")
    print("=" * 60)
    
    await connect_db()
    
    admins = await db.admin.find_many(order_by={"username": "asc"})
    
    if not admins:
        print("\n⚠️  Nenhum administrador cadastrado")
    else:
        print(f"\n✅ Total: {len(admins)} admin(s)\n")
        
        for i, admin in enumerate(admins, 1):
            status = "🟢 Ativo" if admin.active else "🔴 Inativo"
            last_login = admin.lastLogin.strftime('%d/%m/%Y %H:%M') if admin.lastLogin else "Nunca"
            
            print(f"{i}. {admin.username}")
            print(f"   ID: {admin.id}")
            print(f"   Status: {status}")
            print(f"   Último Login: {last_login}")
            print(f"   Criado em: {admin.createdAt.strftime('%d/%m/%Y %H:%M')}")
            print()
    
    await disconnect_db()


async def delete_admin():
    """Deleta um admin"""
    print("=" * 60)
    print("  🗑️  DELETAR ADMINISTRADOR")
    print("=" * 60)
    
    await connect_db()
    
    # Listar admins
    admins = await db.admin.find_many(order_by={"username": "asc"})
    
    if not admins:
        print("\n⚠️  Nenhum administrador cadastrado")
        await disconnect_db()
        return
    
    print("\nAdmins cadastrados:")
    for i, admin in enumerate(admins, 1):
        status = "🟢" if admin.active else "🔴"
        print(f"   {i}. {status} {admin.username} (ID: {admin.id})")
    
    try:
        admin_id = int(input("\n🆔 Digite o ID do admin para deletar: "))
        
        admin = await db.admin.find_unique(where={"id": admin_id})
        
        if not admin:
            print(f"❌ Admin com ID {admin_id} não encontrado")
            await disconnect_db()
            return
        
        # Confirmar
        print(f"\n⚠️  Tem certeza que deseja deletar '{admin.username}'?")
        confirma = input("Digite 'DELETAR' para confirmar: ").strip()
        
        if confirma != "DELETAR":
            print("❌ Operação cancelada")
            await disconnect_db()
            return
        
        # Deletar
        await db.admin.delete(where={"id": admin_id})
        
        print(f"\n✅ Admin '{admin.username}' deletado com sucesso!")
        
    except ValueError:
        print("❌ ID inválido")
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    await disconnect_db()


async def menu():
    """Menu principal"""
    while True:
        print("\n" + "=" * 60)
        print("  🔐 GERENCIAMENTO DE ADMINISTRADORES")
        print("=" * 60)
        print("\n1. Criar novo admin")
        print("2. Listar admins")
        print("3. Deletar admin")
        print("0. Sair")
        
        opcao = input("\nEscolha uma opção: ").strip()
        
        if opcao == "1":
            await create_first_admin()
        elif opcao == "2":
            await list_admins()
        elif opcao == "3":
            await delete_admin()
        elif opcao == "0":
            print("\n👋 Até logo!\n")
            break
        else:
            print("❌ Opção inválida")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  iDFace Control System - Admin Manager")
    print("  Versão 1.0.0")
    print("=" * 60)
    
    try:
        asyncio.run(menu())
    except KeyboardInterrupt:
        print("\n\n⚠️  Operação cancelada pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro: {e}")