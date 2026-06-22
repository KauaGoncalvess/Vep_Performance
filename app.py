import os
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_bcrypt import Bcrypt
from database import init_db, get_db, USE_POSTGRES
from datetime import datetime, timedelta, timezone
from collections import OrderedDict
from dotenv import load_dotenv
import requests
import secrets

load_dotenv()

app = Flask(__name__)
if not os.environ.get('SECRET_KEY'):
    logging.warning("SECRET_KEY nao configurada — sessoes serao invalidadas a cada restart")
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') != 'development'

csrf = CSRFProtect(app)
bcrypt = Bcrypt(app)

EVOLUTION_API_URL  = os.environ.get('EVOLUTION_API_URL', '')
EVOLUTION_API_KEY  = os.environ.get('EVOLUTION_API_KEY', '')
EVOLUTION_INSTANCE = os.environ.get('EVOLUTION_INSTANCE', 'vep_performance')
WHATSAPP_MECANICO  = os.environ.get('WHATSAPP_MECANICO', '5531994572780')

HORARIOS = {
    0: {'inicio': 18, 'fim': 22},
    1: {'inicio': 18, 'fim': 22},
    2: {'inicio': 18, 'fim': 22},
    3: {'inicio': 18, 'fim': 22},
    4: {'inicio': 18, 'fim': 22},
    5: {'inicio': 8,  'fim': 17},
}
DURACAO_SLOT = 60

FERIADOS = [
    '2025-01-01','2025-04-18','2025-04-21','2025-05-01','2025-06-19',
    '2025-09-07','2025-10-12','2025-11-02','2025-11-15','2025-11-20','2025-12-25',
    '2026-01-01','2026-04-03','2026-04-21','2026-05-01','2026-06-04',
    '2026-09-07','2026-10-12','2026-11-02','2026-11-15','2026-11-20','2026-12-25'
]

STATUS_VALIDOS = ['confirmado', 'aguardando', 'concluido', 'cancelado', 'remarcado']

# ── Limite de tentativas de login ──
MAX_TENTATIVAS = 5
JANELA_BLOQUEIO_MIN = 15

init_db()

PH = '%s' if USE_POSTGRES else '?'
FUSO_BRASILIA = timezone(timedelta(hours=-3))

def agora_br():
    return datetime.now(FUSO_BRASILIA).replace(tzinfo=None)

@app.context_processor
def inject_csrf():
    return dict(csrf_token=generate_csrf)

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

def query(sql, params=(), fetchone=False, fetchall=False, commit=False):
    conn = get_db()
    cur = None
    try:
        if USE_POSTGRES:
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(sql, params)
        result = None
        if fetchone:
            result = cur.fetchone()
            if result and not USE_POSTGRES:
                result = dict(result)
        elif fetchall:
            rows = cur.fetchall()
            if rows and not USE_POSTGRES:
                result = [dict(r) for r in rows]
            else:
                result = rows
        if commit:
            conn.commit()
        return result
    finally:
        if cur is not None:
            cur.close()
        conn.close()

def enviar_whatsapp(numero, mensagem):
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY:
        logging.warning("WhatsApp nao configurado — EVOLUTION_API_URL ou EVOLUTION_API_KEY ausente")
        return False
    try:
        url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
        headers = {"Content-Type": "application/json", "apikey": EVOLUTION_API_KEY}
        response = requests.post(url, json={"number": numero, "text": mensagem}, headers=headers, timeout=10)
        if response.status_code != 200:
            logging.error("WhatsApp API retornou status %d para numero %s", response.status_code, numero)
        return response.status_code == 200
    except Exception as e:
        logging.error("Erro ao enviar WhatsApp para %s: %s", numero, e)
        return False

def gerar_slots_disponiveis(data_str, ignorar_id=None):
    try:
        data = datetime.strptime(data_str, "%Y-%m-%d").date()
        hoje = agora_br().date()
        if data < hoje:
            return []
        dia_semana = data.weekday()
        if dia_semana == 6 or data_str in FERIADOS:
            return []
        horario = HORARIOS.get(dia_semana)
        if not horario:
            return []

        if ignorar_id:
            ocupados = query(
                f"SELECT horario FROM agendamentos WHERE data = {PH} AND status NOT IN ('cancelado','remarcado') AND id != {PH}",
                (data_str, ignorar_id), fetchall=True
            )
        else:
            ocupados = query(
                f"SELECT horario FROM agendamentos WHERE data = {PH} AND status NOT IN ('cancelado','remarcado')",
                (data_str,), fetchall=True
            )
        horarios_ocupados = [r['horario'] for r in (ocupados or [])]

        slots = []
        hora = horario['inicio']
        while hora < horario['fim']:
            slot = f"{hora:02d}:00"
            if slot not in horarios_ocupados:
                if data == hoje:
                    slot_dt = datetime.combine(data, datetime.strptime(slot, "%H:%M").time())
                    if slot_dt > agora_br() + timedelta(hours=1):
                        slots.append(slot)
                else:
                    slots.append(slot)
            hora += DURACAO_SLOT // 60
        return slots
    except Exception as e:
        logging.error("Erro ao gerar slots para %s: %s", data_str, e)
        return []

def registrar_historico(agendamento_id, campo, valor_antigo, valor_novo):
    query(
        f"INSERT INTO agendamento_historico (agendamento_id, campo, valor_antigo, valor_novo, alterado_em) VALUES ({PH},{PH},{PH},{PH},{PH})",
        (agendamento_id, campo, str(valor_antigo), str(valor_novo), agora_br().isoformat()),
        commit=True
    )

# ════════════════════════════════════════════
# ROTAS PÚBLICAS
# ════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    try:
        query("SELECT 1", fetchone=True)
        return jsonify({"status": "ok"})
    except Exception:
        return jsonify({"status": "error", "detail": "database unreachable"}), 503

@app.route('/api/slots')
def api_slots():
    data = request.args.get('data', '')
    return jsonify(gerar_slots_disponiveis(data) if data else [])

@app.route('/agendar', methods=['POST'])
def agendar():
    try:
        nome     = request.form.get('nome', '').strip()
        telefone = request.form.get('telefone', '').strip()
        servico  = request.form.get('servico', '').strip()
        data     = request.form.get('data', '').strip()
        horario  = request.form.get('horario', '').strip()
        modelo   = request.form.get('modelo_moto', '').strip()
        obs      = request.form.get('observacao', '').strip()

        if not all([nome, telefone, servico, data, horario]):
            return jsonify({'sucesso': False, 'erro': 'Preencha todos os campos obrigatórios.'})

        if horario not in gerar_slots_disponiveis(data):
            return jsonify({'sucesso': False, 'erro': 'Horário não disponível. Escolha outro.'})

        agora = agora_br().isoformat()
        query(
            f"""INSERT INTO agendamentos (nome, telefone, servico, data, horario, modelo_moto, observacao, status, criado_em, atualizado_em)
               VALUES ({PH},{PH},{PH},{PH},{PH},{PH},{PH},'confirmado',{PH},{PH})""",
            (nome, telefone, servico, data, horario, modelo, obs, agora, agora),
            commit=True
        )

        data_fmt = datetime.strptime(data, "%Y-%m-%d").strftime("%d/%m/%Y")
        num = '55' + telefone.replace('(','').replace(')','').replace('-','').replace(' ','')

        enviar_whatsapp(num,
            f"✅ *Agendamento confirmado, {nome}!*\n\n"
            f"🔧 Serviço: {servico}\n🏍️ Moto: {modelo or 'Não informado'}\n"
            f"📅 Data: {data_fmt}\n🕐 Horário: {horario}\n\n"
            f"📍 R. Walter de Almeida Jardim, 141 – Verde Vale, Sete Lagoas\n\nQualquer dúvida, chame a gente! 🤙"
        )
        enviar_whatsapp(WHATSAPP_MECANICO,
            f"🔔 *Novo agendamento!*\n\n👤 {nome}\n📱 {telefone}\n"
            f"🔧 {servico}\n🏍️ {modelo or 'Não informada'}\n"
            f"📅 {data_fmt} às {horario}\n📝 {obs or 'Sem observação'}"
        )
        return jsonify({'sucesso': True})

    except Exception as e:
        logging.error("Erro ao criar agendamento: %s", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno. Tente novamente.'})

# ════════════════════════════════════════════
# AUTENTICAÇÃO ADMIN
# ════════════════════════════════════════════

def admin_logado():
    return session.get('admin_id') is not None

def checar_bloqueio(email):
    """Retorna minutos restantes de bloqueio, ou 0 se liberado."""
    limite = (agora_br() - timedelta(minutes=JANELA_BLOQUEIO_MIN)).isoformat()
    tentativas = query(
        f"SELECT sucesso, tentado_em FROM login_tentativas WHERE email = {PH} AND tentado_em > {PH} ORDER BY tentado_em DESC",
        (email, limite), fetchall=True
    ) or []
    falhas_seguidas = 0
    ultima_tentativa = None
    for t in tentativas:
        if bool(t['sucesso']):
            break
        falhas_seguidas += 1
        ultima_tentativa = t['tentado_em']

    if falhas_seguidas >= MAX_TENTATIVAS and ultima_tentativa:
        liberado_em = datetime.fromisoformat(ultima_tentativa) + timedelta(minutes=JANELA_BLOQUEIO_MIN)
        restante = (liberado_em - agora_br()).total_seconds() / 60
        if restante > 0:
            return round(restante)
    return 0

def registrar_tentativa(email, sucesso):
    query(
        f"INSERT INTO login_tentativas (email, sucesso, tentado_em) VALUES ({PH},{PH},{PH})",
        (email, sucesso, agora_br().isoformat()),
        commit=True
    )

@app.route('/admin')
def admin_login():
    if admin_logado():
        return redirect(url_for('admin_painel'))
    return render_template('admin_login.html')

@app.route('/admin/entrar', methods=['POST'])
def admin_entrar():
    email = request.form.get('email', '').strip().lower()
    senha = request.form.get('senha', '').strip()

    if not email or not senha:
        return render_template('admin_login.html', erro='Preencha email e senha.')

    minutos_bloqueio = checar_bloqueio(email)
    if minutos_bloqueio > 0:
        return render_template('admin_login.html', erro=f'Muitas tentativas falhas. Tente novamente em {minutos_bloqueio} min.')

    usuario = query(f"SELECT * FROM admin_users WHERE email = {PH}", (email,), fetchone=True)

    if usuario and bcrypt.check_password_hash(usuario['senha_hash'], senha):
        registrar_tentativa(email, True if USE_POSTGRES else 1)
        session.clear()
        session['admin_id'] = usuario['id']
        session['admin_nome'] = usuario['nome']
        return redirect(url_for('admin_painel'))

    registrar_tentativa(email, False if USE_POSTGRES else 0)
    return render_template('admin_login.html', erro='Email ou senha incorretos.')

@app.route('/admin/sair', methods=['GET', 'POST'])
def admin_sair():
    session.clear()
    return redirect(url_for('admin_login'))

# ════════════════════════════════════════════
# PAINEL ADMIN — CRUD
# ════════════════════════════════════════════

@app.route('/admin/painel')
def admin_painel():
    if not admin_logado():
        return redirect(url_for('admin_login'))

    busca = request.args.get('busca', '').strip()
    status_filtro = request.args.get('status', '').strip()
    try:
        pagina = max(1, int(request.args.get('pagina', 1)))
    except (ValueError, TypeError):
        pagina = 1
    por_pagina = 20

    where = []
    params = []
    if busca:
        if USE_POSTGRES:
            where.append(f"(nome ILIKE {PH} OR telefone ILIKE {PH})")
        else:
            where.append(f"(nome LIKE {PH} OR telefone LIKE {PH})")
        params += [f"%{busca}%", f"%{busca}%"]
    if status_filtro and status_filtro in STATUS_VALIDOS:
        where.append(f"status = {PH}")
        params.append(status_filtro)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    total_row = query(f"SELECT COUNT(*) as total FROM agendamentos {where_sql}", tuple(params), fetchone=True)
    total = total_row['total'] if total_row else 0

    offset = (pagina - 1) * por_pagina
    rows = query(
        f"SELECT * FROM agendamentos {where_sql} ORDER BY data DESC, horario DESC LIMIT {PH} OFFSET {PH}",
        tuple(params) + (por_pagina, offset),
        fetchall=True
    ) or []

    por_data = OrderedDict()
    for ag in rows:
        d = ag['data']
        if d not in por_data:
            por_data[d] = []
        por_data[d].append(ag)

    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    return render_template(
        'admin_painel.html',
        por_data=por_data,
        busca=busca,
        status_filtro=status_filtro,
        status_validos=STATUS_VALIDOS,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
        admin_nome=session.get('admin_nome', '')
    )

@app.route('/admin/agendamento/<int:id>')
def admin_ver_agendamento(id):
    if not admin_logado():
        return jsonify({'erro': 'Não autorizado'}), 401
    ag = query(f"SELECT * FROM agendamentos WHERE id = {PH}", (id,), fetchone=True)
    if not ag:
        return jsonify({'erro': 'Agendamento não encontrado'}), 404
    return jsonify({'agendamento': ag})

@app.route('/admin/agendamento/<int:id>/editar', methods=['POST'])
def admin_editar_agendamento(id):
    if not admin_logado():
        return jsonify({'sucesso': False, 'erro': 'Não autorizado'}), 401

    ag_atual = query(f"SELECT * FROM agendamentos WHERE id = {PH}", (id,), fetchone=True)
    if not ag_atual:
        return jsonify({'sucesso': False, 'erro': 'Agendamento não encontrado.'})

    nome     = request.form.get('nome', '').strip()
    telefone = request.form.get('telefone', '').strip()
    servico  = request.form.get('servico', '').strip()
    data     = request.form.get('data', '').strip()
    horario  = request.form.get('horario', '').strip()
    obs      = request.form.get('observacao', '').strip()

    if not all([nome, telefone, servico, data, horario]):
        return jsonify({'sucesso': False, 'erro': 'Preencha todos os campos obrigatórios.'})

    # Se mudou data/horário, valida disponibilidade (ignorando o próprio registro)
    if data != ag_atual['data'] or horario != ag_atual['horario']:
        slots = gerar_slots_disponiveis(data, ignorar_id=id)
        if horario not in slots:
            return jsonify({'sucesso': False, 'erro': 'Novo horário não está disponível.'})

    campos = {
        'nome': nome, 'telefone': telefone, 'servico': servico,
        'data': data, 'horario': horario, 'observacao': obs
    }
    for campo, valor_novo in campos.items():
        valor_antigo = ag_atual.get(campo)
        if str(valor_antigo) != str(valor_novo):
            registrar_historico(id, campo, valor_antigo, valor_novo)

    query(
        f"""UPDATE agendamentos SET nome={PH}, telefone={PH}, servico={PH}, data={PH}, horario={PH}, observacao={PH}, atualizado_em={PH}
            WHERE id={PH}""",
        (nome, telefone, servico, data, horario, obs, agora_br().isoformat(), id),
        commit=True
    )
    return jsonify({'sucesso': True})

@app.route('/admin/agendamento/<int:id>/status', methods=['POST'])
def admin_status_agendamento(id):
    if not admin_logado():
        return jsonify({'sucesso': False, 'erro': 'Não autorizado'}), 401

    novo_status = request.form.get('status', '').strip()
    motivo = request.form.get('motivo', '').strip()

    if novo_status not in STATUS_VALIDOS:
        return jsonify({'sucesso': False, 'erro': 'Status inválido.'})

    ag_atual = query(f"SELECT * FROM agendamentos WHERE id = {PH}", (id,), fetchone=True)
    if not ag_atual:
        return jsonify({'sucesso': False, 'erro': 'Agendamento não encontrado.'})

    registrar_historico(id, 'status', ag_atual['status'], novo_status)

    if novo_status == 'cancelado':
        query(
            f"UPDATE agendamentos SET status={PH}, motivo_cancelamento={PH}, atualizado_em={PH} WHERE id={PH}",
            (novo_status, motivo, agora_br().isoformat(), id),
            commit=True
        )
    else:
        query(
            f"UPDATE agendamentos SET status={PH}, atualizado_em={PH} WHERE id={PH}",
            (novo_status, agora_br().isoformat(), id),
            commit=True
        )
    return jsonify({'sucesso': True})

# Mantido por compatibilidade (botão antigo de cancelar rápido)
@app.route('/admin/cancelar/<int:id>', methods=['POST'])
def admin_cancelar(id):
    if not admin_logado():
        return jsonify({'erro': 'Não autorizado'}), 401
    ag_atual = query(f"SELECT * FROM agendamentos WHERE id = {PH}", (id,), fetchone=True)
    if ag_atual:
        registrar_historico(id, 'status', ag_atual['status'], 'cancelado')
    query(f"UPDATE agendamentos SET status='cancelado', atualizado_em={PH} WHERE id = {PH}", (agora_br().isoformat(), id), commit=True)
    return jsonify({'sucesso': True})

@app.errorhandler(404)
def erro_404(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def erro_500(e):
    return render_template('500.html'), 500

# ════════════════════════════════════════════
# SETUP INICIAL — criar primeiro admin via navegador
# Protegido por chave secreta. REMOVER após o primeiro uso.
# ════════════════════════════════════════════
SETUP_KEY = os.environ.get('SETUP_KEY', '')

@app.route('/setup-admin', methods=['GET', 'POST'])
@csrf.exempt
def setup_admin():
    if not SETUP_KEY:
        return "Setup desativado.", 403

    if request.method == 'GET':
        return '''
        <html><body style="font-family:sans-serif;max-width:400px;margin:60px auto;">
        <h2>Criar admin inicial</h2>
        <form method="POST">
            <p><input name="chave" placeholder="Chave secreta" required style="width:100%;padding:8px"></p>
            <p><input name="nome" placeholder="Nome" required style="width:100%;padding:8px"></p>
            <p><input name="email" type="email" placeholder="Email" required style="width:100%;padding:8px"></p>
            <p><input name="senha" type="password" placeholder="Senha (min 8 caracteres)" required style="width:100%;padding:8px"></p>
            <button type="submit" style="padding:10px 20px">Criar</button>
        </form>
        </body></html>
        '''

    chave = request.form.get('chave', '')
    if chave != SETUP_KEY:
        return "Chave incorreta.", 403

    nome = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip().lower()
    senha = request.form.get('senha', '').strip()

    if not nome or not email or len(senha) < 8:
        return "Dados inválidos (senha precisa ter 8+ caracteres).", 400

    existente = query(f"SELECT id FROM admin_users WHERE email = {PH}", (email,), fetchone=True)
    if existente:
        return f"Já existe um admin com o email {email}. Use outro email ou apague esse no banco antes.", 400

    senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')
    query(
        f"INSERT INTO admin_users (nome, email, senha_hash, criado_em) VALUES ({PH},{PH},{PH},{PH})",
        (nome, email, senha_hash, agora_br().isoformat()),
        commit=True
    )
    return f"✅ Admin '{nome}' criado com sucesso! Email: {email}. Agora vá em /admin para entrar. IMPORTANTE: remova a variável SETUP_KEY da Render depois disso."

if __name__ == '__main__':
    app.run(debug=False, port=5000)
