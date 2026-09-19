from typing import Dict, Optional
import logging
from kiteconnect import KiteConnect
from fastapi import HTTPException
from app.config import settings
from datetime import datetime, time as datetime_time, date
import pytz
from sqlalchemy.orm import Session
from app.models import MarketHoliday, Stock, Order
import time as unix_time

logger = logging.getLogger(__name__)

class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.kite = KiteConnect(api_key=settings.KITE_API_KEY)
        self.kite.set_access_token(settings.KITE_ACCESS_TOKEN)
        
        # Define market hours
        self.MARKET_START = datetime_time(9, 15)  # 9:15 AM
        self.MARKET_END = datetime_time(15, 30)   # 3:30 PM
        self.MARKET_PRE_OPEN = datetime_time(9, 0)  # 9:00 AM
        
        # Set timezone
        self.INDIA_TZ = pytz.timezone('Asia/Kolkata')

    def _check_market_hours(self):
        """Check if market is open"""
        current_time = datetime.now(self.INDIA_TZ).time()
        if not (self.MARKET_START <= current_time <= self.MARKET_END):
            raise HTTPException(
                status_code=400,
                detail=f"Market is closed. Trading hours are {self.MARKET_START.strftime('%H:%M')} to {self.MARKET_END.strftime('%H:%M')} IST"
            )

    def _check_trading_day(self):
        """Check if today is a trading day"""
        today = datetime.now(self.INDIA_TZ).date()
        
        # Check if it's a weekend
        if today.weekday() in [5, 6]:  # 5 is Saturday, 6 is Sunday
            raise HTTPException(
                status_code=400,
                detail="Markets are closed on weekends"
            )
            
        # Check if it's a holiday
        holiday = self.db.query(MarketHoliday).filter(
            MarketHoliday.date == today,
            MarketHoliday.is_full_day == True
        ).first()
        
        if holiday:
            raise HTTPException(
                status_code=400,
                detail=f"Market is closed for {holiday.holiday_name}"
            )

    async def get_account_balance(self) -> Dict:
        """Get account balance and margins"""
        try:
            margins = self.kite.margins()
            logger.info(f"Raw margins data: {margins}")

            equity_margins = margins.get("equity", {})
            available = equity_margins.get("available", {})

            # Include all possible balance components
            total_available = sum([
                float(available.get("cash", 0)),
                float(available.get("live_balance", 0)),  # Added live_balance
                float(available.get("intraday_payin", 0)),  # Added intraday_payin
                float(available.get("collateral", 0)),
                float(available.get("opening_balance", 0))  # Added opening_balance
            ])

            return {
                "status": "success",
                "data": {
                    "total_available": total_available,
                    "live_balance": float(available.get("live_balance", 0)),
                    "intraday_payin": float(available.get("intraday_payin", 0)),
                    "cash": float(available.get("cash", 0)),
                    "collateral": float(available.get("collateral", 0)),
                    "opening_balance": float(available.get("opening_balance", 0)),
                    "margins": {
                        "enabled": equity_margins.get("enabled", False),
                        "net": float(equity_margins.get("net", 0)),
                        "available": available,
                        "used": equity_margins.get("utilised", {})
                    }
                }
            }
        except Exception as e:
            logger.error(f"Error fetching margins: {str(e)}")
            logger.exception("Full error details:")
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Unable to fetch account balance",
                    "error": str(e)
                }
            )

    async def get_stock_quote(self, symbol: str) -> float:
        """Get current market price for a stock"""
        try:
            quote = self.kite.quote(f"NSE:{symbol}")
            return quote[f"NSE:{symbol}"]["last_price"]
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Unable to fetch quote for {symbol}")

    async def validate_order(self, symbol: str, quantity: int, price: Optional[float] = None) -> Dict:
        """Validate order before placing"""
        try:
            # Get account balance
            balance_info = await self.get_account_balance()
            total_available = balance_info["data"]["total_available"]
            
            # Get current stock price if not provided
            current_price = price or await self.get_stock_quote(symbol)
            
            # Calculate order value
            order_value = quantity * current_price
            
            logger.info(f"""
            Order Validation Details:
            Symbol: {symbol}
            Quantity: {quantity}
            Price: {current_price}
            Order Value: {order_value}
            Available Balance: {total_available}
            Live Balance: {balance_info["data"]["live_balance"]}
            Intraday Payin: {balance_info["data"]["intraday_payin"]}
            """)
            
            # Check if enough balance available
            if order_value > total_available:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Insufficient funds for order",
                        "required_amount": order_value,
                        "available_balance": total_available,
                        "balance_breakdown": {
                            "live_balance": balance_info["data"]["live_balance"],
                            "intraday_payin": balance_info["data"]["intraday_payin"],
                            "cash": balance_info["data"]["cash"],
                            "collateral": balance_info["data"]["collateral"],
                            "opening_balance": balance_info["data"]["opening_balance"]
                        },
                        "margin_details": balance_info["data"]["margins"]
                    }
                )
            
            return {
                "is_valid": True,
                "order_value": order_value,
                "current_price": current_price,
                "available_balance": total_available,
                "balance_breakdown": {
                    "live_balance": balance_info["data"]["live_balance"],
                    "intraday_payin": balance_info["data"]["intraday_payin"],
                    "cash": balance_info["data"]["cash"],
                    "collateral": balance_info["data"]["collateral"],
                    "opening_balance": balance_info["data"]["opening_balance"]
                }
            }
            
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error validating order: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def is_market_open(self) -> bool:
        """Check if market is currently open"""
        current_time = datetime.now(self.INDIA_TZ).time()
        
        # Check if it's a weekday (0 = Monday, 6 = Sunday)
        is_weekday = datetime.now(self.INDIA_TZ).weekday() < 5
        
        return (
            is_weekday and 
            self.MARKET_START <= current_time <= self.MARKET_END
        )

    async def validate_trading_hours(self) -> None:
        """Validate if order can be placed at current time"""
        current_time = datetime.now(self.INDIA_TZ).time()
        current_day = datetime.now(self.INDIA_TZ).weekday()
        
        # Check for weekends
        if current_day >= 5:  # Saturday = 5, Sunday = 6
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Markets are closed (Weekend)",
                    "trading_hours": {
                        "regular": "9:15 AM - 3:30 PM",
                        "pre_market": "9:00 AM - 9:15 AM",
                        "days": "Monday to Friday"
                    }
                }
            )
        
        # Check market hours
        if not self.MARKET_START <= current_time <= self.MARKET_END:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Markets are closed",
                    "current_time": current_time.strftime("%I:%M %p"),
                    "trading_hours": {
                        "regular": "9:15 AM - 3:30 PM",
                        "pre_market": "9:00 AM - 9:15 AM",
                        "days": "Monday to Friday"
                    }
                }
            )

    async def validate_trading_segment(self, exchange: str) -> None:
        """Validate if trading segment is enabled"""
        try:
            profile = self.kite.profile()
            enabled_segments = profile.get("exchanges", [])
            
            if exchange not in enabled_segments:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": f"{exchange} is disabled for your account",
                        "enabled_segments": enabled_segments,
                        "action_required": "Please activate the segment at https://console.zerodha.com/account/segment-activation"
                    }
                )
            
            logger.info(f"Trading segment {exchange} is enabled")
            
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error checking segments: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Error validating trading segment",
                    "error": str(e),
                    "exchange": exchange
                }
            )

    async def place_order(self, symbol: str, quantity: int, price: float = 0, 
                         is_intraday: bool = False, is_market_order: bool = True,
                         stop_loss: float = 0, target: float = 0, 
                         exchange: str = "BSE"):
        """Place a buy order"""
        try:
            # Check market hours and trading day
            self._check_market_hours()
            self._check_trading_day()
            
            # Get the stock from the database
            stock = self.db.query(Stock).filter(Stock.ticker_symbol == symbol).first()
            if not stock:
                raise ValueError(f"Stock with symbol {symbol} not found")
            
            # Determine the exchange code
            exchange_code = exchange.upper()  # NSE or BSE
            if exchange_code not in ["NSE", "BSE"]:
                raise ValueError("Exchange must be either NSE or BSE")
            
            # Create order parameters
            order_params = {
                "tradingsymbol": symbol,
                "quantity": quantity,
                "exchange": exchange_code,
                "transaction_type": "BUY",
                "order_type": "MARKET" if is_market_order else "LIMIT",
                "product": "MIS" if is_intraday else "CNC",
            }
            
            # Add price for limit orders
            if not is_market_order and price > 0:
                order_params["price"] = price
            
            # Add stop loss if provided
            if stop_loss > 0:
                order_params["trigger_price"] = stop_loss
            
            # Place the order
            # In a real implementation, you would use the Kite API here
            # kite.place_order(**order_params)
            
            # For now, we'll simulate the order
            order_id = f"ORD{int(unix_time.time())}"
            
            # Save the order to the database
            new_order = Order(
                order_id=order_id,
                instrument_token=stock.instrument_token,
                symbol=symbol,
                exchange=exchange_code,
                quantity=quantity,
                price=price,
                stop_loss=stop_loss,
                target=target,
                is_intraday=is_intraday,
                is_market_order=is_market_order,
                status="OPEN",
                order_type="BUY",
                created_at=datetime.now()
            )
            
            self.db.add(new_order)
            self.db.commit()
            
            return {
                "status": "success",
                "data": {
                    "order_id": order_id,
                    "symbol": symbol,
                    "exchange": exchange_code,
                    "quantity": quantity,
                    "price": price if not is_market_order else "MARKET",
                    "status": "OPEN"
                }
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error placing buy order: {str(e)}")
            raise

    async def get_holdings(self, symbol: str) -> dict:
        """Get holdings for a specific stock"""
        try:
            # Get the stock from database
            stock = self.db.query(Stock).filter(Stock.ticker_symbol == symbol).first()
            if not stock:
                return None

            # Get holdings from Kite Connect
            holdings = self.kite.holdings()
            
            # Find the specific stock in holdings
            stock_holding = next(
                (h for h in holdings if h['tradingsymbol'] == symbol),
                None
            )
            
            if stock_holding:
                return {
                    'symbol': symbol,
                    'quantity': stock_holding['quantity'],
                    'average_price': stock_holding['average_price'],
                    'last_price': stock_holding['last_price'],
                    'pnl': stock_holding['pnl']
                }
            
            return {
                'symbol': symbol,
                'quantity': 0,
                'average_price': 0,
                'last_price': 0,
                'pnl': 0
            }

        except Exception as e:
            logger.error(f"Error fetching holdings for {symbol}: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "message": f"Failed to fetch holdings: {str(e)}",
                    "error": str(e)
                }
            )

    async def place_sell_order(self, symbol: str, quantity: int, price: float = 0, 
                             is_intraday: bool = False, is_market_order: bool = True,
                             stop_loss: float = 0, target: float = 0, 
                             exchange: str = "BSE"):
        """Place a sell order"""
        try:
            # Check market hours and trading day
            self._check_market_hours()
            self._check_trading_day()
            
            # Check if user has sufficient holdings
            holdings = await self.get_holdings(symbol)
            if not holdings or holdings['quantity'] < quantity:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Insufficient holdings",
                        "available": holdings['quantity'] if holdings else 0,
                        "requested": quantity,
                        "symbol": symbol
                    }
                )
            
            # Check account balance
            balance_info = await self.get_account_balance()
            total_available = balance_info["data"]["total_available"]
            
            # Define minimum balance threshold (adjust as needed)
            MIN_BALANCE_THRESHOLD = 1000  # Example: 1000 INR
            
            if total_available < MIN_BALANCE_THRESHOLD:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Account balance is too low",
                        "current_balance": total_available,
                        "minimum_required": MIN_BALANCE_THRESHOLD,
                        "balance_breakdown": {
                            "live_balance": balance_info["data"]["live_balance"],
                            "intraday_payin": balance_info["data"]["intraday_payin"],
                            "cash": balance_info["data"]["cash"],
                            "collateral": balance_info["data"]["collateral"],
                            "opening_balance": balance_info["data"]["opening_balance"]
                        }
                    }
                )
            
            # Get the stock from the database
            stock = self.db.query(Stock).filter(Stock.ticker_symbol == symbol).first()
            if not stock:
                raise ValueError(f"Stock with symbol {symbol} not found")
            
            # Determine the exchange code
            exchange_code = exchange.upper()  # NSE or BSE
            if exchange_code not in ["NSE", "BSE"]:
                raise ValueError("Exchange must be either NSE or BSE")
            
            # Create order parameters
            order_params = {
                "tradingsymbol": symbol,
                "quantity": quantity,
                "exchange": exchange_code,
                "transaction_type": "SELL",
                "order_type": "MARKET" if is_market_order else "LIMIT",
                "product": "MIS" if is_intraday else "CNC",
            }
            
            # Add price for limit orders
            if not is_market_order and price > 0:
                order_params["price"] = price
            
            # Add stop loss if provided
            if stop_loss > 0:
                order_params["trigger_price"] = stop_loss
            
            # Place the order
            # In a real implementation, you would use the Kite API here
            # kite.place_order(**order_params)
            
            # For now, we'll simulate the order
            order_id = f"ORD{int(unix_time.time())}"
            
            # Save the order to the database
            new_order = Order(
                order_id=order_id,
                instrument_token=stock.instrument_token,
                symbol=symbol,
                exchange=exchange_code,
                quantity=quantity,
                price=price,
                stop_loss=stop_loss,
                target=target,
                is_intraday=is_intraday,
                is_market_order=is_market_order,
                status="OPEN",
                order_type="SELL",
                created_at=datetime.now()
            )
            
            self.db.add(new_order)
            self.db.commit()
            
            return {
                "status": "success",
                "data": {
                    "order_id": order_id,
                    "symbol": symbol,
                    "exchange": exchange_code,
                    "quantity": quantity,
                    "price": price if not is_market_order else "MARKET",
                    "status": "OPEN"
                }
            }
            
        except HTTPException as he:
            logger.error(f"Sell order failed: {str(he.detail)}")
            raise he
        except Exception as e:
            logger.error(f"Error placing sell order: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "message": f"Failed to place sell order: {str(e)}",
                    "error": str(e)
                }
            )

    async def modify_order(self, variety: str, order_id: str, params: Dict) -> Dict:
        """Modify an existing order"""
        try:
            # Validate modification if quantity or price changed
            if "quantity" in params or "price" in params:
                await self.validate_order(
                    symbol=params["tradingsymbol"],
                    quantity=params.get("quantity", 0),
                    price=params.get("price")
                )
            
            modified_order_id = self.kite.modify_order(
                variety=variety,
                order_id=order_id,
                **params
            )
            
            return {
                "status": "success",
                "data": {"order_id": modified_order_id}
            }
            
        except Exception as e:
            logger.error(f"Error modifying order: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

    async def cancel_order(self, variety: str, order_id: str) -> Dict:
        """Cancel an order"""
        try:
            cancelled_order_id = self.kite.cancel_order(
                variety=variety,
                order_id=order_id
            )
            
            return {
                "status": "success",
                "data": {"order_id": cancelled_order_id}
            }
            
        except Exception as e:
            logger.error(f"Error cancelling order: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

    async def get_order_history(self, order_id: Optional[str] = None) -> Dict:
        """Get all orders or specific order history"""
        try:
            if order_id:
                orders = self.kite.order_history(order_id)
            else:
                orders = self.kite.orders()
                
            return {
                "status": "success",
                "data": orders
            }
            
        except Exception as e:
            logger.error(f"Error fetching orders: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

    async def get_trades(self, order_id: Optional[str] = None) -> Dict:
        """Get all trades or trades for specific order"""
        try:
            if order_id:
                trades = self.kite.order_trades(order_id)
            else:
                trades = self.kite.trades()
                
            return {
                "status": "success",
                "data": trades
            }
            
        except Exception as e:
            logger.error(f"Error fetching trades: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

    async def get_market_status(self) -> Dict:
        """Get current market status"""
        current_time = datetime.now(self.INDIA_TZ)
        is_open = await self.is_market_open()
        
        return {
            "status": "success",
            "data": {
                "is_market_open": is_open,
                "current_time": current_time.strftime("%I:%M %p"),
                "current_day": current_time.strftime("%A"),
                "trading_hours": {
                    "regular": "9:15 AM - 3:30 PM",
                    "pre_market": "9:00 AM - 9:15 AM",
                    "days": "Monday to Friday"
                }
            }
        }

    async def is_market_holiday(self) -> Dict:
        """Check if today is a market holiday"""
        current_date = datetime.now(self.INDIA_TZ).date()
        
        holiday = self.db.query(MarketHoliday).filter(
            MarketHoliday.date == current_date
        ).first()
        
        if holiday:
            return {
                "is_holiday": True,
                "holiday_name": holiday.holiday_name,
                "date": holiday.date.strftime("%B %d, %Y")
            }
        
        return {
            "is_holiday": False,
            "next_holiday": await self.get_next_holiday(current_date)
        }

    async def get_next_holiday(self, current_date: date) -> Dict:
        """Get the next upcoming holiday"""
        next_holiday = self.db.query(MarketHoliday).filter(
            MarketHoliday.date > current_date
        ).order_by(MarketHoliday.date).first()
        
        if next_holiday:
            return {
                "name": next_holiday.holiday_name,
                "date": next_holiday.date.strftime("%B %d, %Y")
            }
        return None
