#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import threading
from datetime import datetime
from flask import Flask, request, render_template_string
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
import requests
from functools import wraps

# ============================================
# CONFIGURATION
# ============================================
TELEGRAM_BOT_TOKEN = "8243669144:AAEGgOKla5rGQTgU5qLrcsBzhzVl5wb-LFA"
ADMIN_TELEGRAM_IDS = [7612692016]  # আপনার টেলিগ্রাম আইডি
MONETAG_ZONE = "10253210"
DATA_FILE = "database.json"

# Initialize Flask app
app = Flask(__name__)

# Initialize bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# ============================================
# JSON DATABASE HANDLER
# ============================================
class JSONDatabase:
    def __init__(self, filename):
        self.filename = filename
        self.lock = threading.Lock()
        self.init_db()
    
    def init_db(self):
        """Initialize database with default structure if not exists"""
        with self.lock:
            if not os.path.exists(self.filename):
                default_data = {
                    "users": [],
                    "daily_tasks": [],
                    "user_task_completions": [],
                    "tournaments": [],
                    "tournament_participants": [],
                    "tournament_selections": [],
                    "popups": [],
                    "about": [{"id": 1, "content": "Welcome to tunff09 Tournament Platform!", "image_url": "", "updated_at": datetime.now().isoformat()}],
                    "global_notice": [{"id": 1, "text": "Welcome to tunff09 Tournament Bot!", "updated_at": datetime.now().isoformat()}],
                    "support_contacts": [{"id": 1, "whatsapp": "+8801988006937", "telegram": "https://t.me/+m4TD15OINwU5MDc1", "updated_at": datetime.now().isoformat()}],
                    "settings": [{"id": 1, "daily_task_limit": 1, "allow_multiple_completions": False}],
                    "counters": {"user_id": 0, "task_id": 0, "tournament_id": 0, "popup_id": 0}
                }
                self._write_data(default_data)
    
    def _read_data(self):
        """Read data from JSON file"""
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.init_db()
            return self._read_data()
    
    def _write_data(self, data):
        """Write data to JSON file"""
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    # User operations
    def get_user_by_telegram_id(self, telegram_id):
        data = self._read_data()
        for user in data["users"]:
            if user["telegram_id"] == telegram_id:
                return user
        return None
    
    def get_user_by_id(self, user_id):
        data = self._read_data()
        for user in data["users"]:
            if user["id"] == user_id:
                return user
        return None
    
    def create_user(self, telegram_id, username, ff_name, phone):
        data = self._read_data()
        
        if self.get_user_by_telegram_id(telegram_id):
            return None
        
        data["counters"]["user_id"] += 1
        new_id = data["counters"]["user_id"]
        
        user = {
            "id": new_id,
            "telegram_id": telegram_id,
            "username": username,
            "ff_name": ff_name,
            "phone": phone,
            "coins": 100,
            "is_admin": 1 if telegram_id in ADMIN_TELEGRAM_IDS else 0,
            "created_at": datetime.now().isoformat()
        }
        
        data["users"].append(user)
        self._write_data(data)
        return user
    
    def update_user_coins(self, user_id, amount):
        data = self._read_data()
        for user in data["users"]:
            if user["id"] == user_id:
                user["coins"] += amount
                self._write_data(data)
                return user["coins"]
        return None
    
    def get_all_users(self):
        data = self._read_data()
        return data["users"]
    
    # Task operations
    def get_all_tasks(self):
        data = self._read_data()
        return data["daily_tasks"]
    
    def get_task_by_id(self, task_id):
        data = self._read_data()
        for task in data["daily_tasks"]:
            if task["id"] == task_id:
                return task
        return None
    
    def create_task(self, title, description, reward, max_views_per_user=1, is_one_time=0):
        data = self._read_data()
        data["counters"]["task_id"] += 1
        new_id = data["counters"]["task_id"]
        
        task = {
            "id": new_id,
            "title": title,
            "description": description,
            "reward": reward,
            "max_views_per_user": max_views_per_user,
            "is_one_time": is_one_time,
            "is_active": 1,
            "created_at": datetime.now().isoformat()
        }
        
        data["daily_tasks"].append(task)
        self._write_data(data)
        return task
    
    def delete_task(self, task_id):
        data = self._read_data()
        data["daily_tasks"] = [t for t in data["daily_tasks"] if t["id"] != task_id]
        data["user_task_completions"] = [c for c in data["user_task_completions"] if c["task_id"] != task_id]
        self._write_data(data)
        return True
    
    # Task completion
    def get_user_task_completions(self, user_id, task_id=None):
        data = self._read_data()
        completions = [c for c in data["user_task_completions"] if c["user_id"] == user_id]
        if task_id:
            completions = [c for c in completions if c["task_id"] == task_id]
        return completions
    
    def can_complete_task(self, user_id, task_id):
        task = self.get_task_by_id(task_id)
        if not task or not task["is_active"]:
            return False
        
        completions = self.get_user_task_completions(user_id, task_id)
        total_views = sum(c.get("view_count", 1) for c in completions)
        
        if task["is_one_time"] and len(completions) > 0:
            return False
        
        if total_views >= task["max_views_per_user"]:
            return False
        
        return True
    
    def complete_task(self, user_id, task_id):
        if not self.can_complete_task(user_id, task_id):
            return None
        
        task = self.get_task_by_id(task_id)
        if not task:
            return None
        
        data = self._read_data()
        
        completion = {
            "id": len(data["user_task_completions"]) + 1,
            "user_id": user_id,
            "task_id": task_id,
            "view_count": 1,
            "completed_at": datetime.now().isoformat()
        }
        data["user_task_completions"].append(completion)
        
        for user in data["users"]:
            if user["id"] == user_id:
                user["coins"] += task["reward"]
                break
        
        self._write_data(data)
        return task["reward"]
    
    # Tournament operations
    def get_all_tournaments(self, active_only=False):
        data = self._read_data()
        tournaments = data["tournaments"]
        if active_only:
            tournaments = [t for t in tournaments if t["status"] != "completed"]
        return sorted(tournaments, key=lambda x: x.get("start_time", ""), reverse=True)
    
    def get_tournament_by_id(self, tournament_id):
        data = self._read_data()
        for tournament in data["tournaments"]:
            if tournament["id"] == tournament_id:
                return tournament
        return None
    
    def create_tournament(self, name, tournament_type, map_name, entry_fee, max_players, prize_pool, start_time, rules="", image_url=""):
        data = self._read_data()
        data["counters"]["tournament_id"] += 1
        new_id = data["counters"]["tournament_id"]
        
        tournament = {
            "id": new_id,
            "name": name,
            "tournament_type": tournament_type,
            "map": map_name,
            "entry_fee": entry_fee,
            "max_players": max_players,
            "prize_pool": prize_pool,
            "start_time": start_time,
            "status": "upcoming",
            "rules": rules,
            "room_details": None,
            "image_url": image_url,
            "current_participants": 0,
            "created_at": datetime.now().isoformat()
        }
        
        data["tournaments"].append(tournament)
        self._write_data(data)
        return tournament
    
    def delete_tournament(self, tournament_id):
        data = self._read_data()
        data["tournaments"] = [t for t in data["tournaments"] if t["id"] != tournament_id]
        data["tournament_participants"] = [p for p in data["tournament_participants"] if p["tournament_id"] != tournament_id]
        self._write_data(data)
        return True
    
    def get_tournament_participants(self, tournament_id):
        data = self._read_data()
        participants = []
        for p in data["tournament_participants"]:
            if p["tournament_id"] == tournament_id:
                user = self.get_user_by_id(p["user_id"])
                if user:
                    participants.append({
                        **p,
                        "ff_name": user["ff_name"],
                        "username": user["username"],
                        "phone": user["phone"]
                    })
        return participants
    
    def join_tournament(self, user_id, tournament_id):
        tournament = self.get_tournament_by_id(tournament_id)
        if not tournament:
            return None
        
        user = self.get_user_by_id(user_id)
        if not user or user["coins"] < tournament["entry_fee"]:
            return None
        
        data = self._read_data()
        
        for p in data["tournament_participants"]:
            if p["tournament_id"] == tournament_id and p["user_id"] == user_id:
                return None
        
        for u in data["users"]:
            if u["id"] == user_id:
                u["coins"] -= tournament["entry_fee"]
                break
        
        participant = {
            "id": len(data["tournament_participants"]) + 1,
            "tournament_id": tournament_id,
            "user_id": user_id,
            "status": "joined",
            "selection_round": None,
            "joined_at": datetime.now().isoformat()
        }
        data["tournament_participants"].append(participant)
        
        for t in data["tournaments"]:
            if t["id"] == tournament_id:
                t["current_participants"] = len([p for p in data["tournament_participants"] if p["tournament_id"] == tournament_id])
                break
        
        self._write_data(data)
        return participant
    
    # Global settings
    def get_global_notice(self):
        data = self._read_data()
        return data["global_notice"][0] if data["global_notice"] else {"text": ""}
    
    def get_support_contacts(self):
        data = self._read_data()
        return data["support_contacts"][0] if data["support_contacts"] else {"whatsapp": "", "telegram": ""}
    
    def get_about(self):
        data = self._read_data()
        return data["about"][0] if data["about"] else {"content": "", "image_url": ""}
    
    # Backup
    def backup(self):
        return self._read_data()
    
    def restore(self, backup_data):
        with self.lock:
            self._write_data(backup_data)
        return True

# Initialize database
db = JSONDatabase(DATA_FILE)

# ============================================
# HELPER FUNCTIONS
# ============================================
def get_user(telegram_id):
    return db.get_user_by_telegram_id(telegram_id)

def create_user(telegram_id, username, ff_name, phone):
    return db.create_user(telegram_id, username, ff_name, phone)

def add_coins(user_id, amount):
    return db.update_user_coins(user_id, amount)

def can_complete_task(user_id, task_id):
    return db.can_complete_task(user_id, task_id)

def complete_task(user_id, task_id):
    return db.complete_task(user_id, task_id)

# ============================================
# TELEGRAM BOT HANDLERS
# ============================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = get_user(message.from_user.id)
    if user:
        markup = InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton("📋 Daily Tasks", callback_data="daily_tasks"),
            InlineKeyboardButton("🏆 Tournaments", callback_data="tournaments"),
            InlineKeyboardButton("👤 My Profile", callback_data="my_profile"),
            InlineKeyboardButton("ℹ️ About", callback_data="about")
        )
        
        if message.from_user.id in ADMIN_TELEGRAM_IDS:
            markup.add(InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"))
        
        bot.send_message(message.chat.id, 
                        f"🎮 *Welcome to tunff09!*\n\n"
                        f"👤 User: {user['ff_name']}\n"
                        f"💰 Coins: {user['coins']}\n\n"
                        "Select an option:",
                        parse_mode='Markdown', reply_markup=markup)
    else:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ Register", callback_data="register"))
        bot.send_message(message.chat.id, 
                        "🎮 *Welcome to tunff09 Tournament Bot!*\n\n"
                        "Please register to start earning coins and join tournaments.\n\n"
                        "🔥 *Features:*\n"
                        "• Complete daily tasks\n"
                        "• Join tournaments\n"
                        "• Win real prizes\n"
                        "• Watch ads for coins\n\n"
                        "Click the button below to register:",
                        parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "register":
        msg = bot.send_message(call.message.chat.id, "📝 *Registration*\n\nPlease enter your Free Fire name:", parse_mode='Markdown')
        bot.register_next_step_handler(msg, get_ff_name)
    
    elif call.data == "daily_tasks":
        show_daily_tasks(call.message)
    
    elif call.data == "tournaments":
        show_tournaments(call.message)
    
    elif call.data == "my_profile":
        show_profile(call.message)
    
    elif call.data == "about":
        show_about(call.message)
    
    elif call.data == "back_to_main":
        send_welcome(call.message)
    
    elif call.data.startswith("complete_task_"):
        task_id = int(call.data.split("_")[2])
        handle_task_completion(call.message, call.from_user.id, task_id)
    
    elif call.data.startswith("join_tournament_"):
        tournament_id = int(call.data.split("_")[2])
        handle_join_tournament(call.message, call.from_user.id, tournament_id)
    
    elif call.data == "admin_panel" and call.from_user.id in ADMIN_TELEGRAM_IDS:
        show_admin_panel(call.message)

def get_ff_name(message):
    ff_name = message.text
    msg = bot.send_message(message.chat.id, "📱 Please enter your WhatsApp number:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, get_phone, ff_name)

def get_phone(message, ff_name):
    phone = message.text
    user = create_user(message.from_user.id, message.from_user.username, ff_name, phone)
    if user:
        bot.send_message(message.chat.id, 
                        "✅ *Registration Successful!*\n\n"
                        f"Welcome {ff_name}!\n"
                        f"You've received 100 bonus coins!\n\n"
                        "Click /start to access the main menu.",
                        parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "❌ Registration failed. You might already be registered!")

def show_daily_tasks(message):
    tasks = db.get_all_tasks()
    tasks = [t for t in tasks if t["is_active"] == 1]
    
    if not tasks:
        bot.send_message(message.chat.id, "📭 No tasks available at the moment.")
        return
    
    user = get_user(message.from_user.id)
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    
    for task in tasks:
        if can_complete_task(user["id"], task["id"]):
            markup.add(InlineKeyboardButton(f"💰 {task['title']} (+{task['reward']} coins)", callback_data=f"complete_task_{task['id']}"))
        else:
            completions = db.get_user_task_completions(user["id"], task["id"])
            markup.add(InlineKeyboardButton(f"✅ {task['title']} (Completed)", callback_data="noop"))
    
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, 
                    "📋 *Daily Tasks*\n\n"
                    "Complete tasks to earn coins!\n\n"
                    "Click on a task to complete it:",
                    parse_mode='Markdown', reply_markup=markup)

def handle_task_completion(message, telegram_id, task_id):
    user = get_user(telegram_id)
    task = db.get_task_by_id(task_id)
    
    if not can_complete_task(user["id"], task_id):
        bot.send_message(message.chat.id, "❌ You've already completed this task!")
        return
    
    # Generate ad link
    ad_url = f"https://{request.host}/ad?task_id={task_id}&user_id={user['id']}&reward={task['reward']}"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎬 Watch Ad to Complete", url=ad_url))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="daily_tasks"))
    
    bot.send_message(message.chat.id, 
                    "🎬 *Complete Task*\n\n"
                    f"Click the button below to watch an ad.\n\n"
                    f"Reward: {task['reward']} coins",
                    parse_mode='Markdown', reply_markup=markup)

def show_tournaments(message):
    tournaments = db.get_all_tournaments(active_only=True)
    
    if not tournaments:
        bot.send_message(message.chat.id, "🏆 No active tournaments at the moment.")
        return
    
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    
    for t in tournaments:
        status_text = {"upcoming": "🟢 Upcoming", "ongoing": "🟡 Ongoing", "selection": "🔵 Selection"}.get(t["status"], "⚪")
        markup.add(InlineKeyboardButton(f"{status_text} {t['name']} (Entry: {t['entry_fee']} coins)", callback_data=f"join_tournament_{t['id']}"))
    
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, 
                    "🏆 *Active Tournaments*\n\n"
                    "Click on a tournament to see details and join:",
                    parse_mode='Markdown', reply_markup=markup)

def handle_join_tournament(message, telegram_id, tournament_id):
    user = get_user(telegram_id)
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not tournament:
        bot.send_message(message.chat.id, "Tournament not found!")
        return
    
    if tournament["status"] == 'completed':
        bot.send_message(message.chat.id, "This tournament has already ended!")
        return
    
    if user["coins"] < tournament["entry_fee"]:
        bot.send_message(message.chat.id, f"❌ You don't have enough coins!\nNeed: {tournament['entry_fee']} coins\nYou have: {user['coins']} coins")
        return
    
    participants = db.get_tournament_participants(tournament_id)
    if any(p["user_id"] == user["id"] for p in participants):
        bot.send_message(message.chat.id, "❌ You've already joined this tournament!")
        return
    
    result = db.join_tournament(user["id"], tournament_id)
    
    if result:
        bot.send_message(message.chat.id, 
                        f"✅ *Successfully joined {tournament['name']}!*\n\n"
                        f"📝 *Tournament Details:*\n"
                        f"Entry Fee: {tournament['entry_fee']} coins\n"
                        f"Prize Pool: {tournament['prize_pool']}\n\n"
                        f"{tournament['rules'] if tournament['rules'] else 'Rules will be announced soon.'}",
                        parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "❌ Failed to join tournament!")
    
    send_welcome(message)

def show_profile(message):
    user = get_user(message.from_user.id)
    
    tournaments_joined = len(db.get_tournament_participants(user["id"]))
    completions = db.get_user_task_completions(user["id"])
    tasks_completed = len(completions)
    
    profile_text = f"""
👤 *Profile*
━━━━━━━━━━━━━━━━
🎮 *Free Fire Name:* {user['ff_name']}
📱 *WhatsApp:* {user['phone']}
💰 *Total Coins:* {user['coins']}
🏆 *Tournaments Joined:* {tournaments_joined}
📋 *Tasks Completed:* {tasks_completed}
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, profile_text, parse_mode='Markdown', reply_markup=markup)

def show_about(message):
    about = db.get_about()
    notice = db.get_global_notice()
    support = db.get_support_contacts()
    
    text = f"""
ℹ️ *About tunff09*
━━━━━━━━━━━━━━━━
{about['content']}

📢 *Notice:*
{notice['text']}

📞 *Support:*
WhatsApp: {support['whatsapp']}
Telegram: {support['telegram']}
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

def show_admin_panel(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("📋 Manage Tasks", callback_data="admin_tasks"),
        InlineKeyboardButton("🏆 Manage Tournaments", callback_data="admin_tournaments"),
        InlineKeyboardButton("👥 Manage Users", callback_data="admin_users"),
        InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings"),
        InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
        InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")
    )
    
    bot.send_message(message.chat.id, "⚙️ *Admin Panel*\n\nSelect an option:", parse_mode='Markdown', reply_markup=markup)

# ============================================
# FLASK WEBHOOK ENDPOINTS
# ============================================
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json_string, bot)
        bot.process_new_updates([update])
        return 'ok', 200
    return 'bad request', 400

@app.route('/ad')
def serve_ad():
    task_id = request.args.get('task_id')
    user_id = request.args.get('user_id')
    reward = request.args.get('reward', '10')
    zone = MONETAG_ZONE
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Complete Task - tunff09</title>
        <script src='//libtl.com/sdk.js' data-zone='{{ zone }}' data-sdk='show_{{ zone }}'></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                font-family: Arial, sans-serif;
            }
            .card {
                background: rgba(255,255,255,0.95);
                border-radius: 30px;
                padding: 40px;
                text-align: center;
                max-width: 400px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 { color: #333; margin-bottom: 20px; }
            .reward { font-size: 48px; color: #10b981; font-weight: bold; margin: 20px 0; }
            button {
                background: #7c3aed;
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 50px;
                font-size: 18px;
                cursor: pointer;
                margin-top: 20px;
            }
            button:hover { background: #6d28d9; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🎬 Watch Ad</h1>
            <p>Complete this task to earn coins!</p>
            <div class="reward">+{{ reward }} Coins</div>
            <button onclick="watchAd()">Watch Ad Now</button>
        </div>
        <script>
            function watchAd() {
                show_{{ zone }}('pop').then(() => {
                    window.location.href = '/ad_complete?task_id={{ task_id }}&user_id={{ user_id }}';
                }).catch(e => {
                    alert('Error loading ad. Please try again.');
                });
            }
        </script>
    </body>
    </html>
    ''')

@app.route('/ad_complete')
def ad_complete():
    task_id = request.args.get('task_id')
    user_id = request.args.get('user_id')
    
    if task_id and user_id:
        reward = complete_task(int(user_id), int(task_id))
        if reward:
            return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        text-align: center;
                    }
                    .card {
                        background: rgba(255,255,255,0.95);
                        border-radius: 30px;
                        padding: 40px;
                    }
                    .success { color: #10b981; font-size: 64px; }
                    h1 { color: #333; }
                </style>
            </head>
            <body>
                <div class="card">
                    <div class="success">✅</div>
                    <h1>Task Completed!</h1>
                    <p>You earned +{{ reward }} coins!</p>
                    <p>You can close this window now.</p>
                </div>
                <script>setTimeout(() => window.close(), 3000);</script>
            </body>
            </html>
            ''')
    
    return "Invalid request"

@app.route('/')
def index():
    return "tunff09 Telegram Bot is running!"

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    # Initialize database
    db.init_db()
    print("✅ Database initialized")
    
    # Remove existing webhook
    bot.remove_webhook()
    print("✅ Old webhook removed")
    
    # Set new webhook
    render_url = os.environ.get('RENDER_EXTERNAL_URL', 'https://app-0fj5.onrender.com')
    webhook_url = f"{render_url}/webhook"
    bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook set to: {webhook_url}")
    
    # Start Flask app
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Starting server on port {port}")
    app.run(host='0.0.0.0', port=port)
