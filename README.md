# Workshop invitation Telegram bot

Aiogram 3.x bot administrator kiritgan ism-familiya, ID, vaqt va sana asosida workshop uchun shaxsiy taklifnoma yaratadi. Birinchi natija reference template ustiga deterministik algoritm bilan bepul chiziladi. Faqat administrator bu natijani rad etib, alohida tugmani bosganda Google Gemini **Nano Banana Pro** (`gemini-3-pro-image`) ishlatiladi.

Batafsil arxitektura va Telegram workflow: [PLAN.md](PLAN.md).

## Imkoniyatlar

- `ADMIN_IDS` allowlist orqali admin-only foydalanish;
- aiogram FSM: ism → ID → vaqt → sana → tasdiqlash;
- `HH:MM`, ID, Unicode ism va sana input validatsiyasi;
- uzun ism uchun avtomatik 1/2/3 qatorli layout ko‘rsatmasi;
- har bir admin uchun oxirgi sana/vaqtni bot ishlayotgan davrda eslab qolish va yangi draftda bir bosishda qayta ishlatish;
- birinchi urinishda Pillow template renderer — hech qanday AI/API xarajatisiz;
- bepul natijani tasdiqlash yoki faqat zarur bo‘lsa `AI bilan qayta chizish`;
- AI fallback’ga ham aynan paketlangan `1080×1960` master template yuboriladi; prompt faqat to‘rtta value maskni ochiq qoldirib, qolgan canvasni locked deb belgilaydi;
- Nano Banana Pro Interactions API, async client va `store=False`;
- timeout, chegaralangan retry va parallel generatsiya limiti;
- generatsiya vaqtida bitta Telegram xabarida siklik progress animatsiyasi;
- yakuniy natijani metadata siz `705×1280` PNG ga normalizatsiya qilish;
- natijani qayta generatsiya qilish yoki yangi lead boshlash;
- lead ma’lumotlari va rasmlarni diskka saqlamaslik.

## Talablar

- Python 3.11–3.14;
- Telegram BotFather token;
- Google AI Studio/Gemini API key va `gemini-3-pro-image` modeliga access.

## O‘rnatish

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
```

`.env` ni to‘ldiring:

```dotenv
BOT_TOKEN=123456789:telegram-token
GEMINI_API_KEY=your-gemini-api-key
ADMIN_IDS=111111111,222222222
```

API key yoki bot tokenni chatga, Git ga yoki logga joylamang. `ADMIN_IDS` — Telegram foydalanuvchisining numeric ID si; username emas.

## Ishga tushirish

```powershell
python -m ticketbot
```

yoki editable install dan keyin:

```powershell
workshop-invitation-bot
```

Botda `/start` yuboring va **Taklifnoma yaratish** tugmasini bosing. Istalgan bosqichda `/cancel` bilan draftni tozalash mumkin.

## Tekshiruv

```powershell
python -m ruff check .
python -m pytest
```

Testlar real Telegram yoki Gemini API ga ulanmaydi; Nano Banana chaqirig‘i mock qilinadi.

## Konfiguratsiya

| Variable | Default | Vazifa |
|---|---:|---|
| `BOT_TOKEN` | required | Telegram bot token |
| `GEMINI_API_KEY` | required | Gemini API key |
| `ADMIN_IDS` | required | Vergul bilan ajratilgan admin user ID lar |
| `GEMINI_IMAGE_MODEL` | `gemini-3-pro-image` | Nano Banana Pro stable model ID |
| `GEMINI_IMAGE_SIZE` | `2K` | `1K`, `2K` yoki `4K` |
| `GEMINI_IMAGE_ASPECT_RATIO` | `9:16` | Model output aspect ratio |
| `REFERENCE_IMAGE_PATH` | bundled reference | Optional external reference template |
| `OUTPUT_IMAGE_WIDTH` | `705` | Yakuniy PNG eni |
| `OUTPUT_IMAGE_HEIGHT` | `1280` | Yakuniy PNG bo‘yi |
| `GENERATION_TIMEOUT_SECONDS` | `240` | Har bir API urinish timeouti |
| `GENERATION_MAX_ATTEMPTS` | `2` | Vaqtinchalik xato uchun urinishlar |
| `MAX_CONCURRENT_GENERATIONS` | `2` | Parallel model chaqiriqlari |
| `LOG_LEVEL` | `INFO` | Log darajasi |

## Reference ni almashtirish

Tasdiqlangan yangi PNG yo‘lini `.env` dagi `REFERENCE_IMAGE_PATH` ga yozing. Qiymat bo‘sh qolsa, paket ichidagi reference ishlatiladi. Bepul renderer template ichidagi to‘rtta dinamik hududni — ism, ID, vaqt va sanani — algoritmik almashtiradi. Yangi reference shu layout va proporsiyani saqlashi kerak; joylashuv o‘zgarsa `template_renderer.py` koordinatalari ham moslanadi.

AI fallback ham shu faylning aynan o‘zini reference sifatida yuboradi. Prompt logo, header, gradient, ikonka, manzil, helper label’lar va date pill’ni locked deb belgilaydi; modelga faqat ism, ID, vaqt va sana qiymatlari joylashgan masklarda tahrir qilishga ruxsat beriladi.

Deterministik renderer paket ichidagi ochiq litsenziyali Montserrat variable fontidan foydalanadi, matnni adaptive kichraytiradi va uzun ismni 2–3 qatorga bo‘ladi. Shu sabab natija server operatsion tizimidagi fontlarga bog‘liq emas. Font litsenziyasi `ticketbot/assets/fonts/OFL.txt` ichida. Generativ variant faqat admin **AI bilan qayta chizish** tugmasini bosganda chaqiriladi.

## Maxfiylik

Gemini Interactions API odatda server-side state saqlashi mumkin. Ushbu bot har bir generatsiyada `store=False` yuboradi. Botning o‘zi lead ma’lumotlari yoki tayyor rasmlarni doimiy disk/storage ga yozmaydi; ular faqat joriy FSM xotirasida va yuborish vaqtida RAM da turadi.

## Rasm provayderi bo‘yicha manbalar

- [Gemini image generation](https://ai.google.dev/gemini-api/docs/image-generation)
- [Gemini 3 Pro Image model](https://ai.google.dev/gemini-api/docs/models/gemini-3-pro-image)
- [Interactions API migration](https://ai.google.dev/gemini-api/docs/migrate-to-interactions)
- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/)
