"""Compatibility wrapper for pyrnnoise 0.4.3 with audiolab 0.5.x.

The upstream pyrnnoise 0.4.3 Python wrapper still uses the pre-0.5
``audiolab.av.Graph`` keyword names.  The native RNNoise extension continues
to come from the pyrnnoise package; this module only replaces its Python
wrapper so applications do not need to patch site-packages.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np
from audiolab.av import Graph, aformat
from pyrnnoise.rnnoise import FRAME_SIZE, SAMPLE_RATE, create, destroy, process_frame


class RNNoise:
    """Streaming RNNoise denoiser compatible with audiolab 0.5.x."""

    def __init__(self, sample_rate: int):
        self.sample_rate = sample_rate
        self.channels: int | None = None
        self.denoise_states = None
        self.dtype = None
        self._in_graph = None
        self._out_graph = None

    def __del__(self):
        self.reset()

    @property
    def in_graph(self):
        if self._in_graph is None:
            self._in_graph = Graph(
                sample_rate=self.sample_rate,
                dtype=self.dtype,
                channels=self.channels,
                filters=[aformat(np.int16, sample_rate=SAMPLE_RATE)],
                frame_size=FRAME_SIZE,
            )
        return self._in_graph

    @property
    def out_graph(self):
        if self._out_graph is None:
            self._out_graph = Graph(
                sample_rate=SAMPLE_RATE,
                dtype=np.int16,
                channels=self.channels,
                filters=[aformat(np.int16, sample_rate=self.sample_rate)],
            )
        return self._out_graph

    def reset(self):
        if self.denoise_states is not None:
            for denoise_state in self.denoise_states:
                destroy(denoise_state)
        self.denoise_states = None
        self._in_graph = None
        self._out_graph = None

    def denoise_frame(self, frame: np.ndarray, partial: bool = False):
        if self.denoise_states is None:
            self.denoise_states = [create() for _ in range(self.channels)]

        denoised_frame, speech_probs = process_frame(self.denoise_states, frame)
        if self.sample_rate != SAMPLE_RATE:
            self.out_graph.push(denoised_frame)
            output = [audio for audio, _ in self.out_graph.pull(partial)]
            if not output:
                return speech_probs, np.empty((self.channels, 0), dtype=np.int16)
            denoised_frame = np.concatenate(output, axis=1)

        if partial:
            self.reset()
        return speech_probs, denoised_frame

    def denoise_chunk(
        self, chunk: np.ndarray, partial: bool = False
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Yield denoised frames for ``chunk`` shaped ``(channels, samples)``."""
        chunk = np.atleast_2d(chunk)
        self.channels = chunk.shape[0]
        self.dtype = chunk.dtype
        self.in_graph.push(chunk)
        frames = [frame for frame, _ in self.in_graph.pull(partial)]
        for index, frame in enumerate(frames):
            yield self.denoise_frame(frame, partial and index == len(frames) - 1)
