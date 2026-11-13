from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import smtplib
import os
import threading

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'app', 'templates'),
    static_folder=os.path.join(BASE_DIR, 'app', 'static'),
    static_url_path='/static'
)
app.secret_key = os.getenv('SECRET_KEY') or 'change-this-secret-key'

# ===== Rate limit: 10 сообщений / секунду с одного IP =====
RATE_LIMIT_COUNT = 1
RATE_LIMIT_SECONDS = 30
_rate_limit_store = defaultdict(list)
_rate_limit_lock = threading.Lock()


def get_client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def is_rate_limited(ip: str) -> bool:
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=RATE_LIMIT_SECONDS)

    with _rate_limit_lock:
        _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if t > window_start]
        if len(_rate_limit_store[ip]) >= RATE_LIMIT_COUNT:
            return True
        _rate_limit_store[ip].append(now)
        return False


def send_contact_email(name, email, phone, question, ip) -> bool:
    mail_server = os.getenv('MAIL_SERVER', 'smtp.yandex.ru')
    mail_port = int(os.getenv('MAIL_PORT', 587))
    mail_user = os.getenv('MAIL_USERNAME')
    mail_password = os.getenv('MAIL_PASSWORD')
    mail_from = os.getenv('MAIL_DEFAULT_SENDER') or mail_user
    mail_to = os.getenv('MAIL_RECEIVER') or mail_user

    if not mail_user or not mail_password:
        print('Почта не настроена: нет MAIL_USERNAME / MAIL_PASSWORD')
        return False

    subject = f'Новый вопрос с сайта от {name}'
    body = f"""Получено новое сообщение с сайта.

Имя: {name}
Email: {email}
Телефон: {phone or '—'}
IP: {ip}

Вопрос:
{question}
""".strip()

    msg = MIMEMultipart()
    msg['From'] = mail_from
    msg['To'] = mail_to
    msg['Subject'] = subject
    msg['Reply-To'] = email
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP(mail_server, mail_port, timeout=20) as server:
            server.starttls()
            server.login(mail_user, mail_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print('Ошибка отправки email:', repr(e))
        return False


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/products')
def products():
    return render_template('products.html')

@app.route('/ustanovki')
def ustanovki():
    return render_template('ustanovki.html')

@app.route('/sending')
def sending():
    return render_template('sending.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/submit_contact', methods=['POST'])
def submit_contact():
    ip = get_client_ip()

    if is_rate_limited(ip):
        return jsonify({
            'ok': False,
            'error': 'Слишком много запросов. Подождите немного.'
        }), 429

    name = (request.form.get('name') or '').strip()
    phone = (request.form.get('phone') or '').strip()
    email = (request.form.get('email') or '').strip()
    question = (request.form.get('question') or '').strip()
    consent = request.form.get('consent')

    if not name or not email or not question:
        return jsonify({
            'ok': False,
            'error': 'Пожалуйста, заполните все обязательные поля.'
        }), 400

    if not consent:
        return jsonify({
            'ok': False,
            'error': 'Нужно согласие на обработку персональных данных.'
        }), 400

    if len(name) > 100 or len(email) > 150 or len(question) > 3000:
        return jsonify({
            'ok': False,
            'error': 'Слишком длинные данные.'
        }), 400


    # Отправляем на почту
    email_sent = send_contact_email(name, email, phone, question, ip)

    if not email_sent:
        return jsonify({
            'ok': False,
            'error': 'Не удалось отправить сообщение. Попробуйте позже.'
        }), 500

    return jsonify({
        'ok': True,
        'message': 'Спасибо! Ваше сообщение отправлено.'
    })


if __name__ == '__main__':
    app.run(debug=True)