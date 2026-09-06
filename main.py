import numpy as np
import pyaudiowpatch as pyaudio
import threading        # インプット用
import queue
# import asyncio          # タスク用、検討
# import websocket
from faster_whisper import WhisperModel

MODEL = "base"          # 軽 → 重: "tiny" (75MB), "base" (142MB), "small" (466MB), "medium" (1.5GB), "large-v3" (3.0GB)
DEVICE = "cuda"         # CPU: "cpu", Nvidia GPU: "cuda"

SAMPLE_RATE_MIC = 16000
CHUNK_DURATION = 1.0
MAX_BUFFER_DURATION = 10

class Mic:
    def __init__(self):
        self._pa = pyaudio.PyAudio()
        self.queueNormal = queue.Queue()
        self.queueFlattened = queue.Queue()
        self._running = False
        self._devices = {
            index: self._pa.get_device_info_by_index(index) for index in range(self._pa.get_device_count())
            if self._pa.get_device_info_by_index(index)["maxInputChannels"] > 0
        }

    def start(self, sampleRate: int | None = None, deviceIndex: int | None = None, chunkDuration: int | float = 0.5, flatten: bool = True):
        self.deviceIndex = int(self._pa.get_default_input_device_info()["index"]) if deviceIndex == None else deviceIndex
        self.sampleRate = int(self._pa.get_device_info_by_index(self.deviceIndex)["defaultSampleRate"]) if sampleRate == None else sampleRate
        self.channels = self._pa.get_device_info_by_index(self.deviceIndex)["maxInputChannels"]
        self.chunkDuration = chunkDuration
        self.chunkLength = int(self.chunkDuration * self.sampleRate)
        self._flatten = flatten
        self._running = True
        self._stream = self._pa.open(
            format = pyaudio.paFloat32, rate = self.sampleRate, channels = self.channels, input_device_index = self.deviceIndex, input = True, frames_per_buffer = self.chunkLength
        )
        threading.Thread(target = self._loop, daemon = True).start()

    def start_manual(self):
        for index, device in self._devices.items():
            print(f"[{index}] {device['name']}")

        while True:
            try:
                deviceIndex = int(input("Select input device index: "))
                if deviceIndex not in self._devices:
                    continue
                sampleRate = input("Sample rate (enter to use device's default value): ")
                sampleRate = None if sampleRate == "" else int(sampleRate)
                chunkDuration = input("Chunk duration (enter to use default value 0.5): ")
                chunkDuration = 0.5 if chunkDuration == "" else float(chunkDuration)
                break
            except ValueError:
                pass

        self.start(sampleRate = sampleRate, deviceIndex = deviceIndex, chunkDuration = chunkDuration)

    def _loop(self):
        print(f"Mic {self.deviceIndex}: started loop")
        while (self._running):
            if (self._flatten):
                self.queueFlattened.put(np.frombuffer(self._stream.read(self.chunkLength, exception_on_overflow = False), dtype = np.float32).reshape(-1, self.channels).mean(axis = 1))
            self.queueNormal.put(np.frombuffer(self._stream.read(self.chunkLength, exception_on_overflow = False), dtype = np.float32))

    def stop(self):
        self._running = False
        self._stream.stop_stream()
        self._stream.close()
        self._pa.terminate()
        print(f"Mic {self.deviceIndex}: successfully stopped")

class Speaker:
    def __init__(self, sampleRate: int, channels: int):
        self._pa = pyaudio.PyAudio()
        self.sampleRate = sampleRate
        self.channels = channels
        self._stream = self._open()

    def _open(self) -> pyaudio.Stream:
        return self._pa.open(
            format = pyaudio.paFloat32, rate = self.sampleRate, channels = self.channels, output = True
        )

    def play(self, audioBytes):
        self._stream.write(audioBytes)

    def restart(self):
        try:
            self._stream.stop_stream()
            self._stream.close()
        except Exception:
            pass
        self._stream = self._open()

    def close(self):
        self._stream.stop_stream()
        self._stream.close()
        self._pa.terminate()

class WhisperObject:
    def __init__(self, modelSize: str = "base", device: str = "cpu", computeType: str = "int8"):
        self._modelSize = modelSize
        self._device = device
        self._computeType = computeType
        self._model = WhisperModel(self._modelSize, device = self._device, compute_type = self._computeType)

    def transcribe(self, audioData):
        return self._model.transcribe(audioData, beam_size = 5, vad_filter = True, task = "transcribe")


def main():
    # init test
    # mic = Mic()
    # mic.start_manual()
    # mic.stop()

    # with buffer slice playback
    mic = Mic()
    mic.start(sampleRate = SAMPLE_RATE_MIC, chunkDuration = CHUNK_DURATION)
    speaker = Speaker(sampleRate = SAMPLE_RATE_MIC, channels = mic.channels)
    model = WhisperObject(modelSize = "base", device = "cuda", computeType = "float16")
    audioBuffer = np.empty(0, dtype = np.float32)

    while True:
        audioSliceNormal = mic.queueNormal.get()
        audioSliceFlattened = mic.queueFlattened.get()
        speaker.play(audioSliceNormal.tobytes())
        audioBuffer = np.concatenate((audioBuffer, audioSliceFlattened))
        if (len(audioBuffer) > mic.sampleRate * 10):
            audioBuffer = audioBuffer[-MAX_BUFFER_DURATION * mic.sampleRate:]
        segments, info = model.transcribe(audioBuffer)

        for segment in segments:
            print(f"\r[{info.language}] {segment.text:<100}", end = "", flush = True)

if __name__ == "__main__":
    main()