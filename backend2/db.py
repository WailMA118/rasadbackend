from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base


class Database:
    def __init__(self, db_url: str):
        self.engine = create_async_engine(
            db_url,
            echo=True,  # خليها False بالإنتاج
            future=True
        )

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

        self.Base = declarative_base()

    # ✅ هذا للاستخدام مع FastAPI (Dependency)
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # ✅ هذا لإنشاء الجداول (مرة واحدة عند startup)
    async def init_models(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(self.Base.metadata.create_all)