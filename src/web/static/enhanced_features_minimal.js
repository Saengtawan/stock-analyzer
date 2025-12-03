/**
 * Enhanced Features - Minimal Version (2 Features Only)
 * Contains only non-duplicate features:
 * 1. Position Tracker (P&L)
 * 2. Trailing Stop Manager
 */

// Main display function
function displayEnhancedFeaturesMinimal(enhancedData) {
    if (!enhancedData || !enhancedData.features) {
        console.log('No enhanced features data available');
        return;
    }

    const features = enhancedData.features;

    // Show the container
    const container = document.getElementById('enhanced-features-minimal');
    if (container) {
        container.style.display = 'block';
    }

    // Display each feature
    if (features.pnl_tracker) {
        displayPnLTracker(features.pnl_tracker);
    }

    if (features.trailing_stop) {
        displayTrailingStop(features.trailing_stop);
    }
}

// 1. Position Tracker (P&L)
function displayPnLTracker(data) {
    const section = document.getElementById('pnl-tracker-section');
    if (!section) return;

    const entry = data.entry || {};
    const current = data.current || {};
    const targets = data.targets || {};

    // Show section
    section.style.display = 'block';

    // Entry Price - convert safely
    const entryPrice = parseFloat(entry.price) || 0;
    document.getElementById('pnl-entry-price').textContent = `$${entryPrice.toFixed(2)}`;
    document.getElementById('pnl-entry-method').textContent = entry.method || '-';

    // Current P/L - convert safely
    const profitPct = parseFloat(current.profit_pct) || 0;
    const profitDollars = parseFloat(current.profit_dollars) || 0;
    const pnlElement = document.getElementById('pnl-profit-pct');
    const pnlDollarsElement = document.getElementById('pnl-profit-dollars');

    pnlElement.textContent = `${profitPct >= 0 ? '+' : ''}${profitPct.toFixed(2)}%`;
    pnlElement.className = `h4 mb-0 ${profitPct >= 0 ? 'text-success' : 'text-danger'}`;

    pnlDollarsElement.textContent = `${profitDollars >= 0 ? '+' : ''}$${Math.abs(profitDollars).toFixed(2)}`;
    pnlDollarsElement.className = `text-muted small ${profitPct >= 0 ? 'text-success' : 'text-danger'}`;

    // Progress to TP1 - get from correct nested structure
    const tp1Data = targets.tp1 || {};
    const tp2Data = targets.tp2 || {};
    const tp1Progress = parseFloat(tp1Data.progress_pct) || 0;

    document.getElementById('pnl-tp1-progress').textContent = `${tp1Progress.toFixed(0)}%`;

    const progressBar = document.getElementById('pnl-progress-bar');
    progressBar.style.width = `${Math.min(100, tp1Progress)}%`;

    // Color based on progress
    if (tp1Progress >= 75) {
        progressBar.className = 'progress-bar bg-success';
    } else if (tp1Progress >= 50) {
        progressBar.className = 'progress-bar bg-info';
    } else if (tp1Progress >= 25) {
        progressBar.className = 'progress-bar bg-warning';
    } else {
        progressBar.className = 'progress-bar bg-secondary';
    }

    // Target Prices - get from nested structure
    const tp1Price = parseFloat(tp1Data.price) || 0;
    const tp2Price = parseFloat(tp2Data.price) || 0;

    // Get probability data
    const tp1Probability = tp1Data.probability || {};
    const tp2Probability = tp2Data.probability || {};

    const tp1ProbPct = parseFloat(tp1Probability.probability_pct) || 0;
    const tp1DaysReached = tp1Probability.days_reached || 0;
    const tp1TotalDays = tp1Probability.total_days || 0;

    const tp2ProbPct = parseFloat(tp2Probability.probability_pct) || 0;
    const tp2DaysReached = tp2Probability.days_reached || 0;
    const tp2TotalDays = tp2Probability.total_days || 0;

    // Format TP1 with probability
    const tp1Text = `$${tp1Price.toFixed(2)}`;
    const tp1ProbText = tp1TotalDays > 0
        ? `<br><small class="text-muted">📊 ${tp1ProbPct.toFixed(1)}% chance (reached ${tp1DaysReached}/${tp1TotalDays} days)</small>`
        : '';

    // Format TP2 with probability
    const tp2Text = `$${tp2Price.toFixed(2)}`;
    const tp2ProbText = tp2TotalDays > 0
        ? `<br><small class="text-muted">📊 ${tp2ProbPct.toFixed(1)}% chance (reached ${tp2DaysReached}/${tp2TotalDays} days)</small>`
        : '';

    document.getElementById('pnl-tp1-price').innerHTML = tp1Text + tp1ProbText;
    document.getElementById('pnl-tp2-price').innerHTML = tp2Text + tp2ProbText;
}

// 2. Trailing Stop Manager
function displayTrailingStop(data) {
    const section = document.getElementById('trailing-stop-section');
    if (!section) return;

    // Show section
    section.style.display = 'block';

    // Handle should_move as string "True"/"False" or boolean
    const shouldMove = (data.should_move === 'True' || data.should_move === true);
    const originalSL = parseFloat(data.original_sl) || 0;
    const newSL = parseFloat(data.recommended_sl) || parseFloat(data.new_sl) || 0;

    // Get locked profit from nested structure
    const lockedProfitData = data.locked_profit || {};
    const lockedProfit = parseFloat(lockedProfitData.percentage) || parseFloat(data.locked_profit_pct) || 0;

    // Alert styling based on recommendation
    const alertElement = document.getElementById('trailing-alert');
    if (shouldMove) {
        alertElement.className = 'alert alert-success';
        document.getElementById('trailing-recommendation').textContent =
            '✅ Move Stop Loss Up!';
        document.getElementById('trailing-detail').textContent = data.reason ||
            'You have sufficient profit to protect. Consider moving your stop loss.';
    } else {
        alertElement.className = 'alert alert-secondary';
        document.getElementById('trailing-recommendation').textContent =
            '⏸️ Keep Current Stop Loss';
        document.getElementById('trailing-detail').textContent = data.reason ||
            'No adjustment needed at this time.';
    }

    // SL Prices
    document.getElementById('trailing-original-sl').textContent = `$${originalSL.toFixed(2)}`;
    document.getElementById('trailing-new-sl').textContent = `$${newSL.toFixed(2)}`;

    // Locked Profit
    const lockedProfitText = lockedProfit > 0
        ? `+${lockedProfit.toFixed(1)}% guaranteed if stopped out at new SL`
        : 'No profit locked yet';
    document.getElementById('trailing-locked-profit').textContent = lockedProfitText;
}

// Format helper functions
function formatCurrency(value) {
    return `$${Math.abs(value).toFixed(2)}`;
}

function formatPercent(value) {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        displayEnhancedFeaturesMinimal,
        displayPnLTracker,
        displayTrailingStop
    };
}
