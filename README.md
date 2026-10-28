# Daily Gold Price → LINE

ระบบสร้างภาพราคาทองคำแท่ง **ประกาศครั้งที่ 1 ของวัน** ตามดีไซน์ Canva 1080×1080 และส่งผ่าน LINE Messaging API โดยอัตโนมัติทุกวันจันทร์–เสาร์ ช่วงเวลา 09:10–09:40 น. (Asia/Bangkok) โดยลองทุก 5 นาทีจนส่งสำเร็จ

## สิ่งที่ทำให้แล้ว

- ดึงประกาศครั้งที่ 1 จากหน้าการปรับเปลี่ยนระหว่างวันของสมาคมค้าทองคำ
- สำรองด้วย `ราคาทองคำวันนี้.com` หากแหล่งหลักใช้งานไม่ได้
- ตรวจวันที่ตามเขตเวลาไทย ป้องกันหยิบข้อมูลค้างจากวันก่อน
- retry 5 รอบ ทุก 5 นาที หากประกาศแรกมาช้ากว่า 09:10 น.
- render วันที่ เวลา รับซื้อ ขายออก สถานะ ตัวเลข และลูกศร
- รองรับ `ขึ้น`, `ลง` และกรณีพิเศษ `คงที่` เพื่อไม่รายงานข้อมูลผิด
- เก็บภาพ 5 วันล่าสุดบน branch `gold-price-images` พร้อมป้องกันการส่ง LINE ซ้ำด้วย receipt
- มี unit test สำหรับ parser, renderer และ LINE payload

## ฟอนต์และ Canva

- `Anantason` อยู่ในองค์ประกอบคงที่ของภาพ Canva และ **bake อยู่ใน `template_clean.png` แล้ว** จึงไม่แจกจ่ายไฟล์ฟอนต์เชิงพาณิชย์ในโปรเจกต์นี้
- ข้อมูลที่เปลี่ยนทุกวันใช้ `Noto Sans Thai` ตามต้นฉบับ และรวมไฟล์ฟอนต์ภายใต้ SIL Open Font License ไว้แล้ว
- ขนาด สี ตำแหน่ง และ drop shadow อยู่ใน `assets/style_spec.json`

ไฟล์สำหรับตรวจเทียบ:

- `assets/reference_up.png`
- `assets/reference_down.png`
- `assets/template_guide.png`
- `assets/template_clean.png`

## ทดสอบในเครื่อง

ต้องมี Python 3.11 ขึ้นไป

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest

python -m gold_bot render-demo --state up --output generated/demo-up.png
python -m gold_bot render-demo --state down --output generated/demo-down.png
python -m gold_bot render-demo --state neutral --output generated/demo-neutral.png
```

ทดสอบดึงข้อมูลจริง:

```bash
python -m gold_bot fetch-render --retries 1 --retry-delay 0
```

ผลลัพธ์อยู่ที่ `generated/latest.png` และ `generated/latest.json` ภาพที่สร้างในเครื่องไม่ต้อง commit

## ตั้งค่า GitHub Actions

1. สร้าง GitHub repository แล้วนำไฟล์ทั้งหมดในโฟลเดอร์นี้ขึ้น repository
2. ใน **Settings → Actions → General → Workflow permissions** เลือก **Read and write permissions**
3. สร้าง LINE Official Account และเปิด Messaging API
4. เพิ่ม repository secrets:
   - `LINE_CHANNEL_ACCESS_TOKEN` — channel access token ของ LINE Messaging API
   - `LINE_TO` — user ID, group ID หรือ room ID ที่บอตได้รับอนุญาตให้ส่งหา
5. ไปที่แท็บ **Actions → Daily Gold Price Card → Run workflow**
6. รอบแรกให้ `send_to_line = false` แล้วตรวจภาพ artifact
7. เมื่อภาพถูกต้อง ค่อยรันอีกครั้งโดย `send_to_line = true`

Workflow ตั้งเวลาไว้ดังนี้:

```yaml
schedule:
  # 02:10–02:40 UTC = 09:10–09:40 Asia/Bangkok
  - cron: "10-40/5 2 * * 1-6"
```

เมื่อส่งสำเร็จ workflow จะบันทึก receipt ของวันนั้น รอบ schedule ถัดไปจึงหยุดทันทีโดยไม่ดึงราคาและไม่ส่ง LINE ซ้ำ

## เงื่อนไข URL รูปสำหรับ LINE

LINE image message ต้องอ่านรูปผ่าน public HTTPS URL ดังนั้นค่าเริ่มต้นใช้ URL ของ `raw.githubusercontent.com` บน branch `gold-price-images` และ repository ต้องเป็น **public** ตัวอย่าง URL คือ `https://raw.githubusercontent.com/ptrpspeen/daily-gold-line-bot/gold-price-images/2026-10-28.png`

Workflow สร้างไฟล์ชั่วคราวใน `generated/run/` แล้วใช้ `tools/publish_images.py` เผยแพร่เฉพาะภาพ 5 วันที่ล่าสุด พร้อม `latest.png` และ `latest.json` บน branch นี้ `latest.png` เป็นชื่อสำรองของภาพวันล่าสุดและใช้ Git blob เดียวกัน จึงไม่ได้เพิ่มสำเนาใน Git อีกชุด

ทุกครั้งที่เผยแพร่จะสร้าง snapshot commit ที่ไม่มี parent และใช้ `--force-with-lease` เฉพาะ branch ภาพ จึงไม่สะสมประวัติภาพรายวันใน branch นี้ ส่วน `main` เก็บเฉพาะโค้ดและ receipt ตามปกติ พร้อมภาพ `generated/latest.png` และ JSON ที่หยุดอัปเดตไว้เพื่อให้ลิงก์ LINE เดิมยังเปิดได้ ภาพเก่าที่เคย commit ยังอยู่ในประวัติ `main`; การเปลี่ยนนี้หยุดการเพิ่มภาพเข้า history โดยไม่เขียนประวัติโค้ดเดิมใหม่ และไม่ได้รับประกันเวลาที่ GitHub จะเก็บกวาด object ที่ไม่มี branch อ้างถึง

ดูภาพที่เก็บอยู่ได้ที่ [branch ภาพล่าสุด](https://github.com/ptrpspeen/daily-gold-line-bot/tree/gold-price-images) ภาพย้อนหลังที่เกิน 5 วันจะถูกนำออกจาก branch ภาพ

หาก repository เป็น private ให้เผยแพร่ `generated/latest.png` ผ่านโฮสต์ของคุณ แล้วสร้าง GitHub Actions variable:

```text
PUBLIC_IMAGE_BASE_URL=https://example.com/path/to/generated
```

URL ดังกล่าวต้องเปิด `latest.png` ได้โดยไม่ต้องล็อกอิน

## ส่ง LINE จากเครื่อง

```bash
export LINE_CHANNEL_ACCESS_TOKEN="..."
export LINE_TO="..."

python -m gold_bot send-line \
  --data generated/latest.json \
  --image-url "https://example.com/generated/latest.png"
```

หากต้องการส่งซ้ำในวันเดิม ให้เพิ่ม `--force`

## โครงสร้างสำคัญ

```text
assets/                    Canva template, references, style spec
fonts/                     Noto Sans Thai + license
src/gold_bot/scraper.py    ดึงเฉพาะประกาศครั้งที่ 1
src/gold_bot/renderer.py   render ตามสเปก Canva
src/gold_bot/line.py       ส่ง LINE Messaging API
.github/workflows/         schedule จันทร์–เสาร์ 09:10
tools/publish_images.py    เผยแพร่ snapshot ภาพ 5 วันล่าสุด
generated/                 ไฟล์ในเครื่อง; latest.* เดิมเก็บไว้รองรับลิงก์ LINE เก่า
state/sent/                receipt ป้องกันส่งซ้ำ
tests/                     fixture และ automated tests
```

## หมายเหตุด้านข้อมูล

แหล่งหลักคือ [สมาคมค้าทองคำ](https://classic.goldtraders.or.th/UpdatePriceList.aspx) และแหล่งสำรองคือ [ราคาทองคำวันนี้.com](https://xn--42cah7d0cxcvbbb9x.com/) โครงสร้าง HTML ของเว็บไซต์ภายนอกอาจเปลี่ยนได้ในอนาคต; หาก test หรือ workflow แจ้ง parse error ให้ตรวจ selector ใน `src/gold_bot/scraper.py` ก่อนส่งข้อมูลต่อ

การส่งภาพใช้ [LINE Messaging API](https://developers.line.biz/en/reference/messaging-api/) ไม่ใช้ LINE Notify ซึ่งยุติบริการแล้ว
