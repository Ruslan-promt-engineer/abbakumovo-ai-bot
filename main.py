import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
from loguru import logger

from database import init_db, SessionLocal, engine
from models import User, Ticket, CategoryEnum
from llm import analyze_ticket

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")
TENANT_GROUP_ID = os.getenv("TENANT_GROUP_ID")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))  # 0 = доступ запрещён по умолчанию

# 🔹 Инициализация с FSM-хранилищем
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

keyboard_request_contact = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True
)

SMTP_CONFIG = {
    "host": "smtp.mail.ru", "port": 465, "login": "info@lakro.ru",
    "password": "", "from_email": "info@lakro.ru"
}

# 🔹 Состояния для генерации поста
class PostStates(StatesGroup):
    input_topic = State()
    reviewing_draft = State()
    editing_draft = State()

# 🔹 Промпт для генерации поста через ИИ
POST_SYSTEM_PROMPT = """Ты — профессиональный копирайтер и PR-менеджер складского комплекса "Аббакумово".
Твоя задача: написать информативный, структурированный и вежливый пост для Telegram-канала арендаторов.
ПРАВИЛА:
1. Используй эмодзи для визуальной структуры, но не перегружай (3-5 на пост).
2. Чётко выделяй: 📅 Дату, 🕒 Время, 📍 Место/Локацию, 📞 Контакты.
3. Тон: профессиональный, заботливый, без канцеляризмов.
4. Если это объявление об отключении/работах — добавь "Просим заранее подготовиться".
5. В конце добавь подпись "С уважением, администрация СК «Аббакумово», 📞 По вопросам: +7 (991) 635-09-77".
6. Верни ТОЛЬКО готовый текст поста в формате Markdown, без пояснений и кавычек."""

async def generate_post_with_ai(topic: str) -> str:
    """Генерирует пост через YandexGPT"""
    try:
        from llm import ask_yandex_gpt
        # 🔹 Вызываем ИИ с нашим промптом для постов
        return await asyncio.to_thread(
            ask_yandex_gpt, 
            f"Создай пост для канала арендаторов. Тема: {topic}",
            system_prompt=POST_SYSTEM_PROMPT,
            temperature=0.4,  # Чуть креативнее для постов
            max_tokens=1500
        )
    except Exception as e:
        logger.error(f"Ошибка генерации поста: {e}")
        # 🔹 Запасной вариант, если ИИ упал
        return f"📢 **Важная информация**\n\n{topic}\n\n📞 По вопросам: +7 (991) 635-09-77\n\n_С уважением, администрация_"

# 🔹 Функции БД
def get_or_create_user_data(tg_id: int, full_name: str, company_name: str = None, phone: str = None) -> dict:
    with SessionLocal() as session:
        user = session.query(User).filter(User.tg_id == tg_id).first()
        if not user:
            user = User(tg_id=tg_id, full_name=full_name, company_name=company_name, phone=phone)
            session.add(user)
            session.commit()
            session.refresh(user)
        else:
            updated = False
            if company_name and not user.company_name:
                user.company_name = company_name
                updated = True
            if phone and not user.phone:
                user.phone = phone
                updated = True
            if updated:
                session.commit()
                session.refresh(user)
        return {
            "id": user.id, "tg_id": user.tg_id, "full_name": user.full_name,
            "company_name": user.company_name, "phone": user.phone, "role": user.role
        }

def create_ticket(user_id: int, analyzed: dict) -> int:
    with SessionLocal() as session:
        category_map = {
            "электрика": CategoryEnum.ELECTRIC, "сантехника": CategoryEnum.PLUMBING,
            "техническое": CategoryEnum.TECH, "другое": CategoryEnum.OTHER
        }
        category = category_map.get(analyzed.get("category"), CategoryEnum.OTHER)
        ticket = Ticket(
            user_id=user_id, category=category,
            priority=analyzed.get("priority", "средний"),
            description=analyzed.get("description"), status="new"
        )
        session.add(ticket)
        session.commit()
        logger.info(f"Создана заявка #{ticket.id}")
        return ticket.id

def get_ticket_data(ticket_id: int) -> dict:
    with SessionLocal() as session:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket: return None
        return {
            "id": ticket.id, "status": ticket.status, "user_id": ticket.user_id,
            "category": ticket.category, "description": ticket.description,
            "is_important": ticket.is_important,
            "created_at": ticket.created_at
        }

def update_ticket_status(ticket_id: int, new_status: str) -> bool:
    with SessionLocal() as session:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket:
            ticket.status = new_status
            session.commit()
            logger.info(f"Заявка #{ticket_id} переведена в статус: {new_status}")
            return True
        return False

def toggle_ticket_pin(ticket_id: int) -> bool:
    with SessionLocal() as session:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket:
            ticket.is_important = not ticket.is_important
            session.commit()
            logger.info(f"Заявка #{ticket_id} закреплена: {ticket.is_important}")
            return ticket.is_important
        return False

async def send_to_group(text: str, reply_markup=None):
    if ADMIN_GROUP_ID:
        try:
            await bot.send_message(ADMIN_GROUP_ID, text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка отправки в группу: {e}")

def send_email_notification(ticket_dict: dict, user_dict: dict):
    logger.info(f"[EMAIL ЗАГЛУШКА] Заявка #{ticket_dict.get('id')} готова к отправке")
    return True

# =============================================================================
# 🔹 1. КОМАНДЫ (высший приоритет)
# =============================================================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_data = get_or_create_user_data(tg_id=message.from_user.id, full_name=message.from_user.full_name)
    has_phone = bool(user_data.get("phone"))
    base_text = (
        "👋 *Добро пожаловать в сервис заявок СК «Аббакумово»!*\n\n"
        "🤖 Я — ваш виртуальный помощник по техническим и бытовым вопросам.\n\n"
        "📝 *Как создать заявку?*\n"
        "Просто напишите, что случилось. ИИ автоматически:\n"
        "✅ Определит категорию и приоритет\n"
        "✅ Зафиксирует номер офиса и компанию\n"
        "✅ Направит обращение специалисту\n\n"
        "💡 *Примеры:*\n"
        "• Не горит свет в кабинете 302\n"
        "• Протекает кран на 3 этаже, срочно!\n\n"
    )
    if has_phone:
        text = base_text + (f"📞 *Ваш номер:* `{user_data['phone']}`\n\n✅ Контакт сохранён. Опишите проблему!")
        await message.answer(text, parse_mode="Markdown")
    else:
        text = base_text + ("📞 *Для быстрой связи*\nПоделитесь номером, нажав кнопку ниже 👇")
        await message.answer(text, parse_mode="Markdown", reply_markup=keyboard_request_contact)
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

@dp.message(Command("phone"))
async def cmd_phone(message: Message):
    phone = message.text.replace("/phone", "").strip()
    if not phone:
        await message.answer("❌ Укажи телефон. Пример: /phone +7(991)234-34-34")
        return
    with SessionLocal() as session:
        user = session.query(User).filter(User.tg_id == message.from_user.id).first()
        if user:
            user.phone = phone
            session.commit()
            await message.answer(f"✅ Телефон {phone} сохранен!")

@dp.message(F.contact)
async def handle_contact(message: Message):
    phone = message.contact.phone_number
    with SessionLocal() as session:
        user = session.query(User).filter(User.tg_id == message.from_user.id).first()
        if user:
            user.phone = phone
            session.commit()
            await message.answer(f"✅ Телефон {phone} сохранен!", reply_markup=ReplyKeyboardRemove())

# =============================================================================
# 🔹 2. ПОСТ-МЕНЕДЖЕР С ИИ (ВТОРОЙ ПРИОРИТЕТ — ДО handle_text_message!)
# =============================================================================

# =============================================================================
# 🔹 ПОСТ-МЕНЕДЖЕР С ИИ (ИСПРАВЛЕННЫЙ ПОТОК)
# =============================================================================

@dp.message(Command("post"))
async def cmd_new_post(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещён")
        return
    await state.set_state(PostStates.input_topic)
    await message.answer(
        "📝 **Создание поста**\n\n"
        "Напишите тему объявления.\n"
        "Пример: *Отключение воды 25.04 с 10:00*\n"
        "Для отмены: /cancel",
        parse_mode="Markdown"
    )

@dp.message(StateFilter(PostStates.input_topic), F.text)
async def handle_post_topic(message: Message, state: FSMContext):
    if message.text.lower() in ["/cancel", "отмена"]:
        await state.clear()
        await message.answer("❌ Создание поста отменено")
        return
    
    await message.answer("🤖 Генерирую через ИИ... Подождите...")
    draft = await generate_post_with_ai(message.text)
    await state.update_data(draft=draft, original_topic=message.text)
    await state.set_state(PostStates.reviewing_draft)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="post_publish")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_edit")],
        [InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="post_regenerate")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="post_cancel")]
    ])
    await message.answer(f"👀 **Предпросмотр:**\n\n{draft}", parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data.in_(["post_publish", "post_edit", "post_regenerate", "post_cancel"]), StateFilter(PostStates.reviewing_draft))
async def handle_post_buttons(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    draft = data.get("draft")
    original_topic = data.get("original_topic")
    
    if callback.data == "post_cancel":
        await state.clear()
        await callback.message.edit_text("❌ Создание поста отменено")
        await callback.answer()
        return
    
    if callback.data == "post_edit":
        await state.set_state(PostStates.editing_draft)
        
        # 🔹 Клавиатура с кнопкой "Готово"
        finish_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="✅ Готово, показать предпросмотр")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        await callback.message.answer(
            f"✏️ **Редактирование поста**\n\n"
            f"📝 *Скопируй текст ниже, отредактируй и отправь обратно:*\n\n"
            f"```\n{draft}\n```\n\n"
            f"💡 **Инструкция:**\n"
            f"1. Скопируй текст выше (долгий тап → Копировать)\n"
            f"2. Вставь в сообщение и отредактируй\n"
            f"3. Отправь сообщение\n"
            f"4. Или нажми кнопку ниже для отмены",
            parse_mode="Markdown",
            reply_markup=finish_kb
        )
        await callback.answer("✏️ Скопируй текст, отредактируй и отправь обратно")
        return
    
    if callback.data == "post_regenerate":
        await callback.message.edit_text("🔄 Перегенерирую...")
        await callback.answer()
        new_draft = await generate_post_with_ai(original_topic)
        await state.update_data(draft=new_draft)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Опубликовать", callback_data="post_publish")],
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_edit")],
            [InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="post_regenerate")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="post_cancel")]
        ])
        await callback.message.edit_text(f"👀 **Новый вариант:**\n\n{new_draft}", parse_mode="Markdown", reply_markup=kb)
        return

    if callback.data == "post_publish":
        if not CHANNEL_ID:
            await callback.answer("❌ CHANNEL_ID не настроен в .env", show_alert=True)
            return
        try:
            await callback.message.edit_text("🚀 Публикую...")
            await bot.send_message(CHANNEL_ID, draft, parse_mode="Markdown")
            await callback.message.edit_text(f"✅ **Опубликовано!**\n📺 {CHANNEL_ID}\n\n{draft[:150]}...")
            await callback.answer("🎉 Опубликовано!")
            await state.clear()
            if ADMIN_GROUP_ID:
                await bot.send_message(ADMIN_GROUP_ID, f"📢 **Пост в канал**\n\n{draft[:200]}...", parse_mode="Markdown")
        except Exception as e:
            await callback.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
            logger.error(f"Ошибка публикации: {e}")
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Опубликовать", callback_data="post_publish")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_edit")],
                [InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="post_regenerate")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="post_cancel")]
            ])
            await callback.message.edit_text(f"👀 **Предпросмотр:**\n\n{draft}", parse_mode="Markdown", reply_markup=kb)

@dp.message(StateFilter(PostStates.editing_draft), F.text)
async def handle_post_edit(message: Message, state: FSMContext):
    # 🔹 Если нажали кнопку "Готово"
    if message.text == "✅ Готово, показать предпросмотр":
        await message.answer(
            "⚠️ Вы не отправили текст. Для отмены нажмите /cancel",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    # Если пользователь передумал
    if message.text.lower() in ["/cancel", "отмена"]:
        await state.set_state(PostStates.reviewing_draft)
        data = await state.get_data()
        draft = data.get("draft")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Опубликовать", callback_data="post_publish")],
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_edit")],
            [InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="post_regenerate")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="post_cancel")]
        ])
        await message.answer(
            f"❌ Редактирование отменено.\n\n👀 **Предпросмотр:**\n\n{draft}",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    # 🔹 Сохраняем исправленный текст
    new_text = message.text
    await state.update_data(draft=new_text)
    await state.set_state(PostStates.reviewing_draft)
    
    # 🔹 Показываем предпросмотр с кнопками
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="post_publish")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="post_edit")],
        [InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="post_regenerate")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="post_cancel")]
    ])
    
    # ✅ ИСПРАВЛЕНО: Оставлен только один reply_markup
    await message.answer(
        f"✅ Текст получен!\n\n👀 **Исправленный предпросмотр:**\n\n{new_text}",
        parse_mode="Markdown",
        reply_markup=kb
    )

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state in PostStates.__all_states__:
        await state.clear()
        await message.answer("❌ Действие отменено")
    else:
        await message.answer("ℹ️ Нет активных действий для отмены")

# =============================================================================
# 🔹 3. ОБРАБОТЧИКИ КОЛБЭКОВ (статусы, список, просмотр)
# =============================================================================

@dp.callback_query(F.data.startswith("status_"))
async def handle_status_change(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer("Ошибка", show_alert=True)
        return
    ticket_id = int(parts[1])
    new_status = "_".join(parts[2:])
    success = update_ticket_status(ticket_id, new_status)
    if not success:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return
    ticket = get_ticket_data(ticket_id)
    user_tg_id = None
    if ticket:
        with SessionLocal() as session:
            user_obj = session.query(User).filter(User.id == ticket["user_id"]).first()
            if user_obj: user_tg_id = user_obj.tg_id
    notify_text = ""
    if new_status == "in_progress":
        notify_text = f"🛠 Заявка #{ticket_id} взята в работу."
    elif new_status == "done":
        notify_text = f"✅ Заявка #{ticket_id} выполнена!"
    if notify_text and user_tg_id:
        try:
            await bot.send_message(user_tg_id, notify_text)
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Ошибка отправки ЛС: {e}")
    if new_status == "done" and TENANT_GROUP_ID and ticket:
        try:
            cat_display = ticket["category"].value if hasattr(ticket["category"], 'value') else str(ticket["category"])
            desc = ticket["description"] or "—"
            await bot.send_message(TENANT_GROUP_ID, f"✅ **Заявка #{ticket_id} выполнена!**\n📋 {cat_display}\n📝 {desc}", parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Не отправлено в группу: {e}")
    try:
        if new_status == "in_progress":
            new_text = callback.message.text.replace("🆕 **Заявка", "🔧 **В работе")
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔧 В работе ✅", callback_data="noop")], [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"status_{ticket_id}_done")], [InlineKeyboardButton(text="📋 Список", callback_data="list_all")]])
        elif new_status == "done":
            new_text = callback.message.text.replace("🔧 **В работе", "✅ **Выполнена").replace("🆕 **Заявка", "✅ **Выполнена")
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выполнено", callback_data="noop")], [InlineKeyboardButton(text="📋 Список", callback_data="list_all")]])
        else:
            kb = None
        if kb:
            await callback.message.edit_text(new_text, parse_mode="Markdown", reply_markup=kb)
        await callback.answer("✅ Статус обновлен")
    except Exception as e:
        logger.warning(f"Не обновилось сообщение: {e}")
        await callback.answer("✅ В БД обновлено!")

@dp.callback_query(F.data.startswith("list_"))
async def handle_list_tickets(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    filter_type = callback.data.split("_")[1]
    filter_to_db = {"all": "all", "new": "new", "progress": "in_progress", "done": "done"}
    db_status = filter_to_db.get(filter_type, "all")
    status_map = {"new": "🆕 Новая", "in_progress": "🔧 В работе", "done": "✅ Выполнена"}
    with SessionLocal() as session:
        query = session.query(Ticket)
        if db_status != "all":
            query = query.filter(Ticket.status == db_status)
        tickets = query.order_by(Ticket.is_important.desc(), Ticket.id.desc()).limit(15).all()
        if not tickets:
            await callback.message.answer("📭 Заявок нет.")
            await callback.answer("✅ Загружено")
            return
        title_map = {"all": "📋 Все", "new": "🆕 Новые", "progress": "🔧 В работе", "done": "✅ Выполнены"}
        text = f"**{title_map.get(filter_type)}**\n\n"
        kb_rows = []
        for t in tickets:
            user = session.query(User).filter(User.id == t.user_id).first()
            user_name = user.full_name if user else "Неизвестный"
            cat_display = t.category.value if hasattr(t.category, 'value') else str(t.category)
            status_display = status_map.get(t.status, t.status)
            pin_icon = "📌" if t.is_important else ""
            desc = (t.description[:40] + "...") if t.description and len(t.description) > 40 else (t.description or "-")
            text += f"{status_display} {pin_icon}\n🆔 **#{t.id}** | {cat_display}\n👤 {user_name}\n📝 {desc}\n─────────────\n\n"
            kb_rows.append([InlineKeyboardButton(text=f"👁 Подробнее #{t.id}", callback_data=f"view_ticket_{t.id}")])
        filter_kb = [[InlineKeyboardButton(text="📋 Все", callback_data="list_all"), InlineKeyboardButton(text="🆕 Новые", callback_data="list_new")],
                     [InlineKeyboardButton(text="🔧 В работе", callback_data="list_progress"), InlineKeyboardButton(text="✅ Выполнены", callback_data="list_done")]]
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=filter_kb + kb_rows))
        await callback.answer("✅ Обновлено")

@dp.callback_query(F.data.startswith("view_ticket_"))
async def handle_view_ticket(callback: CallbackQuery):
    ticket_id = int(callback.data.split("_")[2])
    with SessionLocal() as session:
        ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            await callback.answer("❌ Не найдена", show_alert=True)
            return
        user = session.query(User).filter(User.id == ticket.user_id).first()
        cat_display = ticket.category.value if hasattr(ticket.category, 'value') else str(ticket.category)
        status_map = {"new": "🆕 Новая", "in_progress": "🔧 В работе", "done": "✅ Выполнена"}
        status_display = status_map.get(ticket.status, ticket.status)
        created = ticket.created_at.strftime('%d.%m.%Y %H:%M') if ticket.created_at else "-"
        pin_text = "📌 Снять" if ticket.is_important else "📌 Закрепить"
        text = (f"📄 **Заявка #{ticket_id}** {'📌' if ticket.is_important else ''}\n\n"
                f"👤 {user.full_name if user else '-'}\n📱 {user.phone if user and user.phone else '-'}\n"
                f"🏢 {user.company_name if user and user.company_name else '-'}\n📋 {cat_display}\n"
                f"⚡ {ticket.priority}\n📊 {status_display}\n🕒 {created}\n\n📝 {ticket.description or '-'}")
        kb_rows = []
        if ticket.status == "new":
            kb_rows.append([InlineKeyboardButton(text="🔧 В работу", callback_data=f"status_{ticket_id}_in_progress"), InlineKeyboardButton(text="✅ Выполнено", callback_data=f"status_{ticket_id}_done")])
        elif ticket.status == "in_progress":
            kb_rows.append([InlineKeyboardButton(text="✅ Выполнено", callback_data=f"status_{ticket_id}_done")])
        kb_rows.append([InlineKeyboardButton(text=pin_text, callback_data=f"pin_{ticket_id}")])
        kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="list_all")])
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
        await callback.answer()

@dp.callback_query(F.data.startswith("pin_"))
async def handle_pin_ticket(callback: CallbackQuery):
    ticket_id = int(callback.data.split("_")[1])
    is_pinned = toggle_ticket_pin(ticket_id)
    await callback.answer(f"{'📌 Закреплена' if is_pinned else '📌 Снято'}")
    await handle_view_ticket(callback)

# =============================================================================
# 🔹 4. ОБРАБОТЧИК ЗАЯВОК (САМЫЙ НИЗКИЙ ПРИОРИТЕТ — В КОНЦЕ!)
# =============================================================================

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message, state: FSMContext):
    # =================================================================
    # 🔹 ФИЛЬТРЫ: Игнорируем ненужные сообщения (в самом начале!)
    # =================================================================
    
    # 1. Игнорируем сообщения от других ботов
    if message.from_user and message.from_user.is_bot:
        return
    
    # 2. Игнорируем автопосты из каналов (когда post из канала дублируется в группу комментариев)
    # У таких сообщений заполнено sender_chat, а from_user может быть None
    if message.sender_chat:
        return
    
    # 3. Игнорируем системные сообщения без отправителя
    if not message.from_user:
        return

    # 4. Пропускаем, если админ в режиме создания поста (чтобы его черновики не стали заявками)
    current_state = await state.get_state()
    if current_state and current_state.startswith("PostStates:"):
        return

    # =================================================================
    # 🔹 ОСНОВНАЯ ЛОГИКА
    # =================================================================
    
    logger.warning(f"💬 СООБЩЕНИЕ: ID={message.chat.id} | Тип={message.chat.type} | От: {message.from_user.full_name}")
    
    current_chat_id = str(message.chat.id)

    # 🔹 СЦЕНАРИЙ 1: Группа арендаторов
    if TENANT_GROUP_ID and current_chat_id == TENANT_GROUP_ID:
        user_id_tg = message.from_user.id
        user = get_or_create_user_data(tg_id=user_id_tg, full_name=message.from_user.full_name)
        
        thinking = await message.answer("🤔 Анализирую...", reply_to_message_id=message.message_id)
        analyzed = analyze_ticket(message.text, has_photo=False)
        await thinking.delete()
        
        if analyzed and analyzed.get("needs_clarification"):
            clar_text = analyzed["needs_clarification"]
            if user.get("phone") and ("телефон" in clar_text.lower() or "контакт" in clar_text.lower()):
                if "суть" not in clar_text.lower() and "проблема" not in clar_text.lower():
                    analyzed["needs_clarification"] = None
                else:
                    analyzed["needs_clarification"] = clar_text.replace(" и контактный телефон", "").strip()
            if analyzed.get("needs_clarification"):
                await message.answer(f"❓ {analyzed['needs_clarification']}", reply_to_message_id=message.message_id)
                return
        
        if analyzed:
            company_from_llm = analyzed.get("company_name")
            if company_from_llm:
                user = get_or_create_user_data(tg_id=user_id_tg, full_name=message.from_user.full_name, company_name=company_from_llm, phone=user.get("phone"))
            
            ticket_id = create_ticket(user["id"], analyzed)
            cat = analyzed.get('category', 'другое')
            emoji_map = {"электрика": "⚡", "сантехника": "💧", "техническое": "🔧", "другое": "📦"}
            emoji = emoji_map.get(cat, "📦")
            user_phone = user.get("phone")
            
            tenant_response = (
                f"{emoji} **Заявка #{ticket_id} принята!**\n\n"
                f"📋 Категория: {cat}\n⚡ Приоритет: {analyzed.get('priority')}\n"
                f"📍 Объект: {analyzed.get('office_number') or 'Не указан'}\n"
                f"📝 Описание: {analyzed.get('description')}\n\n"
                f"✅ Специалист уведомлён. "
                f"{'📞 Свяжемся по телефону ' + user_phone if user_phone else '📱 Укажите телефон в личке боту.'}"
            )
            await message.answer(tenant_response, reply_to_message_id=message.message_id, parse_mode="Markdown")
            
            admin_text = (
                f"🆕 **Заявка #{ticket_id}** (из группы)\n\n"
                f"👤 {user['full_name']}\n🏢 {user['company_name'] or '-'}\n"
                f"📱 {user_phone or '❌'}\n{emoji} {cat} | ⚡ {analyzed.get('priority')}\n"
                f"📍 {analyzed.get('office_number') or '-'}\n📝 {analyzed.get('description')}\n\n"
                f"[Профиль](tg://user?id={user_id_tg})"
            )
            await send_to_group(admin_text)
            await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
            send_email_notification({"id": ticket_id, **analyzed}, user)
            logger.success(f"Заявка #{ticket_id} из группы обработана")
        return

    # 🔹 СЦЕНАРИЙ 2: Личные сообщения / Админ-группа
    user_id_tg = message.from_user.id
    user = get_or_create_user_data(tg_id=user_id_tg, full_name=message.from_user.full_name)
    
    thinking = await message.answer("🤔 Анализирую...")
    analyzed = analyze_ticket(message.text, has_photo=False)
    await thinking.delete()
    
    if analyzed and analyzed.get("needs_clarification"):
        clar_text = analyzed["needs_clarification"]
        if user.get("phone") and ("телефон" in clar_text.lower() or "номер" in clar_text.lower()):
            if "суть" not in clar_text.lower() and "проблема" not in clar_text.lower():
                analyzed["needs_clarification"] = None
            else:
                clar_text = clar_text.replace(" и контактный телефон", "").replace("номер телефона", "")
                analyzed["needs_clarification"] = clar_text.strip()
        if analyzed.get("needs_clarification"):
            await message.answer(f"❓ {analyzed['needs_clarification']}\nОтветьте на вопрос.")
            return
    
    if analyzed:
        company_from_llm = analyzed.get("company_name")
        if company_from_llm:
            user = get_or_create_user_data(tg_id=user_id_tg, full_name=message.from_user.full_name, company_name=company_from_llm, phone=user.get("phone"))
        
        ticket_id = create_ticket(user["id"], analyzed)
        cat = analyzed.get('category', 'другое')
        emoji_map = {"электрика": "⚡", "сантехника": "💧", "техническое": "🔧", "другое": "📦"}
        emoji = emoji_map.get(cat, "📦")
        user_phone = user.get("phone")
        
        if not user_phone:
            user_response = (
                f"{emoji} **Заявка #{ticket_id} принята!**\n\n"
                f"📋 {cat} | ⚡ {analyzed.get('priority')}\n📍 {analyzed.get('office_number') or '-'}\n"
                f"📝 {analyzed.get('description')}\n\n"
                f"✅ Специалист уведомлён.\n\n"
                f"📱 **Поделитесь номером для связи:**"
            )
            await message.answer(user_response, parse_mode="Markdown", reply_markup=keyboard_request_contact)
        else:
            user_response = (
                f"{emoji} **Заявка #{ticket_id} принята!**\n\n"
                f"📋 {cat} | ⚡ {analyzed.get('priority')}\n📍 {analyzed.get('office_number') or '-'}\n"
                f"📝 {analyzed.get('description')}\n\n"
                f"✅ Специалист уведомлён.\n📞 Свяжемся по {user_phone}."
            )
            await message.answer(user_response, parse_mode="Markdown")
        
        admin_text = (
            f"🆕 **Заявка #{ticket_id}**\n\n"
            f"👤 {user['full_name']}\n🏢 {user['company_name'] or '-'}\n📱 {user_phone or '❌'}\n"
            f"{emoji} {cat} | ⚡ {analyzed.get('priority')}\n📍 {analyzed.get('office_number') or '-'}\n"
            f"📝 {analyzed.get('description')}\n\n"
            f"[Диалог](tg://user?id={user_id_tg})"
        )
        admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔧 В работу", callback_data=f"status_{ticket_id}_in_progress"),
             InlineKeyboardButton(text="✅ Выполнено", callback_data=f"status_{ticket_id}_done")],
            [InlineKeyboardButton(text="📋 Список", callback_data="list_all")]
        ])
        await send_to_group(admin_text, reply_markup=admin_keyboard)
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_keyboard)
        send_email_notification({"id": ticket_id, **analyzed}, user)
        logger.success(f"Заявка #{ticket_id} обработана")
    else:
        await message.answer("⚠️ Не удалось обработать. Опишите проблему подробнее.")

# =============================================================================
# 🔹 5. АДМИН-КОМАНДЫ
# =============================================================================

@dp.message(Command("list"))
async def cmd_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещен")
        return
    with SessionLocal() as session:
        tickets = session.query(Ticket).order_by(Ticket.is_important.desc(), Ticket.created_at.desc()).all()
        if not tickets:
            await message.answer("📭 Пусто")
            return
        text = "📋 **Заявки:**\n\n"
        for t in tickets:
            emoji = {"new": "🆕", "in_progress": "🔧", "done": "✅"}.get(t.status, "❓")
            cat = t.category.value if hasattr(t.category, 'value') else str(t.category)
            pin = "📌 " if t.is_important else ""
            text += f"{emoji} {pin}**#{t.id}** | {cat} | {t.status}\n📝 {t.description[:50]}...\n─────────────\n\n"
        await message.answer(text, parse_mode="Markdown")

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещен")
        return
    with SessionLocal() as session:
        total = session.query(Ticket).count()
        new = session.query(Ticket).filter(Ticket.status == "new").count()
        progress = session.query(Ticket).filter(Ticket.status == "in_progress").count()
        done = session.query(Ticket).filter(Ticket.status == "done").count()
        await message.answer(f"📊 **Статистика**\n\nВсего: {total}\n🆕 {new}\n🔧 {progress}\n✅ {done}\n\n/list - список", parse_mode="Markdown")

async def main():
    init_db()
    logger.info("✅ БД готова")
    logger.info(f"📢 Админ-группа: {ADMIN_GROUP_ID}")
    if TENANT_GROUP_ID: logger.info(f"🏢 Группа арендаторов: {TENANT_GROUP_ID}")
    if CHANNEL_ID: logger.info(f"📺 Канал: {CHANNEL_ID}")
    logger.info("🚀 Запуск...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановлен")