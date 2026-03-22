"""
Auto-Refit Orchestrator — runs all periodic maintenance tasks.
Part of Discovery v10.0 Full Autonomous System.

Every 30 days during scan:
  1. Refit ML brains (RegimeBrain, StockBrain)
  2. Optimize parameters (grid search)
  3. Track performance (P&L)
  4. Detect model drift
  5. Health check
"""
import logging
import time

logger = logging.getLogger(__name__)


class AutoRefitOrchestrator:
    """Orchestrate all periodic maintenance tasks."""

    def __init__(self, regime_brain, stock_brain, param_optimizer,
                 performance_tracker, param_manager, adaptive_params=None,
                 knowledge_graph=None, neural_graph=None):
        self._regime_brain = regime_brain
        self._stock_brain = stock_brain
        self._param_optimizer = param_optimizer
        self._perf_tracker = performance_tracker
        self._params = param_manager
        self._adaptive = adaptive_params
        self._knowledge_graph = knowledge_graph
        self._neural_graph = neural_graph
        self._last_run = 0.0
        self._last_results = {}

    def needs_run(self, days: int = 30) -> bool:
        if self._last_run == 0:
            return True
        return (time.time() - self._last_run) > days * 86400

    def run_cycle(self) -> dict:
        """Run full maintenance cycle. Returns summary."""
        logger.info("AutoRefit: starting maintenance cycle")
        results = {}

        # 1. Track performance
        try:
            perf = self._perf_tracker.track_daily()
            results['performance'] = perf
            logger.info("AutoRefit: performance tracking done (%d days)", perf.get('recorded', 0))
        except Exception as e:
            logger.error("AutoRefit: performance tracking error: %s", e)
            results['performance'] = {'error': str(e)}

        # 2. Detect drift
        try:
            drift = self._perf_tracker.detect_drift()
            results['drift'] = drift
            if drift['drift'] != 'NORMAL':
                logger.warning("AutoRefit: %s — forcing immediate refit", drift['drift'])
        except Exception as e:
            logger.error("AutoRefit: drift detection error: %s", e)
            results['drift'] = {'drift': 'ERROR'}

        # 3. Refit ML brains
        try:
            if self._regime_brain.needs_refit(30):
                self._regime_brain.fit()
                results['regime_refit'] = True
                logger.info("AutoRefit: RegimeBrain refitted")
            else:
                results['regime_refit'] = False
        except Exception as e:
            logger.error("AutoRefit: RegimeBrain refit error: %s", e)

        try:
            if self._stock_brain.needs_refit(30):
                self._stock_brain.fit()
                results['stock_refit'] = True
                logger.info("AutoRefit: StockBrain refitted")
            else:
                results['stock_refit'] = False
        except Exception as e:
            logger.error("AutoRefit: StockBrain refit error: %s", e)

        # 4. Optimize parameters
        try:
            if self._param_optimizer.needs_optimize(30):
                opt_results = self._param_optimizer.optimize_all()
                results['optimization'] = opt_results
                logger.info("AutoRefit: params optimized: %s", opt_results)
            else:
                results['optimization'] = 'not_needed'
        except Exception as e:
            logger.error("AutoRefit: optimization error: %s", e)
            results['optimization'] = {'error': str(e)}

        # 5. Refit adaptive parameters
        if self._adaptive:
            try:
                if self._adaptive.needs_refit(30):
                    self._adaptive.fit()
                    results['adaptive_refit'] = True
                    logger.info("AutoRefit: adaptive params refitted (%s)",
                                self._adaptive.get_stats())
                else:
                    results['adaptive_refit'] = False
            except Exception as e:
                logger.error("AutoRefit: adaptive params error: %s", e)
                results['adaptive_refit'] = {'error': str(e)}

        # 6. Rebuild Knowledge Graph (macro sensitivities + speculative flags)
        if self._knowledge_graph:
            try:
                self._knowledge_graph.build_all()
                results['kg_rebuild'] = True
                logger.info("AutoRefit: KnowledgeGraph rebuilt (%s)",
                            self._knowledge_graph.get_stats())
            except Exception as e:
                logger.error("AutoRefit: KG rebuild error: %s", e)
                results['kg_rebuild'] = {'error': str(e)}

        # 7. Rebuild Neural Graph (clusters + vulnerability)
        if self._neural_graph:
            try:
                self._neural_graph.build_all()
                results['neural_graph'] = True
                logger.info("AutoRefit: NeuralGraph rebuilt (%s)",
                            self._neural_graph.get_stats())
            except Exception as e:
                logger.error("AutoRefit: NeuralGraph error: %s", e)
                results['neural_graph'] = {'error': str(e)}

        # 8. Health check
        try:
            drift_status = results.get('drift', {}).get('drift', 'UNKNOWN')
            if drift_status == 'MODEL_FAILING':
                # Emergency: force refit with latest data
                logger.warning("AutoRefit: MODEL_FAILING — emergency refit!")
                self._regime_brain.fit()
                self._stock_brain.fit()
                results['emergency_refit'] = True
            else:
                results['emergency_refit'] = False
        except Exception as e:
            logger.error("AutoRefit: health check error: %s", e)

        self._last_run = time.time()
        self._last_results = results

        logger.info("AutoRefit: cycle complete: %s",
                     {k: v for k, v in results.items() if k != 'optimization'})
        return results

    def get_stats(self) -> dict:
        return {
            'last_run': self._last_run,
            'needs_run': self.needs_run(30),
            'last_results': self._last_results,
        }
