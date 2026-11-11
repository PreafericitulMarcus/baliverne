import asyncio
import json
import logging

import websockets

logger = logging.getLogger(__name__)

connected_clients = {}


async def broadcast_connected_clients():
    if not connected_clients:
        return
    online_users = list(connected_clients.keys())
    message = json.dumps({"type": "presence", "online": online_users})
    websockets.broadcast(connected_clients.values(), message)


async def handler(websocket):
    client_id = None
    try:
        init_message = await websocket.recv()
        print(init_message)
        data = json.loads(init_message)

        if data.get("type") == "register":
            client_id = data.get("client_id")
            connected_clients[client_id] = websocket
            logger.info(
                f"Client {client_id} registered. Total online: {len(connected_clients)}"
            )
            await broadcast_connected_clients()

        async for message in websocket:
            data = json.loads(message)
            target_id = data.get("target_id")

            if target_id and target_id in connected_clients:
                await connected_clients[target_id].send(message)
                logger.debug(
                    f"Relayed {data.get('type')} from {client_id} to {target_id}"
                )
            else:
                logger.warning(f"Target {target_id} not found or offline.")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if client_id and client_id in connected_clients:
            del connected_clients[client_id]
            logger.info(f"Client {client_id} disconnected.")
            await broadcast_connected_clients()


async def main():
    # Bind to 0.0.0.0 so it can accept connections from anywhere
    async with websockets.serve(handler, "0.0.0.0", 8765):
        logger.info("Signaling Server running on ws://0.0.0.0:8765")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
