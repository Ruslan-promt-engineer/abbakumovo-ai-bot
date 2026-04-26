# widget_api.py
import os
import re
import uuid
import time
import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger
from dotenv import load_dotenv
from datetime import datetime

# 🔹 1. ИМПОРТ БАЗЫ ЗНАНИЙ
try:
    from knowledge_base import get_knowledge_text
    logger.info("✅ База знаний загружена: knowledge_base.py")
except ImportError as e:
    logger.error(f"❌ Ошибка импорта knowledge_base: {e}")
    def get_knowledge_text():
        return "База знаний не загружена."

load_dotenv()
app = FastAPI(title="СК Аббакумово AI-Widget")

# 🔹 2. CORS (из .env для гибкости)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔹 3. КОНФИГУРАЦИЯ
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")
YANDEX_API_KEY = os.getenv("YANDEXGPT_API_KEY")
FOLDER_ID = os.getenv("FOLDER_ID")
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# 🔹 ОТЛАДКА: только если включено в .env (DEBUG_LOGS=true)
if os.getenv("DEBUG_LOGS") == "true":
    logger.info(f"🔑 YANDEXGPT_API_KEY: {'✅ задан' if YANDEX_API_KEY else '❌ пустой'}")
    logger.info(f"📁 FOLDER_ID: {FOLDER_ID if FOLDER_ID else '❌ пустой'}")

sessions = {}

class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    is_lead_sent: bool = False

# 🔹 4. СИСТЕМНЫЙ ПРОМПТ
SYSTEM_PROMPT = f"""Ты — менеджер по аренде СК «Аббакумово».
Твоя цель: отвечать на вопросы и собирать заявку (Имя, Телефон, Потребность).

📚 АКТУАЛЬНАЯ ИНФОРМАЦИЯ О КОМПЛЕКСЕ:
{get_knowledge_text()}

🎯 СТРОГИЕ ПРАВИЛА ОТВЕТОВ:
1. Отвечай ТОЛЬКО на последнее сообщение пользователя. НЕ генерируй диалог за пользователя.
2. ❗ НИКОГДА не пиши "Пользователь:", "Клиент:", "Вася:" или любые другие сообщения от имени клиента.
3. ❗ НИКОГДА не придумывай телефон, имя или потребность, если пользователь их не написал.
4. Задавай вопросы ПО ОДНОМУ, естественно:
   - "Как к вам обращаться?" → жди ответа
   - "Пожалуйста оставьте номер телефона для связи!" → жди ответа  
   - "Какая площадь и тип помещения вас интересуют?" → жди ответа
5. ❗ НЕ подводи итоги в формате "Ваши данные: имя — ..., телефон — ...".
6. ❗ НЕ отправляй заявку автоматически. Жди явного подтверждения: "Да", "Отправляйте", "Подтверждаю", "Хорошо, жду звонка".
7. ✅ Только после явного подтверждения напиши: "✅ Заявка принята! Менеджер свяжется с вами в течение 15 минут." и добавь маркер [LEAD_READY].
8. Будь вежлив, краток (1-3 предложения), профессионален.
9. Если вопрос вне базы знаний → "Уточню у менеджера и перезвоню. Оставьте, пожалуйста, телефон."
❗ Когда пользователь присылает телефон — НЕ пиши "Спасибо за звонок", "Благодарю за звонок" или подобные фразы. 
Просто ответь: "Спасибо!", "Принято!" или сразу переходи к следующему вопросу.

📤 ФОРМАТ ОТВЕТА:
- Только твой ответ как менеджера.
- Без диалогов, без "Пользователь: ...", без JSON, без разметки.
- Маркер [LEAD_READY] — ТОЛЬКО после явного подтверждения пользователем.
"""


# =============================================================================
# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def call_yandex_gpt(history: list[dict]) -> str:
    """Вызов YandexGPT API"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "x-folder-id": FOLDER_ID
    }
    payload = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
        "completionOptions": {"stream": False, "temperature": 0.2, "maxTokens": 800},
        "messages": [{"role": "system", "text": SYSTEM_PROMPT}] + history
    }
    try:
        resp = requests.post(YANDEX_API_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        text = resp.json()["result"]["alternatives"][0]["message"]["text"]
        if text.startswith("```"):
            text = text.split("```")[-2] if len(text.split("```")) >= 2 else text
        return text.strip()
    except Exception as e:
        logger.error(f"❌ Ошибка YandexGPT: {e}")
        return "⚠️ Техническая ошибка. Позвоните: +7 (991) 635-09-77"


def extract_phone(text: str) -> str | None:
    """Извлекает российские номера: +7..., 8..., 7... (с разделителями или без)"""
    # 1. Форматированный номер: +7 (999) 123-45-67
    match = re.search(r'(\+?7?\s?\(?\d{3}\)?[\s\.-]?\d{3}[\s\.-]?\d{2}[\s\.-]?\d{2})', text)
    if match:
        digits = re.sub(r'\D', '', match.group(0))
        if len(digits) == 11 and (digits.startswith('7') or digits.startswith('8')):
            return match.group(0).strip()
    # 2. Просто 11 цифр подряд: 89991234567
    match = re.search(r'\b([78]\d{10})\b', text)
    return match.group(0).strip() if match else None


def format_phone(phone: str) -> str:
    """Форматирует телефон: +7 (999) 123-45-67"""
    digits = re.sub(r'\D', '', phone)
    if len(digits) != 11:
        return phone
    if digits.startswith('8'):
        digits = '7' + digits[1:]
    if digits.startswith('7'):
        return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:]}"
    return phone


def send_lead_to_telegram(name: str, phone: str, need: str):
    """Отправляет лид в Telegram"""
    if not BOT_TOKEN or not ADMIN_GROUP_ID:
        logger.warning("⚠️ BOT_TOKEN или ADMIN_GROUP_ID не настроены")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    text = (
        f"🌐 **НОВЫЙ ЛИД С САЙТА**\n\n"
        f"👤 *Имя:* {name}\n"
        f"📱 *Телефон:* {phone}\n"
        f"📦 *Потребность:* {need}\n\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"🔗 Источник: виджет на сайте"
    )
    try:
        resp = requests.post(url, json={"chat_id": ADMIN_GROUP_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
        if resp.status_code == 200:
            logger.success(f"✅ Лид отправлен: {name} ({phone})")
        else:
            logger.error(f"❌ TG API error {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в TG: {e}")


# =============================================================================
# 🌐 API ENDPOINTS
# =============================================================================

@app.post("/api/widget/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks):
    session_id = req.session_id or str(uuid.uuid4())
    
    # 🔹 Rate-limit: не чаще 1 запроса в секунду на сессию
    now = time.time()
    if session_id in sessions:
        last_req = sessions[session_id].get("last_request", 0)
        if now - last_req < 1.0:
            return ChatResponse(session_id=session_id, reply="⏳ Пожалуйста, подождите 1 секунду между сообщениями.")
    
    if session_id not in sessions:
        sessions[session_id] = {
            "history": [],
            "collected": {"name": None, "phone": None, "need": None}
        }
    
    session = sessions[session_id]
    user_msg = req.message.strip()
    
    if not user_msg:
        return ChatResponse(session_id=session_id, reply="Пожалуйста, напишите ваш вопрос.")
    
    if len(session["history"]) > 40:
        sessions.pop(session_id, None)
        return ChatResponse(session_id=session_id, reply="🔄 Давайте начнём заново.")
    
    session["history"].append({"role": "user", "text": user_msg})
    session["last_request"] = now  # Обновляем время последнего запроса
    
    # 🔹 Отладочный лог (только если DEBUG_LOGS=true)
    if os.getenv("DEBUG_LOGS") == "true":
        logger.debug(f"📨 Входящее: '{user_msg}' | История: {len(session['history'])} сообщений")
    
    try:
        ai_reply = call_yandex_gpt(session["history"])
        session["history"].append({"role": "assistant", "text": ai_reply})
        
        collected = session["collected"]
        
        # 📛 Стоп-слова и вопросы
        STOP_WORDS = [
            "привет", "здравствуйте", "добрый", "доброе", "добрая", 
            "хай", "хеллоу", "здрасте", "день", "утро", "вечер", "ночь",
            "пока", "до свидания", "спасибо", "благодарю", "ок", "хорошо",
            "я не", "не иван", "не мой", "не петр", "ошибка", "исправить", 
            "поменять", "это не", "неправильно", "нет", "не тот"
        ]
        QUESTION_WORDS = ["как", "какой", "какая", "какие", "сколько", "где", 
                          "когда", "почему", "зачем", "можно", "есть", "будет",
                          "нужно", "хочу", "интересует", "подскажите", "расскажите"]
        
        # 👤 Имя (строгая валидация)
        if not collected["name"]:
            msg_lower = user_msg.lower().strip()
            words = user_msg.split()
            if (len(words) <= 3 and 
                not re.search(r'\d', user_msg) and
                not any(sw in msg_lower for sw in STOP_WORDS) and
                not any(qw in msg_lower for qw in QUESTION_WORDS) and
                len(words) >= 1 and
                "не " not in msg_lower):
                collected["name"] = user_msg.strip().capitalize()
                
        # 📱 Телефон (валидный РФ номер)
        if not collected["phone"]:
            phone = extract_phone(user_msg)
            if phone:
                collected["phone"] = format_phone(phone)
                
        # 📦 Потребность (с учётом опечаток)
        if not collected["need"]:
            need_keywords = ["склад", "офис", "площадь", "м²", "м2", "аренда", "нужно", 
                           "ищу", "производство", "хранение", "логист", "контейнер", 
                           "условия", "цена", "стоимость", "заезд", "оплата",
                           "слад", "складе", "склада"]
            msg_lower = user_msg.lower()
            is_simple_question = any(q in msg_lower for q in ["есть ли", "какие есть", "что есть", "есть у вас"])
            if any(kw in msg_lower for kw in need_keywords) and not is_simple_question:
                collected["need"] = user_msg.strip()
            
        # 🔹 Проверка готовности лида (защита от ложных срабатываний)
        is_lead_sent = False
        
        lead_confirmed = (
            "[lead_ready]" in ai_reply.lower() or 
            "✅ заявка принята" in ai_reply.lower() or
            ("менеджер свяжется" in ai_reply.lower() and "15 минут" in ai_reply.lower())
        )
        
        ai_summarized = "ваши данные" in ai_reply.lower() or "имя —" in ai_reply.lower()
        
        if all(collected.values()) and lead_confirmed and not ai_summarized:
            logger.info(f"🎯 Лид готов: {collected}")
            background_tasks.add_task(
                send_lead_to_telegram, 
                collected["name"], 
                collected["phone"], 
                collected["need"]
            )
            is_lead_sent = True
            sessions.pop(session_id, None)  # Очищаем сессию после успешной отправки
        elif not all(collected.values()) and os.getenv("DEBUG_LOGS") == "true":
            missing = [k for k, v in collected.items() if not v]
            logger.debug(f"⏳ Ждём: {missing}")
            
        clean_reply = re.sub(r'\[LEAD_READY\]', '', ai_reply, flags=re.IGNORECASE).strip()
        return ChatResponse(session_id=session_id, reply=clean_reply, is_lead_sent=is_lead_sent)
        
    except Exception as e:
        logger.error(f"❌ Ошибка чата: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "abbakumovo-widget", "sessions": len(sessions)}


if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Запуск AI-виджета на порту 8001")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")