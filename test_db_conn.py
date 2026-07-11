import asyncio
import asyncpg

async def test_conn():
    try:
        conn = await asyncpg.connect(user='user', password='password',
                                     database='linkedin_jobs', host='localhost')
        print("Successfully connected!")
        await conn.close()
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_conn())
