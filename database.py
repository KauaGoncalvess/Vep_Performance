import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_POSTGRES = DATABASE_URL.startswith('postgres')

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        os.makedirs('instance', exist_ok=True)
        conn = sqlite3.connect('instance/vep.db')
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    if USE_POSTGRES:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agendamentos (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                telefone TEXT NOT NULL,
                servico TEXT NOT NULL,
                data TEXT NOT NULL,
                horario TEXT NOT NULL,
                modelo_moto TEXT,
                observacao TEXT,
                status TEXT DEFAULT 'confirmado',
                motivo_cancelamento TEXT,
                criado_em TEXT,
                atualizado_em TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                criado_em TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agendamento_historico (
                id SERIAL PRIMARY KEY,
                agendamento_id INTEGER NOT NULL,
                campo TEXT NOT NULL,
                valor_antigo TEXT,
                valor_novo TEXT,
                alterado_em TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS login_tentativas (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL,
                sucesso BOOLEAN,
                tentado_em TEXT
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agendamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                telefone TEXT NOT NULL,
                servico TEXT NOT NULL,
                data TEXT NOT NULL,
                horario TEXT NOT NULL,
                modelo_moto TEXT,
                observacao TEXT,
                status TEXT DEFAULT 'confirmado',
                motivo_cancelamento TEXT,
                criado_em TEXT,
                atualizado_em TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                criado_em TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agendamento_historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agendamento_id INTEGER NOT NULL,
                campo TEXT NOT NULL,
                valor_antigo TEXT,
                valor_novo TEXT,
                alterado_em TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS login_tentativas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                sucesso INTEGER,
                tentado_em TEXT
            )
        """)

    # Migração leve: garante colunas novas em bancos já existentes
    try:
        cur.execute("ALTER TABLE agendamentos ADD COLUMN motivo_cancelamento TEXT")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE agendamentos ADD COLUMN atualizado_em TEXT")
    except Exception:
        pass

    conn.commit()
    cur.close()
    conn.close()
    print(f"Banco {'PostgreSQL' if USE_POSTGRES else 'SQLite local'} inicializado.")
