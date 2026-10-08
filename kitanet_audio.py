import numpy as np
try:
    import pyaudiowpatch as pyaudio
except:
    import pyaudio
import threading
import queue
import time
import kitanet_helper
import asyncio
import torch
import json

from faster_whisper import WhisperModel
from scipy.signal import resample_poly
from pyrnnoise_customfork import RNNoise
from pydub import AudioSegment
from kitanet_comm import RTCInstance

class Mic:
    # INIT RTC BEFORE START
    stemIndexDict = ["drums", "bass", "other", "vocals"]

    def __init__(self, sampleRate: int | None = None, deviceIndex: int | None = None, chunkDuration: int | float = 0.5, flatten: bool = True, denoise: bool = True, manual: bool = False, useRTC: bool = False):
        self._pa = pyaudio.PyAudio() if not useRTC else None
        self._RTCInstance = None
        self.queue = queue.Queue()
        self._running = False
        self.peakAmplitude = -1
        self._devices = {
            index: self._pa.get_device_info_by_index(index) for index in range(self._pa.get_device_count())
            if self._pa.get_device_info_by_index(index)["maxInputChannels"] > 0
        } if not useRTC else None
        if (manual and not useRTC):
            self.start_manual_on_device()
        elif (not useRTC):
            self.start_on_device(sampleRate = sampleRate, deviceIndex = deviceIndex, chunkDuration = chunkDuration, flatten = flatten, denoise = denoise)
        self.ready = False

    def start_on_device(self, sampleRate: int | None = None, deviceIndex: int | None = None, chunkDuration: int | float = 0.5, flatten: bool = True, denoise: bool = True, stem: bool = False):
        self.deviceIndex = None if self._pa == None else int(self._pa.get_default_input_device_info()["index"]) if deviceIndex == None else deviceIndex
        self.sampleRate = sampleRate if (sampleRate != None or self._pa == None) else int(self._pa.get_device_info_by_index(self.deviceIndex)["defaultSampleRate"])
        self.channels = int(self._pa.get_device_info_by_index(self.deviceIndex)["maxInputChannels"])
        self.chunkDuration = chunkDuration
        self.chunkLength = int(self.chunkDuration * self.sampleRate)
        self.flatten = flatten
        self._running = True
        self._stream = None if self._pa == None else self._pa.open(
            format = pyaudio.paFloat32, rate = self.sampleRate, channels = self.channels, input_device_index = self.deviceIndex, input = True, frames_per_buffer = self.chunkLength
        )

        if (denoise and not stem):
            self._denoise = True
            self._denoiser = RNNoise(self.sampleRate)
        else:
            self._denoise = False

        if (stem):
            import demucs.api

            self._stem = True
            self._separator = demucs.api.Separator(model = "htdemucs", shifts = 1, device = "cuda" if torch.cuda.is_available() else "cpu")
            self.stemIndex = input("Set stem index of [drums, bass, other, vocals] in format of 0/1 (e.g. 1110): ")
        else:
            self._stem = False

        threading.Thread(target = self._loop, daemon = True).start()

    async def start_RTC(self, sampleRate: int = 44100, channels: int = 1, manual: bool = True):
        self._RTCInstance = RTCInstance()
        await self._RTCInstance.init_auto_config(offer = True, channels = ["audio"], stackData = True)

        self.sampleRate = sampleRate
        self.channels = channels

        if (manual):
            self.sampleRate = input(f"Sample rate (enter to use default value 44100): ")
            self.sampleRate = 44100 if self.sampleRate == "" else int(self.sampleRate)
            self.channels = input(f"Set input channels (enter to use default 1): ")
            self.channels = 1 if self.channels == "" else int(self.channels)

        self.flatten = self.channels == 1

        self._running = True
        threading.Thread(target = self._loop, daemon = True).start()

    def start_manual_on_device(self):
        for index, device in self._devices.items():
            print(f"[{index}] {device['name']}")

        while True:
            try:
                deviceIndex = int(input("\nSelect input device index: "))
                if deviceIndex not in self._devices:
                    continue
                sampleRate = input(f"Sample rate (enter to use device's default value {self._pa.get_device_info_by_index(deviceIndex)["defaultSampleRate"]}): ")
                sampleRate = None if sampleRate == "" else int(sampleRate)
                chunkDuration = input("Chunk duration (enter to use default value 1.0[s]): ")
                chunkDuration = 1.0 if chunkDuration == "" else float(chunkDuration)
                while True:
                    flatten = input("Flatten channels (true/false): ")
                    if (flatten == ""):
                        flatten = True
                        print("Using default settings: True")
                        break
                    if (kitanet_helper.succeeds(int, flatten)[0]):
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
                    if (kitanet_helper.succeeds(int, denoise)[0]):
                        denoise = int(denoise) != 0
                        break
                    else:
                        if (denoise.lower() not in ["true", "false"]):
                            continue
                        denoise = denoise.lower() == "true"
                        break
                while True:
                    stem = input("Stem audio (true/false): ")
                    if (stem == ""):
                        stem = False
                        print("Using default settings: False")
                        break
                    if (kitanet_helper.succeeds(int, stem)[0]):
                        stem = int(stem) != 0
                        break
                    else:
                        if (stem.lower() not in ["true", "false"]):
                            continue
                        stem = stem.lower() == "true"
                        break
                break
            except ValueError:
                pass

        self.start_on_device(sampleRate = sampleRate, deviceIndex = deviceIndex, chunkDuration = chunkDuration, flatten = flatten, denoise = denoise, stem = stem)

    def _loop(self):
        print(f"RTC device {self._RTCInstance.instanceID}: started loop" if self._pa == None else f"Mic {self.deviceIndex}: started loop with {self.sampleRate} hz sampling rate and {self.chunkLength} samples length chunk")

        if (self._pa != None):
            bufferPaddingLength = min(0.6, self.chunkDuration / 2)
            bufferPaddingLength = int(bufferPaddingLength * self.sampleRate)
            bufferPadding = np.zeros(bufferPaddingLength * self.channels).astype(np.float32)

        while (self._running):
            if (not self.ready):
                time.sleep(0.1)
                continue

            if (self._pa != None):
                rawBuffer = self._stream.read(self.chunkLength, exception_on_overflow = False)
                buffer = np.frombuffer(rawBuffer, dtype = np.float32)
            elif (self._RTCInstance != None):
                buffer = np.frombuffer(self._RTCInstance.queues["audio"].get(), dtype = np.float32)

            if (self._pa != None):
                if (self._denoise and not self._stem):
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
                    buffer = audio.mean(axis = 0) if self.flatten else audio.T.ravel()
                elif self.flatten:
                    buffer = buffer.reshape(-1, self.channels).mean(axis = 1)

                while True:
                    if (self._stem):
                        buffer = np.concatenate([bufferPadding, buffer])
                        bufferPadding = buffer[-bufferPaddingLength * self.channels:]
                        if (self.channels == 2 and not self.flatten):
                            buffer = buffer.reshape(-1, 2).T
                        elif (self.channels == 1 or self.flatten):
                            buffer = np.repeat(buffer[np.newaxis, :], 2, axis = 0)
                        else:
                            break

                        bufferTensor = torch.from_numpy(buffer.copy())
                        origin, stems = self._separator.separate_tensor(bufferTensor, self.sampleRate)
                        bufferEmpty = True
                        for index, (stemName, stemTensor) in enumerate(stems.items()):
                            # print(f"{index}, {stemName}")
                            if (self.stemIndex[self.stemIndexDict.index(stemName)] != "0"):
                                buffer = stemTensor.squeeze(0).cpu().numpy().T if bufferEmpty else buffer + stemTensor.squeeze(0).cpu().numpy().T
                                bufferEmpty = False
                        if (self.channels == 1 or self.flatten):
                            buffer = buffer[:, 0]
                        buffer = resample_poly(buffer, self.sampleRate, 44100).ravel()
                        buffer = buffer[bufferPaddingLength : -bufferPaddingLength]
                        break
                    else:
                        break

            self.queue.put(buffer.astype(np.float32))

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
            if (sourceSampleRate != self.sampleRate):
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