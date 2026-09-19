from datetime import datetime
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from app.models import MarketHoliday

class HolidayService:
    def __init__(self, db: Session):
        self.db = db
        self.NSE_HOLIDAY_URL = "https://www.nseindia.com/api/holiday-master"
        self.BSE_HOLIDAY_URL = "https://www.bseindia.com/markets/MarketInfo/BhavCopy.aspx"

    async def fetch_nse_holidays(self) -> list:
        """Fetch NSE holidays from their API"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.NSE_HOLIDAY_URL, headers=headers)
            holidays = response.json()
            
            return holidays['data']
        except Exception as e:
            logger.error(f"Error fetching NSE holidays: {str(e)}")
            return []

    async def update_holiday_database(self):
        """Update holiday database with latest data"""
        try:
            # Fetch holidays from exchanges
            nse_holidays = await self.fetch_nse_holidays()
            
            current_year = datetime.now().year
            
            # Clear existing holidays for current year
            self.db.query(MarketHoliday).filter(
                MarketHoliday.year == current_year
            ).delete()
            
            # Add new holidays
            for holiday in nse_holidays:
                holiday_date = datetime.strptime(
                    holiday['tradingDate'], 
                    '%d-%b-%Y'
                ).date()
                
                new_holiday = MarketHoliday(
                    date=holiday_date,
                    holiday_name=holiday['description'],
                    exchange='NSE',
                    is_full_day=True,
                    year=holiday_date.year
                )
                self.db.add(new_holiday)
            
            self.db.commit()
            return {"status": "success", "message": "Holidays updated successfully"}
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating holidays: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error updating holidays: {str(e)}"
            )

    async def get_holidays(self, year: int = None) -> list:
        """Get holidays for a specific year"""
        try:
            query = self.db.query(MarketHoliday)
            if year:
                query = query.filter(MarketHoliday.year == year)
            
            holidays = query.all()
            return holidays
            
        except Exception as e:
            logger.error(f"Error fetching holidays: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching holidays: {str(e)}"
            )
