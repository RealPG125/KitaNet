import numpy as np
import pyaudiowpatch as pyaudio
import threading        # インプット用
import queue
import time
import wave
import sys
import os
import helper
# import asyncio          # タスク用、検討
# import websocket
from faster_whisper import WhisperModel
from scipy.signal import resample_poly
from pyrnnoise_customfork import RNNoise

MODEL = "small"         # 軽 → 重: "tiny" (75MB), "base" (142MB), "small" (466MB), "medium" (1.5GB), "large-v3" (3.0GB)
DEVICE = "cuda"         # CPU: "cpu", Nvidia GPU: "cuda"

SAMPLE_RATE_MIC = 16000
CHUNK_DURATION = 2.0
MAX_BUFFER_DURATION = 20

class Mic:
    def __init__(self):
        self._pa = pyaudio.PyAudio()
        self.queue = queue.Queue()
        self._running = False
        self._devices = {
            index: self._pa.get_device_info_by_index(index) for index in range(self._pa.get_device_count())
            if self._pa.get_device_info_by_index(index)["maxInputChannels"] > 0
        }

    def start(self, sampleRate: int | None = None, deviceIndex: int | None = None, chunkDuration: int | float = 0.5, flatten: bool = True, denoise: bool = True):
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

        if (denoise):
            self._denoise = True
            self._denoiser = RNNoise(self.sampleRate)
        else:
            self._denoise = False

        threading.Thread(target = self._loop, daemon = True).start()

    def start_manual(self):
        """
        設定を入力してマイクを開始する。

        引数:
            なし

        戻り値:
            なし
        """
        for index, device in self._devices.items():
            print(f"[{index}] {device['name']}")

        while True:
            try:
                deviceIndex = int(input("\nSelect input device index: "))
                if deviceIndex not in self._devices:
                    continue
                sampleRate = input("Sample rate (enter to use device's default value): ")
                sampleRate = None if sampleRate == "" else int(sampleRate)
                chunkDuration = input("Chunk duration (enter to use default value 0.5[s]): ")
                chunkDuration = 0.5 if chunkDuration == "" else float(chunkDuration)
                while True:
                    flatten = input("Flatten channels (enter to use default value True): ")
                    if (flatten == ""):
                        flatten = True
                        break
                    if (helper.succeeds(int, flatten)):
                        flatten = int(flatten) != 0
                        break
                    else:
                        if (flatten.lower() not in ["true", "false"]):
                            continue
                        flatten = flatten.lower() == "true"
                        break
                while True:
                    denoise = input("Denoise audio (enter to use default value True): ")
                    if (denoise == ""):
                        denoise = True
                        break
                    if (helper.succeeds(int, denoise)):
                        denoise = int(denoise) != 0
                        break
                    else:
                        if (denoise.lower() not in ["true", "false"]):
                            continue
                        denoise = denoise.lower() == "true"
                        break
                break
            except ValueError:
                pass

        self.start(sampleRate = sampleRate, deviceIndex = deviceIndex, chunkDuration = chunkDuration, flatten = flatten, denoise = denoise)

    def _loop(self):
        print(f"\nMic {self.deviceIndex}: started loop with {self.sampleRate} hz sampling rate and {self.chunkLength} samples length chunk")

        while (self._running):
            rawBuffer = self._stream.read(self.chunkLength, exception_on_overflow = False)
            buffer = np.frombuffer(rawBuffer, dtype = np.float32)
            if (self._denoise):
                # audio = buffer.reshape(-1, self.channels).T
                # denoisedBuffer = [
                #     denoised for _, denoised in self._denoiser.denoise_chunk(audio)
                # ]
                # if not denoisedBuffer:
                #     continue
                # audio = np.concatenate(denoisedBuffer, axis = 1)
                # buffer = audio.mean(axis = 0) if self._flatten else audio.T.reshape(-1)
                pass
            elif (self._flatten):
                buffer = buffer.reshape(-1, self.channels).mean(axis = 1)

            self.queue.put(buffer.astype(np.float32))
            
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
    def __init__(self, modelSize: str = "base", device: str = "cpu", computeType: str = "int8", language: str | None = None, contextual: bool = True):
        self._modelSize = modelSize
        self._device = device
        self._computeType = computeType
        self._language = language
        self._contextual = contextual

        if (language == None):
            self._model = WhisperModel(self._modelSize, device = self._device, compute_type = self._computeType)
        else:
            self._model = WhisperModel(self._modelSize, device = self._device, compute_type = self._computeType, language = self._language)

    def transcribe(self, audioData):
        segments, info = self._model.transcribe(audioData, beam_size = 5, vad_filter = True, task = "transcribe", condition_on_previous_text = self._contextual)
        segments = list(segments)

        return segments, info

    def transcribe_to_text(self, audioData):
        segments, info = self.transcribe(audioData)
        text = ""
        language = info.language

        for segment in segments:
            text += segment.text

        return text, language
        


def main():
    try:
        os.system("")

        instancesCount = int(input("Set amount of instances: "))
        mics = [Mic() for _ in range(instancesCount)]
        micsState = [False for _ in range(instancesCount)]
        buffers = [np.empty(0, dtype = np.float32) for _ in range(instancesCount)]
        transcribeText = ["" for _ in range(instancesCount)]
        transcribeTextNoncontextual = ["" for _ in range(instancesCount)]
        language = ["nan" for _ in range(instancesCount)]
        languageNoncontextual = ["nan" for _ in range(instancesCount)]

        timeTranscribe = 0.0

        for i in range(instancesCount):
            mics[i].start_manual()

        models = [WhisperObject(modelSize = "base", device = "cuda", computeType = "float16") for _ in range(instancesCount)]
        modelsNoncontextual = [WhisperObject(modelSize = "base", device = "cuda", computeType = "float16", contextual = False) for _ in range(instancesCount)]
        print("Initiated whisper\n")

        while True:
            print(f"Last transcribe time {timeTranscribe:.5f}s")
            timeTranscribe = 0.0

            for i in range(instancesCount):
                if (mics[i].queue.empty()):
                    micsState[i] = False
                    time.sleep(0.1)

                while (not mics[i].queue.empty()):
                    audioSlice = mics[i].queue.get()
                    buffers[i] = np.concatenate((buffers[i], resample_poly(audioSlice, 16000, mics[i].sampleRate)))
                    micsState[i] = True

                if (micsState[i]):
                    if (len(buffers[i]) > 16000 * MAX_BUFFER_DURATION):
                        buffers[i] = buffers[i][-MAX_BUFFER_DURATION * 16000:]

                    timeTranscribeStart = time.perf_counter()
                    transcribeText[i], language[i] = models[i].transcribe_to_text(buffers[i])
                    timeTranscribe += time.perf_counter() - timeTranscribeStart
                    
                    timeTranscribeStart = time.perf_counter()
                    transcribeTextNoncontextual[i], languageNoncontextual[i] = modelsNoncontextual[i].transcribe_to_text(buffers[i])
                    timeTranscribe += time.perf_counter() - timeTranscribeStart

                print(f"\rInstance {i}: \t[{language[i]}] {transcribeText[i][-50:]:<50}\033[K")
                print(f"\r              \t[{language[i]}] {transcribeTextNoncontextual[i][-50:]:<50}\033[K")

            print(f"\033[{(instancesCount * 2) + 1}A\r", end = "")

    except KeyboardInterrupt:
        try:
            for i in range(instancesCount):
                mics[i].stop()
        except:
            pass
        print("\n\n\nExiting")

if __name__ == "__main__":
    main()
