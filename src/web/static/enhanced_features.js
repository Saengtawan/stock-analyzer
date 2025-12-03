/**
 * Enhanced Features JavaScript
 * Displays 6 enhanced features in the UI
 */

function displayEnhancedFeatures(enhancedData) {
    if (!enhancedData || !enhancedData.features) {
        console.warn('No enhanced features data available');
        return;
    }

    // Show the section
    document.getElementById('enhanced-features-section').style.display = 'block';

    const features = enhancedData.features;

    // Feature 1: Real-Time Price Monitor
    displayPriceMonitor(features.price_monitor);

    // Feature 2: P&L Tracker
    if (features.pnl_tracker) {
        displayPnLTracker(features.pnl_tracker);
    }

    // Feature 3: Trailing Stop
    if (features.trailing_stop) {
        displayTrailingStop(features.trailing_stop);
    }

    // Feature 4: Short Interest
    displayShortInterest(features.short_interest);

    // Feature 5: Decision Matrix
    displayDecisionMatrix(features.decision_matrix);

    // Feature 6: Risk Alerts
    if (features.risk_alerts && features.risk_alerts.alerts.length > 0) {
        displayRiskAlerts(features.risk_alerts);
    }
}

function displayPriceMonitor(data) {
    if (!data) return;

    const readiness = data.readiness;
    const display = data.display;
    const conditions = data.conditions;

    // Readiness score with color
    const scoreEl = document.getElementById('readiness-score');
    scoreEl.textContent = `${readiness.score}/100`;
    scoreEl.className = `text-3xl font-bold ${getScoreColor(readiness.score)}`;

    // Status
    document.getElementById('readiness-status').textContent = display.header;

    // Current price
    document.getElementById('current-price-display').textContent = display.price_status;
    document.getElementById('entry-zone-display').textContent = display.entry_zone;

    // Conditions checklist
    const conditionsList = document.getElementById('entry-conditions-list');
    conditionsList.innerHTML = '';
    Object.values(conditions).forEach(cond => {
        const div = document.createElement('div');
        div.className = `flex items-center ${cond.passed ? 'text-green-600' : 'text-gray-500'}`;
        div.innerHTML = `
            <span class="mr-2">${cond.passed ? '✅' : '❌'}</span>
            <span>${cond.message}</span>
        `;
        conditionsList.appendChild(div);
    });

    // Next action
    document.getElementById('next-action-text').innerHTML = `
        ${display.next_action}<br>
        <span class="text-sm text-gray-600">${display.estimated_wait}</span>
    `;
}

function displayPnLTracker(data) {
    if (!data) return;

    const entry = data.entry;
    const current = data.current;
    const targets = data.targets;

    // Entry price
    document.getElementById('entry-price-display').textContent = `$${entry.price.toFixed(2)}`;
    document.getElementById('entry-method-display').textContent = entry.description;

    // Profit/Loss
    const profitEl = document.getElementById('profit-display');
    const profitPct = current.profit_pct;
    profitEl.textContent = `${profitPct >= 0 ? '+' : ''}${profitPct.toFixed(2)}%`;
    profitEl.className = `text-2xl font-bold ${profitPct >= 0 ? 'text-green-600' : 'text-red-600'}`;

    document.getElementById('profit-dollars-display').textContent =
        `$${current.profit_dollars >= 0 ? '+' : ''}${current.profit_dollars.toFixed(2)}`;

    // Progress to TP1
    const tp1Progress = targets.tp1.progress_pct;
    document.getElementById('tp1-progress-pct').textContent = `${tp1Progress.toFixed(0)}%`;

    // Progress bar
    const progressBar = document.getElementById('tp1-progress-bar');
    progressBar.innerHTML = `
        <div class="bg-blue-600 h-2 rounded-full transition-all duration-500"
             style="width: ${Math.min(tp1Progress, 100)}%"></div>
    `;

    // Targets
    document.getElementById('tp1-price').textContent = `$${targets.tp1.price.toFixed(2)}`;
    document.getElementById('tp2-price').textContent = `$${targets.tp2.price.toFixed(2)}`;
}

function displayTrailingStop(data) {
    if (!data) return;

    const display = data.display;
    const shouldMove = data.should_move;

    // Recommendation
    const recEl = document.getElementById('trailing-stop-recommendation');
    recEl.textContent = display.recommendation;
    recEl.className = `text-lg font-semibold mb-2 ${shouldMove ? 'text-green-600' : 'text-gray-600'}`;

    document.getElementById('trailing-stop-detail').textContent = display.recommendation_detail;

    // Stop loss levels
    document.getElementById('original-sl').textContent = display.original_sl;
    document.getElementById('recommended-sl').textContent = display.new_sl;

    // Locked profit
    document.getElementById('locked-profit').textContent = display.locked_profit;
}

function displayShortInterest(data) {
    if (!data) return;

    const si = data.short_interest;
    const squeeze = data.squeeze;
    const display = data.display;

    // Short interest percentage
    document.getElementById('short-interest-pct').textContent = display.short_pct;

    // Days to cover
    document.getElementById('days-to-cover').textContent = display.days_to_cover;

    // Squeeze potential
    const squeezeEl = document.getElementById('squeeze-potential');
    squeezeEl.textContent = display.squeeze_potential;

    // Interpretation
    document.getElementById('short-interpretation').textContent = display.interpretation;
}

function displayDecisionMatrix(data) {
    if (!data) return;

    const decision = data.decision;
    const display = data.display;

    // Action
    document.getElementById('decision-action').textContent = display.action_header;

    // Confidence
    document.getElementById('decision-confidence').textContent = `${decision.confidence}%`;

    // Confidence bar
    const confBar = document.getElementById('confidence-bar');
    confBar.innerHTML = `
        <div class="bg-white rounded-full h-4 transition-all duration-500"
             style="width: ${decision.confidence}%"></div>
    `;

    // Reasons for
    const reasonsFor = document.getElementById('reasons-for');
    reasonsFor.innerHTML = '';
    const positiveReasons = decision.reasons_for || decision.reasons_for_selling || [];
    positiveReasons.forEach(reason => {
        const li = document.createElement('li');
        li.textContent = reason;
        reasonsFor.appendChild(li);
    });

    // Reasons against
    const reasonsAgainst = document.getElementById('reasons-against');
    reasonsAgainst.innerHTML = '';
    const negativeReasons = decision.reasons_against || decision.reasons_for_holding || [];
    negativeReasons.forEach(reason => {
        const li = document.createElement('li');
        li.textContent = reason;
        reasonsAgainst.appendChild(li);
    });

    // Action plan
    const actionPlan = document.getElementById('action-plan');
    actionPlan.innerHTML = '';
    decision.action_plan.forEach(step => {
        const li = document.createElement('li');
        li.textContent = step;
        li.className = 'font-medium';
        actionPlan.appendChild(li);
    });
}

function displayRiskAlerts(data) {
    if (!data) return;

    const riskScore = data.risk_score;
    const alerts = data.alerts;
    const actions = data.recommended_actions;

    // Show container
    document.getElementById('risk-alerts-container').style.display = 'block';

    // Risk status
    document.getElementById('risk-status').innerHTML = data.display.status;
    document.getElementById('risk-score').textContent = data.display.score;

    // Active alerts
    const alertsContainer = document.getElementById('active-alerts');
    alertsContainer.innerHTML = '';

    alerts.forEach((alert, index) => {
        const div = document.createElement('div');
        const severityColor = {
            'HIGH': 'bg-red-100 border-red-300',
            'MEDIUM': 'bg-yellow-100 border-yellow-300',
            'LOW': 'bg-blue-100 border-blue-300'
        }[alert.severity] || 'bg-gray-100 border-gray-300';

        div.className = `border-l-4 p-4 ${severityColor}`;
        div.innerHTML = `
            <div class="font-semibold">${index + 1}. ${alert.type.replace(/_/g, ' ')}</div>
            <div class="text-sm mt-1">${alert.message}</div>
            <div class="text-sm text-gray-600 mt-1">💡 ${alert.action}</div>
        `;
        alertsContainer.appendChild(div);
    });

    // Recommended actions
    const actionsList = document.getElementById('risk-actions');
    actionsList.innerHTML = '';
    actions.forEach(action => {
        const li = document.createElement('li');
        li.textContent = action;
        actionsList.appendChild(li);
    });
}

// Helper functions
function getScoreColor(score) {
    if (score >= 75) return 'text-green-600';
    if (score >= 50) return 'text-yellow-600';
    return 'text-red-600';
}

// Export for use in analyze.html
window.displayEnhancedFeatures = displayEnhancedFeatures;
