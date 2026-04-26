# models.py
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import enum

# 🔹 Роли пользователей (типобезопасно, защита от опечаток)
class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    TENANT = "tenant"
    MANAGER = "manager"

# 🔹 Категории заявок
class CategoryEnum(str, enum.Enum):
    ELECTRIC = "электрика"
    PLUMBING = "сантехника"
    TECH = "техническое"
    OTHER = "другое"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(BigInteger, unique=True, index=True, nullable=False)  # 🔹 index для быстрого поиска
    full_name = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    role = Column(Enum(RoleEnum), default=RoleEnum.TENANT)  # 🔹 Enum вместо String
    
    tickets = relationship("Ticket", back_populates="user")
    
    def __repr__(self):
        return f"<User(id={self.id}, tg_id={self.tg_id}, name='{self.full_name}', role='{self.role.value}')>"


class Ticket(Base):
    __tablename__ = "tickets"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True)  # 🔹 index + безопасное удаление
    
    category = Column(Enum(CategoryEnum), nullable=True)
    priority = Column(String, default="средний")
    description = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    
    status = Column(String, default="new", index=True)  # 🔹 index для фильтрации
    is_important = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)  # 🔹 index для сортировки
    
    user = relationship("User", back_populates="tickets")
    
    def __repr__(self):
        return f"<Ticket(id={self.id}, status='{self.status}', category='{self.category.value if self.category else None}', created='{self.created_at}')>"