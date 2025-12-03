#!/usr/bin/env python3
"""
ตรวจสอบหัวข้อที่ซ้ำกันจริงๆ โดยดูว่าแสดงข้อมูลอะไร
"""
import re

with open('/home/saengtawan/work/project/cc/stock-analyzer/src/web/templates/analyze.html', 'r', encoding='utf-8') as f:
    content = f.read()

# แยก sections ตาม card
cards = re.findall(r'<div class="card[^>]*>.*?</div>\s*</div>', content, re.DOTALL)

sections = []
lines = content.split('\n')

current_section = None
section_content = []

for i, line in enumerate(lines):
    # หา card-header
    if 'card-header' in line:
        # Save previous section
        if current_section and section_content:
            sections.append({
                'line': current_section['line'],
                'title': current_section['title'],
                'content_preview': '\n'.join(section_content[:20])  # First 20 lines
            })

        # Extract title
        next_lines = '\n'.join(lines[i:min(i+10, len(lines))])
        title_match = re.search(r'<h[456][^>]*>(.*?)</h[456]>', next_lines, re.DOTALL)

        if title_match:
            title = title_match.group(1)
            # Clean HTML tags but keep icons
            title = re.sub(r'<i [^>]*></i>\s*', '', title)
            title = re.sub(r'<[^>]+>', '', title)
            title = title.strip()

            if title and len(title) > 2 and '${' not in title:  # Skip template variables
                current_section = {'line': i+1, 'title': title}
                section_content = []

    # Collect content for current section
    if current_section:
        section_content.append(line)
        # Stop at next card or after 100 lines
        if len(section_content) > 100:
            sections.append({
                'line': current_section['line'],
                'title': current_section['title'],
                'content_preview': '\n'.join(section_content[:20])
            })
            current_section = None
            section_content = []

print("="*100)
print("🔍 ตรวจสอบหัวข้อที่อาจซ้ำกัน")
print("="*100)
print()

# Group by similar titles
title_groups = {}
for section in sections:
    title = section['title']

    # Normalize title for comparison
    normalized = title.lower()
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Check if similar title exists
    found_group = None
    for existing_title in title_groups:
        existing_normalized = existing_title.lower()
        existing_normalized = re.sub(r'[^\w\s]', '', existing_normalized)

        # Check similarity
        if normalized == existing_normalized or normalized in existing_normalized or existing_normalized in normalized:
            found_group = existing_title
            break

    if found_group:
        title_groups[found_group].append(section)
    else:
        title_groups[title] = [section]

# Show all sections first
print("📋 หัวข้อทั้งหมดที่แสดงผล:")
print("-"*100)
for i, section in enumerate(sections, 1):
    print(f"{i:2d}. Line {section['line']:4d}: {section['title']}")
print()

# Show potential duplicates
print("="*100)
print("⚠️ หัวข้อที่อาจซ้ำกัน:")
print("="*100)
print()

duplicates_found = False
for title, group in title_groups.items():
    if len(group) > 1:
        duplicates_found = True
        print(f"🔴 '{title}' - ปรากฏ {len(group)} ครั้ง:")
        for section in group:
            print(f"   Line {section['line']}: {section['title']}")
            # Check what data it displays
            preview = section['content_preview']
            if 'id=' in preview:
                ids = re.findall(r'id="([^"]+)"', preview)
                if ids:
                    print(f"      → แสดงข้อมูล: {', '.join(ids[:5])}")
        print()

if not duplicates_found:
    print("✅ ไม่พบหัวข้อที่ซ้ำกัน")

print("="*100)
print(f"รวม {len(sections)} หัวข้อที่แสดงผลจริง")
print("="*100)
