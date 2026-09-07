import numpy as np
import pyaudiowpatch as pyaudio
import threading        # インプット用
import queue
import time
import wave
import sys
import os
import helper
import asyncio          # タスク用、検討
# import websocket
from faster_whisper import WhisperModel
from scipy.signal import resample_poly
from pyrnnoise_customfork import RNNoise

MODEL = "base"         # 軽 → 重: "tiny" (75MB), "base" (142MB), "small" (466MB), "medium" (1.5GB), "large-v3" (3.0GB)
DEVICE = "cuda"         # CPU: "cpu", Nvidia GPU: "cuda"

SAMPLE_RATE_MIC = 16000
CHUNK_DURATION = 2.0
MAX_BUFFER_DURATION = 20

class Mic:
    def __init__(self, sampleRate: int | None = None, deviceIndex: int | None = None, chunkDuration: int | float = 0.5, flatten: bool = True, denoise: bool = True, manual: bool = False):
        self._pa = pyaudio.PyAudio()
        self.queue = queue.Queue()
        self.queuePlayback = queue.Queue()
        self._running = False
        self._devices = {
            index: self._pa.get_device_info_by_index(index) for index in range(self._pa.get_device_count())
            if self._pa.get_device_info_by_index(index)["maxInputChannels"] > 0
        }
        if (manual):
            self.start_manual()
        else:
            self.start(sampleRate = sampleRate, deviceIndex = deviceIndex, chunkDuration = chunkDuration, flatten = flatten, denoise = denoise)

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
        for index, device in self._devices.items():
            print(f"[{index}] {device['name']}")

        while True:
            try:
                deviceIndex = int(input("\nSelect input device index: "))
                if deviceIndex not in self._devices:
                    continue
                sampleRate = input(f"Sample rate (enter to use device's default value {self._pa.get_device_info_by_index(deviceIndex)["defaultSampleRate"]}): ")
                sampleRate = None if sampleRate == "" else int(sampleRate)
                chunkDuration = input("Chunk duration (enter to use default value 0.5[s]): ")
                chunkDuration = 0.5 if chunkDuration == "" else float(chunkDuration)
                while True:
                    flatten = input("Flatten channels (true/false): ")
                    if (flatten == ""):
                        flatten = True
                        print("Using default settings: True")
                        break
                    if (helper.succeeds(int, flatten)[0]):
                        flatten = int(flatten) != 0
                        break
                    else:
                        if (flatten.lower() not in ["true", "false"]):
                            continue
                        flatten = flatten.lower() == "true"
                        break
                while True:
                    denoise = input("Denoise audio (true/false): ")
                    if (denoise == ""):
                        denoise = True
                        print("Using default settings: True")
                        break
                    if (helper.succeeds(int, denoise)[0]):
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
                audio = buffer.reshape(-1, self.channels).mean(axis = 1)
                # audio = resample_poly(audio, 48000, self.sampleRate)
                denoisedBuffer = [
                    denoised for _, denoised in self._denoiser.denoise_chunk(audio)
                ]
                if not denoisedBuffer:
                    continue
                audio = np.concatenate(denoisedBuffer, axis = 1)
                audio = audio.astype(np.float32) / np.iinfo(np.int16).max
                # audio = resample_poly(audio, self.sampleRate, 48000)
                buffer = audio.mean(axis = 0) if self._flatten else audio.T.ravel()
            elif self._flatten:
                buffer = buffer.reshape(-1, self.channels).mean(axis = 1)

            self.queue.put(buffer.astype(np.float32))
            self.queuePlayback.put(buffer.astype(np.float32))
            
    def stop(self):
        self._running = False
        self._stream.stop_stream()
        self._stream.close()
        self._pa.terminate()
        print(f"Mic {self.deviceIndex}: successfully stopped")

class Speaker:
    def __init__(self, sampleRate: int | None = None, deviceIndex: int | None = None, manual: bool = False):
        self._pa = pyaudio.PyAudio()
        self._devices = {
            index: self._pa.get_device_info_by_index(index) for index in range(self._pa.get_device_count())
            if self._pa.get_device_info_by_index(index)["maxOutputChannels"] > 0
        }
        if (manual):
            self._stream = self.open_manual()
        else:
            self._stream = self._open(sampleRate = sampleRate, deviceIndex = deviceIndex)

    def _open(self, sampleRate: int | None = None, deviceIndex: int | None = None) -> pyaudio.Stream:
        self.deviceIndex = int(self._pa.get_default_output_device_info()["index"]) if deviceIndex == None else deviceIndex
        self.sampleRate = int(self._pa.get_device_info_by_index(self.deviceIndex)["defaultSampleRate"]) if sampleRate == None else sampleRate
        self.channels = self._pa.get_device_info_by_index(self.deviceIndex)["maxOutputChannels"]
        return self._pa.open(
            format = pyaudio.paFloat32, rate = self.sampleRate, channels = self.channels, output = True, output_device_index = self.deviceIndex
        )

    def open_manual(self):
        for index, device in self._devices.items():
            print(f"[{index}] {device['name']}")

        while True:
            try:
                deviceIndex = int(input("\nSelect output device index: "))
                if deviceIndex not in self._devices:
                    continue
                sampleRate = input(f"Sample rate (enter to use device's default value {self._pa.get_device_info_by_index(deviceIndex)["defaultSampleRate"]}): ")
                sampleRate = int(self._pa.get_device_info_by_index(deviceIndex)["defaultSampleRate"]) if sampleRate == "" else int(sampleRate)
                break
            except ValueError:
                pass

        return self._open(sampleRate = sampleRate, deviceIndex = deviceIndex)

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
    models = ["tiny", "base", "small", "medium", "large-v3"]
    computeType = [["int8", "float32"], ["int8", "float16", "float32"]]

    def __init__(self, modelSize: str | int = "base", device: str = "cpu", computeType: str = "int8", language: str | None = None, manual: bool = False):
        self._modelSize = modelSize
        self._device = device
        self._computeType = computeType
        self._language = language

        if (manual):
            while True:
                self._modelSize = input(f"Select model ({str(WhisperObject.models)[1:-1]}): ")
                if (self._modelSize in WhisperObject.models):
                    break
                elif (self._modelSize == ""):
                    self._modelSize = "base"
                    print(f"Using default model: {self._modelSize}")
                    break
                elif (modelSizeIndex := helper.succeeds(int, self._modelSize))[0]:
                    if (0 <= modelSizeIndex[1] < len(WhisperObject.models)):
                        self._modelSize = WhisperObject.models[modelSizeIndex[1]]
                        break
            while True:
                self._device = input("Select device (cpu, cuda)): ")
                if (self._device in ["cpu", "cuda"]):
                    break
                elif (self._device == ""):
                    self._device = "cuda"
                    print(f"Using default device: {self._device}")
                    break
                elif (deviceIndex := helper.succeeds(int, self._device))[0]:
                    if (0 <= deviceIndex[1] <= 1):
                        self._device = ["cpu", "cuda"][deviceIndex[1]]
                        break 
            while True:
                computeTypeAvailable = WhisperObject.computeType[0 if self._device == "cpu" else 1]
                self._computeType = input(f"Select compute type ({str(computeTypeAvailable)}): ")
                if (self._computeType in computeTypeAvailable):
                    break
                elif (self._computeType == ""):
                    self._computeType = "int8" if self._device == "cpu" else "float16"
                    print(f"Using default compute type for device {self._device}: {self._computeType}")
                    break
                elif (computeTypeIndex := helper.succeeds(int, self._computeType))[0]:
                    if (0 <= computeTypeIndex[1] < len(computeTypeAvailable)):
                        self._computeType = computeTypeAvailable[computeTypeIndex[1]]
                        break

        self._model = WhisperModel(self._modelSize, device = self._device, compute_type = self._computeType)

        if (manual):
            while True:
                self._language = input("Select language (type \"list\" to display list): ")
                match (self._language):
                    case "":
                        self._language = None
                        print("No language specified, detecting all languages")
                        break
                    case "list":
                        print(f"Available languages: {str(self._model.supported_languages)[1:-1]}")
                    case _:
                        if (self._language in self._model.supported_languages):
                            break

    def transcribe(self, audioData, contextual: bool | None = None, beamSize: int = 5, filter: bool = True):
        segments, info = self._model.transcribe(audioData, beam_size = beamSize, vad_filter = filter, task = "transcribe", condition_on_previous_text = self._contextual if contextual == None else contextual, language = self._language)
        segments = list(segments)

        return segments, info

    def transcribe_to_text(self, audioData, contextual: bool | None = None, beamSize: int = 5, filter: bool = True):
        segments, info = self.transcribe(audioData, contextual = contextual, beamSize = beamSize, filter = filter)
        text = ""
        language = info.language

        for segment in segments:
            text += segment.text

        return text, language

class Transcriber:
    transcriberID = 0
    transcriptionLock: asyncio.Lock | None = None

    def __init__(self, name: str | None = None, whisperObject: WhisperObject | None = None, speaker: bool = False, beamSize: int = 1, filter: bool = True, manual: bool = True):
        if (whisperObject == None):
            raise ValueError("Error: whisperObject cannot be empty")
        self.name = name if name != None else f"Transcriber{Transcriber.transcriberID}"
        self.id = Transcriber.transcriberID
        Transcriber.transcriberID += 1
        self._mic = Mic(manual = manual)

        if (manual):
            while True:
                speaker = input("\nUse speaker playback (true/false): ")
                if (speaker == ""):
                    speaker = False
                    print("Using default settings: False")
                    break
                elif (returnTuple := helper.succeeds(int, speaker))[0]:
                    speaker = returnTuple[1]
                    break
                else:
                    if (speaker.lower() not in ["true", "false"]):
                        continue
                    speaker = speaker.lower() == "true"
                    break
            while True:
                null, beamSize = helper.succeeds(int, input("Beam size (1~20): "))
                if (0 < beamSize < 21):
                    break
            while True:
                filter = input("Use filter (true/false): ")
                if (filter == ""):
                    filter = True
                    print("Using default settings: True")
                    break
                elif (returnTuple := helper.succeeds(int, filter))[0]:
                    filter = returnTuple[1]
                    break
                else:
                    if (filter.lower() not in ["true", "false"]):
                        continue
                    filter = filter.lower() == "true"
                    break
            
        self._speaker = Speaker(manual = manual) if speaker else None
        self._model = whisperObject
        self.transcribeText = ""
        self.transcribeTextNoncontextual = ""
        self.language = ""
        self.languageNoncontextual = ""
        self._beamSize = beamSize
        self._filter = filter
        self.timeToTranscribe = 0.0
        self._buffer = np.empty(0, dtype = np.float32)

        self.task = asyncio.create_task(self._loop())
        # self.taskPlayback = asyncio.create_task(self._playback())

    async def _loop(self):
        while True:
            if (self._mic.queue.empty()):
                await asyncio.sleep(0.1)
                continue

            while (not self._mic.queue.empty()):
                audioSlice = self._mic.queue.get()
                self._buffer = np.concatenate((self._buffer, resample_poly(audioSlice, 16000, self._mic.sampleRate)))

            if (len(self._buffer) > 16000 * MAX_BUFFER_DURATION):
                # with wave.open("test.wav", "wb") as wf:
                #     wf.setnchannels(1)
                #     wf.setsampwidth(2)
                #     wf.setframerate(16000)
                #     wf.writeframes((self._buffer * 32767).astype(np.int16).tobytes())
                self._buffer = self._buffer[-MAX_BUFFER_DURATION * 16000:]

            async with Transcriber.get_lock():   
                timeTranscribeStart = time.perf_counter()
                self.transcribeText, self.language = await asyncio.to_thread(self._model.transcribe_to_text, self._buffer, True, self._beamSize, self._filter)
                self.transcribeTextNoncontextual, self.languageNoncontextual = await asyncio.to_thread(self._model.transcribe_to_text, self._buffer, False, self._beamSize, self._filter)
                self.timeToTranscribe = time.perf_counter() - timeTranscribeStart

    async def _playback(self):
        while True:
            if (self._mic.queue.empty()):
                await asyncio.sleep(0.1)
                continue

            # stereo only
            audioSlice = self._mic.queuePlayback.get()
            if (self._speaker != None):
                audio = resample_poly(audioSlice, self._speaker.sampleRate, self._mic.sampleRate).astype(np.float32)
                audio = np.repeat(audio[:, np.newaxis], self._speaker.channels, axis = 1).ravel()

                await asyncio.to_thread(self._speaker.play, audio.tobytes())

    def close(self):
        self.task.cancel()
        self._mic.stop()
        if self._speaker != None:
            self._speaker.close()

    @classmethod
    def get_lock(cls) -> asyncio.Lock:
        if cls.transcriptionLock is None:
            cls.transcriptionLock = asyncio.Lock()
        return cls.transcriptionLock



async def main():
    transcribers = []
    try:
        os.system("")

        while True:
            try:
                instancesCount = int(input("Set amount of instances: "))
                break
            except:
                pass
        Transcriber.transcriptionLock = asyncio.Lock()
        whisperObject = WhisperObject(manual = True)
        print("Initiated whisper\n")
        transcribers = [Transcriber(whisperObject = whisperObject, manual = True) for _ in range(instancesCount)]

        iterationCount = 0
        
        while True:
            print(f"[{iterationCount}] Last transcribe time {sum(transcriber.timeToTranscribe for transcriber in transcribers):.5f}s")

            for i, transcriber in enumerate(transcribers):
                print(f"\rInstance {i}: \t[{transcriber.language}] {transcriber.transcribeText[-50:]:<50}\033[K")
                print(f"\r              \t[{transcriber.languageNoncontextual}] {transcriber.transcribeTextNoncontextual[-50:]:<50}\033[K")

            print(f"\033[{(instancesCount * 2) + 1}A\r", end = "")
            iterationCount += 1
            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n\nExiting")
    finally:
        for transcriber in transcribers:
            transcriber.close()

if __name__ == "__main__":
    asyncio.run(main())
