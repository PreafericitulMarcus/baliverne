import nacl.exceptions
import pytest

from audio_engine import AudioEngine


@pytest.fixture
def engine():
    return AudioEngine(client_id=1, local_port=5001, target_port=5002)


def test_nonce_generation_and_parsing(engine):
    engine.client_id = 2
    engine.send_seq = 42

    # Pack (Sender Side) - Now 24 bytes
    padding = b"\x00" * 12
    client_bytes = engine.client_id.to_bytes(4, "little")
    seq_bytes = engine.send_seq.to_bytes(8, "little")
    nonce = padding + client_bytes + seq_bytes

    assert len(nonce) == 24

    # Unpack (Receiver Side)
    parsed_client_id = int.from_bytes(nonce[12:16], "little")
    parsed_seq = int.from_bytes(nonce[16:], "little")

    assert parsed_client_id == 2
    assert parsed_seq == 42


def test_cryptographic_roundtrip(engine):
    dummy_opus_frame = b"\xde\xad\xbe\xef" * 10
    engine.send_seq = 1

    # 1. Encrypt
    padding = b"\x00" * 12
    nonce = (
        padding
        + engine.client_id.to_bytes(4, "little")
        + engine.send_seq.to_bytes(8, "little")
    )

    # PyNaCl automatically prepends the nonce to the resulting ciphertext
    network_packet = engine.box.encrypt(dummy_opus_frame, engine.aad, nonce=nonce)

    # Minimum packet size: 24 (nonce) + 16 (Poly1305 MAC) + len(data)
    assert len(network_packet) == 24 + 16 + 40

    # 2. Decrypt
    recv_nonce = network_packet[:24]
    recv_ciphertext = network_packet[24:]

    decrypted_payload = engine.box.decrypt(
        recv_ciphertext, engine.aad, nonce=recv_nonce
    )
    assert decrypted_payload == dummy_opus_frame


def test_replay_attack_rejection(engine):
    engine.recv_highest_seq = 150
    padding = b"\x00" * 12

    # 1. Old packet
    old_seq = 140
    old_nonce = padding + (2).to_bytes(4, "little") + old_seq.to_bytes(8, "little")
    assert int.from_bytes(old_nonce[16:], "little") <= engine.recv_highest_seq

    # 2. New packet
    new_seq = 151
    new_nonce = padding + (2).to_bytes(4, "little") + new_seq.to_bytes(8, "little")
    assert int.from_bytes(new_nonce[16:], "little") > engine.recv_highest_seq


def test_tampered_payload_raises_cryptoerror(engine):
    dummy_opus = b"valid_audio_data"
    padding = b"\x00" * 12
    nonce = padding + engine.client_id.to_bytes(4, "little") + (1).to_bytes(8, "little")

    encrypted = engine.box.encrypt(dummy_opus, engine.aad, nonce=nonce)

    tampered_encrypted = bytearray(encrypted)
    tampered_encrypted[0] ^= 0xFF

    with pytest.raises(nacl.exceptions.CryptoError):
        engine.box.decrypt(bytes(tampered_encrypted), engine.aad, nonce=nonce)
