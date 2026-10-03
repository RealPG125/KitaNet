import asyncio
import queue
import json
import kitanet_helper
from typing import Any
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCDataChannel

class RTCInstance:
    instanceNumber = 1
    config = {"iceServers": [{"urls": "stun:stun.1.google.com:19302"}]}
    def __init__(self, debug: bool = False, useSTUN: bool = False):
        self.enableDebug = debug
        self._pc = RTCPeerConnection() if not useSTUN else RTCPeerConnection(configuration = RTCInstance.config)
        self._channels: list[RTCDataChannel] = []
        self.instanceID: int = RTCInstance.instanceNumber
        self._useSTUN: bool = useSTUN
        self.queues: dict[str, queue.Queue[Any]] = {}
        self._states: dict[str, str] = {"connectionstate": "none", "iceconnectionstate": "none", "icegatheringstate": "none", "signalingstate": "none"}
        RTCInstance.instanceNumber += 1
        self._pc.on("datachannel", self.on_datachannel)
        self._pc.on("connectionstatechange", self.connection_state_change)
        self._pc.on("iceconnectionstatechange", self.ice_connection_state_change)
        self._pc.on("icegatheringstatechange", self.ice_gathering_state_change)
        self._pc.on("signalingstatechange", self.signaling_state_change)

    def connection_state_change(self):
        state = self._pc.connectionState
        self._states["connectionstate"] = state
        if (self.enableDebug):
            print(f"CommsPort instance {self.instanceID}: Connection state {state}")

    def ice_connection_state_change(self):
        state = self._pc.iceConnectionState
        self._states["iceconnectionstate"] = state
        if (self.enableDebug):
            print(f"CommsPort instance {self.instanceID}: ICE connection state {state}")

    def ice_gathering_state_change(self):
        state = self._pc.iceGatheringState
        self._states["icegatheringstate"] = state
        if (self.enableDebug):
            print(f"CommsPort instance {self.instanceID}: ICE gathering state {state}")

    def signaling_state_change(self):
        state = self._pc.signalingState
        self._states["signalingstate"] = state
        if (self.enableDebug):
            print(f"CommsPort instance {self.instanceID}: Signaling state {state}")

    async def create_offer(self):
        self._offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(self._offer)

    async def create_answer(self):
        self._answer = await self._pc.createAnswer()
        await self._pc.setLocalDescription(self._answer)

    def get_local_dict(self) -> dict[str, str]:
        localDict = {"sdp": self._pc.localDescription.sdp, "type": self._pc.localDescription.type}
        return localDict

    async def set_remote_dict(self, remoteDescriptionDict: dict[str, str]):
        descriptionDict = RTCSessionDescription(sdp = remoteDescriptionDict["sdp"], type = remoteDescriptionDict["type"])
        await self._pc.setRemoteDescription(descriptionDict)
        print(f"CommsPort instance {self.instanceID}: Remote set\n" if self.enableDebug else "", end = "")

    def create_channel(self, channelName: str | None = None, stackToQueue: bool = True) -> RTCDataChannel | None:
        if (channelName != None):
            channel = self._pc.createDataChannel(channelName)

            self._register_channel(channel)

            if (stackToQueue):
                self.queues[channelName] = queue.Queue()

            print(f"CommsPort instance {self.instanceID}: Created and registered channel {channelName}\n" if self.enableDebug else "", end = "")
            return channel
        
        else:
            print(f"CommsPort instance {self.instanceID}: Channel name is empty, aborting channel creation" if self.enableDebug else "", end = "")
            return None

    def _register_channel(self, channel: RTCDataChannel, manual: bool = True):
        self._channels.append(channel)
        channel.on("open", lambda: self.on_channel_open(channel = channel))
        channel.on("message", lambda message: self.on_message(channel = channel, message = message))
        channel.on("close", lambda: self.on_channel_close(channel = channel))

        print(f"CommsPort instance {self.instanceID}: Automatically registered channel {channel.label}\n" if (self.enableDebug and not manual) else "", end = "")

    def on_datachannel(self, channel: RTCDataChannel):
        self._register_channel(channel)

    def on_channel_open(self, channel: RTCDataChannel):
        print(f"CommsPort instance {self.instanceID}: Channel {channel.label} is now open\n" if self.enableDebug else "", end = "")

    def on_message(self, channel: RTCDataChannel, message: Any):
        print(f"CommsPort instance {self.instanceID}: Received message from channel {channel.label}: {message}\n" if self.enableDebug else "", end = "")
        if (channel.label in self.queues):
            self.queues[channel.label].put(message)

    def on_channel_close(self, channel: RTCDataChannel):
        print(f"CommsPort instance {self.instanceID}: Channel {channel.label} is now closed\n" if self.enableDebug else "", end = "")

    def debug_send(self, message: str = ""):
        if (self._channels and self._channels[0].readyState == "open"):
            self._channels[0].send(message)

    def send_data(self, channelName: str, data: Any):
        for channel in self._channels:
            if (channel.label == channelName):
                channel.send(data)
                print(f"CommsPort instance {self.instanceID}: \n" if self.enableDebug else "", end = "")
                break

    def get_queue(self, channelName: str):
        self.queues[channelName].get()

    def get_state(self, stateName: str):
        return self._states[stateName]

async def main():
    rtc = RTCInstance(debug = True)
    while True:
        offer = input("Offer / Answer: ")
        if (offer == ""):
            offer = False
            print("Using default mode: Client")
            break
        elif (returnTuple := kitanet_helper.succeeds(int, offer))[0]:
            if (0 <= returnTuple[1] <= 1):
                offer = returnTuple[1] == 0
                break
        else:
            if (offer.lower() in ["offer", "answer"]):
                offer = offer.lower() == "offer"
                break

    if (offer):
        rtc.create_channel("text")

        await rtc.create_offer()
        while (rtc.get_state("icegatheringstate") != "complete"):
            await asyncio.sleep(0.1)

        offerDict = rtc.get_local_dict()
        print(f"Offer dict: {json.dumps(offerDict)}")

        answer = input("Answer dict: ")
        answerDict: dict[str, str] = json.loads(answer)
        await rtc.set_remote_dict(answerDict)

        while True:
            message = await asyncio.to_thread(input, "> ")
            rtc.send_data("text", message)

    else:
        offer = await asyncio.to_thread(input, "Offer dict: ")
        offerDict: dict[str, str] = json.loads(offer)
        await rtc.set_remote_dict(offerDict)

        await rtc.create_answer()
        while (rtc.get_state("icegatheringstate") != "complete"):
            await asyncio.sleep(0.1)

        answerDict = rtc.get_local_dict()
        print(f"Answer dict: {json.dumps(answerDict)}")

        while (rtc.get_state("connectionstate") != "complete"):
            await asyncio.sleep(0.1)
        while True:
            message = await asyncio.to_thread(input, "> ")
            rtc.send_data("text", message)



if (__name__ == "__main__"):
    asyncio.run(main())