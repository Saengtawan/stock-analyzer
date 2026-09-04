# Stock Analyzer — Intraday ML Trading System

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![Account](https://img.shields.io/badge/account-Alpaca%20Paper-orange.svg)
![Status](https://img.shields.io/badge/status-deployed%20(paper)-green.svg)

Backtest-validated intraday trading on Alpaca **paper**. Two entry lanes, each
with its own regime-conditional exit. Manual workflow (suggest → you click at
Alpaca). Driven via Claude Code + `CLAUDE.md`.

> **`CLAUDE.md` is the canonical spec** (rules, params, history). This README is
> the quickstart + map. When they disagree, trust `CLAUDE.md`.

---

## System at a glance — 2 entry lanes × 2 exits

| Lane (entry) | What it picks | Exit | Holdout result |
|---|---|---|---|
| **H12-A** (`ml_filter`) | per-(zone,sector) ML, top-1 by win_p, 09:30–13:00 | **v18** — SL2.5 / prop-trail / model-PL, gated on `spy_dd≤−0.3` (reacts to a falling market) | +154%/3yr; exit Sharpe 2.93→**3.89**, worst −8.7→**−3.0** |
| **riser** (`riser_capture`) | Z1 ranked by `gain_from_open`, buy top-1, hold-EOD | **riser dynamic** — trail 1% if `VIX_entry≥22 OR own_range[20m]≥3%`, else hold-EOD | WR(peak≥1%) 73%; exit ret/DD 0.85→**1.97** |

`exit_check.sh` **auto-routes**: a symbol in `riser_picks` → riser exit; else → v18.
Both are PAPER/shadow — forward-track before sizing up.

---

## Quick start (new machine)

Code is in git; large artifacts (models ~200MB, DBs incl. 21GB `trade_history`,
`.env`) live in **Google Drive** via rclone.

```bash
git clone git@github.com:Saengtawan/stock-analyzer.git
cd stock-analyzer
bash scripts/setup.sh                 # one command: pyenv + Drive pull + services + cron
#   bash scripts/setup.sh --light     # skip the 21GB DB (rebuild via cron)
```

`setup.sh` is **idempotent** — it does everything it can and stops with the exact
command for the 3 things only you can do (they need sudo / Google login):
`curl https://rclone.org/install.sh | sudo bash` · `rclone config` (remote named
`gdrive`) · install pyenv. Fix the one it names, re-run `setup.sh`, it continues.

<details><summary>…or do the phases manually</summary>

```bash
curl https://rclone.org/install.sh | sudo bash      # rclone
rclone config                                       # remote 'gdrive' → Drive
bash scripts/bootstrap.sh                            # pull models + DBs + .env
# pyenv: install 3.11.8 + envs from deploy/requirements_{issara,cc}.txt
cp deploy/systemd/*.service ~/.config/systemd/user/ && systemctl --user daemon-reload
bash scripts/restore_cron.sh --install               # crontab (auto path-fix)
systemctl --user enable --now auto-trading.service stock-webapp.service
```
</details>

### Make cron + services work (the part git/Drive doesn't auto-handle)

`git clone` + `bootstrap.sh` gives code + models + DBs + `.env`, but **NOT** the
crontab, pyenv envs, or systemd services. Restore them from `deploy/`:

```bash
# 1. pyenv environments (cron + the pkl need these exact ones)
pyenv install 3.11.8
pyenv virtualenv 3.11.8 issara && pip install -r deploy/requirements_issara.txt   # pandas 3.x (loads the pkls)
pyenv virtualenv 3.11.8 cc      && pip install -r deploy/requirements_cc.txt

# 2. systemd services (adjust paths inside if username/dir differ)
cp deploy/systemd/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now auto-trading.service stock-webapp.service

# 3. crontab (auto-rewrites the original machine's paths to THIS machine)
bash scripts/restore_cron.sh             # dry-run: checks deps + previews
bash scripts/restore_cron.sh --install   # apply (backs up existing crontab first)

# 4. rclone for the backup crons
rclone config            # remote named 'gdrive'  (if not done in step above)
```

If there's no Drive backup: fill `.env` from `.env.template` (49 keys) and let
the cron data-collectors rebuild the DBs over time (days–weeks).

> ⚠️ cron uses **absolute paths** + `TZ=Asia/Bangkok` (ET+11 during EDT; shift
> +1h at the Nov EST changeover). `restore_cron.sh` fixes paths; timezone you keep.

---

## Daily usage

```bash
# scan (auto-waits until 09:31:30 ET if run early)
bash scripts/scan_smart.sh            # H12-A picks, auto-tracked with v18
# riser lane runs via cron (09:31 ET) → riser_capture.sh

# check / track an exit (auto-picks the right exit for the symbol)
bash scripts/exit_check.sh SYM            # one-shot verdict
bash scripts/exit_loop.sh SYM ENTRY TIME  # poll every 5 min
bash scripts/watch_riser.sh               # live terminal view of the riser lane

# verdicts: ✅ HOLD  🟢 TRAIL_EXIT  🟡 PL_EXIT  🔴 SL_EXIT  🛡️ VIX_SKIP
# read the Verdict line; EXIT = sell at Alpaca, HOLD = keep, EOD-flat at 15:55.

# weekly: live-vs-backtest drift scorecard
python3 scripts/forward_track.py
```

**Reversibility flags:** `EXIT_ML_VERSION=v17c` or `--v17c` (roll back v18) ·
`RISER_EXIT_DYNAMIC=0` (riser → plain hold-EOD) · `RISER_ENABLED=0` ·
`RISER_TRACK=0` · `H12A_*` env toggles (see `CLAUDE.md`).

---

## Operating via Claude Code (new machine / new session)

The trading system runs **without** Claude — OS-cron writes picks, `watch_riser.sh`
streams them to a terminal, exits route automatically. Claude Code is the *operator*
(scan on demand, analyze, run tooling). Two things are **session-bound** and must be
re-created when you open a fresh Claude session elsewhere:

1. **In-chat riser alert** (Claude pings you at ~09:37:45 when the riser pick prints).
   This is a background watcher tied to the session — start it by telling Claude:
   > "ตั้ง background watcher รอ riser แล้วเด้งบอกในแชตตอน display"

   (or just run the session-independent terminal view yourself: `bash scripts/watch_riser.sh`).

2. **Claude scheduled wake-ups** (optional) — recreate with a request like
   *"ตั้ง Claude schedule ปลุก 09:38 ET มาสรุป riser pick"*.

To bring a fresh Claude session fully up to speed, paste this:

> อ่าน CLAUDE.md + memory/MEMORY.md ก่อน. ระบบ = H12-A (ml_filter) + riser lane,
> exit = v18 (auto) + riser dynamic (VIX/own_range). อยากให้: (1) ยืนยัน cron/services
> รันอยู่ (systemctl, crontab -l), (2) ตั้ง background watcher รอ riser display เด้งในแชต,
> (3) พร้อมช่วย scan/exit_check/forward_track ระหว่างวัน.

Everything the system *needs* to trade is in git + Drive + cron. The Claude session
only adds convenience (alerts, analysis) — never required for an order to fire.

## Architecture

```
src/scan/strategies/ml_filter.py     # H12-A entry (multi-model serving)
src/scan/strategies/riser_momentum.py# riser entry
src/scan/{engine,h12a_picker,ml_scorer}.py
src/exit_ml/inference_v18.py         # v18 exit (H12-A) — spy_dd-reactive
src/exit_ml/inference_riser.py       # riser exit — VIX/own_range dynamic trail
src/exit_ml/cli.py                   # exit_check entry; auto-routes per lane
scripts/{scan_smart,scan_track,riser_capture}.sh   # scan + auto-track
scripts/{exit_check,exit_loop,watch_riser}.sh      # exit / monitor
scripts/{backup_to_drive,bootstrap}.sh             # Drive backup / restore
scripts/forward_track.py                           # drift scorecard
backtests/models_prod_v23_h12a/   # H12-A serving models (235)   [pkl gitignored]
backtests/models_exit_v18/        # v18 exit models               [pkl gitignored]
data/trade_history.db             # 21GB feature store            [gitignored]
CLAUDE.md                         # canonical spec
```

Services are systemd (`auto-trading.service`, `stock-webapp.service`) — **never
`pkill`**, use `systemctl --user restart`.

---

## Backup / restore

| Layer | Where | Refresh |
|---|---|---|
| code | git (github + gitlab) | `git push` |
| models, small DBs, `.env` | Google Drive (`backup_to_drive.sh --light`) | weekly cron (Sun 21:00 BKK) |
| `trade_history.db` (21GB) | Google Drive (`backup_to_drive.sh`) | monthly cron (1st 22:00 BKK) |

New machine = `git clone` + `bootstrap.sh`. Secrets (`.env`) never go to git —
only to your private Drive.

---

## ⚠️ Notes

- **Paper account** — no real money. `.env` holds API keys (gitignored).
- Exits are **shadow/paper**; track 10–15 forward picks (`forward_track.py`)
  before trusting live / increasing size.
- This README is a map; **`CLAUDE.md` is authoritative** for rules and numbers.

**Last updated:** 2026-06-15
