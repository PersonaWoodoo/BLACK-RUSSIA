import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import json
import os
import re

# ===== КОНФИГ =====
BOT_TOKEN = "8960201604:AAF7tEwH2jZGEoF9AFsy-RUkaDPm8SqnE3o"
GROUP_ID = -1001234567890  # ЗАМЕНИ НА ID ТВОЕЙ ГРУППЫ
ADMIN_ID = 8478884644

# ===== ИНИЦИАЛИЗАЦИЯ =====
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
logging.basicConfig(level=logging.INFO)

# ===== ДАННЫЕ =====
DATA_FILE = "family_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "users": {},
        "notifications": [],
        "battles": [],
        "announcements": [],
        "logs": [],
        "last_battle_check": None
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

# ===== ВРЕМЕННЫЕ ДАННЫЕ =====
battle_times = {
    "вышка": [f"{i:02d}:35" for i in range(8, 24)],
    "ферма": [f"{i:02d}:40" for i in range(24)],
    "завод": [f"{i:02d}:45" for i in range(24)],
    "контейнер": [f"{i:02d}:30" for i in range(10, 23)]
}

# ===== FSM СОСТОЯНИЯ =====
class AdminStates(StatesGroup):
    waiting_for_lottery_message = State()
    waiting_for_announcement = State()
    waiting_for_battle_collect = State()

class NickStates(StatesGroup):
    waiting_for_nick = State()

class BattleCheckStates(StatesGroup):
    pass

# ===== КЛАВИАТУРЫ =====
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Старший состав", callback_data="senior")],
        [InlineKeyboardButton(text="📅 Расписание битв", callback_data="schedule")],
        [InlineKeyboardButton(text="ℹ️ Помощь новичкам", callback_data="help")],
        [InlineKeyboardButton(text="⚙️ Админ меню", callback_data="admin_menu")]
    ])

def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton(text="⚔️ Сбор на битву", callback_data="admin_collect")],
        [InlineKeyboardButton(text="🎰 Лотерея", callback_data="admin_lottery")],
        [InlineKeyboardButton(text="📋 Логи действий", callback_data="admin_logs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])

# ===== ФУНКЦИИ =====
def get_user_nick(user_id):
    return data["users"].get(str(user_id), {}).get("nick", f"Игрок_{user_id}")

def set_user_nick(user_id, nick):
    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {}
    data["users"][str(user_id)]["nick"] = nick
    save_data(data)

def add_log(action, user_id, details=""):
    log_entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "nick": get_user_nick(user_id),
        "action": action,
        "details": details
    }
    data["logs"].append(log_entry)
    save_data(data)

def get_next_battle_time(battle_type):
    """Возвращает время следующего захвата"""
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    times = battle_times.get(battle_type.lower(), [])
    if not times:
        return None
    
    # Находим следующее время
    for t in sorted(times):
        if t > current_time:
            hour, minute = map(int, t.split(':'))
            battle_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if battle_time < now:
                battle_time += timedelta(days=1)
            return battle_time
    
    # Если все времена прошли, берем первое на завтра
    hour, minute = map(int, times[0].split(':'))
    battle_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    battle_time += timedelta(days=1)
    return battle_time

def check_battle_start():
    """Проверяет, начался ли захват"""
    now = datetime.now().strftime("%H:%M")
    battles = []
    
    for battle_type, times in battle_times.items():
        if now in times:
            battles.append(battle_type)
    
    return battles

# ===== ХЕНДЛЕРЫ =====

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        await message.answer(
            "👋 Добро пожаловать в бот семьи Dniper Dynasty!\n\n"
            "Выбери нужный раздел:",
            reply_markup=get_main_keyboard()
        )
        add_log("Запуск бота", message.from_user.id)

@dp.message(Command("add_nick"))
async def cmd_add_nick(message: types.Message, command: CommandObject):
    """Команда для смены ника: /add_nick НовыйНик"""
    if not command.args:
        await message.answer("❌ Используй: /add_nick ТвойНовыйНик")
        return
    
    new_nick = command.args.strip()
    if len(new_nick) > 30:
        await message.answer("❌ Ник не может быть длиннее 30 символов")
        return
    
    old_nick = get_user_nick(message.from_user.id)
    set_user_nick(message.from_user.id, new_nick)
    add_log("Смена ника", message.from_user.id, f"{old_nick} → {new_nick}")
    
    await message.answer(f"✅ Твой ник изменен с '{old_nick}' на '{new_nick}'!")

@dp.message(F.chat.id == GROUP_ID)
async def group_message_handler(message: types.Message):
    """Обработчик сообщений в группе"""
    # Проверяем вопрос про время битвы
    text = message.text.lower() if message.text else ""
    
    battle_keywords = {
        "вышка": "вышка",
        "ферма": "ферма", 
        "завод": "завод",
        "контейнер": "контейнер",
        "битв": None  # для общего ответа
    }
    
    if any(keyword in text for keyword in battle_keywords.keys()):
        # Определяем тип битвы
        battle_type = None
        for key in battle_keywords:
            if key in text:
                battle_type = key
                break
        
        if battle_type == "битв":
            # Общий ответ
            next_battles = []
            for b_type in ["вышка", "ферма", "завод", "контейнер"]:
                time = get_next_battle_time(b_type)
                if time:
                    next_battles.append(f"• {b_type.capitalize()}: {time.strftime('%H:%M')}")
            await message.reply(
                "📅 Ближайшие захваты:\n" + "\n".join(next_battles)
            )
        elif battle_type:
            # Конкретный тип
            time = get_next_battle_time(battle_type)
            if time:
                now = datetime.now()
                delta = time - now
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                
                await message.reply(
                    f"⏰ Ближайшая {battle_type.capitalize()}:\n"
                    f"Время: {time.strftime('%H:%M')}\n"
                    f"Осталось: {hours}ч {minutes}м"
                )
            else:
                await message.reply(f"❌ Не нашел расписание для {battle_type}")

@dp.callback_query(F.data == "senior")
async def show_senior(callback: types.CallbackQuery):
    senior_team = "👑 Старший состав семьи:\n\n"
    senior_team += "Глава: @Dniper_Dynasty\n"
    senior_team += "Зам. главы: @Zam\n"
    senior_team += "Совет: @Sovet1, @Sovet2\n"
    senior_team += "Капитаны: @Kap1, @Kap2"
    
    await callback.message.edit_text(
        senior_team,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "schedule")
async def show_schedule(callback: types.CallbackQuery):
    schedule = "📅 Расписание битв:\n\n"
    schedule += "🔸 Вышка: 8:00-24:00, каждый час в :35\n"
    schedule += "🔸 Ферма: каждый час в :40\n"
    schedule += "🔸 Завод: каждый час в :45\n"
    schedule += "🔸 Контейнеры: 10:30-23:30, каждый час в :30\n\n"
    schedule += "⏰ За 5-10 минут до начала бот будет спамить уведомления!"
    
    await callback.message.edit_text(
        schedule,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "help")
async def show_help(callback: types.CallbackQuery):
    help_text = "ℹ️ Помощь новичкам:\n\n"
    help_text += "1️⃣ Установи игру Black Russia\n"
    help_text += "2️⃣ Свяжись с @Dniper_Dynasty для вступления\n"
    help_text += "3️⃣ Скачай Discord для координации\n"
    help_text += "4️⃣ Участвуй в битвах и фарме\n\n"
    help_text += "📌 Полезные ссылки:\n"
    help_text += "• Гайды: https://t.me/...\n"
    help_text += "• Правила: https://t.me/...\n\n"
    help_text += "❓ Вопросы? Пиши старшим!"
    
    await callback.message.edit_text(
        help_text,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_menu")
async def show_admin_menu(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⚙️ Админ панель:\n\nВыбери действие:",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_mailing")
async def admin_mailing(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "✍️ Введи текст для рассылки всем пользователям бота:"
    )
    await state.set_state(AdminStates.waiting_for_announcement)
    await callback.answer()

@dp.message(AdminStates.waiting_for_announcement)
async def process_mailing(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа!")
        return
    
    # Рассылка всем пользователям
    count = 0
    for user_id in data["users"]:
        try:
            await bot.send_message(
                int(user_id),
                f"📢 Объявление от администрации:\n\n{message.text}"
            )
            count += 1
        except:
            pass
    
    add_log("Рассылка", message.from_user.id, f"Отправлено {count} пользователям")
    await message.answer(f"✅ Рассылка отправлена {count} пользователям!")
    await state.clear()

@dp.callback_query(F.data == "admin_collect")
async def admin_collect(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⚔️ Сбор на битву!\n\n"
        "Введи текст приглашения:"
    )
    await state.set_state(AdminStates.waiting_for_battle_collect)
    await callback.answer()

@dp.message(AdminStates.waiting_for_battle_collect)
async def process_collect(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа!")
        return
    
    # Отправляем в группу
    await bot.send_message(
        GROUP_ID,
        f"⚔️ СРОЧНЫЙ СБОР НА БИТВУ!\n\n{message.text}\n\n"
        "🕐 Время: ближайший захват\n"
        "📍 Сбор у базы\n"
        "💪 Кто готов - пиши '+готов' в чат!"
    )
    
    # Рассылка в личку всем
    count = 0
    for user_id in data["users"]:
        try:
            await bot.send_message(
                int(user_id),
                f"⚔️ СБОР НА БИТВУ!\n\n{message.text}"
            )
            count += 1
        except:
            pass
    
    add_log("Сбор на битву", message.from_user.id, f"Оповещено {count} человек")
    await message.answer(f"✅ Оповещение отправлено в группу и {count} пользователям!")
    await state.clear()

@dp.callback_query(F.data == "admin_lottery")
async def admin_lottery(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎰 Лотерея!\n\n"
        "Введи сообщение для розыгрыша:"
    )
    await state.set_state(AdminStates.waiting_for_lottery_message)
    await callback.answer()

@dp.message(AdminStates.waiting_for_lottery_message)
async def process_lottery(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа!")
        return
    
    # Отправляем в группу
    await bot.send_message(
        GROUP_ID,
        f"🎰 РОЗЫГРЫШ!\n\n{message.text}\n\n"
        "Участвуйте в розыгрыше! Просто напишите 'участвую' в чате!\n"
        "🎁 Победитель будет выбран через 5 минут!"
    )
    
    add_log("Лотерея", message.from_user.id, f"Запущен розыгрыш")
    await message.answer("✅ Розыгрыш запущен в группе!")
    await state.clear()

@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    # Показываем последние 10 логов
    logs_text = "📋 Последние действия:\n\n"
    for log in data["logs"][-10:]:
        logs_text += f"• {log['time']} - {log['nick']} [{log['action']}]\n"
        if log['details']:
            logs_text += f"  {log['details']}\n"
    
    if len(logs_text) > 4000:
        logs_text = logs_text[:3990] + "..."
    
    await callback.message.edit_text(
        logs_text,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👋 Добро пожаловать в бот семьи Dniper Dynasty!\n\n"
        "Выбери нужный раздел:",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

# ===== АВТОМАТИЧЕСКОЕ ОПОВЕЩЕНИЕ О БИТВАХ =====
async def battle_notifier():
    """Фоновая задача для оповещения о битвах"""
    while True:
        try:
            now = datetime.now()
            current_minute = now.strftime("%M")
            
            # Проверяем каждые 30 секунд
            if current_minute in ["25", "26", "27", "28", "29"]:
                # За 5-10 минут до битвы
                for battle_type, times in battle_times.items():
                    # Проверяем, есть ли битва через 5-10 минут
                    next_time = get_next_battle_time(battle_type)
                    if next_time:
                        delta = next_time - now
                        if 5*60 <= delta.seconds <= 10*60:
                            # Спамим в группу 3-5 сообщений
                            messages = [
                                f"⚠️ {battle_type.upper()} ЧЕРЕЗ 5-10 МИНУТ!",
                                f"⚔️ ГОТОВИМСЯ К {battle_type.upper()}!",
                                f"🔔 ВНИМАНИЕ! {battle_type.upper()} СКОРО!",
                                f"💪 СБОР НА {battle_type.upper()}!",
                                f"🎯 {battle_type.upper()} НАЧИНАЕТСЯ!"
                            ]
                            for msg in messages[:3]:  # Отправляем 3 сообщения
                                await bot.send_message(GROUP_ID, msg)
                                await asyncio.sleep(2)
            
            # Проверка на начало битвы
            battles = check_battle_start()
            if battles:
                for battle in battles:
                    await bot.send_message(
                        GROUP_ID,
                        f"🚨 {battle.upper()} НАЧАЛАСЬ!\n"
                        f"⌛ Время: {datetime.now().strftime('%H:%M')}\n"
                        f"💪 ВСЕ НА БИТВУ!"
                    )
                    await asyncio.sleep(1)
            
            await asyncio.sleep(30)  # Проверяем каждые 30 секунд
        except Exception as e:
            logging.error(f"Error in notifier: {e}")
            await asyncio.sleep(60)

# ===== СТАРТ =====
async def main():
    # Запускаем фоновую задачу
    asyncio.create_task(battle_notifier())
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
