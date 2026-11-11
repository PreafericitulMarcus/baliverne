import logging

import customtkinter as ctk
from pynput import keyboard

from audio_engine import AudioEngine
from signaling_client import SignalingClient

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


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
