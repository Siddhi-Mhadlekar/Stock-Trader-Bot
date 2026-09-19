# Stock Trader Bot

A full-stack stock market analysis and trading platform built with **FastAPI, Python, PostgreSQL, Zerodha Kite Connect, technical analysis, and OpenAI-powered market analysis**.

The system collects market data through Zerodha Kite, stores historical and real-time market information in PostgreSQL, calculates technical indicators, generates structured AI-assisted stock analysis, and provides trading/order-management capabilities through a REST API.

> **Note:** This project is intended for research, analysis, and development purposes. Trading decisions should not be made solely on AI-generated analysis.

---

## 🚀 Features

### 📈 Real-Time Market Data

* Connects to **Zerodha Kite Connect**
* Receives real-time market data through WebSockets
* Processes binary market-data packets
* Stores quote information in PostgreSQL
* Supports instrument-level subscriptions
* Includes WebSocket reconnection handling

The application processes fields including:

* Last traded price
* Last traded quantity
* Average price
* Volume
* Buy quantity
* Sell quantity
* Open / High / Low / Close
* Open interest
* Exchange timestamps

---

### 📊 Technical Analysis

The platform calculates technical indicators from historical candle data.

Currently implemented indicators include:

* SMA 5
* SMA 20
* SMA 50
* RSI 14
* MACD
* MACD Signal
* MACD Histogram
* Bollinger Bands
* Volume-related metrics

Technical indicators are calculated using **Pandas and NumPy** and stored for later analysis.

---

### 🤖 AI-Powered Stock Analysis

The project integrates **OpenAI** to generate structured analysis from technical-market signals.

The AI analysis considers:

* Current price
* Price vs SMA 20
* Price vs SMA 50
* SMA relationships
* RSI
* Overbought / oversold conditions
* MACD
* MACD crossovers
* Bollinger Bands
* Volume ratio
* Money Flow Index

The generated analysis is structured into:

```text
Trading Action
Confidence Level
Key Reason
Risk Level
Stop Loss
Target Price
```

The application stores the complete raw analysis in the database for historical reference.

---

### 💹 Order Management

The backend includes an order-management service integrated with Kite Connect.

It provides functionality for:

* Account balance and margin retrieval
* Stock quote retrieval
* Order validation
* Available-balance checks
* Market-hour validation
* Trading-day validation
* Exchange/segment validation
* Holdings retrieval
* Order persistence

The system also validates Indian market timings and market holidays before processing trading operations.

> **Current implementation:** order creation is currently simulated in the provided code rather than directly submitting the order through Kite's `place_order()` API.

---

### 📅 Market Holiday Management

The application includes a market-holiday service that retrieves NSE holiday information and stores it in PostgreSQL.

This allows the order service to determine whether the market is closed because of:

* Weekends
* Exchange holidays

---

## 🏗️ System Architecture

```text
                     ┌─────────────────────┐
                     │   Trading Dashboard │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │      FastAPI        │
                     │    REST Backend     │
                     └──────────┬──────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
              ▼                 ▼                 ▼
       ┌─────────────┐   ┌──────────────┐  ┌──────────────┐
       │ Kite Connect│   │ PostgreSQL   │  │   OpenAI     │
       │ Market Data │   │   Database   │  │     LLM      │
       └──────┬──────┘   └──────▲───────┘  └──────▲───────┘
              │                 │                 │
              ▼                 │                 │
       ┌─────────────┐          │          ┌──────┴───────┐
       │  WebSocket  │          │          │ AI Analysis  │
       │   Streaming │          │          │    Service   │
       └──────┬──────┘          │          └──────────────┘
              │                 │
              ▼                 │
       ┌─────────────┐          │
       │ Quote / Tick│──────────┘
       │    Data     │
       └─────────────┘
                               
                     ┌─────────────────────┐
                     │ Technical Analysis  │
                     │ SMA │ RSI │ MACD    │
                     │ Bollinger │ Volume  │
                     └──────────┬──────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Stock Analysis  │
                       └─────────────────┘
```

---

## 🔄 Data Flow

### 1. Market Data Ingestion

The application connects to Zerodha Kite's WebSocket service and subscribes to configured instruments.

```text
Kite WebSocket
      ↓
Binary Market Data
      ↓
Packet Processing
      ↓
Quote Data
      ↓
PostgreSQL
```

---

### 2. Technical Analysis

Historical candle data is retrieved from PostgreSQL and converted into Pandas DataFrames.

```text
Historical Candle Data
        ↓
     Pandas
        ↓
Technical Calculations
        ↓
SMA / RSI / MACD / Bollinger Bands
        ↓
PostgreSQL
```

---

### 3. AI Analysis

The latest technical indicators are passed to the OpenAI analysis service.

```text
Technical Indicators
        ↓
     Prompt
        ↓
      OpenAI
        ↓
 Structured JSON
        ↓
Stock Analysis Record
```

---

### 4. Trading Workflow

```text
Stock Selection
      ↓
Current Quote
      ↓
Balance Validation
      ↓
Market Hours Check
      ↓
Trading Day Check
      ↓
Order Validation
      ↓
Order Record
```

---

## 🗄️ Database Design

The application uses **PostgreSQL with SQLAlchemy ORM**.

### Main Tables

| Table                  | Purpose                          |
| ---------------------- | -------------------------------- |
| `stocks`               | Stock and instrument information |
| `quote_data`           | Real-time market quotes          |
| `tick_data`            | Tick-level market information    |
| `candle_data`          | Historical OHLCV data            |
| `technical_indicators` | Calculated technical indicators  |
| `stock_analysis`       | AI-generated stock analysis      |
| `market_holidays`      | Exchange holiday information     |
| `orders`               | Order records                    |

The candle table also uses a composite index across instrument, interval, and timestamp to support market-data queries efficiently.

---

## 📁 Project Structure

```text
stock-trader-bot/
│
├── app/
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── main.py
│   │
│   ├── services/
│   │   ├── analysis_service.py
│   │   ├── holiday_service.py
│   │   ├── order_service.py
│   │   ├── technical_analysis.py
│   │   └── llm_analysis.py
│   │
│   └── websocket_manager.py
│
├── create_tables.py
├── .env
├── requirements.txt
└── README.md
```

> Adjust the exact directory structure above to match the final repository layout before publishing.

---

## 🛠️ Technology Stack

### Backend

* Python
* FastAPI
* Pydantic
* SQLAlchemy

### Market Data

* Zerodha Kite Connect
* Kite WebSocket API
* WebSockets

### Data Processing

* Pandas
* NumPy

### Database

* PostgreSQL
* SQLAlchemy ORM

### AI

* OpenAI API

### Other

* Requests
* BeautifulSoup
* PyTZ
* Python-dotenv
* AsyncIO

---

## ⚙️ Configuration

The application uses environment variables for sensitive configuration.

Create a `.env` file:

```env
KITE_API_KEY=your_kite_api_key
KITE_SECRET_KEY=your_kite_secret_key

REQUEST_TOKEN=your_request_token
KITE_ACCESS_TOKEN=your_access_token

POSTGRES_USER=your_postgres_user
POSTGRES_PASSWORD=your_postgres_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=stock_trader

OPENAI_API_KEY=your_openai_api_key
```

**Never commit the `.env` file to GitHub.**

Add it to `.gitignore`:

```gitignore
.env
__pycache__/
*.pyc
.venv/
venv/
```

---

## 🗃️ Database Setup

Create the PostgreSQL database and configure the database credentials in `.env`.

Then initialize the application tables:

```bash
python create_tables.py
```

The SQLAlchemy models create the required database tables.

---

## ▶️ Running the Application

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the FastAPI application:

```bash
uvicorn app.main:app --reload
```

The API will be available locally at:

```text
http://localhost:8000
```

FastAPI documentation:

```text
http://localhost:8000/docs
```

---

## 🔌 API Capabilities

The backend exposes APIs for functionality such as:

### Health Check

```http
GET /
```

Returns the application status.

### Start Market Streaming

```http
GET /start-streaming
```

Starts the market-data streaming process using the Kite authentication flow.

### Historical Candle Data

```http
GET /candles
```

Supports retrieving candle information using interval and date parameters.

Additional endpoints are available for analysis, stocks, orders, holdings, market information, and related operations.

---

## 🧠 Technical Analysis Logic

The technical-analysis service retrieves historical candle data and calculates indicators using rolling-window and exponential-moving-average calculations.

For example:

### SMA

```text
SMA = Rolling Mean of Closing Prices
```

### RSI

The implementation calculates RSI using rolling average gains and losses over a 14-period window.

### MACD

```text
MACD = EMA(12) - EMA(26)
```

The signal line is calculated using a 9-period EMA of MACD.

### Bollinger Bands

```text
Middle Band = 20-period SMA

Upper Band = Middle Band + 2 × Standard Deviation

Lower Band = Middle Band - 2 × Standard Deviation
```

---

## 🤖 AI Analysis Architecture

The AI layer converts numerical technical indicators into structured market analysis.

Example conceptual flow:

```text
                Technical Indicators
                         │
        ┌────────────────┼────────────────┐
        │                │                │
       Trend          Momentum        Volatility
        │                │                │
       SMA             RSI             Bollinger
       EMA             MACD            Bands
        │                │                │
        └────────────────┼────────────────┘
                         ↓
                    AI Prompt
                         ↓
                    OpenAI API
                         ↓
                 Structured JSON
                         ↓
                PostgreSQL Storage
```

The analysis service also categorizes results into groups such as:

* High-confidence BUY signals
* Moderate BUY signals
* HOLD signals
* SELL signals

These categories are derived from the returned trading action and confidence level.

---

## 🔐 Security Considerations

Sensitive credentials should be supplied through environment variables rather than source code.

The project requires credentials for:

* Kite API
* Kite secret
* Kite access token
* PostgreSQL
* OpenAI API

Before publishing the repository:

* Remove `.env`
* Remove API keys
* Remove access tokens
* Remove database passwords
* Review Git history for accidentally committed secrets
* Add `.env` to `.gitignore`

---

## 📌 Current Project Status

### Implemented

* [x] FastAPI backend
* [x] PostgreSQL integration
* [x] SQLAlchemy data models
* [x] Zerodha Kite integration
* [x] WebSocket market-data ingestion
* [x] Historical candle storage
* [x] Technical indicator calculation
* [x] OpenAI-based stock analysis
* [x] Market holiday management
* [x] Trading-hour validation
* [x] Balance validation
* [x] Order persistence
* [x] Historical AI analysis storage

### In Progress / Potential Improvements

* [ ] Complete production-grade order execution through Kite
* [ ] Improved authentication and authorization
* [ ] Background task / worker architecture
* [ ] Automated indicator scheduling
* [ ] Better error and retry handling
* [ ] Unit and integration test coverage
* [ ] Production deployment
* [ ] Containerization
* [ ] Monitoring and observability

---

## 🎯 Project Highlights

This project demonstrates practical experience with:

* **Real-time data ingestion**
* **WebSocket-based streaming**
* **REST API development**
* **Financial market data processing**
* **Time-series data modeling**
* **Technical indicator computation**
* **LLM integration**
* **Structured AI outputs**
* **PostgreSQL data persistence**
* **Async Python programming**
* **API integration**
* **Order validation and business rules**

---

## ⚠️ Disclaimer

This project is intended for educational, research, and software-development purposes.

Technical indicators and AI-generated analysis are not guaranteed to predict market movements. The project should not be considered financial advice or a guarantee of investment returns.

---

## 👨‍💻 Author

**Siddhi Mhadlekar**

Data Engineer | Python | SQL | Data Engineering | Distributed Systems

---

## ⭐ If You Find This Project Useful

Feel free to explore the implementation, raise issues, or suggest improvements.
