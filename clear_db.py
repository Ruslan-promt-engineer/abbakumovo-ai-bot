# clear_db.py
# 🔹 Скрипт для очистки базы данных проекта Аббакумово

import sys
from database import SessionLocal, engine
from models import User, Ticket, Base
from loguru import logger

def clear_all_data():
    """Удаляет все данные из таблиц, но оставляет структуру"""
    try:
        with SessionLocal() as session:
            # 🔹 Важно: сначала Tickets, потом Users (из-за внешних ключей)
            tickets_count = session.query(Ticket).count()
            users_count = session.query(User).count()
            
            session.query(Ticket).delete()
            session.query(User).delete()
            session.commit()
            
            logger.success(f"✅ Данные удалены!")
            logger.info(f"   🗑️ Заявок: {tickets_count}")
            logger.info(f"   🗑️ Пользователей: {users_count}")
            return True
    except Exception as e:
        logger.error(f"❌ Ошибка очистки: {e}")
        return False

def reset_tables():
    """Полный сброс: удаляет таблицы и создаёт заново"""
    try:
        # 🔹 Удаляем все таблицы
        Base.metadata.drop_all(bind=engine)
        logger.warning("🗑️ Таблицы удалены")
        
        # 🔹 Создаём заново
        Base.metadata.create_all(bind=engine)
        logger.success("✅ Таблицы созданы заново")
        logger.info("💡 Запусти main.py — база инициализируется автоматически")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сброса: {e}")
        return False

def main():
    print("\n" + "="*60)
    print("🧹 ОЧИСТКА БАЗЫ ДАННЫХ — СК «Аббакумово»")
    print("="*60 + "\n")
    
    print("⚠️  ВНИМАНИЕ: Это действие НЕОБРАТИМО!")
    print("Все заявки и пользователи будут удалены.\n")
    
    print("Выберите действие:")
    print("1 — 🗑️ Удалить только данные (таблицы останутся)")
    print("2 — 🔥 Полностью пересоздать таблицы (жёсткий сброс)")
    print("0 — ❌ Отмена\n")
    
    choice = input("Ваш выбор [0/1/2]: ").strip()
    
    if choice == "0":
        print("\n❌ Отменено. Ничего не удалено.")
        sys.exit(0)
    
    # 🔹 Подтверждение
    confirm = input("\n❓ Вы уверены? Напишите ДА для подтверждения: ").strip().upper()
    if confirm != "ДА":
        print("\n❌ Отменено. Ничего не удалено.")
        sys.exit(0)
    
    print("\n⏳ Выполняю...")
    
    if choice == "1":
        success = clear_all_data()
    elif choice == "2":
        success = reset_tables()
    else:
        print("\n❌ Неверный выбор")
        sys.exit(1)
    
    if success:
        print("\n✅ Готово! Можешь запускать бота: python main.py")
    else:
        print("\n❌ Произошла ошибка. Проверь логи выше.")
        sys.exit(1)

if __name__ == "__main__":
    main()