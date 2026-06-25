import asyncio
from dataclasses import dataclass
import logging
from typing import Any

from app.core.db import SessionLocal
from app.services import ai, conversation, onboarding

logger = logging.getLogger(__name__)


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
            except Exception:
                logger.exception("Failed to handle event %s for business %s", event.name, event.business_id)
            finally:
                self.queue.task_done()

    def handle(self, event: Event) -> None:
        db = SessionLocal()
        try:
            if event.name == "message.inbound.created":
                message = conversation.add_inbound_message(db, event.business_id, event.payload)
                logger.info("Inbound WhatsApp message saved: business=%s conversation=%s message=%s", event.business_id, message.conversation_id, message.id)
                if onboarding.handle_inbound(db, message):
                    logger.info("Inbound WhatsApp message handled by onboarding: message=%s", message.id)
                    return
                reply = ai.respond_to_inbound(db, message)
                if reply:
                    logger.info("AI WhatsApp reply saved: business=%s conversation=%s message=%s status=%s", reply.business_id, reply.conversation_id, reply.id, reply.status)
            if event.name == "message.status.updated":
                conversation.update_status_from_provider(db, event.business_id, event.payload)
        finally:
            db.close()


event_queue = EventQueue()
