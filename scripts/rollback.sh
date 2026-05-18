#!/bin/bash
# Multi-version rollback for ml_filter system.
#
# Restores models + pkl + code to a previous deployed step.
# Creates safety backup before applying. Uses git revert (preserves history).
#
# Usage:
#   bash scripts/rollback.sh <target>             # interactive confirm
#   bash scripts/rollback.sh <target> --yes       # skip confirm
#   bash scripts/rollback.sh <target> --dry-run   # preview only, no changes
#   bash scripts/rollback.sh --status             # show current state
#   bash scripts/rollback.sh --list               # show available targets
#
# Targets (by step number or SemVer tag):
#   18 / v1.8.0      Step 18 legacy 5/14-5/15 era ⚠️ buggy pipeline, OLD VWAP
#   21 / v2.0.0      Step 21 baseline (pipeline-fixed)
#   23 / v2.0.1      Step 23 (Z4 dip filter 0.9%)
#   24 / v2.1.0      Step 24 (Z2 custom_dd)
#   25 / v2.1.1      Step 25 (no Z4 SL)
#   (Step 22 was reverted; cannot roll forward to 26 — only backwards)

set -euo pipefail

REPO="/home/saengtawan/work/project/cc/stock-analyzer"
cd "$REPO"

# ─── Step metadata ───────────────────────────────────────────────────
# commit SHAs (each step's deploy commit)
declare -A STEP_COMMIT=(
    [18]="a5bd6a7"
    [23]="2100214"
    [24]="fb86e16"
    [25]="96cce9a"
    [26]="60550a8"
)

declare -A STEP_DESC=(
    [18]="LEGACY 5/14-5/15 era (Step 18, OLD VWAP, 1-min snap) ⚠️ buggy pipeline"
    [21]="baseline (Z4 SL -3%, dip 0.5%, label_eod_green_v2)"
    [23]="Step 23: Z4 dip filter 0.5%→0.9%"
    [24]="Step 24: + Z2 label_custom_dd"
    [25]="Step 25: + remove Z4 SL (pure hold all)"
    [26]="Step 26: + Z3/Z4 custom_dd + Optuna HPs + R9 ranking"
)

# Which models backup to restore (none = use current)
declare -A MODELS_BACKUP=(
    [18]="backtests/models_prod_v22_v1.8.0"
    [21]="backtests/models_prod_v22_pre_step24"
    [23]="backtests/models_prod_v22_pre_step24"
    [24]="backtests/models_prod_v22_pre_step26"
    [25]="backtests/models_prod_v22_pre_step26"
)

# Which pkl backup to restore (empty = no change needed)
declare -A PKL_BACKUP=(
    [18]="cache/bt_features/backups/features_v1.8.0.pkl"
    [21]="cache/bt_features/backups/features_pre_step24.pkl"
    [23]="cache/bt_features/backups/features_pre_step24.pkl"
    [24]=""
    [25]=""
)

# Which commits to revert (sequential, newest first)
# Rollback to N → revert all commits AFTER N
declare -A REVERT_COMMITS=(
    [18]="60550a8 96cce9a fb86e16 2100214 7d3606c ad2886b 6f38f60 d7ae779 463c35c"
    [21]="60550a8 96cce9a fb86e16 2100214"   # revert Step 26, 25, 24, 23
    [23]="60550a8 96cce9a fb86e16"             # revert 26, 25, 24
    [24]="60550a8 96cce9a"                     # revert 26, 25
    [25]="60550a8"                             # revert 26
)

CURRENT_STEP=26  # Update this after each deploy

# ─── Arg parsing ─────────────────────────────────────────────────────
TARGET=""
DRY_RUN=false
SKIP_CONFIRM=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --yes|-y)  SKIP_CONFIRM=true ;;
        --status)
            echo "Current step: $CURRENT_STEP (${STEP_DESC[$CURRENT_STEP]:-unknown})"
            echo "Latest commit: $(git log --oneline -1)"
            echo "Engine: $(systemctl --user is-active auto-trading.service 2>/dev/null || echo inactive)"
            exit 0
            ;;
        --list)
            echo "Available rollback targets:"
            echo "  Step  SemVer    Description"
            echo "  ----  ------    -----------"
            echo "  25    v2.1.1    ${STEP_DESC[25]}"
            echo "  24    v2.1.0    ${STEP_DESC[24]}"
            echo "  23    v2.0.1    ${STEP_DESC[23]}"
            echo "  21    v2.0.0    ${STEP_DESC[21]}"
            echo "  18    v1.8.0    ${STEP_DESC[18]}"
            echo ""
            echo "Currently at: Step $CURRENT_STEP (v2.2.0)"
            echo ""
            echo "Usage:"
            echo "  bash scripts/rollback.sh 25       # step number"
            echo "  bash scripts/rollback.sh v2.1.1   # SemVer tag"
            exit 0
            ;;
        --help|-h)
            sed -n '2,15p' "$0"
            exit 0
            ;;
        25|24|23|21|18) TARGET="$arg" ;;
        v1.8.0)      TARGET="18" ;;
        v2.0.0)      TARGET="21" ;;
        v2.0.1)      TARGET="23" ;;
        v2.1.0)      TARGET="24" ;;
        v2.1.1)      TARGET="25" ;;
        v2.2.0)
            echo "ERROR: v2.2.0 is current — nothing to rollback"
            exit 1
            ;;
        *)
            echo "Unknown arg: $arg"
            echo "Run with --help for usage."
            exit 1
            ;;
    esac
done

if [ -z "$TARGET" ]; then
    # Interactive menu
    echo ""
    echo "============================================================"
    echo "  ROLLBACK VERSION PICKER"
    echo "============================================================"
    echo "  Current: Step $CURRENT_STEP (v2.2.0)"
    echo ""
    echo "  Select target version to rollback to:"
    echo ""
    echo "    [1] v2.1.1  Step 25  ${STEP_DESC[25]}"
    echo "    [2] v2.1.0  Step 24  ${STEP_DESC[24]}"
    echo "    [3] v2.0.1  Step 23  ${STEP_DESC[23]}"
    echo "    [4] v2.0.0  Step 21  ${STEP_DESC[21]}"
    echo "    [5] v1.8.0  Step 18  ${STEP_DESC[18]}"
    echo "    [q] Quit"
    echo ""
    read -p "  Enter selection [1-5/q]: " choice
    case "$choice" in
        1) TARGET="25" ;;
        2) TARGET="24" ;;
        3) TARGET="23" ;;
        4) TARGET="21" ;;
        5) TARGET="18" ;;
        q|Q|"") echo "  Cancelled."; exit 0 ;;
        *) echo "  Invalid selection."; exit 1 ;;
    esac
    echo ""
fi

if [ "$TARGET" -ge "$CURRENT_STEP" ]; then
    echo "ERROR: target ($TARGET) must be earlier than current ($CURRENT_STEP)"
    echo "This script only rolls BACKWARDS."
    exit 1
fi

# ─── Preview ─────────────────────────────────────────────────────────
TS=$(date +%Y-%m-%d-%H%M)
SAFETY_MODELS="backtests/models_prod_v22_pre_rollback_${TS}"
SAFETY_PKL="cache/bt_features/backups/features_pre_rollback_${TS}.pkl"
TAG="rollback-from-step${CURRENT_STEP}-${TS}"

models_src="${MODELS_BACKUP[$TARGET]}"
pkl_src="${PKL_BACKUP[$TARGET]}"
revert_list="${REVERT_COMMITS[$TARGET]}"

echo ""
echo "============================================================"
echo "  ROLLBACK PREVIEW"
echo "============================================================"
echo "  From: Step $CURRENT_STEP — ${STEP_DESC[$CURRENT_STEP]}"
echo "  To:   Step $TARGET — ${STEP_DESC[$TARGET]}"
echo ""
echo "  Actions to perform:"
echo ""
if [ -n "$models_src" ]; then
    if [ -d "$models_src" ]; then
        nfiles=$(ls "$models_src" | wc -l)
        echo "    [1] Restore models from $models_src ($nfiles files)"
    else
        echo "    [1] ❌ MISSING: $models_src"
        echo ""
        echo "  Cannot proceed — backup folder not found."
        exit 1
    fi
else
    echo "    [1] No models change needed"
fi

if [ -n "$pkl_src" ]; then
    if [ -f "$pkl_src" ]; then
        psize=$(du -h "$pkl_src" | cut -f1)
        echo "    [2] Restore pkl from $pkl_src ($psize)"
    else
        echo "    [2] ❌ MISSING: $pkl_src"
        exit 1
    fi
else
    echo "    [2] No pkl change needed"
fi

echo "    [3] git revert commits: $revert_list"
echo "    [4] Smoke test + restart auto-trading.service"
echo ""
echo "  Safety backup will be created:"
echo "    - Models: $SAFETY_MODELS"
[ -z "$pkl_src" ] || echo "    - Pkl:    $SAFETY_PKL"
echo "    - Git tag: $TAG"
echo ""
echo "  To undo this rollback later:"
echo "    bash scripts/rollback.sh $CURRENT_STEP  (not currently supported — see README)"
echo "    OR: git revert <new revert commits>"
echo ""

if $DRY_RUN; then
    echo "  [DRY RUN] — no changes will be made."
    exit 0
fi

if ! $SKIP_CONFIRM; then
    read -p "Proceed with rollback? [y/N] " ans
    if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# ─── Pre-flight check ────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  PRE-FLIGHT CHECKS"
echo "============================================================"

# 1. Git tree clean (no uncommitted changes)
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "  ❌ Git tree has uncommitted changes. Commit or stash first."
    git status --short
    exit 1
fi
echo "  ✓ Git tree clean"

# 2. All revert commits exist
for c in $revert_list; do
    if ! git rev-parse --verify "$c" >/dev/null 2>&1; then
        echo "  ❌ Commit $c not found in git history"
        exit 1
    fi
done
echo "  ✓ Revert commits exist: $revert_list"

# 3. Backups exist
[ -d "$models_src" ] && echo "  ✓ Models backup: $models_src"
if [ -n "$pkl_src" ]; then
    [ -f "$pkl_src" ] && echo "  ✓ Pkl backup:    $pkl_src"
fi

# ─── Safety backup ───────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  STEP 1: Safety backup"
echo "============================================================"

echo "  Creating $SAFETY_MODELS ..."
cp -r backtests/models_prod_v22 "$SAFETY_MODELS"
echo "  ✓ models backed up ($(ls "$SAFETY_MODELS" | wc -l) files)"

if [ -n "$pkl_src" ]; then
    echo "  Creating $SAFETY_PKL ..."
    mkdir -p "$(dirname "$SAFETY_PKL")"
    cp cache/bt_features/features.pkl "$SAFETY_PKL"
    echo "  ✓ pkl backed up ($(du -h "$SAFETY_PKL" | cut -f1))"
fi

echo "  Creating git tag $TAG ..."
git tag -a "$TAG" -m "Pre-rollback snapshot: Step $CURRENT_STEP → $TARGET"
echo "  ✓ tag created"

# ─── Apply ───────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  STEP 2: Stop engine"
echo "============================================================"
systemctl --user stop auto-trading.service
echo "  ✓ engine stopped"

echo ""
echo "============================================================"
echo "  STEP 3: Restore artifacts"
echo "============================================================"

if [ -n "$models_src" ]; then
    echo "  Restoring models from $models_src ..."
    rm -rf backtests/models_prod_v22
    cp -r "$models_src" backtests/models_prod_v22
    echo "  ✓ models restored"
fi

if [ -n "$pkl_src" ]; then
    echo "  Restoring pkl from $pkl_src ..."
    cp "$pkl_src" cache/bt_features/features.pkl
    echo "  ✓ pkl restored"
fi

echo ""
echo "============================================================"
echo "  STEP 4: Revert commits"
echo "============================================================"
for c in $revert_list; do
    echo "  Reverting $c ($(git log --oneline -1 $c))"
    git revert --no-edit "$c"
done
echo "  ✓ ${revert_list// /, } reverted"

# ─── Verify ──────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  STEP 5: Verify config"
echo "============================================================"
/home/saengtawan/.pyenv/versions/cc/bin/python -c "
from src.scan.ml_scorer import MLScorer
s = MLScorer()
print(f'  ZONE_THRESHOLDS: {s.ZONE_THRESHOLDS}')
print(f'  ZONE_LOSS_THR:   {s.ZONE_LOSS_THR}')
print(f'  Z4_DIP_FILTER:   {s.Z4_DIP_FILTER}')
print(f'  ZONE_HARD_SL:    {s.ZONE_HARD_SL}')
print(f'  Zone models:     {list(s.zone_tp1_models.keys())}')
"

# ─── Restart ─────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  STEP 6: Restart engine"
echo "============================================================"
systemctl --user start auto-trading.service
sleep 3
if systemctl --user is-active auto-trading.service > /dev/null; then
    echo "  ✓ engine active"
else
    echo "  ❌ engine failed to start — check logs/auto_trading_engine_error.log"
    exit 1
fi

# ─── Report ──────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  ✅ ROLLBACK COMPLETE"
echo "============================================================"
echo "  System is now at: Step $TARGET — ${STEP_DESC[$TARGET]}"
echo ""
echo "  Safety artifacts (if you need to undo):"
echo "    Models: $SAFETY_MODELS"
[ -z "$pkl_src" ] || echo "    Pkl:    $SAFETY_PKL"
echo "    Git tag: $TAG"
echo ""
echo "  To undo this rollback (return to Step $CURRENT_STEP):"
echo "    cp -r $SAFETY_MODELS/* backtests/models_prod_v22/"
[ -z "$pkl_src" ] || echo "    cp $SAFETY_PKL cache/bt_features/features.pkl"
echo "    git revert HEAD~$(echo "$revert_list" | wc -w)..HEAD --no-edit"
echo "    systemctl --user restart auto-trading.service"
echo ""
echo "  Next steps:"
echo "    - Verify engine logs: tail -20 logs/auto_trading_engine_error.log"
echo "    - Push reverts: git push origin master && git push github master"
echo "    - Update CURRENT_STEP in this script if not pushing"
echo ""
