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

def _exec_safe(conn, cur, sql):
    try:
        cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()

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
                status TEXT DEFAULT 'aguardando',
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
        conn.commit()
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
                status TEXT DEFAULT 'aguardando',
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
        conn.commit()

    # Migração: garante colunas novas em bancos já existentes
    _exec_safe(conn, cur, "ALTER TABLE agendamentos ADD COLUMN motivo_cancelamento TEXT")
    _exec_safe(conn, cur, "ALTER TABLE agendamentos ADD COLUMN atualizado_em TEXT")

    # Índices para queries frequentes
    _exec_safe(conn, cur, "CREATE INDEX IF NOT EXISTS idx_agendamentos_data ON agendamentos (data)")
    _exec_safe(conn, cur, "CREATE INDEX IF NOT EXISTS idx_agendamentos_status ON agendamentos (status)")
    _exec_safe(conn, cur, "CREATE INDEX IF NOT EXISTS idx_agendamentos_data_status ON agendamentos (data, status)")
    _exec_safe(conn, cur, "CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users (email)")
    _exec_safe(conn, cur, "CREATE INDEX IF NOT EXISTS idx_historico_agendamento_id ON agendamento_historico (agendamento_id)")
    _exec_safe(conn, cur, "CREATE INDEX IF NOT EXISTS idx_login_tentativas_email ON login_tentativas (email, tentado_em)")

    cur.close()
    conn.close()
