"""Demonstrate PostgreSQL JSONB GIN index usage."""

import asyncio

from sqlalchemy import text

from nikshaynavigator.config import get_settings
from nikshaynavigator.db.session import make_engine


async def main() -> None:
    settings = get_settings()
    engine = make_engine(settings)

    query = text(
        """
        EXPLAIN (ANALYZE, BUFFERS)
        SELECT id, external_id, title
        FROM documents
        WHERE metadata @> '{"topic": "Drug-resistant TB diagnosis"}'::jsonb
        """
    )

    try:
        async with engine.connect() as connection:
            # The table is small, so PostgreSQL may naturally prefer
            # a sequential scan. Disable it to demonstrate GIN usage.
            await connection.execute(text("SET enable_seqscan = off"))

            result = await connection.execute(query)

            print("\nPostgreSQL EXPLAIN output:\n")

            for row in result:
                print(row[0])

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
