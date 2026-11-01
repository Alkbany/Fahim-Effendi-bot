import asyncio
import unittest

from main import KeyedLockPool


class KeyedLockPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_conversation_is_serialized_and_entry_is_cleaned_up(self):
        pool = KeyedLockPool()
        first_entered = asyncio.Event()
        release_first = asyncio.Event()
        second_entered = asyncio.Event()
        order = []

        async def first():
            async with pool.hold((1, 2)):
                order.append("first-start")
                first_entered.set()
                await release_first.wait()
                order.append("first-end")

        async def second():
            await first_entered.wait()
            async with pool.hold((1, 2)):
                order.append("second-start")
                second_entered.set()

        first_task = asyncio.create_task(first())
        second_task = asyncio.create_task(second())

        await first_entered.wait()
        await asyncio.sleep(0)
        self.assertFalse(second_entered.is_set())

        release_first.set()
        await asyncio.gather(first_task, second_task)

        self.assertEqual(
            order,
            ["first-start", "first-end", "second-start"],
        )
        self.assertEqual(pool._entries, {})

    async def test_different_conversations_can_run_in_parallel(self):
        pool = KeyedLockPool()
        both_entered = asyncio.Event()
        entered = set()

        async def work(key):
            async with pool.hold(key):
                entered.add(key)
                if len(entered) == 2:
                    both_entered.set()
                await asyncio.wait_for(both_entered.wait(), timeout=1)

        await asyncio.gather(work((1, 2)), work((1, 3)))
        self.assertEqual(entered, {(1, 2), (1, 3)})
        self.assertEqual(pool._entries, {})

    async def test_cancelled_waiter_does_not_leak_lock_entry(self):
        pool = KeyedLockPool()
        entered = asyncio.Event()
        release = asyncio.Event()

        async def holder():
            async with pool.hold((1, 2)):
                entered.set()
                await release.wait()

        async def waiter():
            async with pool.hold((1, 2)):
                self.fail("Cancelled waiter must not acquire the lock.")

        holder_task = asyncio.create_task(holder())
        await entered.wait()
        waiter_task = asyncio.create_task(waiter())
        await asyncio.sleep(0)
        waiter_task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await waiter_task

        release.set()
        await holder_task
        self.assertEqual(pool._entries, {})


if __name__ == "__main__":
    unittest.main()
