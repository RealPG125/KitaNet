import numpy as np
import pyaudiowpatch as pyaudio
import threading        # インプット用
import queue
import time
import wave
# import asyncio          # タスク用、検討
# import websocket
from faster_whisper import WhisperModel
from scipy.signal import resample_poly

MODEL = "small"          # 軽 → 重: "tiny" (75MB), "base" (142MB), "small" (466MB), "medium" (1.5GB), "large-v3" (3.0GB)
DEVICE = "cuda"         # CPU: "cpu", Nvidia GPU: "cuda"

SAMPLE_RATE_MIC = 16000
CHUNK_DURATION = 2.0
MAX_BUFFER_DURATION = 20

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
        print(f"Mic {self.deviceIndex}: started loop with {self.sampleRate} hz sampling rate and {self.chunkLength} samples length chunk")
        while (self._running):
            buffer = np.frombuffer(self._stream.read(self.chunkLength, exception_on_overflow = False), dtype = np.float32)
            self.queueNormal.put(buffer)
            if (self._flatten):
                self.queueFlattened.put(buffer.reshape(-1, self.channels).mean(axis = 1))
            
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
    # mic.start(sampleRate = SAMPLE_RATE_MIC, chunkDuration = CHUNK_DURATION)
    mic.start_manual()
    # speaker = Speaker(sampleRate = mic.sampleRate, channels = 2)
    model = WhisperObject(modelSize = "base", device = "cuda", computeType = "float16")
    audioBuffer = np.empty(0, dtype = np.float32)

    while True:
        audioSliceFlattened = mic.queueFlattened.get()
        audioBuffer = np.concatenate((audioBuffer, resample_poly(audioSliceFlattened, 16000, mic.sampleRate)))
        if (len(audioBuffer) > 16000 * MAX_BUFFER_DURATION):
            # デバッグ用保存
            # with wave.open("test.wav", "wb") as wf:
            #     wf.setnchannels(1)
            #     wf.setsampwidth(2)
            #     wf.setframerate(16000)
            #     wf.writeframes((audioBuffer * 32767).astype(np.int16).tobytes())
            # exit()

            audioBuffer = audioBuffer[-MAX_BUFFER_DURATION * 16000:]

        timeTranscribeStart = time.perf_counter()
        segments, info = model.transcribe(audioBuffer)
        timeTranscribe = time.perf_counter() - timeTranscribeStart

        print(f"\rLast transcribe time {timeTranscribe:.5f}s [{info.language}]", end = " ")
        fulltext = ""

        for segment in segments:
            fulltext += segment.text

        print(f"{fulltext[-100:]:<100}", end = "")

if __name__ == "__main__":
    main()