from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy.orm import Session
from app.models import TechnicalIndicators, Stock, StockAnalysis
from typing import List, Dict
import json
from openai import OpenAI  # Updated import
from app.config import settings  # Import settings instead of direct API key
import logging

logger = logging.getLogger(__name__)

class StockAnalysisService:
    def __init__(self, db: Session):
        self.db = db
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)  # Initialize client

    def analyze_all_stocks(self) -> List[Dict]:
        """Analyze all stocks and store results"""
        
        stocks = self.db.query(Stock).all()
        analyses = []
        analysis_date = datetime.now()
        stored_count = 0

        for stock in stocks:
            try:
                # Get latest technical indicators
                indicators = self.db.query(TechnicalIndicators).filter(
                    TechnicalIndicators.instrument_token == stock.instrument_token
                ).order_by(TechnicalIndicators.calculated_at.desc()).first()
                
                if not indicators:
                    logger.warning(f"No technical indicators found for {stock.ticker_symbol}")
                    continue

                # Prepare prompt for LLM
                prompt = f"""
                Analyze the following technical indicators for {stock.ticker_symbol} ({stock.company_name}) 
                and provide a concise trading analysis:
                
                Current Price: {indicators.last_close}
                
                Technical Signals:
                1. Trend Analysis:
                   - Price vs SMA20: {indicators.last_close > indicators.sma_20}
                   - Price vs SMA50: {indicators.last_close > indicators.sma_50}
                   - SMA20 vs SMA50: {indicators.sma_20 > indicators.sma_50}
                
                2. Momentum:
                   - RSI(14): {indicators.rsi_14}
                   - Oversold: {indicators.is_oversold}
                   - Overbought: {indicators.is_overbought}
                
                3. MACD Signals:
                   - MACD Line: {indicators.macd}
                   - Signal Line: {indicators.macd_signal}
                   - Bullish Crossover: {indicators.macd_bullish_crossover}
                   - Bearish Crossover: {indicators.macd_bearish_crossover}
                
                4. Price Volatility:
                   - Current Price: {indicators.last_close}
                   - BB Upper: {indicators.bb_upper}
                   - BB Lower: {indicators.bb_lower}
                   - BB Middle: {indicators.bb_middle}
                
                5. Volume Analysis:
                   - Volume Ratio: {indicators.volume_avg_ratio}
                   - MFI: {indicators.volume_mfi}

                Based on these indicators, please provide:
                1. Trading Action (BUY/SELL/HOLD)
                2. Confidence Level (HIGH/MEDIUM/LOW)
                3. Key Reason (1-2 sentences)
                4. Risk Level (HIGH/MEDIUM/LOW)
                5. Suggested Stop Loss
                6. Target Price
                
                Format the response as JSON.
                """

                # Get LLM analysis
                llm_response = self.get_llm_analysis(prompt)

                # Create analysis record
                analysis = StockAnalysis(
                    instrument_token=stock.instrument_token,
                    analyzed_at=analysis_date,
                    ticker_symbol=stock.ticker_symbol,
                    company_name=stock.company_name,
                    current_price=indicators.last_close,
                    
                    # Analysis results
                    trading_action=llm_response["trading_action"],
                    confidence_level=llm_response["confidence_level"],
                    key_reason=llm_response["key_reason"],
                    risk_level=llm_response["risk_level"],
                    stop_loss=llm_response["stop_loss"],
                    target_price=llm_response["target_price"],
                    
                    # Indicators
                    rsi_14=indicators.rsi_14,
                    macd=indicators.macd,
                    volume_ratio=indicators.volume_avg_ratio,
                    
                    # Store complete response
                    raw_analysis=llm_response
                )
                
                try:
                    # Save each analysis individually
                    self.db.add(analysis)
                    self.db.flush()  # Check for errors without committing
                    stored_count += 1
                    logger.info(f"Analysis stored for {stock.ticker_symbol}")
                except Exception as db_error:
                    logger.error(f"Database error for {stock.ticker_symbol}: {str(db_error)}")
                    self.db.rollback()
                    continue

                analyses.append({
                    "stock_info": {
                        "ticker": stock.ticker_symbol,
                        "company_name": stock.company_name,
                        "instrument_token": stock.instrument_token
                    },
                    "current_price": indicators.last_close,
                    "indicators": {
                        "rsi": indicators.rsi_14,
                        "macd": indicators.macd,
                        "volume_ratio": indicators.volume_avg_ratio
                    },
                    "analysis": llm_response,
                    "timestamp": analysis_date
                })

            except Exception as e:
                logger.error(f"Error analyzing {stock.ticker_symbol}: {str(e)}")
                continue

        # Final commit
        try:
            self.db.commit()
            logger.info(f"Successfully stored {stored_count} analyses")
        except Exception as e:
            logger.error(f"Error in final commit: {str(e)}")
            self.db.rollback()

        # Verify storage
        verification = self.db.query(StockAnalysis).filter(
            StockAnalysis.analyzed_at == analysis_date
        ).count()
        
        logger.info(f"Verified {verification} records stored for date {analysis_date}")

        sorted_analyses = self.sort_opportunities(analyses)
        
        return {
            "timestamp": analysis_date,
            "total_stocks_analyzed": len(analyses),
            "records_stored": verification,
            "strong_buy_signals": sorted_analyses["strong_buy"],
            "moderate_buy_signals": sorted_analyses["moderate_buy"],
            "hold_signals": sorted_analyses["hold"],
            "sell_signals": sorted_analyses["sell"],
            "all_analyses": analyses
        }

    def get_historical_analysis(self, days: int = 7) -> Dict:
        """Get historical analysis for comparison"""
        start_date = datetime.now() - timedelta(days=days)
        
        historical_analyses = self.db.query(StockAnalysis).filter(
            StockAnalysis.analyzed_at >= start_date
        ).all()
        
        return {
            "start_date": start_date,
            "end_date": datetime.now(),
            "analyses": [
                {
                    "date": analysis.analyzed_at,
                    "ticker": analysis.ticker_symbol,
                    "action": analysis.trading_action,
                    "confidence": analysis.confidence_level,
                    "price": analysis.current_price,
                    "target": analysis.target_price
                }
                for analysis in historical_analyses
            ]
        }

    def sort_opportunities(self, analyses: List[Dict]) -> Dict:
        """Sort analyses into different categories"""
        sorted_results = {
            "strong_buy": [],
            "moderate_buy": [],
            "hold": [],
            "sell": []
        }

        for analysis in analyses:
            action = analysis["analysis"]["trading_action"]
            confidence = analysis["analysis"]["confidence_level"]
            
            if action == "BUY" and confidence == "HIGH":
                sorted_results["strong_buy"].append(analysis)
            elif action == "BUY":
                sorted_results["moderate_buy"].append(analysis)
            elif action == "SELL":
                sorted_results["sell"].append(analysis)
            else:
                sorted_results["hold"].append(analysis)

        return sorted_results

    def get_llm_analysis(self, prompt: str) -> dict:
        """Get analysis from OpenAI using GPT-4"""
        try:
            # Add JSON instruction in the system prompt instead
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system", 
                        "content": """You are a professional stock market analyst specializing in technical analysis. 
                        Provide precise, data-driven analysis.
                        IMPORTANT: Always respond in valid JSON format with the following structure:
                        {
                            "trading_action": "BUY/SELL/HOLD",
                            "confidence_level": "HIGH/MEDIUM/LOW",
                            "key_reason": "explanation",
                            "risk_level": "HIGH/MEDIUM/LOW",
                            "stop_loss": number,
                            "target_price": number
                        }"""
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # Reduced for more consistent responses
                max_tokens=1000  # Increased token limit for detailed analysis
            )
            
            # Extract and parse JSON response
            analysis = response.choices[0].message.content
            return json.loads(analysis)
            
        except Exception as e:
            print(f"Error in LLM analysis: {str(e)}")
            return {
                "trading_action": "HOLD",
                "confidence_level": "LOW",
                "key_reason": f"Error in analysis: {str(e)}",
                "risk_level": "HIGH",
                "stop_loss": None,
                "target_price": None
            }
