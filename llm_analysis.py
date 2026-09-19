from openai import OpenAI
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .technical_analysis import TechnicalAnalysisService
import json

class RealTimeAnalysisService:
    def __init__(self, db: Session, openai_api_key: str):
        self.db = db
        self.tech_analyzer = TechnicalAnalysisService(db)
        self.llm_client = OpenAI(api_key=openai_api_key)
        self.analysis_interval = timedelta(minutes=5)

    async def process_tick(self, instrument_token: int, tick_data: dict):
        """Process real-time tick data"""
        # Calculate technical indicators
        indicators = self.tech_analyzer.calculate_indicators(tick_data)
        
        # Create database entry
        tech_indicators = TechnicalIndicators(
            instrument_token=instrument_token,
            timestamp=datetime.now(),
            indicators=indicators
        )
        
        # Check if we need new LLM analysis
        last_analysis = self.db.query(TechnicalIndicators).filter(
            TechnicalIndicators.instrument_token == instrument_token,
            TechnicalIndicators.llm_analysis.isnot(None)
        ).order_by(TechnicalIndicators.analysis_timestamp.desc()).first()

        need_analysis = (
            not last_analysis or 
            datetime.now() - last_analysis.analysis_timestamp > self.analysis_interval
        )

        if need_analysis:
            analysis = await self._generate_llm_analysis(indicators)
            tech_indicators.llm_analysis = analysis
            tech_indicators.recommendation = analysis['recommendation']
            tech_indicators.confidence_score = analysis['confidence_score']
            tech_indicators.analysis_timestamp = datetime.now()

        self.db.add(tech_indicators)
        self.db.commit()

        return tech_indicators

    async def _generate_llm_analysis(self, indicators: dict) -> dict:
        """Generate analysis using GPT-4"""
        prompt = f"""
        As an expert stock market analyst, analyze these technical indicators and provide a detailed trading recommendation.
        
        1. Trend Indicators:
        - SMA: {indicators['moving_averages']['sma']}
        - EMA: {indicators['moving_averages']['ema']}
        
        2. Momentum:
        - RSI: {indicators['momentum']['rsi']}
        - MACD: {indicators['momentum']['macd']}
        - Stochastic: {indicators['momentum']['stoch']}
        - CCI: {indicators['momentum']['cci']}
        
        3. Volatility:
        - Bollinger Bands: {indicators['volatility']['bollinger']}
        - ATR: {indicators['volatility']['atr']}
        
        4. Volume Analysis:
        - OBV: {indicators['volume']['obv']}
        - A/D: {indicators['volume']['ad']}
        
        5. Trend Strength:
        - ADX: {indicators['trend']['adx']}
        - DI+: {indicators['trend']['di_plus']}
        - DI-: {indicators['trend']['di_minus']}
        
        6. Pattern Recognition:
        - Patterns: {indicators['patterns']}
        
        7. Oscillators:
        - Ultimate: {indicators['oscillators']['ultimate']}
        - MOM: {indicators['oscillators']['mom']}

        Provide a detailed analysis in JSON format with:
        1. Primary recommendation (BUY/SELL/HOLD)
        2. Confidence score (0-100)
        3. Key reasons for the recommendation
        4. Risk assessment
        5. Price targets (short/medium term)
        6. Key levels (support/resistance)
        7. Pattern formations
        8. Volume analysis
        9. Trend strength assessment
        10. Warning signals or concerns
        """

        try:
            response = await self.llm_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert technical analyst."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                response_format={ "type": "json_object" }
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            print(f"LLM Analysis error: {str(e)}")
            return None 