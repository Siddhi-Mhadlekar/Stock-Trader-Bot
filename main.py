from fastapi import FastAPI, HTTPException, Depends, WebSocket
from kiteconnect import KiteConnect
from datetime import datetime, timedelta
import logging
import hashlib
import json
import asyncio
import requests
from sqlalchemy.orm import Session
from .database import get_db, SessionLocal
from .models import QuoteData, Stock, CandleData, TechnicalIndicators, StockAnalysis
from .config import settings
from websockets.exceptions import ConnectionClosed
import backoff  # You'll need to install this: pip install backoff
from typing import Optional
import pandas as pd
import websockets  # Add this import
from app.services.technical_analysis import TechnicalAnalysisService
from app.services.analysis_service import StockAnalysisService
from pydantic import BaseModel, Field
from app.services.order_service import OrderService
from app.services.holiday_service import HolidayService
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv, set_key
import os

# Change relative imports to absolute

#from app.services.technical_analysis import TechnicalAnalysisService

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
#tech_analysis = TechnicalAnalysisService(db)
#llm_analysis = LLMAnalysisService(db, OPENAI_API_KEY)

# Create a dependency for OrderService
def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(db)

# Initialize services with database session
@app.on_event("startup")
async def startup_event():
    db = next(get_db())
    app.state.db = db

# Add this after creating the app instance
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def connect_websocket(access_token: str):
    """Connect to Kite WebSocket with auto-reconnection"""
    print(access_token,"access_token")
    access_token = settings.KITE_ACCESS_TOKEN
    while True:  # Continuous reconnection loop
        try:
            uri = f"wss://ws.kite.trade/?api_key={settings.KITE_API_KEY}&access_token={access_token}"
            logger.info(f"Connecting to WebSocket...")
            
            async with websockets.connect(
                uri,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            ) as websocket:
                logger.info("WebSocket connected successfully")
                
                # Create DB session
                db = SessionLocal()
                
                try:
                    # Get instruments from stocks table
                    stocks = db.query(Stock).filter(Stock.instrument_token.isnot(None)).all()
                    instruments = [stock.instrument_token for stock in stocks]
                    
                    if not instruments:
                        logger.error("No instruments found in stocks table")
                        raise HTTPException(status_code=404, detail="No instruments found")
                    
                    logger.info(f"Found {len(instruments)} instruments in stocks table")
                    
                    # Subscribe to all instruments
                    subscribe_message = {
                        "a": "subscribe",
                        "v": instruments
                    }
                    await websocket.send(json.dumps(subscribe_message))
                    logger.info(f"Subscribed to instruments: {instruments}")

                    # Set mode to full for all instruments
                    mode_message = {
                        "a": "mode",
                        "v": ["full", instruments]
                    }
                    await websocket.send(json.dumps(mode_message))
                    logger.info("Mode set to full")

                    while True:
                        try:
                            message = await websocket.recv()
                            if isinstance(message, bytes):
                                quote_data = process_binary_message(message)
                                if quote_data:
                                    current_time = datetime.now()
                                    db_quote = QuoteData(
                                        instrument_token=quote_data['instrument_token'],
                                        last_price=quote_data['last_price'],
                                        last_quantity=quote_data['last_quantity'],
                                        average_price=quote_data['average_price'],
                                        volume=quote_data['volume'],
                                        buy_quantity=quote_data['buy_quantity'],
                                        sell_quantity=quote_data['sell_quantity'],
                                        open_price=quote_data['open_price'],
                                        high_price=quote_data['high_price'],
                                        low_price=quote_data['low_price'],
                                        close_price=quote_data['close_price'],
                                        last_trade_time=quote_data['last_trade_time'],
                                        oi=quote_data['oi'],
                                        oi_high=quote_data['oi_high'],
                                        oi_low=quote_data['oi_low'],
                                        exchange_timestamp=quote_data['exchange_timestamp'],
                                        timestamp=current_time
                                    )
                                    db.add(db_quote)
                                    db.commit()
                                    logger.info(f"Stored quote for instrument {quote_data['instrument_token']}: ₹{quote_data['last_price']} at {current_time}")
                        except ConnectionClosed:
                            logger.warning("WebSocket connection closed, attempting to reconnect...")
                            break
                        except Exception as e:
                            logger.error(f"Error processing message: {str(e)}")
                            continue
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
                finally:
                    db.close()
                    
        except Exception as e:
            logger.error(f"WebSocket connection error: {str(e)}")
            
        logger.info("Waiting 5 seconds before reconnecting...")
        await asyncio.sleep(5)

def process_binary_message(binary_data):
    """Process binary message from WebSocket"""
    try:
        # First 2 bytes are the number of packets
        num_packets = int.from_bytes(binary_data[0:2], byteorder='big')
        
        # Next 2 bytes are the length of first packet
        packet_length = int.from_bytes(binary_data[2:4], byteorder='big')
        
        # Extract first packet
        packet = binary_data[4:4+packet_length]
        
        current_time = datetime.now()
        
        # Process packet according to Kite's binary protocol
        instrument_token = int.from_bytes(packet[0:4], byteorder='big')
        last_price = int.from_bytes(packet[4:8], byteorder='big') / 100.0
        last_quantity = int.from_bytes(packet[8:12], byteorder='big')
        average_price = int.from_bytes(packet[12:16], byteorder='big') / 100.0
        volume = int.from_bytes(packet[16:20], byteorder='big')
        buy_quantity = int.from_bytes(packet[20:24], byteorder='big')
        sell_quantity = int.from_bytes(packet[24:28], byteorder='big')
        open_price = int.from_bytes(packet[28:32], byteorder='big') / 100.0
        high_price = int.from_bytes(packet[32:36], byteorder='big') / 100.0
        low_price = int.from_bytes(packet[36:40], byteorder='big') / 100.0
        close_price = int.from_bytes(packet[40:44], byteorder='big') / 100.0
        
        # Convert timestamps
        last_trade_time = datetime.fromtimestamp(int.from_bytes(packet[44:48], byteorder='big'))
        oi = int.from_bytes(packet[48:52], byteorder='big')
        oi_high = int.from_bytes(packet[52:56], byteorder='big')
        oi_low = int.from_bytes(packet[56:60], byteorder='big')
        exchange_timestamp = datetime.fromtimestamp(int.from_bytes(packet[60:64], byteorder='big'))
        
        return {
            'instrument_token': instrument_token,
            'last_price': last_price,
            'last_quantity': last_quantity,
            'average_price': average_price,
            'volume': volume,
            'buy_quantity': buy_quantity,
            'sell_quantity': sell_quantity,
            'open_price': open_price,
            'high_price': high_price,
            'low_price': low_price,
            'close_price': close_price,
            'last_trade_time': last_trade_time,
            'oi': oi,
            'oi_high': oi_high,
            'oi_low': oi_low,
            'exchange_timestamp': exchange_timestamp,
            'timestamp': current_time
        }
    except Exception as e:
        logger.error(f"Error processing binary message: {str(e)}")
        return None

@app.get("/start-streaming")
async def start_streaming(request_token: str):
    """Start WebSocket streaming using request token from env"""
    try:
        if request_token != "NA":
            # Get request token from environment variables
            request_token = request_token
            
            if not request_token:
                raise HTTPException(
                    status_code=500, 
                    detail="REQUEST_TOKEN not found in environment variables"
                )

            # Generate access token
            input_string = f"{settings.KITE_API_KEY}{request_token}{settings.KITE_SECRET_KEY}"
            checksum = hashlib.sha256(input_string.encode()).hexdigest()
            
            logger.info(f"Attempting to generate access token with API key: {settings.KITE_API_KEY[:5]}...")
            
            response = requests.post(
                "https://api.kite.trade/session/token",
                headers={
                    "X-Kite-Version": "3"
                },
                data={
                    "api_key": settings.KITE_API_KEY,
                    "request_token": request_token,
                    "checksum": checksum
                }
            )
            
            if response.status_code != 200:
                error_msg = f"Status Code: {response.status_code}, Response: {response.text}"
                logger.error(f"Failed to generate access token: {error_msg}")
                raise HTTPException(
                    status_code=500, 
                    detail=f"Could not generate access token: {error_msg}"
                )
                
            access_token = response.json()["data"]["access_token"]
            logger.info("Successfully generated access token")
            
            # Update the .env file with new access token
            env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
            set_key(env_path, 'KITE_ACCESS_TOKEN', access_token)
            logger.info("Updated .env file with new access token")
            
            # Reload environment variables
            load_dotenv(env_path, override=True)
            
            # Start WebSocket connection in background with auto-reconnection
            asyncio.create_task(connect_websocket(settings.KITE_ACCESS_TOKEN))
            
            return {
                "status": "success",
                "message": "WebSocket streaming started and access token updated",
                "access_token": access_token[:5] + "..." # Show first 5 chars for verification
            }
        else:
            asyncio.create_task(connect_websocket("Td1v25W0tP7ursVop6MaTL6pYPSyMpOO"))
        
    except Exception as e:
        logger.error(f"Error starting stream: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "running"}

@app.get("/candles")
async def get_all_candle_data(
    interval: str = "day",
    from_date: str = None,
    to_date: str = None,
    db: Session = Depends(get_db)
):
    try:
        stocks = db.query(Stock).filter(Stock.instrument_token.isnot(None)).all()
        
        if not stocks:
            return {"status": "error", "message": "No instruments found"}

        # Set default date range if not provided
        if not from_date:
            from_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%d")

        # Clean up date strings and parse to datetime
        try:
            # Handle different date formats
            date_formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y-%m-%d%H:%M:%S",  # No space
                "%Y%m%d%H%M%S",
                "%Y%m%d"
            ]

            from_date_dt = None
            to_date_dt = None

            # Try different formats for from_date
            for fmt in date_formats:
                try:
                    from_date_dt = datetime.strptime(from_date, fmt)
                    break
                except ValueError:
                    continue

            # Try different formats for to_date
            for fmt in date_formats:
                try:
                    to_date_dt = datetime.strptime(to_date, fmt) if to_date else datetime.now()
                    break
                except ValueError:
                    continue

            if not from_date_dt:
                raise ValueError(f"Could not parse from_date: {from_date}")
            if not to_date_dt:
                raise ValueError(f"Could not parse to_date: {to_date}")

            # Convert to proper format for Kite API
            from_date = from_date_dt.strftime("%Y-%m-%d")
            to_date = to_date_dt.strftime("%Y-%m-%d")
            
            logger.info(f"Parsed dates - From: {from_date}, To: {to_date}")
            
        except Exception as e:
            logger.error(f"Date parsing error: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS. Error: {str(e)}"
            )

        # Initialize Kite Connect
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        kite.set_access_token(settings.KITE_ACCESS_TOKEN)

        all_candles = {}

        for stock in stocks:
            try:
                db.begin_nested()
                
                try:
                    # Check existing data
                    candles = db.query(CandleData).filter(
                        CandleData.instrument_token == stock.instrument_token,
                        CandleData.interval == interval,
                        CandleData.timestamp.between(from_date, to_date)
                    ).order_by(CandleData.timestamp.asc()).all()

                    if not candles:
                        all_kite_candles = []
                        
                        # Split date range into chunks of 60 days
                        current_from = from_date_dt
                        while current_from < to_date_dt:
                            # Calculate chunk end date
                            chunk_to = min(current_from + timedelta(days=60), to_date_dt)
                            
                            logger.info(f"Fetching data for {stock.ticker_symbol} from {current_from.strftime('%Y-%m-%d')} to {chunk_to.strftime('%Y-%m-%d')}")
                            
                            try:
                                chunk_candles = kite.historical_data(
                                    instrument_token=stock.instrument_token,
                                    from_date=current_from.strftime("%Y-%m-%d"),
                                    to_date=chunk_to.strftime("%Y-%m-%d"),
                                    interval=interval
                                )
                                if chunk_candles:
                                    all_kite_candles.extend(chunk_candles)
                                    logger.info(f"Got {len(chunk_candles)} candles for {stock.ticker_symbol}")
                                
                                # Add delay to avoid rate limiting
                                await asyncio.sleep(0.5)
                                
                            except Exception as e:
                                logger.error(f"Error fetching chunk for {stock.ticker_symbol}: {str(e)}")
                            
                            # Move to next chunk
                            current_from = chunk_to + timedelta(days=1)
                        
                        if all_kite_candles:
                            # Store all fetched candles
                            for candle in all_kite_candles:
                                new_candle = CandleData(
                                    instrument_token=stock.instrument_token,
                                    interval=interval,
                                    timestamp=candle['date'],
                                    open=candle['open'],
                                    high=candle['high'],
                                    low=candle['low'],
                                    close=candle['close'],
                                    volume=candle['volume'],
                                    oi=candle.get('oi'),
                                    created_at=datetime.utcnow()
                                )
                                db.add(new_candle)
                            
                            db.commit()
                            
                            # Query all stored candles
                            candles = db.query(CandleData).filter(
                                CandleData.instrument_token == stock.instrument_token,
                                CandleData.interval == interval,
                                CandleData.timestamp.between(from_date, to_date)
                            ).order_by(CandleData.timestamp.asc()).all()
                            
                            logger.info(f"Stored {len(candles)} candles for {stock.ticker_symbol}")
                        else:
                            logger.error(f"No data returned for {stock.ticker_symbol}")
                            db.rollback()
                            continue

                    # Format response
                    all_candles[stock.instrument_token] = {
                        "company_name": stock.company_name,
                        "ticker_symbol": stock.ticker_symbol,
                        "candles": [
                            {
                                "timestamp": c.timestamp,
                                "open": c.open,
                                "high": c.high,
                                "low": c.low,
                                "close": c.close,
                                "volume": c.volume,
                                "oi": c.oi
                            } for c in candles
                        ]
                    }
                    db.commit()
                    
                except Exception as e:
                    db.rollback()
                    logger.error(f"Database error for {stock.ticker_symbol}: {str(e)}")
                    continue

            except Exception as e:
                logger.error(f"Error processing {stock.ticker_symbol}: {str(e)}")
                continue

        return {
            "status": "success",
            "data": {
                "interval": interval,
                "from": from_date,
                "to": to_date,
                "instruments": all_candles
            }
        }

    except Exception as e:
        logger.error(f"Error fetching candle data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-stocks-csv")
async def upload_stocks_csv(db: Session = Depends(get_db)):
    """Upload stocks from CSV and get their instrument tokens"""
    try:
        # Read the CSV file
        df = pd.read_csv('/Users/siddhimhadlekar/Documents/stocks.csv')
        
        # Initialize Kite Connect
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        kite.set_access_token(settings.KITE_ACCESS_TOKEN)
        
        # Get all instruments from Kite
        instruments = kite.instruments("NSE")
        
        # Create a mapping of symbol to instrument token
        symbol_to_token = {instrument['tradingsymbol']: instrument['instrument_token'] 
                          for instrument in instruments}
        
        added_count = 0
        updated_count = 0
        
        # Process each stock
        for _, row in df.iterrows():
            company_name = row['Company Name']
            ticker_symbol = row['Ticker Symbol']
            
            # Get instrument token for this symbol
            instrument_token = symbol_to_token.get(ticker_symbol)
            
            if not instrument_token:
                logger.warning(f"No instrument token found for {ticker_symbol}")
                continue
                
            # Check if stock already exists
            existing_stock = db.query(Stock).filter(Stock.ticker_symbol == ticker_symbol).first()
            
            if existing_stock:
                # Update existing stock if needed
                if (existing_stock.company_name != company_name or 
                    existing_stock.instrument_token != instrument_token):
                    existing_stock.company_name = company_name
                    existing_stock.instrument_token = instrument_token
                    updated_count += 1
            else:
                # Create new stock entry
                new_stock = Stock(
                    company_name=company_name,
                    ticker_symbol=ticker_symbol,
                    instrument_token=instrument_token
                )
                db.add(new_stock)
                added_count += 1
        
        db.commit()
        return {
            "status": "success",
            "message": f"Processed stocks: {added_count} added, {updated_count} updated"
        }
        
    except Exception as e:
        logger.error(f"Error uploading stocks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/add-stock")
async def add_stock(
    company_name: str,
    ticker_symbol: str,
    db: Session = Depends(get_db)
):
    """Add a single stock with company name and ticker symbol"""
    try:
        # Check if stock already exists
        existing_stock = db.query(Stock).filter(Stock.ticker_symbol == ticker_symbol).first()
        if existing_stock:
            return {
                "status": "error",
                "message": f"Stock with ticker {ticker_symbol} already exists"
            }
            
        # Initialize Kite Connect
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        kite.set_access_token(settings.KITE_ACCESS_TOKEN)
        
        # Get instrument token for this symbol
        instruments = kite.instruments("NSE")
        instrument_token = None
        
        for instrument in instruments:
            if instrument['tradingsymbol'] == ticker_symbol:
                instrument_token = instrument['instrument_token']
                break
                
        if not instrument_token:
            return {
                "status": "error",
                "message": f"No instrument token found for {ticker_symbol}"
            }
            
        # Create new stock
        new_stock = Stock(
            company_name=company_name,
            ticker_symbol=ticker_symbol,
            instrument_token=instrument_token
        )
        
        db.add(new_stock)
        db.commit()
        
        return {
            "status": "success",
            "message": "Stock added successfully",
            "data": {
                "company_name": company_name,
                "ticker_symbol": ticker_symbol,
                "instrument_token": instrument_token
            }
        }
        
    except Exception as e:
        logger.error(f"Error adding stock: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/calculate-indicators/all")
async def calculate_all_indicators(db: Session = Depends(get_db)):
    """Calculate indicators for all stocks"""
    try:
        ta_service = TechnicalAnalysisService(db)
        results = ta_service.calculate_store_indicators_for_all_stocks()
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail="No indicators calculated. Check logs for details."
            )
            
        return {
            "status": "success",
            "message": f"Calculated indicators for {len(results)} stocks",
            "data": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/indicators/{instrument_token}")
async def get_stock_indicators(
    instrument_token: int,
    days: Optional[int] = 1,
    db: Session = Depends(get_db)
):
    """Get indicators for a specific stock"""
    try:
        # Get stock info
        stock = db.query(Stock).filter(
            Stock.instrument_token == instrument_token
        ).first()
        
        if not stock:
            raise HTTPException(
                status_code=404,
                detail=f"Stock with instrument token {instrument_token} not found"
            )
            
        # Get latest indicators
        indicators = db.query(TechnicalIndicators).filter(
            TechnicalIndicators.instrument_token == instrument_token,
            TechnicalIndicators.calculated_at >= datetime.now() - timedelta(days=days)
        ).order_by(TechnicalIndicators.calculated_at.desc()).all()
        
        if not indicators:
            raise HTTPException(
                status_code=404,
                detail=f"No indicators found for {stock.ticker_symbol}"
            )
            
        return {
            "status": "success",
            "data": {
                "stock": {
                    "ticker": stock.ticker_symbol,
                    "company_name": stock.company_name
                },
                "indicators": [{
                    "calculated_at": ind.calculated_at,
                    "data_timestamp": ind.data_timestamp,
                    "price": {
                        "close": ind.last_close,
                        "volume": ind.last_volume
                    },
                    "moving_averages": {
                        "sma": {
                            "5": ind.sma_5,
                            "10": ind.sma_10,
                            "20": ind.sma_20,
                            "50": ind.sma_50,
                            "200": ind.sma_200
                        },
                        "ema": {
                            "5": ind.ema_5,
                            "10": ind.ema_10,
                            "20": ind.ema_20,
                            "50": ind.ema_50,
                            "200": ind.ema_200
                        }
                    },
                    "momentum": {
                        "rsi": {
                            "value": ind.rsi_14,
                            "is_overbought": ind.is_overbought,
                            "is_oversold": ind.is_oversold
                        },
                        "macd": {
                            "value": ind.macd,
                            "signal": ind.macd_signal,
                            "histogram": ind.macd_histogram,
                            "bullish_crossover": ind.macd_bullish_crossover,
                            "bearish_crossover": ind.macd_bearish_crossover
                        }
                    },
                    "volatility": {
                        "bollinger_bands": {
                            "upper": ind.bb_upper,
                            "middle": ind.bb_middle,
                            "lower": ind.bb_lower,
                            "bandwidth": ind.bb_bandwidth
                        }
                    },
                    "volume": {
                        "sma_20": ind.volume_sma_20,
                        "obv": ind.volume_obv,
                        "mfi": ind.volume_mfi,
                        "roc": ind.volume_roc,
                        "avg_ratio": ind.volume_avg_ratio
                    },
                    "fibonacci": {
                        "recent_high": ind.fib_recent_high,
                        "recent_low": ind.fib_recent_low,
                        "levels": {
                            "0.236": ind.fib_0_236,
                            "0.382": ind.fib_0_382,
                            "0.5": ind.fib_0_5,
                            "0.618": ind.fib_0_618,
                            "0.786": ind.fib_0_786
                        }
                    }
                } for ind in indicators]
            }
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/indicators/signals/oversold")
async def get_oversold_stocks(db: Session = Depends(get_db)):
    """Get all currently oversold stocks"""
    try:
        # Get latest oversold stocks
        results = db.query(
            Stock.ticker_symbol,
            Stock.company_name,
            TechnicalIndicators
        ).join(
            TechnicalIndicators,
            Stock.instrument_token == TechnicalIndicators.instrument_token
        ).filter(
            TechnicalIndicators.is_oversold == True,
            TechnicalIndicators.calculated_at >= datetime.now() - timedelta(hours=24)
        ).all()
        
        if not results:
            return {
                "status": "success",
                "message": "No oversold stocks found",
                "data": []
            }
            
        return {
            "status": "success",
            "data": [{
                "ticker": r.ticker_symbol,
                "company_name": r.company_name,
                "rsi": r[2].rsi_14,
                "last_price": r[2].last_close,
                "volume_ratio": r[2].volume_avg_ratio,
                "calculated_at": r[2].calculated_at
            } for r in results]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analysis/all-stocks")
async def analyze_all_stocks(
    db: Session = Depends(get_db)
):
    """Get analysis for all stocks"""
    analysis_service = StockAnalysisService(db)
    return analysis_service.analyze_all_stocks()

@app.get("/analysis/historical/{days}")
async def get_historical_analysis(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get historical analysis for comparison"""
    analysis_service = StockAnalysisService(db)
    return analysis_service.get_historical_analysis(days)

class OrderRequest(BaseModel):
    symbol: str
    quantity: int
    price: Optional[float] = 0
    is_intraday: bool = False
    is_market_order: bool = True
    stop_loss: Optional[float] = 0
    target: Optional[float] = 0
    exchange: str = "BSE"
    
    class Config:
        schema_extra = {
            "example": {
                "symbol": "TATASTEEL",
                "quantity": 1,
                "price": 0,
                "is_intraday": False,
                "is_market_order": True,
                "stop_loss": 0,
                "target": 0,
                "exchange": "NSE"
            }
        }

@app.get("/account/balance")
async def get_balance():
    """Get account balance and margins"""
    return await order_service.get_account_balance()

@app.post("/orders/buy")
async def place_buy_order(
    order_data: OrderRequest,
    order_service: OrderService = Depends(get_order_service)
):
    """Place a buy order"""
    try:
        return await order_service.place_order(
            symbol=order_data.symbol,
            quantity=order_data.quantity,
            price=order_data.price,
            is_intraday=order_data.is_intraday,
            is_market_order=order_data.is_market_order,
            stop_loss=order_data.stop_loss,
            target=order_data.target,
            exchange=order_data.exchange
        )
    except Exception as e:
        logger.error(f"Error placing buy order: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/orders/sell")
async def place_sell_order(
    order_data: OrderRequest,
    order_service: OrderService = Depends(get_order_service)
):
    """Place a sell order"""
    try:
        return await order_service.place_sell_order(
            symbol=order_data.symbol,
            quantity=order_data.quantity,
            price=order_data.price,
            is_intraday=order_data.is_intraday,
            is_market_order=order_data.is_market_order,
            stop_loss=order_data.stop_loss,
            target=order_data.target,
            exchange=order_data.exchange
        )
    except Exception as e:
        logger.error(f"Error placing sell order: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/orders")
async def get_orders():
    """Get all orders"""
    return await order_service.get_order_history()

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Get specific order details"""
    return await order_service.get_order_history(order_id)

@app.delete("/orders/{variety}/{order_id}")
async def cancel_order(variety: str, order_id: str):
    """Cancel an order"""
    return await order_service.cancel_order(variety, order_id)

@app.put("/orders/{variety}/{order_id}")
async def modify_order(variety: str, order_id: str, order: OrderRequest):
    """Modify an existing order"""
    try:
        modify_params = {
            "tradingsymbol": order.symbol,
            "quantity": order.quantity
        }

        if not order.is_market_order:
            modify_params["price"] = order.price

        return await order_service.modify_order(
            variety=variety,
            order_id=order_id,
            params=modify_params
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/trades")
async def get_trades():
    """Get all trades"""
    return await order_service.get_trades()

@app.get("/trades/{order_id}")
async def get_order_trades(order_id: str):
    """Get trades for specific order"""
    return await order_service.get_trades(order_id)

@app.post("/admin/holidays/update")
async def update_holidays(db: Session = Depends(get_db)):
    """Update holiday database from exchange APIs"""
    holiday_service = HolidayService(db)
    return await holiday_service.update_holiday_database()

@app.get("/market/holidays/{year}")
async def get_holidays(
    year: int = datetime.now().year,
    db: Session = Depends(get_db)
):
    """Get market holidays for a specific year"""
    holiday_service = HolidayService(db)
    holidays = await holiday_service.get_holidays(year)
    
    return {
        "status": "success",
        "data": {
            "year": year,
            "holidays": [
                {
                    "date": holiday.date.strftime("%B %d, %Y"),
                    "day": holiday.date.strftime("%A"),
                    "holiday_name": holiday.holiday_name,
                    "exchange": holiday.exchange,
                    "is_full_day": holiday.is_full_day
                }
                for holiday in holidays
            ]
        }
    }

@app.get("/dashboard/stocks")
async def get_dashboard_stocks(db: Session = Depends(get_db)):
    """Get latest stock data for dashboard"""
    try:
        # Get all stocks with their latest quotes and analysis
        stocks = db.query(Stock).all()
        dashboard_data = []

        for stock in stocks:
            # Get latest quote
            latest_quote = db.query(QuoteData).filter(
                QuoteData.instrument_token == stock.instrument_token
            ).order_by(QuoteData.timestamp.desc()).first()

            # Get latest analysis
            latest_analysis = db.query(StockAnalysis).filter(
                StockAnalysis.instrument_token == stock.instrument_token
            ).order_by(StockAnalysis.analyzed_at.desc()).first()

            if latest_quote:
                dashboard_data.append({
                    "id": stock.id,
                    "symbol": stock.ticker_symbol,
                    "name": stock.company_name,
                    "current_price": latest_quote.last_price,
                    "updated_at": latest_quote.timestamp,
                    "analysis": {
                        "recommendation": latest_analysis.trading_action if latest_analysis else "HOLD",
                        "confidence": latest_analysis.confidence_level if latest_analysis else "LOW",
                        "key_reason": latest_analysis.key_reason if latest_analysis else "",
                        "target_price": latest_analysis.target_price if latest_analysis else None,
                        "stop_loss": latest_analysis.stop_loss if latest_analysis else None
                    } if latest_analysis else None
                })

        return {
            "status": "success",
            "data": dashboard_data
        }

    except Exception as e:
        logger.error(f"Error fetching dashboard data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stock/{symbol}/analysis")
async def get_stock_analysis(symbol: str, db: Session = Depends(get_db)):
    """Get detailed analysis for a specific stock"""
    try:
        # Find the stock
        stock = db.query(Stock).filter(Stock.ticker_symbol == symbol).first()
        if not stock:
            raise HTTPException(status_code=404, detail=f"Stock with symbol {symbol} not found")
            
        # Get latest analysis
        latest_analysis = db.query(StockAnalysis).filter(
            StockAnalysis.instrument_token == stock.instrument_token
        ).order_by(StockAnalysis.analyzed_at.desc()).first()
        
        if not latest_analysis:
            return {
                "status": "success",
                "data": {
                    "symbol": symbol,
                    "name": stock.company_name,
                    "analysis": None
                }
            }
            
        return {
            "status": "success",
            "data": {
                "symbol": symbol,
                "name": stock.company_name,
                "analysis": {
                    "recommendation": latest_analysis.trading_action,
                    "confidence": latest_analysis.confidence_level,
                    "key_reason": latest_analysis.key_reason,
                    "target_price": latest_analysis.target_price,
                    "stop_loss": latest_analysis.stop_loss,
                    "analyzed_at": latest_analysis.analyzed_at.isoformat(),
                    "full_analysis": latest_analysis.analysis_text
                }
            }
        }
    except Exception as e:
        logger.error(f"Error fetching stock analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Example usage of the endpoints:
"""
1. Check balance:
GET /account/balance

2. Place market buy order:
POST /orders/buy
{
    "symbol": "TATASTEEL",
    "quantity": 10,
    "is_intraday": false,
    "is_market_order": true
}

3. Place limit sell order:
POST /orders/sell
{
    "symbol": "RELIANCE",
    "quantity": 5,
    "price": 2450.30,
    "is_intraday": true,
    "is_market_order": false
}

4. Check order status:
GET /orders/{order_id}

5. Cancel order:
DELETE /orders/regular/{order_id}

6. View all trades:
GET /trades
"""