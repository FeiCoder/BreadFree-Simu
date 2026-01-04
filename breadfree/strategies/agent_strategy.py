import json
import asyncio
import os
from datetime import datetime, timedelta
import pandas as pd
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from .base_strategy import Strategy
from ..utils.llm_client import async_hunyuan_chat, logger

# --- State Definition ---
class AgentState(TypedDict):
    date: str
    market_data: str
    account_status: str
    analyst_view: str
    risk_view: str
    final_decision: str # JSON string

# --- Prompts ---
ANALYST_PROMPT = """
你是一个激进的A股市场分析师，专注于政策敏感型市场。你的任务是基于共享内存中的最新数据（OHLCV、均线、真实新闻舆情、散户情绪指标）判断当前趋势。必须考虑A股T+1交易制度、涨跌停板限制和政策影响。

【事件驱动分析要求】
请对提供的【新闻舆情】进行事件分类和影响评估：
1. **Policy_Support (政策扶持)**: 如降息、行业补贴 -> 长期利好
2. **Earnings_Surprise (业绩超预期)**: 如财报预增 -> 短期爆发
3. **M_and_A (并购重组)**: 资产注入 -> 高波动
4. **Scandal (丑闻/立案)**: 违规、减持 -> **一票否决（建议卖出）**
5. **Noise (噪音)**: 无实质影响 -> 忽略

【反射检查要求】
1. 确认数据完整性：检查最近5个交易日数据是否完整
2. 评估预期差：对比【新闻事件】与【今日股价表现】。例如：利好发布但股价下跌=利好出尽；利空发布但股价不跌=底部确认。
3. 考察散户情绪：结合交易量异常波动和热门板块热度指标

输出必须包含：
1. **事件分析**：
   - 核心事件类型：(从上述5类中选择)
   - 预期差判断：(符合预期/低于预期/超预期)
2. **市场趋势**（上涨/下跌/震荡）及多维度理由：
   - 技术面：价格与均线关系
   - 资金面：成交量变化
3. **交易建议**（强烈买入/买入/观望/卖出/强烈卖出）及依据
4. **简短理由**（包含事件驱动逻辑，字数≤50字）
"""

RISK_MANAGER_PROMPT = """
你是一个保守的A股风控官，核心目标是保护本金并防止回撤。你的任务是基于共享内存中的当前账户资金、持仓、市场分析师观点，结合A股特性给出仓位管理建议。

【反射检查要求】
1. 验证分析师数据：确认分析师报告是否包含政策面分析（缺失则要求重分析）
2. 评估A股特殊风险：计算T+1交易下可能的流动性风险，考虑涨跌停板导致的无法及时止损
3. 检查波动率：对比当前波动率与近30日均值（波动率>30%则风险等级上调）

输出必须包含：
1. 风险评估（高/中/低）及详细理由：
   - 高风险：政策突变+波动率>30%+涨跌停板限制
   - 中风险：政策影响+波动率20-30%
   - 低风险：政策平稳+波动率<20%
2. 建议仓位比例（0.0-1.0，必须考虑T+1和涨跌停）：
   - 例：若分析师建议"强烈买入"但风险评估"高"，则建议≤0.3
3. 简短理由（明确说明T+1/涨跌停对仓位的影响，字数≤40字）
"""

FUND_MANAGER_PROMPT = """
你是一个基金经理，拥有最终决策权。必须基于共享内存中的所有信息（市场分析、风控建议、账户状态）做出交易指令，优先遵循风控官意见。

【关键规则】
1. 冲突处理：当分析师建议"买入"但风控建议"卖出"时，强制采用风控建议
2. A股特殊约束：所有决策必须考虑T+1交易和涨跌停板
3. 学习机制：每次决策后必须记录依据，用于后续优化

输出必须是严格JSON格式（无任何额外文本）：
{
    "action": "BUY" | "SELL" | "HOLD",
    "quantity_pct": 0.0 - 1.0, // 买入时占可用资金比例，卖出时占持仓比例
    "reason": "综合分析：包含市场趋势（技术/政策/情绪）、风险评估等级、A股特性影响（如'涨跌停限制导致仓位≤0.3'）",
    "learning_note": "决策依据与结果记录（例：'2023-10-05政策利好未被计入，下次需增加政策监测'）"
}
"""

# --- Node Functions ---

async def market_analyst_node(state: AgentState):
    logger.info(f"Market Analyst Node Input: {state}")
    query = f"日期: {state['date']}\n市场数据:\n{state['market_data']}"
    response, _ = await async_hunyuan_chat(query=query, prompt=ANALYST_PROMPT)
    return {"analyst_view": response}

async def risk_manager_node(state: AgentState):
    logger.info(f"Risk Manager Node Input: {state}")
    query = f"日期: {state['date']}\n账户状态:\n{state['account_status']}\n市场分析师观点:\n{state['analyst_view']}"
    response, _ = await async_hunyuan_chat(query=query, prompt=RISK_MANAGER_PROMPT)
    return {"risk_view": response}

async def fund_manager_node(state: AgentState):
    logger.info(f"Fund Manager Node Input: {state}")
    query = f"""
    日期: {state['date']}
    市场分析师观点:
    {state['analyst_view']}
    
    风控官观点:
    {state['risk_view']}
    
    请做出决策。
    """
    response, _ = await async_hunyuan_chat(query=query, prompt=FUND_MANAGER_PROMPT)
    # Clean up response to ensure it's valid JSON
    cleaned_response = response.strip()
    if cleaned_response.startswith("```json"):
        cleaned_response = cleaned_response[7:]
    if cleaned_response.endswith("```"):
        cleaned_response = cleaned_response[:-3]
    return {"final_decision": cleaned_response.strip()}

# --- Graph Construction ---
def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("market_analyst", market_analyst_node)
    workflow.add_node("risk_manager", risk_manager_node)
    workflow.add_node("fund_manager", fund_manager_node)

    workflow.set_entry_point("market_analyst")
    workflow.add_edge("market_analyst", "risk_manager")
    workflow.add_edge("risk_manager", "fund_manager")
    workflow.add_edge("fund_manager", END)

    return workflow.compile()

# --- Strategy Implementation ---
class AgentStrategy(Strategy):
    def __init__(self, broker, lot_size=100):
        super().__init__(broker, lot_size)
        self.app = build_graph()
        self.symbol = None
        self.history = [] # Keep track of close prices for indicators
        self.news_data = [] # Store loaded news

    def set_symbol(self, symbol):
        self.symbol = symbol
        self.load_news()

    def load_news(self):
        """Load news from JSON cache"""
        try:
            # Assuming the cache directory is relative to the project root
            # breadfree/strategies/langgraph_strategy.py -> breadfree/strategies -> breadfree -> data/cache
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cache_dir = os.path.join(base_dir, "data", "cache")
            file_path = os.path.join(cache_dir, f"news_{self.symbol}.json")
            
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.news_data = json.load(f)
                print(f"Loaded {len(self.news_data)} news items for {self.symbol}")
            else:
                print(f"No news cache found for {self.symbol} at {file_path}")
                self.news_data = []
        except Exception as e:
            print(f"Error loading news: {e}")
            self.news_data = []

    def get_news_context(self, current_date_str, days=2):
        """Get news context for the past N days relative to current_date"""
        if not self.news_data:
            return "暂无相关新闻数据 (未知)"
            
        try:
            current_date = pd.to_datetime(current_date_str)
            start_date = current_date - timedelta(days=days)
            
            relevant_news = []
            for item in self.news_data:
                news_time = pd.to_datetime(item['发布时间'])
                # Filter news: start_date <= news_time <= current_date (end of day)
                if start_date <= news_time <= current_date + timedelta(days=1): 
                    relevant_news.append(f"- [{item['发布时间']}] {item['新闻标题']} {item['新闻内容'][:200]} ...")
            
            if not relevant_news:
                return "该时段暂无新闻 (未知)"
                
            # Return top 10 most recent relevant news
            return "\n".join(relevant_news[:10]) 
        except Exception as e:
            print(f"Error filtering news: {e}")
            return "新闻数据处理出错"

    def preload_history(self, history_df):
        """Preload history data for indicators calculation"""
        if not history_df.empty:
            self.history = history_df['close'].tolist()
            print(f"Preloaded {len(self.history)} days of history.")

    def on_bar(self, date, bar_data):
        # Update history
        self.history.append(bar_data['close'])
        
        # Run async graph in sync context
        try:
            asyncio.run(self._run_graph(date, bar_data))
        except Exception as e:
            print(f"Error running LangGraph strategy: {e}")

    async def _run_graph(self, date, bar_data):
        # 1. Prepare Data
        # Calculate Indicators
        ma5 = pd.Series(self.history).rolling(window=5).mean().iloc[-1] if len(self.history) >= 5 else bar_data['close']
        ma20 = pd.Series(self.history).rolling(window=20).mean().iloc[-1] if len(self.history) >= 20 else bar_data['close']
        
        # Calculate Volatility (Standard Deviation of last 30 days returns)
        volatility = 0.0
        if len(self.history) >= 30:
            returns = pd.Series(self.history).pct_change().dropna()
            volatility = returns.tail(30).std() * 100 # Percentage

        # Get recent price history (last 5 days)
        recent_prices = self.history[-5:] if len(self.history) >= 5 else self.history
        recent_prices_str = ", ".join([f"{p:.2f}" for p in recent_prices])

        # Get Real News Context
        news_context = self.get_news_context(str(date))
        
        # Simulated Sentiment (Still simulated for now, or could be derived from volume)
        # Simple volume based sentiment
        # Note: self.history only stores close prices, so we can't calculate avg volume easily here 
        # without storing volume history. For now, we keep it simple or use a placeholder.
        sentiment = "散户情绪稳定。" # Default
        
        market_data_str = f"""
        Date: {date}
        Close: {bar_data['close']:.2f}
        Open: {bar_data['open']:.2f}
        High: {bar_data['high']:.2f}
        Low: {bar_data['low']:.2f}
        Volume: {bar_data['volume']}
        
        Technical Indicators:
        MA5: {ma5:.2f}
        MA20: {ma20:.2f}
        Volatility (30-day): {volatility:.2f}%
        
        Recent 5 Days Close Prices: [{recent_prices_str}]
        
        Shared Memory Context:
        News Events:
        {news_context}
        
        Retail Sentiment: {sentiment}
        """

        account_status_str = f"""
        Cash: {self.broker.cash:.2f}
        Positions: {self.broker.positions}
        """

        initial_state = AgentState(
            date=str(date),
            market_data=market_data_str,
            account_status=account_status_str,
            analyst_view="",
            risk_view="",
            final_decision=""
        )

        # 2. Run Graph
        result = await self.app.ainvoke(initial_state)
        
        # 3. Execute Decision
        try:
            decision = json.loads(result["final_decision"])
            action = decision.get("action", "HOLD").upper()
            quantity_pct = float(decision.get("quantity_pct", 0.0))
            reason = decision.get("reason", "")

            print(f"[{date}] Agent Decision: {action} | Reason: {reason}")

            close_price = bar_data['close']

            if action == "BUY":
                available_cash = self.broker.cash
                target_cash = available_cash * quantity_pct
                if target_cash > 0:
                    # 先按目标资金计算最多可买入的股数（未考虑整手）
                    max_shares = int(target_cash / (close_price * (1 + self.broker.commission_rate)))
                    quantity = (max_shares // self.lot_size) * self.lot_size

                    # 边界处理：若按目标仓位计算结果为0，但账户可用现金足以购买至少一手，则按一手下单并记录警告
                    lot_cost = close_price * self.lot_size * (1 + self.broker.commission_rate)
                    if quantity == 0:
                        if available_cash >= lot_cost and quantity_pct > 0:
                            quantity = self.lot_size
                            print(f"[{date}] Warning: target_cash insufficient for a lot, falling back to 1 lot (lot_size={self.lot_size}).")
                        else:
                            # 无法买入任何整手，输出调试信息
                            print(f"[{date}] Info: target_cash={target_cash:.2f}, lot_cost={lot_cost:.2f}, available_cash={available_cash:.2f} -> no shares to buy.")

                    if quantity > 0:
                        self.broker.buy(date, self.symbol, close_price, quantity)
            
            elif action == "SELL":
                if self.symbol in self.broker.positions:
                    pos = self.broker.positions[self.symbol]
                    quantity = int(pos.quantity * quantity_pct)
                    quantity = (quantity // self.lot_size) * self.lot_size

                    # 边界处理：当计算结果为0但持仓小于整手时，允许清仓卖出（全部持仓），或当quantity_pct>0且pos.quantity>=lot_size但四舍五入为0时，提示原因
                    if quantity == 0:
                        # 如果持仓少于一手但用户希望卖出，允许全部卖出
                        if pos.quantity > 0 and pos.quantity < self.lot_size:
                            quantity = pos.quantity
                            print(f"[{date}] Info: holding less than one lot ({pos.quantity}), selling entire position.")
                        else:
                            print(f"[{date}] Info: computed sell quantity is 0 (pos={pos.quantity}, quantity_pct={quantity_pct}). Skipping sell.")

                    if quantity > 0:
                        self.broker.sell(date, self.symbol, close_price, quantity)

        except json.JSONDecodeError:
            print(f"[{date}] Failed to parse JSON decision: {result['final_decision']}")
        except Exception as e:
            print(f"[{date}] Error executing decision: {e}")
