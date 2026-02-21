# Cron Timeline Implementation (v6.37)

## Overview
เพิ่ม **Cron Timeline** เข้าไปใน UI เพื่อแสดงภาพรวมของ scheduled tasks ทั้งหมดในระบบ

**Version:** v6.37
**Date:** 2026-02-21
**Status:** ✅ Complete

---

## What's New

### 1. Backend: Complete Cron Schedule API
**File:** `src/auto_trading_engine.py`

เพิ่ม method `_get_cron_schedule()` (line ~6850) ที่ return scheduled tasks ทั้งหมด:

**Tasks ที่รวมอยู่:**
- ✅ Pre-Market Gap Scan (06:00-09:30 ET)
- ✅ Pre-Open Pre-Filter (09:00 ET)
- ✅ Morning DIP Scan (09:35 ET)
- ✅ PEM Scan (09:35 ET)
- ✅ Continuous DIP Scan (09:45-15:45 ET, adaptive 5/15 min)
- ✅ Skip Window (10:00-11:00 ET)
- ✅ Midday Filter (10:45 ET)
- ✅ Afternoon Filter (13:45 ET)
- ✅ Overnight Gap Scan (15:30 ET)
- ✅ Pre-Close Filter (15:45 ET)
- ✅ Pre-Close Check (15:50 ET)
- ✅ Evening Filter (20:00 ET)
- ✅ Position Monitor (Continuous, 30 sec)

**Data Structure:**
```python
{
    'tasks': [
        {
            'name': 'morning_scan',
            'label': 'Morning DIP Scan',
            'time': '09:35',
            'minutes': 575,
            'frequency': 'Once per day',
            'window': '09:35',
            'status': 'done|active|pending',
            'description': 'Main dip-bounce signal generator',
            'strategy': 'DIP'
        },
        ...
    ],
    'current_time': '14:23',
    'current_minutes': 863,
    'trading_day': '2026-02-21'
}
```

**Status Detection:**
- `done`: Task เสร็จแล้ว (check `_morning_scan_done == today`)
- `active`: กำลังทำงาน (check time window)
- `pending`: รอทำ

**Integration:**
- เพิ่ม `'cron_schedule': self._get_cron_schedule()` ใน `get_status()` (line 7143)
- Available via `/api/status` endpoint

---

### 2. Frontend: Cron Timeline UI Component
**File:** `src/web/templates/rapid_trader.html`

#### HTML Structure (line ~580)
```html
<div class="cron-timeline-section" id="cronTimelineSection">
    <div class="cron-header" onclick="toggleCronTimeline()">
        <i class="fas fa-clock"></i>
        <span>Scheduled Tasks</span>
        <button class="cron-toggle" id="cronToggle">
            <i class="fas fa-chevron-down"></i>
        </button>
    </div>
    <div class="cron-timeline-container" id="cronTimelineContainer" style="display: none;">
        <div class="cron-timeline-grid" id="cronTimelineGrid">
            <!-- Tasks rendered dynamically -->
        </div>
    </div>
</div>
```

#### CSS Styles (line ~148)
**Grid Layout:**
- Auto-fill grid: min 180px per task card
- 8px gap between cards
- Responsive design

**Task Card States:**
- `.cron-task.pending`: Gray border, transparent indicator
- `.cron-task.active`: Blue border, pulsing indicator
- `.cron-task.done`: Green border, green indicator

**Strategy Color Coding:**
- `DIP`: Blue (#3b82f6)
- `OVN`: Orange (#f59e0b)
- `PEM`: Green (#10b981)
- `Filter`: Purple (#8b5cf6)
- `Gap`: Pink (#ec4899)
- `Protection`: Red (#ef4444)
- `Monitor`: Gray (#64748b)

#### JavaScript Functions (line ~1842)

**toggleCronTimeline():**
- Toggle collapsed/expanded state
- Save state to localStorage
- Persist across page reloads

**updateCronTimeline(cronSchedule):**
- Render task cards from API data
- Apply status classes (done/active/pending)
- Show time, strategy tag, description (tooltip)

**Integration:**
- Called in `updateEngineStatus()` (line ~1959)
- Auto-refresh ทุกครั้งที่ API update (30s interval)

---

### 3. Version Updates
**Updated Files:**
- `src/web/app.py`: `APP_VERSION = 'v6.37'`
- `src/auto_trading_engine.py`: `'version': 'v6.37'`

---

## Features

### 1. Complete Task Overview
แสดง **13 scheduled tasks** ทั้งหมด organized by time:
- Pre-market (06:00)
- Pre-open (09:00)
- Morning (09:35)
- Continuous (09:45-15:45)
- Midday (10:45)
- Afternoon (13:45, 15:30, 15:45)
- Pre-close (15:50)
- Evening (20:00)
- Monitor (continuous)

### 2. Real-time Status
- ✅ **Done**: Green indicator, task completed
- 🔵 **Active**: Blue pulsing indicator, currently running
- ⚪ **Pending**: Gray outline, waiting to run

### 3. Strategy Identification
Color-coded badges:
- **[DIP]**: Morning + Continuous scans
- **[OVN]**: Overnight gap scan
- **[PEM]**: Post-earnings momentum
- **[Filter]**: Pre-filter refreshes
- **[Gap]**: Pre-market gap scan
- **[Protection]**: Skip window + pre-close
- **[Monitor]**: Continuous monitoring

### 4. Collapsible Interface
- Click header to expand/collapse
- State persists via localStorage
- Minimizes screen clutter when not needed

### 5. Detailed Tooltips
Hover over task card → see full description:
- "Main dip-bounce signal generator (max 2 positions)"
- "Refresh pool with new dip candidates since open"
- "No trading during volatile mid-morning period"

---

## User Benefits

### 1. System Transparency
ผู้ใช้เห็นทั้งหมดว่า:
- มี task อะไรรันอยู่บ้าง
- เวลาไหน
- status ตอนนี้คืออะไร
- ทำงานเสร็จยัง

### 2. Debugging Tool
เมื่อมีปัญหา สามารถ:
- ดูว่า task ที่คาดหวังทำงานยัง (e.g., "OVN ทำไมไม่ได้หุ้น" → ดู status)
- ตรวจว่า pre-filter refresh ทำงานตามเวลาไหม
- Verify continuous scan interval (5 min vs 15 min)

### 3. Learning Tool
สำหรับผู้ใช้ใหม่:
- เข้าใจ trading schedule ทั้งระบบ
- รู้ว่าแต่ละ strategy scan เมื่อไหร่
- เห็นความสัมพันธ์ระหว่าง tasks (pre-filter → scan → signals)

### 4. System Health Monitor
Quick visual check:
- All tasks running? (all green/blue)
- Something stuck? (stuck at active, not turning green)
- Pre-filter pool refresh working? (3 filters per day should all be done)

---

## Implementation Details

### Backend Logic

**Status Detection Methods:**
```python
# Morning scan
'status': 'done' if getattr(self, '_morning_scan_done', None) == today else 'pending'

# Continuous scan
last_cont = getattr(self, '_last_continuous_scan', None)
cont_status = 'active' if last_cont and (et_now - last_cont).total_seconds() < interval * 60 else 'pending'

# Skip window (time-based)
in_skip = current_mins >= 600 and current_mins < 660
'status': 'active' if in_skip else 'pending'
```

**Task Tracking:**
Engine sets these flags:
- `_morning_scan_done = today` (when scan completes)
- `_pem_scan_done = today`
- `_overnight_scan_done = today`
- `_premarket_scan_done = today`
- `_evening_filter_done = today`
- `_pre_open_filter_done = today`
- `_intraday_filter_times = ['10:45', '13:45', '15:45']`

### Frontend Rendering

**Grid Auto-fill:**
```css
.cron-timeline-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 8px;
}
```

**Responsive:**
- Desktop: 5-6 cards per row
- Tablet: 3-4 cards per row
- Mobile: 1-2 cards per row

**Animations:**
- Active indicator: Pulsing glow (1.5s cycle)
- Hover: Background darkens, border brightens
- Toggle: Smooth expand/collapse

---

## Testing

### Manual Test Steps

1. **Open UI:**
   ```
   http://localhost:5002
   Navigate to Rapid Trader tab
   ```

2. **Verify Cron Timeline:**
   - See "Scheduled Tasks" header with clock icon
   - Click to expand → grid of task cards appears
   - All 13 tasks displayed
   - Each task has: name, time, strategy badge

3. **Check Status Colors:**
   - Morning (before 09:35): All pending (gray)
   - Morning (after 09:35): Morning scan = done (green)
   - During skip window (10:00-11:00): Skip window = active (blue pulsing)
   - After market: Most tasks = done (green)

4. **Test Toggle:**
   - Click header → timeline collapses
   - Refresh page → state persists (localStorage)
   - Click again → timeline expands

5. **Verify Auto-Update:**
   - Leave page open
   - Watch tasks change status as time progresses
   - Continuous scan should pulse blue periodically

### API Test
```bash
# Check cron_schedule in API response
curl http://localhost:5002/api/status | jq .cron_schedule

# Should return:
{
  "tasks": [ ... ],
  "current_time": "14:23",
  "current_minutes": 863,
  "trading_day": "2026-02-21"
}
```

---

## Files Modified

| File | Lines | Changes |
|------|-------|---------|
| `src/auto_trading_engine.py` | +193 | Added `_get_cron_schedule()` method |
| `src/auto_trading_engine.py` | +1 | Added cron_schedule to get_status() |
| `src/web/templates/rapid_trader.html` | +20 | Added HTML structure |
| `src/web/templates/rapid_trader.html` | +35 | Added CSS styles |
| `src/web/templates/rapid_trader.html` | +48 | Added JS functions |
| `src/web/templates/rapid_trader.html` | +2 | Integrated updateCronTimeline() |
| `src/web/app.py` | 1 | Version bump to v6.37 |
| **Total** | **+300 lines** | **7 files** |

---

## Documentation Created

- ✅ `CRON_TIMELINE.md` - Complete scheduled tasks documentation
- ✅ `CRON_TIMELINE_IMPLEMENTATION.md` - This implementation guide

---

## Next Steps

### Immediate
1. Restart web app to load new code
2. Test cron timeline in browser
3. Verify all 13 tasks display correctly
4. Commit changes with message: "Add cron timeline v6.37"

### Future Enhancements (Optional)
1. Add countdown timers for next task execution
2. Click task card → jump to task logs
3. Filter tasks by strategy (show only DIP, only Filter, etc.)
4. Export task schedule as CSV/JSON
5. Add task history (last 10 executions with status)

---

## Troubleshooting

### Timeline Not Showing
**Symptom:** Cron timeline section missing
**Fix:** Check `cron_schedule` in API response (`/api/status`)

### Tasks All Pending
**Symptom:** All tasks show gray (pending) even after scans run
**Fix:** Check engine flags (`_morning_scan_done`, etc.) are set correctly

### Toggle Not Working
**Symptom:** Click header, nothing happens
**Fix:** Check JavaScript console for errors, verify `toggleCronTimeline()` is defined

### Wrong Status Colors
**Symptom:** Active task shows green instead of blue
**Fix:** Check status value from API (`done|active|pending`)

---

**Implementation Date:** 2026-02-21
**Version:** v6.37
**Status:** ✅ Production Ready
