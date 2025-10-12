# NOTE: Doesn't work because input() blocks the terminal, I think
import asyncio
import math
import sys


class DynamicPrompt:
    def __init__(self) -> None:
        self.value: int = 0
        self.is_non_zero = asyncio.Event()
        self.task = asyncio.create_task(self.keep_zero())

    def prompt(self) -> str:
        return f"[q: quit | int: modify value ({self.value})] > "

    async def keep_zero(self):
        while True:
            await self.is_non_zero.wait()
            self.value -= 1
            await asyncio.sleep(3)
            if self.value == 0:
                self.is_non_zero.clear()

    async def run(self):
        while True:
            user_input = await asyncio.to_thread(input, self.prompt())
            user_input = user_input.strip()
            if user_input == "q":
                return

            self.value += abs(int(user_input))
            self.is_non_zero.set()


async def main():
    dynamic_prompt = DynamicPrompt()
    await dynamic_prompt.run()


if __name__ == "__main__":
    asyncio.run(main())
