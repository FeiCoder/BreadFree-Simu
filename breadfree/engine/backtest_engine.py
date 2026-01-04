import pandas as pd
from datetime import datetime, timedelta
from pyecharts.charts import Line, Grid
from pyecharts import options as opts
from ..data.data_fetcher import DataFetcher
from .broker import Broker

class BacktestEngine:
    def __init__(self, strategy_cls, symbol, start_date, end_date, initial_cash=100000.0, asset_type="stock", lot_size=100):
        self.data_fetcher = DataFetcher(data_dir="breadfree/data/cache")
        self.broker = Broker(initial_cash=initial_cash)
        self.strategy = strategy_cls(self.broker, lot_size=lot_size)
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.asset_type = asset_type
        self.data = None

    def run(self):
        # 1. Fetch Data with Warmup
        # Calculate fetch start date (45 days before start_date to ensure enough history for indicators)
        try:
            start_dt = datetime.strptime(self.start_date, "%Y%m%d")
            fetch_start_dt = start_dt - timedelta(days=45) # Fetch extra to cover holidays
            fetch_start_date = fetch_start_dt.strftime("%Y%m%d")
        except ValueError:
            print(f"Invalid date format: {self.start_date}. Expected YYYYMMDD.")
            return

        print(f"Fetching data from {fetch_start_date} to {self.end_date} (including warmup)...")
        full_data = self.data_fetcher.fetch_data(self.symbol, fetch_start_date, self.end_date, asset_type=self.asset_type)
        
        if full_data.empty:
            print("No data to backtest.")
            return

        # Split into warmup and backtest data
        # Ensure index is datetime
        if not isinstance(full_data.index, pd.DatetimeIndex):
             full_data.index = pd.to_datetime(full_data.index)
             
        warmup_data = full_data[full_data.index < start_dt]
        self.data = full_data[full_data.index >= start_dt]
        
        if self.data.empty:
             print(f"No data found for backtest period {self.start_date} to {self.end_date}")
             return

        # 2. Initialize Strategy
        if hasattr(self.strategy, 'set_symbol'):
            self.strategy.set_symbol(self.symbol)
            
        # Preload history if supported
        if hasattr(self.strategy, 'preload_history'):
            self.strategy.preload_history(warmup_data)

        print(f"Starting backtest for {self.symbol} from {self.start_date} to {self.end_date}")
        print(f"Initial Cash: {self.broker.cash}")

        # 3. Loop through data
        for date, row in self.data.iterrows():
            # Update Broker's view of the market (for equity calculation)
            current_prices = {self.symbol: row['close']}
            
            # Run Strategy
            self.strategy.on_bar(date, row)
            
            # Record Equity
            equity = self.broker.get_total_equity(current_prices)
            self.broker.equity_curve.append({'date': date, 'equity': equity})

        # 4. Final Results
        final_equity = self.broker.equity_curve[-1]['equity']
        print(f"Backtest finished.")
        print(f"Final Equity: {final_equity:.2f}")
        print(f"Return: {(final_equity - self.broker.initial_cash) / self.broker.initial_cash * 100:.2f}%")

    def plot_results(self, filename="backtest_result.html"):
        if not self.broker.equity_curve:
            print("No results to plot.")
            return

        # Calculate Benchmark and Drawdown
        df_equity = pd.DataFrame(self.broker.equity_curve)
        dates = df_equity['date'].dt.strftime('%Y-%m-%d').tolist()
        equity = df_equity['equity'].tolist()
        
        # Benchmark: Buy & Hold
        initial_price = self.data.iloc[0]['close']
        initial_cash = self.broker.initial_cash
        benchmark_equity = (self.data['close'] / initial_price * initial_cash).tolist()
        
        # Ensure alignment
        min_len = min(len(equity), len(benchmark_equity))
        equity = equity[:min_len]
        benchmark_equity = benchmark_equity[:min_len]
        dates = dates[:min_len]
        
        # Drawdown Calculation
        equity_series = pd.Series(equity)
        running_max = equity_series.cummax()
        drawdown = (equity_series - running_max) / running_max
        max_drawdown = drawdown.min()
        
        final_return = (equity[-1] - initial_cash) / initial_cash
        
        subtitle = f"Return: {final_return:.2%} | Max Drawdown: {max_drawdown:.2%}"

        # Trade Markers
        markers = []
        date_to_equity = dict(zip(dates, equity))
        for tx in self.broker.transaction_history:
            tx_date = tx['date'].strftime('%Y-%m-%d')
            if tx_date in date_to_equity:
                val = date_to_equity[tx_date]
                if tx['action'] == 'BUY':
                    markers.append(opts.MarkPointItem(
                        coord=[tx_date, val], 
                        value="Buy", 
                        symbol="arrow", 
                        symbol_size=15, 
                        itemstyle_opts=opts.ItemStyleOpts(color="#d14a61")
                    ))
                elif tx['action'] == 'SELL':
                    markers.append(opts.MarkPointItem(
                        coord=[tx_date, val], 
                        value="Sell", 
                        symbol="arrow", 
                        symbol_size=15, 
                        symbol_rotate=180, 
                        itemstyle_opts=opts.ItemStyleOpts(color="#5793f3")
                    ))

        # Main Chart
        line_main = (
            Line()
            .add_xaxis(dates)
            .add_yaxis(
                "Strategy Equity", 
                equity, 
                is_smooth=True, 
                label_opts=opts.LabelOpts(is_show=False),
                linestyle_opts=opts.LineStyleOpts(width=2, color="#c23531"),
                markpoint_opts=opts.MarkPointOpts(data=markers)
            )
            .add_yaxis(
                "Benchmark (Buy & Hold)", 
                benchmark_equity, 
                is_smooth=True, 
                label_opts=opts.LabelOpts(is_show=False),
                linestyle_opts=opts.LineStyleOpts(width=2, color="#2f4554", type_="dashed")
            )
            .set_global_opts(
                title_opts=opts.TitleOpts(
                    title=f"Backtest: {self.symbol}", 
                    subtitle=subtitle
                ),
                tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
                xaxis_opts=opts.AxisOpts(
                    type_="category", 
                    boundary_gap=False, 
                    axislabel_opts=opts.LabelOpts(is_show=False)
                ),
                yaxis_opts=opts.AxisOpts(
                    type_="value", 
                    is_scale=True, 
                    axislabel_opts=opts.LabelOpts(formatter="{value:.0f}"),
                    splitline_opts=opts.SplitLineOpts(is_show=True)
                ),
                datazoom_opts=[opts.DataZoomOpts(xaxis_index=[0, 1], is_show=True)],
                legend_opts=opts.LegendOpts(pos_top="5%"),
            )
        )

        # Drawdown Chart
        line_drawdown = (
            Line()
            .add_xaxis(dates)
            .add_yaxis(
                "Drawdown", 
                drawdown.tolist(), 
                is_smooth=True, 
                label_opts=opts.LabelOpts(is_show=False),
                areastyle_opts=opts.AreaStyleOpts(opacity=0.3, color="#00da3c"),
                linestyle_opts=opts.LineStyleOpts(width=1, color="#00da3c")
            )
            .set_global_opts(
                tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
                xaxis_opts=opts.AxisOpts(type_="category", boundary_gap=False),
                yaxis_opts=opts.AxisOpts(
                    type_="value", 
                    axislabel_opts=opts.LabelOpts(formatter="{value:.0%}"),
                    splitline_opts=opts.SplitLineOpts(is_show=True)
                ),
                legend_opts=opts.LegendOpts(is_show=False),
            )
        )

        # Grid Layout
        grid = (
            Grid(init_opts=opts.InitOpts(width="100%", height="800px"))
            .add(line_main, grid_opts=opts.GridOpts(pos_left="5%", pos_right="5%", height="60%"))
            .add(line_drawdown, grid_opts=opts.GridOpts(pos_left="5%", pos_right="5%", pos_top="75%", height="20%"))
        )

        grid.render(filename)
        print(f"Results saved to {filename}")
        print(f"Result saved to {filename}")
