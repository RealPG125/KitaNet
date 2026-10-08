import kitanet_comm
import threading
import asyncio
import numpy as np
import json
from kitanet_comm import RTCInstance
from kitanet_audio import Mic, Speaker


async def main():
    rtc = RTCInstance()
    await rtc.init_auto_config(offer = False, channels = ["audio", "control"])
    mic = Mic(manual = True)
    speaker = Speaker(manual = True)
    rtc.send_data("control", f"CONFIG_{json.dumps({'MICSAMPLERATE': mic.sampleRate})}")
    rtc.send_data("control", f"CONFIG_{json.dumps({'MICCHANNELS': mic.channels})}")
    rtc.send_data("control", f"CONFIG_{json.dumps({'SPEAKERSAMPLERATE': speaker.sampleRate})}")
    rtc.send_data("control", f"CONFIG_{json.dumps({'SPEAKERCHANNELS': speaker.channels})}")
    rtc.send_data("control", f"EOF")

    input("Press enter to start")
    mic.ready = True

    while True:
        if (mic.queue.empty()):
            await asyncio.sleep(0.1)
            continue

        while (not mic.queue.empty()):
            sendAudioSlice = mic.queue.get()
            rtc.send_data(channelName = "audio", data = sendAudioSlice.tobytes())

        while (rtc.queue_has_item("audio")):
            playbackAudioSlice = np.frombuffer(rtc.get_queue(), dtype = np.float32)
            if (speaker.sampleRate != mic.sampleRate):
                audio = resample_poly(playbackAudioSlice, speaker.sampleRate, mic.sampleRate).astype(np.float32)
            else:
                audio = playbackAudioSlice.astype(np.float32).ravel()

            speaker.play(audio, sourceChannels = mic.channels if not mic.flatten else 1)


if __name__ == "__main__":
    asyncio.run(main())