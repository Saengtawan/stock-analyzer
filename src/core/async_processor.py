"""
Async and Concurrent Processing Utilities
Provides efficient parallel processing for API calls and data operations
"""
from typing import List, Dict, Any, Callable, Optional, TypeVar, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
import asyncio
from functools import wraps
from loguru import logger
import time

from .exceptions import APITimeoutException, AnalysisTimeoutException

T = TypeVar('T')


class ConcurrentProcessor:
    """Handles concurrent processing using thread pools"""

    def __init__(self, max_workers: int = 5):
        """
        Initialize concurrent processor

        Args:
            max_workers: Maximum number of concurrent workers
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def process_batch(
        self,
        items: List[Any],
        process_func: Callable[[Any], T],
        timeout: Optional[float] = 30.0,
        return_exceptions: bool = True
    ) -> List[Tuple[Any, Optional[T], Optional[Exception]]]:
        """
        Process a batch of items concurrently

        Args:
            items: List of items to process
            process_func: Function to apply to each item
            timeout: Timeout for each task (seconds)
            return_exceptions: If True, return exceptions instead of raising

        Returns:
            List of (item, result, exception) tuples

        Example:
            processor = ConcurrentProcessor(max_workers=5)
            symbols = ['AAPL', 'MSFT', 'GOOGL']
            results = processor.process_batch(
                symbols,
                lambda s: fetch_stock_data(s),
                timeout=10.0
            )
        """
        futures_to_items: Dict[Future, Any] = {}

        # Submit all tasks
        for item in items:
            future = self.executor.submit(process_func, item)
            futures_to_items[future] = item

        results = []

        # Collect results as they complete
        for future in as_completed(futures_to_items, timeout=timeout):
            item = futures_to_items[future]

            try:
                result = future.result(timeout=timeout)
                results.append((item, result, None))

                logger.debug(f"Successfully processed item: {item}")

            except Exception as e:
                logger.warning(
                    f"Error processing item {item}: {e}",
                    extra={
                        'item': item,
                        'error': str(e),
                        'error_type': type(e).__name__
                    }
                )

                if return_exceptions:
                    results.append((item, None, e))
                else:
                    raise

        return results

    def process_with_progress(
        self,
        items: List[Any],
        process_func: Callable[[Any], T],
        timeout: Optional[float] = 30.0,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Tuple[Any, Optional[T], Optional[Exception]]]:
        """
        Process batch with progress reporting

        Args:
            items: List of items to process
            process_func: Function to apply to each item
            timeout: Timeout for each task
            progress_callback: Called with (completed, total) after each item

        Returns:
            List of (item, result, exception) tuples
        """
        futures_to_items: Dict[Future, Any] = {}
        total = len(items)
        completed = 0

        # Submit all tasks
        for item in items:
            future = self.executor.submit(process_func, item)
            futures_to_items[future] = item

        results = []

        # Collect results with progress updates
        for future in as_completed(futures_to_items, timeout=timeout):
            item = futures_to_items[future]

            try:
                result = future.result(timeout=timeout)
                results.append((item, result, None))
            except Exception as e:
                results.append((item, None, e))

            completed += 1

            # Call progress callback
            if progress_callback:
                progress_callback(completed, total)

        return results

    def map_concurrent(
        self,
        items: List[Any],
        process_func: Callable[[Any], T],
        timeout: Optional[float] = None
    ) -> List[T]:
        """
        Map function over items concurrently (similar to map())

        Args:
            items: List of items
            process_func: Function to apply
            timeout: Overall timeout for all operations

        Returns:
            List of results (in same order as input)
        """
        start_time = time.time()

        futures_to_indices: Dict[Future, int] = {}

        # Submit all tasks with index tracking
        for i, item in enumerate(items):
            future = self.executor.submit(process_func, item)
            futures_to_indices[future] = i

        # Collect results in order
        results: List[Optional[T]] = [None] * len(items)

        for future in as_completed(futures_to_indices, timeout=timeout):
            if timeout:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise APITimeoutException("batch_processing", int(timeout))

            index = futures_to_indices[future]
            try:
                results[index] = future.result()
            except Exception as e:
                logger.error(f"Error processing item at index {index}: {e}")
                raise

        return results

    def shutdown(self, wait: bool = True):
        """Shutdown the executor"""
        self.executor.shutdown(wait=wait)

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.shutdown()


class AsyncProcessor:
    """Handles async processing"""

    @staticmethod
    async def gather_with_timeout(
        tasks: List[asyncio.Task],
        timeout: float,
        return_exceptions: bool = True
    ) -> List[Any]:
        """
        Gather async tasks with timeout

        Args:
            tasks: List of async tasks
            timeout: Timeout in seconds
            return_exceptions: Return exceptions instead of raising

        Returns:
            List of results
        """
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=return_exceptions),
                timeout=timeout
            )
            return results
        except asyncio.TimeoutError:
            # Cancel pending tasks
            for task in tasks:
                if not task.done():
                    task.cancel()

            raise APITimeoutException("async_batch", int(timeout))

    @staticmethod
    async def process_batch_async(
        items: List[Any],
        process_func: Callable[[Any], asyncio.Future],
        max_concurrent: int = 5,
        timeout: Optional[float] = None
    ) -> List[Tuple[Any, Optional[Any], Optional[Exception]]]:
        """
        Process batch of items asynchronously with concurrency limit

        Args:
            items: Items to process
            process_func: Async function to process each item
            max_concurrent: Maximum concurrent tasks
            timeout: Timeout per task

        Returns:
            List of (item, result, exception) tuples
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []

        async def process_with_semaphore(item):
            async with semaphore:
                try:
                    if timeout:
                        result = await asyncio.wait_for(
                            process_func(item),
                            timeout=timeout
                        )
                    else:
                        result = await process_func(item)

                    return (item, result, None)

                except Exception as e:
                    logger.warning(f"Error processing {item}: {e}")
                    return (item, None, e)

        # Create tasks
        tasks = [process_with_semaphore(item) for item in items]

        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=False)

        return results


class BatchProcessor:
    """High-level batch processor that chooses best strategy"""

    def __init__(
        self,
        max_workers: int = 5,
        default_timeout: float = 30.0
    ):
        """
        Initialize batch processor

        Args:
            max_workers: Maximum concurrent workers
            default_timeout: Default timeout for operations
        """
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.concurrent_processor = ConcurrentProcessor(max_workers)

    def process_symbols(
        self,
        symbols: List[str],
        fetch_func: Callable[[str], Dict[str, Any]],
        timeout: Optional[float] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Process multiple stock symbols concurrently

        Args:
            symbols: List of stock symbols
            fetch_func: Function to fetch data for a symbol
            timeout: Timeout per symbol

        Returns:
            Dictionary mapping symbol to data

        Example:
            processor = BatchProcessor(max_workers=5)
            data = processor.process_symbols(
                ['AAPL', 'MSFT', 'GOOGL'],
                lambda s: fetch_stock_data(s),
                timeout=10.0
            )
        """
        if timeout is None:
            timeout = self.default_timeout

        logger.info(f"Processing {len(symbols)} symbols concurrently")

        results = self.concurrent_processor.process_batch(
            symbols,
            fetch_func,
            timeout=timeout,
            return_exceptions=True
        )

        # Convert to dictionary
        data = {}
        errors = []

        for symbol, result, error in results:
            if error:
                errors.append((symbol, error))
                logger.warning(f"Failed to fetch data for {symbol}: {error}")
            else:
                data[symbol] = result

        if errors:
            logger.warning(
                f"Failed to fetch data for {len(errors)}/{len(symbols)} symbols",
                extra={'failed_symbols': [s for s, _ in errors]}
            )

        logger.info(f"Successfully fetched data for {len(data)}/{len(symbols)} symbols")

        return data

    def process_with_fallback(
        self,
        items: List[Any],
        primary_func: Callable[[Any], T],
        fallback_func: Callable[[Any], T],
        timeout: Optional[float] = None
    ) -> List[T]:
        """
        Process items with fallback function if primary fails

        Args:
            items: Items to process
            primary_func: Primary processing function
            fallback_func: Fallback function if primary fails
            timeout: Timeout per item

        Returns:
            List of results
        """
        if timeout is None:
            timeout = self.default_timeout

        results = self.concurrent_processor.process_batch(
            items,
            primary_func,
            timeout=timeout,
            return_exceptions=True
        )

        final_results = []

        for item, result, error in results:
            if error:
                # Try fallback
                logger.info(f"Using fallback function for {item}")
                try:
                    fallback_result = fallback_func(item)
                    final_results.append(fallback_result)
                except Exception as e:
                    logger.error(f"Fallback also failed for {item}: {e}")
                    raise
            else:
                final_results.append(result)

        return final_results

    def shutdown(self):
        """Shutdown the processor"""
        self.concurrent_processor.shutdown()


# Decorator for making functions concurrent
def concurrent(max_workers: int = 5, timeout: float = 30.0):
    """
    Decorator to make a function process lists concurrently

    Args:
        max_workers: Maximum concurrent workers
        timeout: Timeout per item

    Example:
        @concurrent(max_workers=10, timeout=15.0)
        def fetch_multiple_stocks(symbols: List[str]) -> List[Dict]:
            # This will be called concurrently for each symbol
            return [fetch_stock_data(s) for s in symbols]
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(items: List[Any], *args, **kwargs) -> List[Any]:
            processor = ConcurrentProcessor(max_workers)

            try:
                results = processor.process_batch(
                    items,
                    lambda item: func(item, *args, **kwargs),
                    timeout=timeout,
                    return_exceptions=False
                )
                return [result for _, result, _ in results]
            finally:
                processor.shutdown()

        return wrapper
    return decorator
