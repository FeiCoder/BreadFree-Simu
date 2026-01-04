import sys
import os
from datetime import datetime, timedelta

# Add the project root to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from breadfree.engine.backtest_engine import BacktestEngine
from breadfree.strategies.ma_strategy import DoubleMAStrategy
from breadfree.strategies.agent_strategy import AgentStrategy
from breadfree.strategies.benchmark_strategy import BenchmarkStrategy
from breadfree.data.stock_pool import STOCK_POOLS

def main():
    # Configuration for Stock
    # 建议从 breadfree/data/stock_pool.py 中选择
    # 1. 宽基 ETF (推荐): "510050" (上证50), "588000" (科创50)
    # 2. 科技成长: "300750" (宁德时代), "688981" (中芯国际)
    # 3. 稳健白马: "600519" (茅台), "600036" (招行)
    

    # 读取配置文件
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "breadfree", "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    symbol = config.get("symbol", "518850")
    start_date = config.get("start_date", datetime.now().strftime("%Y%m%d"))
    end_date = config.get("end_date", (datetime.now() - timedelta(days=30)).strftime("%Y%m%d"))
    initial_cash = config.get("initial_cash", 1000000.0)
    asset_type = config.get("asset_type", "stock")
    lot_size = config.get("lot_size", 100)
    strategy_name = config.get("strategy", "AgentStrategy")

    # 策略类选择
    strategy_map = {
        "DoubleMAStrategy": DoubleMAStrategy,
        "BenchmarkStrategy": BenchmarkStrategy,
        "AgentStrategy": AgentStrategy
    }
    strategy_cls = strategy_map.get(strategy_name, AgentStrategy)

    print(f"Running backtest with {strategy_cls.__name__}...")

    # Create and run backtest
    engine = BacktestEngine(
        strategy_cls=strategy_cls,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        asset_type=asset_type,
        lot_size=lot_size
    )
    engine.run()

    # Plot results (generates HTML file)
    try:
        engine.plot_results("backtest_result.html")
    except Exception as e:
        print(f"Could not plot results: {e}")

if __name__ == "__main__":
    main()
