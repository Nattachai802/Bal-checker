# AI Credit Service

Service สำหรับจำกัดวงเงินการใช้ AI ของแต่ละ owner ต่อวัน (ค่าเริ่มต้น 35 บาท) ถ้าเครดิตคงเหลือน้อยกว่า 1 บาทจะไม่อนุญาตให้ใช้

ผู้เรียกใช้คือ **supervisor** เท่านั้น ไม่ได้เปิดให้ user เรียกตรง

## Flow

1. ก่อนเรียก AI — supervisor เรียก `GET /credit/{owner_id}` ถ้า `allowed = false` ให้ block
2. เรียก AI แล้วคิดเงินเป็นบาท
3. หลังเรียก AI — supervisor เรียก `POST /credit/deduct` เพื่อตัดเครดิต

- เครดิตรีเซ็ตอัตโนมัติทุกเที่ยงคืนเวลาไทย (Asia/Bangkok) ไม่ต้องมี cron
- owner ใหม่ใช้ได้ทันที ไม่ต้องลงทะเบียน (owner ที่ไม่เคยใช้ = ใช้ไป 0 บาท)
- ยอดติดลบได้: ค่าใช้จริงรู้หลังเรียก AI จึงตัดเต็มจำนวน แล้ว block ครั้งถัดไป

## Endpoints

### `GET /credit/{owner_id}`

เช็กเครดิตคงเหลือของ owner ในวันนี้

**Response `200`**

```json
{
  "owner_id": "5ffbc22292c64e42990106ef6f73efbc",
  "limit": 35,
  "used": 12.5,
  "remaining": 22.5,
  "allowed": true
}
```

| Field | Type | ความหมาย |
|---|---|---|
| `owner_id` | string | owner ที่ถาม |
| `limit` | number | วงเงินต่อวัน (`DAILY_LIMIT`) |
| `used` | number | ใช้ไปแล้ววันนี้ (บาท) |
| `remaining` | number | คงเหลือ = `limit - used` (ติดลบได้) |
| `allowed` | boolean | `true` ถ้า `remaining >= MIN_BALANCE` |

### `POST /credit/deduct`

ตัดเครดิตหลังเรียก AI

**Request body**

```json
{
  "request_id": "req-20261019-0001",
  "owner_id": "5ffbc22292c64e42990106ef6f73efbc",
  "cost": 4.5
}
```

| Field | Type | Required | ความหมาย |
|---|---|---|---|
| `request_id` | string | ✓ | id ไม่ซ้ำของแต่ละ request — ใช้กันตัดซ้ำเวลา retry |
| `owner_id` | string | ✓ | owner ที่จะตัด |
| `cost` | number/string | ✓ | ยอดเงิน (บาท) ต้อง `>= 0`, ทศนิยมได้ 4 ตำแหน่ง |

**Response `200`**

```json
{
  "owner_id": "5ffbc22292c64e42990106ef6f73efbc",
  "duplicate": false,
  "limit": 35,
  "used": 17.0,
  "remaining": 18.0,
  "allowed": true
}
```

| Field | Type | ความหมาย |
|---|---|---|
| `duplicate` | boolean | `true` = `request_id` นี้เคยตัดไปแล้ว รอบนี้**ไม่ได้ตัดซ้ำ** |
| อื่น ๆ | | เหมือน `GET /credit/{owner_id}` (ยอดหลังตัด) |

**Response `422`** — input ไม่ถูกต้อง เช่น `cost` ติดลบ / ไม่ใช่ตัวเลข, `request_id` หรือ `owner_id` ว่าง, ส่ง field ไม่ครบ

```json
{
  "detail": [
    {"type": "greater_than_equal", "loc": ["body", "cost"], "msg": "Input should be greater than or equal to 0", "input": "-1", "ctx": {"ge": 0}}
  ]
}
```

### `GET /docs`

Swagger UI ของ FastAPI ใช้ลองยิงทุกเส้นได้

## Config (`.env`)

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `DATABASE_URL` | — (บังคับ) | PostgreSQL connection string |
| `DAILY_LIMIT` | `35` | วงเงินต่อ owner ต่อวัน (บาท) |
| `MIN_BALANCE` | `1` | คงเหลือต่ำกว่านี้ = ไม่ให้ใช้ |

ดูตัวอย่างใน `.env.example` — แก้ค่าแล้วต้อง restart service

## Database

สร้างตารางอัตโนมัติตอน service start

| ตาราง | เก็บอะไร |
|---|---|
| `ai_credit_usage` | ยอดใช้รวมต่อ owner ต่อวัน — `(owner_id, day)` เป็น primary key |
| `ai_credit_txn` | log การตัดทุกครั้ง — `request_id` เป็น primary key (กันตัดซ้ำ) |

ไม่มีการเก็บข้อมูลส่วนตัวของ owner

## Run

**Local**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # แก้ DATABASE_URL
.venv/bin/uvicorn main:app --reload
```

**Docker**

```bash
docker build -t ai-credit .
docker run -d -p 8000:8000 --env-file .env ai-credit
```

ถ้า Postgres อยู่บนเครื่อง host ให้ใช้ `host.docker.internal` แทน `localhost` ใน `DATABASE_URL`

**Test** (ต้องมี Postgres ตาม `DATABASE_URL`)

```bash
.venv/bin/pytest -q
```

## ข้อจำกัด

- **ยังไม่มี auth** — ต้องวางไว้ใน network ภายในที่ supervisor เข้าถึงได้เท่านั้น
- วงเงินเท่ากันทุก owner
- ไม่ได้ตรวจว่า `owner_id` มีอยู่จริง — เชื่อค่าที่ supervisor ส่งมา
