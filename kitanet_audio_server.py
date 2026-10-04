import kitanet_comm
import threading
import asyncio
from kitanet_comm import RTCInstance
from kitanet_audio import Mic


async def main():
    mic = Mic(manual = True)
    rtc = RTCInstance()
    await rtc.init_auto_config(offer = False, channels = ["audio"])

    input("Press enter to start")
    mic.ready = True

    while True:
        if (mic.queue.empty()):
            await asyncio.sleep(0.1)
            continue

        while (not mic.queue.empty()):
            audioSlice = mic.queue.get()
            rtc.send_data(channelName = "audio", data = audioSlice.tobytes())

if __name__ == "__main__":
    asyncio.run(main())