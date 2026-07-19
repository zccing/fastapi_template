"""SQLAlchemy ORM 模型的共享声明式基类。"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from src.constants import DB_NAMING_CONVENTION


class Base(DeclarativeBase):
    """所有领域 ORM 模型共用的声明式基类。"""

    metadata = MetaData(naming_convention=DB_NAMING_CONVENTION)
