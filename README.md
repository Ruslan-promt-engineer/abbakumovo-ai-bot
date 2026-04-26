# 🤖 AI-Бот и Виджет для СК «Аббакумово»

> Интеллектуальная система приёма заявок для складского комплекса. Включает Telegram-бота для арендаторов/админов и AI-виджет для сайта на Tilda.

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-green.svg)](https://fastapi.tiangolo.com)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-yellow.svg)](https://docs.aiogram.dev)

## ✨ Возможности

### 🤖 Telegram-бот
- 📝 Приём заявок от арендаторов с автоматическим анализом через YandexGPT
- 🧠 Классификация: категория, приоритет, извлечение номера офиса/компании
- 👥 Уведомление админов в группу, управление статусами (`new → in_progress → done`)
- 📢 Публикация объявлений в канал через ИИ-генерацию постов
- 🔍 Поиск и фильтрация заявок, закрепление важных

### 🌐 Виджет для сайта (Tilda)
- 💬 Диалоговый интерфейс сбора заявок прямо на сайте
- 🧠 Интеграция с YandexGPT для умных ответов по базе знаний
- 📱 Валидация телефона, защита от галлюцинаций ИИ
- 📤 Отправка лидов в ту же админ-группу Telegram
- 🛡 CORS, rate-limit, защита от спама

### 🗄 Общие компоненты
- 📚 Вынесенная база знаний (`knowledge_base.py`) — обновление цен/площадей без правки кода
- 🧩 Модульная архитектура: `llm.py`, `models.py`, `database.py`
- 🪵 Логирование через `loguru`, обработка ошибок
- 🔐 Конфигурация через `.env`, безопасность ключей

## 📁 Структура проекта

```
abbakumovo-ai-bot/
├── .env.example          # Шаблон переменных окружения
├── .gitignore            # Исключаемые файлы для Git
├── README.md             # Этот файл
├── requirements.txt      # Зависимости Python
├── main.py               # Telegram-бот (Aiogram 3)
├── widget_api.py         # FastAPI AI-виджет
├── database.py           # SQLAlchemy engine & session
├── models.py             # Модели БД (User, Ticket)
├── llm.py                # Интеграция с YandexGPT
├── knowledge_base.py     # База знаний комплекса
├── clear_db.py           # Утилита очистки БД
└── deploy/               # (опционально) скрипты для сервера
```

## ⚙️ Установка и запуск (локально)

### 1. Клонирование и окружение
```bash
git clone <repo-url>
cd abbakumovo-ai-bot
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка .env
```bash
cp .env.example .env
# Открой .env и заполни реальными значениями:
# - BOT_TOKEN (от @BotFather)
# - ADMIN_GROUP_ID, TENANT_GROUP_ID, CHANNEL_ID
# - YANDEXGPT_API_KEY, FOLDER_ID (из Яндекс.Облака)
# - DATABASE_URL (SQLite или PostgreSQL)
# - ADMIN_ID (твой Telegram ID)
```

### 3. Запуск
```bash
# Telegram-бот:
python main.py

# Виджет (отдельный терминал):
python widget_api.py
# Доступен на: http://localhost:8001
# Swagger UI: http://localhost:8001/docs
# Health check: http://localhost:8001/health
```

## 📚 Обновление базы знаний

Все цены, площади и контакты хранятся в `knowledge_base.py`.  
Чтобы обновить:
1. Открой `knowledge_base.py`
2. Измени данные в словаре `COMPLEX_INFO`
3. Сохрани файл
4. Перезапусти бота/виджет

✅ Код трогать не нужно — изменения подтянутся автоматически.

## 🚀 Деплой на сервер

Проект готов к развёртыванию на Ubuntu + Nginx + systemd.

### Минимальные требования:
- 1 vCPU, 1 GB RAM, 20 GB SSD
- Ubuntu 22.04 LTS
- Домен (опционально, но рекомендуется для HTTPS)

### Быстрый старт:
```bash
# На сервере:
git clone <repo-url>
cd abbakumovo-ai-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # и заполни
# Настрой systemd-сервисы (инструкция в deploy/)
sudo systemctl start abbakumovo-bot abbakumovo-widget
```

## 🔒 Безопасность

- ✅ Никогда не коммить `.env` с реальными ключами
- ✅ Токены и пароли хранятся только в переменных окружения
- ✅ CORS виджета настраивается через `.env` для продакшена
- ✅ Все запросы к YandexGPT идут через HTTPS с валидацией сертификатов

---

**С уважением, Ваш разработчик.**  
📞 +7 (991) 635-09-77 
