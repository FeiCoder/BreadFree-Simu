import pandas as pd
import os
from datetime import datetime, timedelta
import os
from ..data.data_fetcher import DataFetcher
from ..data.database import get_db_manager
from .broker import Broker
from ..utils.metrics import *
from ..utils.plotter import plot_backtest_results

class BacktestEngine:
    def __init__(self, strategy_cls, symbols, start_date, end_date, initial_cash=100000.0, asset_type="stock", lot_size=100, data_source="akshare", tushare_token=None, **kwargs):
        self.data_fetcher = DataFetcher(data_dir="breadfree/data/cache", data_source=data_source, tushare_token=tushare_token)
        self.broker = Broker(initial_cash=initial_cash)
        
        # Pass additional strategy parameters
        self.strategy = strategy_cls(self.broker, lot_size=lot_size, **kwargs)
        
        # Support passing single symbol string or symbol list
        if isinstance(symbols, str):
            self.symbols = [symbols]
        else:
            self.symbols = symbols
            
        self.start_date = start_date
        self.end_date = end_date
        self.asset_type = asset_type
        self.data_map = {} # {symbol: dataframe}

    def run(self):
        # 1. Fetch Data with Warmup
        # Calculate fetch start date (45 days before start_date)
        try:
            start_dt = datetime.strptime(self.start_date, "%Y%m%d")
            fetch_start_dt = start_dt - timedelta(days=60) 
            fetch_start_date = fetch_start_dt.strftime("%Y%m%d")
        except ValueError:
            print(f"Invalid date format: {self.start_date}. Expected YYYYMMDD.")
            return

        print(f"Fetching data from database for {len(self.symbols)} symbols from {fetch_start_date} to {self.end_date}...")
        
        # Prepare data containers
        all_dates = set()
        warmup_data_map = {}
        backtest_data_map = {}
        db_manager = get_db_manager()

        for symbol in self.symbols:
            # Use database manager to fetch data (Works for both Stocks and ETFs)
            df = db_manager.get_daily_data(symbol, fetch_start_date, self.end_date)
            
            if df.empty:
                print(f"Warning: No data for {symbol} in database. Please ensure it is imported.")
                # 采用data_fetcher尝试获取数据
                df = self.data_fetcher.fetch_a_stock_daily(symbol, fetch_start_date, self.end_date)
                if df.empty:
                    print(f"Error: Unable to fetch data for {symbol}. Skipping.")
                    continue
                else:
                    print(f"Data for {symbol} fetched from data source, {len(df)} records.")
            
            # Ensure trade_date is the index
            if 'trade_date' in df.columns:
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                df.set_index('trade_date', inplace=True)
                
            if not isinstance(df.index, pd.DatetimeIndex):
                 df.index = pd.to_datetime(df.index)
            
            # Store data
            self.data_map[symbol] = df
            
            # Split Warmup and Backtest
            warmup = df[df.index < start_dt]
            backtest = df[df.index >= start_dt]
            
            warmup_data_map[symbol] = warmup
            backtest_data_map[symbol] = backtest
            
            if not backtest.empty:
                all_dates.update(backtest.index)

        if not all_dates:
            print("No data found for backtest period.")
            return
            
        sorted_dates = sorted(list(all_dates))

        # 2. Initialize Strategy
        if hasattr(self.strategy, 'set_symbols'):
            self.strategy.set_symbols(self.symbols)
            
        # Preload history if supported
        if hasattr(self.strategy, 'preload_history'):
            # Pass dictionary of warmup data
            self.strategy.preload_history(warmup_data_map)

        print(f"Starting backtest from {self.start_date} to {self.end_date}")
        print(f"Initial Cash: {self.broker.cash}")

        # 3. Loop through time
        last_prices = {} # Used to estimate market value if a stock is suspended
        
        for date in sorted_dates:
            # Construct daily bars dictionary
            bars = {}
            for symbol, df in backtest_data_map.items():
                if date in df.index:
                    row = df.loc[date]
                    bars[symbol] = row
                    last_prices[symbol] = row['close']
            
            if not bars:
                continue

            # Run Strategy
            # on_bar receives (date, bars_dict)
            self.strategy.on_bar(date, bars)
            
            # Record Equity
            # Use last_prices to ensure position value calculation even if a stock has no trades today
            equity = self.broker.get_total_equity(last_prices)
            self.broker.equity_curve.append({'date': date, 'equity': equity})

        # 4. Final Results
        if not self.broker.equity_curve:
            print("No trades or equity data.")
            return

        final_equity = self.broker.equity_curve[-1]['equity']
        equity_series = pd.Series([d['equity'] for d in self.broker.equity_curve])
        
        # Use unified utility functions to calculate metrics
        final_return = calculate_total_return(equity_series, initial_capital=self.broker.initial_cash)
        max_drawdown = calculate_max_drawdown(equity_series)
        sharpe_ratio = calculate_sharpe_ratio(equity_series)
        annualized_return = calculate_annualized_return(equity_series, annual_days=242)        
        
        # 5. Calculate Trade Statistics
        trade_returns = [t['return_pct'] for t in self.broker.closed_trades]
        profit_loss_ratio = calculate_profit_loss_ratio(trade_returns)
        win_rate, win_count, total_trades = calculate_win_rate(trade_returns)
        # calculate_calmar_ratio
        calmar_ratio = calculate_calmar_ratio(annualized_return, abs(max_drawdown), risk_free_rate=0.015)

        print(f"Backtest finished.")
        print(f"Final Equity: {final_equity:.2f}")
        print(f"Total Return: {final_return:.2%}")
        print(f"Annualized Return: {annualized_return:.2%}")
        print(f"Sharpe Ratio: {sharpe_ratio:.2f}")
        print(f"Calmar Ratio: {calmar_ratio:.2f}")
        print(f"Max Drawdown: {max_drawdown:.2%}")
        print(f"Win Rate: {win_rate:.2%} ({win_count}/{total_trades})")
        print(f"Profit/Loss Ratio: {profit_loss_ratio:.2f}")

        # 6. Plot Results
        # self.plot_results()
        # self.plot_results_png()

    def plot_results_png(self, filename="./output/backtest_result.png"):
        try:
            import matplotlib.pyplot as plt
        except Exception as e:
            print(f"无法导入 matplotlib，绘图功能将被跳过: {e}")
            return

        if not self.broker.equity_curve:
            print("No results to plot.")
            return

        # 将 equity_curve 转换为 DataFrame
        equity_df = pd.DataFrame(self.broker.equity_curve)
        equity_df.set_index('date', inplace=True)

        # For simplicity, we use the first symbol as benchmark if available
        benchmark_series = None
        first_symbol = self.symbols[0]
        if first_symbol in self.data_map:
            df = self.data_map[first_symbol]
            # Filter for backtest period
            start_dt = datetime.strptime(self.start_date, "%Y%m%d")
            df_bt = df[df.index >= start_dt]
            if not df_bt.empty:
                benchmark_series = df_bt['close']
        
        # Determine title
        if len(self.symbols) == 1:
            title = f"Backtest: {self.symbols[0]}"
        else:
            title = f"Portfolio Backtest ({len(self.symbols)} symbols)"

        # Plotting
        plt.figure(figsize=(12, 6))
        plt.plot(equity_df.index, equity_df['equity'], label='Strategy Equity')

        if benchmark_series is not None:
            # Normalize benchmark series
            benchmark_series = benchmark_series / benchmark_series.iloc[0] * equity_df['equity'].iloc[0]
            # Align time indexes
            benchmark_series = benchmark_series.reindex(equity_df.index)
            plt.plot(benchmark_series.index, benchmark_series, label=f'Benchmark ({first_symbol})', alpha=0.6, linestyle='--')
        
        plt.title(title)
        plt.xlabel('Date')
        plt.ylabel('Equity')
        plt.legend()
        plt.grid(True)

        # Ensure output directory exists
        if not os.path.exists("./output"):
            os.makedirs("./output")

        # Save figure
        plt.savefig(filename)
        print(f"Result chart saved to {filename}")

        # Close the plot to free memory
        plt.close()

    def plot_results_html(self, filename="./output/backtest_result.html"):
        if not self.broker.equity_curve:
            print("No results to plot.")
            return

        # For simplicity, we use the first symbol as benchmark if available
        benchmark_series = None
        first_symbol = self.symbols[0]
        if first_symbol in self.data_map:
            df = self.data_map[first_symbol]
            # Filter for backtest period
            start_dt = datetime.strptime(self.start_date, "%Y%m%d")
            df_bt = df[df.index >= start_dt]
            if not df_bt.empty:
                benchmark_series = df_bt['close']
        
        # Determine title
        if len(self.symbols) == 1:
            title = f"Backtest: {self.symbols[0]}"
        else:
            title = f"Portfolio Backtest ({len(self.symbols)} symbols)"

        print(f"Plotting results to {filename}...")
        plot_backtest_results(
            equity_curve=self.broker.equity_curve,
            transaction_history=self.broker.transaction_history,
            benchmark_series=benchmark_series,
            initial_cash=self.broker.initial_cash,
            title=title,
            filename=filename
        )

        print(f"Results saved to {filename}")
