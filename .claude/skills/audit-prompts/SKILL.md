---
name: audit-prompts
description: Audit CLAUDE.md + all prompts for directive language, hardcoded rules, bias, and inconsistencies
allowed-tools: Read, Grep, Glob, Bash, Agent
---

# Prompt Audit

Read ALL these files and check every line:

- `CLAUDE.md`
- `prompts/orb_breakout_prompt.md`
- `prompts/intraday_3pct_prompt.md`
- `prompts/top_movers_prompt.md`
- `prompts/ovn_gap_prompt.md`
- `prompts/friday_monday_prompt.md`

## Check for:

### 1. Directive language
Search for: ต้อง, ห้าม, skip, SKIP, ออก, ขาย, อย่า, เด็ดขาด, ทันที, ไม่แนะนำ, ข้าม
These should be data (WR%, avg return) not commands.

### 2. Judgment icons
Search for: ⚠️, ❌, 🔥, ✅ used as judgment labels on candidates
Scan output should show clean data, no pre-judgment.

### 3. Hardcoded rules
- Fixed sector lists ("Tech/HC = ดี")
- Fixed thresholds as absolute ("Vol < 1.5x = skip")
- "SPY แดง → WATCH/skip" (should be per-stock judgment)
- Multi-condition BUY NOW rules (should be AI weigh factors)

### 4. Bias toward one setup
- "BEST", "#1 Pick", "ดีที่สุด" labels
- Down Bounce presented above other setups
- Rankings that push AI to prefer one setup

### 5. Contradicting data
- WR numbers that differ between files for same setup
- Avg return claims that don't match

### 6. Scan code issues
- Any remaining yfinance
- Missing imports
- Hardcoded sector in code
- Inconsistent price filters across scans
- Volume ratio calculated differently

### 7. Missing data
- Market breadth not queried
- Options interpretation not explained
- Expected value (EV) not shown

## Output

Report EVERY issue with:
- File + line number
- Exact problematic text
- Why it's a problem
- What to change

Then ask: "แก้ทั้งหมดเลยมั้ย?"
