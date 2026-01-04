from .base_strategy import Strategy
import pandas as pd
import sys
import os
# Add the project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from breadfree.utils.logger import get_logger

logger = get_logger(__name__)

class DoubleMAStrategy(Strategy):
    def __init__(self, broker, short_window=5, long_window=20, lot_size=100, max_position_pct: float = 1.0):
        """Double moving average strategy.

        Args:
            broker: Broker instance
            short_window: short MA window
            long_window: long MA window
            lot_size: minimal tradeable lot size
            max_position_pct: fraction of available cash to use when opening a position (0.0-1.0)
        """
        super().__init__(broker, lot_size=lot_size)
        self.short_window = short_window
        self.long_window = long_window
        self.history = []  # Keep track of close prices
        self.symbol = None
        self.max_position_pct = float(max_position_pct)

    def set_symbol(self, symbol):
        self.symbol = symbol

    def preload_history(self, history_df):
        if not history_df.empty:
            self.history = history_df['close'].tolist()
            logger.info(f"DoubleMAStrategy: Preloaded {len(self.history)} days of history.")

    def on_bar(self, date, bar_data):
        # bar_data is expected to be a row from the dataframe
        close_price = bar_data['close']

        # Validate price
        if pd.isna(close_price) or close_price <= 0:
            logger.warning(f"[{date}] Invalid close price: {close_price}. Skipping bar.")
            return

        self.history.append(close_price)

        if len(self.history) < self.long_window:
            return

        # Calculate MAs
        short_ma = pd.Series(self.history).rolling(window=self.short_window).mean().iloc[-1]
        long_ma = pd.Series(self.history).rolling(window=self.long_window).mean().iloc[-1]
        
        # Previous MAs to check for crossover
        prev_short_ma = pd.Series(self.history).rolling(window=self.short_window).mean().iloc[-2]
        prev_long_ma = pd.Series(self.history).rolling(window=self.long_window).mean().iloc[-2]

        # Check for crossover
        # Golden Cross (Short crosses above Long) -> Buy
        if prev_short_ma <= prev_long_ma and short_ma > long_ma:
            # Buy signal
            # Simple logic: Buy as many shares as possible (in lots of lot_size)
            if self.symbol not in self.broker.positions:
                logger.info(f"[{date}] Golden Cross detected for {self.symbol}. Preparing to buy.")

                available_cash = self.broker.cash
                # Respect max_position_pct so we don't use full wallet unless allowed
                target_cash = available_cash * max(0.0, min(1.0, self.max_position_pct))

                # Estimate cost including commission
                est_share_cost = close_price * (1 + self.broker.commission_rate)
                if est_share_cost <= 0:
                    logger.error(f"[{date}] Invalid estimated share cost: {est_share_cost}. Skipping buy.")
                else:
                    max_shares = int(target_cash / est_share_cost)
                    quantity = (max_shares // self.lot_size) * self.lot_size

                    # Fallback: if target allocation can't buy even one lot but wallet can afford one lot, buy one lot
                    lot_cost = close_price * self.lot_size * (1 + self.broker.commission_rate)
                    if quantity == 0:
                        if available_cash >= lot_cost and self.max_position_pct > 0:
                            quantity = self.lot_size
                            logger.warning(f"[{date}] target_cash insufficient for a lot, falling back to 1 lot (lot_size={self.lot_size}).")
                        else:
                            logger.info(f"[{date}] Not enough funds to buy a lot. target_cash={target_cash:.2f}, lot_cost={lot_cost:.2f}, available_cash={available_cash:.2f}")

                    if quantity > 0:
                        logger.info(f"[{date}] Executing buy: symbol={self.symbol}, quantity={quantity}, price={close_price:.2f}")
                        self.broker.buy(date, self.symbol, close_price, quantity)

        # Death Cross (Short crosses below Long) -> Sell
        elif prev_short_ma >= prev_long_ma and short_ma < long_ma:
            # Sell signal
            if self.symbol in self.broker.positions:
                logger.info(f"[{date}] Death Cross detected for {self.symbol}. Preparing to sell.")
                pos = self.broker.positions[self.symbol]
                sell_qty = (pos.quantity // self.lot_size) * self.lot_size

                # If holding less than one lot, allow full clear
                if sell_qty == 0:
                    if pos.quantity > 0:
                        sell_qty = pos.quantity
                        logger.info(f"[{date}] Holding less than one lot ({pos.quantity}), will sell entire holding.")
                    else:
                        logger.info(f"[{date}] No shares to sell for {self.symbol}.")

                if sell_qty > 0:
                    logger.info(f"[{date}] Executing sell: symbol={self.symbol}, quantity={sell_qty}, price={close_price:.2f}")
                    self.broker.sell(date, self.symbol, close_price, sell_qty)