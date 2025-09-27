"""
Backtesting Engine for Trading Strategies
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from loguru import logger

from signals.signal_generator import SignalGenerator
from risk.position_sizing import PositionSizingCalculator


class BacktestEngine:
    """Comprehensive backtesting engine"""

    def __init__(self, initial_capital: float = 100000, config: Dict[str, Any] = None):
        """
        Initialize backtesting engine

        Args:
            initial_capital: Starting capital
            config: Configuration dictionary
        """
        self.initial_capital = initial_capital
        self.config = config or {}

        # Trading costs
        self.commission = config.get('commission', 0.001)  # 0.1%
        self.slippage = config.get('slippage', 0.0005)     # 0.05%

        # Risk management
        self.max_positions = config.get('max_positions', 20)
        self.position_sizing = config.get('position_sizing', 'fixed_fractional')

        # Initialize position sizing calculator
        self.position_calculator = PositionSizingCalculator(initial_capital, config)

    def run_backtest(self,
                    data: Dict[str, pd.DataFrame],
                    strategy_func: Callable,
                    start_date: str,
                    end_date: str,
                    benchmark: str = 'SPY') -> Dict[str, Any]:
        """
        Run comprehensive backtest

        Args:
            data: Dictionary of price data {symbol: DataFrame}
            strategy_func: Strategy function that generates signals
            start_date: Backtest start date
            end_date: Backtest end date
            benchmark: Benchmark symbol for comparison

        Returns:
            Backtest results
        """
        logger.info(f"Starting backtest from {start_date} to {end_date}")

        try:
            # Initialize portfolio tracking
            portfolio = Portfolio(self.initial_capital)

            # Get date range
            date_range = self._get_date_range(data, start_date, end_date)

            # Run simulation
            for current_date in date_range:
                # Update portfolio with current prices
                self._update_portfolio_prices(portfolio, data, current_date)

                # Generate signals for current date
                signals = self._generate_signals(strategy_func, data, current_date)

                # Execute trades based on signals
                self._execute_trades(portfolio, signals, data, current_date)

                # Update portfolio metrics
                portfolio.update_daily_metrics(current_date)

            # Calculate performance metrics
            performance = self._calculate_performance_metrics(portfolio, data.get(benchmark), start_date, end_date)

            # Generate detailed results
            results = {
                'backtest_period': {
                    'start_date': start_date,
                    'end_date': end_date,
                    'duration_days': len(date_range)
                },
                'portfolio_summary': portfolio.get_summary(),
                'performance_metrics': performance,
                'trades': portfolio.get_trades(),
                'equity_curve': portfolio.get_equity_curve(),
                'drawdown_analysis': self._analyze_drawdowns(portfolio),
                'monthly_returns': self._calculate_monthly_returns(portfolio),
                'trade_analysis': self._analyze_trades(portfolio.get_trades()),
                'risk_metrics': self._calculate_risk_metrics(portfolio),
                'config': self.config
            }

            logger.info(f"Backtest completed. Total return: {performance.get('total_return', 0):.2%}")
            return results

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return {'error': str(e)}

    def _get_date_range(self, data: Dict[str, pd.DataFrame], start_date: str, end_date: str) -> List[str]:
        """Get trading date range"""
        # Use the first symbol's dates as reference
        first_symbol = list(data.keys())[0]
        dates = data[first_symbol].index

        # Filter by date range
        mask = (dates >= start_date) & (dates <= end_date)
        return dates[mask].tolist()

    def _update_portfolio_prices(self, portfolio: 'Portfolio', data: Dict[str, pd.DataFrame], current_date: str):
        """Update portfolio with current market prices"""
        for symbol in portfolio.positions.keys():
            if symbol in data and current_date in data[symbol].index:
                current_price = data[symbol].loc[current_date, 'close']
                portfolio.update_position_price(symbol, current_price)

    def _generate_signals(self,
                         strategy_func: Callable,
                         data: Dict[str, pd.DataFrame],
                         current_date: str) -> Dict[str, Any]:
        """Generate trading signals for current date"""
        signals = {}

        for symbol, price_data in data.items():
            try:
                # Get historical data up to current date
                historical_data = price_data[price_data.index <= current_date]

                if len(historical_data) < 50:  # Need minimum data
                    continue

                # Generate signal for this symbol
                signal = strategy_func(historical_data, symbol, current_date)
                if signal:
                    signals[symbol] = signal

            except Exception as e:
                logger.warning(f"Failed to generate signal for {symbol}: {e}")

        return signals

    def _execute_trades(self,
                       portfolio: 'Portfolio',
                       signals: Dict[str, Any],
                       data: Dict[str, pd.DataFrame],
                       current_date: str):
        """Execute trades based on signals"""
        for symbol, signal in signals.items():
            try:
                action = signal.get('action')
                if action in ['BUY', 'SELL']:
                    self._execute_trade(portfolio, symbol, signal, data[symbol], current_date)

            except Exception as e:
                logger.warning(f"Failed to execute trade for {symbol}: {e}")

    def _execute_trade(self,
                      portfolio: 'Portfolio',
                      symbol: str,
                      signal: Dict[str, Any],
                      price_data: pd.DataFrame,
                      current_date: str):
        """Execute individual trade"""
        if current_date not in price_data.index:
            return

        current_price = price_data.loc[current_date, 'close']
        action = signal.get('action')

        # Apply slippage
        if action == 'BUY':
            execution_price = current_price * (1 + self.slippage)
        else:
            execution_price = current_price * (1 - self.slippage)

        if action == 'BUY':
            # Check if we can open a new position
            if len(portfolio.positions) >= self.max_positions:
                return

            # Calculate position size
            stop_loss = signal.get('stop_loss', execution_price * 0.95)
            position_size_result = self.position_calculator.calculate_position_size(
                execution_price, stop_loss, self.position_sizing
            )

            shares = position_size_result.get('position_size', 0)
            if shares <= 0:
                return

            # Calculate total cost including commission
            total_cost = shares * execution_price * (1 + self.commission)

            if total_cost <= portfolio.cash:
                # Execute buy order
                portfolio.buy_stock(
                    symbol=symbol,
                    shares=shares,
                    price=execution_price,
                    date=current_date,
                    commission=total_cost - (shares * execution_price),
                    stop_loss=stop_loss,
                    take_profit=signal.get('take_profit')
                )

        elif action == 'SELL':
            # Sell existing position
            if symbol in portfolio.positions:
                position = portfolio.positions[symbol]
                shares = position['shares']

                # Calculate proceeds after commission
                gross_proceeds = shares * execution_price
                commission_cost = gross_proceeds * self.commission
                net_proceeds = gross_proceeds - commission_cost

                # Execute sell order
                portfolio.sell_stock(
                    symbol=symbol,
                    shares=shares,
                    price=execution_price,
                    date=current_date,
                    commission=commission_cost
                )

    def _calculate_performance_metrics(self,
                                     portfolio: 'Portfolio',
                                     benchmark_data: pd.DataFrame,
                                     start_date: str,
                                     end_date: str) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics"""
        equity_curve = portfolio.get_equity_curve()
        if equity_curve.empty:
            return {}

        # Basic metrics
        initial_value = self.initial_capital
        final_value = equity_curve['total_value'].iloc[-1]
        total_return = (final_value / initial_value) - 1

        # Time-based metrics
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        days = (end_dt - start_dt).days
        years = days / 365.25

        annualized_return = (final_value / initial_value) ** (1 / years) - 1 if years > 0 else 0

        # Volatility metrics
        daily_returns = equity_curve['total_value'].pct_change().dropna()
        volatility = daily_returns.std() * np.sqrt(252)

        # Sharpe ratio (assuming 3% risk-free rate)
        risk_free_rate = 0.03
        sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0

        # Drawdown metrics
        rolling_max = equity_curve['total_value'].expanding().max()
        drawdown = (equity_curve['total_value'] / rolling_max - 1) * 100
        max_drawdown = drawdown.min()

        # Calmar ratio
        calmar_ratio = annualized_return / abs(max_drawdown / 100) if max_drawdown != 0 else 0

        # Win rate
        trades = portfolio.get_trades()
        winning_trades = [t for t in trades if t.get('profit', 0) > 0]
        win_rate = len(winning_trades) / len(trades) if trades else 0

        # Average win/loss
        profits = [t.get('profit', 0) for t in trades if t.get('profit', 0) > 0]
        losses = [t.get('profit', 0) for t in trades if t.get('profit', 0) < 0]

        avg_win = np.mean(profits) if profits else 0
        avg_loss = abs(np.mean(losses)) if losses else 0
        profit_factor = sum(profits) / abs(sum(losses)) if losses else float('inf')

        # Benchmark comparison
        benchmark_metrics = {}
        if benchmark_data is not None:
            benchmark_returns = self._calculate_benchmark_performance(benchmark_data, start_date, end_date)
            benchmark_metrics = {
                'benchmark_return': benchmark_returns.get('total_return', 0),
                'alpha': annualized_return - benchmark_returns.get('annualized_return', 0),
                'excess_return': total_return - benchmark_returns.get('total_return', 0)
            }

        return {
            'total_return': total_return * 100,  # Convert to percentage
            'annualized_return': annualized_return * 100,  # Convert to percentage
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,  # Already in percentage
            'calmar_ratio': calmar_ratio,
            'win_rate': win_rate * 100,  # Convert to percentage
            'total_trades': len(trades),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'initial_capital': initial_value,
            'final_value': final_value,
            **benchmark_metrics
        }

    def _calculate_benchmark_performance(self,
                                       benchmark_data: pd.DataFrame,
                                       start_date: str,
                                       end_date: str) -> Dict[str, Any]:
        """Calculate benchmark performance"""
        if benchmark_data is None or benchmark_data.empty:
            return {}

        try:
            # Filter benchmark data
            mask = (benchmark_data.index >= start_date) & (benchmark_data.index <= end_date)
            filtered_data = benchmark_data[mask]

            if len(filtered_data) < 2:
                return {}

            initial_price = filtered_data['close'].iloc[0]
            final_price = filtered_data['close'].iloc[-1]

            total_return = (final_price / initial_price) - 1

            # Annualized return
            days = len(filtered_data)
            years = days / 252  # Trading days
            annualized_return = (final_price / initial_price) ** (1 / years) - 1 if years > 0 else 0

            return {
                'total_return': total_return,
                'annualized_return': annualized_return
            }

        except Exception as e:
            logger.warning(f"Failed to calculate benchmark performance: {e}")
            return {}

    def _analyze_drawdowns(self, portfolio: 'Portfolio') -> Dict[str, Any]:
        """Analyze drawdown periods"""
        equity_curve = portfolio.get_equity_curve()
        if equity_curve.empty:
            return {}

        # Calculate drawdowns
        rolling_max = equity_curve['total_value'].expanding().max()
        drawdown = (equity_curve['total_value'] / rolling_max - 1) * 100

        # Find drawdown periods
        drawdown_periods = []
        in_drawdown = False
        start_date = None
        peak_value = 0

        for date, dd in drawdown.items():
            if dd < 0 and not in_drawdown:
                # Start of drawdown
                in_drawdown = True
                start_date = date
                peak_value = rolling_max.loc[date]
            elif dd >= 0 and in_drawdown:
                # End of drawdown
                in_drawdown = False
                min_value = equity_curve['total_value'][start_date:date].min()
                max_dd = ((min_value / peak_value) - 1) * 100

                drawdown_periods.append({
                    'start_date': start_date,
                    'end_date': date,
                    'duration_days': (pd.to_datetime(date) - pd.to_datetime(start_date)).days,
                    'max_drawdown': max_dd,
                    'peak_value': peak_value,
                    'trough_value': min_value
                })

        # Summary statistics
        if drawdown_periods:
            avg_drawdown = np.mean([dd['max_drawdown'] for dd in drawdown_periods])
            avg_duration = np.mean([dd['duration_days'] for dd in drawdown_periods])
            max_duration = max([dd['duration_days'] for dd in drawdown_periods])
        else:
            avg_drawdown = avg_duration = max_duration = 0

        return {
            'max_drawdown': drawdown.min(),
            'avg_drawdown': avg_drawdown,
            'num_drawdown_periods': len(drawdown_periods),
            'avg_duration_days': avg_duration,
            'max_duration_days': max_duration,
            'drawdown_periods': drawdown_periods
        }

    def _calculate_monthly_returns(self, portfolio: 'Portfolio') -> pd.DataFrame:
        """Calculate monthly returns"""
        equity_curve = portfolio.get_equity_curve()
        if equity_curve.empty:
            return pd.DataFrame()

        # Resample to monthly
        monthly_values = equity_curve['total_value'].resample('M').last()
        monthly_returns = monthly_values.pct_change().dropna()

        return monthly_returns.to_frame('monthly_return')

    def _analyze_trades(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze trade performance"""
        if not trades:
            return {}

        # Basic trade statistics
        profits = [t.get('profit', 0) for t in trades]
        winning_trades = [p for p in profits if p > 0]
        losing_trades = [p for p in profits if p < 0]

        # Performance metrics
        total_profit = sum(profits)
        win_rate = len(winning_trades) / len(trades)
        avg_win = np.mean(winning_trades) if winning_trades else 0
        avg_loss = np.mean(losing_trades) if losing_trades else 0

        # Hold period analysis
        hold_periods = []
        for trade in trades:
            if 'buy_date' in trade and 'sell_date' in trade:
                buy_date = pd.to_datetime(trade['buy_date'])
                sell_date = pd.to_datetime(trade['sell_date'])
                hold_periods.append((sell_date - buy_date).days)

        avg_hold_period = np.mean(hold_periods) if hold_periods else 0

        # Best and worst trades
        best_trade = max(profits) if profits else 0
        worst_trade = min(profits) if profits else 0

        return {
            'total_trades': len(trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'total_profit': total_profit,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_hold_period_days': avg_hold_period,
            'profit_factor': sum(winning_trades) / abs(sum(losing_trades)) if losing_trades else float('inf')
        }

    def _calculate_risk_metrics(self, portfolio: 'Portfolio') -> Dict[str, Any]:
        """Calculate risk metrics"""
        equity_curve = portfolio.get_equity_curve()
        if equity_curve.empty:
            return {}

        daily_returns = equity_curve['total_value'].pct_change().dropna()

        # Downside deviation
        negative_returns = daily_returns[daily_returns < 0]
        downside_deviation = negative_returns.std() * np.sqrt(252)

        # Sortino ratio
        mean_return = daily_returns.mean() * 252
        risk_free_rate = 0.03
        sortino_ratio = (mean_return - risk_free_rate) / downside_deviation if downside_deviation > 0 else 0

        # VaR calculations
        var_95 = np.percentile(daily_returns, 5) * portfolio.get_current_value()
        var_99 = np.percentile(daily_returns, 1) * portfolio.get_current_value()

        return {
            'volatility': daily_returns.std() * np.sqrt(252),
            'downside_deviation': downside_deviation,
            'sortino_ratio': sortino_ratio,
            'var_95': var_95,
            'var_99': var_99,
            'skewness': daily_returns.skew(),
            'kurtosis': daily_returns.kurtosis()
        }


class Portfolio:
    """Portfolio tracking for backtesting"""

    def __init__(self, initial_capital: float):
        """Initialize portfolio"""
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}  # {symbol: {shares, avg_price, current_price, ...}}
        self.trades = []
        self.equity_history = []

    def buy_stock(self,
                  symbol: str,
                  shares: int,
                  price: float,
                  date: str,
                  commission: float = 0,
                  stop_loss: float = None,
                  take_profit: float = None):
        """Buy stock position"""
        total_cost = shares * price + commission

        if total_cost > self.cash:
            return False

        self.cash -= total_cost

        if symbol in self.positions:
            # Add to existing position
            old_shares = self.positions[symbol]['shares']
            old_avg_price = self.positions[symbol]['avg_price']

            new_shares = old_shares + shares
            new_avg_price = ((old_shares * old_avg_price) + (shares * price)) / new_shares

            self.positions[symbol].update({
                'shares': new_shares,
                'avg_price': new_avg_price,
                'current_price': price
            })
        else:
            # New position
            self.positions[symbol] = {
                'shares': shares,
                'avg_price': price,
                'current_price': price,
                'stop_loss': stop_loss,
                'take_profit': take_profit
            }

        # Record trade
        self.trades.append({
            'symbol': symbol,
            'action': 'BUY',
            'shares': shares,
            'price': price,
            'date': date,
            'commission': commission,
            'total_cost': total_cost,
            'value': total_cost  # For frontend display
        })

        return True

    def sell_stock(self,
                   symbol: str,
                   shares: int,
                   price: float,
                   date: str,
                   commission: float = 0):
        """Sell stock position"""
        if symbol not in self.positions:
            return False

        position = self.positions[symbol]
        if shares > position['shares']:
            shares = position['shares']  # Sell all available

        gross_proceeds = shares * price
        net_proceeds = gross_proceeds - commission
        self.cash += net_proceeds

        # Calculate profit/loss
        avg_price = position['avg_price']
        profit = (price - avg_price) * shares - commission

        # Update position
        remaining_shares = position['shares'] - shares
        if remaining_shares > 0:
            self.positions[symbol]['shares'] = remaining_shares
        else:
            del self.positions[symbol]

        # Record trade
        trade_record = {
            'symbol': symbol,
            'action': 'SELL',
            'shares': shares,
            'price': price,
            'date': date,
            'commission': commission,
            'gross_proceeds': gross_proceeds,
            'net_proceeds': net_proceeds,
            'avg_buy_price': avg_price,
            'profit': profit,
            'profit_pct': (profit / (avg_price * shares)) * 100,
            'value': net_proceeds,  # For frontend display
            'pnl': profit  # P&L for frontend display
        }

        # Add buy date if available
        buy_trades = [t for t in self.trades if t['symbol'] == symbol and t['action'] == 'BUY']
        if buy_trades:
            trade_record['buy_date'] = buy_trades[-1]['date']
            trade_record['sell_date'] = date

        self.trades.append(trade_record)

        return True

    def update_position_price(self, symbol: str, current_price: float):
        """Update current price for position"""
        if symbol in self.positions:
            self.positions[symbol]['current_price'] = current_price

    def get_current_value(self) -> float:
        """Get current total portfolio value"""
        positions_value = sum(
            pos['shares'] * pos['current_price']
            for pos in self.positions.values()
        )
        return self.cash + positions_value

    def update_daily_metrics(self, date: str):
        """Update daily portfolio metrics"""
        total_value = self.get_current_value()
        positions_value = total_value - self.cash

        self.equity_history.append({
            'date': date,
            'total_value': total_value,
            'cash': self.cash,
            'positions_value': positions_value,
            'num_positions': len(self.positions)
        })

    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame"""
        if not self.equity_history:
            return pd.DataFrame()

        df = pd.DataFrame(self.equity_history)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        return df

    def get_trades(self) -> List[Dict[str, Any]]:
        """Get all trades"""
        return self.trades

    def get_summary(self) -> Dict[str, Any]:
        """Get portfolio summary"""
        current_value = self.get_current_value()
        total_return = (current_value / self.initial_capital - 1) * 100

        return {
            'initial_capital': self.initial_capital,
            'current_value': current_value,
            'cash': self.cash,
            'positions_value': current_value - self.cash,
            'total_return_pct': total_return,
            'num_positions': len(self.positions),
            'total_trades': len(self.trades)
        }