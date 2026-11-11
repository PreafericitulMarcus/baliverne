import argparse
import logging

from audio_engine import AudioEngine
from signaling_client import SignalingClient
from ui import VoiceApp

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="Baliverne Voice Chat")
    parser.add_argument(
        "--user",
        choices=["1", "2"],
        default="1",
        help="Run as User 1 (port 5001) or User 2 (port 5002)",
    )
    args = parser.parse_args()

    client_id = int(args.user)
    local_port = 5000 + client_id

    # 1. Initialize Audio Engine (Targets are now dynamically set during handshake)
    engine = AudioEngine(client_id=client_id, local_port=local_port)

    # 2. Initialize Signaling Client
    sig_client = SignalingClient(
        client_id=client_id, server_url="wss://baliverne.red8red.com"
    )

    # 3. Pass both to your GUI
    app = VoiceApp(engine=engine, sig_client=sig_client)

    # 4. Start the background signaling thread
    sig_client.start()

    # 5. Start the GUI blocking loop
    app.mainloop()


if __name__ == "__main__":
    main()
