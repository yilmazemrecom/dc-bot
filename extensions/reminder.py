import asyncio
from datetime import timezone, datetime
import os
import aiofiles
import json
from typing import Optional, List, Dict, Any

class Reminder:
    REMINDER_DATA = '../json/reminders.json'

    @staticmethod
    def current_time() -> float:
        dt = datetime.now(timezone.utc)
        return dt.timestamp()

    @staticmethod
    def has_expired(timestamp: float) -> bool:
        return timestamp < Reminder.current_time()

    @classmethod
    async def add(cls, frequency: str, content: str, timestamp: Optional[float] = None) -> None:
        if timestamp is None:
            timestamp = cls.current_time()

        reminders = await cls.get_reminders()
        reminder_id = reminders[-1]["id"] + 1 if reminders else 0

        reminder_context = {
            "id": reminder_id,
            "frequency": frequency,
            "content": content,
            "timestamp": timestamp
        }

        reminders.append(reminder_context)
        await cls.save_reminders(reminders)

    @classmethod
    async def delete(cls, reminder_id: int) -> None:
        reminders = await cls.get_reminders()
        reminder = cls.find_reminder(reminders, reminder_id)

        if reminder:
            reminders.remove(reminder)
            await cls.save_reminders(reminders)
        else:
            print(f"There is no reminder with ID {reminder_id}!")

    @classmethod
    def find_reminder(cls, reminders: List[Dict[str, Any]], reminder_id: int) -> Optional[Dict[str, Any]]:
        return next((reminder for reminder in reminders if reminder["id"] == reminder_id), None)

    @classmethod
    async def get_reminders(cls) -> List[Dict[str, Any]]:
        if not os.path.exists(Reminder.REMINDER_DATA):
            await Reminder.create_empty_reminder_file()

        async with aiofiles.open(cls.REMINDER_DATA, 'r') as f:
            content = await f.read()
            return sorted(json.loads(content), key=lambda x: x['timestamp']) if content else []

    @classmethod
    async def save_reminders(cls, reminders: List[Dict[str, Any]]) -> None:
        async with aiofiles.open(cls.REMINDER_DATA, 'w') as f:
            await f.write(json.dumps(reminders, indent=4))

    @staticmethod
    async def create_empty_reminder_file() -> None:
        async with aiofiles.open(Reminder.REMINDER_DATA, 'w') as f:
            await f.write(json.dumps([]))