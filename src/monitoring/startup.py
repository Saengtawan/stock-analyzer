"""
Monitoring Startup Hook
=======================
Initialize monitoring when the application starts.

Add this to your main app initialization:
    from monitoring.startup import initialize_monitoring
    initialize_monitoring()
"""

from loguru import logger

from .auto_monitor import get_auto_monitor


def initialize_monitoring(
    auto_start: bool = True,
    health_check_interval: int = 300,  # 5 minutes
    alert_threshold: float = 70.0,
    log_alerts: bool = True
):
    """
    Initialize monitoring system on application startup.

    Args:
        auto_start: Automatically start background monitoring (default: True)
        health_check_interval: Seconds between health checks (default: 300)
        alert_threshold: Health score threshold for alerts (default: 70)
        log_alerts: Log alerts to console (default: True)

    Returns:
        AutoMonitor instance
    """
    logger.info("Initializing monitoring system...")

    # Get monitor instance
    monitor = get_auto_monitor()

    # Configure
    monitor.health_check_interval = health_check_interval
    monitor.alert_threshold = alert_threshold

    # Add logging callback if requested
    if log_alerts:
        def log_alert(alert):
            level_map = {
                'health': 'WARNING',
                'performance': 'WARNING',
                'error': 'ERROR'
            }
            level = level_map.get(alert['type'], 'WARNING')
            logger.log(level, f"ALERT [{alert['type']}]: {alert['message']}")

        monitor.add_alert_callback(log_alert)

    # Start if requested
    if auto_start:
        monitor.start()
        logger.info(f"✅ Automatic monitoring started (checks every {health_check_interval}s)")
    else:
        logger.info("⏸️  Automatic monitoring initialized but not started")

    return monitor


def shutdown_monitoring():
    """
    Shutdown monitoring system on application shutdown.

    Add this to your shutdown hooks:
        from monitoring.startup import shutdown_monitoring
        shutdown_monitoring()
    """
    logger.info("Shutting down monitoring system...")

    monitor = get_auto_monitor()
    if monitor.is_running():
        monitor.stop()
        logger.info("✅ Monitoring stopped")
    else:
        logger.info("⏸️  Monitoring was not running")
