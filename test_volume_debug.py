#!/usr/bin/env python3
"""
Debug Volume Calculation - ตรวจสอบว่าทำไม volume ratio ต่ำผิดปกติ
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from api.data_manager import DataManager
import pandas as pd
from loguru import logger
import warnings
warnings.filterwarnings('ignore')

logger.info("=" * 80)
logger.info("🔬 DEBUG VOLUME CALCULATION")
logger.info("=" * 80)
logger.info("")

dm = DataManager()

# Test with stocks that showed low volume ratio
test_stocks = ['NVDA', 'AMZN', 'TSLA', 'AAPL']

for symbol in test_stocks:
    logger.info(f"📊 Testing {symbol}:")
    logger.info("-" * 40)
    
    try:
        # Get price data (same as screener)
        data = dm.get_price_data(symbol, period='90d', interval='1d')
        
        if data is None or data.empty:
            logger.error(f"   ❌ No data received")
            continue
        
        logger.info(f"   Data shape: {data.shape}")
        logger.info(f"   Columns: {data.columns.tolist()}")
        logger.info(f"   Index type: {type(data.index)}")
        
        # Check volume column
        if 'Volume' in data.columns:
            volume = data['Volume']
        elif 'volume' in data.columns:
            volume = data['volume']
        else:
            logger.error(f"   ❌ No Volume column found!")
            continue
        
        # Show last 5 days
        logger.info(f"\n   Last 5 days of volume data:")
        logger.info(f"   {volume.tail(5).to_dict()}")
        
        # Calculate volume ratio (same as screener)
        if len(volume) >= 20:
            avg_volume = volume.rolling(window=20).mean().iloc[-1]
            current_volume = volume.iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            logger.info(f"\n   Current volume: {current_volume:,.0f}")
            logger.info(f"   20-day avg volume: {avg_volume:,.0f}")
            logger.info(f"   📊 Volume Ratio: {volume_ratio:.2f}x")
            
            # Check if volume data looks normal
            if avg_volume < 1000:
                logger.warning(f"   ⚠️ WARNING: Average volume too low ({avg_volume:.0f}) - data might be scaled!")
            
            if volume_ratio < 0.5:
                logger.warning(f"   ⚠️ WARNING: Volume ratio unusually low!")
            elif volume_ratio > 3.0:
                logger.warning(f"   ⚠️ WARNING: Volume ratio unusually high!")
            else:
                logger.info(f"   ✅ Volume ratio looks normal")
        else:
            logger.warning(f"   ⚠️ Insufficient data (only {len(volume)} days)")
        
        logger.info("")
        
    except Exception as e:
        logger.error(f"   ❌ Error: {e}")
        logger.info("")

logger.info("=" * 80)
logger.info("💡 ANALYSIS")
logger.info("=" * 80)
logger.info("")
logger.info("If volume ratios are all normal here (0.5-2.0),")
logger.info("then the problem is in how screener processes the data.")
logger.info("")
logger.info("If volume ratios are low here too (<0.5),")
logger.info("then Yahoo Finance data format might have changed.")
logger.info("")
logger.info("=" * 80)
