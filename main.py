import numpy as np
import pyaudiowpatch as pyaudio
import threading
import queue
import time
import wave
import sys
import os
import helper
import asyncio
# import websocket
from faster_whisper import WhisperModel
from scipy.signal import resample_poly
from pyrnnoise_customfork import RNNoise
from io import BytesIO
from pydub import AudioSegment

# model     : 軽 → 重: "tiny" (75MB), "base" (142MB), "small" (466MB), "medium" (1.5GB), "large-v3" (3.0GB)
# device    : "cpu", Nvidia GPU: "cuda"

MAX_BUFFER_DURATION = 20
SILENCE_THRESHOLD = 0.08
LLM_TRIGGER_SILENCE_DURATION = 2.0

class Mic:
    def __init__(self, sampleRate: int | None = None, deviceIndex: int | None = None, chunkDuration: int | float = 0.5, flatten: bool = True, denoise: bool = True, manual: bool = False):
        self._pa = pyaudio.PyAudio()
        self.queue = queue.Queue()
        self.queuePlayback = queue.Queue()
        self._running = False
        self.peakAmplitude = -1
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
                        denoise = False
                        print("Using default settings: False")
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
        print(f"Mic {self.deviceIndex}: started loop with {self.sampleRate} hz sampling rate and {self.chunkLength} samples length chunk")

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

            self.peakAmplitude = np.max(np.abs(buffer))
            
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

    def play(self, audioSample, sourceSampleRate: int | None = None, sourceChannels: int | None = None):
        if (sourceSampleRate != None):
            audioSample = resample_poly(audioSample, self.sampleRate, sourceSampleRate)
        if (sourceChannels != None):
            if (sourceChannels != self.channels):
                audioSample = audioSample.reshape(-1, sourceChannels).mean(axis = 1)
                audioSample = np.repeat(audioSample[:, np.newaxis], self.channels, axis = 1).ravel()
        self._stream.write(audioSample.tobytes())

    def restart(self):
        try:
            self._stream.stop_stream()
            self._stream.close()
        except Exception:
            pass

        self._stream = self._open()

    def abortPlayback(self):
        # find ways to safely restart stream
        pass

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
                    self._modelSize = "small"
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

    def transcribe_to_text(self, audioData, contextual: bool | None = None, beamSize: int = 5, filter: bool = True, splitParts: bool = False):
        segments, info = self.transcribe(audioData, contextual = contextual, beamSize = beamSize, filter = filter)
        text = ""
        language = info.language

        for index, segment in enumerate(segments):
            text += (f"[{index}]" if splitParts else "") + segment.text + (f"<>{segment.start} - {segment.end}" if splitParts and (index < len(segments) - 1) else "")

        return text, language

class Transcriber:
    transcriberID = 0
    transcriptionLock: asyncio.Lock | None = None

    def __init__(self, name: str | None = None, whisperObject: WhisperObject | None = None, speaker: bool = False, beamSize: int = 1, filter: bool = True, useContextual: str | int = 1, splitParts: bool = False, manual: bool = True, diarization: bool = False):
        if (whisperObject == None):
            raise ValueError("Error: whisperObject cannot be empty")
        self.name = name if name != None else f"Transcriber{Transcriber.transcriberID}"
        self.id = Transcriber.transcriberID
        Transcriber.transcriberID += 1
        self.mic = Mic(manual = manual) # OPEN FOR DEBUG, CHANGE TO PROTECTED LATER

        if (manual):
            while True:
                speaker = input("Use speaker playback (true/false): ")
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
            while True:
                useContextual = input("Use contextual (true/false/both): ")
                if (useContextual == ""):
                    useContextual = 1
                    print("Using default settings: True")
                    break
                elif (returnTuple := helper.succeeds(int, useContextual))[0]:
                    if (0 <= returnTuple[1] <= 2):
                        useContextual = returnTuple[1]
                        break
                else:
                    if (useContextual.lower() in ["true", "false", "both"]):
                        useContextual = ["false", "true", "both"].index(useContextual.lower())
                        break
            while True:
                diarization = input("Enable diarization preview (true/false): ")
                if (diarization == ""):
                    diarization = False
                    print("Using default settings: False")
                    break
                elif (returnTuple := helper.succeeds(int, diarization))[0]:
                    if (0 <= returnTuple[1] <= 1):
                        diarization = returnTuple[1] == 1
                        break
                else:
                    if (diarization.lower() in ["true", "false"]):
                        diarization = diarization.lower() == "true"
                        break
            while True:
                splitParts = input("Split transcription sections (true/false): ")
                if (splitParts == ""):
                    splitParts = False
                    print("Using default settings: False")
                    break
                elif (returnTuple := helper.succeeds(int, splitParts))[0]:
                    if (0 <= returnTuple[1] <= 1):
                        splitParts = returnTuple[1] == 1
                        break
                else:
                    if (splitParts.lower() in ["true", "false"]):
                        splitParts = splitParts.lower() == "true"
                        break

        self._speaker = Speaker(manual = manual) if speaker else None
        self._model = whisperObject
        self._diarizationTool = DiarizationTool() if diarization else None
        self.enableDiarization = diarization
        self.diarizationOutput = None
        self._splitParts = splitParts
        self.transcribeText = ""
        self.transcribeTextNoncontextual = ""
        self.language = ""
        self.languageNoncontextual = ""
        self._beamSize = beamSize
        self._filter = filter
        self.timeToTranscribe = 0.0
        self._buffer = np.empty(0, dtype = np.float32)
        self.contextualMode = [useContextual in [1, 2], useContextual in [0, 2]]

        self.task = asyncio.create_task(self._loop())
        if (self._speaker != None):
            threading.Thread(target = self._playback, daemon = True).start()
        if (diarization):
            self.taskDiarization = asyncio.create_task(self._diarization())

    async def _loop(self):
        while True:
            if (self.mic.queue.empty()):
                await asyncio.sleep(0.01)
                continue

            while (not self.mic.queue.empty()):
                audioSlice = self.mic.queue.get()
                self._buffer = np.concatenate((self._buffer, resample_poly(audioSlice, 16000, self.mic.sampleRate)))

            if (len(self._buffer) > 16000 * MAX_BUFFER_DURATION):
                # with wave.open("test.wav", "wb") as wf:
                #     wf.setnchannels(1)
                #     wf.setsampwidth(2)
                #     wf.setframerate(16000)
                #     wf.writeframes((self._buffer * 32767).astype(np.int16).tobytes())
                self._buffer = self._buffer[-MAX_BUFFER_DURATION * 16000:]

            if (self.contextualMode[0]):
                async with Transcriber.get_lock():
                    timeTranscribeStart = time.perf_counter()
                    self.transcribeText, self.language = await asyncio.to_thread(self._model.transcribe_to_text, self._buffer, True, self._beamSize, self._filter, self._splitParts)
                    self.timeToTranscribe = time.perf_counter() - timeTranscribeStart

            if (self.contextualMode[1]):
                async with Transcriber.get_lock():
                    timeTranscribeStart = time.perf_counter()
                    self.transcribeTextNoncontextual, self.languageNoncontextual = await asyncio.to_thread(self._model.transcribe_to_text, self._buffer, False, self._beamSize, self._filter, self._splitParts)
                    self.timeToTranscribe = time.perf_counter() - timeTranscribeStart

    def _playback(self):
        while True:
            if (self.mic.queuePlayback.empty()):
                time.sleep(0.1)
                continue

            # stereo only
            audioSlice = self.mic.queuePlayback.get()
            if (self._speaker != None):
                audio = resample_poly(audioSlice, self._speaker.sampleRate, self.mic.sampleRate).astype(np.float32)
                audio = np.repeat(audio[:, np.newaxis], self._speaker.channels, axis = 1).ravel()

                self._speaker.play(audio)

    async def _diarization(self):
        while True:
            # if (len(self._buffer) > 16000 * (MAX_BUFFER_DURATION / 2)):
            audioData = self._buffer.copy()
            try:
                self.diarizationOutput = await asyncio.to_thread(self._diarizationTool.process, audioData, 16000)
                await asyncio.sleep(MAX_BUFFER_DURATION / 8)
            except Exception as error:
                print(f"Diarization failed: {error}", file=sys.stderr)
                await asyncio.sleep(MAX_BUFFER_DURATION / 8)
            # else:
            #     await asyncio.sleep(MAX_BUFFER_DURATION / 8)

    def flushBuffer(self):
        self._buffer = np.empty(0, dtype = np.float32)

    def close(self):
        self.task.cancel()
        if self.enableDiarization:
            self.taskDiarization.cancel()
        self.mic.stop()
        if self._speaker != None:
            self._speaker.close()

    @classmethod
    def get_lock(cls) -> asyncio.Lock:
        if cls.transcriptionLock is None:
            cls.transcriptionLock = asyncio.Lock()
        return cls.transcriptionLock

class DiarizationTool:
    def __init__(self):
        import torch
        from pyannote.audio import Pipeline

        self._torch = torch
        self._torch.backends.cuda.matmul.allow_tf32 = False
        self._torch.backends.cudnn.allow_tf32 = False
        # self._torch.backends.cuda.matmul.fp32_precision = "ieee"
        # self._torch.backends.cudnn.fp32_precision = "ieee"
        self._pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token="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")
        self._pipeline.to(self._torch.device("cuda"))
        self.output = None

    def process(self, audioData, sampleRate: int):
        self.output = self._pipeline({
            "waveform": self._torch.from_numpy(audioData).unsqueeze(0),
            "sample_rate": sampleRate,
        })
        return self.output

class TTS:
    languageVoiceDict = {"ja": "ja-JP-NanamiNeural", "en": "en-US-EmmaNeural", "id": "id-ID-GadisNeural"}

    def __init__(self, voiceModel: str = "ja-JP-NanamiNeural", manual: bool = False):
        import edge_tts

        self.edgeTTS = edge_tts
        self._voiceShortnames = []
        self._voiceList = []
        self.manual = manual
        self.voiceModel = voiceModel # fallback

        self._speaker = Speaker(manual = manual)
    
    def promptManual(self):
        if (self.manual):
            for index, voice in enumerate(self._voiceShortnames):
                print(f"[{index}] {voice}")
            while True:
                voiceModel = input("Select voice model by index: ")
                if (voiceModel == ""):
                    voiceModel = "auto"
                    print("Using dictionary-provided auto voice model")
                    break
                elif (returnTuple := helper.succeeds(int, voiceModel))[0]:
                    if (0 <= returnTuple[1] <= len(self._voiceShortnames)):
                        voiceModel = self._voiceShortnames[returnTuple[1]]
                        break
            
        self._voiceModel = voiceModel


    def speak(self, text, language: str = "en"):
        voiceModel = (TTS.languageVoiceDict[language] if language in TTS.languageVoiceDict else TTS.languageVoiceDict["en"]) if self._voiceModel == "auto" else self._voiceModel
        communicator = self.edgeTTS.Communicate(text, voiceModel)

        audioData = b''

        for chunk in communicator.stream_sync():
            if chunk["type"] == "audio" and chunk["data"]:
                audioData += chunk["data"]

        audioData = np.array(AudioSegment.from_mp3(BytesIO(audioData)).get_array_of_samples())
        audioData = audioData.astype(np.float32) / np.iinfo(np.int16).max
        self._speaker.play(audioData, sourceSampleRate = 24000, sourceChannels = 1)

    def stopAudio(self):
        self._speaker.abortPlayback()

    @classmethod
    async def create(cls, voiceModel: str = "ja-JP-NanamiNeural", manual: bool = False):
        instance = cls(voiceModel = voiceModel, manual = manual)
        instance._voiceList = await instance.edgeTTS.voices.list_voices()
        instance._voiceShortnames = [voice["ShortName"] for voice in instance._voiceList]
        instance.promptManual()
        return instance

class LLM:
    def __init__(self, model: str = "llama3.2", systemPrompt: str | None = None, enableAudio: bool = True, tts: TTS | None = None, manual: bool = False):
        import ollama
        self.ollama = ollama

        if (manual):
            modelsList = self.ollama.list().get("models", [])
            for index, model in enumerate(modelsList):
                print(f"[{index}] {model}")
            while True:
                model = input("Select LLM model by index: ")
                if (model == ""):
                    model = "llama3.2"
                    print(f"Using default OLLAMA model: {model}")
                    break
                elif (returnTuple := helper.succeeds(int, model))[0]:
                    if (0 <= returnTuple[1] < len(modelsList)):
                        model = modelsList[returnTuple[1]]
                        break
                    
        self.model = model
        self.tts = tts
        self._enableAudio = enableAudio
        self.systemPrompt = "Reply in the same language as the input text. Be a casual chatting company and reply slightly short." if systemPrompt == None else systemPrompt
        self._response = None

    def getResponse(self, message: str | None = None):
        self._response = self.ollama.chat(model = self.model, messages = [
            {"role": "system", "content": self.systemPrompt},
            {"role": "user", "content": message}
            ]) if message != None else "Empty input message"
        return self._response

    def getTextResponse(self, message: str | None = None) -> str:
        return self.getResponse(message = message)['message']['content']

    def audioChat(self, message: str | None = None, language: str = "en"):
        if (not self._enableAudio):
            print("Audio is disabled")
        else:
            self.tts.speak(text = self.getTextResponse(message = message), language = language)

    def stopAudio(self):
        self.tts.stopAudio()

    @classmethod
    async def create(cls, model: str = "llama3.2", systemPrompt: str | None = None, enableAudio: bool = True, manual: bool = False):
        tts = await TTS.create(manual = manual) if enableAudio else None
        instance = cls(model = model, systemPrompt = systemPrompt, enableAudio = enableAudio, tts = tts, manual = manual)
        return instance



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

        while True:
            useLLM = input("Enable LLM interaction (true/false): ")
            if (useLLM == ""):
                useLLM = True
                print("Using default settings: True")
                break
            if (helper.succeeds(int, useLLM)[0]):
                useLLM = int(useLLM) != 0
                break
            else:
                if (useLLM.lower() not in ["true", "false"]):
                    continue
                useLLM = useLLM.lower() == "true"
                break

        if (useLLM):
            llm = await LLM.create(model = "qwen2.5:3b-instruct-q8_0", manual = True)

        iterationCount = 0
        silentTime = 0.0
        startTime = time.perf_counter()
        spoken = False
        
        while True:
            speakerCount = 0
            newlineCount = 0
            peakAmplitude = 0.0
            lastPeakTranscriber = -1
            print(f"[{iterationCount}] Last transcribe time {sum(transcriber.timeToTranscribe for transcriber in transcribers):.5f}s\033[K")

            for i, transcriber in enumerate(transcribers):
                print(f"Peak input signal: {transcriber.mic.peakAmplitude}\033[K")
                if (transcriber.mic.peakAmplitude > peakAmplitude):
                    peakAmplitude = transcriber.mic.peakAmplitude
                    lastPeakTranscriber = i

                if (transcriber.contextualMode[0]):
                    language = transcriber.language
                    text = transcriber.transcribeText
                    if (text.count("<>") > 0):
                        text = text.split("<>")
                        print(f"\rInstance {i}: \t[{language}] {text[0]}\033[K")
                        for textPart in text:
                            print(f"{textPart}\033[K")
                            newlineCount += 1
                    else:
                        print(f"\rInstance {i}: \t[{language}] {text[-50:]:<50}\033[K")

                if (transcriber.contextualMode[1]):
                    language = transcriber.languageNoncontextual
                    text = transcriber.transcribeTextNoncontextual
                    if (text.count("<>") > 0):
                        text = text.split("<>")
                        print(f"\rInstance {i}: \t[{language}] {text[0]}\033[K")
                        for textPart in text:
                            print(f"{textPart}\033[K")
                            newlineCount += 1
                    else:
                        print(f"\rInstance {i}: \t[{language}] {text[-50:]:<50}\033[K")
                        
                if (transcriber.enableDiarization):
                    try:
                        for turn, speaker in transcriber.diarizationOutput.speaker_diarization:
                            print(f"Start = {turn.start:.1f}s, Stop = {turn.end:.1f}s, {speaker}\033[K")
                            speakerCount += 1
                    except Exception as exception:
                        print(f"Diarization failed: {exception}")
                        speakerCount += 1
                        continue

            if (spoken):
                silentTime += time.perf_counter() - startTime
            startTime = time.perf_counter()

            print(f"Transcriber {lastPeakTranscriber} monitored for LLM input, time since last silence: {silentTime}\033[K")
            print("=============================================================================================================================\x1b[J")

            print(f"\033[{((transcriber.contextualMode.count(True) + 1) * len(transcribers)) + 3 + speakerCount + newlineCount}A\r", end = "")
            iterationCount += 1

            if (peakAmplitude > SILENCE_THRESHOLD):
                silentTime = 0
                spoken = True

            if ((silentTime > LLM_TRIGGER_SILENCE_DURATION) and spoken and useLLM):
                # llm.stopAudio()
                message = transcribers[lastPeakTranscriber].transcribeText
                if (message != ""):
                    llm.audioChat(message = message, language = transcribers[lastPeakTranscriber].language)
                for transcriber in transcribers:
                    transcriber.flushBuffer()
                silentTime = 0
                spoken = False
                
            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n\nExiting")
    finally:
        for transcriber in transcribers:
            transcriber.close()
        print("\033[K\n\033[K\n\033[K\n")

if __name__ == "__main__":
    asyncio.run(main())
