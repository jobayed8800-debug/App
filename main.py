# main.py - Complete Flask application with Telegram bot using JSON storage
import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
import requests
from functools import wraps

app = Flask(__name__)

# Configuration - NEW TELEGRAM BOT TOKEN
TELEGRAM_BOT_TOKEN = "8505253868:AAG94UH2syVHFS_68BV3Mi25gucLVY1V9do"
ADMIN_TELEGRAM_IDS = [7612692016]  # Your admin Telegram ID
MONETAG_ZONE = "10253210"
DATA_FILE = "database.json"

# Get base URL from environment variable
BASE_URL = os.environ.get('BASE_URL', 'https://app-0fj5.onrender.com')

# Initialize bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# JSON Database Handler
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
        
        # Check if user already exists
        if self.get_user_by_telegram_id(telegram_id):
            return None
        
        # Generate new ID
        data["counters"]["user_id"] += 1
        new_id = data["counters"]["user_id"]
        
        user = {
            "id": new_id,
            "telegram_id": telegram_id,
            "username": username,
            "ff_name": ff_name,
            "phone": phone,
            "coins": 100,  # Bonus coins for new users
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
    
    def update_task(self, task_id, **kwargs):
        data = self._read_data()
        for task in data["daily_tasks"]:
            if task["id"] == task_id:
                task.update(kwargs)
                self._write_data(data)
                return task
        return None
    
    def delete_task(self, task_id):
        data = self._read_data()
        data["daily_tasks"] = [t for t in data["daily_tasks"] if t["id"] != task_id]
        # Also delete task completions
        data["user_task_completions"] = [c for c in data["user_task_completions"] if c["task_id"] != task_id]
        self._write_data(data)
        return True
    
    # Task completion operations
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
        
        # Add completion record
        completion = {
            "id": len(data["user_task_completions"]) + 1,
            "user_id": user_id,
            "task_id": task_id,
            "view_count": 1,
            "completed_at": datetime.now().isoformat()
        }
        data["user_task_completions"].append(completion)
        
        # Add coins to user
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
            "created_at": datetime.now().isoformat()
        }
        
        data["tournaments"].append(tournament)
        self._write_data(data)
        return tournament
    
    def update_tournament(self, tournament_id, **kwargs):
        data = self._read_data()
        for tournament in data["tournaments"]:
            if tournament["id"] == tournament_id:
                tournament.update(kwargs)
                self._write_data(data)
                return tournament
        return None
    
    def delete_tournament(self, tournament_id):
        data = self._read_data()
        data["tournaments"] = [t for t in data["tournaments"] if t["id"] != tournament_id]
        data["tournament_participants"] = [p for p in data["tournament_participants"] if p["tournament_id"] != tournament_id]
        data["tournament_selections"] = [s for s in data["tournament_selections"] if s["tournament_id"] != tournament_id]
        self._write_data(data)
        return True
    
    # Tournament participants
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
                        "phone": user["phone"],
                        "email": user.get("email", "")
                    })
        return participants
    
    def get_tournament_participants_by_user(self, user_id):
        """Get all tournaments a user has joined"""
        data = self._read_data()
        participants = []
        for p in data["tournament_participants"]:
            if p["user_id"] == user_id:
                tournament = self.get_tournament_by_id(p["tournament_id"])
                if tournament:
                    participants.append({
                        **p,
                        "tournament_name": tournament["name"],
                        "tournament_status": tournament["status"]
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
        
        # Check if already joined
        for p in data["tournament_participants"]:
            if p["tournament_id"] == tournament_id and p["user_id"] == user_id:
                return None
        
        # Deduct coins
        for u in data["users"]:
            if u["id"] == user_id:
                u["coins"] -= tournament["entry_fee"]
                break
        
        # Add participant
        participant = {
            "id": len(data["tournament_participants"]) + 1,
            "tournament_id": tournament_id,
            "user_id": user_id,
            "status": "joined",
            "selection_round": None,
            "joined_at": datetime.now().isoformat()
        }
        data["tournament_participants"].append(participant)
        
        # Update tournament participant count
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
    
    def update_global_notice(self, text):
        data = self._read_data()
        if data["global_notice"]:
            data["global_notice"][0]["text"] = text
            data["global_notice"][0]["updated_at"] = datetime.now().isoformat()
        else:
            data["global_notice"] = [{"id": 1, "text": text, "updated_at": datetime.now().isoformat()}]
        self._write_data(data)
        return True
    
    def get_support_contacts(self):
        data = self._read_data()
        return data["support_contacts"][0] if data["support_contacts"] else {"whatsapp": "", "telegram": ""}
    
    def update_support_contacts(self, whatsapp, telegram):
        data = self._read_data()
        if data["support_contacts"]:
            data["support_contacts"][0]["whatsapp"] = whatsapp
            data["support_contacts"][0]["telegram"] = telegram
            data["support_contacts"][0]["updated_at"] = datetime.now().isoformat()
        else:
            data["support_contacts"] = [{"id": 1, "whatsapp": whatsapp, "telegram": telegram, "updated_at": datetime.now().isoformat()}]
        self._write_data(data)
        return True
    
    def get_about(self):
        data = self._read_data()
        return data["about"][0] if data["about"] else {"content": "", "image_url": ""}
    
    def update_about(self, content, image_url=""):
        data = self._read_data()
        if data["about"]:
            data["about"][0]["content"] = content
            data["about"][0]["image_url"] = image_url
            data["about"][0]["updated_at"] = datetime.now().isoformat()
        else:
            data["about"] = [{"id": 1, "content": content, "image_url": image_url, "updated_at": datetime.now().isoformat()}]
        self._write_data(data)
        return True
    
    # Popup operations
    def get_all_popups(self):
        data = self._read_data()
        return data["popups"]
    
    def create_popup(self, image_url, link="", text=""):
        data = self._read_data()
        data["counters"]["popup_id"] += 1
        new_id = data["counters"]["popup_id"]
        
        popup = {
            "id": new_id,
            "image_url": image_url,
            "link": link,
            "text": text,
            "is_active": 1,
            "created_at": datetime.now().isoformat()
        }
        
        data["popups"].append(popup)
        self._write_data(data)
        return popup
    
    def delete_popup(self, popup_id):
        data = self._read_data()
        data["popups"] = [p for p in data["popups"] if p["id"] != popup_id]
        self._write_data(data)
        return True
    
    # Backup and restore
    def backup(self):
        return self._read_data()
    
    def restore(self, backup_data):
        with self.lock:
            self._write_data(backup_data)
        return True

# Initialize database
db = JSONDatabase(DATA_FILE)

# Helper functions
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

def get_task_reward(task_id):
    task = db.get_task_by_id(task_id)
    return task["reward"] if task else 0

# Admin decorator
def admin_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if message.from_user.id not in ADMIN_TELEGRAM_IDS:
            bot.send_message(message.chat.id, "❌ You don't have permission to access this!")
            return
        return func(message, *args, **kwargs)
    return wrapper

# Telegram bot handlers
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = get_user(message.from_user.id)
    if user:
        show_main_menu(message)
    else:
        markup = InlineKeyboardMarkup()
        markup.row_width = 1
        markup.add(InlineKeyboardButton("✅ Register Now", callback_data="register"))
        bot.send_message(message.chat.id, 
                        "🎮 *Welcome to tunff09 Tournament Bot!*\n\n"
                        "You are not registered yet. Please register to start earning coins and join tournaments.\n\n"
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
    elif call.data.startswith("complete_task_"):
        task_id = int(call.data.split("_")[2])
        handle_task_completion(call.message, call.from_user.id, task_id)
    elif call.data.startswith("join_tournament_"):
        tournament_id = int(call.data.split("_")[2])
        handle_join_tournament(call.message, call.from_user.id, tournament_id)
    elif call.data.startswith("confirm_join_"):
        tournament_id = int(call.data.split("_")[2])
        confirm_join_tournament(call, tournament_id)
    elif call.data == "daily_tasks":
        show_daily_tasks(call.message)
    elif call.data == "tournaments":
        show_tournaments(call.message)
    elif call.data == "my_profile":
        show_profile(call.message)
    elif call.data == "about":
        show_about(call.message)
    elif call.data.startswith("admin_"):
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            if call.data == "admin_panel":
                show_admin_panel(call.message)
            elif call.data == "admin_tasks":
                show_admin_tasks(call.message)
            elif call.data == "admin_tournaments":
                show_admin_tournaments(call.message)
            elif call.data == "admin_users":
                show_admin_users(call.message)
            elif call.data == "admin_settings":
                show_admin_settings(call.message)
            elif call.data == "admin_stats":
                show_admin_stats(call.message)
            elif call.data == "admin_backup":
                handle_admin_backup(call.message)
    elif call.data == "back_to_main":
        show_main_menu(call.message)
    elif call.data.startswith("delete_task_"):
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            task_id = int(call.data.split("_")[2])
            delete_task(call.message, task_id)
    elif call.data.startswith("delete_tournament_"):
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            tournament_id = int(call.data.split("_")[2])
            delete_tournament(call.message, tournament_id)
    elif call.data.startswith("set_task_limit_"):
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            task_id = int(call.data.split("_")[3])
            msg = bot.send_message(call.message.chat.id, "Enter max views per user:")
            bot.register_next_step_handler(msg, set_task_limit, task_id)
    elif call.data.startswith("toggle_one_time_"):
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            task_id = int(call.data.split("_")[3])
            toggle_one_time_task(call.message, task_id)
    elif call.data == "backup_data":
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            handle_admin_backup(call.message)
    elif call.data == "restore_data":
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            msg = bot.send_message(call.message.chat.id, "Send me the JSON backup file as a document:")
            bot.register_next_step_handler(msg, handle_restore_file)
    elif call.data == "add_task":
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            msg = bot.send_message(call.message.chat.id, "Enter task title:")
            bot.register_next_step_handler(msg, add_task_title)
    elif call.data == "add_tournament":
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            msg = bot.send_message(call.message.chat.id, "Enter tournament name:")
            bot.register_next_step_handler(msg, add_tournament_name)
    elif call.data == "add_coins_user":
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            msg = bot.send_message(call.message.chat.id, "Enter user Telegram ID or Free Fire name:")
            bot.register_next_step_handler(msg, add_coins_find_user)
    elif call.data == "user_rankings":
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            show_user_rankings(call)
    elif call.data == "edit_notice":
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            msg = bot.send_message(call.message.chat.id, "Enter new global notice text:")
            bot.register_next_step_handler(msg, update_notice)
    elif call.data == "edit_support":
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            msg = bot.send_message(call.message.chat.id, "Enter WhatsApp number (with country code):")
            bot.register_next_step_handler(msg, update_support_whatsapp)
    elif call.data == "edit_about":
        if call.from_user.id in ADMIN_TELEGRAM_IDS:
            msg = bot.send_message(call.message.chat.id, "Enter about page content:")
            bot.register_next_step_handler(msg, update_about)
    elif call.data == "noop":
        bot.answer_callback_query(call.id, "Task already completed!")

def get_ff_name(message):
    ff_name = message.text
    msg = bot.send_message(message.chat.id, "📱 Please enter your WhatsApp number (with country code):", parse_mode='Markdown')
    bot.register_next_step_handler(msg, get_phone, ff_name)

def get_phone(message, ff_name):
    phone = message.text
    user = create_user(message.from_user.id, message.from_user.username or "NoUsername", ff_name, phone)
    if user:
        bot.send_message(message.chat.id, 
                        "✅ *Registration Successful!*\n\n"
                        f"Welcome {ff_name}!\n"
                        f"You've received 100 bonus coins!\n\n"
                        "Click /start to access the main menu.",
                        parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "❌ Registration failed. You might already be registered!\n\nClick /start to try again.")

def show_main_menu(message):
    user = get_user(message.from_user.id)
    if not user:
        send_welcome(message)
        return
    
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
    
    # Get global notice
    notice = db.get_global_notice()
    notice_text = f"\n\n📢 *Notice:* {notice['text']}" if notice['text'] else ""
    
    bot.send_message(message.chat.id, 
                    f"🎮 *Main Menu*\n\n"
                    f"👤 User: {user['ff_name']}\n"
                    f"💰 Coins: {user['coins']}{notice_text}\n\n"
                    "Select an option:",
                    parse_mode='Markdown', reply_markup=markup)

def show_daily_tasks(message):
    tasks = db.get_all_tasks()
    tasks = [t for t in tasks if t["is_active"] == 1]
    
    if not tasks:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
        bot.send_message(message.chat.id, "📭 No tasks available at the moment.", reply_markup=markup)
        return
    
    user = get_user(message.from_user.id)
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    
    for task in tasks:
        if can_complete_task(user["id"], task["id"]):
            markup.add(InlineKeyboardButton(f"💰 {task['title']} (+{task['reward']} coins)", callback_data=f"complete_task_{task['id']}"))
        else:
            completions = db.get_user_task_completions(user["id"], task["id"])
            markup.add(InlineKeyboardButton(f"✅ {task['title']} (Completed {len(completions)}/{task['max_views_per_user']} times)", callback_data="noop"))
    
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, 
                    "📋 *Daily Tasks*\n\n"
                    "Complete tasks to earn coins!\n\n"
                    "Click on a task to complete it (requires watching an ad):",
                    parse_mode='Markdown', reply_markup=markup)

def handle_task_completion(message, telegram_id, task_id):
    user = get_user(telegram_id)
    if not can_complete_task(user["id"], task_id):
        bot.send_message(message.chat.id, "❌ You've already completed this task the maximum number of times!")
        return
    
    task = db.get_task_by_id(task_id)
    
    # Generate ad completion URL
    ad_url = f"{BASE_URL}/ad?task_id={task_id}&user_id={user['id']}&reward={task['reward']}"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎬 Watch Ad to Complete Task", url=ad_url))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="daily_tasks"))
    
    bot.send_message(message.chat.id, 
                    "🎬 *Complete Task*\n\n"
                    f"Click the button below to watch an ad.\n"
                    f"After watching the ad, you will automatically receive your reward.\n\n"
                    f"Reward: {task['reward']} coins",
                    parse_mode='Markdown', reply_markup=markup)

def show_tournaments(message):
    tournaments = db.get_all_tournaments(active_only=True)
    
    if not tournaments:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
        bot.send_message(message.chat.id, "🏆 No active tournaments at the moment.", reply_markup=markup)
        return
    
    user = get_user(message.from_user.id)
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    
    for t in tournaments:
        status_text = {"upcoming": "🟢 Upcoming", "ongoing": "🟡 Ongoing", "selection": "🔵 Selection"}.get(t["status"], "⚪")
        # Check if user already joined
        participants = db.get_tournament_participants(t["id"])
        already_joined = any(p["user_id"] == user["id"] for p in participants)
        joined_text = " ✅ Joined" if already_joined else ""
        markup.add(InlineKeyboardButton(f"{status_text} {t['name']} (Entry: {t['entry_fee']} coins){joined_text}", callback_data=f"join_tournament_{t['id']}"))
    
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, 
                    "🏆 *Active Tournaments*\n\n"
                    "Click on a tournament to see details and join:",
                    parse_mode='Markdown', reply_markup=markup)

def handle_join_tournament(message, telegram_id, tournament_id):
    user = get_user(telegram_id)
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not tournament:
        bot.send_message(message.chat.id, "❌ Tournament not found!")
        return
    
    if tournament["status"] == 'completed':
        bot.send_message(message.chat.id, "❌ This tournament has already ended!")
        return
    
    # Check if already joined
    participants = db.get_tournament_participants(tournament_id)
    if any(p["user_id"] == user["id"] for p in participants):
        # Show tournament details even if already joined
        details = f"""
🏆 *{tournament['name']}*
━━━━━━━━━━━━━━━━
📝 *Type:* {tournament['tournament_type']}
🗺️ *Map:* {tournament['map']}
💰 *Entry Fee:* {tournament['entry_fee']} coins
🏆 *Prize Pool:* {tournament['prize_pool']}
👥 *Players:* {len(participants)}/{tournament['max_players']}
📅 *Start Time:* {tournament['start_time']}
📊 *Status:* {tournament['status']}

📜 *Rules:*
{tournament['rules'] if tournament['rules'] else 'No specific rules.'}

✅ *You have already joined this tournament!*
"""
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back to Tournaments", callback_data="tournaments"))
        bot.send_message(message.chat.id, details, parse_mode='Markdown', reply_markup=markup)
        return
    
    if user["coins"] < tournament["entry_fee"]:
        bot.send_message(message.chat.id, f"❌ You don't have enough coins!\nNeed: {tournament['entry_fee']} coins\nYou have: {user['coins']} coins")
        return
    
    # Show tournament details and confirm join
    details = f"""
🏆 *{tournament['name']}*
━━━━━━━━━━━━━━━━
📝 *Type:* {tournament['tournament_type']}
🗺️ *Map:* {tournament['map']}
💰 *Entry Fee:* {tournament['entry_fee']} coins
🏆 *Prize Pool:* {tournament['prize_pool']}
👥 *Players:* {len(participants)}/{tournament['max_players']}
📅 *Start Time:* {tournament['start_time']}
📊 *Status:* {tournament['status']}

📜 *Rules:*
{tournament['rules'] if tournament['rules'] else 'No specific rules.'}

⚠️ *Confirm Join?*
Your coins will be deducted immediately.
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Confirm Join", callback_data=f"confirm_join_{tournament_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data="tournaments")
    )
    
    bot.send_message(message.chat.id, details, parse_mode='Markdown', reply_markup=markup)

def confirm_join_tournament(call, tournament_id):
    user = get_user(call.from_user.id)
    tournament = db.get_tournament_by_id(tournament_id)
    
    if not tournament or tournament["status"] == 'completed':
        bot.send_message(call.message.chat.id, "❌ Tournament no longer available!")
        return
    
    # Check again if already joined
    participants = db.get_tournament_participants(tournament_id)
    if any(p["user_id"] == user["id"] for p in participants):
        bot.send_message(call.message.chat.id, "❌ You've already joined this tournament!")
        return
    
    if user["coins"] < tournament["entry_fee"]:
        bot.send_message(call.message.chat.id, f"❌ You don't have enough coins!")
        return
    
    # Join tournament
    result = db.join_tournament(user["id"], tournament_id)
    
    if result:
        bot.send_message(call.message.chat.id, 
                        f"✅ *Successfully joined {tournament['name']}!*\n\n"
                        f"📝 *Tournament Details:*\n"
                        f"Entry Fee: {tournament['entry_fee']} coins\n"
                        f"Prize Pool: {tournament['prize_pool']}\n\n"
                        f"{tournament['rules'] if tournament['rules'] else 'Rules will be announced soon.'}\n\n"
                        f"Keep an eye on this bot for room details!",
                        parse_mode='Markdown')
    else:
        bot.send_message(call.message.chat.id, "❌ Failed to join tournament!")
    
    show_main_menu(call.message)

def show_profile(message):
    user = get_user(message.from_user.id)
    
    tournaments_joined = len(db.get_tournament_participants_by_user(user["id"]))
    completions = db.get_user_task_completions(user["id"])
    tasks_completed = len(completions)
    
    profile_text = f"""
👤 *My Profile*
━━━━━━━━━━━━━━━━
🎮 *Free Fire Name:* {user['ff_name']}
📱 *WhatsApp:* {user['phone']}
💰 *Total Coins:* {user['coins']}
🏆 *Tournaments Joined:* {tournaments_joined}
📋 *Tasks Completed:* {tasks_completed}
👑 *Admin:* {'Yes' if user.get('is_admin') else 'No'}
📅 *Joined:* {user['created_at'][:10]}
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

📢 *Global Notice:*
{notice['text']}

📞 *Support Contacts:*
WhatsApp: {support['whatsapp']}
Telegram: {support['telegram']}
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

# Admin functions
@admin_required
def show_admin_panel(message):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("📋 Manage Tasks", callback_data="admin_tasks"),
        InlineKeyboardButton("🏆 Manage Tournaments", callback_data="admin_tournaments"),
        InlineKeyboardButton("👥 Manage Users", callback_data="admin_users"),
        InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings"),
        InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
        InlineKeyboardButton("💾 Backup/Restore", callback_data="admin_backup"),
        InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")
    )
    
    bot.send_message(message.chat.id, "⚙️ *Admin Panel*\n\nSelect an option:", parse_mode='Markdown', reply_markup=markup)

@admin_required
def show_admin_tasks(message):
    tasks = db.get_all_tasks()
    
    if not tasks:
        text = "📋 *Manage Tasks*\n\nNo tasks available."
    else:
        text = "📋 *Manage Tasks*\n\n"
        for task in tasks:
            status = "✅ Active" if task["is_active"] else "❌ Inactive"
            one_time = "🔒 One-time" if task["is_one_time"] else "🔄 Repeatable"
            text += f"━━━━━━━━━━━━━━━━\n"
            text += f"ID: {task['id']}\n"
            text += f"📌 {task['title']}\n"
            text += f"📝 {task['description'][:50]}...\n"
            text += f"💰 Reward: {task['reward']} coins\n"
            text += f"🔄 Max Views: {task['max_views_per_user']}\n"
            text += f"{status} | {one_time}\n"
    
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton("➕ Add New Task", callback_data="add_task"))
    
    if tasks:
        for task in tasks:
            markup.add(
                InlineKeyboardButton(f"✏️ Edit {task['id']}", callback_data=f"edit_task_{task['id']}"),
                InlineKeyboardButton(f"🗑️ Delete {task['id']}", callback_data=f"delete_task_{task['id']}")
            )
    
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

def add_task_title(message):
    title = message.text
    msg = bot.send_message(message.chat.id, "Enter task description:")
    bot.register_next_step_handler(msg, add_task_description, title)

def add_task_description(message, title):
    description = message.text
    msg = bot.send_message(message.chat.id, "Enter reward (coins):")
    bot.register_next_step_handler(msg, add_task_reward, title, description)

def add_task_reward(message, title, description):
    try:
        reward = int(message.text)
        msg = bot.send_message(message.chat.id, "Enter max views per user (default 1):")
        bot.register_next_step_handler(msg, add_task_max_views, title, description, reward)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid number. Please try again.")
        show_admin_tasks(message)

def add_task_max_views(message, title, description, reward):
    try:
        max_views = int(message.text) if message.text.isdigit() else 1
        msg = bot.send_message(message.chat.id, "Is this a one-time task? (yes/no):")
        bot.register_next_step_handler(msg, add_task_one_time, title, description, reward, max_views)
    except ValueError:
        max_views = 1
        msg = bot.send_message(message.chat.id, "Is this a one-time task? (yes/no):")
        bot.register_next_step_handler(msg, add_task_one_time, title, description, reward, max_views)

def add_task_one_time(message, title, description, reward, max_views):
    is_one_time = 1 if message.text.lower() in ['yes', 'y'] else 0
    
    db.create_task(title, description, reward, max_views, is_one_time)
    
    bot.send_message(message.chat.id, f"✅ Task '{title}' added successfully!")
    show_admin_tasks(message)

def delete_task(message, task_id):
    db.delete_task(task_id)
    bot.send_message(message.chat.id, f"✅ Task {task_id} deleted successfully!")
    show_admin_tasks(message)

def set_task_limit(message, task_id):
    try:
        max_views = int(message.text)
        db.update_task(task_id, max_views_per_user=max_views)
        bot.send_message(message.chat.id, f"✅ Task limit updated to {max_views} views per user!")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid number!")
    show_admin_tasks(message)

def toggle_one_time_task(message, task_id):
    task = db.get_task_by_id(task_id)
    new_value = 0 if task["is_one_time"] else 1
    db.update_task(task_id, is_one_time=new_value)
    bot.send_message(message.chat.id, f"✅ Task {'now one-time' if new_value else 'now repeatable'}!")
    show_admin_tasks(message)

@admin_required
def show_admin_tournaments(message):
    tournaments = db.get_all_tournaments()
    
    if not tournaments:
        text = "🏆 *Manage Tournaments*\n\nNo tournaments available."
    else:
        text = "🏆 *Manage Tournaments*\n\n"
        for t in tournaments:
            text += f"━━━━━━━━━━━━━━━━\n"
            text += f"ID: {t['id']}\n"
            text += f"📌 {t['name']}\n"
            text += f"💰 Entry: {t['entry_fee']} coins\n"
            text += f"🏆 Prize: {t['prize_pool']}\n"
            text += f"📊 Status: {t['status']}\n"
    
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(InlineKeyboardButton("➕ Add New Tournament", callback_data="add_tournament"))
    
    if tournaments:
        for t in tournaments:
            markup.add(
                InlineKeyboardButton(f"✏️ Edit {t['id']}", callback_data=f"edit_tournament_{t['id']}"),
                InlineKeyboardButton(f"🗑️ Delete {t['id']}", callback_data=f"delete_tournament_{t['id']}")
            )
    
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

def add_tournament_name(message):
    name = message.text
    msg = bot.send_message(message.chat.id, "Enter tournament type (solo/duo/squad):")
    bot.register_next_step_handler(msg, add_tournament_type, name)

def add_tournament_type(message, name):
    t_type = message.text
    msg = bot.send_message(message.chat.id, "Enter map (bermuda/purgatory/kalahari):")
    bot.register_next_step_handler(msg, add_tournament_map, name, t_type)

def add_tournament_map(message, name, t_type):
    map_name = message.text
    msg = bot.send_message(message.chat.id, "Enter entry fee (coins):")
    bot.register_next_step_handler(msg, add_tournament_fee, name, t_type, map_name)

def add_tournament_fee(message, name, t_type, map_name):
    try:
        fee = int(message.text)
        msg = bot.send_message(message.chat.id, "Enter max players:")
        bot.register_next_step_handler(msg, add_tournament_max_players, name, t_type, map_name, fee)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid number. Please try again.")
        show_admin_tournaments(message)

def add_tournament_max_players(message, name, t_type, map_name, fee):
    try:
        max_players = int(message.text)
        msg = bot.send_message(message.chat.id, "Enter prize pool:")
        bot.register_next_step_handler(msg, add_tournament_prize, name, t_type, map_name, fee, max_players)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid number. Please try again.")
        show_admin_tournaments(message)

def add_tournament_prize(message, name, t_type, map_name, fee, max_players):
    prize = message.text
    msg = bot.send_message(message.chat.id, "Enter start time (YYYY-MM-DD HH:MM):")
    bot.register_next_step_handler(msg, add_tournament_start, name, t_type, map_name, fee, max_players, prize)

def add_tournament_start(message, name, t_type, map_name, fee, max_players, prize):
    start_time = message.text
    msg = bot.send_message(message.chat.id, "Enter tournament rules (optional, send 'skip' to skip):")
    bot.register_next_step_handler(msg, add_tournament_rules, name, t_type, map_name, fee, max_players, prize, start_time)

def add_tournament_rules(message, name, t_type, map_name, fee, max_players, prize, start_time):
    rules = message.text if message.text != 'skip' else ""
    
    db.create_tournament(name, t_type, map_name, fee, max_players, prize, start_time, rules)
    
    bot.send_message(message.chat.id, f"✅ Tournament '{name}' added successfully!")
    show_admin_tournaments(message)

def delete_tournament(message, tournament_id):
    db.delete_tournament(tournament_id)
    bot.send_message(message.chat.id, f"✅ Tournament {tournament_id} deleted successfully!")
    show_admin_tournaments(message)

@admin_required
def show_admin_users(message):
    users = db.get_all_users()
    
    total_users = len(users)
    total_coins = sum(u["coins"] for u in users)
    
    text = f"""
👥 *User Statistics*
━━━━━━━━━━━━━━━━
👤 *Total Users:* {total_users}
💰 *Total Coins:* {total_coins}
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("💰 Add Coins to User", callback_data="add_coins_user"),
        InlineKeyboardButton("📊 User Rankings", callback_data="user_rankings"),
        InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")
    )
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

def add_coins_find_user(message):
    search_term = message.text
    users = db.get_all_users()
    
    found_users = []
    for user in users:
        if str(user["telegram_id"]) == search_term or search_term.lower() in user["ff_name"].lower():
            found_users.append(user)
    
    if not found_users:
        bot.send_message(message.chat.id, "❌ User not found!")
        return
    
    if len(found_users) == 1:
        user = found_users[0]
        msg = bot.send_message(message.chat.id, f"Found user: {user['ff_name']} (ID: {user['telegram_id']})\nEnter amount of coins to add:")
        bot.register_next_step_handler(msg, add_coins_amount, user["id"])
    else:
        markup = InlineKeyboardMarkup()
        for user in found_users:
            markup.add(InlineKeyboardButton(f"{user['ff_name']} (ID: {user['telegram_id']})", callback_data=f"select_user_{user['id']}"))
        bot.send_message(message.chat.id, "Multiple users found. Select one:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_user_"))
def select_user_for_coins(call):
    user_id = int(call.data.split("_")[2])
    msg = bot.send_message(call.message.chat.id, "Enter amount of coins to add:")
    bot.register_next_step_handler(msg, add_coins_amount, user_id)

def add_coins_amount(message, user_id):
    try:
        amount = int(message.text)
        db.update_user_coins(user_id, amount)
        bot.send_message(message.chat.id, f"✅ Added {amount} coins to user!")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid amount!")
    show_admin_users(message)

def show_user_rankings(call):
    users = db.get_all_users()
    sorted_users = sorted(users, key=lambda x: x["coins"], reverse=True)[:10]
    
    text = "🏆 *Top 10 Users by Coins*\n━━━━━━━━━━━━━━━━\n"
    for i, user in enumerate(sorted_users, 1):
        text += f"{i}. {user['ff_name']} - {user['coins']} coins\n"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="admin_users"))
    
    bot.send_message(call.message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@admin_required
def show_admin_settings(message):
    notice = db.get_global_notice()
    support = db.get_support_contacts()
    about = db.get_about()
    
    text = f"""
⚙️ *Settings*
━━━━━━━━━━━━━━━━
📢 *Global Notice:*
{notice['text']}

📞 *Support Contacts:*
WhatsApp: {support['whatsapp']}
Telegram: {support['telegram']}

ℹ️ *About Page:*
{about['content'][:100]}...
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(
        InlineKeyboardButton("📢 Edit Global Notice", callback_data="edit_notice"),
        InlineKeyboardButton("📞 Edit Support Contacts", callback_data="edit_support"),
        InlineKeyboardButton("📝 Edit About Page", callback_data="edit_about"),
        InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")
    )
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

def update_notice(message):
    notice_text = message.text
    db.update_global_notice(notice_text)
    bot.send_message(message.chat.id, "✅ Global notice updated successfully!")
    show_admin_settings(message)

def update_support_whatsapp(message):
    whatsapp = message.text
    msg = bot.send_message(message.chat.id, "Enter Telegram group link:")
    bot.register_next_step_handler(msg, update_support_telegram, whatsapp)

def update_support_telegram(message, whatsapp):
    telegram = message.text
    db.update_support_contacts(whatsapp, telegram)
    bot.send_message(message.chat.id, "✅ Support contacts updated successfully!")
    show_admin_settings(message)

def update_about(message):
    about_content = message.text
    msg = bot.send_message(message.chat.id, "Enter image URL (optional, send 'skip' to skip):")
    bot.register_next_step_handler(msg, update_about_image, about_content)

def update_about_image(message, about_content):
    image_url = message.text if message.text != 'skip' else ''
    db.update_about(about_content, image_url)
    bot.send_message(message.chat.id, "✅ About page updated successfully!")
    show_admin_settings(message)

@admin_required
def show_admin_stats(message):
    users = db.get_all_users()
    tasks = db.get_all_tasks()
    tournaments = db.get_all_tournaments()
    
    active_tasks = len([t for t in tasks if t["is_active"]])
    active_tournaments = len([t for t in tournaments if t["status"] != "completed"])
    
    total_completions = 0
    for user in users:
        completions = db.get_user_task_completions(user["id"])
        total_completions += len(completions)
    
    total_participations = 0
    for tournament in tournaments:
        participants = db.get_tournament_participants(tournament["id"])
        total_participations += len(participants)
    
    text = f"""
📊 *System Statistics*
━━━━━━━━━━━━━━━━
📋 *Tasks:*
• Active Tasks: {active_tasks}
• Total Tasks: {len(tasks)}
• Total Completions: {total_completions}

👥 *Users:*
• Total Users: {len(users)}
• Total Coins in System: {sum(u['coins'] for u in users)}
• Average Coins per User: {sum(u['coins'] for u in users) // len(users) if users else 0}

🏆 *Tournaments:*
• Active Tournaments: {active_tournaments}
• Total Tournaments: {len(tournaments)}
• Total Participations: {total_participations}
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats"))
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@admin_required
def handle_admin_backup(message):
    backup_data = db.backup()
    
    # Save backup to file
    backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_filename, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)
    
    # Send backup file
    with open(backup_filename, 'rb') as f:
        bot.send_document(message.chat.id, f, caption="📦 Database Backup")
    
    # Clean up
    os.remove(backup_filename)
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🔄 Restore from Backup", callback_data="restore_data"),
        InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")
    )
    
    bot.send_message(message.chat.id, "✅ Backup created successfully!", reply_markup=markup)

def handle_restore_file(message):
    if message.document:
        # Download file
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        try:
            backup_data = json.loads(downloaded_file.decode('utf-8'))
            db.restore(backup_data)
            bot.send_message(message.chat.id, "✅ Database restored successfully!")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Restore failed: {str(e)}")
    else:
        bot.send_message(message.chat.id, "❌ Please send a JSON file.")

# Flask web routes for ad serving
@app.route('/')
def index():
    return "tunff09 Telegram Bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Bad Request', 400

@app.route('/set_webhook')
def set_webhook():
    try:
        bot.remove_webhook()
        time.sleep(1)
        webhook_url = f"{BASE_URL}/webhook"
        bot.set_webhook(url=webhook_url)
        return f"Webhook set to {webhook_url}", 200
    except Exception as e:
        return f"Error setting webhook: {str(e)}", 500

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

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
                margin: 0; 
                padding: 0; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .container {
                text-align: center;
                padding: 20px;
                max-width: 500px;
                width: 100%;
            }
            .card {
                background: rgba(255,255,255,0.1);
                backdrop-filter: blur(10px);
                border-radius: 30px;
                padding: 40px 30px;
                box-shadow: 0 25px 45px rgba(0,0,0,0.2);
            }
            h1 {
                font-size: 28px;
                margin-bottom: 20px;
            }
            .reward {
                font-size: 48px;
                font-weight: bold;
                color: #FFD700;
                margin: 20px 0;
            }
            .reward-amount {
                font-size: 64px;
                font-weight: bold;
                color: #FFD700;
            }
            button {
                background: linear-gradient(115deg, #7c3aed, #a855f7);
                color: white;
                border: none;
                padding: 16px 32px;
                border-radius: 50px;
                font-size: 18px;
                font-weight: bold;
                cursor: pointer;
                margin-top: 20px;
                transition: transform 0.2s;
            }
            button:hover {
                transform: translateY(-2px);
            }
            .loading {
                display: none;
                margin-top: 20px;
            }
            .loading.show {
                display: block;
            }
            .spinner {
                width: 40px;
                height: 40px;
                border: 4px solid rgba(255,255,255,0.3);
                border-top-color: white;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto;
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <h1>🎬 Complete Task</h1>
                <p>Watch the ad to earn coins</p>
                <div class="reward">
                    <span>💰 </span>
                    <span class="reward-amount">+{{ reward }}</span>
                    <span> coins</span>
                </div>
                <button onclick="watchAd()">🎬 Watch Ad Now</button>
                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    <p style="margin-top: 10px;">Loading ad...</p>
                </div>
            </div>
        </div>
        
        <script>
            const BASE_URL = '{{ base_url }}';
            
            function watchAd() {
                const btn = event.target;
                const loading = document.getElementById('loading');
                btn.disabled = true;
                loading.classList.add('show');
                
                show_{{ zone }}('pop').then(() => {
                    window.location.href = BASE_URL + '/ad_complete?task_id={{ task_id }}&user_id={{ user_id }}&reward={{ reward }}';
                }).catch(e => {
                    loading.classList.remove('show');
                    btn.disabled = false;
                    alert('Error loading ad. Please try again.');
                });
            }
        </script>
    </body>
    </html>
    ''', zone=zone, task_id=task_id, user_id=user_id, reward=reward, base_url=BASE_URL)

@app.route('/ad_complete')
def ad_complete():
    task_id = request.args.get('task_id')
    user_id = request.args.get('user_id')
    reward = request.args.get('reward')
    
    if task_id and user_id:
        # Complete the task and add coins
        result = complete_task(int(user_id), int(task_id))
        
        if result:
            return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {
                        margin: 0;
                        padding: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        font-family: sans-serif;
                        min-height: 100vh;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        text-align: center;
                    }
                    .container {
                        padding: 20px;
                    }
                    .success {
                        background: rgba(34,197,94,0.2);
                        border-radius: 30px;
                        padding: 40px;
                        backdrop-filter: blur(10px);
                    }
                    h1 { color: #22c55e; font-size: 48px; margin-bottom: 20px; }
                    .coins { font-size: 32px; font-weight: bold; color: #FFD700; }
                    button {
                        background: #7c3aed;
                        color: white;
                        border: none;
                        padding: 12px 24px;
                        border-radius: 50px;
                        font-size: 16px;
                        margin-top: 20px;
                        cursor: pointer;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success">
                        <h1>✅ Task Completed!</h1>
                        <p>You have earned</p>
                        <div class="coins">+{{ reward }} Coins</div>
                        <button onclick="window.close()">Close Window</button>
                    </div>
                </div>
                <script>
                    setTimeout(() => window.close(), 5000);
                </script>
            </body>
            </html>
            ''', reward=reward)
    
    return "Invalid request"

# Main entry point
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask server on port {port}...")
    print(f"Base URL: {BASE_URL}")
    print(f"Set webhook at: {BASE_URL}/set_webhook")
    app.run(host='0.0.0.0', port=port)
