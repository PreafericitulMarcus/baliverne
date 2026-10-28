import argparse
from audio_engine import AudioEngine
from ui import VoiceApp


def main():
    parser = argparse.ArgumentParser(description="Baliverne Voice Chat")
    parser.add_argument(
        "--user",
        choices=["1", "2"],
        default="1",
        help="Run as User 1 (port 5001 -> 5002) or User 2 (port 5002 -> 5001)",
    )
    args = parser.parse_args()

    if args.user == "1":
        engine = AudioEngine(local_port=5001, target_ip="127.0.0.1", target_port=5002)
    else:
        engine = AudioEngine(local_port=5002, target_ip="127.0.0.1", target_port=5001)

    app = VoiceApp(engine=engine)
    app.mainloop()


if __name__ == "__main__":
    main()
