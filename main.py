import os, logging, asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from database import Database
from datetime import datetime, timedelta
import threading
from dotenv import load_dotenv
from http.server import HTTPServer, BaseHTTPRequestHandler


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"✅ Health check server started on port {port}")
    server.serve_forever()


logger = logging.getLogger(__name__)
logging.getLogger('aiogram').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
db = Database()
dp = Dispatcher()
load_dotenv()
bot = Bot(token=os.getenv("BOT_TOKEN"))
ADMIN_IDS = [5140862195, 5135358368]

async def access_middleware(handler, event: types.Message, data: dict):
    user_id = event.from_user.id
    command = event.text.split()[0] if event.text and event.text.startswith('/') else ''
    allowed_without_approval = ['/start', '/help', '/myid']
    if command in allowed_without_approval:
        return await handler(event, data)
    if command.startswith('/approve_') or command in ['/admin', '/users']:
        if user_id in ADMIN_IDS:
            return await handler(event, data)
        await event.answer("❌ Нет прав")
        return None
    if not db.is_user_approved(user_id):
        status = db.get_user_status(user_id)
        if status == 'pending':
            await event.answer("⏳ Ожидайте одобрения админом")
        elif status is None:
            await event.answer("📝 Сначала отправьте /start")
        return None
    return await handler(event, data)
dp.message.middleware(access_middleware)

async def notify_admins_about_new_user(user_id: int, user_name: str):
    message_text = (
        f"🆕 *Новый пользователь*\n\n👤 *Имя:* {user_name}\n🆔 *ID:* `{user_id}`\n\nДля одобрения:\n\n`/approve_{user_id}`")
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, message_text, parse_mode='Markdown')
            logger.info(f"Уведомление админу {admin_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {e}")

async def notify_user_approved(user_id: int):
    try:
        await bot.send_message(
            user_id,
            text="✅ *Ваша заявка одобрена!*\n\nИспользуйте /start для команд")
    except Exception as e:
        logger.error(f"Не удалось уведомить {user_id}: {e}")

box_start = ReplyKeyboardMarkup(
    resize_keyboard=True,
    one_time_keyboard=False,
    keyboard=[
        [
            KeyboardButton(text='📅 Расписание'),
            KeyboardButton(text='📚 ДЗ')
        ]
    ]
)

@dp.message(Command("admin_schedule"))
async def admin_schedule_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder = InlineKeyboardBuilder()
    for i, day in enumerate(days):
        builder.button(text=f"{day} 📅", callback_data=f"admin_schedule_day_{i}")
    builder.button(text="📅 Сегодня", callback_data="admin_schedule_today")
    builder.button(text="📅 Завтра", callback_data="admin_schedule_tomorrow")
    builder.button(text="📅 На неделю", callback_data="admin_schedule_week")
    builder.adjust(4, 3, 3)
    await message.answer(text="⚙️ <b>Админ-панель: Расписание</b>\n\nВыберите действие:", parse_mode='HTML', reply_markup=builder.as_markup())


@dp.callback_query(lambda c: c.data.startswith('admin_schedule_') or c.data == 'back_to_admin_schedule')
async def handle_admin_schedule_callback(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    data = callback.data
    if data == "admin_schedule_today":
        await handle_today_schedule_admin(callback)
    elif data == "admin_schedule_tomorrow":
        await handle_tomorrow_schedule_admin(callback)
    elif data == "admin_schedule_week":
        await handle_week_schedule_admin(callback)
    elif data.startswith("admin_schedule_day_"):
        day_num = int(data.split("_")[-1])
        await handle_day_schedule_admin(callback, day_num)
    elif data == "back_to_admin_schedule":  # ← ДОБАВЬТЕ ЭТУ СТРОЧКУ
        await back_to_admin_schedule_handler(callback)
        return  # Возвращаемся, чтобы не вызывать callback.answer() дважды
    await callback.answer()

async def handle_today_schedule_admin(callback: types.CallbackQuery):
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    day_name = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][today.weekday()]
    image_path = db.get_actual_schedule_image(date_str)
    if image_path and os.path.exists(image_path):
        photo = FSInputFile(image_path)
        await callback.message.answer_photo(
            photo=photo,
            caption=f"📅 <b>Актуальное расписание на сегодня ({date_str})</b>\nИспользуйте /upload_date {date_str} для обновления",
            parse_mode='HTML'
        )
    else:
        builder = InlineKeyboardBuilder()
        builder.button(text="📤 Загрузить на сегодня", callback_data=f"upload_today_{date_str}")
        await callback.message.answer(text="📅 <b>Расписание на сегодня ({day_name})</b>\n\n"
            f"Дата: {date_str}\nСтатус: ❌ Не загружено\n\nНажмите кнопку ниже чтобы загрузить:",
            parse_mode='HTML', reply_markup=builder.as_markup()
        )

async def handle_tomorrow_schedule_admin(callback: types.CallbackQuery):
    tomorrow = datetime.now() + timedelta(days=1)
    date_str = tomorrow.strftime("%Y-%m-%d")
    day_name = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][tomorrow.weekday()]
    image_path = db.get_actual_schedule_image(date_str)
    if image_path and os.path.exists(image_path):
        photo = FSInputFile(image_path)
        await callback.message.answer_photo(
            photo=photo, caption=f"📅 <b>Актуальное расписание на завтра ({date_str})</b>", parse_mode='HTML'
        )
    else:
        builder = InlineKeyboardBuilder()
        builder.button(text="📤 Загрузить на завтра", callback_data=f"upload_date_{date_str}")
        await callback.message.answer(
            f"📅 <b>Расписание на завтра ({day_name})</b>\n\n"
            f"Дата: {date_str}\n"
            f"Статус: ❌ Не загружено\n",
            parse_mode='HTML',
            reply_markup=builder.as_markup()
        )

async def handle_day_schedule_admin(callback: types.CallbackQuery, day_num: int):
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
    day_name = days[day_num]
    has_all = db.get_schedule_image(day_num, "all") and os.path.exists(db.get_schedule_image(day_num, "all"))
    status_text = f"📅 <b>{day_name}</b>\n\n"
    status_text += f"📁 Все недели: {'✅' if has_all else '❌'}\n"
    builder = InlineKeyboardBuilder()
    if has_all:
        builder.button(text="👁️ Показать (все)", callback_data=f"show_day_{day_num}_all")
    builder.button(text="📤 Загрузить (все)", callback_data=f"upload_day_{day_num}_all")
    builder.button(text="↩️ Назад", callback_data="back_to_admin_schedule")
    builder.adjust(2, 1)
    await callback.message.edit_text(status_text, parse_mode='HTML', reply_markup=builder.as_markup())

async def handle_week_schedule_admin(callback: types.CallbackQuery):
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
    status_text = "🗓️ <b>Статус расписания на неделю:</b>\n\n"
    for day_num in range(6):
        has_all = db.get_schedule_image(day_num, "all") and os.path.exists(db.get_schedule_image(day_num, "all"))
        status_text += f"{days[day_num]}: {'✅' if has_all else '❌'}\n"
    status_text += "\nНажмите на день для управления"
    builder = InlineKeyboardBuilder()
    for i, day in enumerate(days):
        builder.button(text=f"{day}", callback_data=f"admin_schedule_day_{i}")
    builder.button(text="📤 Загрузить всю неделю", callback_data="upload_whole_week")
    builder.button(text="↩️ Назад", callback_data="back_to_admin_schedule")
    builder.adjust(6, 1, 1)
    await callback.message.edit_text(status_text, parse_mode='HTML', reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data.startswith('upload_today_'))
async def upload_today_callback(callback: types.CallbackQuery):
    date = callback.data.split('_')[-1]
    upload_state[callback.from_user.id] = {'type': 'date', 'date': date}
    await callback.message.answer(text="📤 <b>Загрузка расписания на сегодня:</b>\n\nДата: {date}\n\n<i>Отправьте фото расписания...</i>", parse_mode='HTML')
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'upload_whole_week')
async def upload_whole_week_callback(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Все недели", callback_data="upload_week_all")
    builder.button(text="📤 Чётные недели", callback_data="upload_week_even")
    builder.button(text="📤 Нечётные недели", callback_data="upload_week_odd")
    builder.button(text="↩️ Назад", callback_data="back_to_admin_schedule")
    builder.adjust(1, 1, 1, 1)
    await callback.message.edit_text(text="📤 <b>Загрузка недельного расписания</b>\n\nВыберите тип недели:",
        parse_mode='HTML', reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('upload_week_'))
async def upload_week_callback(callback: types.CallbackQuery):
    week_type = callback.data.split('_')[-1]
    upload_state[callback.from_user.id] = {
        'type': 'week',
        'week_type': week_type
    }
    week_type_names = {
        "all": "все недели",
        "even": "чётные недели",
        "odd": "нечётные недели"
    }
    await callback.message.answer(text=f"🗓️ <b>Загрузка недельного расписания</b>\n\nТип: {week_type_names[week_type]}\n\n"
        f"<i>Отправьте фото расписания на всю неделю...</i>",parse_mode='HTML')
    await callback.answer()


@dp.callback_query(lambda c: c.data == 'back_to_admin_schedule')
async def back_to_admin_schedule_handler(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет прав")
        return
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Пн 📅", callback_data="admin_schedule_day_0"),
                InlineKeyboardButton(text="Вт 📅", callback_data="admin_schedule_day_1"),
                InlineKeyboardButton(text="Ср 📅", callback_data="admin_schedule_day_2"),
                InlineKeyboardButton(text="Чт 📅", callback_data="admin_schedule_day_3"),
            ],
            [
                InlineKeyboardButton(text="Пт 📅", callback_data="admin_schedule_day_4"),
                InlineKeyboardButton(text="Сб 📅", callback_data="admin_schedule_day_5"),
                InlineKeyboardButton(text="Вс 📅", callback_data="admin_schedule_day_6"),
            ],
            [
                InlineKeyboardButton(text="📅 Сегодня", callback_data="admin_schedule_today"),
                InlineKeyboardButton(text="📅 Завтра", callback_data="admin_schedule_tomorrow"),
                InlineKeyboardButton(text="📅 На неделю", callback_data="admin_schedule_week"),
            ]
        ])
        await callback.message.edit_text(text="⚙️ <b>Админ-панель: Расписание</b>\n\nВыберите действие:", parse_mode='HTML', reply_markup=keyboard)
        await callback.answer("⬅️ Возврат в меню")
    except Exception as e:
        print(f"Ошибка при редактировании: {e}")
        await callback.message.answer(text="⚙️ <b>Админ-панель: Расписание</b>\n\nВыберите действие:", parse_mode='HTML', reply_markup=keyboard)
        await callback.answer()

@dp.message(lambda m: m.text == '⚙️ Админ-панель')
async def admin_panel_button(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await admin_schedule_panel(message)

@dp.message(Command("start"))
async def start(message: types.Message):
    full_name = message.from_user.full_name
    user_id = message.from_user.id

    if not db.user_exists(user_id):
        db.add_user(user_id=user_id, username=message.from_user.username, full_name=full_name)
        await message.answer("📝 Ваша заявка отправлена на рассмотрение.\nОжидайте подтверждения.")
        if user_id not in ADMIN_IDS:
            await notify_admins_about_new_user(user_id, full_name)
    else:
        status = db.get_user_status(user_id)
        if status == 'approved':
            if user_id in ADMIN_IDS:
                admin_menu = ReplyKeyboardMarkup(
                    resize_keyboard=True, keyboard=[
                        [
                            KeyboardButton(text='📅 Расписание'),
                            KeyboardButton(text='⚙️ Редакция Расписания')
                        ],
                        [
                            KeyboardButton(text='👥 Пользователи'),
                            KeyboardButton(text='📚 ДЗ'),
                        ]
                    ]
                )
                await message.answer(text="👑 <b>Админ-панель</b>\n\n<b>Доступные команды:</b>\n"
                    '┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n\n'
                    f"• /admin_schedule - управление расписанием\n"
                    f"• /users - список пользователей\n"
                    f"• /broadcast - рассылка\n\n"
                    '┗━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n'
                    f"Или используйте кнопки ниже.\n\nДоброго времени суток, {full_name}! Вот список быстрых команд:\n\n"
                    '┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n\n'
                    '  ➀: [ /Schedule ] ― Нажми, чтобы увидеть расписание.\n'
                    '  ➁: [ /HomeWork ] ― Нажми, чтобы узнать Д/З.\n'
                    '┗━━━━━━━━━━━━━━━━━━━━━━━━━━━┛', parse_mode='HTML', reply_markup=admin_menu
                )
            else:
                await message.answer(parse_mode='HTML', reply_markup=box_start,
                    text=f'Доброго времени суток, {full_name}! Вот список быстрых команд:\n\n'
                         '┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n\n'
                         '  ➀: [ /Schedule ] ― Нажми, чтобы увидеть расписание.\n'
                         '  ➁: [ /HomeWork ] ― Нажми, чтобы узнать Д/З.\n'
                         '┗━━━━━━━━━━━━━━━━━━━━━━━━━━━┛',
                )
        else:
            await message.answer("⏳ Ваша заявка еще на рассмотрении.")

@dp.message(lambda message: message.text and message.text.startswith("/approve_"))
async def approve_user_command(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    try:
        target_user_id = int(message.text.replace("/approve_", "").strip())
        db.approve_user(target_user_id)
        await message.answer(f"✅ Пользователь `{target_user_id}` одобрен.", parse_mode='Markdown')
        await notify_user_approved(target_user_id)
    except:
        await message.answer("❌ Неверный формат команды")

@dp.message(Command("Schedule"))
async def schedule_handler(message: types.Message):
    tomorrow = datetime.now() + timedelta(days=1)
    date_str = tomorrow.strftime("%Y-%m-%d")
    image_path = db.get_actual_schedule_image(date_str)
    if image_path and os.path.exists(image_path):
        try:
            photo = FSInputFile(image_path)
            await bot.send_photo(chat_id=message.chat.id, photo=photo, caption=f"📅 <b>Актуальное расписание на {tomorrow.strftime('%d.%m.%Y')}</b>", parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            logging.error(f"Ошибка отправки фото: {e}")
    day_of_week = tomorrow.weekday()
    image_path = db.get_schedule_image(day_of_week)
    if not image_path:
        image_path = db.get_schedule_image(day_of_week)
    if image_path and os.path.exists(image_path):
        try:
            photo = FSInputFile(image_path)
            await bot.send_photo(chat_id=message.chat.id, photo=photo, caption=f"📅 <b>Расписание на {tomorrow.strftime('%d.%m.%Y')}</b>", parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            logging.error(f"Ошибка отправки фото: {e}")
    await message.answer(text="📅 <b>Расписание на {today.strftime('%d.%m.%Y')}</b>\n\nФото расписания пока не загружено.\nАдминистратор скоро его добавит!", parse_mode=ParseMode.HTML)

@dp.message(Command("upload_schedule"))
async def upload_schedule_help(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    help_text = ("📤 <b>Загрузка расписания:</b>\n\n1. <b>Основное расписание на день:</b>\n"
        "<code>/upload_day 0</code> — загрузить фото для понедельника\n0-пн, 1-вт, 2-ср, 3-чт, 4-пт, 5-сб\n\n"
        "2. <b>Актуальное расписание на дату:</b>\n<code>/upload_date 2024-01-15</code> — загрузить фото на 15 января\n\n"
        "3. <b>С указанием типа недели:</b>\n<code>/upload_day 0 even</code> — для чётной недели\n"
        "<code>/upload_day 0 odd</code> — для нечётной\n\n<i>После команды отправьте фото расписания</i>")
    await message.answer(help_text, parse_mode=ParseMode.HTML)
upload_state = {}  # {user_id: {'type': 'day/date', 'day': 0, 'week_type': 'all'}}

@dp.callback_query(lambda c: c.data.startswith('show_day_'))
async def show_schedule_callback(callback: types.CallbackQuery):
    _, _, day_num, week_type = callback.data.split('_')
    day_num = int(day_num)
    image_path = db.get_schedule_image(day_num, week_type)
    if image_path and os.path.exists(image_path):
        photo = FSInputFile(image_path)
        days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
        await callback.message.answer_photo(photo=photo, caption=f"📅 <b>{days[day_num]} ({week_type})</b>", parse_mode='HTML')
        await callback.answer()
    else:
        await callback.answer("❌ Файл не найден", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith('upload_day_'))
async def start_upload_callback(callback: types.CallbackQuery):
    _, _, day_num, week_type = callback.data.split('_')
    day_num = int(day_num)
    upload_state[callback.from_user.id] = {'type': 'day', 'day': day_num, 'week_type': week_type}
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
    await callback.message.answer(text="📤 <b>Загрузка расписания:</b>\n\nДень: {days[day_num]}\nТип недели: {week_type}\n\n"
        f"<i>Отправьте фото расписания...</i>", parse_mode='HTML')
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('upload_date_'))
async def start_upload_date_callback(callback: types.CallbackQuery):
    date = callback.data.split('_')[-1]
    upload_state[callback.from_user.id] = {'type': 'date', 'date': date}
    await callback.message.answer(text="📤 <b>Загрузка актуального расписания:</b>\n\nДата: {date}\n\n<i>Отправьте фото расписания...</i>",
        parse_mode='HTML')
    await callback.answer()

@dp.message(lambda m: m.photo)
async def handle_photo_upload(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    user_id = message.from_user.id
    if user_id not in upload_state:
        return
    state = upload_state[user_id]
    try:
        os.makedirs("schedules", exist_ok=True)
        photo = message.photo[-1]
        file_id = photo.file_id
        file = await bot.get_file(file_id)
        if state['type'] == 'day':
            filename = f"schedules/day_{state['day']}_{state['week_type']}.jpg"
            db.add_schedule_image(state['day'], filename, state['week_type'])
            days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
            builder = InlineKeyboardBuilder()
            builder.button(text="👁️ Показать", callback_data=f"show_day_{state['day']}_{state['week_type']}")
            builder.button(text="⚙️ Управление днем", callback_data=f"admin_schedule_day_{state['day']}")
            await message.answer(text=f"✅ <b>Расписание сохранено!</b>\n\nДень: {days[state['day']]}\n"
                f"Тип недели: {state['week_type']}", parse_mode='HTML', reply_markup=builder.as_markup())
        elif state['type'] == 'week':  # ← ДОБАВЛЕНО ДЛЯ НЕДЕЛЬНОГО РАСПИСАНИЯ
            filename = f"schedules/week_{state['week_type']}.jpg"
            db.add_week_schedule(filename, state['week_type'])
            week_type_names = {"all": "все недели"}
            await message.answer(text=f"✅ <b>Недельное расписание сохранено!</b>\n\nТип: {week_type_names[state['week_type']]}\n\n"
                f"Теперь пользователи могут использовать команду /week", parse_mode='HTML')
        else:  # date
            filename = f"schedules/date_{state['date']}.jpg"
            db.add_actual_schedule_image(state['date'], filename)
            await message.answer(text=f"✅ <b>Актуальное расписание сохранено!</b>\n\nДата: {state['date']}\n"
                f"Теперь пользователи увидят его при запросе.", parse_mode='HTML')
        await bot.download_file(file.file_path, filename)
        del upload_state[user_id]
    except Exception as e:
        await message.answer(f"❌ <b>Ошибка:</b>\n{str(e)}", parse_mode='HTML')

@dp.message(lambda m: m.text == '👥 Пользователи')
async def users_button(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        db.cursor.execute("SELECT user_id, full_name, username, status FROM users")
        users = db.cursor.fetchall()
        if not users:
            await message.answer("📭 В базе данных нет пользователей.")
            return
        response = "👥 <b>Список пользователей:</b>\n\n"
        pending_count = 0
        approved_count = 0
        for user in users:
            user_id_db, full_name, username, status = user
            status_icon = "✅" if status == 'approved' else "⏳"
            if status == 'pending':
                pending_count += 1
            else:
                approved_count += 1
            response += f"{status_icon} <code>{user_id_db}</code> — {full_name}"
            if username:
                response += f" (@{username})"
            response += f" — <b>{status}</b>\n"
        response += f"\n📊 <b>Статистика:</b>\n"
        response += f"✅ Одобрено: {approved_count}\n"
        response += f"⏳ Ожидают: {pending_count}\n"
        response += f"📈 Всего: {len(users)}"
        await message.answer(response, parse_mode='HTML')
    else:
        await message.answer("❌ Эта функция только для администраторов")

@dp.message(lambda m: m.text == '📅 Расписание')
async def schedule_button(message: types.Message):
    await schedule_handler(message)

@dp.message(Command("week"))
async def week_schedule_handler(message: types.Message):
    today = datetime.now()
    image_path = db.get_week_schedule()
    if not image_path:
        image_path = db.get_week_schedule("all")
    if image_path and os.path.exists(image_path):
        try:
            photo = FSInputFile(image_path)
            await bot.send_photo(chat_id=message.chat.id,photo=photo, caption=f"🗓️ <b>Расписание на неделю</b>\n",parse_mode='HTML')
            return
        except Exception as e:
            logging.error(f"Ошибка отправки недельного фото: {e}")
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
    response = "🗓️ <b>Расписание на неделю:</b>\n\n"
    for day_num in range(6):
        day_image = db.get_schedule_image(day_num)
        if not day_image:
            day_image = db.get_schedule_image(day_num, "all")
        if day_image and os.path.exists(day_image):
            response += f"✅ {days[day_num]} — есть расписание\n"
        else:
            response += f"❌ {days[day_num]} — нет расписания\n"
    response += "\nИспользуйте /day [0-5] для конкретного дня\n(0-пн, 1-вт, 2-ср, 3-чт, 4-пт, 5-сб)"
    await message.answer(response, parse_mode='HTML')

@dp.message(Command("day"))
async def day_schedule_handler(message: types.Message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer(text="📅 <b>Используйте:</b> /day [0-5]\n\n<b>Дни недели:</b>\n"
                "0 — Понедельник\n1 — Вторник\n2 — Среда\n3 — Четверг\n4 — Пятница\n5 — Суббота", parse_mode='HTML')
            return
        day_num = int(parts[1])
        if day_num < 0 or day_num > 5:
            await message.answer("❌ День должен быть от 0 (пн) до 5 (сб)")
            return
        days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
        day_name = days[day_num]
        today = datetime.now()
        week_num = today.isocalendar()[1]
        week_type = "even" if week_num % 2 == 0 else "odd"
        image_path = db.get_schedule_image(day_num, week_type)
        if not image_path:
            image_path = db.get_schedule_image(day_num, "all")
        if image_path and os.path.exists(image_path):
            photo = FSInputFile(image_path)
            await bot.send_photo(chat_id=message.chat.id, photo=photo,
                caption=f"📅 <b>Расписание на {day_name}</b>\nНеделя: {'чётная' if week_type == 'even' else 'нечётная'}", parse_mode='HTML')
        else:
            await message.answer(text=f"📅 <b>Расписание на {day_name}</b>\n\nНа этот день расписание пока не загружено.", parse_mode='HTML')
    except ValueError:
        await message.answer("❌ Используйте число: /day 0 (где 0 - понедельник)")

@dp.message(lambda m: m.text == '📚 ДЗ')
async def homework_handler(message: types.Message):
    await message.answer("📚 Функция ДЗ в разработке")

@dp.callback_query()
async def unknown_callback_handler(callback: types.CallbackQuery):
    print(f"DEBUG: Неизвестный коллбэк: {callback.data}")
    await callback.answer(f"❌ Кнопка '{callback.data}' еще не настроена", show_alert=True)

@dp.message(Command("add_schedule"))
async def add_schedule_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Эта команда только для администраторов")
        return
    help_text = ("📝 <b>Добавление расписания:</b>\n\nФормат команды:\n"
        "<code>/add_day день_недели номер_пары предмет время аудитория</code>\n\nПример:\n"
        "<code>/add_day 0 1 Математика 9:00-10:30 301</code>\n\nДни недели:\n0 - Понедельник, 1 - Вторник, ... 5 - Суббота")
    await message.answer(help_text, parse_mode='HTML')

@dp.message(lambda m: m.text and m.text.startswith('/add_day'))
async def add_day_schedule(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        if len(parts) < 6:
            await message.answer("❌ Недостаточно параметров")
            return
        day_of_week = int(parts[1])
        lesson_num = int(parts[2])
        subject = parts[3]
        time_range = parts[4]
        classroom = parts[5]
        if '-' in time_range:
            time_start, time_end = time_range.split('-')
        else:
            time_start = time_range
            time_end = ""
        await message.answer(f"✅ Пара добавлена:\nДень: {day_of_week}\nПара #{lesson_num}: {subject}\n"
            f"Время: {time_start}-{time_end}\nАудитория: {classroom}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


async def main():
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    print("🚀 Telegram bot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
