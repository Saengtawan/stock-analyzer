#!/usr/bin/env python3
"""
Test Parallel Performance - ThreadPool vs ProcessPool
"""
import time
import sys
import os
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

# Add parent directory to path
sys.path.append(os.path.dirname(__file__))

from main import StockAnalyzer
from screeners.support_level_screener import SupportLevelScreener
from screeners.dividend_screener import DividendGrowthScreener
from loguru import logger


def test_single_stock_analysis(symbol):
    """Test single stock analysis for timing"""
    analyzer = StockAnalyzer()
    start_time = time.time()
    result = analyzer.analyze_stock(symbol, time_horizon='medium')
    end_time = time.time()
    return symbol, end_time - start_time, 'error' not in result


def test_parallel_methods():
    """Test different parallel processing methods"""
    logger.info("Testing Parallel Processing Methods...")

    # Test symbols
    test_symbols = ['SPYI', 'SPY', 'AAPL', 'MSFT', 'VYM', 'QQQ', 'VTI', 'BND']

    # 1. Sequential processing
    logger.info("=== 1. Sequential Processing ===")
    start_time = time.time()
    sequential_results = []
    for symbol in test_symbols:
        result = test_single_stock_analysis(symbol)
        sequential_results.append(result)
    sequential_time = time.time() - start_time
    successful_sequential = sum(1 for _, _, success in sequential_results if success)
    logger.info(f"Sequential: {sequential_time:.2f}s, {successful_sequential}/{len(test_symbols)} successful")

    # 2. ThreadPoolExecutor with 8 workers
    logger.info("\n=== 2. ThreadPoolExecutor (8 workers) ===")
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(test_single_stock_analysis, symbol) for symbol in test_symbols]
        thread8_results = [future.result() for future in futures]
    thread8_time = time.time() - start_time
    successful_thread8 = sum(1 for _, _, success in thread8_results if success)
    logger.info(f"ThreadPool(8): {thread8_time:.2f}s, {successful_thread8}/{len(test_symbols)} successful")

    # 3. ThreadPoolExecutor with 16 workers
    logger.info("\n=== 3. ThreadPoolExecutor (16 workers) ===")
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(test_single_stock_analysis, symbol) for symbol in test_symbols]
        thread16_results = [future.result() for future in futures]
    thread16_time = time.time() - start_time
    successful_thread16 = sum(1 for _, _, success in thread16_results if success)
    logger.info(f"ThreadPool(16): {thread16_time:.2f}s, {successful_thread16}/{len(test_symbols)} successful")

    # 4. ProcessPoolExecutor with 8 workers
    logger.info("\n=== 4. ProcessPoolExecutor (8 workers) ===")
    start_time = time.time()
    try:
        with ProcessPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(test_single_stock_analysis, symbol) for symbol in test_symbols]
            process8_results = [future.result() for future in futures]
        process8_time = time.time() - start_time
        successful_process8 = sum(1 for _, _, success in process8_results if success)
        logger.info(f"ProcessPool(8): {process8_time:.2f}s, {successful_process8}/{len(test_symbols)} successful")
    except Exception as e:
        logger.error(f"ProcessPool failed: {e}")
        process8_time = float('inf')

    # Results summary
    logger.info("\n=== Performance Summary ===")
    logger.info(f"Sequential:      {sequential_time:.2f}s (baseline)")
    logger.info(f"ThreadPool(8):   {thread8_time:.2f}s ({sequential_time/thread8_time:.2f}x faster)")
    logger.info(f"ThreadPool(16):  {thread16_time:.2f}s ({sequential_time/thread16_time:.2f}x faster)")
    if process8_time != float('inf'):
        logger.info(f"ProcessPool(8):  {process8_time:.2f}s ({sequential_time/process8_time:.2f}x faster)")

    # Best method
    methods = [
        ("Sequential", sequential_time),
        ("ThreadPool(8)", thread8_time),
        ("ThreadPool(16)", thread16_time),
    ]
    if process8_time != float('inf'):
        methods.append(("ProcessPool(8)", process8_time))

    best_method, best_time = min(methods, key=lambda x: x[1])
    logger.info(f"\n🏆 Best method: {best_method} with {best_time:.2f}s")

    return best_method, best_time


if __name__ == "__main__":
    best_method, best_time = test_parallel_methods()
    logger.success(f"🎉 Optimal parallel method: {best_method}")