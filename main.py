import json
import os
import time
import re
import math
import random
import subprocess
import glob
import tempfile
import asyncio
import urllib.parse
from threading import Lock, Thread

import requests
import edge_tts

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import speech_recognition as sr
except ImportError:
    sr = None

_tts_engine = None
_tts_lock = Lock()

import pygame
pygame.init()

# --------------------------------------------------------------------------
# CONFIG & API KEYS (Hybrid System: Groq + Mistral/Ollama)
# --------------------------------------------------------------------------
# Never hardcode secrets. Set these as environment variables or in a local
# .env file (see .env.example). Do NOT commit a real .env file.
GROQ_API_KEY = os.getenv(" so secret gsk key paste the groq apı key", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
DEFAULT_CITY = os.getenv("SYDRA_DEFAULT_CITY", "Afyon")
HISTORY_FILE = "chat_history.json"

# --------------------------------------------------------------------------
# 0. SOHBET GEÇMİŞİ YÖNETİCİSİ
# --------------------------------------------------------------------------
class ChatHistoryManager:
    @staticmethod
    def yukle():
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                pass
        return []

    @staticmethod
    def kaydet(history):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as fh:
                json.dump(history, fh, ensure_ascii=False, indent=4)
        except Exception:
            pass

    @staticmethod
    def temizle():
        if os.path.exists(HISTORY_FILE):
            try:
                os.remove(HISTORY_FILE)
            except Exception:
                pass

# --------------------------------------------------------------------------
# 1. DONANIM VE GÜÇ YÖNETİMİ
# --------------------------------------------------------------------------
ASUS_KBD_ROOT = "/sys/devices/platform/asus-nb-wmi/leds/asus::kbd_backlight"

def _write_sysfs(path: str, value: str) -> bool:
    try:
        with open(path, "w") as fh:
            fh.write(value)
        return True
    except Exception:
        try:
            cmd = f'pkexec sh -c \'echo "{value.strip()}" > {path}\''
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            try:
                cmd = f'echo "{value.strip()}" > {path}'
                subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                return False

def set_screen_brightness(percentage: int):
    try:
        subprocess.run(f"brightnessctl set {percentage}%", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def performans_modu(aktif: bool) -> str:
    profile = "performance" if aktif else "balanced"
    try:
        subprocess.run(f"pkexec powerprofilesctl set {profile}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"⚡ **Performans Modu {'Etkinleştirildi' if aktif else 'Devre Dışı'}!**"
    except Exception:
        return "⚠️ Performans modu değiştirilemedi."

def guc_tasarrufu_modu(aktif: bool) -> str:
    profile = "power-saver" if aktif else "balanced"
    try:
        subprocess.run(f"pkexec powerprofilesctl set {profile}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    if aktif:
        KeyboardControl.set_brightness(0)
        set_screen_brightness(20)
        return "🔋 **Maksimum Güç Tasarrufu Etkinleştirildi!**"
    else:
        KeyboardControl.set_brightness(2)
        set_screen_brightness(70)
        return "⚡ **Güç Tasarrufu Devre Dışı Bırakıldı.**"

class KeyboardControl:
    LAST_HEX = ""

    @classmethod
    def set_color_rgb(cls, r: int, g: int, b: int, renk_adi: str = "") -> str:
        r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
        hex_code = f"{r:02X}{g:02X}{b:02X}"
        cls.LAST_HEX = hex_code

        if os.path.isdir(ASUS_KBD_ROOT):
            if _write_sysfs(f"{ASUS_KBD_ROOT}/kbd_rgb_mode", f"1 0 {r} {g} {b} 0\n"):
                return f"🎨 Klavye rengi '{renk_adi.upper() if renk_adi else hex_code}' yapıldı."

        try:
            subprocess.run(["openrgb", "--mode", "static", "--color", hex_code], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"🎨 Klavye rengi #{hex_code} yapıldı (OpenRGB)."
        except Exception:
            pass

        alt_paths = glob.glob("/sys/class/leds/*::kbd_backlight*") + glob.glob("/sys/devices/platform/asus-nb-wmi/leds/*rgb*")
        for p in alt_paths:
            if _write_sysfs(os.path.join(p, "brightness"), "255"):
                return f"🎨 Klavye aydınlatması tetiklendi (#{hex_code})."

        return f"🎨 Klavye rengi #{hex_code} uygulandı."

    @staticmethod
    def set_brightness(level: int) -> str:
        level = max(0, min(3, level))
        if os.path.isdir(ASUS_KBD_ROOT):
            _write_sysfs(f"{ASUS_KBD_ROOT}/brightness", f"{level}\n")
            return f"💡 Klavye parlaklığı {level} yapıldı."
        return f"💡 Parlaklık {level} seviyesine ayarlandı."

def read_cpu_temperature() -> str:
    for zone in sorted(glob.glob("/sys/class/thermal/thermal_zone*/type")):
        try:
            with open(zone) as fh:
                if any(x in fh.read().strip().lower() for x in ["cpu", "x86_pkg_temp", "soc"]):
                    with open(zone.replace("/type", "/temp")) as tfh:
                        temp = int(tfh.read().strip()) / 1000
                        return f"🔥 CPU Sıcaklığı: {temp:.1f}°C"
        except Exception: continue
    return "⚠️ CPU sıcaklığı okunamadı."

def read_fan_rpm() -> str:
    speeds = []
    for fan_input in sorted(glob.glob("/sys/class/hwmon/hwmon*/fan*_input")):
        try:
            with open(fan_input) as fh:
                val = fh.read().strip()
                if val.isdigit(): speeds.append(int(val))
        except Exception: continue
    if speeds:
        return "❄️ Fan Hızları: " + ", ".join([f"Fan {i+1}: {rpm} RPM" for i, rpm in enumerate(speeds)])
    return "⚠️ Aktif fan devir sensörü okunamadı."

COLOR_DICTIONARY = {
    "mavi": (0, 0, 255), "açık mavi": (173, 216, 230), "koyu mavi": (0, 0, 139),
    "lacivert": (0, 0, 128), "camgöbeği": (0, 255, 255), "turkuaz": (64, 224, 208),
    "yeşil": (0, 255, 0), "açık yeşil": (144, 238, 144), "kırmızı": (255, 0, 0),
    "turuncu": (255, 165, 0), "sarı": (255, 255, 0), "mor": (128, 0, 128),
    "pembe": (255, 192, 203), "beyaz": (255, 255, 255), "gri": (128, 128, 128)
}

# --------------------------------------------------------------------------
# 2. HİBRİT AI SİSTEMİ (Hava Durumu ve Arama Düzeltmesi)
# --------------------------------------------------------------------------
def hava_durumu_getir(sehir: str) -> str:
    try:
        url = f"https://wttr.in/{urllib.parse.quote(sehir)}?format=%C+%t"
        res = requests.get(url, headers={"User-Agent": "curl"}, timeout=3)
        if res.status_code == 200:
            return f"🌤️ {sehir.capitalize()} Hava Durumu: {res.text.strip()}"
    except Exception:
        pass
    return ""

def internette_ara(sorgu: str) -> str:
    if not sorgu: return ""
    sorgu_lower = sorgu.lower()

    # Eğer hava durumu soruluyorsa doğrudan güvenli API'yi kullan
    if "hava" in sorgu_lower or "derece" in sorgu_lower or "sıcaklık" in sorgu_lower:
        sehir = DEFAULT_CITY
        for kelime in ["afyon", "istanbul", "ankara", "izmir", "bursa", "antalya"]:
            if kelime in sorgu_lower:
                sehir = kelime
                break
        hw = hava_durumu_getir(sehir)
        if hw: return hw

    try:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        res = requests.post("https://html.duckduckgo.com/html/", headers={"User-Agent": ua}, data={"q": sorgu}, timeout=3)
        if res.status_code == 200:
            snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', res.text, re.DOTALL | re.IGNORECASE)
            clean_list = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s)).strip() for s in snippets[:3]]
            if clean_list: return "\n".join(f"• {item}" for item in clean_list)
    except Exception:
        pass
    return ""

def hibrit_cevap_al(messages_list: list) -> str:
    system_instruction = "Adın SYDRA. Sen samimi, akıllı, yardımsever ve detaylı Türkçe yanıtlar veren bir yapay zeka asistanısın."

    if GROQ_API_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            full_messages = [{"role": "system", "content": system_instruction}] + messages_list
            payload = {"model": "llama-3.3-70b-versatile", "messages": full_messages, "max_tokens": 800, "temperature": 0.6}
            res = requests.post(url, headers=headers, json=payload, timeout=5)
            if res.status_code == 200:
                return res.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass

    try:
        ollama_messages = [{"role": "system", "content": system_instruction}] + messages_list
        payload = {"model": OLLAMA_MODEL, "messages": ollama_messages, "stream": False}
        res = requests.post(OLLAMA_URL, json=payload, timeout=10)
        if res.status_code == 200:
            return f"🏠 *(Yerel Mistral)*\n" + res.json()["message"]["content"].strip()
    except Exception:
        pass

    return "⚠️ Hem bulut servisine hem de yerel modele ulaşılamadı."

def sesli_konusmayi_durdur():
    try:
        if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
    except Exception:
        pass

async def _async_text_to_speech(metin: str):
    temiz_metin = re.sub(r"[*#`_]", "", metin)
    if not temiz_metin: return
    try:
        voice = "tr-TR-AhmetNeural"
        communicate = edge_tts.Communicate(temiz_metin, voice)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tf:
            temp_filename = tf.name
        await communicate.save(temp_filename)
        if pygame.mixer.get_init() is None: pygame.mixer.init()
        pygame.mixer.music.load(temp_filename)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
        pygame.mixer.music.unload()
        os.remove(temp_filename)
    except Exception:
        pass

def sesli_cevap_ver(metin: str):
    try:
        asyncio.run(_async_text_to_speech(metin))
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(_async_text_to_speech(metin))
        except Exception:
            pass

def sesli_komut_dinle() -> str:
    if sr is None: return ""
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 250
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.4)
            audio = recognizer.listen(source, timeout=4, phrase_time_limit=8)
        return recognizer.recognize_google(audio, language="tr-TR")
    except Exception:
        return ""

def akilli_niyet_analizi(metin: str):
    m = metin.lower().strip()
    if "güç tasarrufu" in m or "tasarruf" in m:
        return guc_tasarrufu_modu(not ("kapat" in m or "iptal" in m))
    if "performans" in m:
        return performans_modu(not ("kapat" in m or "iptal" in m))

    for renk_adi, rgb in COLOR_DICTIONARY.items():
        parca = renk_adi[:3]
        if renk_adi in m or parca in m:
            return KeyboardControl.set_color_rgb(rgb[0], rgb[1], rgb[2], renk_adi)

    hex_m = re.search(r'#?([0-9a-fA-F]{6})', metin)
    if hex_m:
        h = hex_m.group(1)
        return KeyboardControl.set_color_rgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), f"#{h}")

    if any(k in m for k in ["parlaklık", "ışık"]):
        if any(k in m for k in ["kıs", "azalt", "1"]): return KeyboardControl.set_brightness(1)
        if any(k in m for k in ["kapat", "söndür", "0"]): return KeyboardControl.set_brightness(0)
        if any(k in m for k in ["orta", "2"]): return KeyboardControl.set_brightness(2)
        if any(k in m for k in ["aç", "yüksek", "max", "3"]): return KeyboardControl.set_brightness(3)

    if "fan" in m: return read_fan_rpm()
    if "sıcaklık" in m or "cpu" in m: return read_cpu_temperature()
    return ("ASYNC_PROCESS", metin)

# --------------------------------------------------------------------------
# 3. SATÜRN VISUALIZER
# --------------------------------------------------------------------------
class SaturnParticle:
    def __init__(self, is_ring=True, center_x=220, center_y=400):
        self.is_ring = is_ring
        self.state = "orbit"
        self.angle = random.uniform(0, 2 * math.pi)
        self.cx, self.cy = center_x, center_y
        if self.is_ring:
            self.radius = random.uniform(80, 140)
            self.speed = random.uniform(0.015, 0.035)
            self.tilt_y = 0.35
            self.size = random.uniform(2, 3.5)
            self.color = (52, random.randint(180, 255), 255)
        else:
            self.radius = random.uniform(10, 55)
            self.speed = random.uniform(0.01, 0.025)
            self.tilt_y = 0.8
            self.size = random.uniform(2, 4)
            self.color = (0, random.randint(120, 220), random.randint(220, 255))
        self.x, self.y = 0, 0
        self.scatter_x, self.scatter_y = 0, 0

    def scatter(self):
        self.state = "scattered"
        dist = random.uniform(180, 350)
        sa = random.uniform(0, 2 * math.pi)
        self.scatter_x = self.cx + math.cos(sa) * dist
        self.scatter_y = self.cy + math.sin(sa) * dist

    def recall(self):
        if self.state == "scattered": self.state = "returning"

    def update(self, cx, cy):
        self.cx, self.cy = cx, cy
        self.angle += self.speed
        tx = self.cx + math.cos(self.angle) * self.radius
        ty = self.cy + math.sin(self.angle) * (self.radius * self.tilt_y)
        if self.state == "orbit":
            self.x, self.y = tx, ty
        elif self.state == "scattered":
            self.x += (self.scatter_x - self.x) * 0.1
            self.y += (self.scatter_y - self.y) * 0.1
        elif self.state == "returning":
            self.x += (tx - self.x) * 0.08
            self.y += (ty - self.y) * 0.08
            if math.hypot(tx - self.x, ty - self.y) < 5: self.state = "orbit"

    def draw(self, screen):
        depth = math.sin(self.angle)
        af = 0.6 + 0.4 * depth
        pygame.draw.circle(screen, (int(self.color[0]*af), int(self.color[1]*af), int(self.color[2]*af)), (int(self.x), int(self.y)), int(self.size))

class SaturnOrb:
    def __init__(self, count=280, cx=220, cy=400):
        self.cx, self.cy = cx, cy
        self.particles = [SaturnParticle(is_ring=(i % 3 != 0), center_x=cx, center_y=cy) for i in range(count)]
        self.pulse = 0.0

    def explode(self):
        for p in random.sample(self.particles, int(len(self.particles) * 0.6)): p.scatter()

    def recall(self):
        for p in self.particles: p.recall()

    def update(self):
        self.pulse += 0.05
        for p in self.particles: p.update(self.cx, self.cy)

    def draw(self, screen):
        gs = int(14 + math.sin(self.pulse) * 3)
        g_surf = pygame.Surface((gs * 4, gs * 4), pygame.SRCALPHA)
        pygame.draw.circle(g_surf, (52, 200, 255, 30), (gs * 2, gs * 2), gs * 2)
        pygame.draw.circle(g_surf, (52, 200, 255, 75), (gs * 2, gs * 2), gs)
        screen.blit(g_surf, (self.cx - gs * 2, self.cy - gs * 2))
        for p in self.particles: p.draw(screen)
        pygame.draw.circle(screen, (220, 245, 255), (self.cx, self.cy), 5)

# --------------------------------------------------------------------------
# 4. SYDRA APP
# --------------------------------------------------------------------------
class SydraApp:
    def __init__(self):
        info = pygame.display.Info()
        global WIDTH, HEIGHT
        WIDTH, HEIGHT = info.current_w, info.current_h
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        pygame.display.set_caption("🤖 SYDRA - Smart Control Center")

        self.clock = pygame.time.Clock()
        self.font_title = pygame.font.Font(None, 32)
        self.font_small = pygame.font.Font(None, 22)

        self.orb = SaturnOrb(count=280, cx=220, cy=HEIGHT // 2)
        self.chat_history = ChatHistoryManager.yukle()

        self.input_text = ""
        self.is_loading = False
        self.scroll_offset = 0
        self.total_chat_height = 0

        self.hotword_active = False
        self.voice_status = "💤 Uyku Modunda (F1 ile Uyar, F3 ile İptal)"

        Thread(target=self._background_hotword_listener, daemon=True).start()

    def add_message(self, role, message):
        self.chat_history.append({"role": role, "message": message})
        ChatHistoryManager.kaydet(self.chat_history)

    def send_message(self, user_msg=""):
        msg = user_msg if user_msg else self.input_text.strip()
        if not msg or self.is_loading: return

        self.add_message("Siz", msg)
        if not user_msg: self.input_text = ""
        self.is_loading = True
        self.orb.explode()

        sistem_yaniti = akilli_niyet_analizi(msg)
        if isinstance(sistem_yaniti, str):
            self.add_message("SYDRA", sistem_yaniti)
            sesli_cevap_ver(sistem_yaniti)
            self.is_loading = False
            self.orb.recall()
            return

        if isinstance(sistem_yaniti, tuple) and sistem_yaniti[0] == "ASYNC_PROCESS":
            Thread(target=self._async_ai_task, args=(sistem_yaniti[1], list(self.chat_history)), daemon=True).start()

    def _async_ai_task(self, metin, history):
        m_lower = metin.lower()
        zorunlu_ara = "?" in metin or "araştır" in m_lower or "google" in m_lower or "kaç derece" in m_lower or "hava" in m_lower

        web_bilgi = ""
        if zorunlu_ara:
            temiz_sorgu = re.sub(r"araştır|google|baksana|bul|kaç derece|şu an", "", metin, flags=re.IGNORECASE).strip()
            web_bilgi = internette_ara(temiz_sorgu if temiz_sorgu else metin)

        messages_for_api = [{"role": "user" if x["role"] == "Siz" else "assistant", "content": x["message"]} for x in history[-6:]]
        if web_bilgi:
            messages_for_api.append({"role": "user", "content": f"Soru: {metin}\nGüncel Bilgi:\n{web_bilgi}"})
        else:
            messages_for_api.append({"role": "user", "content": metin})

        res = hibrit_cevap_al(messages_for_api)
        if web_bilgi and not "🌐" in res and not "🌤️" in res:
            res = f"🌐 **Güncel Bilgi:**\n{web_bilgi}\n\n{res}"

        self.add_message("SYDRA", res)
        sesli_cevap_ver(res)
        self.is_loading = False
        self.orb.recall()

    def _background_hotword_listener(self):
        while True:
            if self.hotword_active and not self.is_loading:
                self.voice_status = "🎙️ 'Asus' veya 'Sydra' bekleniyor..."
                komut = sesli_komut_dinle()
                if komut:
                    k_lower = komut.lower()
                    tetikleyiciler = [
                        "sydra", "sitra", "sidra", "südra", "sitara", "sıla", "seda",
                        "asus", "asuz", "asur", "as", "ass", "asiz", "hazis", "a sus", "asüs"
                    ]

                    if any(w in k_lower for w in tetikleyiciler):
                        self.voice_status = "✨ Dinliyorum, buyurun..."
                        sesli_cevap_ver("Efendim?")

                        while self.hotword_active:
                            self.voice_status = "🗣️ Komut bekleniyor..."
                            takip_komutu = sesli_komut_dinle()

                            if takip_komutu:
                                tk_lower = takip_komutu.lower()

                                if any(c in tk_lower for c in ["iptal et", "durdur", "sus", "kapat", "yeter", "tamamdır"]):
                                    sesli_konusmayi_durdur()
                                    sesli_cevap_ver("Tamamdır, sustum.")
                                    self.is_loading = False
                                    self.orb.recall()
                                    break

                                self.voice_status = "⚡ İşleniyor..."
                                self.send_message(takip_komutu)

                                while self.is_loading:
                                    time.sleep(0.1)
                            else:
                                break
            else:
                self.voice_status = "💤 Uyku Modunda (F1 ile Uyar, F3 ile İptal)"
            time.sleep(0.3)

    def wrap_text(self, text, font, max_width):
        lines = []
        for p in text.split('\n'):
            current_line = ""
            for word in p.split(' '):
                test_line = current_line + word + " "
                if font.size(test_line)[0] <= max_width: current_line = test_line
                else:
                    if current_line: lines.append(current_line.strip())
                    current_line = word + " "
            if current_line: lines.append(current_line.strip())
        return lines

    def draw_ui(self):
        chat_x = 440
        chat_w = WIDTH - 460

        pygame.draw.rect(self.screen, (16, 19, 26), (chat_x - 20, 0, WIDTH - (chat_x - 20), HEIGHT))

        self.screen.blit(self.font_title.render("🤖 SYDRA Smart Control Center", True, (52, 200, 255)), (chat_x, 20))

        status_bg = (20, 60, 40) if self.hotword_active else (40, 40, 50)
        status_border = (0, 255, 120) if self.hotword_active else (100, 100, 100)
        pygame.draw.rect(self.screen, status_bg, (WIDTH - 370, 15, 350, 32), border_radius=6)
        pygame.draw.rect(self.screen, status_border, (WIDTH - 370, 15, 350, 32), 1, border_radius=6)
        self.screen.blit(self.font_small.render(self.voice_status, True, (240, 240, 240)), (WIDTH - 360, 23))

        chat_area = pygame.Rect(chat_x, 70, chat_w, HEIGHT - 140)
        self.screen.set_clip(chat_area)

        y_cursor = 80 - self.scroll_offset
        max_box_width = chat_w - 40

        for msg in self.chat_history:
            role, text = msg["role"], msg["message"]
            is_user = (role == "Siz")
            lines = self.wrap_text(text, self.font_small, max_box_width)
            if not lines: continue

            box_height = 25 + (len(lines) * 20) + 10
            box_rect = pygame.Rect(chat_x, y_cursor, max_box_width, box_height)

            bg_col = (32, 38, 50) if is_user else (24, 30, 42)
            border_col = (80, 140, 220) if is_user else (52, 200, 255)

            pygame.draw.rect(self.screen, bg_col, box_rect, border_radius=8)
            pygame.draw.rect(self.screen, border_col, box_rect, 1, border_radius=8)

            self.screen.blit(self.font_small.render(f"👤 {role}" if is_user else f"🤖 {role}", True, border_col), (chat_x + 12, y_cursor + 8))

            line_y = y_cursor + 32
            for line in lines:
                self.screen.blit(self.font_small.render(line, True, (220, 225, 235)), (chat_x + 12, line_y))
                line_y += 20

            y_cursor += box_height + 12

        self.total_chat_height = y_cursor + self.scroll_offset - 80
        self.screen.set_clip(None)

        bar_y = HEIGHT - 65
        pygame.draw.rect(self.screen, (22, 26, 35), (chat_x - 20, bar_y - 10, WIDTH - chat_x + 20, 75))
        pygame.draw.rect(self.screen, (52, 160, 255), (chat_x, bar_y, chat_w - 20, 48), 2, border_radius=8)

        txt = self.input_text if self.input_text else "Komut verin veya mesaj yazın (Örn: Turuncu yap, F3 ile sustur)..."
        txt_col = (255, 255, 255) if self.input_text else (120, 130, 145)
        self.screen.blit(self.font_small.render(txt, True, txt_col), (chat_x + 15, bar_y + 15))

        if self.is_loading:
            self.screen.blit(self.font_small.render("⚡ İşlem yapılıyor (İptal için F3)...", True, (52, 200, 255)), (chat_x, bar_y - 35))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.MOUSEWHEEL:
                max_scroll = max(0, self.total_chat_height - (HEIGHT - 200))
                self.scroll_offset -= event.y * 35
                self.scroll_offset = max(0, min(max_scroll, self.scroll_offset))
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    self.send_message()
                elif event.key == pygame.K_BACKSPACE:
                    self.input_text = self.input_text[:-1]
                elif event.key == pygame.K_F5:
                    self.chat_history = []
                    ChatHistoryManager.temizle()
                elif event.key == pygame.K_F1:
                    self.hotword_active = not self.hotword_active
                    durum = "Aktif (Asus/Sydra dinleniyor)" if self.hotword_active else "Kapatıldı"
                    self.add_message("SYDRA", f"F1 Uyandırma Modu {durum}")
                elif event.key == pygame.K_F3:
                    sesli_konusmayi_durdur()
                    self.is_loading = False
                    self.orb.recall()
                    self.voice_status = "🛑 İşlem İptal Edildi (F3)"
                    self.add_message("SYDRA", "İşlem durduruldu.")
                elif event.unicode.isprintable():
                    self.input_text += event.unicode
        return True

    def run(self):
        running = True
        while running:
            running = self.handle_events()
            self.orb.update()

            self.screen.fill((10, 13, 18))
            self.orb.draw(self.screen)
            pygame.draw.line(self.screen, (52, 160, 255), (420, 0), (420, HEIGHT), 2)

            self.draw_ui()
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()

if __name__ == "__main__":
    app = SydraApp()
    app.run()
