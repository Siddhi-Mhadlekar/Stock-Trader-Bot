from kiteconnect import KiteTicker
from sqlalchemy.orm import Session
from .models import QuoteData
from .config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KiteWebsocketManager:
    def __init__(self, db: Session):
        self.db = db
        self.kws = KiteTicker(settings.KITE_API_KEY, settings.KITE_SECRET_KEY)
        
        # Set callbacks
        self.kws.on_ticks = self.on_ticks
        self.kws.on_connect = self.on_connect
        self.kws.on_close = self.on_close
        self.kws.on_error = self.on_error

    def on_ticks(self, ws, ticks):
        for tick in ticks:
            quote = QuoteData(
                instrument_token=tick.get('instrument_token'),
                last_price=tick.get('last_price'),
                volume=tick.get('volume'),
                average_price=tick.get('average_price'),
                oi=tick.get('oi'),
                buy_quantity=tick.get('buy_quantity'),
                sell_quantity=tick.get('sell_quantity')
            )
            self.db.add(quote)
            self.db.commit()
            logger.info(f"Stored tick data for instrument {tick.get('instrument_token')}")

    def on_connect(self, ws, response):
        logger.info("Successfully connected to Kite WebSocket")
        # Subscribe to the instruments you want to track
        # Example: self.kws.subscribe([<instrument_tokens>])

    def on_close(self, ws, code, reason):
        logger.info(f"Connection closed: {reason}")

    def on_error(self, ws, code, reason):
        logger.error(f"Error: {reason}")

    def start(self, instruments):
        """
        Start the WebSocket connection
        instruments: list of instrument tokens to subscribe to
        """
        self.kws.subscribe(instruments)
        self.kws.connect() 