import asyncpg
import pytest

import pytest

@pytest.mark.skip(reason="No PostgreSQL server available in CI")
async def test_conn():
    pass
