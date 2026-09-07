"""
TTS 音声合成 - VOICEVOX版（高品質・日本語）
事前準備:
  1. VOICEVOX をインストール・起動 → https://voicevox.hiroshiba.jp/
  2. pip install requests pyaudio

pyttsx3 フォールバック版も内蔵（VOICEVOXなしでも動く）
"""

import requests
import json
import io
import sys

# ============================
#  VOICEVOX 設定
# ============================
VOICEVOX_URL = "http://localhost:50021"
SPEAKER_ID = 3  # ずんだもん(3) / 四国めたん(2) / 春日部つむぎ(8)

def voicevox_speak(text: str, speaker: int = SPEAKER_ID):
    """VOICEVOXで読み上げ（要: VOICEVOXアプリ起動中）"""
    try:
        # 音声クエリ生成
        query_res = requests.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": speaker}
        )
        query_res.raise_for_status()
        query = query_res.json()

        # 音声合成
        synth_res = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": speaker},
            data=json.dumps(query),
            headers={"Content-Type": "application/json"}
        )
        synth_res.raise_for_status()

        # 再生
        import pyaudio
        import wave

        audio_data = io.BytesIO(synth_res.content)
        with wave.open(audio_data) as wf:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pa.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True
            )
            stream.write(wf.readframes(wf.getnframes()))
            stream.stop_stream()
            stream.close()
            pa.terminate()

        return True

    except requests.ConnectionError:
        return False  # VOICEVOX未起動


def pyttsx3_speak(text: str):
    """pyttsx3フォールバック（VOICEVOXなしでも動く）"""
    import pyttsx3
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    for voice in voices:
        if 'japanese' in voice.name.lower() or 'ja' in voice.id.lower():
            engine.setProperty('voice', voice.id)
            break
    engine.setProperty('rate', 130)
    engine.say(text)
    engine.runAndWait()


def speak(text: str):
    """VOICEVOX優先、なければpyttsx3で読み上げ"""
    print("読み上げ中...")
    success = voicevox_speak(text)
    if not success:
        print("VOICEVOX未起動 -> pyttsx3で代替")
        pyttsx3_speak(text)
    print("完了")


# ============================
#  メイン: 自分で文字入力
# ============================
def main():
    print("=" * 45)
    print("  TTS 音声読み上げツール")
    print("=" * 45)
    print("  VOICEVOX起動中 -> 高品質音声")
    print("  VOICEVOX未起動 -> pyttsx3で代替")
    print("-" * 45)
    print("  スピーカーID (VOICEVOX):")
    print("    2 = 四国めたん  3 = ずんだもん")
    print("    8 = 春日部つむぎ  13 = 青山龍星")
    print("=" * 45)
    print("終了: quit または exit")
    print()

    while True:
        text = input("読み上げたい文字 > ").strip()

        if text.lower() in ("quit", "exit", "q"):
            print("終了します")
            break

        if text == "":
            print("文字を入力してください")
            continue

        speak(text)
        print()


if __name__ == "__main__":
    main()
