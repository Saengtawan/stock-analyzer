"""
Utility functions for the Stock Analyzer
"""
import json
import numpy as np
import pandas as pd
from typing import Any
from enum import Enum


def make_json_serializable(obj: Any) -> Any:
    """
    Convert numpy arrays, pandas DataFrames and other non-serializable objects to JSON-serializable format

    Args:
        obj: Object to convert

    Returns:
        JSON-serializable object
    """
    if isinstance(obj, pd.DataFrame):
        # Convert DataFrame to list of dicts and clean each value
        records = obj.to_dict('records')
        return [make_json_serializable(record) for record in records]
    elif isinstance(obj, pd.Series):
        # Convert Series to dict and clean each value
        series_dict = obj.to_dict()
        return {str(key): make_json_serializable(value) for key, value in series_dict.items()}
    elif isinstance(obj, np.ndarray):
        # Convert array to list and clean each element
        return [make_json_serializable(item) for item in obj.tolist()]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, int):
        return obj
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        # Handle NaN and infinite values
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, float):
        # Handle Python float NaN and infinite values
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    elif isinstance(obj, Enum):  # Handle Enum objects (like TimeFrame)
        return obj.value
    elif isinstance(obj, dict):
        return {key: make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return [make_json_serializable(item) for item in obj]
    elif hasattr(obj, 'isoformat'):  # datetime objects
        return obj.isoformat()
    elif pd.isna(obj):  # Handle pandas NaN
        return None
    else:
        # Try to convert to string for unknown objects
        try:
            return str(obj)
        except:
            return None


def clean_analysis_results(results: dict) -> dict:
    """
    Clean analysis results to ensure JSON serializability

    Args:
        results: Analysis results dictionary

    Returns:
        Cleaned results dictionary
    """
    return make_json_serializable(results)