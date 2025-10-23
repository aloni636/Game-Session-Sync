import asyncio


async def coro_a():
    print("I am coro_a(). Hi!")


async def coro_b():
    print("I am coro_b(). I sure hope no one hogs the event loop...")


async def main():
    task_b = asyncio.create_task(coro_b())
    num_repeats = 3
    for _ in range(num_repeats):
        await asyncio.create_task(coro_a())
    await task_b

loop = asyncio.new_event_loop()
loop.run_until_complete(main())
loop.close()
