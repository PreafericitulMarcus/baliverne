import asyncio
import json
import logging
import threading
from collections.abc import Callable

import websockets

logger = logging.getLogger(__name__)


class SignalingClient:
    def __init__(self, client_id: int, server_url: str = "ws://127.0.0.1:8765"):
        self.client_id = client_id
        self.server_url = server_url
        self.ws = None
        self.loop = asyncio.new_event_loop()

        # Callbacks to trigger UI updates safely
        self.on_presence_update: Callable[[list], None] | None = None
        self.on_call_offer: Callable[[dict], None] | None = None
        self.on_call_answer: Callable[[dict], None] | None = None

        # Run the async WebSocket loop in a background daemon thread
        self.thread = threading.Thread(
            target=self._start_loop, daemon=True, name="SignalingSocket"
        )

    def start(self) -> None:
        self.thread.start()

    def _start_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._connect_and_listen())

    async def _connect_and_listen(self) -> None:
        try:
            async with websockets.connect(self.server_url) as ws:
                self.ws = ws
                logger.info(f"Connected to signaling server at {self.server_url}")

                register_msg = json.dumps(
                    {"type": "register", "client_id": self.client_id}
                )
                await ws.send(register_msg)

                async for message in ws:
                    data = json.loads(message)
                    self._handle_message(data)
        except Exception as e:
            logger.error(f"Signaling connection failed: {e}")

    def _handle_message(self, data: dict) -> None:
        msg_type = data.get("type")

        if msg_type == "presence":
            online_users = data.get("online", [])
            logger.info(f"Online friends updated: {online_users}")
            if self.on_presence_update:
                self.on_presence_update(online_users)

        elif msg_type == "call_offer":
            logger.info(f"Incoming call from {data.get('source_id')}")
            if self.on_call_offer:
                self.on_call_offer(data)

        elif msg_type == "call_answer":
            logger.info(f"Call answered by {data.get('source_id')}")
            if self.on_call_answer:
                self.on_call_answer(data)

    def send_message(self, target_id: int, msg_type: str, payload: dict) -> None:
        if payload is None:
            payload = {}

        data = {
            "type": msg_type,
            "source_id": self.client_id,
            "target_id": target_id,
            **payload,
        }

        if self.ws:
            # Schedule the async send function from the synchronous UI thread
            asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(data)), self.loop)
        else:
            logger.warning("Cannot send message; websocket is disconnected.")
