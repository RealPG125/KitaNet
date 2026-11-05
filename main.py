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
import boto3
import difflib
import json

from faster_whisper import WhisperModel
from scipy.signal import resample_poly
from io import BytesIO
from pydub import AudioSegment
from kitanet_audio import Mic, Speaker
from kitanet_comm import RTCInstance, get_ip
from kitanet_db import DB
from pykokoro import GenerationConfig, KokoroSynthesizer, SynthesisConfig
from datetime import datetime
from websockets.asyncio.server import serve, ServerConnection
from dotenv import load_dotenv

# model     : 軽 → 重: "tiny" (75MB), "base" (142MB), "small" (466MB), "medium" (1.5GB), "large-v3" (3.0GB)
# device    : "cpu", Nvidia GPU: "cuda"

load_dotenv(".env")

SSH_HOST = os.getenv("SSH_HOST")
SSH_USER = os.getenv("SSH_USER")
SSH_PKEY_PATH = os.getenv("SSH_PKEY_PATH")
RDS_HOST = os.getenv("RDS_HOST")
rds_port = os.getenv("RDS_PORT")
if (returnTuple := kitanet_helper.succeeds(int, rds_port))[0]:
    rds_port = returnTuple[1]
else:
    rds_port = None
RDS_PORT = rds_port
RDS_CA_PATH = os.getenv("RDS_CA_PATH")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
PYANNOTE_TOKEN = os.getenv("PYANNOTE_TOKEN")

MAX_BUFFER_DURATION = 20
SILENCE_THRESHOLD = 0.025
LLM_TRIGGER_SILENCE_DURATION = 1.0

with open("Key/aws_access_key_id.txt", "r", encoding = "utf=8") as file:
    AWS_ACCESS_KEY_ID = file.read()
with open("Key/aws_secret_access_key.txt", "r", encoding = "utf=8") as file:
    AWS_SECRET_ACCESS_KEY = file.read()
with open("Key/aws_session_token.txt", "r", encoding = "utf=8") as file:
    AWS_SESSION_TOKEN = file.read()

INTENTS = ["Does the user wants to know about this restaurant's menu?",
           "Does the user have an interest into interacting with the restaurant workers?",
           "Does the user need direct human worker assistance?",
           "Is the user looking for information regarding localities, events, or point of interests?",
           "Does the latest user query has any non-sensitive personal information (quirks, hobbies etc.) specific to the user worth storing for better and more enjoyable future interactions, or for the ease of communication with the workers? Only score if the information is identifiable (has clear names as subject for example).",
           "Does the latest user query has any non-sensitive conversational information that's substantial enough to be stored separately in addition to the limited conversation history, or for the ease of communication with the workers?",
           "Does the user actively show a preference of a certain menu?"]
INTENTS_THRESHOLD = [6, 5, 5, 5, 8, 5, 7]

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
            raise ValueError("whisperObject cannot be empty")
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
        self._pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token = PYANNOTE_TOKEN)
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
        self._kokoroTTSAggregate: dict[str, KPipeline] | None = {"ja": KPipeline(lang_code = "j", repo_id = "hexgrad/Kokoro-82M"), "en": KPipeline(lang_code = "a", repo_id = "hexgrad/Kokoro-82M")} if mode == "kokoro" else None
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
            
            self.voiceModel = voiceModel

    def invoke_speak(self, text, language: str = "en", speakerInstance: Speaker | None = None):
        try:
            audioData = self.generate_voice(text = text, language = language)
        except:
            return
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
            voiceModel = (TTS.edgeTTSLanguageVoiceDict[language] if language in TTS.edgeTTSLanguageVoiceDict else TTS.edgeTTSLanguageVoiceDict["en"]) if self.voiceModel == "auto" else self.voiceModel
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
    def __init__(self, model: str = "llama3.2", systemPrompt: str | None = None, enableAudio: bool = True, tts: TTS | None = None, manual: bool = False, local: bool = True, intents: list[str] = []):
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

        self.local = local
        self.model = model
        self.tts = tts
        self.intents = intents
        self._enableAudio = enableAudio
        self.systemPrompt = "Be a casual chatting company as a friendly chatbot in a restaurant. Users varies between 1 to 8 people, so keep the flow understandable for more people to follow. Reply in text only and do not use any formatting (bold, italic etc), unnecessary symbols, or emojis as the result will be used to invoke speech using a text-to-speech system. Most importantly, reply shortly, 4 sentences maximum if possible. When asked about something outside your general knowledge (such as events, restaurant menus, news etc.), absolutely do not answer and apologize (suggest asking the human workers instead) unless a system message is provided to supply context or information of said topic. But remember to not be too stiff and cheer up the conversation by showing curiosity, if the situation allows and it's something non-critical. Make sure to take account of possible typo / incoherent input due to speech-to-text inaccuracies, and apply fixes if deemed necessary to fit the context. Ask the user if you're not sure of the original sentence." if systemPrompt == None else systemPrompt
        self.intentPrompt = "Strictly answer in integer numbers. Evaluate the latest user conversation message and give a score ranging from 0 to 10 for each following user intents. Give one value for each intent entry, and separate each using a single space. Do not use period or any other symbols."
        self.response = None
        self.bedrockClient = boto3.client("bedrock-runtime", region_name = "ap-northeast-1", aws_access_key_id = AWS_ACCESS_KEY_ID, aws_secret_access_key = AWS_SECRET_ACCESS_KEY, aws_session_token = AWS_SESSION_TOKEN) 

    def compile_message(self, info: list[str] = [], message: str | None = None, memory: list[dict[str, str]] = [], mode: str = "chat", language: str | None = None, instruction: str | None = None):
        supportsSystemPromptFlag = self.model not in ["openai.gpt-oss-120b-1:0", "openai.gpt-oss-20b-1:0", "arn:aws:bedrock:ap-northeast-1::foundation-model/amazon.nova-lite-v1:0"] 

        if (mode == "custom"):
            compiledMessages = [{"role": "system" if supportsSystemPromptFlag else "user", "content": ((self.systemPrompt if instruction == None else instruction) + f" Use the language {language} and translate every other language into it so that it strictly contain only letters from the target language.") if self.local else [{"text": ("This is a system instruction. Instructions for this conversation: " if supportsSystemPromptFlag else "") + (self.systemPrompt if instruction == None else instruction) + f" Use the language {language} and translate every other language into it so that it strictly contain only letters from the target language."}]}]
            compiledMessages.append({"role": "user", "content": message if self.local else [{"text": message}]})
            return compiledMessages

        if (mode == "chat"):
            compiledMessages = [{"role": "system" if supportsSystemPromptFlag else "user", "content": ((self.systemPrompt if instruction == None else instruction) + f" Use the language {language} and translate every other language into it so that it strictly contain only letters from the target language.") if self.local else [{"text": ("This is a system instruction. Instructions for this conversation: " if supportsSystemPromptFlag else "") + (self.systemPrompt if instruction == None else instruction) + f" Use the language {language} and translate every other language into it so that it strictly contain only letters from the target language."}]}]
            for item in info:
                compiledMessages.append({"role": "system" if supportsSystemPromptFlag else "user", "content": f"Additional info: {item}" if self.local else [{"text": f"Additional info: {item}"}]})
        elif (mode == "intent"):
            compiledMessages = [{"role": "system" if supportsSystemPromptFlag else "user", "content": (self.systemPrompt if instruction == None else instruction) if self.local else [{"text": ("The original instruction for this conversation is: " if supportsSystemPromptFlag else "") + f"'{(self.systemPrompt if instruction == None else instruction)}'"}]}]

        if (mode == "intent"):
            compiledMessages.append({"role": "system" if supportsSystemPromptFlag else "user", "content": (self.systemPrompt if instruction == None else instruction) if self.local else [{"text": ("This is a system instruction. Past instructions are for references only. Follow the instructions: " if supportsSystemPromptFlag else "") + self.intentPrompt}]})        
            for index, intent in enumerate(self.intents):
                compiledMessages.append({"role": "system" if supportsSystemPromptFlag else "user", "content": (f"Intent {index}" + intent) if self.local else [{"text": f"Intent: {index}" + intent}]})            

        for item in memory:
            compiledMessages.append({"role": "user", "content": item["user"] if self.local else [{"text": ("User sends the following message: " if supportsSystemPromptFlag else "") + item["user"]}]})
            compiledMessages.append({"role": "assistant", "content": item["response"] if self.local else [{"text": item["response"]}]})
        compiledMessages.append({"role": "user", "content": message if self.local else [{"text": message}]})

        return compiledMessages

    async def get_response(self, info: list[str] = [], message: str | None = None, memory: list[dict[str, str]] = [], mode: str = "chat", language: str | None = None, instruction: str | None = None):
        compiledMessages = self.compile_message(info = info, message = message, memory = memory, mode = mode, language = language, instruction = instruction)

        # print(compiledMessages)

        if (self.local):
            response = self.ollama.chat(model = self.model, messages = compiledMessages, think = False)["message"]["content"] if message != None else "Empty input message"
        else:
            response = self.bedrockClient.converse(modelId = self.model, messages = compiledMessages)
            try:
                response = response["output"]["message"]["content"][1]["text"]
            except:
                response = response["output"]["message"]["content"][0]["text"]

        if (mode == "chat"):
            self.response = response
        return response

    async def get_text_response(self, info: list[str] = [], message: str | None = None, memory: list[dict[str, str]] = [], mode: str = "chat", language: str | None = None, instruction: str | None = None) -> str:
        response = await self.get_response(info = info, message = message, memory = memory, mode = mode, language = language, instruction = instruction)
        return response

    async def audio_chat(self, info: list[str] = [], message: str | None = None, language: str = "en", speakerInstance: Speaker | None = None, memory: list[dict[str, str]] = []) -> str:
        if (not self._enableAudio):
            print("Audio is disabled")
            return ""
        else:
            startLLMTime = time.perf_counter()
            response = await self.get_text_response(info = info, message = message, memory = memory, language = language)
            print(f"llm response time: {(time.perf_counter() - startLLMTime):.1f}")
            response = re.split(r'[.。!！？?\n]+', response)
            for sentence in response:
                startSpeakTime = time.perf_counter()
                self.tts.invoke_speak(text = sentence, language = language, speakerInstance = speakerInstance)
                print(f"speak invoke time: {(time.perf_counter() - startSpeakTime):.1f}")
            return response

    # add info implementation
    async def audio_chat_stream(self, info: list[str] = [], message: str | None = None, language: str = "en", speakerInstance: Speaker | None = None, memory: list[dict[str, str]] = []):
        if (not self._enableAudio):
            print("Audio is disabled")
            return ""
        else:
            compiledMessages = self.compile_message(info = info, message = message, memory = memory, language = language)

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

            print("audio chat stream finished")
            self.response = response
            return response

    # async def chat_get_audio(self, message: str | None = None, language: str = "en", memory: list[dict[str, str]] = []):

    def stop_audio(self):
        self.tts.stop_audio()

    @classmethod
    async def create(cls, speakerInstance: Speaker | None = None, model: str = "llama3.2", systemPrompt: str | None = None, enableAudio: bool = True, manual: bool = False, externalSpeaker: bool = False, ttsMode: str = "edge", local: bool = True, intents: list[str] = []):
        tts = await TTS.create(speakerInstance = speakerInstance, manual = manual, externalSpeaker = externalSpeaker, mode = ttsMode, voiceModel = "auto") if enableAudio else None
        instance = cls(model = model, systemPrompt = systemPrompt, enableAudio = enableAudio, tts = tts, manual = manual, local = local, intents = intents)
        return instance

class TableResponder:
    def __init__(self, llmInstance: LLM, textOnly: bool = False, manual: bool = False, whisperModelSize: str | int = "base", whisperDevice: str = "cpu", whisperComputeType: str = "int8", whisperLanguage: str | None = None, speakerDeviceIndex: int | None = None, speakerSampleRate: int | None = None, micSampleRate: int | None = None, micDeviceIndex: int | None = None, micChunkDuration: int | float = 0.5, micFlatten: bool = True, micDenoise: bool = True, micStem: bool = False, transcriberBeamSize: int = 1, transcriberFilter: bool = True, transcriberUseContextual: str | int = 1, transcriberSplitParts: bool = False, transcriberDiarization: bool = False, RTCIP: str = "127.0.0.1", RTCPort: int = 55555):
        self.SILENCE_THRESHOLD = SILENCE_THRESHOLD
        self._RTCInstance = RTCInstance(debug = True, ip = RTCIP, port = RTCPort)
        self._whisperObject = WhisperObject(manual = manual, device = whisperDevice, modelSize = whisperModelSize, computeType = whisperComputeType, language = whisperLanguage) if not textOnly else None
        # skip debug playback and its speaker components
        self.transcriber = Transcriber(useRTC = True, rtcInstance = self._RTCInstance, whisperObject = self._whisperObject, manual = manual, beamSize = transcriberBeamSize, filter = transcriberFilter, useContextual = transcriberUseContextual, splitParts = transcriberSplitParts, diarization = transcriberDiarization, micStem = micStem, micSampleRate = micSampleRate, micDenoise = micDenoise, micFlatten = micFlatten, micChunkDuration = micChunkDuration, micDeviceIndex = micDeviceIndex) if not textOnly else None
        self._LLMInstance = llmInstance
        self._speaker = Speaker(manual = manual, useRTC = self.transcriber.useRTC, sampleRate = speakerSampleRate, deviceIndex = speakerDeviceIndex)
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
        self.tableSessionId = None
        self.tableSessionUpdated = False
        self.users = []
        self.userHistory = []
        self.conversationHistory = []

    def get_tableSessionId(self):
        for item in self._RTCInstance.storage["control"]:
            if (item[:6] == "CONFIG"):
                configItem = json.loads(item[7:])
                print(f"JSON {configItem}")
                try:
                    self.tableSessionId = configItem["TABLESESSIONID"]
                    print(f"set table session id as {self.tableSessionId}")
                except:
                    pass

    def get_users(self, db: DB):
        self.users = db.execute(f"select * from userdata where id = (select user_id from tablesessionmember where table_session_id = {table.tableSessionId});")

    def get_user_history(self, db: DB):
        self.userHistory = db.execute(f"select distinct on (name) name, memory_topic, memory_content from usermemory natural join userdata where user_id in (select user_id from tablesessionmember where table_session_id = {table.tableSessionId}) and expiration_datetime > now();")

    def get_history(self, db: DB):
        self.conversationHistory = db.execute(f"select memory_topic, memory_content from conversationmemory where table_session_id = {self.tableSessionId};")

    def set_user_history(self, db: DB, name: str | None = None, topic: str | None = None, content: str | None = None, ):
        if (content != None and user != None):
            db.execute(f"insert into usermemory values ((select id from userdata where name = {name}), {self.tableSessionId}, now(), null, now(), {topic if topic != None else "null"}, {content}, true);")

    def set_conversation_history(self, db: DB, topic: str | None = None, content: str | None = None):
        if (content != None):
            db.execute(f"insert into conversationmemory values ({self.tableSessionId}, now(), {topic if topic != None else null}, {content})")

    async def llm_match_item(self, target: str | None = None, pool: list[str] = []) -> tuple:
        poolString = ""
        for index, item in enumerate(pool):
            poolString += f"Index {index}: {item}, "
        poolString = poolString[:-2]
        result = await self._LLMInstance.get_text_response(message = f"Find {target} index in [{poolString}]", mode = "custom", language = "en", instruction = "Strictly answer in integer numbers only. Do not output any word or sentence. Determine one index in the pool that has the same item or most similar item to the target item. If none fits, reply with -1.")
        print(f"llm find item {target} in {pool}, found index {result}")
        return (result, pool[result])

    async def llm_filter_pool(self, pool: str | None = None, source: str | None = None) -> str:
        result = await self._LLMInstance.get_text_response(message = f"Find any item of {pool} in the following source text: {source}", mode = "custom", language = "en", instruction = "Strictly answer in the following example format for item 1, 2, and 5: '1, 2, 5'. Do not output any word or sentence. Determine which item inside pool is contained within the source text. You can choose multiple, and search fuzzily. If none is found, reply with '-1'.")
        result = result.replace("'", "").split(",")
        return result
    
    async def llm_format_user_memory(self, message: str | None = None) -> list[tuple[str, str]]:
        result = await self._LLMInstance.get_text_response(message = message, mode = "custom", language = "en", instruction = "Summarize non-sensitive personal information (hobbies etc.) that you can get judging from this message and determine the subject's name. Output the subject's name first and the summary with the following format: 'Name1>Topic=Content | Name2>Topic=Content | (...)'. Summarize multiple users if necessary.")
        result = result.split("|")
        userMemory = []
        for item in result:
            item = item.split(">")
            content = item[1].split("=")
            userMemory.append((item[0], content[0], content[1]))
        print(f"llm format user memory: {userMemory}")
        return userMemory

    async def llm_format_conversation_memory(self, message: str | None = None) -> list[tuple[str, str]]:
        result = await self._LLMInstance.get_text_response(message = message, mode = "custom", language = "en", instruction = "Summarize non-sensitive conversational information (activities engaged, small talks, topic of interest etc.) that you can get judging from this message. Output with the following format: 'Topic=Content'.")
        result = result.split("=")
        print(f"llm format conversation memory: {result}")
        return (result[0], result[1])

    async def llm_process_info(self, message: str | None = None):
        intentsResponse = await self._LLMInstance.get_text_response(message = message, memory = self._memory, mode = "intent")
        intentsResponse = intentsResponse.split(" ")
        info = []
        menuInfo = None
        for item in self.userHistory:
            info.append(f"[User info] Name: {item[0]}, Topic: {item[1]}, Content: {item[2]}")
        if (len(intentsResponse) == len(INTENTS)):
            # menu
            if (returnTuple := kitanet_helper.succeeds(int, intentsResponse[0]))[0] and returnTuple[1] > INTENTS_THRESHOLD[0]:
                menuInfo = db.execute("select * from menu where availability = true;")
                for item in menuInfo:
                    availability = (("Breakfast " if (int(item[7]) & 0b100) else "") + ("Lunch " if (int(item[7]) & 0b010) else "") + ("Dinner" if (int(item[7]) & 0b001) else ""))
                    info.append(f"[Menu info] Name: {item[1]}, Price in yen: {item[2]}, Stock = {item[4]}, Seasonal = {item[5]}, Description = {item[6]}, Available Time = {availability}")
            # worker
            if (returnTuple := kitanet_helper.succeeds(int, intentsResponse[1]))[0] and returnTuple[1] > INTENTS_THRESHOLD[1]:
                workerInfo = db.execute("select * from workerdata where status = 'active';")
                for item in workerInfo:
                    workerMemory = db.execute(f"select memory_topic, memory_content from workermemory where worker_id = {item[0]}")
                    workerMemoryString = ""
                    for memory in workerMemory:
                        workerMemoryString += f"[Topic: {memory[0]}, Content: {memory[1]}]"
                    info.append(f"[Worker info] Name: {item[1]}, Region: {item[2]}, Info: {workerMemoryString}")
            # localities
            if (returnTuple := kitanet_helper.succeeds(int, intentsResponse[3]))[0] and returnTuple[1] > INTENTS_THRESHOLD[3]:
                localInfo = db.execute("select * from othersdata;")
                for item in localInfo:
                    info.append(f"[Event info] Category: {item[1]}, Content: {item[3]}")
            # store user memory
            if (returnTuple := kitanet_helper.succeeds(int, intentsResponse[4]))[0] and returnTuple[1] > INTENTS_THRESHOLD[4]:
                userMemory = await self.llm_format_user_memory(message = message)
                usersName = [item[1] for item in self.users]
                for item in userMemory:
                    user = await self.llm_match_item(target = item[0], pool = usersName)
                    self.userHistory.append((item[0], item[1], item[2]))
                    db.execute(f"insert into usermemory values ((select id from userdata where name = {user[1]}), {self.tableSessionId}, now(), null, now(), {item[1]}, {item[2]}, true);")
            # store conversation memory
            if (returnTuple := kitanet_helper.succeeds(int, intentsResponse[5]))[0] and returnTuple[1] > INTENTS_THRESHOLD[5]:
                conversationMemory = await self.llm_format_conversation_memory(message = message)
                self.conversationHistory.append((conversationMemory[0], conversationMemory[1]))
                db.execute(f"insert into conversationmemory values ({self.tableSessionId}, now(), {conversationMemory[0]}, {conversationMemory[1]});")
            # store user preference
            if (returnTuple := kitanet_helper.succeeds(int, intentsResponse[6]))[0] and returnTuple[1] > INTENTS_THRESHOLD[6]:
                if (menuInfo == None):
                    menuInfo = db.execute("select * from menu where availability = true;")
                menuPool = []
                for item in menuInfo:
                    menuPool.append(item[1])

                # handle separate prompt for asking name / nickname, consider reconstructing preference saving function to include past conversations
                self.llm_filter_pool(pool = menuPool, source = message)
                # db.execute(f"insert into usermenupreference values ();")

        print(intentsResponse)
        return info

    async def init_RTC(self):
        await self.transcriber.init_RTC()
        await self._speaker.open_RTC(rtcInstance = self._RTCInstance)

    # CALL ONLY FOR AUDIO LOOP, no diarization implementation for now
    async def loop_frame_audio(self):
        global db

        while True:
            try:
                self.get_tableSessionId()
                break
            except:
                await asyncio.sleep(0.1)

        while (self.running):
            if (self.transcriber.closed):
                break

            if (self.tableSessionId != None):
                if (not self.tableSessionUpdated):
                    db.execute(f"update tablesession set conversation_status = true where id = UUID('{self.tableSessionId}');")
                    self.tableSessionUpdated = True

            self.audioPeakAmplitude = self.transcriber.mic.peakAmplitude

            self.process_transcription_preview()
            if (self.spoken):
                self.silentTime += time.perf_counter() - self.startTime
            self.startTime = time.perf_counter()

            if (self.audioPeakAmplitude > self.SILENCE_THRESHOLD):
                self.silentTime = 0.0
                self.spoken = True

            if ((self.silentTime > self.llmTriggerSilenceDuration) and self.spoken):
                self.transcriber.pauseTranscribe = True
                startChatTime = time.perf_counter()
                message = self.transcriber.transcribeTextNoncontextual
                if (message != ""):
                    # use audio_chat (aws / remote, local) or audio_chat_stream (local only)
                    info = await self.llm_process_info(message)
                    response = await self._LLMInstance.audio_chat(info = info, message = message, language = self.transcriber.languageNoncontextual, speakerInstance = self._speaker, memory = self._memory)
                    self._add_memory(message = message, response = response)
                print("finished responding")
                self.transcriber.mic.ready = False
                self.transcriber.flush_buffer()
                self.transcriber.mic.ready = True
                self.silentTime = 0.0
                self.spoken = False
                print("unlocking transcriber")
                self.transcriber.pauseTranscribe = False
                print("unlocked transcriber")
                print(f"total respond time: {(time.perf_counter() - startChatTime):.1f}s")

            await asyncio.sleep(0.05)

        self.closed = True

    def start(self):
        global db
        self.running = True
        asyncio.create_task(self.loop_frame_audio())

    def close(self):
        self.running = False
        db.execute(f"update tablesession set conversation_status = false where id = UUID('{self.tableSessionId}');")

    def print_state(self):
        print(f"[{self.transcriber.mic.peakAmplitude:.5f}] [{self.silentTime:.5f}s {self.spoken}] [{self.transcriber.languageNoncontextual}] {self.transcriber.transcribeTextNoncontextual:.40} | {(self._LLMInstance.response if self._LLMInstance.response != None else ""):.40}\033[K")

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
        self.previewTranscribeLanguage = self.transcriber.languageNoncontextual
        self.previewTranscribeText = self.transcriber.transcribeTextNoncontextual

def find_item(target: str | None = None, pool: list[str] | None = None) -> tuple:
    match = difflib.get_close_matches(target, pool, n = 1)
    index = pool.index(match)
    return (index, match)

async def instance_server_handler(websocket: ServerConnection):
    global lastIP
    global lastPort
    global served
    global occupiedPorts
    
    while True:
        response = await websocket.recv()
        if (response[0:6] == "REQINS"):
            lastPort = kitanet_helper.find_port(55555, 56000, occupiedPorts)
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
        occupiedPorts.append(lastPort)
        table = TableResponder(manual = False, llmInstance = llmInstance, whisperModelSize = "small", whisperDevice = "cuda", whisperComputeType = "float16", micChunkDuration = 1.0, micFlatten = True, micDenoise = False, RTCIP = lastIP, RTCPort = lastPort, transcriberBeamSize = 2, transcriberDiarization = False, transcriberFilter = True, transcriberSplitParts = False, transcriberUseContextual = 0)
        print(f"assigned port {lastPort}")
        await table.init_RTC()
        print("finished init rtc")
        table.transcriber.mic.ready = True
        tables.append(table)
        print("appended")

async def main():
    global tables
    global lastIP
    global lastPort
    global occupiedPorts
    global db
    occupiedPorts = []
    tables: list[TableResponder] = []
    lastIP = "127.0.0.1"
    lastPort = 55555

    try:
        os.system("")

        db = DB(dbName = DB_NAME, dbUser = DB_USER, dbPassword = DB_PASSWORD)

        Transcriber.transcriptionLock = asyncio.Lock()
        llm = await LLM.create(model = "openai.gpt-oss-120b-1:0", manual = False, externalSpeaker = True, ttsMode = "edge", local = False, intents = INTENTS) #qwen2.5:3b-instruct-q8_0

        ip = get_ip()
        ipList: list[str] = []
        print("IP addresses:")
        indexMax = 0
        for index, (key, value) in enumerate(ip.items()):
            print(f"[{index}] {key:35} | {value}")
            ipList.append(value.split("/")[0])
            indexMax = index
        while True:
            serverAddress = input("Input IP address for instance server: ")
            if (serverAddress == ""):
                serverAddress = "127.0.0.1"
                print("Using default address localhost 127.0.0.1")
                break
            elif (serverAddress) in ipList:
                break
            elif ((returnTuple := kitanet_helper.succeeds(int, serverAddress))[0] and returnTuple[1] <= indexMax):
                serverAddress = ipList[returnTuple[1]]
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

        while True:
            for index, table in enumerate(tables):
                if (table.closed):
                    table.close()
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
            table.close()

if __name__ == "__main__":
    asyncio.run(main())