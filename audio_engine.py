import logging
import os
import queue
import socket
import sys
import threading

import nacl.exceptions
import nacl.secret
import numpy as np
import opuslib_next as opus
import sounddevice as sd
from dotenv import load_dotenv

from stun_client import discover_public_coordinates

logger = logging.getLogger(__name__)

load_dotenv()
SUPER_SECRET_KEY = bytes.fromhex(os.environ["SUPER_SECRET_KEY"])

if sys.platform == "win32":
    basedir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    os.add_dll_directory(basedir)


class AudioEngine:
    def __init__(
        self,
        client_id: int,  # 1 for A, 2 for B
        local_port: int = 5001,
        sample_rate: int = 48000,
        channels: int = 1,
        block_size: int = 960,  # 48 kHz * 20ms
    ):
        self.client_id = client_id
        self.local_port = local_port
        self.target_ip: str | None = None
        self.target_port: int | None = None
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

        # Encoder & decoder
        self.encoder = None
        self.decoder = None

        # Cryptography
        self.box = nacl.secret.Aead(SUPER_SECRET_KEY)
        self.aad = b"baliverne_voice_session_v1"
        self.send_seq = 0
        self.recv_highest_seq = -1

    def bind_and_discover(self) -> tuple[str, int]:
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", self.local_port))

        logger.info("Querying STUN for public coordinates...")
        public_ip, public_port = discover_public_coordinates(self.sock)
        return public_ip, public_port

    def start(self, peer_ip: str, peer_port: int) -> None:
        if self.is_running:
            return

        logger.info(
            f"Starting AudioEngine on port {self.local_port}, targeting {self.target_ip}:{self.target_port}"
        )
        self.is_running = True

        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(("0.0.0.0", self.local_port))

        self.target_ip = peer_ip
        self.target_port = peer_port

        logger.info(f"Punching UDP hole to {self.target_ip}:{self.target_port}")
        self.sock.sendto(b"PUNCH", (self.target_ip, self.target_port))

        self.send_seq = 0
        self.recv_highest_seq = -1

        self.encoder = opus.Encoder(
            self.sample_rate, self.channels, opus.APPLICATION_VOIP
        )
        self.decoder = opus.Decoder(self.sample_rate, self.channels)

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

        if self.sock is None:
            return
        self.sock.settimeout(0.2)

        while self.is_running and self.sock:
            try:
                data, _ = self.sock.recvfrom(4096)

                if data == b"PUNCH":
                    logger.debug("Received peer's hole-punch packet")
                    continue

                # Minimum viable packet length (24 byte sequence + 16 byte MAC tag + Opus data)
                if len(data) < 40:
                    continue

                nonce = data[:24]
                ciphertext = data[24:]
                seq = int.from_bytes(nonce[16:], "little")

                if seq <= self.recv_highest_seq:
                    logger.debug(f"Dropped delayed/replayed packet (Seq {seq})")
                    continue

                decrypted_receive = self.box.decrypt(ciphertext, self.aad, nonce=nonce)

                self.recv_highest_seq = seq

                if self.decoder is None:
                    continue

                decoded_data = self.decoder.decode(decrypted_receive, self.block_size)

                if not self.inbound_buffer.full():
                    self.inbound_buffer.put_nowait(decoded_data)
                else:
                    logger.warning("Inbound buffer full, dropping frame.")
            except TimeoutError:
                continue
            except nacl.exceptions.CryptoError:
                logger.warning("Packet decyption failed (tampered or wrong key).")
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
                    # logger.debug(
                    #     f"Opus: {len(raw_pcm)} bytes -> {len(encoded_data)} bytes"
                    # )

                    self.send_seq += 1

                    # 12 bytes (Padding) + 4 bytes (Client ID) + 8 bytes (Sequence) = 24-byte Nonce
                    padding = b"\x00" * 12
                    client_bytes = self.client_id.to_bytes(4, "little")
                    seq_bytes = self.send_seq.to_bytes(8, "little")
                    nonce = padding + client_bytes + seq_bytes

                    encrypted_send = self.box.encrypt(
                        encoded_data, self.aad, nonce=nonce
                    )

                    self.sock.sendto(encrypted_send, (self.target_ip, self.target_port))
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
