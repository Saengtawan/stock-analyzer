#!/usr/bin/env python3
"""
ดึงหัวข้อทั้งหมดในหน้า analyze.html
"""
import re

with open('/home/saengtawan/work/project/cc/stock-analyzer/src/web/templates/analyze.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ค้นหา card headers และ sections สำคัญ
sections = []
lines = content.split('\n')

for i, line in enumerate(lines):
    # ค้นหา comments ที่บอกว่าเป็น section ไหน
    if '<!--' in line and ('Section' in line or 'Enhanced' in line or 'Feature' in line):
        comment = line.strip()
        sections.append(f"Line {i+1}: {comment}")

    # ค้นหา card-header ที่มี icon และชื่อ
    if 'card-header' in line:
        # หาข้อความหลัง icon หรือใน h5
        next_lines = '\n'.join(lines[i:min(i+5, len(lines))])

        # Extract text from h5 or h6
        h_match = re.search(r'<h[456][^>]*>([^<]+(?:<i[^>]*>[^<]*</i>[^<]*)?.*?)</h[456]>', next_lines)
        if h_match:
            text = h_match.group(1)
            # Clean up HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            text = text.strip()
            if text and len(text) > 3:
                sections.append(f"Line {i+1}: 📋 {text}")

# พิมพ์เฉพาะ sections ที่ไม่ซ้ำกัน
print("="*80)
print("🔍 หัวข้อทั้งหมดในหน้า Analyze (เรียงตามลำดับที่ปรากฏ)")
print("="*80)
print()

seen = set()
count = 0
for section in sections:
    # ลบ line number เพื่อเช็คซ้ำ
    text = section.split(': ', 1)[1] if ': ' in section else section
    if text not in seen and text.strip():
        seen.add(text)
        count += 1
        print(f"{count}. {text}")

print()
print("="*80)
print(f"รวม {count} หัวข้อ")
print("="*80)
