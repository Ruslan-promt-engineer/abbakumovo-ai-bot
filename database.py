#database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# Получаем строку подключения из .env
DATABASE_URL = os.getenv("DATABASE_URL")

# Создаём движок БД
engine = create_engine(DATABASE_URL)

# Сессия для работы с БД
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
Base = declarative_base()

def init_db():
    """Создаёт все таблицы, если их ещё нет"""
    Base.metadata.create_all(bind=engine)
    print("✅ База данных и таблицы успешно созданы!")