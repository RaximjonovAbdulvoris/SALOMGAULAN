# WB SALOM Telegram bot

Python 3.11+ va python-telegram-bot 21.6.

## Ishga tushirish

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-ocr.txt
cp .env.example .env
# .env ichiga BotFather tokenini kiriting.
mkdir -p runtime
set -a
. ./.env
set +a
python -m bot.main
```

Hostingda Build command: `pip install -r requirements.txt`.
Start command: `python -m bot.main`. Bot long polling bilan ishlaydi:
bitta token uchun faqat bitta process/worker ishlating. HTTP port talab
qiluvchi web service o'rniga background worker ishlating.

Hosting environment sozlamalariga `.env.example` dagi qiymatlar va
`TELEGRAM_BOT_TOKEN` ni kiriting. `.env` avtomatik o'qilmaydi.
`PERSIST_DIR` mavjud, yozish mumkin bo'lgan doimiy disk papkasi bo'lsin.
GitHub orqali token va eski bot holati tarqatilmaydi.

## Guruhlardagi boshqaruv

- Arizalar 01 va 02 guruhlariga navbat bilan tushadi.
- Asosiy guruhlar: Tayyor, Chala rasm, Boshqa park, Jarayonda.
- Chala rasm / Boshqa park: Tayyor, O'chirish, Jarayonda.
- Jarayonda avval qizil, bosilganda sariq; boshqa guruhga o'tganda qizil.
- Tayyor: arxivga tugmalarsiz ko'chirish, keyin eski xabarlarni o'chirish.
- O'chirish: maxsus guruhdagi arizani arxivlamasdan o'chirish.
- To'liq ko'chirish tasdiqlanmasa, asl ariza o'chirilmaydi.
- Bot barcha tegishli guruhlarda xabar/rasm yuborish va xabarlarni o'chirish
  huquqiga ega bo'lishi kerak. Telegram eski xabarlarni o'chirishni cheklashi mumkin.

## Tekshirish

```bash
set -a
. ./.env
set +a
python -m unittest discover -s tests -v
```

Testlar Telegramga ulanmaydi. Ommaviy ishga tushirishdan oldin har ikkala
asosiy guruhga sinov arizasi yuborib, Chala rasm, Boshqa park, Jarayonda,
Tayyor va O'chirish yo'llarini haqiqiy guruhlarda tekshiring.

## SALOM yo'nalishlari

Haydovchi arizalari ikki guruhga navbat bilan yuboriladi. Brend va Spectre
arizalari alohida guruhlarga oddiy xabar sifatida tushadi; Google Sheets
integratsiyasi yo'q. Haydovchi hujjatlari mahalliy RapidOCR bilan o'qiladi;
OCR natijasini operator hujjatlar bilan solishtirishi kerak. ZIP faylni yuklash,
Chala rasm, Boshqa park, Jarayonda va arxiv funksiyalari mavjud.

`.env.example` dagi guruh IDlari SALOM uchun; tokenni faqat serverdagi
`.env` faylga kiriting. `python -m bot.configure check` orqali
guruh huquqlarini tekshiring. Botni ishga tushirishdan oldin shu token bilan
ishlayotgan boshqa jarayonni to'xtating.

VPSga o‘rnatishda `bash scripts/deploy_vps.sh` ishlating. Script tokenni
ekranda ko‘rsatmasdan so‘raydi, guruh huquqlari va OCRni tekshiradi, shundan
keyin `salomgaulan.service` ni yoqadi. U `/root/SALOMGAULAN` papkasida
ishlaydi. Kod yangilanganda scriptni qayta ishlatish mumkin.
