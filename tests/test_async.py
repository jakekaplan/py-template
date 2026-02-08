import asyncio


async def add_async(a: int, b: int) -> int:
    await asyncio.sleep(0)
    return a + b


async def test_add_async() -> None:
    assert await add_async(2, 3) == 5
