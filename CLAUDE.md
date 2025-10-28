# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tushare_MCP is an intelligent stock data assistant built on the Model Context Protocol (MCP). It provides comprehensive access to Chinese stock market data through Tushare's financial data API, wrapped in a FastAPI service with MCP tool integration.

## Architecture

### Core Components

1. **server.py** - Main application entry point
   - FastAPI app with MCP SSE integration
   - Contains 30+ MCP tools for stock data retrieval
   - Runs on port 8000 using Uvicorn
   - SSE endpoint at `/sse` for MCP protocol communication

2. **demo/hotlist.py** - Market hotlist and trend analysis module
   - Tracks concept sector rankings from multiple platforms (开盘啦/KPL, 同花顺/THS, 东方财富/Eastmoney)
   - Provides daily limit-up/limit-down stock queries
   - Historical hotlist tracking and intersection analysis capabilities

3. **demo/tushare_api_adapter.py** - API adapter utilities (if needed)

### Key Design Patterns

- **Module-level Tushare Pro API initialization**: `PRO_API_INSTANCE` is initialized at module load with token from environment
- **Helper function `_fetch_latest_report_data()`**: Fetches latest financial report data by filtering on announcement date
- **SSE Workaround Pattern**: Custom SSE integration using `SseServerTransport` from `mcp.server.sse` mounted at `/sse` path with manual message routing

### Token Management

Token is stored at `~/.tushare_mcp/.env` with key `TUSHARE_TOKEN`. Functions:
- `get_tushare_token()` - retrieves token from env file
- `set_tushare_token()` - sets token in env file and initializes `ts.set_token()`
- `init_env_file()` - ensures env file exists and is loaded

## Development Commands

### Setup
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# venv/Scripts/activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running

```bash
# Start the FastAPI server (listens on 0.0.0.0:8000)
python server.py

# The MCP SSE endpoint will be available at http://localhost:8000/sse
```

### Docker

```bash
# Build image
docker build -t tushare-mcp .

# Run container (expects TUSHARE_TOKEN env var or Cloud Run's PORT env var)
docker run -p 8080:8080 -e TUSHARE_TOKEN=your_token tushare-mcp
```

## MCP Tools Overview

Tools are registered using `@mcp.tool()` decorator and fall into these categories:

### Token Management
- `setup_tushare_token` - Configure API token
- `check_token_status` - Verify token validity

### Basic Stock Info
- `get_stock_basic_info` - A-share basic info by code/name
- `get_hk_stock_basic` - Hong Kong stock listing info
- `search_stocks` - Keyword search across stocks

### Market Data
- `get_daily_prices` - OHLC prices for single day or date range
- `get_daily_metrics` - Volume, turnover rate, PE/PB ratios
- `get_daily_basic_info` - Share capital and market cap data
- `get_period_price_change` - Price change % between dates

### Financial Reports
- `get_financial_indicator` - Comprehensive financial indicators (supports period, ann_date, or date range queries)
- `get_income_statement` - Income statement with YoY growth calculation
- `get_balance_sheet` - Balance sheet main items
- `get_cash_flow` - Cash flow statement data
- `get_fina_mainbz` - Revenue breakdown by product/region/industry
- `get_fina_audit` - Audit opinion data

### Shareholder Info
- `get_shareholder_count` - Number of shareholders by period
- `get_top_holders` - Top 10 shareholders (type 'H') or float shareholders (type 'F')

### Index Data
- `search_index` - Search index by name/market/publisher
- `get_index_list` - Query index list with filters
- `get_index_constituents` - Get constituent stocks and weights for monthly data
- `get_global_index_quotes` - International index quotes

### Special Data
- `get_pledge_detail` - Share pledge statistics
- `get_top_list_detail` - Dragon-Tiger List daily trading details
- `get_top_institution_detail` - Institutional trading on Dragon-Tiger List

### Calendar & Utility
- `get_trade_calendar` - Exchange trading calendar (filters by `is_open=1` for trading days)
- `get_start_date_for_n_days` - Calculate start date N trading days before end_date

## Important Implementation Details

### Date Format
All dates use `YYYYMMDD` format (e.g., `20240930` for Sept 30, 2024)

### Stock Code Format
- A-shares: `000001.SZ` (Shenzhen), `600000.SH` (Shanghai)
- HK stocks: `00700.HK`
- Indices: `000300.SH` (CSI 300), `399300.SZ` (Shenzhen variant)

### Financial Report Fetching Logic
The `_fetch_latest_report_data()` helper:
1. Filters by period (end_date field)
2. Sorts by announcement date descending
3. Returns latest announced report for that period
4. Supports `is_list_result=True` to return all rows for latest ann_date (used for multi-row results like top holders)

### Data Units
- Financial amounts from Tushare are in **Yuan (元)**, tools convert to **亿元 (hundred million yuan)** by dividing by 100,000,000
- Share amounts are in **万股 (10K shares)** or **万元 (10K yuan)**

### Error Handling Pattern
All tools follow this pattern:
```python
token_value = get_tushare_token()
if not token_value:
    return "错误：Tushare token 未配置或无法获取。请使用 setup_tushare_token 配置。"
try:
    # ... tool logic
except Exception as e:
    print(f"DEBUG: ERROR in tool_name: {str(e)}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    return f"操作失败：{str(e)}"
```

## Testing & Debugging

- All debug output goes to `sys.stderr` with `flush=True`
- Look for `DEBUG:` prefixed messages in stderr for detailed execution traces
- FastAPI automatic docs available at `http://localhost:8000/docs` when server is running

## Dependencies Highlights

- `tushare` - Financial data API client
- `fastapi` + `uvicorn` - Web framework and ASGI server
- `mcp` - Model Context Protocol SDK
- `pandas` - Data manipulation
- `python-dotenv` - Environment variable management
- `sse-starlette` - Server-Sent Events support (for MCP SSE transport)

## Known Limitations

- No support for announcement/research report text data
- No minute-level or tick data
- A-share and index data only; no futures, options, or macroeconomic data
- Some financial APIs require higher Tushare point levels for full data access
