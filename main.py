import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import json
import os
import re
import signal
import sys

# ===== КОНФИГ =====
BOT_TOKEN = "8960201604:AAF7tEwH2jZGEoF9AFsy-RUkaDPm8SqnE3o"
GROUP_ID = -1003974555455  # ID группы
ADMIN_ID = 8478884644

# ===== ИНИЦИАЛИЗАЦИЯ =====
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

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
        "last_battle_check": None,
        "senior_team": {
            "leader": "@Sniper_Dynasty",
            "deputy": "@Zam",
            "council": "@Sovet1, @Sovet2",
            "captains": "@Kap1, @Kap2"
        }
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
    waiting_for_senior_edit = State()

class NickStates(StatesGroup):
    waiting_for_nick = State()

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
        [InlineKeyboardButton(text="✏️ Редактировать состав", callback_data="admin_edit_senior")],
        [InlineKeyboardButton(text="📋 Логи действий", callback_data="admin_logs")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])

def get_senior_edit_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Глава", callback_data="edit_leader")],
        [InlineKeyboardButton(text="⭐ Зам. главы", callback_data="edit_deputy")],
        [InlineKeyboardButton(text="📋 Совет", callback_data="edit_council")],
        [InlineKeyboardButton(text="⚔️ Капитаны", callback_data="edit_captains")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu")]
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
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    times = battle_times.get(battle_type.lower(), [])
    if not times:
        return None
    
    for t in sorted(times):
        if t > current_time:
            hour, minute = map(int, t.split(':'))
            battle_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if battle_time < now:
                battle_time += timedelta(days=1)
            return battle_time
    
    hour, minute = map(int, times[0].split(':'))
    battle_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    battle_time += timedelta(days=1)
    return battle_time

def check_battle_start():
    now = datetime.now().strftime("%H:%M")
    battles = []
    for battle_type, times in battle_times.items():
        if now in times:
            battles.append(battle_type)
    return battles

# ===== ОБРАБОТЧИК ОСТАНОВКИ =====
def signal_handler(sig, frame):
    print('\nБот остановлен')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ===== ХЕНДЛЕРЫ =====

# === Стартовые команды ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type == "private":
        await message.answer(
            "👋 Добро пожаловать в бот семьи Sniper Dynasty!\n\n"
            "Выбери нужный раздел:",
            reply_markup=get_main_keyboard()
        )
        add_log("Запуск бота", message.from_user.id)

# === Смена ника ===
@dp.message(Command("add_nick"))
async def cmd_add_nick(message: types.Message, command: CommandObject):
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

# === Обработка сообщений в группе ===
@dp.message(F.chat.id == GROUP_ID)
async def group_message_handler(message: types.Message):
    text = message.text.lower() if message.text else ""
    
    # Проверка вопроса про битвы
    battle_keywords = ["вышка", "ферма", "завод", "контейнер"]
    
    if any(keyword in text for keyword in battle_keywords):
        battle_type = None
        for key in battle_keywords:
            if key in text:
                battle_type = key
                break
        
        if battle_type:
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

# === Старший состав ===
@dp.callback_query(F.data == "senior")
async def show_senior(callback: types.CallbackQuery):
    senior = data["senior_team"]
    senior_team = "👑 Старший состав Sniper Dynasty:\n\n"
    senior_team += f"👑 Глава: {senior['leader']}\n"
    senior_team += f"⭐ Зам. главы: {senior['deputy']}\n"
    senior_team += f"📋 Совет: {senior['council']}\n"
    senior_team += f"⚔️ Капитаны: {senior['captains']}"
    
    await callback.message.edit_text(
        senior_team,
        reply_markup=get_back_keyboard()
    )
    await callback.answer()

# === Расписание ===
@dp.callback_query(F.data == "schedule")
async def show_schedule(callback: types.CallbackQuery):
    schedule = "📅 Расписание битв Sniper Dynasty:\n\n"
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

# === Помощь новичкам ===
@dp.callback_query(F.data == "help")
async def show_help(callback: types.CallbackQuery):
    help_text = "ℹ️ Помощь новичкам Sniper Dynasty:\n\n"
    help_text += "1️⃣ Установи игру Black Russia\n"
    help_text += "2️⃣ Свяжись с главой для вступления\n"
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

# === Админ меню ===
@dp.callback_query(F.data == "admin_menu")
async def show_admin_menu(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⚙️ Админ панель Sniper Dynasty:\n\nВыбери действие:",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

# === Рассылка ===
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
    
    # Проверяем, есть ли пользователи
    if not data["users"]:
        await message.answer("❌ Нет пользователей для рассылки!")
        await state.clear()
        return
    
    count = 0
    failed = 0
    
    # Отправляем каждому пользователю
    for user_id in data["users"]:
        try:
            await bot.send_message(
                int(user_id),
                f"📢 Объявление от администрации Sniper Dynasty:\n\n{message.text}"
            )
            count += 1
            await asyncio.sleep(0.1)  # Чтобы не превысить лимиты Telegram
        except Exception as e:
            failed += 1
            logging.error(f"Не удалось отправить сообщение {user_id}: {e}")
    
    add_log("Рассылка", message.from_user.id, f"Отправлено {count}, не доставлено {failed}")
    await message.answer(f"✅ Рассылка завершена!\n📨 Отправлено: {count}\n❌ Не доставлено: {failed}")
    await state.clear()

# === Сбор на битву ===
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
    
    count = 0
    failed = 0
    
    # Рассылка в личку всем
    for user_id in data["users"]:
        try:
            await bot.send_message(
                int(user_id),
                f"⚔️ СБОР НА БИТВУ!\n\n{message.text}"
            )
            count += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1
    
    add_log("Сбор на битву", message.from_user.id, f"Оповещено {count} человек")
    await message.answer(f"✅ Оповещение отправлено!\n📨 В группу и {count} пользователям\n❌ Не доставлено: {failed}")
    await state.clear()

# === Лотерея ===
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
    
    await bot.send_message(
        GROUP_ID,
        f"🎰 РОЗЫГРЫШ В SNIPER DYNASTY!\n\n{message.text}\n\n"
        "Участвуйте в розыгрыше! Просто напишите 'участвую' в чате!\n"
        "🎁 Победитель будет выбран через 5 минут!"
    )
    
    add_log("Лотерея", message.from_user.id, f"Запущен розыгрыш")
    await message.answer("✅ Розыгрыш запущен в группе!")
    await state.clear()

# === Редактирование старшего состава ===
@dp.callback_query(F.data == "admin_edit_senior")
async def admin_edit_senior(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "✏️ Выбери кого хочешь изменить:",
        reply_markup=get_senior_edit_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("edit_"))
async def edit_senior_field(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    field_map = {
        "edit_leader": ("leader", "👑 Глава"),
        "edit_deputy": ("deputy", "⭐ Зам. главы"),
        "edit_council": ("council", "📋 Совет"),
        "edit_captains": ("captains", "⚔️ Капитаны")
    }
    
    field, label = field_map.get(callback.data, (None, None))
    if field:
        await state.update_data(edit_field=field)
        await callback.message.edit_text(
            f"✏️ Введи новое значение для {label}:\n"
            f"Текущее: {data['senior_team'][field]}"
        )
        await state.set_state(AdminStates.waiting_for_senior_edit)
    
    await callback.answer()

@dp.message(AdminStates.waiting_for_senior_edit)
async def process_senior_edit(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа!")
        return
    
    data_state = await state.get_data()
    field = data_state.get("edit_field")
    
    if field:
        old_value = data["senior_team"][field]
        data["senior_team"][field] = message.text
        save_data(data)
        add_log("Изменение состава", message.from_user.id, f"{field}: {old_value} → {message.text}")
        
        await message.answer(f"✅ {field.capitalize()} успешно обновлен!\nНовое значение: {message.text}")
        await state.clear()
        
        # Возвращаем в админ меню
        await message.answer(
            "⚙️ Админ панель:",
            reply_markup=get_admin_keyboard()
        )

# === Логи ===
@dp.callback_query(F.data == "admin_logs")
async def admin_logs(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    logs_text = "📋 Последние действия:\n\n"
    if not data["logs"]:
        logs_text += "Пока нет записей"
    else:
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

# === Назад ===
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👋 Добро пожаловать в бот семьи Sniper Dynasty!\n\n"
        "Выбери нужный раздел:",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

# ===== АВТОМАТИЧЕСКОЕ ОПОВЕЩЕНИЕ О БИТВАХ =====
async def battle_notifier():
    while True:
        try:
            now = datetime.now()
            current_minute = now.strftime("%M")
            
            # Проверка за 5-10 минут до битвы
            if current_minute in ["25", "26", "27", "28", "29"]:
                for battle_type in battle_times.keys():
                    next_time = get_next_battle_time(battle_type)
                    if next_time:
                        delta = next_time - now
                        if 5*60 <= delta.seconds <= 10*60:
                            messages = [
                                f"⚠️ {battle_type.upper()} ЧЕРЕЗ 5-10 МИНУТ!",
                                f"⚔️ ГОТОВИМСЯ К {battle_type.upper()}!",
                                f"🔔 ВНИМАНИЕ! {battle_type.upper()} СКОРО!",
                            ]
                            for msg in messages:
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
                        f"💪 ВСЕ НА БИТВУ! ВПЕРЕД, SNIPER DYNASTY!"
                    )
                    await asyncio.sleep(1)
            
            await asyncio.sleep(30)
        except Exception as e:
            logging.error(f"Error in notifier: {e}")
            await asyncio.sleep(60)

# ===== СТАРТ =====
async def main():
    # Сбрасываем вебхук и удаляем все ожидающие обновления
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("✅ Webhook удален, старые подключения сброшены")
    except Exception as e:
        logging.error(f"Ошибка при сбросе webhook: {e}")
    
    # Небольшая задержка для очистки
    await asyncio.sleep(1)
    
    # Запускаем фоновую задачу
    asyncio.create_task(battle_notifier())
    
    # Запускаем бота
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
