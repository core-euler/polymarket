from app.db.base import Base
from app.db.session import get_engine
from app.db import models  # noqa: F401


async def init_db() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
