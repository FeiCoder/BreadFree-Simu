import json
import pandas as pd
from curl_cffi import requests
from datetime import datetime, timedelta
import os
import time

class NewsFetcher:
    def __init__(self, data_dir: str | None = None):
        # 默认将缓存目录放在与本模块同级的 `cache` 文件夹中
        if data_dir is None:
            base_dir = os.path.dirname(__file__)
            self.data_dir = os.path.join(base_dir, "cache")
        else:
            # 如果传入了相对路径或绝对路径，则按原样使用
            self.data_dir = data_dir

        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)

    def _fetch_page(self, symbol: str, page_index: int = 1, page_size: int = 50) -> pd.DataFrame:
        """
        获取单页新闻数据
        """
        url = "https://search-api-web.eastmoney.com/search/jsonp"
        inner_param = {
            "uid": "",
            "keyword": symbol,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": page_index,
                    "pageSize": page_size,
                    "preTag": "<em>",
                    "postTag": "</em>"
                }
            }
        }
        params = {
            "cb": "jQuery35101792940631092459_1764599530165",
            "param": json.dumps(inner_param, ensure_ascii=False),
            "_": str(int(time.time() * 1000))
        }
        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8",
            "cache-control": "no-cache",
            "connection": "keep-alive",
            "host": "search-api-web.eastmoney.com",
            "pragma": "no-cache",
            "referer": f"https://so.eastmoney.com/news/s?keyword={symbol}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
        }
        
        try:
            r = requests.get(url, params=params, headers=headers)
            data_text = r.text
            if "jQuery" in data_text:
                start_idx = data_text.find("(") + 1
                end_idx = data_text.rfind(")")
                data_text = data_text[start_idx:end_idx]
            
            data_json = json.loads(data_text)
            
            if "result" not in data_json or "cmsArticleWebOld" not in data_json["result"]:
                return pd.DataFrame()

            temp_df = pd.DataFrame(data_json["result"]["cmsArticleWebOld"])
            if temp_df.empty:
                return pd.DataFrame()

            temp_df["url"] = "http://finance.eastmoney.com/a/" + temp_df["code"] + ".html"
            
            temp_df.rename(
                columns={
                    "date": "date", # 保持英文方便后续处理，最后再统一改名
                    "mediaName": "mediaName",
                    "title": "title",
                    "content": "content",
                    "url": "url",
                },
                inplace=True,
            )
            
            for col in ["title", "content"]:
                temp_df[col] = (
                    temp_df[col]
                    .str.replace(r"\(<em>", "", regex=True)
                    .str.replace(r"</em>\)", "", regex=True)
                    .str.replace(r"<em>", "", regex=True)
                    .str.replace(r"</em>", "", regex=True)
                    .str.replace(r"\u3000", "", regex=True)
                    .str.replace(r"\r\n", " ", regex=True)
                )

            return temp_df[[
                "date",
                "mediaName",
                "title",
                "content",
                "url",
            ]]

        except Exception as e:
            print(f"Error fetching page {page_index} for {symbol}: {e}")
            return pd.DataFrame()

    def fetch_and_save_news(self, symbol: str, max_pages: int = 20) -> str:
        """
        获取指定股票的历史新闻并保存为 JSON
        :param symbol: 股票代码
        :param max_pages: 最大抓取页数
        :return: 保存的文件路径
        """
        all_news = []
        print(f"Start fetching news for {symbol}, max_pages={max_pages}...")
        
        for page in range(1, max_pages + 1):
            print(f"Fetching page {page}/{max_pages}...")
            df = self._fetch_page(symbol, page_index=page)
            
            if df.empty:
                print("No more data found.")
                break
                
            all_news.extend(df.to_dict(orient="records"))
            time.sleep(0.5) # 避免请求过快
            
        if not all_news:
            print("No news fetched.")
            return ""
            
        # 转换为 DataFrame 进行统一处理
        final_df = pd.DataFrame(all_news)
        final_df["date"] = pd.to_datetime(final_df["date"])
        final_df.sort_values(by="date", ascending=False, inplace=True)
        
        # 格式化日期为字符串
        final_df["date"] = final_df["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # 重命名为用户要求的格式
        final_df.rename(columns={
            "date": "发布时间",
            "mediaName": "文章来源",
            "title": "新闻标题",
            "content": "新闻内容",
            "url": "新闻链接"
        }, inplace=True)
        
        # 保存为 JSON
        file_path = os.path.join(self.data_dir, f"news_{symbol}.json")
        final_df.to_json(file_path, orient="records", force_ascii=False, indent=4)
        print(f"Saved {len(final_df)} news items to {file_path}")
        return file_path

    def get_stock_news(self, symbol: str) -> pd.DataFrame:
        """
        兼容旧接口：获取最近一页新闻
        """
        df = self._fetch_page(symbol, page_index=1, page_size=50)
        if not df.empty:
            # 确保日期列为 datetime 类型，便于后续比较和格式化
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df.rename(columns={
                "date": "发布时间",
                "mediaName": "文章来源",
                "title": "新闻标题",
                "content": "新闻内容",
                "url": "新闻链接"
            }, inplace=True)
            # 如果重命名后发布时间不是 datetime（例如 parse 失败），再转换一次以保险
            try:
                df["发布时间"] = pd.to_datetime(df["发布时间"], errors="coerce")
            except Exception:
                pass
        return df

    def get_recent_news_text(self, symbol: str, hours: int = 24, top_n: int = 5) -> str:
        """
        获取最近 N 小时的新闻文本，用于 LLM 上下文
        """
        df = self.get_stock_news(symbol)
        if df.empty:
            return "暂无相关新闻"
            
        # 筛选最近 N 小时
        cutoff_time = datetime.now() - timedelta(hours=hours)
        # 确保发布时间列为 datetime，然后进行比较
        if not pd.api.types.is_datetime64_any_dtype(df.get("发布时间")):
            df["发布时间"] = pd.to_datetime(df["发布时间"], errors="coerce")

        recent_df = df[df["发布时间"] >= cutoff_time]
        
        if recent_df.empty:
            # 如果最近没新闻，取最新的几条兜底
            recent_df = df.head(top_n)
        else:
            recent_df = recent_df.head(top_n)
            
        news_list = []
        for _, row in recent_df.iterrows():
            pub = row.get("发布时间")
            if pd.isna(pub):
                time_str = "未知时间"
            else:
                # pub 可能是 pandas.Timestamp 或 datetime
                try:
                    time_str = pd.Timestamp(pub).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    time_str = str(pub)

            news_list.append(f"- [{time_str}] {row.get('新闻标题', '')} ({row.get('文章来源', '')})")
            
        return "\n".join(news_list)

if __name__ == "__main__":
    fetcher = NewsFetcher()
    # 读取配置文件 -- 在多个候选路径中查找 config.yaml（优先 breadfree/config.yaml）
    import yaml
    here = os.path.dirname(__file__)
    candidates = [
        os.path.normpath(os.path.join(here, "..", "config.yaml")),            # breadfree/config.yaml
        os.path.normpath(os.path.join(here, "..", "..", "config.yaml")),   # repo_root/config.yaml
        os.path.normpath(os.path.join(here, "..", "..", "breadfree", "config.yaml")),
    ]

    config = {}
    loaded_path = None
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                    loaded_path = p
                    print(f"Loaded config from: {p}")
            except Exception as e:
                print(f"Failed to parse config at {p}: {e}")
            break

    if not config:
        print("No config.yaml found; using defaults.")

    symbol = config.get("symbol", "518850")
    max_pages = int(config.get("max_pages", 10))
    print(f"Fetching news for {symbol} (max_pages={max_pages})...")

    # 1. 测试获取并保存历史新闻
    json_path = fetcher.fetch_and_save_news(symbol, max_pages=max_pages)
    print(f"History saved to: {json_path}")

    # 2. 测试获取最近新闻文本
    news_text = fetcher.get_recent_news_text(symbol)
    print("\nRecent News Context:")
    print(news_text)
