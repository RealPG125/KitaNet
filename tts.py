"""
TTS 音声読み上げツール - 全言語対応版

言語検出: lingua-language-detector (75言語) + langdetect フォールバック
TTS エンジン優先順位:
  日本語 -> VOICEVOX -> gTTS -> pyttsx3
  タイ語 -> PyThaiTTS -> gTTS -> pyttsx3
  他言語 -> gTTS (Google TTS, 60+言語対応) -> pyttsx3

インストール:
  pip install lingua-language-detector langdetect gtts pygame pyaudio pythaitts requests pyttsx3

VOICEVOX (日本語高品質・任意):
  https://voicevox.hiroshiba.jp/
"""

import requests
import json
import io
import os
import tempfile

# ============================
#  VOICEVOX 設定
# ============================
VOICEVOX_URL     = "http://localhost:50021"
VOICEVOX_SPEAKER = 3  # 3=ずんだもん / 2=四国めたん / 8=春日部つむぎ

# ============================
#  gTTS 対応言語マップ
#  lingua ISO 639-1 -> gTTS lang code
# ============================
GTTS_LANG_MAP = {
    "af": "af",       # Afrikaans
    "ar": "ar",       # Arabic
    "bg": "bg",       # Bulgarian
    "bn": "bn",       # Bengali
    "bs": "bs",       # Bosnian
    "ca": "ca",       # Catalan
    "cs": "cs",       # Czech
    "cy": "cy",       # Welsh
    "da": "da",       # Danish
    "de": "de",       # German
    "el": "el",       # Greek
    "en": "en",       # English
    "eo": "eo",       # Esperanto
    "es": "es",       # Spanish
    "et": "et",       # Estonian
    "fi": "fi",       # Finnish
    "fr": "fr",       # French
    "gu": "gu",       # Gujarati
    "hi": "hi",       # Hindi
    "hr": "hr",       # Croatian
    "hu": "hu",       # Hungarian
    "hy": "hy",       # Armenian
    "id": "id",       # Indonesian
    "is": "is",       # Icelandic
    "it": "it",       # Italian
    "ja": "ja",       # Japanese
    "jw": "jw",       # Javanese
    "km": "km",       # Khmer
    "kn": "kn",       # Kannada
    "ko": "ko",       # Korean
    "la": "la",       # Latin
    "lv": "lv",       # Latvian
    "lt": "lt",       # Lithuanian  (lingua: "lt")
    "mk": "mk",       # Macedonian
    "ml": "ml",       # Malayalam
    "mr": "mr",       # Marathi
    "my": "my",       # Myanmar (Burmese)
    "ne": "ne",       # Nepali
    "nl": "nl",       # Dutch
    "no": "no",       # Norwegian
    "pl": "pl",       # Polish
    "pt": "pt",       # Portuguese
    "ro": "ro",       # Romanian
    "ru": "ru",       # Russian
    "si": "si",       # Sinhala
    "sk": "sk",       # Slovak
    "sq": "sq",       # Albanian
    "sr": "sr",       # Serbian
    "su": "su",       # Sundanese
    "sv": "sv",       # Swedish
    "sw": "sw",       # Swahili
    "ta": "ta",       # Tamil
    "te": "te",       # Telugu
    "th": "th",       # Thai
    "tl": "tl",       # Filipino
    "tr": "tr",       # Turkish
    "uk": "uk",       # Ukrainian
    "ur": "ur",       # Urdu
    "vi": "vi",       # Vietnamese
    "zh-cn": "zh-CN", # Chinese Simplified
    "zh-tw": "zh-TW", # Chinese Traditional
    "zh": "zh-CN",    # Chinese (fallback)
}

# ============================
#  言語検出
# ============================
def detect_language(text: str) -> str:
    """
    テキストの言語を自動検出。
    lingua (高精度・75言語) を優先し、失敗時は langdetect にフォールバック。
    返り値は ISO 639-1 小文字コード (例: "ja", "en", "th")
    """
    # --- lingua で検出 ---
    try:
        from lingua import LanguageDetectorBuilder
        detector = LanguageDetectorBuilder.from_all_languages().build()
        result = detector.detect_language_of(text)
        if result is not None:
            iso = result.iso_code_639_1.name.lower()
            return iso
    except ImportError:
        pass
    except Exception:
        pass

    # --- langdetect フォールバック ---
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        pass

    return "en"  # 検出不能時は英語扱い


# ============================
#  エンジン: VOICEVOX (日本語専用)
# ============================
def voicevox_speak(text: str, speaker: int = VOICEVOX_SPEAKER) -> bool:
    try:
        q = requests.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": speaker},
            timeout=5,
        )
        q.raise_for_status()

        s = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": speaker},
            data=json.dumps(q.json()),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        s.raise_for_status()
        _play_wav_bytes(s.content)
        return True

    except (requests.ConnectionError, requests.Timeout):
        return False
    except Exception as e:
        print(f"VOICEVOX error: {e}")
        return False


# ============================
#  エンジン: PyThaiTTS (タイ語専用・オフライン)
# ============================
def pythaitts_speak(text: str) -> bool:
    try:
        from pythaitts import TTS
        import pygame

        tts = TTS()
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        tts.tts(text, filename=tmp.name)

        pygame.mixer.init()
        pygame.mixer.music.load(tmp.name)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.quit()
        os.unlink(tmp.name)
        return True

    except ImportError:
        print("pythaitts が未インストール: pip install pythaitts")
        return False
    except Exception as e:
        print(f"PyThaiTTS error: {e}")
        return False


# ============================
#  エンジン: gTTS (多言語・オンライン)
# ============================
def gtts_speak(text: str, lang: str) -> bool:
    try:
        from gtts import gTTS, lang as gtts_langs
        import pygame

        # サポート言語か確認。なければ英語にフォールバック
        supported = gtts_langs.tts_langs()
        gtts_code  = GTTS_LANG_MAP.get(lang, lang)
        if gtts_code not in supported:
            print(f"gTTS: '{lang}' 未対応 -> en にフォールバック")
            gtts_code = "en"

        tts = gTTS(text=text, lang=gtts_code)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        tts.save(tmp.name)

        pygame.mixer.init()
        pygame.mixer.music.load(tmp.name)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.quit()
        os.unlink(tmp.name)
        return True

    except ImportError:
        print("gtts / pygame が未インストール: pip install gtts pygame")
        return False
    except Exception as e:
        print(f"gTTS error: {e}")
        return False


# ============================
#  エンジン: pyttsx3 (オフライン・最終フォールバック)
# ============================
def pyttsx3_speak(text: str, lang: str) -> bool:
    try:
        import pyttsx3

        engine  = pyttsx3.init()
        voices  = engine.getProperty("voices")
        target  = lang.split("-")[0].lower()
        matched = next(
            (v for v in voices if target in v.name.lower() or target in v.id.lower()),
            None,
        )
        if matched:
            engine.setProperty("voice", matched.id)

        engine.setProperty("rate", 135)
        engine.setProperty("volume", 1.0)
        engine.say(text)
        engine.runAndWait()
        return True

    except ImportError:
        print("pyttsx3 が未インストール: pip install pyttsx3")
        return False
    except Exception as e:
        print(f"pyttsx3 error: {e}")
        return False


# ============================
#  WAV 再生ヘルパー
# ============================
def _play_wav_bytes(wav_bytes: bytes):
    import pyaudio
    import wave

    buf = io.BytesIO(wav_bytes)
    with wave.open(buf) as wf:
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pa.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
        )
        stream.write(wf.readframes(wf.getnframes()))
        stream.stop_stream()
        stream.close()
        pa.terminate()


# ============================
#  メイン読み上げロジック
# ============================
def speak(text: str, lang: str = "auto"):
    """
    言語を自動検出または指定してTTSで読み上げる。

    lang: "auto" で自動検出、または ISO 639-1 コード ("ja", "en", "th" など)
    """
    if lang == "auto":
        lang = detect_language(text)
        print(f"検出言語: {lang}")
    else:
        print(f"指定言語: {lang}")

    print("読み上げ中...")

    if lang == "ja":
        if voicevox_speak(text):
            print("完了 [VOICEVOX]")
            return
        print("VOICEVOX 未起動 -> gTTS へ")

    elif lang == "th":
        if pythaitts_speak(text):
            print("完了 [PyThaiTTS]")
            return
        print("PyThaiTTS 失敗 -> gTTS へ")

    if gtts_speak(text, lang):
        print("完了 [gTTS]")
        return

    print("gTTS 失敗 -> pyttsx3 へ")
    if pyttsx3_speak(text, lang):
        print("完了 [pyttsx3]")
        return

    print("全エンジン失敗: インストール状況を確認してください")


# ============================
#  メイン
# ============================
def print_supported_langs():
    """gTTS の対応言語一覧を動的に表示"""
    try:
        from gtts.lang import tts_langs
        langs = tts_langs()
        print(f"  gTTS 対応言語数: {len(langs)}")
        for code, name in sorted(langs.items()):
            print(f"    {code:<8} {name}")
    except ImportError:
        print("  (gTTS 未インストールのため一覧取得不可)")


def main():
    print("=" * 55)
    print("  TTS 全言語対応読み上げツール")
    print("=" * 55)
    print("  テキストを入力すると言語を自動検出して読み上げます")
    print("  言語を手動指定: テキスト:言語コード")
    print("  例) Hello:en  /  สวัสดี:th  /  你好:zh-cn")
    print()
    print("  対応言語一覧を表示: langs と入力")
    print("  終了: quit または exit")
    print("=" * 55)
    print()

    while True:
        raw = input("テキスト > ").strip()

        if raw.lower() in ("quit", "exit", "q"):
            print("終了します")
            break

        if raw == "":
            print("テキストを入力してください")
            continue

        if raw.lower() == "langs":
            print_supported_langs()
            print()
            continue

        # 言語コード手動指定 (テキスト:langcode)
        if ":" in raw:
            parts = raw.rsplit(":", 1)
            text = parts[0].strip()
            lang = parts[1].strip().lower()
        else:
            text = raw
            lang = "auto"

        speak(text, lang)
        print()


if __name__ == "__main__":
    main()
