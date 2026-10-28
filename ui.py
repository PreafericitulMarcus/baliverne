import customtkinter as ctk
from audio_engine import AudioEngine
from pynput import keyboard
import logging

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


class VoiceApp(ctk.CTk):
    def __init__(self, engine: AudioEngine):
        super().__init__()
        self.engine = engine

        self.title("Baliverne")
        self.geometry("420x260")
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
        self.controls_frame.pack(pady=20)

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

        # Volume Slider Container
        self.volume_frame = ctk.CTkFrame(master=self, fg_color="transparent")
        self.volume_frame.pack(pady=15, padx=30, fill="x")

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
        self.volume_slider.set(1.0)
        self.volume_slider.pack(fill="x", pady=(5, 0))

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

    def on_volume_change(self, value: float) -> None:
        gain = value / 100.0
        self.engine.set_volume(gain)
        self.volume_label.configure(text=f"Output Volume: {int(value)}%")
        logger.debug(f"Volume ajusted to: {int(value)}%")

    def on_connect_click(self) -> None:
        if not self.engine.is_running:
            logger.info("Join Call button pressed. Initializing engine")
            self.engine.start()
            logger.info("Call connected ok")
            self.status_value.configure(text="Connected", text_color="#2ecc71")
            self.connect_voice_button.configure(
                text="Leave Voice", fg_color="#e74c3c", hover_color="#c0392b"
            )
        else:
            logger.info("Disconnect Call button pressed. Stopping engine")
            self.engine.stop()
            logger.info("Bye!")
            self.status_value.configure(text="Offline", text_color="#e74c3c")
            self.connect_voice_button.configure(
                text="Join Voice", fg_color="#2ecc71", hover_color="#27ae60"
            )

    def on_mute_click(self) -> None:
        muted = self.engine.toggle_mute()
        state = "Muted" if muted else "NOT Muted"
        logger.info(f"Mute toggled -> {state}")
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
        state = "Deafened" if deafened else "NOT Deafened"
        logger.info(f"Deafen toggled -> {state}")
        if deafened:
            self.deafen_voice_button.configure(
                text="Undeafen", fg_color="#c0392b", hover_color="#962d22"
            )
        else:
            self.deafen_voice_button.configure(
                text="Deafen", fg_color="#3a3a3a", hover_color="#4a4a4a"
            )

    def on_close(self) -> None:
        """Ensures background audio threads and sockets close on window exit."""
        self.engine.stop()
        self.destroy()
        logger.info("Window closed. See you later!")
