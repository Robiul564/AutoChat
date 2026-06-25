import asyncio
from dataclasses import dataclass
from typing import Any

from app.core.db import SessionLocal
from app.services import ai, conversation, onboarding


@dataclass
class Event:
    name: str
    business_id: int
    payload: dict[str, Any]


class EventQueue:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[Event] = asyncio.Queue()
        self.task: asyncio.Task | None = None

    async def publish(self, event: Event) -> None:
        await self.queue.put(event)

    async def start(self) -> None:
        if self.task and not self.task.done():
            return
        self.task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()

    async def run(self) -> None:
        while True:
            event = await self.queue.get()
            try:
                self.handle(event)
            finally:
                self.queue.task_done()

    def handle(self, event: Event) -> None:
        db = SessionLocal()
        try:
            if event.name == "message.inbound.created":
                message = conversation.add_inbound_message(db, event.business_id, event.payload)
                if onboarding.handle_inbound(db, message):
                    return
                ai.respond_to_inbound(db, message)
            if event.name == "message.status.updated":
                conversation.update_status_from_provider(db, event.business_id, event.payload)
        finally:
            db.close()


event_queue = EventQueue()
