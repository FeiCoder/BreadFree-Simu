import akshare as ak
import pandas as pd
import os

class DataFetcher:
    def __init__(self, data_dir="data_cache"):
        self.data_dir = data_dir
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def fetch_data(self, symbol: str, start_date: str, end_date: str, asset_type: str = "stock") -> pd.DataFrame:
        """
        通用数据获取接口
        :param symbol: 标的代码
        :param start_date: 开始日期 'YYYYMMDD'
        :param end_date: 结束日期 'YYYYMMDD'
        :param asset_type: 资产类型 'stock' 或 'gold'
        :return: DataFrame
        """
        if asset_type == "stock":
            return self.fetch_a_stock_daily(symbol, start_date, end_date)
        elif asset_type == "gold":
            return self.fetch_sge_gold_daily(symbol, start_date, end_date)
        else:
            print(f"Unknown asset type: {asset_type}")
            return pd.DataFrame()

    def fetch_sge_gold_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取上海黄金交易所现货数据
        :param symbol: 例如 'Au99.99'
        """
        # 格式化日期为 YYYYMMDD 用于缓存文件名，但 akshare 接口可能不需要日期过滤或者需要特定格式
        # ak.spot_hist_sge 返回所有历史数据，我们需要自己过滤
        cache_file = os.path.join(self.data_dir, f"gold_{symbol}_{start_date}_{end_date}.csv")
        
        if os.path.exists(cache_file):
            print(f"Loading data from cache: {cache_file}")
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            return df

        print(f"Fetching gold data for {symbol} from AkShare...")
        try:
            df = ak.spot_hist_sge(symbol=symbol)
            
            if df.empty:
                print("Warning: No data fetched.")
                return pd.DataFrame()

            # df columns: date, open, high, low, close
            # 确保列名一致
            df.rename(columns={
                'date': 'date',
                'open': 'open',
                'close': 'close',
                'high': 'high',
                'low': 'low'
            }, inplace=True)
            
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # 过滤日期
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            df = df[(df.index >= start) & (df.index <= end)]
            
            if df.empty:
                print("Warning: No data in date range.")
                return pd.DataFrame()

            # 黄金数据可能没有 volume，补全以防策略报错
            if 'volume' not in df.columns:
                df['volume'] = 0

            # 保存缓存
            df.to_csv(cache_file)
            return df
            
        except Exception as e:
            print(f"Error fetching gold data: {e}")
            return pd.DataFrame()

    def fetch_a_stock_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取A股日线数据或ETF数据
        :param symbol: 股票代码或ETF代码，例如 '000001' 或 '588000'
        :param start_date: 开始日期 'YYYYMMDD'
        :param end_date: 结束日期 'YYYYMMDD'
        :return: DataFrame
        """
        cache_file = os.path.join(self.data_dir, f"{symbol}_{start_date}_{end_date}.csv")
        
        if os.path.exists(cache_file):
            print(f"Loading data from cache: {cache_file}")
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            return df

        print(f"Fetching data for {symbol} from AkShare...")
        try:
            # 检查是否为ETF（以5开头）
            if symbol.startswith('5'):
                # 使用ETF接口
                df = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
            else:
                # 使用A股接口
                df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
            
            if df.empty:
                print("Warning: No data fetched.")
                return pd.DataFrame()

            # 重命名列以符合通用习惯
            df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '涨跌幅': 'pct_chg',
                '涨跌额': 'change',
                '换手率': 'turnover'
            }, inplace=True)
            
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # 保存缓存
            df.to_csv(cache_file)
            return df
            
        except Exception as e:
            print(f"Error fetching data: {e}")
            return pd.DataFrame()

if __name__ == "__main__":
    # 测试代码
    fetcher = DataFetcher(data_dir="breadfree/data/cache")
    df = fetcher.fetch_a_stock_daily("000001", "20230101", "20231231")
    print(df.head())
