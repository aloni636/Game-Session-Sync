import asyncio


class CustomException(RuntimeError):
    pass


async def raise_exc(custom=False):
    await asyncio.sleep(0)
    if custom:
        raise CustomException("Custom Exception")
    else:
        raise Exception("Exception")


async def main():
    while True:
        user_input = (
            await asyncio.to_thread(input, "[q: quit | r: raise exception] > ")
        ).strip()
        if user_input == "q":
            break
        if user_input == "r":
            # no one awaits, or pulls the task to their scope,
            # so the exception is logged to stdout but never crashes anything
            asyncio.create_task(raise_exc())
        else:
            print(f"Unrecognized command: {user_input!r}")


if __name__ == "__main__":
    asyncio.run(main())
