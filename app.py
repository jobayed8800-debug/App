# main.py - Flask application with Telegram bot
import os
import json
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
import requests

app = Flask(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = "8243669144:AAEGgOKla5rGQTgU5qLrcsBzhzVl5wb-LFA"
ADMIN_TELEGRAM_IDS = [7612692016]  # Replace with your Telegram ID
DATABASE_FILE = "database.db"
MONETAG_ZONE = "10253210"

# Initialize bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Database setup
def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        ff_name TEXT,
        phone TEXT,
        coins INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Daily tasks table
    c.execute('''CREATE TABLE IF NOT EXISTS daily_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        reward INTEGER,
        max_views_per_user INTEGER DEFAULT 1,
        is_one_time INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # User task completions
    c.execute('''CREATE TABLE IF NOT EXISTS user_task_completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        task_id INTEGER,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        view_count INTEGER DEFAULT 1,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(task_id) REFERENCES daily_tasks(id)
    )''')
    
    # Tournaments table
    c.execute('''CREATE TABLE IF NOT EXISTS tournaments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        tournament_type TEXT,
        map TEXT,
        entry_fee INTEGER,
        max_players INTEGER,
        prize_pool TEXT,
        start_time TIMESTAMP,
        status TEXT DEFAULT 'upcoming',
        rules TEXT,
        room_details TEXT,
        image_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Tournament participants
    c.execute('''CREATE TABLE IF NOT EXISTS tournament_participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER,
        user_id INTEGER,
        status TEXT DEFAULT 'joined',
        selection_round INTEGER,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(tournament_id) REFERENCES tournaments(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    # Tournament selections history
    c.execute('''CREATE TABLE IF NOT EXISTS tournament_selections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER,
        round INTEGER,
        selected_count INTEGER,
        selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(tournament_id) REFERENCES tournaments(id)
    )''')
    
    # Popups table
    c.execute('''CREATE TABLE IF NOT EXISTS popups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_url TEXT,
        link TEXT,
        text TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # About page content
    c.execute('''CREATE TABLE IF NOT EXISTS about (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT,
        image_url TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Global notice
    c.execute('''CREATE TABLE IF NOT EXISTS global_notice (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Support contacts
    c.execute('''CREATE TABLE IF NOT EXISTS support_contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        whatsapp TEXT,
        telegram TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Initialize default data
    c.execute("SELECT COUNT(*) FROM global_notice")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO global_notice (text) VALUES (?)", ("Welcome to tunff09 Tournament Bot!",))
    
    c.execute("SELECT COUNT(*) FROM support_contacts")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO support_contacts (whatsapp, telegram) VALUES (?, ?)", ("+8801234567890", "https://t.me/tunff09"))
    
    conn.commit()
    conn.close()

# Helper functions
def get_user(telegram_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(telegram_id, username, ff_name, phone):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (telegram_id, username, ff_name, phone) VALUES (?, ?, ?, ?)",
                  (telegram_id, username, ff_name, phone))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None

def add_coins(user_id, amount):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def can_complete_task(user_id, task_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT max_views_per_user, is_one_time FROM daily_tasks WHERE id = ?", (task_id,))
    task = c.fetchone()
    if not task:
        conn.close()
        return False
    
    c.execute("SELECT SUM(view_count) as total FROM user_task_completions WHERE user_id = ? AND task_id = ?", 
              (user_id, task_id))
    result = c.fetchone()
    total_views = result[0] if result[0] else 0
    
    if task[1] == 1 and total_views > 0:
        conn.close()
        return False
    
    if total_views >= task[0]:
        conn.close()
        return False
    
    conn.close()
    return True

def complete_task(user_id, task_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT reward FROM daily_tasks WHERE id = ?", (task_id,))
    reward = c.fetchone()[0]
    
    c.execute("INSERT INTO user_task_completions (user_id, task_id) VALUES (?, ?)", (user_id, task_id))
    conn.commit()
    
    c.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (reward, user_id))
    conn.commit()
    conn.close()
    return reward

# Telegram bot handlers
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = get_user(message.from_user.id)
    if user:
        show_main_menu(message)
    else:
        markup = InlineKeyboardMarkup()
        markup.row_width = 1
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
    elif call.data.startswith("complete_task_"):
        task_id = int(call.data.split("_")[2])
        handle_task_completion(call.message, call.from_user.id, task_id)
    elif call.data.startswith("join_tournament_"):
        tournament_id = int(call.data.split("_")[2])
        handle_join_tournament(call.message, call.from_user.id, tournament_id)
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

def get_ff_name(message):
    ff_name = message.text
    msg = bot.send_message(message.chat.id, "📱 Please enter your WhatsApp number:", parse_mode='Markdown')
    bot.register_next_step_handler(msg, get_phone, ff_name)

def get_phone(message, ff_name):
    phone = message.text
    user_id = create_user(message.from_user.id, message.from_user.username, ff_name, phone)
    if user_id:
        bot.send_message(message.chat.id, 
                        "✅ *Registration Successful!*\n\n"
                        f"Welcome {ff_name}!\n"
                        f"You've received 100 bonus coins!\n\n"
                        "Use /start to access the main menu.",
                        parse_mode='Markdown')
        add_coins(user_id, 100)
    else:
        bot.send_message(message.chat.id, "❌ Registration failed. You might already be registered!")

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
    
    bot.send_message(message.chat.id, 
                    f"🎮 *Main Menu*\n\n"
                    f"👤 User: {user[2]}\n"
                    f"💰 Coins: {user[4]}\n\n"
                    "Select an option:",
                    parse_mode='Markdown', reply_markup=markup)

def show_daily_tasks(message):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, description, reward FROM daily_tasks WHERE is_active = 1")
    tasks = c.fetchall()
    conn.close()
    
    if not tasks:
        bot.send_message(message.chat.id, "📭 No tasks available at the moment.")
        return
    
    user = get_user(message.from_user.id)
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    
    for task in tasks:
        if can_complete_task(user[0], task[0]):
            markup.add(InlineKeyboardButton(f"💰 {task[1]} (+{task[2]} coins)", callback_data=f"complete_task_{task[0]}"))
        else:
            markup.add(InlineKeyboardButton(f"✅ {task[1]} (Completed)", callback_data="noop"))
    
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, 
                    "📋 *Daily Tasks*\n\n"
                    "Complete tasks to earn coins!\n"
                    "Each task can be completed multiple times based on limits.\n\n"
                    "Click on a task to complete it (requires watching an ad):",
                    parse_mode='Markdown', reply_markup=markup)

def handle_task_completion(message, telegram_id, task_id):
    user = get_user(telegram_id)
    if not can_complete_task(user[0], task_id):
        bot.send_message(message.chat.id, "❌ You've already completed this task the maximum number of times!")
        return
    
    # Generate ad link with monetag
    ad_link = f"https://app.monetag.com/ads/{MONETAG_ZONE}/rewarded"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎬 Watch Ad to Complete Task", url=ad_link))
    markup.add(InlineKeyboardButton("✅ I've Completed the Ad", callback_data=f"verify_task_{task_id}"))
    markup.add(InlineKeyboardButton("🔙 Back", callback_data="daily_tasks"))
    
    bot.send_message(message.chat.id, 
                    "🎬 *Complete Task*\n\n"
                    f"Click the button below to watch an ad.\n"
                    f"After watching the ad, click 'I've Completed the Ad' to receive your reward.\n\n"
                    f"Reward: {get_task_reward(task_id)} coins",
                    parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("verify_task_"))
def verify_task_completion(call):
    task_id = int(call.data.split("_")[2])
    user = get_user(call.from_user.id)
    
    if not can_complete_task(user[0], task_id):
        bot.answer_callback_query(call.id, "Task already completed maximum times!")
        return
    
    reward = complete_task(user[0], task_id)
    bot.answer_callback_query(call.id, f"✅ Task completed! You earned {reward} coins!")
    
    # Show updated main menu
    show_main_menu(call.message)

def get_task_reward(task_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT reward FROM daily_tasks WHERE id = ?", (task_id,))
    reward = c.fetchone()[0]
    conn.close()
    return reward

def show_tournaments(message):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, entry_fee, prize_pool, max_players, status FROM tournaments WHERE status != 'completed' ORDER BY start_time DESC")
    tournaments = c.fetchall()
    conn.close()
    
    if not tournaments:
        bot.send_message(message.chat.id, "🏆 No active tournaments at the moment.")
        return
    
    user = get_user(message.from_user.id)
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    
    for t in tournaments:
        status_text = {"upcoming": "🟢 Upcoming", "ongoing": "🟡 Ongoing", "selection": "🔵 Selection"}.get(t[5], "⚪")
        markup.add(InlineKeyboardButton(f"{status_text} {t[1]} (Entry: {t[2]} coins)", callback_data=f"join_tournament_{t[0]}"))
    
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, 
                    "🏆 *Active Tournaments*\n\n"
                    "Click on a tournament to see details and join:",
                    parse_mode='Markdown', reply_markup=markup)

def handle_join_tournament(message, telegram_id, tournament_id):
    user = get_user(telegram_id)
    
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT name, entry_fee, prize_pool, status, rules FROM tournaments WHERE id = ?", (tournament_id,))
    tournament = c.fetchone()
    
    if not tournament:
        bot.send_message(message.chat.id, "Tournament not found!")
        return
    
    if tournament[3] == 'completed':
        bot.send_message(message.chat.id, "This tournament has already ended!")
        return
    
    if user[4] < tournament[1]:
        bot.send_message(message.chat.id, f"❌ You don't have enough coins!\nNeed: {tournament[1]} coins\nYou have: {user[4]} coins")
        return
    
    # Check if already joined
    c.execute("SELECT * FROM tournament_participants WHERE tournament_id = ? AND user_id = ?", (tournament_id, user[0]))
    if c.fetchone():
        bot.send_message(message.chat.id, "❌ You've already joined this tournament!")
        conn.close()
        return
    
    # Join tournament
    c.execute("INSERT INTO tournament_participants (tournament_id, user_id) VALUES (?, ?)", (tournament_id, user[0]))
    c.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (tournament[1], user[0]))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, 
                    f"✅ *Successfully joined {tournament[0]}!*\n\n"
                    f"📝 *Tournament Details:*\n"
                    f"Entry Fee: {tournament[1]} coins\n"
                    f"Prize Pool: {tournament[2]}\n\n"
                    f"{tournament[4] if tournament[4] else 'Rules will be announced soon.'}\n\n"
                    f"Keep an eye on this bot for room details!",
                    parse_mode='Markdown')
    
    show_main_menu(message)

def show_profile(message):
    user = get_user(message.from_user.id)
    
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tournament_participants WHERE user_id = ?", (user[0],))
    tournaments_joined = c.fetchone()[0]
    
    c.execute("SELECT SUM(reward) FROM user_task_completions utc JOIN daily_tasks dt ON utc.task_id = dt.id WHERE user_id = ?", (user[0],))
    tasks_completed = c.fetchone()[0] or 0
    
    conn.close()
    
    profile_text = f"""
👤 *Profile*
━━━━━━━━━━━━━━━━
🎮 *Free Fire Name:* {user[2]}
📱 *WhatsApp:* {user[3]}
💰 *Total Coins:* {user[4]}
🏆 *Tournaments Joined:* {tournaments_joined}
📋 *Tasks Completed:* {tasks_completed}
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, profile_text, parse_mode='Markdown', reply_markup=markup)

def show_about(message):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT content, image_url FROM about ORDER BY id DESC LIMIT 1")
    about = c.fetchone()
    c.execute("SELECT text FROM global_notice ORDER BY id DESC LIMIT 1")
    notice = c.fetchone()
    c.execute("SELECT whatsapp, telegram FROM support_contacts ORDER BY id DESC LIMIT 1")
    support = c.fetchone()
    conn.close()
    
    about_text = about[0] if about else "tunff09 Tournament Platform"
    
    text = f"""
ℹ️ *About tunff09*
━━━━━━━━━━━━━━━━
{about_text}

📢 *Notice:*
{notice[0] if notice else "No notices"}

📞 *Support:*
WhatsApp: {support[0] if support else "N/A"}
Telegram: {support[1] if support else "N/A"}
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

# Admin functions
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

def show_admin_tasks(message):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, reward, max_views_per_user, is_one_time, is_active FROM daily_tasks ORDER BY id DESC")
    tasks = c.fetchall()
    conn.close()
    
    text = "📋 *Manage Tasks*\n\n"
    for task in tasks:
        status = "✅ Active" if task[5] else "❌ Inactive"
        one_time = "🔒 One-time" if task[4] else "🔄 Repeatable"
        text += f"ID: {task[0]}\n📌 {task[1]}\n💰 Reward: {task[2]} coins\n🔄 Max Views: {task[3]}\n{status} | {one_time}\n\n"
    
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("➕ Add New Task", callback_data="add_task"),
        InlineKeyboardButton("📊 View Stats", callback_data="task_stats")
    )
    
    for task in tasks:
        markup.add(
            InlineKeyboardButton(f"✏️ Edit Task {task[0]}", callback_data=f"edit_task_{task[0]}"),
            InlineKeyboardButton(f"🗑️ Delete {task[0]}", callback_data=f"delete_task_{task[0]}")
        )
    
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_task")
def add_task_prompt(call):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    msg = bot.send_message(call.message.chat.id, "Enter task title:")
    bot.register_next_step_handler(msg, add_task_title)

def add_task_title(message):
    title = message.text
    msg = bot.send_message(message.chat.id, "Enter task description:")
    bot.register_next_step_handler(msg, add_task_description, title)

def add_task_description(message, title):
    description = message.text
    msg = bot.send_message(message.chat.id, "Enter reward (coins):")
    bot.register_next_step_handler(msg, add_task_reward, title, description)

def add_task_reward(message, title, description):
    reward = int(message.text)
    msg = bot.send_message(message.chat.id, "Enter max views per user (default 1):")
    bot.register_next_step_handler(msg, add_task_max_views, title, description, reward)

def add_task_max_views(message, title, description, reward):
    max_views = int(message.text) if message.text.isdigit() else 1
    msg = bot.send_message(message.chat.id, "Is this a one-time task? (yes/no):")
    bot.register_next_step_handler(msg, add_task_one_time, title, description, reward, max_views)

def add_task_one_time(message, title, description, reward, max_views):
    is_one_time = 1 if message.text.lower() in ['yes', 'y'] else 0
    
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO daily_tasks (title, description, reward, max_views_per_user, is_one_time) VALUES (?, ?, ?, ?, ?)",
              (title, description, reward, max_views, is_one_time))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f"✅ Task '{title}' added successfully!")
    show_admin_tasks(message)

def delete_task(message, task_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM daily_tasks WHERE id = ?", (task_id,))
    c.execute("DELETE FROM user_task_completions WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f"✅ Task {task_id} deleted successfully!")
    show_admin_tasks(message)

def set_task_limit(message, task_id):
    max_views = int(message.text)
    
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("UPDATE daily_tasks SET max_views_per_user = ? WHERE id = ?", (max_views, task_id))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f"✅ Task limit updated to {max_views} views per user!")
    show_admin_tasks(message)

def toggle_one_time_task(message, task_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT is_one_time FROM daily_tasks WHERE id = ?", (task_id,))
    current = c.fetchone()[0]
    new_value = 0 if current else 1
    c.execute("UPDATE daily_tasks SET is_one_time = ? WHERE id = ?", (new_value, task_id))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f"✅ Task {'now one-time' if new_value else 'now repeatable'}!")
    show_admin_tasks(message)

def show_admin_tournaments(message):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name, entry_fee, prize_pool, status FROM tournaments ORDER BY id DESC")
    tournaments = c.fetchall()
    conn.close()
    
    text = "🏆 *Manage Tournaments*\n\n"
    for t in tournaments:
        text += f"ID: {t[0]}\n📌 {t[1]}\n💰 Entry: {t[2]} coins | Prize: {t[3]}\n📊 Status: {t[4]}\n\n"
    
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("➕ Add New Tournament", callback_data="add_tournament"),
        InlineKeyboardButton("📊 Tournament Stats", callback_data="tournament_stats")
    )
    
    for t in tournaments:
        markup.add(
            InlineKeyboardButton(f"✏️ Edit {t[0]}", callback_data=f"edit_tournament_{t[0]}"),
            InlineKeyboardButton(f"🗑️ Delete {t[0]}", callback_data=f"delete_tournament_{t[0]}")
        )
    
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_tournament")
def add_tournament_prompt(call):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    msg = bot.send_message(call.message.chat.id, "Enter tournament name:")
    bot.register_next_step_handler(msg, add_tournament_name)

def add_tournament_name(message):
    name = message.text
    msg = bot.send_message(message.chat.id, "Enter tournament type (solo/duo/squad):")
    bot.register_next_step_handler(msg, add_tournament_type, name)

def add_tournament_type(message, name):
    t_type = message.text
    msg = bot.send_message(message.chat.id, "Enter map (bermuda/purgatory):")
    bot.register_next_step_handler(msg, add_tournament_map, name, t_type)

def add_tournament_map(message, name, t_type):
    map_name = message.text
    msg = bot.send_message(message.chat.id, "Enter entry fee (coins):")
    bot.register_next_step_handler(msg, add_tournament_fee, name, t_type, map_name)

def add_tournament_fee(message, name, t_type, map_name):
    fee = int(message.text)
    msg = bot.send_message(message.chat.id, "Enter max players:")
    bot.register_next_step_handler(msg, add_tournament_max_players, name, t_type, map_name, fee)

def add_tournament_max_players(message, name, t_type, map_name, fee):
    max_players = int(message.text)
    msg = bot.send_message(message.chat.id, "Enter prize pool:")
    bot.register_next_step_handler(msg, add_tournament_prize, name, t_type, map_name, fee, max_players)

def add_tournament_prize(message, name, t_type, map_name, fee, max_players):
    prize = message.text
    msg = bot.send_message(message.chat.id, "Enter start time (YYYY-MM-DD HH:MM):")
    bot.register_next_step_handler(msg, add_tournament_start, name, t_type, map_name, fee, max_players, prize)

def add_tournament_start(message, name, t_type, map_name, fee, max_players, prize):
    start_time = message.text
    msg = bot.send_message(message.chat.id, "Enter tournament rules (optional):")
    bot.register_next_step_handler(msg, add_tournament_rules, name, t_type, map_name, fee, max_players, prize, start_time)

def add_tournament_rules(message, name, t_type, map_name, fee, max_players, prize, start_time):
    rules = message.text
    
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("""INSERT INTO tournaments 
                (name, tournament_type, map, entry_fee, max_players, prize_pool, start_time, rules) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (name, t_type, map_name, fee, max_players, prize, start_time, rules))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f"✅ Tournament '{name}' added successfully!")
    show_admin_tournaments(message)

def delete_tournament(message, tournament_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM tournaments WHERE id = ?", (tournament_id,))
    c.execute("DELETE FROM tournament_participants WHERE tournament_id = ?", (tournament_id,))
    c.execute("DELETE FROM tournament_selections WHERE tournament_id = ?", (tournament_id,))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f"✅ Tournament {tournament_id} deleted successfully!")
    show_admin_tournaments(message)

def show_admin_users(message):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(coins) FROM users")
    total_coins = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM tournament_participants")
    total_joins = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM user_task_completions")
    total_tasks = c.fetchone()[0]
    conn.close()
    
    text = f"""
👥 *User Statistics*
━━━━━━━━━━━━━━━━
👤 *Total Users:* {total_users}
💰 *Total Coins:* {total_coins}
🏆 *Tournament Joins:* {total_joins}
📋 *Tasks Completed:* {total_tasks}
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("📊 User Rankings", callback_data="user_rankings"),
        InlineKeyboardButton("💰 Add Coins to User", callback_data="add_coins_user"),
        InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")
    )
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_coins_user")
def add_coins_prompt(call):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    msg = bot.send_message(call.message.chat.id, "Enter user Telegram ID:")
    bot.register_next_step_handler(msg, add_coins_user_id)

def add_coins_user_id(message):
    user_id = int(message.text)
    msg = bot.send_message(message.chat.id, "Enter amount of coins to add:")
    bot.register_next_step_handler(msg, add_coins_amount, user_id)

def add_coins_amount(message, user_id):
    amount = int(message.text)
    
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + ? WHERE telegram_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, f"✅ Added {amount} coins to user {user_id}!")
    show_admin_users(message)

def show_admin_settings(message):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT text FROM global_notice ORDER BY id DESC LIMIT 1")
    notice = c.fetchone()
    c.execute("SELECT whatsapp, telegram FROM support_contacts ORDER BY id DESC LIMIT 1")
    support = c.fetchone()
    conn.close()
    
    text = f"""
⚙️ *Settings*
━━━━━━━━━━━━━━━━
📢 *Global Notice:*
{notice[0] if notice else 'Not set'}

📞 *Support Contacts:*
WhatsApp: {support[0] if support else 'N/A'}
Telegram: {support[1] if support else 'N/A'}
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

@bot.callback_query_handler(func=lambda call: call.data == "edit_notice")
def edit_notice_prompt(call):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    msg = bot.send_message(call.message.chat.id, "Enter new global notice text:")
    bot.register_next_step_handler(msg, update_notice)

def update_notice(message):
    notice_text = message.text
    
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO global_notice (text) VALUES (?)", (notice_text,))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, "✅ Global notice updated successfully!")
    show_admin_settings(message)

@bot.callback_query_handler(func=lambda call: call.data == "edit_support")
def edit_support_prompt(call):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    msg = bot.send_message(call.message.chat.id, "Enter WhatsApp number (with country code):")
    bot.register_next_step_handler(msg, update_support_whatsapp)

def update_support_whatsapp(message):
    whatsapp = message.text
    msg = bot.send_message(message.chat.id, "Enter Telegram group link:")
    bot.register_next_step_handler(msg, update_support_telegram, whatsapp)

def update_support_telegram(message, whatsapp):
    telegram = message.text
    
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO support_contacts (whatsapp, telegram) VALUES (?, ?)", (whatsapp, telegram))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, "✅ Support contacts updated successfully!")
    show_admin_settings(message)

@bot.callback_query_handler(func=lambda call: call.data == "edit_about")
def edit_about_prompt(call):
    if call.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    msg = bot.send_message(call.message.chat.id, "Enter about page content:")
    bot.register_next_step_handler(msg, update_about)

def update_about(message):
    about_content = message.text
    msg = bot.send_message(message.chat.id, "Enter image URL (optional, send 'skip' to skip):")
    bot.register_next_step_handler(msg, update_about_image, about_content)

def update_about_image(message, about_content):
    image_url = message.text if message.text != 'skip' else ''
    
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO about (content, image_url) VALUES (?, ?)", (about_content, image_url))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, "✅ About page updated successfully!")
    show_admin_settings(message)

def show_admin_stats(message):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    
    # Daily task stats
    c.execute("SELECT COUNT(*) FROM daily_tasks WHERE is_active = 1")
    active_tasks = c.fetchone()[0]
    
    c.execute("SELECT SUM(reward) FROM daily_tasks")
    total_rewards = c.fetchone()[0] or 0
    
    # User stats
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT SUM(coins) FROM users")
    total_coins = c.fetchone()[0] or 0
    
    # Tournament stats
    c.execute("SELECT COUNT(*) FROM tournaments WHERE status != 'completed'")
    active_tournaments = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM tournament_participants")
    total_participations = c.fetchone()[0]
    
    # Task completion stats
    c.execute("SELECT COUNT(*) FROM user_task_completions")
    total_completions = c.fetchone()[0]
    
    conn.close()
    
    text = f"""
📊 *System Statistics*
━━━━━━━━━━━━━━━━
📋 *Tasks:*
• Active Tasks: {active_tasks}
• Total Rewards Available: {total_rewards} coins
• Total Completions: {total_completions}

👥 *Users:*
• Total Users: {total_users}
• Total Coins in System: {total_coins}

🏆 *Tournaments:*
• Active Tournaments: {active_tournaments}
• Total Participations: {total_participations}
━━━━━━━━━━━━━━━━
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats"))
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel"))
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

# Flask web routes for ad serving
@app.route('/')
def index():
    return "tunff09 Telegram Bot is running!"

@app.route('/ad')
def serve_ad():
    zone = request.args.get('zone', MONETAG_ZONE)
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Complete Task - tunff09</title>
        <script src='//libtl.com/sdk.js' data-zone='{{ zone }}' data-sdk='show_{{ zone }}'></script>
        <style>
            body { 
                margin: 0; 
                padding: 0; 
                background: #0a0f1e; 
                color: white;
                font-family: Arial, sans-serif;
            }
            .container {
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                flex-direction: column;
                padding: 20px;
            }
            .message {
                text-align: center;
                margin-top: 20px;
            }
            button {
                background: linear-gradient(115deg, #7c3aed, #a855f7);
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 50px;
                font-size: 18px;
                font-weight: bold;
                cursor: pointer;
                margin-top: 20px;
            }
            .reward {
                color: #22c55e;
                font-size: 24px;
                font-weight: bold;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>🎬 Complete Task to Earn Coins</h2>
            <div id="ad-container"></div>
            <div class="message">
                <p>Watch the ad to complete your task and earn <span class="reward">+{{ reward }} coins</span></p>
                <button onclick="watchAd()">🎬 Watch Ad</button>
            </div>
        </div>
        
        <script>
            function watchAd() {
                show_{{ zone }}('pop').then(() => {
                    // User watched ad successfully
                    window.location.href = '/ad_complete?task_id={{ task_id }}&user_id={{ user_id }}';
                }).catch(e => {
                    alert('Error playing ad. Please try again.');
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
        # Update task completion in database
        conn = sqlite3.connect(DATABASE_FILE)
        c = conn.cursor()
        c.execute("SELECT reward FROM daily_tasks WHERE id = ?", (task_id,))
        reward = c.fetchone()
        if reward:
            c.execute("INSERT INTO user_task_completions (user_id, task_id) VALUES (?, ?)", (user_id, task_id))
            c.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (reward[0], user_id))
            conn.commit()
        conn.close()
        
        return '''
        <html>
        <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="background:#0a0f1e; color:white; text-align:center; padding:50px;">
            <h1>✅ Task Completed!</h1>
            <p>You have earned ''' + str(reward[0]) + ''' coins!</p>
            <p>You can close this window and return to Telegram.</p>
            <script>setTimeout(() => window.close(), 3000);</script>
        </body>
        </html>
        '''
    
    return "Invalid request"

# Start bot in background thread
def run_bot():
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

# Main entry point
if __name__ == '__main__':
    init_db()
    
    # Start bot thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
