"""数据库引擎、会话工厂与写事务封装。"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine: Engine = create_engine(
    settings.database_url,
    echo=settings.echo_sql,
    future=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    """SQLite 打开外键约束，保证 REFERENCES 生效。"""
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def write_transaction(db: Session) -> Iterator[Session]:
    """写事务上下文：SQLite 用 BEGIN IMMEDIATE 前置写锁，其他方言用普通事务。

    进入时若会话已有事务则先提交，确保 BEGIN IMMEDIATE 生效。
    """
    if db.in_transaction():
        db.commit()
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        db.execute(_text("BEGIN IMMEDIATE"))
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def _text(sql: str):  # noqa: ANN202
    from sqlalchemy import text

    return text(sql)


def init_db() -> None:
    """启动时建表（schema.sql 为唯一事实源，models.py 与之保持一致）。"""
    from app import models  # noqa: F401  确保模型已注册

    models.Base.metadata.create_all(bind=engine)
    logger.info("数据库表结构已就绪: %s", settings.database_url)


def reset_engine(database_url: Optional[str] = None) -> None:
    """测试辅助：重建引擎与会话工厂。"""
    global engine, SessionLocal
    url = database_url or settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, echo=settings.echo_sql, future=True, connect_args=connect_args)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
