"""
TTS 音声読み上げツール - 全言語 / 感情 / 性別 対応版

言語検出 : lingua-language-detector (75言語) + langdetect フォールバック
感情検出 : 末尾記号から自動判定
  !  -> excited  (速め・高め)
  ?  -> curious  (やや高め)
  .. -> sad      (遅め・低め)
  ~~ -> calm     (ゆっくり)
  なし -> normal

TTS エンジン優先順位:
  日本語 -> VOICEVOX (感情パラメータ直接注入) -> gTTS+後処理 -> pyttsx3
  タイ語 -> PyThaiTTS -> gTTS+後処理 -> pyttsx3
  他言語 -> gTTS+後処理 (60+言語) -> pyttsx3

インストール:
  pip install lingua-language-detector langdetect gtts pygame pyaudio
             pythaitts requests pyttsx3 pydub static-ffmpeg

VOICEVOX (日本語高品質・任意):
  https://voicevox.hiroshiba.jp/
"""

import re
import requests
import json
import io
import os
import tempfile

# pydub が使う ffmpeg/ffprobe を static-ffmpeg から自動設定
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

# ============================
#  VOICEVOX 設定
# ============================
VOICEVOX_URL = "http://localhost:50021"

VOICEVOX_SPEAKERS = {
    "female": {"normal": 3,  "excited": 2,  "curious": 8,  "sad": 3,  "calm": 2},
    "male":   {"normal": 13, "excited": 13, "curious": 13, "sad": 16, "calm": 16},
}
# female: 3=ずんだもん 2=四国めたん 8=春日部つむぎ
# male:   13=青山龍星  16=玄野武宏

# ============================
#  感情プロファイル
# ============================
EMOTION_PROFILES = {
    "excited": dict(rate=200, volume=1.00, gtts_slow=False, vx_speed=1.40, vx_pitch= 0.12, pydub_speed=1.20, pydub_semitones= 3, label="excited  [ ! ]"),
    "curious": dict(rate=160, volume=0.95, gtts_slow=False, vx_speed=1.10, vx_pitch= 0.08, pydub_speed=1.05, pydub_semitones= 2, label="curious  [ ? ]"),
    "sad":     dict(rate=110, volume=0.80, gtts_slow=True,  vx_speed=0.78, vx_pitch=-0.10, pydub_speed=0.80, pydub_semitones=-3, label="sad      [ ... ]"),
    "calm":    dict(rate=130, volume=0.88, gtts_slow=True,  vx_speed=0.88, vx_pitch=-0.05, pydub_speed=0.88, pydub_semitones=-1, label="calm     [ ~~ ]"),
    "normal":  dict(rate=160, volume=1.00, gtts_slow=False, vx_speed=1.10, vx_pitch= 0.00, pydub_speed=1.00, pydub_semitones= 0, label="normal"),
}

# ============================
#  gTTS 言語マップ
# ============================
GTTS_LANG_MAP = {
    "af": "af", "ar": "ar", "bg": "bg", "bn": "bn", "bs": "bs",
    "ca": "ca", "cs": "cs", "cy": "cy", "da": "da", "de": "de",
    "el": "el", "en": "en", "eo": "eo", "es": "es", "et": "et",
    "fi": "fi", "fr": "fr", "gu": "gu", "hi": "hi", "hr": "hr",
    "hu": "hu", "hy": "hy", "id": "id", "is": "is", "it": "it",
    "ja": "ja", "jw": "jw", "km": "km", "kn": "kn", "ko": "ko",
    "la": "la", "lv": "lv", "lt": "lt", "mk": "mk", "ml": "ml",
    "mr": "mr", "my": "my", "ne": "ne", "nl": "nl", "no": "no",
    "pl": "pl", "pt": "pt", "ro": "ro", "ru": "ru", "si": "si",
    "sk": "sk", "sq": "sq", "sr": "sr", "su": "su", "sv": "sv",
    "sw": "sw", "ta": "ta", "te": "te", "th": "th", "tl": "tl",
    "tr": "tr", "uk": "uk", "ur": "ur", "vi": "vi",
    "zh-cn": "zh-CN", "zh-tw": "zh-TW", "zh": "zh-CN",
}

# ============================
#  感情検出
# ============================
def detect_emotion(text: str) -> str:
    s = text.strip()
    if re.search(r"!+\s*$", s):   return "excited"
    if re.search(r"\?\s*$", s):   return "curious"
    if re.search(r"\.{2,}\s*$", s): return "sad"
    if re.search(r"~~\s*$", s):   return "calm"
    return "normal"

# ============================
#  言語検出
# ============================
def detect_language(text: str) -> str:
    try:
        from lingua import LanguageDetectorBuilder
        detector = LanguageDetectorBuilder.from_all_languages().build()
        result = detector.detect_language_of(text)
        if result is not None:
            return result.iso_code_639_1.name.lower()
    except Exception:
        pass
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        pass
    return "en"

# ============================
#  WAV 再生
# ============================
def _play_wav_bytes(wav_bytes: bytes):
    import pyaudio, wave
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
#  エンジン: VOICEVOX
# ============================
def voicevox_speak(text: str, emotion: str, gender: str) -> bool:
    try:
        speaker = VOICEVOX_SPEAKERS[gender][emotion]
        p = EMOTION_PROFILES[emotion]

        q = requests.post(f"{VOICEVOX_URL}/audio_query",
                          params={"text": text, "speaker": speaker}, timeout=5)
        q.raise_for_status()
        query = q.json()
        query["speedScale"]  = p["vx_speed"]
        query["pitchScale"]  = round(p["vx_pitch"], 2)
        query["volumeScale"] = p["volume"]

        s = requests.post(f"{VOICEVOX_URL}/synthesis",
                          params={"speaker": speaker},
                          data=json.dumps(query),
                          headers={"Content-Type": "application/json"},
                          timeout=10)
        s.raise_for_status()
        _play_wav_bytes(s.content)
        return True
    except (requests.ConnectionError, requests.Timeout):
        return False
    except Exception as e:
        print(f"VOICEVOX error: {e}")
        return False

# ============================
#  エンジン: PyThaiTTS (タイ語)
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
#  感情を MP3 に適用 (pydub)
# ============================
def _apply_emotion_to_mp3(src: str, dst: str, emotion: str):
    p         = EMOTION_PROFILES[emotion]
    speed     = p["pydub_speed"]
    semitones = p["pydub_semitones"]

    if speed == 1.0 and semitones == 0:
        import shutil; shutil.copy(src, dst); return

    try:
        from pydub import AudioSegment
        from pydub.effects import speedup

        audio = AudioSegment.from_mp3(src)

        if semitones != 0:
            factor   = 2 ** (semitones / 12.0)
            new_rate = int(audio.frame_rate * factor)
            audio    = audio._spawn(audio.raw_data,
                                    overrides={"frame_rate": new_rate})
            audio    = audio.set_frame_rate(44100)

        if speed > 1.0:
            audio = speedup(audio, playback_speed=speed)
        elif speed < 1.0:
            slow_rate = int(audio.frame_rate * speed)
            audio     = audio._spawn(audio.raw_data,
                                     overrides={"frame_rate": slow_rate})
            audio     = audio.set_frame_rate(44100)

        audio.export(dst, format="mp3")

    except Exception as e:
        print(f"pydub error: {e} -> 感情なしで再生")
        import shutil; shutil.copy(src, dst)

# ============================
#  エンジン: gTTS (多言語・感情後処理)
# ============================
def gtts_speak(text: str, lang: str, emotion: str) -> bool:
    try:
        from gtts import gTTS
        from gtts.lang import tts_langs
        import pygame

        p         = EMOTION_PROFILES[emotion]
        supported = tts_langs()
        code      = GTTS_LANG_MAP.get(lang, lang)
        if code not in supported:
            print(f"gTTS: '{lang}' 未対応 -> en")
            code = "en"

        tts = gTTS(text=text, lang=code, slow=p["gtts_slow"])
        raw = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        raw.close()
        tts.save(raw.name)

        out = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        out.close()
        _apply_emotion_to_mp3(raw.name, out.name, emotion)
        os.unlink(raw.name)

        pygame.mixer.init()
        pygame.mixer.music.load(out.name)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.quit()
        os.unlink(out.name)
        return True
    except ImportError:
        print("gtts / pygame が未インストール")
        return False
    except Exception as e:
        print(f"gTTS error: {e}")
        return False

# ============================
#  エンジン: pyttsx3 (オフライン・フォールバック)
# ============================
def pyttsx3_speak(text: str, lang: str, emotion: str, gender: str) -> bool:
    try:
        import pyttsx3

        p        = EMOTION_PROFILES[emotion]
        engine   = pyttsx3.init()
        voices   = engine.getProperty("voices")
        lang_key = lang.split("-")[0].lower()
        gen_key  = gender.lower()

        matched = None
        for v in voices:
            n, i = v.name.lower(), v.id.lower()
            if (lang_key in n or lang_key in i) and (gen_key in n or gen_key in i):
                matched = v; break
        if not matched:
            for v in voices:
                n, i = v.name.lower(), v.id.lower()
                if lang_key in n or lang_key in i:
                    matched = v; break
        if not matched:
            for v in voices:
                if gen_key in v.name.lower() or gen_key in v.id.lower():
                    matched = v; break
        if matched:
            engine.setProperty("voice", matched.id)

        engine.setProperty("rate",   p["rate"])
        engine.setProperty("volume", p["volume"])
        engine.say(text)
        engine.runAndWait()
        return True
    except ImportError:
        print("pyttsx3 が未インストール")
        return False
    except Exception as e:
        print(f"pyttsx3 error: {e}")
        return False

# ============================
#  メイン読み上げ
# ============================
def speak(text: str, lang: str, gender: str, emotion_override: str = "auto"):
    if lang == "auto":
        lang = detect_language(text)

    emotion = (emotion_override
               if emotion_override != "auto" and emotion_override in EMOTION_PROFILES
               else detect_emotion(text))

    print(f"言語: {lang}  /  感情: {EMOTION_PROFILES[emotion]['label']}  /  性別: {gender}")
    print("読み上げ中...")

    if lang == "ja":
        if voicevox_speak(text, emotion, gender):
            print("完了 [VOICEVOX]"); return
        print("VOICEVOX 未起動 -> gTTS へ")
        if gtts_speak(text, lang, emotion):
            print("完了 [gTTS]"); return
        print("gTTS 失敗 -> pyttsx3 へ")
        if pyttsx3_speak(text, lang, emotion, gender):
            print("完了 [pyttsx3]"); return

    elif lang == "th":
        if pythaitts_speak(text):
            print("完了 [PyThaiTTS]"); return
        print("PyThaiTTS 失敗 -> gTTS へ")
        if gtts_speak(text, lang, emotion):
            print("完了 [gTTS]"); return
        print("gTTS 失敗 -> pyttsx3 へ")
        if pyttsx3_speak(text, lang, emotion, gender):
            print("完了 [pyttsx3]"); return

    else:
        if gtts_speak(text, lang, emotion):
            print("完了 [gTTS]"); return
        print("gTTS 失敗 -> pyttsx3 へ")
        if pyttsx3_speak(text, lang, emotion, gender):
            print("完了 [pyttsx3]"); return

    print("全エンジン失敗")

# ============================
#  ユーティリティ
# ============================
def print_supported_langs():
    try:
        from gtts.lang import tts_langs
        langs = tts_langs()
        print(f"  gTTS 対応言語数: {len(langs)}")
        for code, name in sorted(langs.items()):
            print(f"    {code:<8} {name}")
    except ImportError:
        print("  (gTTS 未インストール)")

def select_gender() -> str:
    print("性別を選択:  1 = female  /  2 = male")
    while True:
        c = input("選択 (1/2) > ").strip()
        if c == "1": return "female"
        if c == "2": return "male"

def select_emotion() -> str:
    opts = {"1":"auto","2":"normal","3":"excited","4":"curious","5":"sad","6":"calm"}
    print("感情を選択:")
    print("  1=auto  2=normal  3=excited[!]  4=curious[?]  5=sad[...]  6=calm[~~]")
    while True:
        c = input("選択 (1-6) > ").strip()
        if c in opts: return opts[c]

# ============================
#  メイン
# ============================
def main():
    print("=" * 55)
    print("  TTS 全言語 / 感情 / 性別 対応ツール")
    print("=" * 55)
    print("  入力形式:")
    print("    テキスト              -> 言語・感情 自動")
    print("    テキスト:言語         -> 言語手動")
    print("    テキスト@感情         -> 感情手動")
    print("    テキスト@感情:言語    -> 両方手動")
    print()
    print("  例) Hello world@excited:en  /  悲しいな@sad:ja")
    print()
    print("  コマンド: emotion / gender / langs / quit")
    print("=" * 55)
    print()

    gender       = select_gender()
    print(f"性別: {gender}\n")
    emotion_mode = select_emotion()
    print(f"感情モード: {emotion_mode}\n")

    while True:
        raw = input("テキスト > ").strip()

        if raw.lower() in ("quit", "exit", "q"):
            print("終了します"); break
        if raw == "":
            continue
        if raw.lower() == "langs":
            print_supported_langs(); print(); continue
        if raw.lower() == "gender":
            gender = select_gender()
            print(f"性別: {gender}\n"); continue
        if raw.lower() == "emotion":
            emotion_mode = select_emotion()
            print(f"感情モード: {emotion_mode}\n"); continue

        # テキスト解析: テキスト@感情:言語
        text    = raw
        lang    = "auto"
        emotion = emotion_mode

        if "@" in text:
            t_parts = text.rsplit("@", 1)
            text    = t_parts[0].strip()
            rest    = t_parts[1].strip()
            if ":" in rest:
                emo_raw, lang = rest.split(":", 1)
                emo_raw = emo_raw.strip().lower()
                lang    = lang.strip().lower()
            else:
                emo_raw = rest.lower()
            emotion = emo_raw if emo_raw in EMOTION_PROFILES else emotion_mode

        elif ":" in text:
            parts = text.rsplit(":", 1)
            text  = parts[0].strip()
            lang  = parts[1].strip().lower()

        speak(text, lang, gender, emotion)
        print()

if __name__ == "__main__":
    main()
