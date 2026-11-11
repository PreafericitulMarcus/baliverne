import json
import logging
from pathlib import Path

import customtkinter as ctk
from pynput import keyboard

from audio_engine import AudioEngine
from signaling_client import SignalingClient

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

CONFIG_PATH = Path("config.json")
DEFAULT_CONFIG = {"microphone": None, "speaker": None}


def load_saved_settings() -> dict:
    if not CONFIG_PATH.exists():
        logger.info("No config.json found. Generating default configuration file...")
        try:
            CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        except Exception as e:
            logger.error(f"Failed to create default config.json: {e}")

    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception as e:
        logger.warning(f"Corrupt config.json detected, resetting to defaults: {e}")
        return DEFAULT_CONFIG.copy()


def save_setting(key: str, value: str) -> None:
    config = load_saved_settings()
    config[key] = value
    try:
        CONFIG_PATH.write_text(json.dumps(config, indent=2))
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, engine: AudioEngine):
        super().__init__(parent)
        self.engine = engine
        self.config = load_saved_settings()

        self.title("Baliverne - Settings")
        self.geometry("420x300")
        self.resizable(False, False)

        # Make window modal (optional, keeps focus on settings)
        self.grab_set()

        # Header Label
        self.header_label = ctk.CTkLabel(
            master=self,
            text="Audio Device Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.header_label.pack(pady=(20, 15))

        input_devices = self.engine.get_input_devices()
        output_devices = self.engine.get_output_devices()

        # --- Microphone Selection ---
        self.mic_frame = ctk.CTkFrame(master=self, fg_color="transparent")
        self.mic_frame.pack(pady=10, padx=30, fill="x")

        self.mic_label = ctk.CTkLabel(
            master=self.mic_frame,
            text="Microphone (Input)",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.mic_label.pack(anchor="w")

        self.mic_dropdown = ctk.CTkOptionMenu(
            master=self.mic_frame,
            values=input_devices,
            command=self.on_mic_select,
            width=360,
        )
        self.mic_dropdown.pack(pady=(5, 0), fill="x")
        saved_mic = self.config.get("microphone")
        if saved_mic in input_devices:
            self.mic_dropdown.set(saved_mic)
            self.engine.set_input_device(saved_mic)
        else:
            self.mic_dropdown.set(input_devices[0])

        # --- Speaker Selection ---
        self.speaker_frame = ctk.CTkFrame(master=self, fg_color="transparent")
        self.speaker_frame.pack(pady=10, padx=30, fill="x")

        self.speaker_label = ctk.CTkLabel(
            master=self.speaker_frame,
            text="Speaker / Headphones (Output)",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.speaker_label.pack(anchor="w")

        self.speaker_dropdown = ctk.CTkOptionMenu(
            master=self.speaker_frame,
            values=output_devices,
            command=self.on_speaker_select,
            width=360,
        )
        self.speaker_dropdown.pack(pady=(5, 0), fill="x")
        saved_speaker = self.config.get("speaker")
        if saved_speaker in output_devices:
            self.speaker_dropdown.set(saved_speaker)
            self.engine.set_output_device(saved_speaker)
        else:
            self.speaker_dropdown.set(output_devices[0])
        # --- Close Button ---
        self.close_button = ctk.CTkButton(
            master=self,
            text="Save & Close",
            width=120,
            command=self.destroy,
            fg_color="#2ecc71",
            hover_color="#27ae60",
        )
        self.close_button.pack(pady=(15, 20))

    def on_mic_select(self, choice: str) -> None:
        logger.info(f"Selected microphone: {choice}")
        save_setting("microphone", choice)
        self.engine.set_input_device(choice)

    def on_speaker_select(self, choice: str) -> None:
        logger.info(f"Selected speaker: {choice}")
        save_setting("speaker", choice)
        self.engine.set_output_device(choice)


class VoiceApp(ctk.CTk):
    def __init__(self, engine: AudioEngine, sig_client: SignalingClient):
        super().__init__()
        self.engine = engine
        self.sig_client = sig_client

        # Bind background network events to UI handlers
        self.sig_client.on_presence_update = self.handle_presence
        self.sig_client.on_call_offer = self.handle_offer
        self.sig_client.on_call_answer = self.handle_answer

        self.title("Baliverne")
        self.geometry("420x340")
        self.resizable(False, False)

        # Open Setting Window
        self.settings_button = ctk.CTkButton(
            master=self, text="Settings", command=self.open_settings
        )
        self.settings_button.pack(side="top", padx=20, pady=20)
        self.settings_window = None

        # Status Container
        self.status_frame = ctk.CTkFrame(master=self, fg_color="transparent")
        self.status_frame.pack(pady=(25, 15))

        self.status_prefix = ctk.CTkLabel(
            master=self.status_frame,
            text="Status: ",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="gray",
        )
        self.status_prefix.pack(side="left")

        self.status_value = ctk.CTkLabel(
            master=self.status_frame,
            text="Offline",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#e74c3c",
        )
        self.status_value.pack(side="left")

        # Controls Container
        self.controls_frame = ctk.CTkFrame(master=self, fg_color="transparent")
        self.controls_frame.pack(pady=15)

        self.mute_voice_button = ctk.CTkButton(
            master=self.controls_frame,
            text="Mute",
            width=90,
            height=36,
            corner_radius=0,
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=self.on_mute_click,
        )
        self.mute_voice_button.pack(side="left", padx=8)

        self.connect_voice_button = ctk.CTkButton(
            master=self.controls_frame,
            text="Join Voice",
            width=140,
            height=36,
            corner_radius=0,
            fg_color="#2ecc71",
            hover_color="#27ae60",
            command=self.on_connect_click,
        )
        self.connect_voice_button.pack(side="left", padx=8)

        self.deafen_voice_button = ctk.CTkButton(
            master=self.controls_frame,
            text="Deafen",
            width=90,
            height=36,
            corner_radius=0,
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=self.on_deafen_click,
        )
        self.deafen_voice_button.pack(side="left", padx=8)

        # Output Volume Slider Container
        self.volume_frame = ctk.CTkFrame(master=self, fg_color="transparent")
        self.volume_frame.pack(pady=(10, 5), padx=30, fill="x")

        self.volume_label = ctk.CTkLabel(
            master=self.volume_frame,
            text="Output Volume: 100%",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.volume_label.pack(anchor="w")

        self.volume_slider = ctk.CTkSlider(
            master=self.volume_frame,
            from_=0,
            to=150,
            number_of_steps=30,
            command=self.on_volume_change,
        )
        self.volume_slider.set(100)
        self.volume_slider.pack(fill="x", pady=(5, 0))

        # Mic Volume Slider Container
        self.mic_volume_frame = ctk.CTkFrame(master=self, fg_color="transparent")
        self.mic_volume_frame.pack(pady=(10, 15), padx=30, fill="x")

        self.mic_volume_label = ctk.CTkLabel(
            master=self.mic_volume_frame,
            text="Mic Volume: 100%",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.mic_volume_label.pack(anchor="w")

        self.mic_volume_slider = ctk.CTkSlider(
            master=self.mic_volume_frame,
            from_=0,
            to=200,
            number_of_steps=40,
            command=self.on_mic_volume_change,
        )
        self.mic_volume_slider.set(100)
        self.mic_volume_slider.pack(fill="x", pady=(5, 0))

        self._start_global_keybinds()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def open_settings(self) -> None:
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = SettingsWindow(self, self.engine)
        else:
            self.settings_window.focus()

    def _start_global_keybinds(self) -> None:
        def trigger(callback):
            self.after(0, callback)

        hotkeys = {
            "<ctrl>+<alt>+j": lambda: trigger(self.on_connect_click),
            "<ctrl>+<alt>+m": lambda: trigger(self.on_mute_click),
            "<ctrl>+<alt>+d": lambda: trigger(self.on_deafen_click),
        }

        self.global_listener = keyboard.GlobalHotKeys(hotkeys)
        self.global_listener.daemon = True
        self.global_listener.start()

    # --- Network Handshake Handlers (Running on Background Thread) ---

    def handle_presence(self, online_users: list) -> None:
        logger.info(f"Online users updated: {online_users}")

    def handle_offer(self, data: dict) -> None:
        """Triggered when the other user calls you."""

        def execute_ui_update():
            caller_id = data["source_id"]
            peer_ip = data["ip"]
            peer_port = data["port"]
            peer_pubkey = data["pubkey"]
            logger.info(f"Incoming call from {caller_id}...")

            # 1. Discover our own IP/Port and generate our ephemeral keypair
            my_ip, my_port = self.engine.bind_and_discover()
            my_pubkey = self.engine.generate_keypair()

            # 2. Derive the shared encryption key using the caller's public key
            self.engine.derive_shared_key(peer_pubkey)

            # 3. Reply with our coordinates and our public key
            self.sig_client.send_message(
                target_id=caller_id,
                msg_type="call_answer",
                payload={"ip": my_ip, "port": my_port, "pubkey": my_pubkey},
            )

            # 4. Punch hole and start audio engine
            self.engine.start(peer_ip, peer_port)
            self._set_ui_connected()

        self.after(0, execute_ui_update)

    def handle_answer(self, data: dict) -> None:
        """Triggered when the peer accepts your call offer."""

        def execute_ui_update():
            peer_ip = data["ip"]
            peer_port = data["port"]
            peer_pubkey = data["pubkey"]

            # 1. Derive the shared encryption key using the answerer's public key
            self.engine.derive_shared_key(peer_pubkey)

            # 2. Punch hole and start audio engine
            self.engine.start(peer_ip, peer_port)
            self._set_ui_connected()

        self.after(0, execute_ui_update)

    # --- UI Action Handlers (Running on Main Thread) ---

    def on_connect_click(self) -> None:
        if not self.engine.is_running:
            logger.info("Initiating call...")
            self.status_value.configure(text="Calling...", text_color="#f39c12")
            self.connect_voice_button.configure(
                text="Cancel", fg_color="#e74c3c", hover_color="#c0392b"
            )

            target_id = 2 if self.engine.client_id == 1 else 1

            try:
                my_ip, my_port = self.engine.bind_and_discover()
                my_pubkey = self.engine.generate_keypair()
                self.sig_client.send_message(
                    target_id=target_id,
                    msg_type="call_offer",
                    payload={"ip": my_ip, "port": my_port, "pubkey": my_pubkey},
                )
            except Exception as e:
                logger.error(f"Failed to initiate call: {e}")
                self._set_ui_disconnected()
        else:
            logger.info("Disconnecting call...")
            self.engine.stop()
            self._set_ui_disconnected()

    def _set_ui_connected(self) -> None:
        self.status_value.configure(text="Connected", text_color="#2ecc71")
        self.connect_voice_button.configure(
            text="Leave Voice", fg_color="#e74c3c", hover_color="#c0392b"
        )

    def _set_ui_disconnected(self) -> None:
        self.status_value.configure(text="Offline", text_color="#e74c3c")
        self.connect_voice_button.configure(
            text="Join Voice", fg_color="#2ecc71", hover_color="#27ae60"
        )

    def on_volume_change(self, value: float) -> None:
        gain = value / 100.0
        self.engine.set_output_volume(gain)
        self.volume_label.configure(text=f"Output Volume: {int(value)}%")

    def on_mic_volume_change(self, value: float) -> None:
        gain = value / 100.0
        self.engine.set_input_volume(gain)
        self.mic_volume_label.configure(text=f"Mic Volume: {int(value)}%")

    def on_mute_click(self) -> None:
        muted = self.engine.toggle_mute()
        if muted:
            self.mute_voice_button.configure(
                text="Unmute", fg_color="#c0392b", hover_color="#962d22"
            )
        else:
            self.mute_voice_button.configure(
                text="Mute", fg_color="#3a3a3a", hover_color="#4a4a4a"
            )

    def on_deafen_click(self) -> None:
        deafened = self.engine.toggle_deafen()
        if deafened:
            self.deafen_voice_button.configure(
                text="Undeafen", fg_color="#c0392b", hover_color="#962d22"
            )
        else:
            self.deafen_voice_button.configure(
                text="Deafen", fg_color="#3a3a3a", hover_color="#4a4a4a"
            )

    def on_close(self) -> None:
        self.engine.stop()
        self.destroy()
