from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# ယာယီ User စာရင်း
USERS = {
    "admin": "12345"
}

# 1. ပထမဆုံး ဝင်လာရင် index.html (Welcome / Splash Screen) ကို ပြမယ်
@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('chat')) # Login ဝင်ပြီးသားဆိုရင် Chat ကို တန်းသွားမယ်
    return render_template('index.html')

# 2. Login မျက်နှာပြင် (login.html) နှင့် Login စစ်ဆေးရန်
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('chat'))
        
    if request.method == 'POST':
        email = request.form.get('email') or request.form.get('username')
        
        if email:
            session['user'] = email
            return redirect(url_for('chat'))
        else:
            return render_template('login.html', error="ကျေးဇူးပြု၍ အချက်အလက်ဖြည့်ပါ")
            
    return render_template('login.html')

# 3. Login ဝင်ပြီးမှ မြင်ရမယ့် Chat စာမျက်နှာ (chat.html)
@app.route('/chat')
def chat():
    if 'user' not in session:
        return redirect(url_for('home'))
    return render_template('chat.html', user=session['user'])

# Logout လုပ်လျှင် Welcome (index.html) သို့ ပြန်သွားမည်
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
