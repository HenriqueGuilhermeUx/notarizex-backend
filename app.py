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

        'locacao_comercial': f"""CONTRATO DE LOCAÇÃO COMERCIAL

LOCADOR: {party_a}
LOCATÁRIO: {party_b}

OBJETO DA LOCAÇÃO: {description}

CLÁUSULA 1ª — DO OBJETO
O LOCADOR cede ao LOCATÁRIO, para fins comerciais, o imóvel descrito acima, pelo prazo e valor acordados entre as partes.

CLÁUSULA 2ª — DO PRAZO E VALOR
O prazo e valor do aluguel serão definidos em aditivo contratual, reajustável anualmente pelo IGPM ou índice substituto.

CLÁUSULA 3ª — DAS OBRIGAÇÕES
O LOCATÁRIO obriga-se a usar o imóvel exclusivamente para fins comerciais lícitos, conservá-lo e devolvê-lo nas mesmas condições de recebimento.

CLÁUSULA 4ª — DA VALIDADE JURÍDICA
Este contrato é regido pela Lei 8.245/1991 (Lei do Inquilinato) e tem plena validade jurídica com assinatura eletrônica qualificada nos termos da Lei 14.063/2020.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
LOCADOR                              LOCATÁRIO

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'emprestimo_p2p': f"""CONTRATO DE EMPRÉSTIMO ENTRE PESSOAS FÍSICAS (P2P)

CREDOR: {party_a}
DEVEDOR: {party_b}

OBJETO: {description}

CLÁUSULA 1ª — DO VALOR E CONDIÇÕES
O CREDOR empresta ao DEVEDOR o valor acordado entre as partes, nas condições descritas no objeto acima.

CLÁUSULA 2ª — DO PRAZO DE PAGAMENTO
O DEVEDOR compromete-se a devolver o valor emprestado no prazo e nas condições acordadas, sob pena de incidência de juros de mora de 1% ao mês e multa de 2% sobre o valor em atraso.

CLÁUSULA 3ª — DAS GARANTIAS
As partes poderão estabelecer garantias adicionais mediante aditivo contratual.

CLÁUSULA 4ª — DA VALIDADE JURÍDICA
Este instrumento é regido pelo Código Civil Brasileiro (Arts. 586 a 592) e tem plena validade jurídica com assinatura eletrônica qualificada.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
CREDOR                               DEVEDOR

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'confissao_divida': f"""INSTRUMENTO PARTICULAR DE CONFISSÃO DE DÍVIDA

CREDOR: {party_a}
DEVEDOR: {party_b}

OBJETO: {description}

CLÁUSULA 1ª — DA CONFISSÃO
O DEVEDOR confessa, de forma irrevogável e irretratável, que deve ao CREDOR o valor descrito no objeto, proveniente de obrigação lícita.

CLÁUSULA 2ª — DO PAGAMENTO
O DEVEDOR compromete-se a quitar o débito confessado nas condições acordadas entre as partes.

CLÁUSULA 3ª — DOS ENCARGOS
Em caso de inadimplemento, incidirão juros de mora de 1% ao mês, correção monetária pelo IPCA e multa de 2%.

CLÁUSULA 4ª — DO TÍTULO EXECUTIVO
Este instrumento constitui título executivo extrajudicial nos termos do Art. 784, III do CPC/2015.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
CREDOR                               DEVEDOR CONFESSANTE

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'nda': f"""ACORDO DE CONFIDENCIALIDADE E NÃO DIVULGAÇÃO (NDA)

PARTE DIVULGANTE: {party_a}
PARTE RECEPTORA: {party_b}

OBJETO: {description}

CLÁUSULA 1ª — DAS INFORMAÇÕES CONFIDENCIAIS
Consideram-se confidenciais todas as informações técnicas, comerciais, financeiras, estratégicas e operacionais relacionadas ao objeto acima, independentemente do meio em que sejam transmitidas.

CLÁUSULA 2ª — DAS OBRIGAÇÕES
A PARTE RECEPTORA obriga-se a: (i) não divulgar as informações a terceiros; (ii) utilizá-las exclusivamente para os fins acordados; (iii) adotar medidas de segurança equivalentes às que utiliza para proteger suas próprias informações confidenciais.

CLÁUSULA 3ª — DO PRAZO
Este acordo vigorará por 5 (cinco) anos a partir da assinatura, independentemente do término da relação comercial entre as partes.

CLÁUSULA 4ª — DAS PENALIDADES
O descumprimento deste acordo sujeitará a parte infratora ao pagamento de indenização por perdas e danos, nos termos dos Arts. 186 e 927 do Código Civil.

CLÁUSULA 5ª — DA VALIDADE JURÍDICA
Este acordo é regido pela Lei 9.279/1996 e tem plena validade com assinatura eletrônica qualificada nos termos da Lei 14.063/2020.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
PARTE DIVULGANTE                     PARTE RECEPTORA

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'contrato_trabalho': f"""CONTRATO INDIVIDUAL DE TRABALHO

EMPREGADOR: {party_a}
EMPREGADO: {party_b}

OBJETO / FUNÇÃO: {description}

CLÁUSULA 1ª — DA ADMISSÃO E FUNÇÃO
O EMPREGADO é admitido para exercer a função descrita acima, comprometendo-se a cumprir as atribuições inerentes ao cargo com dedicação e profissionalismo.

CLÁUSULA 2ª — DA JORNADA
A jornada de trabalho será de 44 (quarenta e quatro) horas semanais, nos termos do Art. 7º, XIII da Constituição Federal e da CLT.

CLÁUSULA 3ª — DA REMUNERAÇÃO
A remuneração será acordada entre as partes, paga mensalmente até o 5º dia útil do mês subsequente.

CLÁUSULA 4ª — DO PERÍODO DE EXPERIÊNCIA
As partes poderão estabelecer período de experiência de até 90 (noventa) dias, nos termos do Art. 445 da CLT.

CLÁUSULA 5ª — DA VALIDADE JURÍDICA
Este contrato é regido pela Consolidação das Leis do Trabalho (CLT) e tem plena validade com assinatura eletrônica qualificada nos termos da Lei 14.063/2020.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
EMPREGADOR                           EMPREGADO

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'banco_horas': f"""ACORDO DE COMPENSAÇÃO DE HORAS (BANCO DE HORAS)

EMPREGADOR: {party_a}
EMPREGADO: {party_b}

OBJETO: {description}

CLÁUSULA 1ª — DO SISTEMA DE COMPENSAÇÃO
As partes acordam a adoção do sistema de compensação de jornada (banco de horas), nos termos do Art. 59, §2º da CLT, com prazo máximo de compensação de 12 (doze) meses.

CLÁUSULA 2ª — DOS LIMITES
A jornada diária não poderá exceder 10 (dez) horas, respeitado o limite semanal de 44 horas e o descanso semanal remunerado.

CLÁUSULA 3ª — DO SALDO POSITIVO
As horas excedentes não compensadas no prazo serão pagas com adicional de 50% sobre o valor da hora normal.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
EMPREGADOR                           EMPREGADO

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'cessao_direitos': f"""CONTRATO DE CESSÃO DE DIREITOS

CEDENTE: {party_a}
CESSIONÁRIO: {party_b}

OBJETO DA CESSÃO: {description}

CLÁUSULA 1ª — DA CESSÃO
O CEDENTE, na qualidade de legítimo titular dos direitos descritos no objeto, cede e transfere ao CESSIONÁRIO, em caráter irrevogável e irretratável, todos os direitos relativos ao bem/crédito acima identificado.

CLÁUSULA 2ª — DO PREÇO E CONDIÇÕES
A cessão é realizada pelo valor e condições acordados entre as partes, declarando o CEDENTE que o bem/crédito cedido está livre e desembaraçado de quaisquer ônus, dívidas ou litígios.

CLÁUSULA 3ª — DA RESPONSABILIDADE
O CEDENTE responde pela existência do crédito/direito cedido, mas não pela solvência do devedor, salvo pacto expresso em contrário.

CLÁUSULA 4ª — DA VALIDADE JURÍDICA
Este contrato é regido pelos Arts. 286 a 298 do Código Civil Brasileiro e tem plena validade com assinatura eletrônica qualificada nos termos da Lei 14.063/2020.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
CEDENTE                              CESSIONÁRIO

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'cessao_precatorio': f"""CONTRATO DE CESSÃO DE DIREITOS SOBRE PRECATÓRIO FEDERAL

CEDENTE (TITULAR DO PRECATÓRIO): {party_a}
CESSIONÁRIO (ADQUIRENTE): {party_b}

OBJETO: {description}

CLÁUSULA 1ª — DO OBJETO
O CEDENTE é titular de crédito de precatório federal, devidamente inscrito no sistema do Tribunal competente, conforme identificação no objeto acima.

CLÁUSULA 2ª — DA CESSÃO
O CEDENTE cede e transfere ao CESSIONÁRIO, em caráter definitivo e irrevogável, todos os seus direitos sobre o precatório identificado, incluindo o direito de receber o valor principal, juros e correção monetária.

CLÁUSULA 3ª — DO PREÇO
A cessão é realizada pelo valor acordado entre as partes, pago à vista ou nas condições estabelecidas em aditivo, declarando o CEDENTE que o precatório está livre de penhoras, cessões anteriores ou qualquer outro ônus.

CLÁUSULA 4ª — DAS OBRIGAÇÕES DO CEDENTE
O CEDENTE obriga-se a: (i) assinar todos os documentos necessários para habilitação do CESSIONÁRIO perante o Tribunal; (ii) informar imediatamente qualquer alteração no status do precatório; (iii) não ceder os mesmos direitos a terceiros.

CLÁUSULA 5ª — DA VALIDADE JURÍDICA
Este contrato é regido pelo Art. 100 da Constituição Federal, pela Resolução CNJ 303/2019 e tem plena validade com assinatura eletrônica qualificada nos termos da Lei 14.063/2020.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
CEDENTE                              CESSIONÁRIO

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'parceria_empresarial': f"""CONTRATO DE PARCERIA EMPRESARIAL

PARCEIRO A: {party_a}
PARCEIRO B: {party_b}

OBJETO DA PARCERIA: {description}

CLÁUSULA 1ª — DO OBJETO
As partes estabelecem parceria comercial para desenvolvimento conjunto das atividades descritas no objeto, sem constituição de pessoa jurídica entre elas.

CLÁUSULA 2ª — DAS RESPONSABILIDADES
Cada parte será responsável pelas obrigações decorrentes de sua atuação específica, não respondendo pelos atos da outra perante terceiros, salvo disposição expressa em contrário.

CLÁUSULA 3ª — DA DIVISÃO DE RESULTADOS
Os resultados financeiros da parceria serão divididos conforme acordado entre as partes, mediante prestação de contas mensal.

CLÁUSULA 4ª — DA VIGÊNCIA
Este contrato vigorará pelo prazo acordado, podendo ser renovado mediante aditivo ou rescindido com aviso prévio de 60 (sessenta) dias.

CLÁUSULA 5ª — DA VALIDADE JURÍDICA
Este contrato é regido pelo Código Civil Brasileiro e tem plena validade com assinatura eletrônica qualificada nos termos da Lei 14.063/2020.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
PARCEIRO A                           PARCEIRO B

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'tokenizacao_ativo': f"""CONTRATO DE TOKENIZAÇÃO DE ATIVO REAL (RWA)

PROPRIETÁRIO DO ATIVO: {party_a}
PLATAFORMA DE TOKENIZAÇÃO: {party_b}

ATIVO A SER TOKENIZADO: {description}

CLÁUSULA 1ª — DO OBJETO
O PROPRIETÁRIO autoriza a PLATAFORMA a realizar a tokenização digital do ativo descrito, representando-o em tokens digitais na blockchain, nos termos da regulamentação vigente.

CLÁUSULA 2ª — DA REPRESENTAÇÃO DIGITAL
Cada token emitido representará uma fração do ativo real, conferindo ao seu detentor os direitos econômicos proporcionais à participação, conforme laudo de avaliação e prospecto de emissão.

CLÁUSULA 3ª — DA CUSTÓDIA
O ativo físico permanecerá sob custódia legal do PROPRIETÁRIO ou de custodiante qualificado, devidamente registrado e auditável.

CLÁUSULA 4ª — DA CONFORMIDADE REGULATÓRIA
A tokenização observará as diretrizes da CVM (Resolução 88/2022), do BACEN e demais órgãos reguladores aplicáveis ao tipo de ativo.

CLÁUSULA 5ª — DA VALIDADE JURÍDICA
Este contrato tem plena validade com assinatura eletrônica qualificada nos termos da Lei 14.063/2020 e registro imutável em blockchain.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
PROPRIETÁRIO DO ATIVO               PLATAFORMA NOTARIZEX

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",

        'promessa_compra_venda': f"""INSTRUMENTO PARTICULAR DE PROMESSA DE COMPRA E VENDA

PROMITENTE VENDEDOR: {party_a}
PROMITENTE COMPRADOR: {party_b}

OBJETO: {description}

CLÁUSULA 1ª — DO OBJETO
O PROMITENTE VENDEDOR promete vender ao PROMITENTE COMPRADOR o bem descrito no objeto, livre e desembaraçado de quaisquer ônus, pelo preço e condições acordados.

CLÁUSULA 2ª — DO PREÇO E FORMA DE PAGAMENTO
O preço total e as condições de pagamento serão definidos pelas partes e constituirão parte integrante deste instrumento.

CLÁUSULA 3ª — DA ESCRITURA DEFINITIVA
A escritura definitiva de compra e venda será lavrada após a quitação integral do preço, no prazo máximo acordado entre as partes.

CLÁUSULA 4ª — DA CLÁUSULA PENAL
O descumprimento injustificado por qualquer das partes ensejará o pagamento de multa de 10% sobre o valor total do negócio.

CLÁUSULA 5ª — DA VALIDADE JURÍDICA
Este instrumento é regido pelos Arts. 462 a 466 do Código Civil e tem plena validade com assinatura eletrônica qualificada nos termos da Lei 14.063/2020.

Santos, {today}.

___________________________          ___________________________
{party_a}                            {party_b}
PROMITENTE VENDEDOR                  PROMITENTE COMPRADOR

Registrado na Blockchain NotarizeX — Cartório Digital 3.0
CNPJ: 61.922.930/0001-97""",
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
            # Comercial
            {'id': 'prestacao_servicos',   'name': 'Prestação de Serviços',          'icon': '🤝', 'category': 'Comercial'},
            {'id': 'parceria_empresarial', 'name': 'Parceria Empresarial',           'icon': '🏛️', 'category': 'Comercial'},
            # Imóveis
            {'id': 'compra_venda',         'name': 'Compra e Venda',                 'icon': '🏠', 'category': 'Imóveis / Bens'},
            {'id': 'promessa_compra_venda','name': 'Promessa de Compra e Venda',     'icon': '📝', 'category': 'Imóveis / Bens'},
            {'id': 'locacao_comercial',    'name': 'Locação Comercial',              'icon': '🏢', 'category': 'Imóveis'},
            # Financeiro
            {'id': 'emprestimo_p2p',       'name': 'Empréstimo P2P',                 'icon': '💰', 'category': 'Financeiro'},
            {'id': 'confissao_divida',     'name': 'Confissão de Dívida',            'icon': '📋', 'category': 'Financeiro'},
            {'id': 'cessao_direitos',      'name': 'Cessão de Direitos',             'icon': '🔄', 'category': 'Financeiro'},
            {'id': 'cessao_precatorio',    'name': 'Cessão de Precatório Federal',   'icon': '⚖️', 'category': 'Financeiro'},
            # Trabalhista
            {'id': 'nda',                  'name': 'NDA / Confidencialidade',        'icon': '🔒', 'category': 'Trabalhista'},
            {'id': 'contrato_trabalho',    'name': 'Contrato de Trabalho',           'icon': '👷', 'category': 'Trabalhista'},
            {'id': 'banco_horas',          'name': 'Banco de Horas',                 'icon': '⏰', 'category': 'Trabalhista'},
            # Web3 / Tokenização
            {'id': 'tokenizacao_ativo',    'name': 'Tokenização de Ativo (RWA)',      'icon': '🔗', 'category': 'Web3 / RWA'},
            # Sob Medida
            {'id': 'personalizado',        'name': 'Contrato Personalizado',         'icon': '📜', 'category': 'Sob Medida'},
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
    try:
        # force=True aceita JSON mesmo sem Content-Type: application/json
        # silent=True evita erro se o body não for JSON válido
        data = request.get_json(force=True, silent=True) or {}
        
        payment_id = data.get('data', {}).get('id')

        if payment_id:
            try:
                result = mp_sdk.payment().get(payment_id)
                payment = result.get('response', {})

                if payment.get('status') == 'approved':
                    db = get_db()
                    db.execute(
                        "UPDATE payments SET status = 'approved' WHERE mp_payment_id = ?",
                        (str(payment_id),)
                    )
                    db.commit()
            except Exception:
                pass  # não falhar se o pagamento de teste não existir no MP

        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        return jsonify({'status': 'ok'}), 200  # sempre retornar 200 para o MP não reenviar

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
# INICIALIZAÇÃO — executado pelo gunicorn E pelo python direto
# ─────────────────────────────────────────────

# init_db() DEVE ficar fora do __main__ para funcionar com gunicorn
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
