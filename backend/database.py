from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
import os

# Default to a local SQLite file so no database server is required.
# Override by setting DATABASE_URL env var (e.g. postgresql+asyncpg://...).
_default_db = "sqlite+aiosqlite:///./linkedin_jobs.db"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

_is_sqlite = DATABASE_URL.startswith("sqlite")

# SQLite needs check_same_thread=False via connect_args.
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

# aiosqlite spawns one OS thread per connection.  Using the default pool
# keeps those threads alive indefinitely; under load this exhausts the
# OS thread limit and raises "RuntimeError: can't start new thread".
# NullPool closes every connection immediately after the session ends,
# releasing the aiosqlite thread right away.
_pool_class = NullPool if _is_sqlite else AsyncAdaptedQueuePool

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
    poolclass=_pool_class,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
