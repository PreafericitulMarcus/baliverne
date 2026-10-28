import queue
import socket
import threading
import numpy as np
import sounddevice as sd


class AudioEngine:
    def __init__(
        self,
        local_port: int = 5001,
        target_ip: str = "127.0.0.1",
        target_port: int = 5002,
        sample_rate: int = 48000,
        channels: int = 1,
        block_size: int = 1024,
    ):
        self.local_port = local_port
        self.target_ip = target_ip
        self.target_port = target_port
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.dtype = "int16"

        # State flags
        self.is_running = False
        self.is_muted = False
        self.is_deafened = False

        # Networking & Audio state
        self.sock: socket.socket | None = None
        self.stream: sd.Stream | None = None
        self.audio_buffer = queue.Queue(maxsize=100)
        self.receiver_thread: threading.Thread | None = None

    def start(self) -> None:
        """Starts network socket, listener thread, and audio hardware stream."""
        if self.is_running:
            return

        self.is_running = True

        # 1. Setup UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.local_port))

        # 2. Run socket receiver thread
        self.receiver_thread = threading.Thread(
            target=self._network_receive_loop, daemon=True
        )
        self.receiver_thread.start()

        # 3. Start audio stream
        self.stream = sd.Stream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.block_size,
            callback=self._audio_callback,
        )
        self.stream.start()

    def stop(self) -> None:
        """Stops audio stream and closes the socket."""
        if not self.is_running:
            return

        self.is_running = False

        # Close audio stream
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        # Close socket (breaks listener loop)
        if self.sock:
            self.sock.close()
            self.sock = None

        # Clear buffer
        while not self.audio_buffer.empty():
            try:
                self.audio_buffer.get_nowait()
            except queue.Empty:
                break

    def toggle_mute(self) -> bool:
        self.is_muted = not self.is_muted
        return self.is_muted

    def toggle_deafen(self) -> bool:
        self.is_deafened = not self.is_deafened
        return self.is_deafened

    def _network_receive_loop(self) -> None:
        while self.is_running and self.sock:
            try:
                data, _ = self.sock.recvfrom(4096)
                if not self.audio_buffer.full():
                    self.audio_buffer.put_nowait(data)
            except (OSError, queue.Full):
                break

    def _audio_callback(self, indata, outdata, frames, time_info, status):
        # 1. Mic Outbound: Send only if not muted and network is active
        if self.is_running and self.sock and not self.is_muted:
            try:
                self.sock.sendto(indata.tobytes(), (self.target_ip, self.target_port))
            except OSError:
                pass

        # 2. Speaker Inbound: Play only if not deafened
        if self.is_deafened:
            outdata.fill(0)
            return

        try:
            packet = self.audio_buffer.get_nowait()
            outdata[:] = np.frombuffer(packet, dtype=self.dtype).reshape(
                -1, self.channels
            )
        except queue.Empty:
            outdata.fill(0)
