---
title: Book Language Tool — Product Card
doc_id: CARD-book-language-tool
doc_type: product-card
verdict: template
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Product owner (Book Dev)
---

# Book Language Tool — Product Card

## 1. สรุปคุณค่าในหนึ่งประโยค

เป็น reference app ตัวแรกของ Software Program Factory ที่พิสูจน์หมวด programming-language-tool ด้วยภาษาเล็ก ๆ ที่ compile เป็น IR แบบ deterministic และรันใน VM ปิด

## 2. ปัญหาและผู้ใช้เป้าหมาย

- ปัญหา: ต้องการตัวอย่างครบวงจร source → compile → run ที่อ่านได้ทั้งหมด สำหรับการเรียนรู้และ regression fixture
- ผู้ใช้: นักพัฒนา/ผู้เรียน — ไม่ใช่ตลาด

## 3. สิ่งที่ทำได้จริงตอนนี้

- CLI `check`, `compile`, `exec`, `run` พร้อม `--json` และ exit code ที่นิยามไว้
- ภาษา: `let` (int/string), `+ - * /`, ต่อ string, `print`; diagnostic มีบรรทัด/คอลัมน์และรหัสคงที่
- IR `book-language-tool.ir.v1` + SHA-256; VM รันเฉพาะ instruction set ของตัวเอง
- ไม่มี dependency ภายนอก; test แบบ unittest offline

## 4. หลักฐานสถานะ

| รายการ | ค่า (ตรวจจาก repository) |
|---|---|
| Stack | Python |
| Commits | 7 (แรก 2026-09-09 → ล่าสุด 2026-10-01) |
| Source | 7 ไฟล์ / 1,330 บรรทัด |
| Tests | 13 ไฟล์ |
| CI | 1 workflow |
| Deploy config | ไม่มี |
| Live URL | ไม่มี |
| README | 99 บรรทัด (`Book Language Tool`) |
| โครงสร้างซ้ำ (template family) | 1 repo ที่มี structure signature เดียวกัน |

## 5. คุณค่าและจุดต่าง

- เป็นหลักฐาน portfolio ด้าน compiler และตัวอย่างวินัย deterministic/safe execution
- ไม่มีมุมรายได้ — PRODUCT.md ระบุว่าเป็น educational/reference ไม่ใช่ production compiler

## 6. ช่องว่างสำคัญ

- ภาษาเล็กเกินกว่าจะมีผู้ใช้จริง และตั้งใจให้เป็นเช่นนั้น

## 7. คำตัดสิน

**`template`** — เป็น reference ของ factory ไม่ใช่ผลิตภัณฑ์ จะมีค่ามากขึ้นถ้าถูกใช้เป็นสื่อสอน (เช่น บทเรียน compiler) ที่มีผู้เรียนจริง

## 8. ขั้นต่อไป

1. ติด label template/reference
2. ไม่เพิ่มฟีเจอร์ภาษาโดยไม่มีผู้ใช้หรือบทเรียนรองรับ

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| Product owner (Book Dev) | รอพิจารณา | — | ________ |

## แหล่งข้อมูล

- `README.md`
- `PRODUCT.md`
- `evidence/BASELINE.md`
- `src/book_language_tool/core.py`
