# 🤖 SYDRA — Smart Control Center

SYDRA is a fullscreen desktop AI assistant built with `pygame`, featuring a live animated "Saturn" particle orb visualizer, a interactive chat interface, English voice input/output (via `SpeechRecognition` + `edge-tts`), multilingual text response capabilities, real-time web search capabilities, and hardware controls tailored for ASUS laptops on Linux (keyboard RGB, brightness, fan speed, CPU temperature, power profiles).

It uses a hybrid AI backend: it first tries the [Groq](https://groq.com) cloud API (Llama 3.3 70B) for ultra-fast responses and gracefully falls back to a local [Ollama](https://ollama.ai) model (`qwen2.5:1.5b` by default) if the cloud call fails or no API key is provided.

---

## 🌟 Key Features

- 🎙️ **English Voice Wake-word:** Hands-free listening ("Sydra" / "Asus") with follow-up voice command processing (`en-US` speech recognition & `edge-tts`).
- 💬 **Multilingual Text Chat:** Persistent chat history (`chat_history.json`) with an AI engine that automatically responds in the exact language of your prompt.
- 🌐 **Real-Time Web & Weather Integration:** Append a `?` to any message or use keywords (`search`, `google`, `find`, `weather`) to fetch real-time web results from DuckDuckGo and live weather reports from `wttr.in`.
- 🔄 **Dynamic Model Switching:** Switch local Ollama models on the fly directly inside the chat bar using the `/model <model_name>` command.
- ⌨️ **ASUS Hardware & RGB Control:** Native Linux controls for keyboard RGB lighting (colors, hex codes, brightness), with an OpenRGB fallback for non-ASUS setups.
- 🔋 **Power Profile Management:** Toggle system power profiles (`performance`, `balanced`, `power-saver`).
- 🌡️ **Hardware Monitoring:** Read real-time CPU temperatures and active fan speeds (RPM) via Linux `sysfs`/`hwmon`.
- 🌌 **Reactive Particle Visualizer:** Interactive "Saturn orb" particle animation that reacts dynamically when SYDRA is thinking or talking.

---

## 🔑 1. How to Get a Free Groq API Key

Groq provides extremely fast cloud inference (Llama 3.3 70B) with a generous free tier.

1. Go to [https://console.groq.com/keys](https://console.groq.com/keys).
2. Sign in with your Google or GitHub account.
3. Click **"Create API Key"**.
4. Give your key a name (e.g., `sydra-key`) and click **"Create API Key"**.
5. Copy the key (it starts with `gsk_...`).
6. Paste it into your `.env` file under `GROQ_API_KEY`.

---

## 🦙 2. How to Install & Configure Ollama (Local LLM)

Ollama runs open-source models locally on your system. It works seamlessly as SYDRA's offline fallback engine.

### Step A: Install Ollama on Linux
Open your terminal and run:
```bash
curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh
