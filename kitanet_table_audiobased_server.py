import kitanet_comm
import threading
import asyncio
import numpy as np
import json

from scipy.signal import resample_poly
from kitanet_comm import RTCInstance
from kitanet_audio import Mic, Speaker
from websockets.asyncio.client import connect



async def main():
    mic = Mic(manual = True)
    speaker = Speaker(manual = True)

    serverAddress = "127.0.0.1"
    serverPort = 55555
    serverConfigAddress = "127.0.0.1"
    serverConfigPort = 50000
    uri = f"ws://{serverConfigAddress}:{serverConfigPort}/"

    async with connect(uri) as websocket:
        await websocket.send("REQINS")

        while True:
            response = await websocket.recv()
            if (response[:6] == "ANSINS"):
                response = response[6:].split("/")
                serverAddress = response[0]
                serverPort = response[1]
                await websocket.close()
                print(f"got {serverAddress}/{serverPort}")
                break

    input("Press enter to connect")

    await asyncio.sleep(10)
    rtc = RTCInstance(debug = True, ip = serverAddress, port = serverPort)
    await rtc.init_auto_config(offer = False, channels = ["audio", "control"], stackData = True, manual = False)
    rtc.send_data("control", f'CONFIG_{json.dumps({"MICSAMPLERATE": mic.sampleRate})}')
    rtc.send_data("control", f'CONFIG_{json.dumps({"MICCHANNELS": 1 if mic.flatten else mic.channels})}')
    rtc.send_data("control", f'CONFIG_{json.dumps({"SPEAKERSAMPLERATE": speaker.sampleRate})}')
    rtc.send_data("control", f'CONFIG_{json.dumps({"SPEAKERCHANNELS": speaker.channels})}')
    rtc.send_data("control", "EOF")

    mic.ready = True

    while True:
        if (mic.queue.empty()):
            await asyncio.sleep(0.1)
            continue

        while (not mic.queue.empty()):
            sendAudioSlice = mic.queue.get()
            rtc.send_data(channelName = "audio", data = sendAudioSlice.tobytes())

        while (rtc.queue_has_item("audio")):
            mic.ready = False
            playbackAudioSlice = np.frombuffer(rtc.get_queue(channelName = "audio"), dtype = np.float32)
            if (speaker.sampleRate != mic.sampleRate):
                audio = resample_poly(playbackAudioSlice, speaker.sampleRate, mic.sampleRate).astype(np.float32)
            else:
                audio = playbackAudioSlice.astype(np.float32).ravel()

            speaker.play(audio)
            mic.ready = True



if __name__ == "__main__":
    asyncio.run(main())