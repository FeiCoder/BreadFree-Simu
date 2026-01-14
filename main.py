import sys
import os
import argparse
from datetime import datetime, timedelta

# Add the project root to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from breadfree.engine.backtest_engine import BacktestEngine
from breadfree.strategies.ma_strategy import DoubleMAStrategy
from breadfree.strategies.agent_strategy import AgentStrategy
from breadfree.strategies.benchmark_strategy import BenchmarkStrategy
from breadfree.strategies.rotation_strategy import RotationStrategy

def main():
    # 1. 定义命令行参数
    parser = argparse.ArgumentParser(description='BreadFree 策略回测引擎')
    parser.add_argument('--strategy', type=str, help='策略名称', choices=[
        'DoubleMAStrategy', 'BenchmarkStrategy', 'AgentStrategy', 'RotationStrategy'
    ])
    parser.add_argument('--start_date', type=str, help='开始日期 YYYYMMDD')
    parser.add_argument('--end_date', type=str, help='结束日期 YYYYMMDD')
    parser.add_argument('--initial_cash', type=float, help='初始资金')
    parser.add_argument('--lookback_period', type=int, help='调仓参考周期')
    parser.add_argument('--hold_period', type=int, help='持仓周期')
    parser.add_argument('--top_n', type=int, help='持有标的数量')
    parser.add_argument('--min_momentum', type=float, help='最小动量阈值')

    parser.add_argument('--use_efficiency', type=str, choices=['True', 'False'], help='是否启用效率得分')

    parser.add_argument('--output_file', type=str, default='backtest_result.png', help='输出PNG文件名')
    
    args = parser.parse_args()

    # 2. 读取配置文件
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "breadfree", "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    # 3. 参数优先级：命令行参数 > 配置文件 > 默认值
    strategy_name = args.strategy or config.get("strategy", "RotationStrategy")
    start_date = args.start_date or config.get("start_date", datetime.now().strftime("%Y%m%d"))
    end_date = args.end_date or config.get("end_date", (datetime.now() - timedelta(days=30)).strftime("%Y%m%d"))
    initial_cash = args.initial_cash or config.get("initial_cash", 100000.0)
    asset_type = config.get("asset_type", "stock")
    lot_size = config.get("lot_size", 100)
    symbols = list(config.get("etf_pool", {"510300": "沪深300ETF"}).keys())  # 默认一些ETF

    # 策略类选择
    strategy_map = {
        "DoubleMAStrategy": DoubleMAStrategy,
        "BenchmarkStrategy": BenchmarkStrategy,
        "AgentStrategy": AgentStrategy,
        "RotationStrategy": RotationStrategy
    }
    strategy_cls = strategy_map.get(strategy_name, RotationStrategy)

    print(f"Running backtest with {strategy_cls.__name__}...")

    # 提取策略参数 (除了通用参数外的配置)
    # 策略参数映射
    strategy_params = {}
    
    # 手动映射可能传入的超参数
    param_keys = ["lookback_period", "hold_period", "top_n"]
    for key in param_keys:
        val = getattr(args, key)
        if val is not None:
            strategy_params[key] = val
        elif key in config:
            strategy_params[key] = config[key]
            
    # 特殊处理布尔值
    if args.use_efficiency is not None:
        strategy_params["use_efficiency"] = args.use_efficiency == 'True'
    elif "use_efficiency" in config:
        strategy_params["use_efficiency"] = config["use_efficiency"]

    # Create and run backtest
    # 注意：BacktestEngine 现在接受 symbols 列表
    engine = BacktestEngine(
        strategy_cls=strategy_cls,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        initial_cash=initial_cash,
        asset_type=asset_type,
        lot_size=lot_size,
        **strategy_params
    )
    engine.run()

    # Plot results (generates HTML file)
    try:
        engine.plot_results_png(args.output_file)
    except Exception as e:
        print(f"Could not plot results: {e}")

if __name__ == "__main__":
    main()
