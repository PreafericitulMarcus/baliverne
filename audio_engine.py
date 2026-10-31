import queue
import socket
import threading
import logging
import numpy as np
import sounddevice as sd
import opuslib_next as opus

logger = logging.getLogger(__name__)


class AudioEngine:
    def __init__(
        self,
        local_port: int = 5001,
        target_ip: str = "127.0.0.1",
        target_port: int = 5002,
        sample_rate: int = 48000,
        channels: int = 1,
        block_size: int = 960,  # 48 kHz * 20ms
    ):
        self.local_port = local_port
        self.target_ip = target_ip
        self.target_port = target_port
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self.dtype = "int16"

        # Audio state
        self.is_running = False
        self.is_muted = False
        self.is_deafened = False
        self.output_volume: float = 1.0

        # Networking & Audio hardware handles
        self.sock: socket.socket | None = None
        self.stream: sd.Stream | None = None

        # Thread-safe queues
        self.inbound_buffer = queue.Queue(maxsize=100)
        self.outbound_buffer = queue.Queue(maxsize=100)

        # Background worker threads
        self.receiver_thread: threading.Thread | None = None
        self.sender_thread: threading.Thread | None = None

        self.encoder = None
        self.decoder = None

    def start(self) -> None:
        if self.is_running:
            return

        logger.info(
            f"Starting AudioEngine on port {self.local_port}, targeting {self.target_ip}:{self.target_port}"
        )
        self.is_running = True

        self.encoder = opus.Encoder(
            self.sample_rate, self.channels, opus.APPLICATION_VOIP
        )
        self.decoder = opus.Decoder(self.sample_rate, self.channels)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", self.local_port))

        self.receiver_thread = threading.Thread(
            target=self._network_receive_loop, daemon=True
        )
        self.receiver_thread.start()

        self.sender_thread = threading.Thread(
            target=self._network_send_loop, daemon=True
        )
        self.sender_thread.start()

        self.stream = sd.Stream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.block_size,
            callback=self._audio_callback,
        )
        self.stream.start()
        logger.info("Audio stream and network threads started successfully.")

    def stop(self) -> None:
        if not self.is_running:
            return

        logger.info("Stopping AudioEngine...")
        self.is_running = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if self.sock:
            self.sock.close()
            self.sock = None

        self._clear_queue(self.inbound_buffer)
        self._clear_queue(self.outbound_buffer)
        logger.info("AudioEngine stopped and buffers cleared.")

    def _clear_queue(self, q: queue.Queue) -> None:
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break

    def toggle_mute(self) -> bool:
        self.is_muted = not self.is_muted
        logger.info(f"Microphone muted: {self.is_muted}")
        return self.is_muted

    def toggle_deafen(self) -> bool:
        self.is_deafened = not self.is_deafened
        logger.info(f"Audio deafened: {self.is_deafened}")
        return self.is_deafened

    def set_volume(self, volume: float) -> None:
        self.output_volume = max(0.0, min(volume, 1.5))
        logger.debug(f"Volume adjusted to {self.output_volume:.2f}")

    def _network_receive_loop(self) -> None:
        logger.debug("Receiver thread started.")
        while self.is_running and self.sock:
            try:
                data, _ = self.sock.recvfrom(4096)

                if self.decoder is None:
                    continue

                decoded_data = self.decoder.decode(data, self.block_size)

                if not self.inbound_buffer.full():
                    self.inbound_buffer.put_nowait(decoded_data)
                else:
                    logger.warning("Inbound buffer full, dropping frame.")
            except queue.Full:
                pass
            except opus.OpusError as ope:
                logger.debug(f"Opus decode failed (corrupt packet?): {ope}")
            except OSError as e:
                if self.is_running:
                    logger.error(f"Socket error in receive loop: {e}")
                break
        logger.debug("Receiver thread exiting.")

    def _network_send_loop(self) -> None:
        logger.debug("Sender thread started.")
        while self.is_running and self.sock:
            try:
                # timeout allows the loop to check self.is_running periodically
                raw_pcm = self.outbound_buffer.get(timeout=0.1)

                if not self.is_muted and self.encoder is not None:
                    encoded_data = self.encoder.encode(raw_pcm, self.block_size)
                    logger.debug(
                        f"Opus: {len(raw_pcm)} bytes -> {len(encoded_data)} bytes"
                    )
                    self.sock.sendto(encoded_data, (self.target_ip, self.target_port))
            except queue.Empty:
                continue
            except opus.OpusError as ope:
                logger.error(f"Opus encode failed: {ope}")
            except OSError as e:
                if self.is_running:
                    logger.error(f"Socket error in send loop: {e}")
                break
        logger.debug("Sender thread exiting.")

    def _audio_callback(self, indata, outdata, frames, time_info, status):
        if status:
            logger.warning(f"Audio callback status: {status}")

        # 1. Microphone Outbound
        if self.is_running and not self.is_muted:
            try:
                self.outbound_buffer.put_nowait(indata.tobytes())
            except queue.Full:
                pass  # Network thread is lagging behind; drop mic frame

        # 2. Speaker Inbound
        if self.is_deafened or self.output_volume == 0.0:
            outdata.fill(0)
            return

        try:
            packet = self.inbound_buffer.get_nowait()
            pcm_data = np.frombuffer(packet, dtype=self.dtype).reshape(
                -1, self.channels
            )

            if self.output_volume != 1.0:
                scaled = pcm_data.astype(np.float32) * self.output_volume
                outdata[:] = np.clip(scaled, -32768, 32767).astype(np.dtype(self.dtype))
            else:
                outdata[:] = pcm_data
        except queue.Empty:
            outdata.fill(0)
