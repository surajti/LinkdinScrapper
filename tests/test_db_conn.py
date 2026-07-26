import asyncpg
import pytest

@pytest.mark.asyncio
async def test_conn():
    conn = await asyncpg.connect(
        user='user',
        password='password',
        database='linkedin_jobs',
        host='localhost',
    )
    await conn.close()
