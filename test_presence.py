import logging
import time

from signaling_client import SignalingClient

logging.basicConfig(level=logging.INFO)

# Create two dummy clients
client_a = SignalingClient(client_id=1)
client_b = SignalingClient(client_id=2)


# Define what happens when presence updates
def ui_update(online_list):
    print(f"--> UI DOT UPDATE: These IDs are online: {online_list}")


client_a.on_presence_update = ui_update
client_b.on_presence_update = ui_update

print("Starting Client A...")
client_a.start()
time.sleep(2)  # Give it a moment to connect

print("Starting Client B...")
client_b.start()
time.sleep(2)

print("Client A sending a test call offer to Client B...")
client_a.send_message(target_id=2, msg_type="call_offer")
time.sleep(1)
