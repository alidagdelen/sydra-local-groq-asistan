# 🤖 SYDRA — Smart Control Center

SYDRA is a fullscreen desktop AI assistant built with `pygame`, featuring a live
animated "Saturn" orb visualizer, a chat interface, Turkish voice input/output
(via `SpeechRecognition` + `edge-tts`), and hardware controls tailored for
ASUS laptops on Linux (keyboard RGB, brightness, fan speed, CPU temperature,
power profiles).

It uses a hybrid AI backend: it first tries the [Groq](https://groq.com) cloud
API (Llama 3.3 70B) and falls back to a local [Ollama](https://ollama.ai)
model (Mistral by default) if the cloud call fails or no API key is set.

> **Note:** SYDRA's assistant persona and voice responses are in **Turkish**
> (`Adın SYDRA...` system prompt, `tr-TR` speech recognition/TTS voices). The
> code and comments have been kept bilingual — feel free to fork and adapt the
> prompt/voice locale to your own language.

## Features

- 🎙️ Turkish voice wake-word listening ("Sydra" / "Asus") with follow-up
  voice commands
- 💬 Text chat with persistent history (`chat_history.json`)
- ⌨️ ASUS keyboard RGB control (color names, hex codes, brightness levels),
  with an OpenRGB fallback for non-ASUS setups
- 🔋 Power profile switching (performance / balanced / power-saver)
- 🌡️ CPU temperature and fan RPM readouts (Linux `sysfs`/`hwmon`)
- 🌤️ Weather lookups (`wttr.in`) and lightweight web search fallback
- 🌌 Animated particle "Saturn orb" visualizer that reacts to conversation
  state

## Requirements

- Linux (the hardware controls use Linux-specific paths — `sysfs`,
  `hwmon`, `powerprofilesctl`, `brightnessctl`, ASUS `asus-nb-wmi`
  driver). It will still run on other platforms, but hardware/keyboard
  features will silently no-op.
- Python 3.10+
- A [Groq API key](https://console.groq.com/keys) (free tier available), and/or
  a local [Ollama](https://ollama.ai) install with a pulled model, as fallback

## Setup

```bash
git clone https://github.com/<your-username>/sydra.git
cd sydra

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# then edit .env and add your GROQ_API_KEY
```

Run it:

```bash
python sydra_app.py
```

## Keybindings

| Key     | Action                                  |
|---------|------------------------------------------|
| `Enter` | Send typed message                        |
| `F1`    | Toggle voice wake-word listening          |
| `F3`    | Cancel current speech/response            |
| `F5`    | Clear chat history                        |
| Scroll  | Scroll chat history                       |

## Configuration

All secrets and tunables are read from environment variables (see
`.env.example`):

| Variable             | Default                              | Description                    |
|----------------------|---------------------------------------|---------------------------------|
| `GROQ_API_KEY`       | *(empty)*                             | Groq cloud API key              |
| `OLLAMA_URL`         | `http://localhost:11434/api/chat`     | Local Ollama endpoint           |
| `OLLAMA_MODEL`       | `mistral`                             | Local fallback model name       |
| `SYDRA_DEFAULT_CITY` | `Afyon`                               | Default city for weather lookup |

## Notes on ASUS hardware controls

Keyboard RGB and brightness control write to
`/sys/devices/platform/asus-nb-wmi/leds/asus::kbd_backlight`. On non-ASUS
hardware, or if that path isn't present, SYDRA falls back to `openrgb` if
installed, then gives up gracefully. Some actions (`powerprofilesctl`,
writing to `sysfs`) may prompt for a `pkexec` password depending on your
system's polkit rules.

## License

MIT — see [LICENSE](LICENSE).
