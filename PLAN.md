# Workshop taklifnoma boti — reja va workflow

## 1. Maqsad

Aiogram 3.x asosida faqat ruxsat berilgan administratorlar ishlata oladigan Telegram bot yaratiladi. Bot administrator kiritgan:

- ism-familiya;
- lead/ishtirokchi ID si;
- boshlanish vaqti;
- tadbir kuni/sanasi

bo‘yicha berilgan reference rasm ustiga individual workshop taklifnomasini avval deterministik algoritm bilan bepul chizadi va Telegram chatiga tayyor PNG sifatida qaytaradi. Faqat administrator bepul natijani tasdiqlamasa, Nano Banana Pro orqali pullik AI fallback ishga tushadi.

V1 bir taklifnomani bir vaqtda interaktiv tarzda yaratadi. CSV/Excel orqali ommaviy generatsiya keyingi bosqich sifatida qo‘shilishi mumkin.

## 2. Asosiy qarorlar

1. **Telegram qatlami:** `aiogram` 3.x va FSM (finite-state machine).
2. **Asosiy renderer:** Pillow orqali reference’dagi dinamik hududlarni deterministik to‘ldirish; bu bosqichda tashqi API chaqirilmaydi.
3. **AI fallback:** faqat admin alohida tasdiqlaganda Google Gemini Nano Banana Pro — `gemini-3-pro-image`; algoritm bilan bir xil `1080×1960` master reference va locked-canvas prompt ishlatiladi.
4. **API usuli:** `google-genai` Interactions API.
5. **Maxfiylik:** AI so‘rovlari Google tomonida saqlanmasligi uchun har bir chaqiriqda `store=False`.
6. **Reference:** `ticketbot/assets/invitation_reference.png` — paket va runtime ichidagi yagona nusxa; uslub, kompozitsiya, rang, ikonka va tipografik ierarxiya manbasi.
7. **Dinamik maydonlar:** faqat ism-familiya, ID, vaqt va sana o‘zgaradi. Sarlavha, logotip, manzil va ikonkalar o‘zgarmaydi.
8. **Chiqish:** algoritm yoki model natijasi `705×1280` PNG ga normalizatsiya qilinib, Telegram document sifatida yuboriladi.
9. **Saqlash:** lead ma’lumotlari va yaratilgan rasm diskka yozilmaydi; FSM xotirasida va `bytes` ko‘rinishida vaqtincha ishlatiladi.
10. **Human review:** admin bepul natijani tasdiqlaydi yoki ongli ravishda xarajatli AI fallback’ni tanlaydi.
11. **Sana/vaqt shortcut:** har bir adminning oxirgi valid sana va vaqti process xotirasida saqlanadi; keyingi draftda vaqt bosqichida `Bekor qilish` ustidagi tugma orqali ikkala qiymat birdan qo‘llanadi.
12. **Generatsiya animatsiyasi:** faqat AI javobi kutilayotganda bitta Telegram status xabari siklik edit qilinadi.

## 3. Reference dizayn talablari

Joriy reference rasm o‘lchami `1080×1960` px; yakuniy yuboriladigan PNG `705×1280` ga normalizatsiya qilinadi.

- Yuqori qism oq fon, chapda ko‘k-to‘q sariq logotip, o‘ngda uch qator sarlavha.
- Asosiy panel yumaloq yuqori burchakli ko‘k gradient.
- Oq ikonlar chap ustunda, qiymatlar va label lar o‘ngda.
- Asosiy qiymatlar Poppins/Montserrat ga o‘xshash qalin geometrik sans-serif shriftida.
- Pastda oq, yumaloq sana pill elementi.
- Asosiy ranglar: oq, to‘q ko‘k/kobalt gradient, logotip uchun ko‘k va to‘q sariq.

Prompt modelga reference dagi barcha invariant elementlarni saqlashni, eski demo qiymatlarni esa aynan yangi qiymatlar bilan almashtirishni buyuradi.

## 4. Uzun ism-familiya strategiyasi

Bot ism uzunligi va so‘zlar chegarasiga qarab layout ko‘rsatmasini avtomatik tanlaydi:

1. **Qisqa/normal ism:** bitta qatorda, reference dagi katta bold o‘lcham.
2. **Uzun ism:** font o‘lchamini proporsional kichraytirib, bitta qatorda sig‘dirishga urinish.
3. **Juda uzun ism:** so‘z oralig‘idan eng muvozanatli joyda ikki qatorga ajratish, ikkala qatorni markazlash.
4. **Favqulodda uzun ism:** maksimal uch qator; ism kesilmaydi, qisqartirilmaydi, gorizontal cho‘zilmaydi va harflar o‘zgartirilmaydi.

O‘zbekcha `O‘`, `G‘`, apostrof, tire va lotin/kirill harflari literal matn sifatida saqlanadi. Prompt ichidagi foydalanuvchi qiymatlari JSON bilan escape qilinadi va buyruq emas, oddiy ma’lumot deb belgilanadi.

## 5. Telegram bot workflow

```text
/start
  |
  +-- admin emas --> “Ruxsat yo‘q” va jarayon tugaydi
  |
  +-- admin --> “Taklifnoma yaratish” tugmasi
                   |
                   v
             Ism-familiya kiritish
                   |
                   v
                 ID kiritish
                   |
                   v
             Vaqt kiritish (HH:MM)
                   |
                   v
             Sana/kuni kiritish
                   |
                   v
              Tasdiqlash oynasi
              |                |
          Bekor qilish    Bepul algoritm
                               |
                    Template PNG yuborish
                         |              |
                    Tasdiqlash     AI bilan chizish
                         |              |
                       Tugadi    Nano Banana Pro API
                                        |
                                  AI PNG yuborish
                                  |            |
                            Yangi yaratish  AI qayta yaratish
```

Har bir FSM bosqichida `/cancel` yoki “Bekor qilish” tugmasi jarayonni tozalaydi. `/start` ham eski tugallanmagan state ni tozalab, bosh menyuni qayta ochadi.

## 6. Input validatsiyasi

- **Ism-familiya:** trim va ko‘p bo‘shliqlarni bitta bo‘shliqqa keltirish; nazorat belgilarini, emoji va yangi qatorlarni rad etish; oqilona maksimal uzunlik.
- **ID:** maksimum 20 belgi; faqat lotin harfi, raqam, tire va underscore; katta-kichik harf qiymati saqlanadi.
- **Vaqt:** qat’iy `HH:MM`, `00:00–23:59`.
- **Sana/kuni:** maksimum 36 belgi; foydalanuvchi ko‘rishni xohlagan tayyor matn, masalan `Shanba 15-avgust`; nazorat belgilari rad etiladi.
- Barcha qiymatlar tasdiqlashdan oldin administratorga qayta ko‘rsatiladi.

## 7. Xatoliklar va qayta urinish

- Bepul renderer tashqi tarmoqqa chiqmaydi va provider chaqirmaydi.
- AI tanlangandagina API timeout, vaqtinchalik 429/5xx va bo‘sh image response uchun chegaralangan retry ishlaydi.
- Bitta API chaqirig‘i event loop ni bloklamaydi; Google SDK ning async klienti ishlatiladi.
- Bir vaqtning o‘zida ketadigan generatsiyalar semaphore bilan chegaralanadi.
- Jarayon davomida Telegram `upload_document` chat action ko‘rsatiladi; AI kutishda siklik status animatsiyasi ishlaydi.
- Yakuniy rasm ochilmasa yoki noto‘g‘ri formatda bo‘lsa, yuborilmaydi va administratorga tushunarli xabar beriladi.
- Generativ model matnni xato yozishi mumkin; AI natijasida “AI bilan qayta yaratish” tugmasi shu draft bilan yana urinish imkonini beradi.

## 8. Xavfsizlik va konfiguratsiya

Sirlar kodga yozilmaydi. `.env` orqali:

- `BOT_TOKEN`;
- `GEMINI_API_KEY`;
- `ADMIN_IDS` — vergul bilan ajratilgan Telegram user ID lar;
- model, timeout, retry, concurrency, aspect ratio va image size sozlamalari.

`.env` Git ga kiritilmaydi, `.env.example` esa qiymatsiz namuna sifatida beriladi. Unauthorized user lar handler/FSM ga kiritilmaydi.

## 9. Rejalashtirilgan fayl tuzilmasi

```text
ticketbot/
├── PLAN.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── src/ticketbot/
│   ├── __main__.py
│   ├── app.py
│   ├── config.py
│   ├── keyboards.py
│   ├── middleware.py
│   ├── states.py
│   ├── assets/invitation_reference.png
│   ├── assets/fonts/Montserrat-Variable.ttf
│   ├── assets/fonts/OFL.txt
│   ├── handlers/admin.py
│   ├── models/invitation.py
│   └── services/
│       ├── generator.py
│       ├── image_processor.py
│       ├── nano_banana.py
│       ├── prompt_builder.py
│       └── template_renderer.py
└── tests/
    ├── test_config.py
    ├── test_generator.py
    ├── test_handlers.py
    ├── test_image_processor.py
    ├── test_invitation.py
    ├── test_middleware.py
    ├── test_nano_banana.py
    ├── test_prompt_builder.py
    └── test_template_renderer.py
```

## 10. Tekshiruv mezonlari

- Admin tekshiruvi va FSM ketma-ketligi to‘g‘ri ishlaydi.
- Noto‘g‘ri vaqt/ID/ism/sana qabul qilinmaydi.
- Prompt to‘rtta dinamik qiymatni aynan bir marta data manifestida beradi va invariantlarni o‘zgartirmaslikni talab qiladi.
- Qisqa, uzun, apostrof/tireli va Unicode ismlar uchun layout tanlovi test qilinadi.
- Template renderer dinamik hududlarni almashtirishi, statik header’ni saqlashi va AI provider’ni chaqirmasligi test qilinadi.
- Nano Banana response mock bilan muvaffaqiyat, bo‘sh response, timeout va retry test qilinadi.
- Rasm PNG ga normalizatsiya qilinadi va `705×1280` chiqish tekshiriladi.
- `ruff` va `pytest` muvaffaqiyatli o‘tadi.

## 11. Ish tartibi

1. Ushbu reja/workflow hujjatini yaratish.
2. Loyiha scaffoldi, konfiguratsiya va dependency larni qo‘shish.
3. Input model/validator va uzun ism layout algoritmini yozish.
4. Deterministik template renderer, Nano Banana Pro fallback va image post-processing qatlamini yozish.
5. Aiogram FSM, xarajatni tasdiqlash workflowi, admin middleware va keyboard larni ulash.
6. Unit testlar va mock API testlarini yozish.
7. Dependency larni o‘rnatib, lint/testlarni ishga tushirish.
8. Ishga tushirish bo‘yicha README va yakuniy handoff.

## 12. Muhim cheklov

Bepul renderer paketlangan Montserrat variable fonti va tasdiqlangan reference template placeholder’laridan o‘lchangan koordinata/spacing kalibratsiyasidan foydalanadi. Nano Banana Pro fallback generativ model bo‘lgani uchun har bir harfning 100% aniqligi kafolatlanmaydi; shu sabab AI faqat adminning ongli tanlovidan keyin chaqiriladi.
