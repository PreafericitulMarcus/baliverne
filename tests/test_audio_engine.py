import pytest
import queue
import numpy as np
import opuslib_next as opus
from audio_engine import AudioEngine


@pytest.fixture
def engine():
    """Provides a fresh AudioEngine instance for each test."""
    return AudioEngine(local_port=5001, target_port=5002)


def test_initial_state(engine):
    assert engine.is_running is False
    assert engine.is_muted is False
    assert engine.is_deafened is False
    assert engine.output_volume == 1.0


def test_toggle_mute(engine):
    assert engine.toggle_mute() is True
    assert engine.is_muted is True
    assert engine.toggle_mute() is False
    assert engine.is_muted is False


def test_toggle_deafen(engine):
    assert engine.toggle_deafen() is True
    assert engine.is_deafened is True
    assert engine.toggle_deafen() is False
    assert engine.is_deafened is False


def test_set_volume_boundaries(engine):
    # Test valid mid-range
    engine.set_volume(0.5)
    assert engine.output_volume == 0.5

    # Test upper bound clipping (max 1.5)
    engine.set_volume(2.0)
    assert engine.output_volume == 1.5

    # Test lower bound clipping (min 0.0)
    engine.set_volume(-0.5)
    assert engine.output_volume == 0.0


def test_opus_compression_roundtrip():
    """
    Tests the Opus encode/decode math independently from the sockets and hardware threads.
    """
    encoder = opus.Encoder(48000, 1, opus.APPLICATION_VOIP)
    decoder = opus.Decoder(48000, 1)
    frame_size = 960

    # 1. Generate 960 samples of dummy audio (1920 bytes)
    raw_pcm = np.zeros(frame_size, dtype=np.int16).tobytes()
    assert len(raw_pcm) == 1920

    # 2. Encode to Opus
    encoded_data = encoder.encode(raw_pcm, frame_size)

    # Verify compression occurred
    assert 0 < len(encoded_data) < len(raw_pcm)

    # 3. Decode back to PCM
    decoded_data = decoder.decode(encoded_data, frame_size)

    # Verify the byte size is restored perfectly
    assert len(decoded_data) == len(raw_pcm)


def test_queue_clearing(engine):
    """Tests that lingering audio packets are wiped when stopped."""
    engine.inbound_buffer.put(b"dummy_data_1")
    engine.outbound_buffer.put(b"dummy_data_2")

    engine._clear_queue(engine.inbound_buffer)
    engine._clear_queue(engine.outbound_buffer)

    assert engine.inbound_buffer.empty() is True
    assert engine.outbound_buffer.empty() is True


def test_audio_callback_volume_scaling(engine):
    """Tests that volume math correctly scales PCM data."""
    engine.output_volume = 0.5
    engine.channels = 1
    engine.dtype = "int16"

    # Create a fake decoded PCM packet with a known amplitude (10000)
    fake_pcm = np.full(960, 10000, dtype=np.int16)
    engine.inbound_buffer.put(fake_pcm.tobytes())

    # Create a dummy outdata array for the callback to write into
    outdata = np.zeros((960, 1), dtype=np.int16)

    # Trigger the callback manually (ignoring indata/mic for this test)
    engine._audio_callback(
        indata=None, outdata=outdata, frames=960, time_info=None, status=None
    )

    # 10000 * 0.5 = 5000
    assert outdata[0][0] == 5000


def test_audio_callback_clipping(engine):
    """Tests that extreme volume doesn't overflow 16-bit limits and cause static."""
    engine.output_volume = 1.5
    engine.channels = 1

    # 30000 * 1.5 = 45000 (which exceeds the int16 max of 32767)
    fake_pcm = np.full(960, 30000, dtype=np.int16)
    engine.inbound_buffer.put(fake_pcm.tobytes())

    outdata = np.zeros((960, 1), dtype=np.int16)
    engine._audio_callback(
        indata=None, outdata=outdata, frames=960, time_info=None, status=None
    )

    # Must be safely clipped to the 16-bit ceiling
    assert outdata[0][0] == 32767
