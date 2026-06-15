#!/usr/bin/env bash
# setup.sh — one-command new-machine setup. Idempotent: re-run after fixing any
# interactive blocker (sudo / rclone auth / pyenv) and it continues where it left off.
#
#   git clone git@github.com:Saengtawan/stock-analyzer.git && cd stock-analyzer
#   bash scripts/setup.sh             # full (pulls 21GB DB)
#   bash scripts/setup.sh --light     # skip the 21GB DB (rebuild via cron)
#
# Does automatically: pyenv envs, Drive pull (bootstrap), systemd services (path-fixed),
# crontab (path-fixed), enable services. Stops with clear instructions for the 3 things
# that NEED you: install rclone (sudo), `rclone config` (Google auth), pyenv install.
set -uo pipefail
cd "$(dirname "$0")/.."
PROJ="$(pwd -P)"; OLD_PROJ="/home/saengtawan/work/project/cc/stock-analyzer"; OLD_HOME="/home/saengtawan"
LIGHT=""; [[ "${1:-}" == "--light" ]] && LIGHT="--light"
PYV="3.11.8"
step(){ echo; echo "──────── $1 ────────"; }
die(){ echo; echo "⛔ $1"; echo "   ↳ ทำขั้นนี้แล้วรัน  bash scripts/setup.sh $LIGHT  ซ้ำ (มันต่อให้เอง)"; exit 1; }

step "0. prerequisites"
command -v git >/dev/null || die "ไม่มี git"
command -v python3 >/dev/null || die "ไม่มี python3"
command -v rclone >/dev/null || die "ไม่มี rclone → ติดตั้ง:  curl https://rclone.org/install.sh | sudo bash"
command -v pyenv  >/dev/null || die "ไม่มี pyenv → ติดตั้ง: https://github.com/pyenv/pyenv#installation (+ pyenv-virtualenv)"
echo "  ✓ git, python3, rclone, pyenv"

step "1. pyenv environments (issara=pandas3 โหลด pkl, cc)"
export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"; eval "$(pyenv init - 2>/dev/null)" || true
pyenv versions --bare | grep -qx "$PYV" || { echo "  installing python $PYV (อาจนานหลายนาที)..."; pyenv install -s "$PYV" || die "pyenv install $PYV ล้มเหลว"; }
for env in issara cc; do
  if pyenv versions --bare | grep -qx "$env"; then echo "  ✓ env:$env";
  else echo "  creating env:$env..."; pyenv virtualenv "$PYV" "$env" || die "สร้าง env $env ล้มเหลว"
       "$HOME/.pyenv/versions/$env/bin/pip" install -q -r "deploy/requirements_$env.txt" && echo "  ✓ env:$env (pip installed)" || die "pip install $env ล้มเหลว"; fi
done

step "2. Google Drive (rclone remote 'gdrive')"
rclone listremotes | grep -qx "gdrive:" || die "ยังไม่ได้ config Drive → รัน:  rclone config   (New → ชื่อ 'gdrive' → Google Drive → authorize)"
echo "  ✓ gdrive: connected"

step "3. pull artifacts from Drive (models + DB + .env)"
bash scripts/bootstrap.sh $LIGHT || die "bootstrap ล้มเหลว"
[[ -f .env ]] || { cp .env.template .env 2>/dev/null && echo "  ⚠️ ไม่มี .env บน Drive → copy template แล้ว กรอก 49 keys เอง"; }

step "4. systemd services (path-adjusted)"
mkdir -p "$HOME/.config/systemd/user"
for svc in deploy/systemd/*.service; do
  [[ -f "$svc" ]] || continue
  base="$(basename "$svc")"
  sed -e "s#${OLD_PROJ}#${PROJ}#g" -e "s#${OLD_HOME}#${HOME}#g" "$svc" > "$HOME/.config/systemd/user/$base"
  echo "  ✓ $base"
done
systemctl --user daemon-reload 2>/dev/null || echo "  (systemd --user ไม่พร้อม — ข้าม)"

step "5. crontab (path-adjusted)"
bash scripts/restore_cron.sh --install || echo "  ⚠️ restore_cron มี dep ขาด (ดูข้างบน) — แก้แล้วรัน restore_cron.sh --install เอง"

step "6. enable services"
systemctl --user enable --now auto-trading.service stock-webapp.service 2>/dev/null && echo "  ✓ services started" || echo "  (start เองภายหลัง: systemctl --user start auto-trading.service stock-webapp.service)"

echo; echo "════════ ✅ SETUP DONE ════════"
echo "  verify:"
echo "    ls backtests/models_exit_v18/sector_specialists.pkl   # model มา"
echo "    ls -lh data/trade_history.db                          # DB มา (~21GB ถ้าไม่ --light)"
echo "    crontab -l | grep -vc '^#'                            # cron jobs"
echo "    systemctl --user is-active auto-trading.service       # active"
echo "    bash scripts/watch_riser.sh                           # terminal riser view"
echo "  ⚠️ ตรวจ TZ=Asia/Bangkok ใน crontab ตรงเขตเวลาเครื่องนี้ (ET+11 ช่วง EDT)"
