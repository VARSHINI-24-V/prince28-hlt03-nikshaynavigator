import asyncio

from nikshaynavigator.workers.queue import (
    close_queue,
    connect_queue,
    ping_queue,
)


async def main():
    redis = await connect_queue()

    try:
        print("Redis connected:", await ping_queue(redis))
    finally:
        await close_queue(redis)


asyncio.run(main())
