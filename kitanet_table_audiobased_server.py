import kitanet_comm
import kitanet_helper
import threading
import asyncio
import numpy as np
import json
import threading
import time
import os

from scipy.signal import resample_poly
from kitanet_comm import RTCInstance
from kitanet_audio import Mic, Speaker
from kitanet_db import DB
from dotenv import load_dotenv
from websockets.asyncio.client import connect

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

async def main():
    db = DB(dbName = DB_NAME, dbUser = DB_USER, dbPassword = DB_PASSWORD)

    while True:
        null, tableId = kitanet_helper.succeeds(int, input("Table ID: "))
        if (tableId > -1):
            tableSessionsId = db.execute(f"select id from tablesession where table_id = {tableId} and end_datetime is null order by start_datetime desc;")
            if (len(tableSessionsId) > 0):
                break
            else:
                print(f"No table session available at table {tableId}")

    try:
        mic = Mic(manual = True)
        speaker = Speaker(manual = True)

        input("Press enter to connect")

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

        await asyncio.sleep(10)
        rtc = RTCInstance(debug = True, ip = serverAddress, port = serverPort)
        await rtc.init_auto_config(offer = False, channels = ["audio", "control"], stackData = True, manual = False)
        rtc.send_data("control", f'CONFIG_{json.dumps({"MICSAMPLERATE": mic.sampleRate})}')
        rtc.send_data("control", f'CONFIG_{json.dumps({"MICCHANNELS": 1 if mic.flatten else mic.channels})}')
        rtc.send_data("control", f'CONFIG_{json.dumps({"SPEAKERSAMPLERATE": speaker.sampleRate})}')
        rtc.send_data("control", f'CONFIG_{json.dumps({"SPEAKERCHANNELS": speaker.channels})}')

        tableSessionsId = db.execute(f"select id from tablesession where table_id = {tableId} and end_datetime is null order by start_datetime desc;")
        # activation logic
        # set latest session conversation to active
        # db.execute(f"update tablesession set conversation_status = true where id = UUID('{tableSessionsId[0][0]}');")

        rtc.send_data("control", f'CONFIG_{json.dumps({"TABLESESSIONID": str(tableSessionsId[0][0])})}')
        rtc.send_data("control", "EOF")

        # # if multiple open conversation sessions exist within the same tableId, end the old session
        # # scrap, do from web
        # if (len(tableSessions) > 1):
        #     for item in tableSessions:
        #         if item[0] != tableSessions[0]:
        #             db.execute(f"update tablesession set conversation_status = false, end_datetime = now() where id = {item[0]};")

        mic.ready = True

        playbackState = True

        def playback():
            while playbackState:
                while (rtc.queue_has_item("audio")):
                    mic.ready = False
                    playbackAudioSlice = np.frombuffer(rtc.get_queue(channelName = "audio"), dtype = np.float32)
                    if (speaker.sampleRate != mic.sampleRate):
                        audio = resample_poly(playbackAudioSlice, speaker.sampleRate, mic.sampleRate).astype(np.float32)
                    else:
                        audio = playbackAudioSlice.astype(np.float32).ravel()
        
                    speaker.play(audio)
                    mic.ready = True
                time.sleep(0.1)

        threading.Thread(target = playback, daemon = True).start()

        while True:
            if (mic.queue.empty()):
                await asyncio.sleep(0.1)
                continue

            while (not mic.queue.empty()):
                sendAudioSlice = mic.queue.get()
                rtc.send_data(channelName = "audio", data = sendAudioSlice.tobytes())
    
    except Exception as e:
        print(e)
        # db.execute(f"update tablesession set conversation_status = false where id = UUID('{tableSessionsId[0][0]}');")
        print("switched off conversation status")
        playbackState = False

if __name__ == "__main__":
    asyncio.run(main())