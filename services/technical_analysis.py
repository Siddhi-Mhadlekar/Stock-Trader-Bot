import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from app.models import Stock, QuoteData, TechnicalIndicators, CandleData

logger = logging.getLogger(__name__)

class TechnicalAnalysisService:
    def __init__(self, db):
        self.db = db

    def calculate_store_indicators_for_all_stocks(self):
        """Calculate and store indicators for all stocks"""
        try:
            stocks = self.db.query(Stock).filter(Stock.instrument_token.isnot(None)).all()
            
            if not stocks:
                logger.warning("No stocks found in database")
                return None

            results = {}
            for stock in stocks:
                try:
                    logger.info(f"Processing {stock.ticker_symbol} ({stock.instrument_token})")
                    df = self.get_historical_data(stock.instrument_token)
                    
                    if df.empty:
                        logger.warning(f"No data found for {stock.ticker_symbol}")
                        continue
                    
                    logger.info(f"Got {len(df)} records for {stock.ticker_symbol}")
                    
                    if len(df) < 60:
                        logger.warning(f"Not enough data for {stock.ticker_symbol}. Got {len(df)} days, need 60")
                        continue
                    
                    # Calculate indicators
                    # Moving Averages
                    df['SMA_5'] = df['close'].rolling(window=5).mean()
                    df['SMA_20'] = df['close'].rolling(window=20).mean()
                    df['SMA_50'] = df['close'].rolling(window=50).mean()
                    
                    # RSI
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    df['RSI_14'] = 100 - (100 / (1 + rs))
                    
                    # MACD
                    exp1 = df['close'].ewm(span=12, adjust=False).mean()
                    exp2 = df['close'].ewm(span=26, adjust=False).mean()
                    df['MACD'] = exp1 - exp2
                    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
                    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
                    
                    # Bollinger Bands
                    df['BB_Middle'] = df['close'].rolling(window=20).mean()
                    df['BB_Upper'] = df['BB_Middle'] + 2 * df['close'].rolling(window=20).std()
                    df['BB_Lower'] = df['BB_Middle'] - 2 * df['close'].rolling(window=20).std()
                    
                    # Get latest values
                    latest = df.iloc[-1]
                    
                    # Create technical indicators record
                    tech_indicators = TechnicalIndicators(
                        instrument_token=stock.instrument_token,
                        calculated_at=datetime.now(),
                        data_timestamp=latest.name,
                        
                        # Price data
                        last_close=float(latest['close']),
                        last_volume=float(latest['volume']),
                        
                        # Moving Averages
                        sma_5=float(latest['SMA_5']),
                        sma_20=float(latest['SMA_20']),
                        sma_50=float(latest['SMA_50']),
                        
                        # RSI
                        rsi_14=float(latest['RSI_14']),
                        is_overbought=float(latest['RSI_14']) > 70,
                        is_oversold=float(latest['RSI_14']) < 30,
                        
                        # MACD
                        macd=float(latest['MACD']),
                        macd_signal=float(latest['MACD_Signal']),
                        macd_histogram=float(latest['MACD_Hist']),
                        macd_bullish_crossover=float(latest['MACD']) > float(latest['MACD_Signal']),
                        macd_bearish_crossover=float(latest['MACD']) < float(latest['MACD_Signal']),
                        
                        # Bollinger Bands
                        bb_upper=float(latest['BB_Upper']),
                        bb_middle=float(latest['BB_Middle']),
                        bb_lower=float(latest['BB_Lower']),
                        bb_bandwidth=float((latest['BB_Upper'] - latest['BB_Lower']) / latest['BB_Middle'])
                    )
                    
                    self.db.add(tech_indicators)
                    results[stock.instrument_token] = {
                        'ticker': stock.ticker_symbol,
                        'calculated_at': tech_indicators.calculated_at
                    }
                    
                    logger.info(f"Successfully calculated indicators for {stock.ticker_symbol}")
                
                except Exception as e:
                    logger.error(f"Error processing {stock.ticker_symbol}: {str(e)}")
                    continue

            self.db.commit()
            return results

        except Exception as e:
            logger.error(f"Error in calculate_store_indicators_for_all_stocks: {str(e)}")
            self.db.rollback()
            return None

    def get_historical_data(self, instrument_token: int) -> pd.DataFrame:
        """Get historical data for calculations"""
        try:
            # Get all available data without date restriction
            quotes = self.db.query(CandleData).filter(
                CandleData.instrument_token == instrument_token
            ).order_by(CandleData.timestamp.asc()).all()
            
            if not quotes:
                logger.warning(f"No historical data found for instrument {instrument_token}")
                return pd.DataFrame()

            # Create DataFrame
            df = pd.DataFrame([{
                'timestamp': q.timestamp,
                'open': q.open_price if hasattr(q, 'open_price') else q.open,  # Handle both column names
                'high': q.high_price if hasattr(q, 'high_price') else q.high,
                'low': q.low_price if hasattr(q, 'low_price') else q.low,
                'close': q.close_price if hasattr(q, 'close_price') else q.close,
                'volume': q.volume
            } for q in quotes])
            
            if not df.empty:
                df.set_index('timestamp', inplace=True)
                logger.info(f"Got {len(df)} records for instrument {instrument_token}")
            
            return df

        except Exception as e:
            logger.error(f"Error fetching historical data for {instrument_token}: {str(e)}")
            return pd.DataFrame()