import pandas as pd
import os
from pyecharts.charts import Line, Grid
from pyecharts import options as opts
from .metrics import calculate_max_drawdown, calculate_sharpe_ratio

def plot_backtest_results(equity_curve, transaction_history, benchmark_series=None, initial_cash=100000.0, title="Backtest Result", filename="backtest_result.html"):
    """
    Plot backtest results chart (supports multi-stock/portfolio)

    Args:
        equity_curve: list of dict, e.g. [{'date': datetime, 'equity': float}, ...]
        transaction_history: list of dict, e.g. [{'date': datetime, 'action': 'BUY', ...}, ...]
        benchmark_series: pd.Series, index is date, values are benchmark prices/net value. Optional.
        initial_cash: float, initial capital
        title: str, chart title
        filename: str, save filename
    """
    if not equity_curve:
        print("No results to plot.")
        return

    # 1. Prepare strategy equity data
    equity_values = [d['equity'] for d in equity_curve]
    # Ensure dates are formatted as strings
    dates = [d['date'].strftime('%Y-%m-%d') if hasattr(d['date'], 'strftime') else str(d['date']) for d in equity_curve]
    
    equity_series = pd.Series(equity_values, index=pd.to_datetime(dates))

    # 2. Prepare benchmark data (if available)
    benchmark_equity = []
    if benchmark_series is not None and not benchmark_series.empty:
        # Align dates
        # benchmark_series index should be datetime type
        if not isinstance(benchmark_series.index, pd.DatetimeIndex):
            benchmark_series.index = pd.to_datetime(benchmark_series.index)
            
        common_dates = benchmark_series.index.intersection(equity_series.index)
        
        if not common_dates.empty:
            # Extract corresponding time period and normalize to initial capital
            aligned_benchmark = benchmark_series.loc[common_dates]
            # Reindex according to backtest date order (handling suspension or missing dates, simple intersection approach)
            # For plotting convenience, we find corresponding benchmark values in the dates list
            # If a date in dates is not in benchmark, fill with previous value or None
            
            # Simpler method:
            # Take benchmark slice within dates range, then normalize
            start_price = 0
            # Find the first valid price for normalization
            for d in dates:
                dt = pd.to_datetime(d)
                if dt in benchmark_series.index:
                    start_price = benchmark_series.loc[dt]
                    break
            
            if start_price > 0:
                # Generate benchmark list aligned with dates
                for d in dates:
                    dt = pd.to_datetime(d)
                    if dt in benchmark_series.index:
                        val = benchmark_series.loc[dt]
                        benchmark_equity.append(val / start_price * initial_cash)
                    else:
                        # If missing, use previous value or None
                        benchmark_equity.append(benchmark_equity[-1] if benchmark_equity else initial_cash)
            else:
                 benchmark_equity = [initial_cash] * len(dates)
        else:
            benchmark_equity = [initial_cash] * len(dates)
    else:
        # No benchmark, fill with None or don't plot
        pass

    # 3. Calculate metrics
    max_drawdown = calculate_max_drawdown(equity_series)
    sharpe_ratio = calculate_sharpe_ratio(equity_series)
    final_return = (equity_values[-1] - initial_cash) / initial_cash
    
    # Drawdown curve
    running_max = equity_series.cummax()
    drawdown = (equity_series - running_max) / running_max
    
    subtitle = f"Total Return: {final_return:.2%} | Sharpe Ratio: {sharpe_ratio:.2f} | Max Drawdown: {max_drawdown:.2%}"

    # 4. Transaction markers
    markers = []
    # Create date to equity mapping for easy coordinate lookup
    date_to_equity = dict(zip(dates, equity_values))
    
    for tx in transaction_history:
        tx_date = tx['date'].strftime('%Y-%m-%d') if hasattr(tx['date'], 'strftime') else str(tx['date'])
        
        # Only mark if transaction date is within chart date range
        if tx_date in date_to_equity:
            val = date_to_equity[tx_date]
            action = tx['action']
            
            # For multiple stocks, can display symbol in tooltip or value
            symbol_info = tx.get('symbol', '')
            
            if action == 'BUY':
                markers.append(opts.MarkPointItem(
                    coord=[tx_date, val], 
                    value=f"{symbol_info}", 
                    symbol="arrow", 
                    symbol_size=15, 
                    itemstyle_opts=opts.ItemStyleOpts(color="#d14a61"),
                    # tooltip_opts=opts.TooltipOpts(formatter=f"Buy {symbol_info}<br/>Price: {tx['price']}")
                ))
            elif action == 'SELL':
                markers.append(opts.MarkPointItem(
                    coord=[tx_date, val], 
                    value=f"{symbol_info}", 
                    symbol="arrow", 
                    symbol_size=15, 
                    symbol_rotate=180, 
                    itemstyle_opts=opts.ItemStyleOpts(color="#5793f3"),
                    # tooltip_opts=opts.TooltipOpts(formatter=f"Sell {symbol_info}<br/>Price: {tx['price']}")
                ))

    # 5. Build chart
    # Main chart: Equity curve + benchmark
    line_main = (
        Line()
        .add_xaxis(dates)
        .add_yaxis(
            "Strategy Equity", 
            equity_values, 
            is_smooth=True, 
            label_opts=opts.LabelOpts(is_show=False),
            linestyle_opts=opts.LineStyleOpts(width=2, color="#c23531"),
            markpoint_opts=opts.MarkPointOpts(
                data=markers,
                label_opts=opts.LabelOpts(is_show=True)
            )
        )
    )
    
    if benchmark_equity and len(benchmark_equity) == len(dates):
        line_main.add_yaxis(
            "Benchmark", 
            benchmark_equity, 
            is_smooth=True, 
            label_opts=opts.LabelOpts(is_show=False),
            linestyle_opts=opts.LineStyleOpts(width=2, color="#2f4554", type_="dashed")
        )

    line_main.set_global_opts(
        title_opts=opts.TitleOpts(
            title=title, 
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
            axislabel_opts=opts.LabelOpts(formatter="{value}"),  # 这里改为 {value}
            splitline_opts=opts.SplitLineOpts(is_show=True)
        ),
        datazoom_opts=[opts.DataZoomOpts(xaxis_index=[0, 1], is_show=True)],
        legend_opts=opts.LegendOpts(pos_top="5%"),
    )

    # Secondary chart: Drawdown
    line_drawdown = (
        Line()
        .add_xaxis(dates)
        .add_yaxis(
            "Drawdown", 
            drawdown.tolist(), 
            is_smooth=True, 
            label_opts=opts.LabelOpts(is_show=False),
            areastyle_opts=opts.AreaStyleOpts(opacity=0.3, color="#00da3c"),
            linestyle_opts=opts.LineStyleOpts(width=1, color="#00da3c"),
            yaxis_index=1,  # 新增，指定副图y轴
            xaxis_index=1   # 新增，指定副图x轴
        )
        .set_global_opts(
            tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
            xaxis_opts=opts.AxisOpts(type_="category", boundary_gap=False, grid_index=1),  # 新增 grid_index=1
            yaxis_opts=opts.AxisOpts(
                type_="value", 
                axislabel_opts=opts.LabelOpts(formatter="{value}"),
                splitline_opts=opts.SplitLineOpts(is_show=True),
                grid_index=1  # 新增 grid_index=1
            ),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )

    # Combine layout
    grid = (
        Grid(init_opts=opts.InitOpts(width="100%", height="800px"))
        .add(line_main, grid_opts=opts.GridOpts(pos_left="5%", pos_right="5%", height="60%"))
        .add(line_drawdown, grid_opts=opts.GridOpts(pos_left="5%", pos_right="5%", pos_top="75%", height="20%"))
    )
    if os.path.exists(os.path.dirname(filename)) is False:
        os.makedirs(os.path.dirname(filename))

    grid.render(filename)
    return filename
