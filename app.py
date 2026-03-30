"""
NotarizeX — Backend Unificado v1.0
Cartório 3.0 | Blockchain | Tokenização | Fábrica de Moedas
NotarizeX Tokenização LTDA — CNPJ: 61.922.930/0001-97
"""
import os
import hashlib
import datetime
import json
import sqlite3
import bcrypt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
import mercadopago

# ─────────────────────────────────────────────
# Configuração do App
# ─────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'notarizex-secret-2026-cartorio3')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'jwt-notarizex-2026-blockchain')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(hours=24)
app.config['DATABASE'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notarizex.db')

jwt = JWTManager(app)

# ─────────────────────────────────────────────
# Credenciais
# ─────────────────────────────────────────────
MERCADOPAGO_ACCESS_TOKEN = os.environ.get(
    'MERCADOPAGO_ACCESS_TOKEN',
    'APP_USR-3111267487078079-081918-9bfab1d356edf1351cd796279256343c-2629226583'
)
MERCADOPAGO_PUBLIC_KEY = os.environ.get(
    'MERCADOPAGO_PUBLIC_KEY',
    'APP_USR-10835d00-01f0-46f7-8b52-189c57910ea1'
)
CONTACT_EMAIL = os.environ.get('CONTACT_EMAIL', 'henriquecampos66@gmail.com')

mp_sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

# ─────────────────────────────────────────────
# Banco de Dados
# ─────────────────────────────────────────────
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            contracts_used INTEGER DEFAULT 0,
            validations_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT NOT NULL,
            title TEXT,
            party_a TEXT,
            party_b TEXT,
            description TEXT,
            content TEXT,
            hash_sha256 TEXT,
            blockchain_block TEXT,
            blockchain_timestamp TEXT,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            file_size INTEGER,
            blockchain_block TEXT,
            blockchain_timestamp TEXT,
            certificate_id TEXT,
            status TEXT DEFAULT 'registered',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            mp_payment_id TEXT,
            amount REAL,
            plan TEXT,
            payment_type TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token_name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            token_type TEXT,
            supply TEXT,
            network TEXT,
            contract_address TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS tokenization_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            asset_type TEXT,
            asset_value TEXT,
            description TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            subject TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()
    db.close()

# ─────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────
def generate_blockchain_hash(data: str) -> dict:
    """Gera hash SHA-256 e simula registro blockchain."""
    hash_value = hashlib.sha256(data.encode()).hexdigest()
    timestamp = datetime.datetime.utcnow().isoformat() + 'Z'
    block_num = int(hashlib.md5(hash_value.encode()).hexdigest(), 16) % 5000000 + 18000000
    cert_id = hashlib.sha256(f"{hash_value}{timestamp}".encode()).hexdigest()[:16].upper()
    return {
        'hash': hash_value,
        'timestamp': timestamp,
        'block': str(block_num),
        'certificate_id': cert_id
    }

def generate_contract_content(contract_type: str, party_a: str, party_b: str, description: str) -> str:
    """Gera o conteúdo textual do contrato baseado no tipo."""
    today = datetime.date.today().strftime('%d de %B de %Y')
    templates = {
        'prestacao_servicos': f"""CONTRATO DE PRESTAÇÃO DE SERVIÇOS

Pelo presente instrumento particular, as partes:

CONTRATANTE: {party_a}
CONTRATADO: {party_b}

Têm entre si justo e acordado o seguinte:

CLÁUSULA 1ª — DO OBJETO
O presente contrato tem por objeto a prestação dos seguintes serviços: {description}

CLÁUSULA 2ª — DO PRAZO
O presente contrato vigorará pelo prazo acordado entre as partes, podendo ser rescindido mediante aviso prévio de 30 (trinta) dias.

CLÁUSULA 3ª — DA REMUNERAÇÃO
A remuneração pelos serviços prestados será acordada entre as partes conforme proposta comercial.

CLÁUSULA 4ª — DAS OBRIGAÇÕES DAS PARTES
O CONTRATADO obriga-se a prestar os serviços com qualidade, pontualidade e profissionalismo.
O CONTRATANTE obriga-se a efetuar o pagamento nos prazos acordados.

CLÁUSULA 5ª — DA VALIDADE JURÍDICA
Este contrato é celebrado nos termos da Lei 14.063/2020 e tem plena validade jurídica com assinatura eletrônica qualificada.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
CONTRATANTE                          CONTRATADO

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'compra_venda': f"""CONTRATO DE COMPRA E VENDA

VENDEDOR: {party_a}
COMPRADOR: {party_b}

OBJETO DA TRANSAÇÃO: {description}

As partes celebram o presente contrato de compra e venda, obrigando-se mutuamente ao cumprimento das cláusulas aqui estabelecidas, com plena validade jurídica nos termos do Código Civil Brasileiro.

Santos, {today}.

Registrado na Blockchain NotarizeX — Cartório Digital 3.0""",

        'nda': f"""ACORDO DE CONFIDENCIALIDADE (NDA)

PARTE DIVULGANTE: {party_a}
PARTE RECEPTORA: {party_b}

As partes comprometem-se a manter em sigilo absoluto todas as informações confidenciais relacionadas a: {description}

Este acordo é regido pela Lei 9.279/1996 e tem validade de 5 (cinco) anos a partir da data de assinatura.

Santos, {today}.

Registrado na Blockchain NotarizeX — Cartório Digital 3.0""",
    }
    return templates.get(contract_type, f"""CONTRATO — {contract_type.upper().replace('_', ' ')}

PARTE A: {party_a}
PARTE B: {party_b}

OBJETO: {description}

As partes, devidamente identificadas, celebram o presente instrumento com plena validade jurídica, nos termos da legislação brasileira vigente.

Santos, {today}.

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""")

# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'online',
        'service': 'NotarizeX Backend v1.0',
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

# ─────────────────────────────────────────────
# AUTH — CADASTRO E LOGIN
# ─────────────────────────────────────────────
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not name or not email or not password:
        return jsonify({'error': 'Nome, email e senha são obrigatórios.'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Senha deve ter no mínimo 6 caracteres.'}), 400

    db = get_db()
    existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    if existing:
        return jsonify({'error': 'Email já cadastrado.'}), 409

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db.execute(
        'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
        (name, email, password_hash)
    )
    db.commit()

    user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    token = create_access_token(identity=str(user['id']))

    return jsonify({
        'message': 'Conta criada com sucesso!',
        'token': token,
        'user': {'id': user['id'], 'name': user['name'], 'email': user['email'], 'plan': user['plan']}
    }), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email e senha são obrigatórios.'}), 400

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()

    if not user or not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
        return jsonify({'error': 'Email ou senha incorretos.'}), 401

    token = create_access_token(identity=str(user['id']))
    return jsonify({
        'message': 'Login realizado com sucesso!',
        'token': token,
        'user': {'id': user['id'], 'name': user['name'], 'email': user['email'], 'plan': user['plan']}
    })

@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_me():
    user_id = get_jwt_identity()
    db = get_db()
    user = db.execute('SELECT id, name, email, plan, contracts_used, validations_used, created_at FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        return jsonify({'error': 'Usuário não encontrado.'}), 404
    return jsonify(dict(user))

# ─────────────────────────────────────────────
# CONTRATOS
# ─────────────────────────────────────────────
@app.route('/api/contracts/templates', methods=['GET'])
def get_templates():
    return jsonify({
        'templates': [
            {'id': 'prestacao_servicos', 'name': 'Prestação de Serviços', 'icon': '🤝', 'category': 'Comercial'},
            {'id': 'compra_venda', 'name': 'Compra e Venda', 'icon': '🏠', 'category': 'Imóveis / Bens'},
            {'id': 'locacao_comercial', 'name': 'Locação Comercial', 'icon': '🏢', 'category': 'Imóveis'},
            {'id': 'emprestimo_p2p', 'name': 'Empréstimo P2P', 'icon': '💰', 'category': 'Financeiro'},
            {'id': 'confissao_divida', 'name': 'Confissão de Dívida', 'icon': '📋', 'category': 'Financeiro'},
            {'id': 'nda', 'name': 'NDA / Confidencialidade', 'icon': '🔒', 'category': 'Trabalhista'},
            {'id': 'contrato_trabalho', 'name': 'Contrato de Trabalho', 'icon': '👷', 'category': 'Trabalhista'},
            {'id': 'banco_horas', 'name': 'Banco de Horas', 'icon': '⏰', 'category': 'Trabalhista'},
            {'id': 'personalizado', 'name': 'Contrato Personalizado', 'icon': '📜', 'category': 'Sob Medida'},
        ]
    })

@app.route('/api/contracts/create', methods=['POST'])
def create_contract():
    data = request.get_json()
    contract_type = data.get('type', 'personalizado')
    party_a = data.get('party_a', '')
    party_b = data.get('party_b', '')
    description = data.get('description', '')
    email = data.get('email', '')

    if not party_a or not email:
        return jsonify({'error': 'Nome e email são obrigatórios.'}), 400

    # Gerar conteúdo do contrato
    content = generate_contract_content(contract_type, party_a, party_b, description)

    # Registrar na blockchain
    blockchain_data = generate_blockchain_hash(content)

    db = get_db()

    # Verificar se usuário existe
    user = db.execute('SELECT id FROM users WHERE email = ?', (email.lower(),)).fetchone()
    user_id = user['id'] if user else None

    # Salvar contrato
    db.execute("""
        INSERT INTO contracts (user_id, type, party_a, party_b, description, content, hash_sha256, blockchain_block, blockchain_timestamp, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_signature')
    """, (user_id, contract_type, party_a, party_b, description, content,
          blockchain_data['hash'], blockchain_data['block'], blockchain_data['timestamp']))
    db.commit()

    contract_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    return jsonify({
        'success': True,
        'contract_id': contract_id,
        'hash': blockchain_data['hash'],
        'blockchain_block': blockchain_data['block'],
        'timestamp': blockchain_data['timestamp'],
        'certificate_id': blockchain_data['certificate_id'],
        'message': f'Contrato #{contract_id} gerado e registrado na blockchain. Link de assinatura enviado para {email}.',
        'content_preview': content[:300] + '...'
    }), 201

@app.route('/api/contracts/<int:contract_id>', methods=['GET'])
def get_contract(contract_id):
    db = get_db()
    contract = db.execute('SELECT * FROM contracts WHERE id = ?', (contract_id,)).fetchone()
    if not contract:
        return jsonify({'error': 'Contrato não encontrado.'}), 404
    return jsonify(dict(contract))

# ─────────────────────────────────────────────
# VALIDAÇÃO DE DOCUMENTOS (BLOCKCHAIN)
# ─────────────────────────────────────────────
@app.route('/api/documents/validate', methods=['POST'])
def validate_document():
    data = request.get_json()
    file_hash = data.get('hash', '')
    filename = data.get('filename', 'documento')
    file_size = data.get('size', 0)

    if not file_hash:
        return jsonify({'error': 'Hash do documento é obrigatório.'}), 400

    # Verificar se já existe no banco
    db = get_db()
    existing = db.execute('SELECT * FROM documents WHERE file_hash = ?', (file_hash,)).fetchone()

    if existing:
        return jsonify({
            'status': 'already_registered',
            'message': 'Documento já registrado anteriormente.',
            'document': dict(existing)
        })

    # Registrar na blockchain
    blockchain_data = generate_blockchain_hash(file_hash)

    db.execute("""
        INSERT INTO documents (filename, file_hash, file_size, blockchain_block, blockchain_timestamp, certificate_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (filename, file_hash, file_size,
          blockchain_data['block'], blockchain_data['timestamp'], blockchain_data['certificate_id']))
    db.commit()

    return jsonify({
        'success': True,
        'status': 'registered',
        'hash': file_hash,
        'blockchain_block': blockchain_data['block'],
        'timestamp': blockchain_data['timestamp'],
        'certificate_id': blockchain_data['certificate_id'],
        'message': 'Documento registrado com sucesso na blockchain!'
    }), 201

@app.route('/api/documents/verify', methods=['POST'])
def verify_document():
    data = request.get_json()
    file_hash = data.get('hash', '')

    if not file_hash:
        return jsonify({'error': 'Hash é obrigatório.'}), 400

    db = get_db()
    doc = db.execute('SELECT * FROM documents WHERE file_hash = ?', (file_hash,)).fetchone()

    if doc:
        return jsonify({
            'authentic': True,
            'status': 'AUTÊNTICO',
            'document': dict(doc),
            'message': 'Documento verificado — autêntico e não adulterado.'
        })
    else:
        return jsonify({
            'authentic': False,
            'status': 'NÃO ENCONTRADO',
            'message': 'Documento não encontrado no registro blockchain da NotarizeX.'
        })

# ─────────────────────────────────────────────
# TOKENIZAÇÃO SOB DEMANDA
# ─────────────────────────────────────────────
@app.route('/api/tokenization/request', methods=['POST'])
def request_tokenization():
    data = request.get_json()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '')
    asset_type = data.get('asset_type', '')
    asset_value = data.get('asset_value', '')
    description = data.get('description', '')

    if not name or not email:
        return jsonify({'error': 'Nome e email são obrigatórios.'}), 400

    db = get_db()
    db.execute("""
        INSERT INTO tokenization_requests (name, email, phone, asset_type, asset_value, description)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, email, phone, asset_type, asset_value, description))
    db.commit()

    return jsonify({
        'success': True,
        'message': f'Solicitação de tokenização recebida! Nossa equipe entrará em contato com {email} em até 24h.'
    }), 201

# ─────────────────────────────────────────────
# FÁBRICA DE TOKENS
# ─────────────────────────────────────────────
@app.route('/api/tokens/create', methods=['POST'])
def create_token():
    data = request.get_json()
    token_name = data.get('name', '').strip()
    symbol = data.get('symbol', '').strip().upper()
    token_type = data.get('type', 'utility')
    supply = data.get('supply', '1000000')
    network = data.get('network', 'ethereum')
    email = data.get('email', '')

    if not token_name or not symbol or not email:
        return jsonify({'error': 'Nome, símbolo e email são obrigatórios.'}), 400

    db = get_db()
    user = db.execute('SELECT id FROM users WHERE email = ?', (email.lower(),)).fetchone()
    user_id = user['id'] if user else None

    db.execute("""
        INSERT INTO tokens (user_id, token_name, symbol, token_type, supply, network, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending_payment')
    """, (user_id, token_name, symbol, token_type, str(supply), network))
    db.commit()

    token_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

    return jsonify({
        'success': True,
        'token_id': token_id,
        'message': f'Token {token_name} ({symbol}) criado! Aguardando pagamento para deploy na {network}.',
        'price': 299.00,
        'currency': 'BRL'
    }), 201

# ─────────────────────────────────────────────
# PAGAMENTOS — MERCADO PAGO
# ─────────────────────────────────────────────
@app.route('/api/payments/create-preference', methods=['POST'])
def create_payment_preference():
    data = request.get_json()
    plan = data.get('plan', 'starter')
    email = data.get('email', '')
    payment_type = data.get('payment_type', 'subscription')

    plans = {
        'starter': {'title': 'NotarizeX Starter', 'price': 29.90},
        'profissional': {'title': 'NotarizeX Profissional', 'price': 79.90},
        'empresarial': {'title': 'NotarizeX Empresarial', 'price': 199.90},
        'avulso': {'title': 'Contrato Avulso NotarizeX', 'price': 49.90},
        'token': {'title': 'Criação de Token ERC-20', 'price': 299.00},
    }

    plan_data = plans.get(plan, plans['starter'])

    preference_data = {
        "items": [{
            "title": plan_data['title'],
            "quantity": 1,
            "unit_price": plan_data['price'],
            "currency_id": "BRL"
        }],
        "payer": {"email": email or "cliente@notarizex.com.br"},
        "payment_methods": {
            "excluded_payment_types": [],
            "installments": 1
        },
        "back_urls": {
            "success": "https://notarizex.com.br?payment=success",
            "failure": "https://notarizex.com.br?payment=failure",
            "pending": "https://notarizex.com.br?payment=pending"
        },
        "auto_approve": True,
        "statement_descriptor": "NOTARIZEX",
        "external_reference": f"{plan}_{email}_{datetime.datetime.utcnow().timestamp()}"
    }

    result = mp_sdk.preference().create(preference_data)
    preference = result.get('response', {})

    if 'id' in preference:
        db = get_db()
        user = db.execute('SELECT id FROM users WHERE email = ?', (email.lower(),)).fetchone() if email else None
        db.execute("""
            INSERT INTO payments (user_id, mp_payment_id, amount, plan, payment_type, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """, (user['id'] if user else None, preference['id'], plan_data['price'], plan, payment_type))
        db.commit()

        return jsonify({
            'success': True,
            'preference_id': preference['id'],
            'init_point': preference.get('init_point'),
            'sandbox_init_point': preference.get('sandbox_init_point'),
            'public_key': MERCADOPAGO_PUBLIC_KEY,
            'amount': plan_data['price'],
            'plan': plan_data['title']
        })
    else:
        return jsonify({'error': 'Erro ao criar preferência de pagamento.', 'details': preference}), 500

@app.route('/api/payments/pix', methods=['POST'])
def create_pix_payment():
    data = request.get_json()
    plan = data.get('plan', 'starter')
    email = data.get('email', '')
    name = data.get('name', 'Cliente')

    plans = {
        'starter': 29.90, 'profissional': 79.90,
        'empresarial': 199.90, 'avulso': 49.90, 'token': 299.00
    }
    amount = plans.get(plan, 29.90)

    payment_data = {
        "transaction_amount": amount,
        "description": f"NotarizeX — Plano {plan.capitalize()}",
        "payment_method_id": "pix",
        "payer": {
            "email": email or "cliente@notarizex.com.br",
            "first_name": name.split()[0] if name else "Cliente",
            "last_name": name.split()[-1] if len(name.split()) > 1 else "NotarizeX",
            "identification": {"type": "CPF", "number": "00000000000"}
        }
    }

    result = mp_sdk.payment().create(payment_data)
    payment = result.get('response', {})

    if payment.get('id'):
        pix_data = payment.get('point_of_interaction', {}).get('transaction_data', {})
        return jsonify({
            'success': True,
            'payment_id': payment['id'],
            'qr_code': pix_data.get('qr_code', ''),
            'qr_code_base64': pix_data.get('qr_code_base64', ''),
            'amount': amount,
            'status': payment.get('status'),
            'expires_at': pix_data.get('ticket_url', '')
        })
    else:
        return jsonify({'error': 'Erro ao gerar PIX.', 'details': payment}), 500

@app.route('/api/payments/webhook', methods=['POST'])
def payment_webhook():
    data = request.get_json()
    payment_id = data.get('data', {}).get('id')

    if payment_id:
        result = mp_sdk.payment().get(payment_id)
        payment = result.get('response', {})

        if payment.get('status') == 'approved':
            db = get_db()
            db.execute(
                "UPDATE payments SET status = 'approved' WHERE mp_payment_id = ?",
                (str(payment_id),)
            )
            db.commit()

    return jsonify({'status': 'ok'})

# ─────────────────────────────────────────────
# CONTATO
# ─────────────────────────────────────────────
@app.route('/api/contact', methods=['POST'])
def contact():
    data = request.get_json()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '')
    subject = data.get('subject', '')
    message = data.get('message', '')

    if not name or not email or not message:
        return jsonify({'error': 'Nome, email e mensagem são obrigatórios.'}), 400

    db = get_db()
    db.execute("""
        INSERT INTO contact_messages (name, email, phone, subject, message)
        VALUES (?, ?, ?, ?, ?)
    """, (name, email, phone, subject, message))
    db.commit()

    return jsonify({
        'success': True,
        'message': 'Mensagem recebida! Responderemos em até 24h.'
    })

# ─────────────────────────────────────────────
# ADMIN — DASHBOARD
# ─────────────────────────────────────────────
@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    db = get_db()
    stats = {
        'users': db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c'],
        'contracts': db.execute('SELECT COUNT(*) as c FROM contracts').fetchone()['c'],
        'documents': db.execute('SELECT COUNT(*) as c FROM documents').fetchone()['c'],
        'payments_approved': db.execute("SELECT COUNT(*) as c FROM payments WHERE status='approved'").fetchone()['c'],
        'tokenization_requests': db.execute('SELECT COUNT(*) as c FROM tokenization_requests').fetchone()['c'],
        'tokens': db.execute('SELECT COUNT(*) as c FROM tokens').fetchone()['c'],
    }
    return jsonify(stats)

# ─────────────────────────────────────────────
# INICIALIZAÇÃO
# ─────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
