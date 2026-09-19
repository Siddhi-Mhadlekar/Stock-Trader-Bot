from sqlalchemy import Column, Integer, Float, DateTime, BigInteger, String, Enum, Index, Boolean, ForeignKey, JSON, Date, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from .database import Base
import enum

class IntervalType(enum.Enum):
    ONE_MINUTE = "1minute"
    FIVE_MINUTE = "5minute"
    FIFTEEN_MINUTE = "15minute"
    THIRTY_MINUTE = "30minute"
    SIXTY_MINUTE = "60minute"
    DAY = "day"

class CandleData(Base):
    __tablename__ = "candle_data"

    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(Integer, index=True)
    interval = Column(String, index=True)
    timestamp = Column(DateTime, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Integer)
    oi = Column(Integer, nullable=True)  # Make it nullable
    created_at = Column(DateTime, default=datetime.utcnow)  # Add created_at

    # Add composite index for quick queries
    __table_args__ = (
        Index('idx_token_interval_timestamp', 
              'instrument_token', 'interval', 'timestamp'),
    )

    class Config:
        orm_mode = True

class QuoteData(Base):
    __tablename__ = "quote_data"

    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(Integer, index=True)  # First 4 bytes
    last_price = Column(Float)                      # Next 4 bytes
    last_quantity = Column(Integer)                 # Next 4 bytes
    average_price = Column(Float)                   # Next 4 bytes
    volume = Column(BigInteger)                     # Next 4 bytes
    buy_quantity = Column(BigInteger)               # Next 4 bytes
    sell_quantity = Column(BigInteger)              # Next 4 bytes
    open_price = Column(Float)                      # Next 4 bytes
    high_price = Column(Float)                      # Next 4 bytes
    low_price = Column(Float)                       # Next 4 bytes
    close_price = Column(Float)                     # Next 4 bytes
    last_trade_time = Column(DateTime)              # Next 4 bytes
    oi = Column(BigInteger)                         # Next 4 bytes
    oi_high = Column(BigInteger)                    # Next 4 bytes
    oi_low = Column(BigInteger)                     # Next 4 bytes
    exchange_timestamp = Column(DateTime)           # Next 4 bytes
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Market depth entries are optional and depend on mode
    # If needed, we can add them in a separate table

class TickData(Base):
    __tablename__ = "tick_data"

    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(Integer)
    timestamp = Column(DateTime)
    last_price = Column(Float)
    # Add other fields as needed 

class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, index=True)
    ticker_symbol = Column(String, unique=True, index=True)
    instrument_token = Column(Integer, unique=True, nullable=True)

    class Config:
        orm_mode = True

class TechnicalIndicators(Base):
    __tablename__ = "technical_indicators"

    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(Integer, index=True)
    calculated_at = Column(DateTime, default=datetime.utcnow, index=True)  # When indicators were calculated
    data_timestamp = Column(DateTime, index=True)  # Timestamp of the data used
    
    # Price and Volume
    last_close = Column(Float)
    last_volume = Column(Float)
    
    # SMA Values
    sma_5 = Column(Float)
    sma_10 = Column(Float)
    sma_20 = Column(Float)
    sma_50 = Column(Float)
    sma_200 = Column(Float)
    
    # EMA Values
    ema_5 = Column(Float)
    ema_10 = Column(Float)
    ema_20 = Column(Float)
    ema_50 = Column(Float)
    ema_200 = Column(Float)
    
    # RSI
    rsi_14 = Column(Float)
    is_overbought = Column(Boolean)
    is_oversold = Column(Boolean)
    
    # MACD
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_histogram = Column(Float)
    macd_bullish_crossover = Column(Boolean)
    macd_bearish_crossover = Column(Boolean)
    
    # Bollinger Bands
    bb_upper = Column(Float)
    bb_middle = Column(Float)
    bb_lower = Column(Float)
    bb_bandwidth = Column(Float)
    
    # Volume Indicators
    volume_sma_20 = Column(Float)
    volume_obv = Column(Float)
    volume_mfi = Column(Float)
    volume_roc = Column(Float)
    volume_avg_ratio = Column(Float)
    
    # Fibonacci Levels
    fib_recent_high = Column(Float)
    fib_recent_low = Column(Float)
    fib_0_236 = Column(Float)
    fib_0_382 = Column(Float)
    fib_0_5 = Column(Float)
    fib_0_618 = Column(Float)
    fib_0_786 = Column(Float)

    class Config:
        orm_mode = True

class StockAnalysis(Base):
    __tablename__ = "stock_analysis"

    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(Integer, ForeignKey("stocks.instrument_token"))
    analyzed_at = Column(DateTime, default=datetime.now)
    
    # Stock Info at Analysis Time
    ticker_symbol = Column(String)
    company_name = Column(String)
    current_price = Column(Float)
    
    # Analysis Results
    trading_action = Column(String)  # BUY/SELL/HOLD
    confidence_level = Column(String)  # HIGH/MEDIUM/LOW
    key_reason = Column(String)
    risk_level = Column(String)  # HIGH/MEDIUM/LOW
    stop_loss = Column(Float)
    target_price = Column(Float)
    
    # Indicators at Analysis Time
    rsi_14 = Column(Float)
    macd = Column(Float)
    volume_ratio = Column(Float)
    
    # Raw Analysis
    raw_analysis = Column(JSON)  # Store complete LLM response 

class MarketHoliday(Base):
    __tablename__ = "market_holidays"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True)
    holiday_name = Column(String)
    exchange = Column(String)  # NSE/BSE
    is_full_day = Column(Boolean, default=True)
    year = Column(Integer)

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, index=True)
    instrument_token = Column(Integer, index=True)
    symbol = Column(String, index=True)
    exchange = Column(String)
    quantity = Column(Integer)
    price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    is_intraday = Column(Boolean, default=False)
    is_market_order = Column(Boolean, default=True)
    status = Column(String)  # OPEN, COMPLETE, CANCELLED, REJECTED
    order_type = Column(String)  # BUY, SELL
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<Order {self.order_id}: {self.order_type} {self.quantity} {self.symbol} @ {self.price if not self.is_market_order else 'MARKET'}>" 