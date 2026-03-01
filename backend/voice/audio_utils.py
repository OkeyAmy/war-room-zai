"""
WAR ROOM — Audio Utilities
PCM conversion, resampling, and audio format helpers.
"""

from __future__ import annotations

import struct
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def resample_pcm(
    audio_data: bytes,
    source_rate: int,
    target_rate: int,
    sample_width: int = 2,  # 16-bit
) -> bytes:
    """
    Simple linear interpolation resampling for PCM audio.
    For production, use a proper resampling library (e.g., scipy, librosa).

    Args:
        audio_data: Raw PCM bytes.
        source_rate: Source sample rate (e.g., 16000).
        target_rate: Target sample rate (e.g., 24000).
        sample_width: Bytes per sample (2 for 16-bit).

    Returns:
        Resampled PCM bytes.
    """
    if source_rate == target_rate:
        return audio_data

    # Parse samples
    num_samples = len(audio_data) // sample_width
    fmt = f"<{num_samples}h"  # little-endian signed 16-bit
    try:
        samples = list(struct.unpack(fmt, audio_data))
    except struct.error:
        logger.warning("Failed to unpack audio data for resampling")
        return audio_data

    # Resample via linear interpolation
    ratio = target_rate / source_rate
    new_length = int(num_samples * ratio)
    resampled = []

    for i in range(new_length):
        src_idx = i / ratio
        idx_floor = int(src_idx)
        idx_ceil = min(idx_floor + 1, num_samples - 1)
        frac = src_idx - idx_floor

        sample = int(samples[idx_floor] * (1 - frac) + samples[idx_ceil] * frac)
        sample = max(-32768, min(32767, sample))
        resampled.append(sample)

    return struct.pack(f"<{len(resampled)}h", *resampled)


def pcm_to_wav_header(
    data_length: int,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """
    Generate a WAV file header for PCM data.

    Args:
        data_length: Length of PCM data in bytes.
        sample_rate: Sample rate.
        channels: Number of channels.
        sample_width: Bytes per sample.

    Returns:
        44-byte WAV header.
    """
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    bits_per_sample = sample_width * 8

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        data_length + 36,
        b"WAVE",
        b"fmt ",
        16,  # Subchunk1Size (PCM)
        1,   # AudioFormat (PCM)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_length,
    )
    return header


def merge_audio_chunks(chunks: list[bytes]) -> bytes:
    """Merge multiple PCM audio chunks into a single byte string."""
    return b"".join(chunks)


def audio_duration_seconds(
    audio_data: bytes,
    sample_rate: int = 24000,
    sample_width: int = 2,
    channels: int = 1,
) -> float:
    """Calculate the duration of PCM audio data in seconds."""
    if not audio_data:
        return 0.0
    bytes_per_second = sample_rate * sample_width * channels
    return len(audio_data) / bytes_per_second


def is_silence(
    audio_data: bytes,
    threshold: int = 500,
    sample_width: int = 2,
) -> bool:
    """
    Check if a PCM audio chunk is silence (below amplitude threshold).
    Useful for manual VAD fallback.

    Args:
        audio_data: Raw PCM bytes.
        threshold: Amplitude threshold for silence detection.
        sample_width: Bytes per sample.

    Returns:
        True if the chunk is considered silence.
    """
    if not audio_data:
        return True

    num_samples = len(audio_data) // sample_width
    fmt = f"<{num_samples}h"
    try:
        samples = struct.unpack(fmt, audio_data)
    except struct.error:
        return True

    # RMS amplitude
    rms = (sum(s * s for s in samples) / num_samples) ** 0.5
    return rms < threshold
