import numpy as np
import threading
import queue
import time
import sys
import os
import kitanet_helper
import asyncio
import torch
import re

# import websocket
from faster_whisper import WhisperModel
from scipy.signal import resample_poly
from io import BytesIO
from pydub import AudioSegment
from kitanet_audio import Mic, Speaker
from kitanet_comm import RTCInstance, get_ip
from pykokoro import GenerationConfig, KokoroSynthesizer, SynthesisConfig
from datetime import datetime
from websockets.asyncio.server import serve, ServerConnection
# from websockets.asyncio.client import ClientConnection

# model     : 軽 → 重: "tiny" (75MB), "base" (142MB), "small" (466MB), "medium" (1.5GB), "large-v3" (3.0GB)
# device    : "cpu", Nvidia GPU: "cuda"

MAX_BUFFER_DURATION = 20
SILENCE_THRESHOLD = 0.05
LLM_TRIGGER_SILENCE_DURATION = 1.0

class WhisperObject:
    models = ["tiny", "base", "small", "medium", "large-v3"]
    computeType = [["int8", "float32"], ["int8", "float16", "float32"]]

    def __init__(self, modelSize: str | int = "base", device: str = "cpu", computeType: str = "int8", language: str | None = None, manual: bool = False):
        self.modelSize = modelSize
        self._device = device
        self._computeType = computeType
        self._language = language

        if (manual):
            while True:
                self.modelSize = input(f"Select model ({str(WhisperObject.models)[1:-1]}): ")
                if (self.modelSize in WhisperObject.models):
                    break
                elif (self.modelSize == ""):
                    self.modelSize = "small"
                    print(f"Using default model: {self.modelSize}")
                    break
                elif (modelSizeIndex := kitanet_helper.succeeds(int, self.modelSize))[0]:
                    if (-1 <= modelSizeIndex[1] < len(WhisperObject.models)):
                        self.modelSize = WhisperObject.models[modelSizeIndex[1]] if modelSizeIndex[1] != -1 else None
                        break
            while True:
                self._device = input("Select device (cpu, cuda)): ")
                if (self._device in ["cpu", "cuda"]):
                    break
                elif (self._device == ""):
                    self._device = "cuda"
                    print(f"Using default device: {self._device}")
                    break
                elif (deviceIndex := kitanet_helper.succeeds(int, self._device))[0]:
                    if (0 <= deviceIndex[1] <= 1):
                        self._device = ["cpu", "cuda"][deviceIndex[1]]
                        break 
            while True:
                computeTypeAvailable = WhisperObject.computeType[0 if self._device == "cpu" else 1]
                self._computeType = input(f"Select compute type ({str(computeTypeAvailable)[1:-1]}): ")
                if (self._computeType in computeTypeAvailable):
                    break
                elif (self._computeType == ""):
                    self._computeType = "int8" if self._device == "cpu" else "float16"
                    print(f"Using default compute type for device {self._device}: {self._computeType}")
                    break
                elif (computeTypeIndex := kitanet_helper.succeeds(int, self._computeType))[0]:
                    if (0 <= computeTypeIndex[1] < len(computeTypeAvailable)):
                        self._computeType = computeTypeAvailable[computeTypeIndex[1]]
                        break

        if (self.modelSize != None):
            self._model = WhisperModel(self.modelSize, device = self._device, compute_type = self._computeType)

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
        if (self.modelSize != None):
            segments, info = self._model.transcribe(audioData, beam_size = beamSize, vad_filter = filter, task = "transcribe", condition_on_previous_text = self._contextual if contextual == None else contextual, language = self._language)
            segments = list(segments)

            return segments, info
        else:
            return None, None

    def transcribe_to_text(self, audioData, contextual: bool | None = None, beamSize: int = 5, filter: bool = True, splitParts: bool = False):
        if (self.modelSize != None):
            segments, info = self.transcribe(audioData, contextual = contextual, beamSize = beamSize, filter = filter)
            text = ""
            language = info.language

            for index, segment in enumerate(segments):
                text += (f"[{index}]" if splitParts else "") + segment.text + (f"<>{segment.start} - {segment.end}" if splitParts and (index < len(segments) - 1) else "")

            return text, language
        else:
            return "", ""

class Transcriber:
    transcriberID = 0
    transcriptionLock: asyncio.Lock | None = None

    def __init__(self, name: str | None = None, whisperObject: WhisperObject | None = None, enablePlayback: bool = False, beamSize: int = 1, filter: bool = True, useContextual: str | int = 1, splitParts: bool = False, manual: bool = True, diarization: bool = False, useRTC: bool = False, rtcInstance: RTCInstance | None = None, speakerDeviceIndex: int | None = None, speakerSampleRate: int | None = None, micSampleRate: int | None = None, micDeviceIndex: int | None = None, micChunkDuration: int | float = 0.5, micFlatten: bool = True, micDenoise: bool = True, micStem: bool = False):
        if (whisperObject == None):
            raise ValueError("Error: whisperObject cannot be empty")
        self.name = name if name != None else f"Transcriber{Transcriber.transcriberID}"
        self.id = Transcriber.transcriberID
        Transcriber.transcriberID += 1

        if (manual):
            while True:
                enablePlayback = input("Use speaker playback (true/false): ")
                if (enablePlayback == ""):
                    enablePlayback = False
                    print("Using default settings: False")
                    break
                elif (returnTuple := kitanet_helper.succeeds(int, enablePlayback))[0]:
                    enablePlayback = returnTuple[1]
                    break
                else:
                    if (enablePlayback.lower() not in ["true", "false"]):
                        continue
                    enablePlayback = enablePlayback.lower() == "true"
                    break
            while True:
                useRTC = input("Use RTC mic (true/false): ")
                if (useRTC == ""):
                    useRTC = False
                    print("Using default settings: False")
                    break
                elif (returnTuple := kitanet_helper.succeeds(int, useRTC))[0]:
                    useRTC = returnTuple[1]
                    break
                else:
                    if (useRTC.lower() not in ["true", "false"]):
                        continue
                    useRTC = useRTC.lower() == "true"
                    break
            while True:
                null, beamSize = kitanet_helper.succeeds(int, input("Beam size (1~20): "))
                if (0 < beamSize < 21):
                    break
            while True:
                filter = input("Use filter (true/false): ")
                if (filter == ""):
                    filter = True
                    print("Using default settings: True")
                    break
                elif (returnTuple := kitanet_helper.succeeds(int, filter))[0]:
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
                    useContextual = 0
                    print("Using default settings: False")
                    break
                elif (returnTuple := kitanet_helper.succeeds(int, useContextual))[0]:
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
                elif (returnTuple := kitanet_helper.succeeds(int, diarization))[0]:
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
                elif (returnTuple := kitanet_helper.succeeds(int, splitParts))[0]:
                    if (0 <= returnTuple[1] <= 1):
                        splitParts = returnTuple[1] == 1
                        break
                else:
                    if (splitParts.lower() in ["true", "false"]):
                        splitParts = splitParts.lower() == "true"
                        break

        self.mic = Mic(manual = manual, useRTC = useRTC, sampleRate = micSampleRate, deviceIndex = micDeviceIndex, chunkDuration = micChunkDuration, flatten = micFlatten, denoise = micDenoise, stem = micStem)
        self.useRTC: bool = useRTC
        self._speaker = Speaker(manual = manual, deviceIndex = speakerDeviceIndex, sampleRate = speakerSampleRate) if enablePlayback else None
        self._RTCInstance = rtcInstance if rtcInstance != None else RTCInstance(debug = True) if useRTC else None
        self._model: WhisperObject = whisperObject
        self._diarizationTool = DiarizationTool() if diarization else None
        self.enableDiarization: bool = diarization
        self.diarizationOutput = None
        self._splitParts: bool = splitParts
        self.transcribeText: str = ""
        self.transcribeTextNoncontextual: str = ""
        self.language: str = ""
        self.languageNoncontextual: str = ""
        self._beamSize: int = beamSize
        self._filter: bool = filter
        self.timeToTranscribe: float = 0.0
        self._buffer = np.empty(0, dtype = np.float32)
        self._queuePlayback = queue.Queue()
        self.contextualMode = [useContextual in [1, 2], useContextual in [0, 2]]
        self.started = False
        self.closed = False
        self.pauseTranscribe = False

        self.task = asyncio.create_task(self._loop())
        if (self._speaker != None):
            threading.Thread(target = self._playback, daemon = True).start()
        if (diarization):
            self.taskDiarization = asyncio.create_task(self._diarization())

    async def init_RTC(self):
        if (not self._RTCInstance.configured):
            await self._RTCInstance.init_auto_config(offer = True, channels = ["audio", "control"], stackData = True)
        await self.mic.start_RTC(rtcInstance = self._RTCInstance)

    async def _loop(self):
        while True:
            if (self._RTCInstance.states["connectionstate"] == "closed" and self.started):
                self.close()
                break

            if (self.mic.queue.empty()):
                await asyncio.sleep(0.01)
                continue

            while (not self.mic.queue.empty()):
                audioSlice = self.mic.queue.get()
                self._queuePlayback.put(audioSlice)
                self._buffer = np.concatenate((self._buffer, resample_poly(audioSlice, 16000, self.mic.sampleRate)))

            self.started = True

            if (len(self._buffer) > 16000 * MAX_BUFFER_DURATION):
                # with wave.open("test.wav", "wb") as wf:
                #     wf.setnchannels(1)
                #     wf.setsampwidth(2)
                #     wf.setframerate(16000)
                #     wf.writeframes((self._buffer * 32767).astype(np.int16).tobytes())
                self._buffer = self._buffer[-MAX_BUFFER_DURATION * 16000:]

            if (not self.pauseTranscribe):
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
            if (self._queuePlayback.empty()):
                time.sleep(0.1)
                continue

            audioSlice = self._queuePlayback.get()
            if (self._speaker != None):
                if (self._speaker.sampleRate != self.mic.sampleRate):
                    audio = resample_poly(audioSlice, self._speaker.sampleRate, self.mic.sampleRate).astype(np.float32)
                else:
                    audio = audioSlice.astype(np.float32)
                # audio = np.repeat(audio[:, np.newaxis], self._speaker.channels, axis = 1).ravel()

                self._speaker.play(audio, sourceChannels = self.mic.channels if not self.mic.flatten else 1, sourceSampleRate = self.mic.sampleRate)

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

    def flush_buffer(self):
        self.mic.flush_queue()
        self._buffer = np.empty(0, dtype = np.float32)

    def close(self):
        self.closed = True
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
        from pyannote.audio import Pipeline
        
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        # torch.backends.cuda.matmul.fp32_precision = "ieee"
        # torch.backends.cudnn.fp32_precision = "ieee"
        self._pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token="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")
        self._pipeline.to(torch.device("cuda"))
        self.output = None

    def process(self, audioData, sampleRate: int):
        self.output = self._pipeline({
            "waveform": torch.from_numpy(audioData).unsqueeze(0),
            "sample_rate": sampleRate,
        })
        return self.output

class TTS:
    edgeTTSLanguageVoiceDict = {"ja": "ja-JP-NanamiNeural", "en": "en-US-EmmaNeural", "id": "id-ID-GadisNeural"}
    kokoroTTSLanguageVoiceDict = {"ja": "jf_alpha", "en": "af_heart"}
    pykokoroTTSLanguageCodeDict = {"ja": "ja-jp", "en": "en-us"}

    def __init__(self, speakerInstance: Speaker | None = None, fallbackEdgeVoiceModel: str = "ja-JP-NanamiNeural", manual: bool = False, externalSpeaker: bool = False, mode: str = "edge"):
        import edge_tts
        from kokoro import KPipeline

        self.mode = mode
        self._edgeTTS = edge_tts if mode == "edge" else None
        self._kokoroTTSAggregate: dict[str, KPipeline] | None = {"ja": KPipeline(lang_code = "j"), "en": KPipeline(lang_code = "a")} if mode == "kokoro" else None
        if (mode == "pykokoro"):
            redundantOverheadConfigThatDoesAbsolutelyNoShit = SynthesisConfig(voice = TTS.kokoroTTSLanguageVoiceDict[language], generation = GenerationConfig(lang = TTS.pykokoroTTSLanguageCodeDict[language]))
            synthesizer = KokoroSynthesizer(redundantOverheadConfigThatDoesAbsolutelyNoShit)
            self._pykokoroSynthesizer = synthesizer.__enter__()
        self._voiceShortnames = []
        self._voiceList = []
        self.manual = manual
        self.voiceModel = fallbackEdgeVoiceModel # fallback

        self._speaker = None if externalSpeaker else Speaker(manual = manual) if speakerInstance == None else speakerInstance
    
    def prompt_manual(self):
        if (self.manual and self.mode == "edge"):
            for index, voice in enumerate(self._voiceShortnames):
                print(f"[{index}] {voice}")
            while True:
                voiceModel = input("Select voice model by index: ")
                if (voiceModel == ""):
                    voiceModel = "auto"
                    print("Using dictionary-provided auto voice model")
                    break
                elif (returnTuple := kitanet_helper.succeeds(int, voiceModel))[0]:
                    if (0 <= returnTuple[1] <= len(self._voiceShortnames)):
                        voiceModel = self._voiceShortnames[returnTuple[1]]
                        break
            
            self._voiceModel = voiceModel

    def invoke_speak(self, text, language: str = "en", speakerInstance: Speaker | None = None):
        audioData = self.generate_voice(text = text, language = language)
        if (speakerInstance == None):
            if (self._speaker.useRTC):
                self._speaker.play(audioData, sourceSampleRate = 24000, sourceChannels = 1)
            else:
                asyncio.create_task(self._speaker.async_play(audioData, sourceSampleRate = 24000, sourceChannels = 1))
        else:
            if (speakerInstance.useRTC):
                speakerInstance.play(audioData, sourceSampleRate = 24000, sourceChannels = 1)
            else:
                asyncio.create_task(speakerInstance.async_play(audioData, sourceSampleRate = 24000, sourceChannels = 1))

    def generate_voice(self, text, language: str = "en"):
        if (self.mode == "edge"):
            voiceModel = (TTS.edgeTTSLanguageVoiceDict[language] if language in TTS.edgeTTSLanguageVoiceDict else TTS.edgeTTSLanguageVoiceDict["en"]) if self._voiceModel == "auto" else self._voiceModel
            communicator = self._edgeTTS.Communicate(text, voiceModel)
            
            audioData = b''

            for chunk in communicator.stream_sync():
                if chunk["type"] == "audio" and chunk["data"]:
                    audioData += chunk["data"]

            audioData = np.array(AudioSegment.from_mp3(BytesIO(audioData)).get_array_of_samples())
            audioData = audioData.astype(np.float32) / np.iinfo(np.int16).max

            return audioData

        elif (self.mode == "kokoro"):
            language = language if language in TTS.kokoroTTSLanguageVoiceDict else "en"

            audioData = np.array([], dtype = np.float32)

            generator = self._kokoroTTSAggregate[language](text = text, voice = TTS.kokoroTTSLanguageVoiceDict[language], split_pattern = r'[.。!！？?\n]+')

            for i, (gs, ps, audio) in enumerate(generator):
                audioData = np.concatenate((audioData, audio.cpu().numpy()))

            return audioData

        elif (self.mode == "pykokoro"):
            language = language if language in TTS.kokoroTTSLanguageVoiceDict else "en"
            
            rendered = self._pykokoroSynthesizer.synthesize_text(text, language = TTS.pykokoroTTSLanguageCodeDict[language], voice = TTS.kokoroTTSLanguageVoiceDict[language])

            audioData = rendered.audio.astype(np.float32)

            return audioData

    def stop_audio(self):
        try:
            self._speaker.abortPlayback()
        except:
            pass

    def close(self):
        self._pykokoroSynthesizer.__exit__()

    @classmethod
    async def create(cls, speakerInstance: Speaker | None = None, voiceModel: str = "ja-JP-NanamiNeural", manual: bool = False, externalSpeaker: bool = False, mode: str = "edge"):
        instance = cls(speakerInstance = speakerInstance, fallbackEdgeVoiceModel = voiceModel, manual = manual, externalSpeaker = externalSpeaker, mode = mode)
        if (mode == "edge"):
            instance._voiceList = await instance._edgeTTS.voices.list_voices()
            instance._voiceShortnames = [voice["ShortName"] for voice in instance._voiceList]
        instance.prompt_manual()
        return instance

class LLM:
    def __init__(self, model: str = "llama3.2", systemPrompt: str | None = None, enableAudio: bool = True, tts: TTS | None = None, manual: bool = False):
        import ollama
        self.ollama = ollama
        self.asyncClient = self.ollama.AsyncClient()

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
                elif (returnTuple := kitanet_helper.succeeds(int, model))[0]:
                    if (0 <= returnTuple[1] < len(modelsList)):
                        model = modelsList[returnTuple[1]].model
                        break
                    
        self.model = model
        self.tts = tts
        self._enableAudio = enableAudio
        self.systemPrompt = "Reply in the same language as the input text. Be a casual chatting company." if systemPrompt == None else systemPrompt
        self.response = None

    def compile_message(self, message: str | None = None, memory: list[dict[str, str]] = []):
        compiledMessages = [{"role": "system", "content": self.systemPrompt}]
        for item in memory:
            compiledMessages.append({"role": "user", "content": item["user"]})
            compiledMessages.append({"role": "assistant", "content": item["response"]})
        compiledMessages.append({"role": "user", "content": message})

        return compiledMessages

    async def get_response(self, message: str | None = None, memory: list[dict[str, str]] = []):
        compiledMessages = self.compile_message(message = message, memory = memory)

        # print(compiledMessages)

        self.response = self.ollama.chat(model = self.model, messages = compiledMessages, think = False)["message"]["content"] if message != None else "Empty input message"
        return self.response

    async def get_text_response(self, message: str | None = None, memory: list[dict[str, str]] = []) -> str:
        response = await self.get_response(message = message, memory = memory)
        return response

    async def audio_chat(self, message: str | None = None, language: str = "en", speakerInstance: Speaker | None = None, memory: list[dict[str, str]] = []) -> str:
        if (not self._enableAudio):
            print("Audio is disabled")
            return ""
        else:
            response = await self.get_text_response(message = message, memory = memory)
            self.tts.invoke_speak(text = response, language = language, speakerInstance = speakerInstance)
            return response

    async def audio_chat_stream(self, message: str | None = None, language: str = "en", speakerInstance: Speaker | None = None, memory: list[dict[str, str]] = []):
        if (not self._enableAudio):
            print("Audio is disabled")
            return ""
        else:
            compiledMessages = self.compile_message(message = message, memory = memory)

            response = ""
            responseSentence = ""
            
            async for chunk in await self.asyncClient.chat(model = self.model, messages = compiledMessages, stream = True, think = False):
                responseChunk = chunk["message"]["content"]
                print(responseChunk)
                responseSentence += responseChunk
                if (re.search(r'[.。!！？?\n]+', responseChunk)):
                    print(responseSentence)
                    self.tts.invoke_speak(text = responseSentence, language = language, speakerInstance = speakerInstance)
                    response += responseSentence
                    responseSentence = ""

                if chunk.get("done", False):
                    break

            print("audio chat finished")
            self.response = response
            return response

    # async def chat_get_audio(self, message: str | None = None, language: str = "en", memory: list[dict[str, str]] = []):

    def stop_audio(self):
        self.tts.stop_audio()

    @classmethod
    async def create(cls, speakerInstance: Speaker | None = None, model: str = "llama3.2", systemPrompt: str | None = None, enableAudio: bool = True, manual: bool = False, externalSpeaker: bool = False, ttsMode: str = "edge"):
        tts = await TTS.create(speakerInstance = speakerInstance, manual = manual, externalSpeaker = externalSpeaker, mode = ttsMode) if enableAudio else None
        instance = cls(model = model, systemPrompt = systemPrompt, enableAudio = enableAudio, tts = tts, manual = manual)
        return instance

class TableResponder:
    def __init__(self, llmInstance: LLM, textOnly: bool = False, manual: bool = False, whisperModelSize: str | int = "base", whisperDevice: str = "cpu", whisperComputeType: str = "int8", whisperLanguage: str | None = None, speakerDeviceIndex: int | None = None, speakerSampleRate: int | None = None, micSampleRate: int | None = None, micDeviceIndex: int | None = None, micChunkDuration: int | float = 0.5, micFlatten: bool = True, micDenoise: bool = True, micStem: bool = False, transcriberBeamSize: int = 1, transcriberFilter: bool = True, transcriberUseContextual: str | int = 1, transcriberSplitParts: bool = False, transcriberDiarization: bool = False, RTCIP: str = "127.0.0.1", RTCPort: int = 55555):
        self.SILENCE_THRESHOLD = SILENCE_THRESHOLD
        self._RTCInstance = RTCInstance(debug = True, ip = RTCIP, port = RTCPort)
        self._whisperObject = WhisperObject(manual = manual, device = whisperDevice, modelSize = whisperModelSize, computeType = whisperComputeType, language = whisperLanguage) if not textOnly else None
        # skip debug playback and its speaker components
        self._transcriber = Transcriber(useRTC = True, rtcInstance = self._RTCInstance, whisperObject = self._whisperObject, manual = manual, beamSize = transcriberBeamSize, filter = transcriberFilter, useContextual = transcriberUseContextual, splitParts = transcriberSplitParts, diarization = transcriberDiarization, micStem = micStem, micSampleRate = micSampleRate, micDenoise = micDenoise, micFlatten = micFlatten, micChunkDuration = micChunkDuration, micDeviceIndex = micDeviceIndex) if not textOnly else None
        self._LLMInstance = llmInstance
        self._speaker = Speaker(manual = manual, useRTC = self._transcriber.useRTC, sampleRate = speakerSampleRate, deviceIndex = speakerDeviceIndex)
        self.silentTime = 0.0
        self.startTime = time.perf_counter()
        self.spoken = False
        self.audioPeakAmplitude = 0.0
        self.llmTriggerSilenceDuration = LLM_TRIGGER_SILENCE_DURATION
        self.previewTranscribeText = ""
        self.previewTranscribeLanguage = ""
        self.memoryEntryLimit = 5
        self.running = False
        self.closed = False
        self.port = RTCPort
        self._memory = []

    async def init_RTC(self):
        await self._transcriber.init_RTC()
        await self._speaker.open_RTC(rtcInstance = self._RTCInstance)

    # CALL ONLY FOR AUDIO LOOP, no diarization implementation for now
    async def loop_frame_audio(self):
        while (self.running):
            if (self._transcriber.closed):
                break

            self.audioPeakAmplitude = self._transcriber.mic.peakAmplitude

            self.process_transcription_preview()
            if (self.spoken):
                self.silentTime += time.perf_counter() - self.startTime
            self.startTime = time.perf_counter()

            if (self.audioPeakAmplitude > self.SILENCE_THRESHOLD):
                self.silentTime = 0.0
                self.spoken = True

            if ((self.silentTime > self.llmTriggerSilenceDuration) and self.spoken):
                self._transcriber.pauseTranscribe = True
                message = self._transcriber.transcribeTextNoncontextual
                if (message != ""):
                    response = await self._LLMInstance.audio_chat_stream(message = message, language = self._transcriber.languageNoncontextual, speakerInstance = self._speaker, memory = self._memory)
                    self._add_memory(message = message, response = response)
                print("finished responding")
                self._transcriber.mic.ready = False
                self._transcriber.flush_buffer()
                self._transcriber.mic.ready = True
                self.silentTime = 0.0
                self.spoken = False
                print("unlocking transcriber")
                self._transcriber.pauseTranscribe = False
                print("unlocked transcriber")

            await asyncio.sleep(0.05)

        self.closed = True

    def start(self):
        self.running = True
        asyncio.create_task(self.loop_frame_audio())

    def close(self):
        self.running = False

    def print_state(self):
        print(f"[{self._transcriber.mic.peakAmplitude:.5f}] [{self.silentTime:.5f}s {self.spoken}] [{self._transcriber.languageNoncontextual}] {self._transcriber.transcribeTextNoncontextual:.40} | {(self._LLMInstance.response if self._LLMInstance.response != None else ""):.40}\033[K")

    # CALL ONLY FOR TEXT LOOP ["text" channel]
    # async def loop_frame_text(self):

    def _add_memory(self, message: str = "", response: str = ""):
        timeNow = datetime.now()
        timestamp = timeNow.strftime("%Y-%m-%d %H:%M:%S")
        memory = {"timestamp": timestamp, "user": message, "response": " ".join(response) if type(response) != str else response}
        self._memory.append(memory)
        if (len(self._memory) > 5):
            self._memory.pop(0)

    # USE NONCONTEXTUAL BY DEFAULT, resort to raw string for now
    def process_transcription_preview(self):
        self.previewTranscribeLanguage = self._transcriber.languageNoncontextual
        self.previewTranscribeText = self._transcriber.transcribeTextNoncontextual

async def instance_server_handler(websocket: ServerConnection):
    global lastIP
    global lastPort
    global served
    global occupiedPorts
    
    while True:
        response = await websocket.recv()
        if (response[0:6] == "REQINS"):
            await websocket.send(f"ANSINS{lastIP}/{lastPort}", text = True)
            await websocket.close()
            print("handler closed")
            served = True

async def instance_server_task_loop(llmInstance: LLM, serverAddress: str, serverPort: int):
    global tables
    global lastIP
    global lastPort
    global served
    global occupiedPorts
    served = False

    print("await serve")
    server = await serve(instance_server_handler, serverAddress, serverPort)

    while True:
        while (not served):        
            await asyncio.sleep(0.1)
        served = False
        print("served, initializing responder")
        lastPort = kitanet_helper.find_port(55555, 56000, occupiedPorts)
        occupiedPorts.append(lastPort)
        table = TableResponder(manual = False, llmInstance = llmInstance, whisperModelSize = "small", whisperDevice = "cuda", whisperComputeType = "float16", micChunkDuration = 1.0, micFlatten = True, micDenoise = False, RTCIP = lastIP, RTCPort = lastPort, transcriberBeamSize = 2, transcriberDiarization = False, transcriberFilter = True, transcriberSplitParts = False, transcriberUseContextual = 0)
        print(f"assigned port {lastPort}")
        await table.init_RTC()
        print("finished init rtc")
        table._transcriber.mic.ready = True
        tables.append(table)
        print("appended")

async def main():
    global tables
    global lastIP
    global lastPort
    global occupiedPorts
    occupiedPorts = []
    tables = []
    lastIP = "127.0.0.1"
    lastPort = 55555

    try:
        os.system("")

        # while True:
        #     null, tablesCount = kitanet_helper.succeeds(int, input("Table instances: "))
        #     if (0 < tablesCount):
        #         break

        Transcriber.transcriptionLock = asyncio.Lock()
        llm = await LLM.create(model = "qwen2.5:7b", manual = False, externalSpeaker = True, ttsMode = "kokoro") #qwen2.5:3b-instruct-q8_0
        await llm.get_text_response(message = "")

        ip = get_ip()
        ipList: list[str] = []
        print("IP addresses:")
        for key, value in ip.items():
            print(f"{key:35} | {value}")
            ipList.append(value.split("/")[0])
        while True:
            serverAddress = input("Input IP address for instance server: ")
            if (serverAddress == ""):
                serverAddress = "127.0.0.1"
                print("Using default address localhost 127.0.0.1")
                break
            elif (serverAddress) in ipList:
                break
            else:
                print("Invalid IP address")
        while True:
            serverPort = input("Input port for server (enter to use default value 50000): ")
            if (serverPort == ""):
                serverPort = 50000
                print("Using default value: 50000")
                break
            elif (returnTuple := kitanet_helper.succeeds(int, serverPort))[0]:
                if (0 <= returnTuple[1] <= 65535):
                    serverPort = returnTuple[1]
                    break
                else:
                    print("Value is outside of port range (0~65535)")

        lastIP = serverAddress
        asyncio.create_task(instance_server_task_loop(llm, serverAddress, serverPort))

        ### handle this in separate loop
        # tables = [TableResponder(llmInstance = llm, manual = True) for _ in range(tablesCount)]
        # for table in tables:
        #     await table.init_RTC()
        #     table._transcriber.mic.ready = True

        # for table in tables:
        #     asyncio.create_task(table.loop_frame_audio())
        ###

        # add available ports assignment mechanism
        while True:
            for index, table in enumerate(tables):
                if (table.closed):
                    print(f"removed table {index}")
                    occupiedPorts.remove(table.port)
                    tables.pop(index)
                if (not table.running):
                    table.start()
                table.print_state()
            if (len(tables) > 0):
                print(f"\033[{len(tables)}A\r", end = "")
            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        llm.tts.close()
        for table in tables:
            table._transcriber.close()

# check whether all manual configs have an init parameter
# add incoming connection request handler loop, communicate with datestamp / id -> append a new TableResponder to list

# async def main_legacy():
#     transcribers = []
#     try:
#         os.system("")

#         instancesCount = await asyncio.to_thread(input, "Set amount of instances: ")
#         instancesCount = int(instancesCount)
        
#         Transcriber.transcriptionLock = asyncio.Lock()
#         whisperObject = WhisperObject(manual = True)
#         if (whisperObject.modelSize != None):
#             print("Initiated whisper\n")

#         # using rtc
#         transcribers = [Transcriber(whisperObject = whisperObject, manual = True) for _ in range(instancesCount)]
#         for transcriber in transcribers:
#             # configs, rtc assignments done here
#             if (transcriber.useRTC): await transcriber.init_RTC()

#         while True:
#             useLLM = input("Enable LLM interaction (true/false): ")
#             if (useLLM == ""):
#                 useLLM = True
#                 print("Using default settings: True")
#                 break
#             if (kitanet_helper.succeeds(int, useLLM)[0]):
#                 useLLM = int(useLLM) != 0
#                 break
#             else:
#                 if (useLLM.lower() not in ["true", "false"]):
#                     continue
#                 useLLM = useLLM.lower() == "true"
#                 break

#         if (useLLM):
#             llm = await LLM.create(model = "qwen2.5:3b-instruct-q8_0", manual = True)

#         iterationCount = 0
#         silentTime = 0.0
#         startTime = time.perf_counter()
#         spoken = False

#         for transcriber in transcribers:
#             transcriber.mic.ready = True
        
#         while True:
#             speakerCount = 0
#             newlineCount = 0
#             peakAmplitude = 0.0
#             lastPeakTranscriber = -1
#             print(f"[{iterationCount}] Last transcribe time {sum(transcriber.timeToTranscribe for transcriber in transcribers):.5f}s\033[K")

#             for i, transcriber in enumerate(transcribers):
#                 print(f"Peak input signal: {transcriber.mic.peakAmplitude}\033[K")
#                 if (transcriber.mic.peakAmplitude > peakAmplitude):
#                     peakAmplitude = transcriber.mic.peakAmplitude
#                     lastPeakTranscriber = i

#                 if (transcriber.contextualMode[0]):
#                     language = transcriber.language
#                     text = transcriber.transcribeText
#                     if (text.count("<>") > 0):
#                         text = text.split("<>")
#                         print(f"\rInstance {i}: \t[{language}] {text[0]}\033[K")
#                         for textPart in text:
#                             print(f"{textPart}\033[K")
#                             newlineCount += 1
#                     else:
#                         print(f"\rInstance {i}: \t[{language}] {text[-50:]:<50}\033[K")

#                 if (transcriber.contextualMode[1]):
#                     language = transcriber.languageNoncontextual
#                     text = transcriber.transcribeTextNoncontextual
#                     if (text.count("<>") > 0):
#                         text = text.split("<>")
#                         print(f"\rInstance {i}: \t[{language}] {text[0]}\033[K")
#                         for textPart in text:
#                             print(f"{textPart}\033[K")
#                             newlineCount += 1
#                     else:
#                         print(f"\rInstance {i}: \t[{language}] {text[-50:]:<50}\033[K")
                        
#                 if (transcriber.enableDiarization):
#                     try:
#                         for turn, speaker in transcriber.diarizationOutput.speaker_diarization:
#                             print(f"Start = {turn.start:.1f}s, Stop = {turn.end:.1f}s, {speaker}\033[K")
#                             speakerCount += 1
#                     except Exception as exception:
#                         print(f"Diarization failed: {exception}")
#                         speakerCount += 1
#                         continue

#             if (spoken):
#                 silentTime += time.perf_counter() - startTime
#             startTime = time.perf_counter()

#             print(f"Transcriber {lastPeakTranscriber} monitored for LLM input, time since last silence: {silentTime}\033[K")
#             print("=============================================================================================================================\x1b[J")

#             print(f"\033[{((transcriber.contextualMode.count(True) + 1) * len(transcribers)) + 3 + speakerCount + newlineCount}A\r", end = "")
#             iterationCount += 1

#             if (peakAmplitude > SILENCE_THRESHOLD):
#                 silentTime = 0
#                 spoken = True

#             if ((silentTime > LLM_TRIGGER_SILENCE_DURATION) and spoken and useLLM):
#                 # llm.stopAudio()
#                 message = transcribers[lastPeakTranscriber].transcribeText
#                 if (message != ""):
#                     await llm.audio_chat(message = message, language = transcribers[lastPeakTranscriber].language)
#                 for transcriber in transcribers:
#                     transcriber.flush_buffer()
#                 silentTime = 0
#                 spoken = False
                
#             await asyncio.sleep(0.1)

#     except KeyboardInterrupt:
#         print("\n\n\nExiting")
#     finally:
#         for transcriber in transcribers:
#             transcriber.close()
#         print("\033[K\n\033[K\n\033[K\n")



if __name__ == "__main__":
    asyncio.run(main())