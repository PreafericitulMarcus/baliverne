import customtkinter as ctk
from audio_engine import AudioEngine

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
            text="Mute (M)",
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
            text="Join Voice (J)",
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
            text="Deafen (D)",
            width=90,
            height=36,
            corner_radius=0,
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=self.on_deafen_click,
        )
        self.deafen_voice_button.pack(side="left", padx=8)

        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _bind_shortcuts(self) -> None:
        self.bind("<j>", lambda e: self.on_connect_click())
        self.bind("<J>", lambda e: self.on_connect_click())
        self.bind("<m>", lambda e: self.on_mute_click())
        self.bind("<M>", lambda e: self.on_mute_click())
        self.bind("<d>", lambda e: self.on_deafen_click())
        self.bind("<D>", lambda e: self.on_deafen_click())

    def on_connect_click(self) -> None:
        if not self.engine.is_running:
            self.engine.start()
            self.status_value.configure(text="Connected", text_color="#2ecc71")
            self.connect_voice_button.configure(
                text="Leave Voice (J)", fg_color="#e74c3c", hover_color="#c0392b"
            )
        else:
            self.engine.stop()
            self.status_value.configure(text="Offline", text_color="#e74c3c")
            self.connect_voice_button.configure(
                text="Join Voice (J)", fg_color="#2ecc71", hover_color="#27ae60"
            )

    def on_mute_click(self) -> None:
        muted = self.engine.toggle_mute()
        if muted:
            self.mute_voice_button.configure(
                text="Unmute (M)", fg_color="#c0392b", hover_color="#962d22"
            )
        else:
            self.mute_voice_button.configure(
                text="Mute (M)", fg_color="#3a3a3a", hover_color="#4a4a4a"
            )

    def on_deafen_click(self) -> None:
        deafened = self.engine.toggle_deafen()
        if deafened:
            self.deafen_voice_button.configure(
                text="Undeafen (D)", fg_color="#c0392b", hover_color="#962d22"
            )
        else:
            self.deafen_voice_button.configure(
                text="Deafen (D)", fg_color="#3a3a3a", hover_color="#4a4a4a"
            )

    def on_close(self) -> None:
        """Ensures background audio threads and sockets close on window exit."""
        self.engine.stop()
        self.destroy()
