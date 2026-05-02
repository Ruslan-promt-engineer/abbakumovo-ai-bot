# 🤖 AI-Экосистема для СК «Аббакумово»

> Интеллектуальная система автоматизации складского комплекса: приём заявок, консультации арендаторов и генерация контента на базе YandexGPT.

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-green.svg)](https://fastapi.tiangolo.com)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-yellow.svg)](https://docs.aiogram.dev)
[![YandexGPT](https://img.shields.io/badge/YandexGPT-API-orange.svg)](https://cloud.yandex.ru/docs/foundation-models/)

---

## 🎯 О проекте

**Проблема:** Управляющая компания тратит много времени на рутинные операции: ответы на вопросы об аренде, обработка заявок от резидентов, написание постов для канала.

**Решение:** Единая AI-система, которая автоматизирует три ключевых направления:

| Контур | Функция | Результат |
|--------|---------|-----------|
| 🛒 **Sales** | ИИ-консультант по аренде, сбор лидов 24/7 | Рост конверсии, работа без выходных |
| 🛠 **Support** | Приём заявок от арендаторов, ИИ-классификация | Разгрузка диспетчерской на 60% |
| 📢 **Communications** | Генерация постов для канала, авто-уведомления | Экономия 10+ часов/неделю на маркетинге |

---

## ✨ Возможности

### 🤖 Telegram-бот
- 📝 **Приём заявок**: Арендаторы пишут в бота → ИИ извлекает суть, категорию, приоритет, номер офиса
- 🧠 **YandexGPT-анализ**: Автоматическая классификация (`ремонт` / `охрана` / `бухгалтерия` / `аренда`)
- 👥 **Уведомления админам**: Мгновенное оповещение в группу с карточкой заявки
- 🔄 **Управление статусами**: `new` → `in_progress` → `done` с историей изменений
- 📢 **Генерация контента**: Команда `/generate_post` → ИИ создаёт пост для канала по вводным
- 🔍 **Поиск и фильтрация**: Быстрый доступ к заявкам по статусу, дате, категории

### 🌐 Виджет для сайта (Tilda)
- 💬 **Диалоговый интерфейс**: Посетители сайта пишут в чат → получают ответ от ИИ
- 🧠 **База знаний**: Интеграция с `knowledge_base.py` для точных ответов по ценам и условиям
- 📱 **Валидация данных**: Проверка телефона, защита от некорректного ввода
- 📤 **Сбор лидов**: Заявки с сайта → та же админ-группа Telegram
- 🛡 **Безопасность**: CORS, rate-limiting, защита от спама

### 🗄 Общие компоненты
- 📚 **Динамическая база знаний**: Обновление цен/площадей в `knowledge_base.py` без перезапуска
- 🧩 **Модульная архитектура**: `llm.py`, `models.py`, `database.py` — легко масштабировать
- 🪵 **Логирование**: `loguru` с ротацией, удобная отладка
- 🔐 **Безопасность**: Конфигурация через `.env`, ключи не хранятся в коде

---

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
