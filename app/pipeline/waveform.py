"""Waveform peak extraction from media files using PyAV and NumPy."""

from pathlib import Path

import av
import numpy as np


def extract_waveform_peaks(input_path: Path, num_peaks: int = 1000) -> list[float]:
    """
    Extract normalized peak audio amplitude values from a media file.

    Returns a list of float values bounded in [0.0, 1.0] representing the audio envelope,
    ideal for rendering in a web timeline or waveform visualizer.
    """
    frame_peaks: list[float] = []
    try:
        with av.open(str(input_path)) as container:
            if not container.streams.audio:
                return []
            for frame in container.decode(container.streams.audio[0]):
                arr = frame.to_ndarray()
                if arr.size == 0:
                    continue
                if arr.dtype == np.uint8:
                    peak = float(np.max(np.abs(arr.astype(np.float32) - 128.0))) / 128.0
                elif np.issubdtype(arr.dtype, np.integer):
                    peak = float(np.max(np.abs(arr))) / float(np.iinfo(arr.dtype).max)
                else:
                    peak = float(np.max(np.abs(arr)))
                frame_peaks.append(min(1.0, max(0.0, peak)))
    except av.FFmpegError, ValueError, RuntimeError, OSError:
        return []

    if not frame_peaks:
        return []

    sampled = (
        [float(np.max(c)) for c in np.array_split(frame_peaks, num_peaks)]
        if len(frame_peaks) > num_peaks
        else frame_peaks
    )
    max_p = max(sampled)
    scale = (1.0 / max_p) if max_p > 0.01 else 1.0
    return [round(min(1.0, p * scale), 4) for p in sampled]
