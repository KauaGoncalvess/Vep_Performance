"""
Script para criar o usuário administrador inicial.
Rode UMA VEZ: python criar_admin.py
Depois pode apagar ou guardar em local seguro (não sobe pro GitHub).
"""
import os
import getpass
from datetime import datetime
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from database import init_db, get_db, USE_POSTGRES

load_dotenv()
bcrypt = Bcrypt()

PH = '%s' if USE_POSTGRES else '?'

def criar_admin():
    init_db()

    print("=== Criar usuário administrador ===\n")
    nome = input("Nome: ").strip()
    email = input("Email: ").strip().lower()
    senha = getpass.getpass("Senha (mín. 8 caracteres): ").strip()
    senha2 = getpass.getpass("Confirme a senha: ").strip()

    if not nome or not email or not senha:
        print("\nTodos os campos são obrigatórios.")
        return

    if senha != senha2:
        print("\nAs senhas não coincidem.")
        return

    if len(senha) < 8:
        print("\nA senha precisa ter pelo menos 8 caracteres.")
        return

    senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            f"INSERT INTO admin_users (nome, email, senha_hash, criado_em) VALUES ({PH},{PH},{PH},{PH})",
            (nome, email, senha_hash, datetime.now().isoformat())
        )
        conn.commit()
        print(f"\n✅ Administrador '{nome}' criado com sucesso. Use o email '{email}' para entrar em /admin")
    except Exception as e:
        print(f"\n❌ Erro ao criar admin (talvez o email já exista): {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    criar_admin()
