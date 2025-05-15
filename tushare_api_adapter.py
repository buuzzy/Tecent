import os
import sys
import traceback
from pathlib import Path
from typing import Optional, Any, List, Dict
from contextlib import asynccontextmanager

import pandas as pd
import tushare as ts
from fastapi import FastAPI, HTTPException, Query, Body
from dotenv import load_dotenv

# --- Configuration & Initialization (Adapted from server.py) ---

# Attempt to use the same .env file location logic as server.py
ENV_FILE_DIR_NAME = ".tushare_mcp"
ENV_FILE_NAME = ".env"
try:
    APP_DATA_DIR = Path.home() / ENV_FILE_DIR_NAME
except RuntimeError:  # pragma: no cover
    print(f"Warning: Could not determine home directory. Using current directory for .env file: {Path.cwd() / ENV_FILE_DIR_NAME}", file=sys.stderr, flush=True)
    APP_DATA_DIR = Path.cwd() / ENV_FILE_DIR_NAME
ENV_FILE = APP_DATA_DIR / ENV_FILE_NAME

PRO_API_ADAPTER_INSTANCE: Optional[Any] = None

def get_tushare_token_for_adapter() -> Optional[str]:
    """Loads .env and gets TUSHARE_TOKEN specifically for this adapter."""
    if ENV_FILE.exists():
        print(f"DEBUG: tushare_api_adapter.py: Loading .env file from: {ENV_FILE}", file=sys.stderr, flush=True)
        load_dotenv(ENV_FILE, override=True)
    else:
        print(f"DEBUG: tushare_api_adapter.py: .env file not found at {ENV_FILE}. Relying on environment variables.", file=sys.stderr, flush=True)
    
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        print("ERROR: tushare_api_adapter.py: TUSHARE_TOKEN not found in environment or .env file.", file=sys.stderr, flush=True)
    return token

def initialize_pro_api() -> Any:
    """Initializes and returns a Tushare Pro API instance for the adapter."""
    global PRO_API_ADAPTER_INSTANCE
    if PRO_API_ADAPTER_INSTANCE is not None:
        return PRO_API_ADAPTER_INSTANCE

    token = get_tushare_token_for_adapter()
    if not token:
        print("CRITICAL: tushare_api_adapter.py: Cannot initialize Tushare Pro API - token not available.", file=sys.stderr, flush=True)
        raise HTTPException(status_code=503, detail="Tushare token not configured. Cannot initialize Tushare Pro API.")
    
    try:
        print("DEBUG: tushare_api_adapter.py: Initializing Tushare Pro API...", file=sys.stderr, flush=True)
        pro_instance = ts.pro_api(token)
        # Perform a simple test call to ensure connectivity and token validity
        pro_instance.trade_cal(exchange='SSE', limit=1)
        PRO_API_ADAPTER_INSTANCE = pro_instance
        print("INFO: tushare_api_adapter.py: Tushare Pro API initialized and tested successfully.", file=sys.stderr, flush=True)
        return PRO_API_ADAPTER_INSTANCE
    except Exception as e:
        print(f"CRITICAL: tushare_api_adapter.py: Failed to initialize Tushare Pro API: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        PRO_API_ADAPTER_INSTANCE = None # Ensure it's None on failure
        raise HTTPException(status_code=503, detail=f"Tushare Pro API initialization failed: {str(e)}")

# --- Import Helper Functions from server.py ---
# Ensure server.py is in the Python path (e.g., same directory or installed package)
try:
    from server import _get_stock_name as imported_get_stock_name
    from server import _fetch_latest_report_data as imported_fetch_latest_report_data
    print("INFO: tushare_api_adapter.py: Successfully imported helper functions from server.py.", file=sys.stderr, flush=True)
except ImportError as e:
    print(f"CRITICAL: tushare_api_adapter.py: Could not import helper functions (_get_stock_name, _fetch_latest_report_data) from server.py: {e}. API endpoints requiring them will fail or use fallbacks.", file=sys.stderr, flush=True)
    # Define fallbacks or raise errors if critical helpers are missing
    def imported_get_stock_name(pro_api_instance, ts_code: str) -> str:
        print(f"WARNING: Using fallback imported_get_stock_name for {ts_code}", file=sys.stderr)
        return ts_code # Basic fallback

    def imported_fetch_latest_report_data(*args, **kwargs):
        print("ERROR: imported_fetch_latest_report_data is not available due to import error.", file=sys.stderr)
        raise NotImplementedError("Core helper function _fetch_latest_report_data could not be imported.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    print("INFO: tushare_api_adapter.py: Lifespan startup: Initializing Tushare Pro API...", file=sys.stderr)
    try:
        initialize_pro_api()
        print("INFO: tushare_api_adapter.py: Lifespan startup: Tushare Pro API initialization successful.", file=sys.stderr)
    except HTTPException as http_exc:
        print(f"ERROR during lifespan startup (HTTPException): {http_exc.detail}", file=sys.stderr)
        # Depending on severity, you might want to prevent app from fully starting
        # or allow it to start and let individual requests fail.
        # For now, just logging. FastAPI will likely still start.
    except Exception as e:
        print(f"CRITICAL ERROR during lifespan startup: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # This is a more severe error; consider if the app should proceed.
    yield
    # Code to run on shutdown (if any)
    print("INFO: tushare_api_adapter.py: Lifespan shutdown sequence initiated.", file=sys.stderr)
    # Example: PRO_API_ADAPTER_INSTANCE = None # Or any other cleanup

app_adapter = FastAPI(
    title="Tushare Tools HTTP API Adapter",
    version="1.0.0",
    description="Provides HTTP JSON APIs for Tushare financial data tools.",
    lifespan=lifespan # Assign the lifespan manager
)

def handle_df_output(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Converts DataFrame to list of dicts, handling NaN/NaT."""
    if df.empty:
        return []
    # Replace Pandas NaT/NaN with None for JSON compatibility
    return df.fillna(pd.NA).replace({pd.NA: None}).to_dict(orient='records')

# --- API Endpoints ---

@app_adapter.get("/stock/basic_info", summary="Get Stock Basic Information")
async def get_stock_basic_info_api(
    ts_code: Optional[str] = Query(None, description="股票代码 (例如: 000001.SZ)"),
    name: Optional[str] = Query(None, description="股票名称 (例如: 平安银行)")
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    if not (ts_code or name):
        raise HTTPException(status_code=400, detail="Either 'ts_code' or 'name' query parameter must be provided.")
    try:
        filters = {}
        if ts_code:
            filters['ts_code'] = ts_code
        if name:
            filters['name'] = name
        
        # Specify fields to match the typical output of the original tool
        fields = 'ts_code,name,area,industry,fullname,enname,market,exchange,curr_type,list_status,list_date,delist_date,is_hs'
        df = pro.stock_basic(**filters, fields=fields)
        return handle_df_output(df)
    except Exception as e:
        print(f"ERROR in get_stock_basic_info_api: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch stock basic info: {str(e)}")

@app_adapter.get("/financial/indicator", summary="Get Financial Indicators")
async def get_financial_indicator_api(
    ts_code: str = Query(..., description="股票代码 (例如: 600348.SH)"),
    period: Optional[str] = Query(None, description="报告期 (YYYYMMDD格式, 例如: 20231231)"),
    ann_date: Optional[str] = Query(None, description="公告日期 (YYYYMMDD格式)"),
    start_date: Optional[str] = Query(None, description="公告开始日期 (YYYYMMDD格式)"),
    end_date: Optional[str] = Query(None, description="公告结束日期 (YYYYMMDD格式)"),
    limit: int = Query(10, description="返回记录的条数上限", ge=1, le=100) # Added sensible limits
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    if not (period or ann_date or (start_date and end_date)):
        raise HTTPException(status_code=400, detail="Must provide 'period', 'ann_date', or both 'start_date' and 'end_date'.")
    if (start_date and not end_date) or (not start_date and end_date):
        raise HTTPException(status_code=400, detail="'start_date' and 'end_date' must be provided together.")

    try:
        api_params = {'ts_code': ts_code}
        if period:
            api_params['period'] = period
        if ann_date:
            api_params['ann_date'] = ann_date
        if start_date and end_date:
            api_params['start_date'] = start_date
            api_params['end_date'] = end_date
        
        # Fields from original tool
        req_fields = (
            'ts_code,ann_date,end_date,eps,dt_eps,grossprofit_margin,netprofit_margin,'
            'roe_yearly,roe_waa,roe_dt,n_income_attr_p,total_revenue,rd_exp,debt_to_assets,'
            'n_income_attr_p_yoy,dtprofit_yoy,tr_yoy,or_yoy,bps,ocfps,update_flag'
        )
        api_params['fields'] = req_fields
        
        df = pro.fina_indicator(**api_params)
        if df.empty:
            return []
        
        df_sorted = df.sort_values(by=['end_date', 'ann_date'], ascending=[False, False])
        df_limited = df_sorted.head(limit)
        return handle_df_output(df_limited)

    except Exception as e:
        print(f"ERROR in get_financial_indicator_api: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch financial indicators: {str(e)}")


@app_adapter.get("/financial/income_statement", summary="Get Income Statement Data")
async def get_income_statement_api(
    ts_code: str = Query(..., description="股票代码 (例如: 000001.SZ)"),
    period: str = Query(..., description="报告期 (YYYYMMDD格式, 例如: 20231231)"),
    report_type: str = Query("1", description="报告类型 (默认为1，合并报表)")
) -> Dict[str, Any]:
    pro = initialize_pro_api()
    try:
        # Fetch current period data
        current_fields = (
            'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,basic_eps,diluted_eps,'
            'total_revenue,revenue,int_income,prem_earned,comm_income,oth_biz_income,'
            'total_cogs,oper_cost,int_exp,comm_exp,biz_tax_surchg,sell_exp,admin_exp,fin_exp,assets_impair_loss,'
            'oper_profit,non_oper_revenue,non_oper_exp,n_income,n_income_attr_p,minority_gain,ebit,ebitda'
        )
        df_current = pro.income(ts_code=ts_code, period=period, report_type=report_type, fields=current_fields)
        
        if df_current.empty:
            raise HTTPException(status_code=404, detail=f"No income statement data found for {ts_code} for period {period}.")
        
        current_data_dict = handle_df_output(df_current.head(1))[0] # Should be one record for specific period

        # Fetch previous year's same period data for YOY calculation (n_income_attr_p)
        year = int(period[:4])
        month_day = period[4:]
        last_year_period = f"{year - 1}{month_day}"
        
        previous_profit = None
        previous_ann_date = None
        previous_end_date = None

        # Use the imported _fetch_latest_report_data for robustly getting last year's comparable report
        # Prepare params for _fetch_latest_report_data carefully
        params_previous = {
            'ts_code': ts_code, 
            'period': last_year_period, # This param name might be 'period' or 'end_date' depending on how pro.income is wrapped
                                        # in _fetch_latest_report_data. Assuming 'period' is what pro.income takes.
            'report_type': report_type, 
            'fields': 'n_income_attr_p,end_date,ann_date' # Fields for previous period
        }
        # _fetch_latest_report_data expects the API function itself (pro.income)
        # and the name of the field in the *result* that corresponds to the queried period.
        # For pro.income, 'end_date' in the result corresponds to the 'period' we query by.
        df_previous_latest = imported_fetch_latest_report_data(
            api_func=pro.income, # Pass the actual Tushare API function
            result_period_field_name='end_date', # The field in pro.income's output that represents the report period
            result_period_value=last_year_period, # The target report period value
            **params_previous # Other necessary params for pro.income
        )

        if df_previous_latest is not None and not df_previous_latest.empty:
            prev_data_row = df_previous_latest.iloc[0]
            previous_profit = pd.to_numeric(prev_data_row.get('n_income_attr_p'), errors='coerce')
            previous_ann_date = prev_data_row.get('ann_date')
            previous_end_date = prev_data_row.get('end_date')

        # Calculate YOY for net income attributable to parent
        current_profit_attr_p = pd.to_numeric(current_data_dict.get('n_income_attr_p'), errors='coerce')
        n_income_attr_p_yoy = None
        if pd.notna(current_profit_attr_p) and pd.notna(previous_profit) and previous_profit != 0:
            n_income_attr_p_yoy = ((current_profit_attr_p - previous_profit) / abs(previous_profit)) * 100
        
        return {
            "current_period_data": current_data_dict,
            "previous_period_comparable": {
                "period": last_year_period,
                "ann_date": previous_ann_date,
                "end_date": previous_end_date,
                "n_income_attr_p": previous_profit
            },
            "calculated_metrics": {
                "n_income_attr_p_yoy_pct": n_income_attr_p_yoy
            }
        }

    except HTTPException: # Re-raise known HTTP exceptions
        raise
    except Exception as e:
        print(f"ERROR in get_income_statement_api: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch income statement: {str(e)}")


@app_adapter.get("/market/top_list_detail", summary="Get Dragon List (Longhubang) Daily Details")
async def get_top_list_detail_api(
    trade_date: str = Query(..., description="交易日期 (YYYYMMDD格式)"),
    ts_code: Optional[str] = Query(None, description="股票代码 (可选, 例如: 000001.SZ)")
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    try:
        params = {'trade_date': trade_date}
        if ts_code:
            params['ts_code'] = ts_code
        
        # Fields from original tool, adjusted for direct Tushare call if necessary
        fields = 'trade_date,ts_code,name,close,pct_chg,turnover_rate,amount,l_sell,l_buy,l_amount,buy_sm_amount,sell_sm_amount,net_amount,exlist_reason'
        df = pro.top_list(**params, fields=fields) # Tushare's top_list
        
        # Post-processing: get stock names if 'name' column is missing or incomplete for some ts_codes
        # (Tushare's top_list usually provides 'name', but as a fallback)
        if not df.empty and 'name' in df.columns:
            # Ensure names are fetched for any missing ones, though top_list usually has them
            # This is more of a general good practice if an API might return ts_code without name.
            # For top_list, it might not be strictly necessary if Tushare always populates 'name'.
            # df['name'] = df.apply(lambda row: imported_get_stock_name(pro, row['ts_code']) if pd.isna(row['name']) or row['name'] == '' else row['name'], axis=1)
            pass # Assuming pro.top_list provides the name

        return handle_df_output(df)
        
    except Exception as e:
        print(f"ERROR in get_top_list_detail_api: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch top list details: {str(e)}")

@app_adapter.get("/index/search", summary="Search for Index Basic Information")
async def search_index_api(
    index_name: str = Query(..., description="指数简称或包含在全称中的关键词 (例如: \\\"沪深300\\\", \\\"A50\\\")"),
    market: Optional[str] = Query(None, description="交易所或服务商代码 (可选, 例如: CSI, SSE, SZSE, MSCI, OTH)"),
    publisher: Optional[str] = Query(None, description="发布商 (可选, 例如: \\\"中证公司\\\", \\\"申万\\\", \\\"MSCI\\\")"),
    category: Optional[str] = Query(None, description="指数类别 (可选, 例如: \\\"规模指数\\\", \\\"行业指数\\\")"),
    limit: int = Query(20, description="返回记录的条数上限", ge=1, le=100)
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    try:
        query_params = {
            'name': index_name,
            'fields': 'ts_code,name,fullname,market,publisher,category,list_date,base_date,base_point,index_type' # Added index_type
        }
        if market:
            query_params['market'] = market
        if publisher:
            query_params['publisher'] = publisher
        if category:
            query_params['category'] = category
        
        df = pro.index_basic(**query_params)
        if df.empty:
            return []
        
        df_sorted = df.sort_values(by=['market', 'list_date', 'ts_code'], ascending=[True, False, True]).head(limit)
        return handle_df_output(df_sorted)
        
    except Exception as e:
        print(f"ERROR in search_index_api for '{index_name}': {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to search index '{index_name}': {str(e)}")

@app_adapter.get("/index/list", summary="Get List of Index Basic Information")
async def get_index_list_api(
    ts_code: Optional[str] = Query(None, description="指数代码 (可选, 例如: 000300.SH)"),
    name: Optional[str] = Query(None, description="指数简称或包含在全称中的关键词 (可选, 例如: \\\"沪深300\\\", \\\"A50\\\")"),
    market: Optional[str] = Query(None, description="交易所或服务商代码 (可选, 例如: CSI, SSE, SZSE, MSCI, OTH)"),
    publisher: Optional[str] = Query(None, description="发布商 (可选, 例如: \\\"中证公司\\\", \\\"申万\\\", \\\"MSCI\\\")"),
    category: Optional[str] = Query(None, description="指数类别 (可选, 例如: \\\"规模指数\\\", \\\"行业指数\\\")"),
    limit: int = Query(30, description="返回记录的条数上限", ge=1, le=200)
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    if not any([ts_code, name, market, publisher, category]):
        raise HTTPException(status_code=400, detail="At least one query parameter (ts_code, name, market, publisher, or category) must be provided.")
    
    try:
        query_params = {}
        if ts_code: query_params['ts_code'] = ts_code
        if name: query_params['name'] = name
        if market: query_params['market'] = market
        if publisher: query_params['publisher'] = publisher
        if category: query_params['category'] = category
        
        query_params['fields'] = 'ts_code,name,fullname,market,publisher,category,list_date,base_date,base_point,index_type,weight_rule,desc,exp_date'
        
        df = pro.index_basic(**query_params)
        if df.empty:
            return []

        df_sorted = df.sort_values(by=['market', 'list_date', 'ts_code'], ascending=[True, False, True]).head(limit)
        return handle_df_output(df_sorted)

    except Exception as e:
        error_msg_detail = f"ts_code={ts_code}, name={name}, market={market}, publisher={publisher}, category={category}"
        print(f"DEBUG: ERROR in get_index_list_api for {error_msg_detail}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to get index list: {str(e)}")

@app_adapter.get("/stock/search", summary="Search for Stocks by Keyword")
async def search_stocks_api(
    keyword: str = Query(..., description="关键词（可以是股票代码的一部分或股票名称的一部分）"),
    limit: int = Query(50, description="返回记录的条数上限", ge=1, le=200)
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    try:
        # stock_basic can return many fields, let's select a few relevant ones
        df_all = pro.stock_basic(fields='ts_code,symbol,name,area,industry,market,list_date')
        mask = (
            df_all['ts_code'].str.contains(keyword, case=False, na=False) | \
            df_all['name'].str.contains(keyword, case=False, na=False) | \
            df_all['symbol'].str.contains(keyword, case=False, na=False)
        ) # Also search by symbol
        
        results_df = df_all[mask].head(limit)
        return handle_df_output(results_df)
    except Exception as e:
        print(f"ERROR in search_stocks_api for keyword '{keyword}': {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to search stocks: {str(e)}")

@app_adapter.get("/market/daily_metrics", summary="Get Daily Market Metrics for a Stock")
async def get_daily_metrics_api(
    ts_code: str = Query(..., description="股票代码 (例如: 300170.SZ)"),
    trade_date: str = Query(..., description="交易日期 (YYYYMMDD格式, 例如: 20240421)")
) -> Optional[Dict[str, Any]]: # Returns a single day's metrics, so one dict or null
    pro = initialize_pro_api()
    try:
        # Fields from original tool + a few more potentially useful ones like free_share
        fields = ('ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,'
                  'pb,ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv')
        df = pro.daily_basic(ts_code=ts_code, trade_date=trade_date, fields=fields)
        
        if df.empty:
            # Return 404 if no data for that specific stock and date
            raise HTTPException(status_code=404, detail=f"No daily metrics found for {ts_code} on {trade_date}.")
            
        # Should be a single row
        result_list = handle_df_output(df)
        return result_list[0] if result_list else None # Should not be None if not empty, but good practice
        
    except HTTPException: # Re-raise
        raise
    except Exception as e:
        print(f"ERROR in get_daily_metrics_api for {ts_code} on {trade_date}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch daily metrics: {str(e)}")

@app_adapter.get("/market/daily_prices", summary="Get Daily Open, High, Low, Close Prices for a Stock")
async def get_daily_prices_api(
    ts_code: str = Query(..., description="股票代码 (例如: 600126.SH)"),
    trade_date: str = Query(..., description="交易日期 (YYYYMMDD格式, 例如: 20250227)")
) -> Optional[Dict[str, Any]]: # Single day's prices
    pro = initialize_pro_api()
    try:
        fields = 'ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
        df = pro.daily(ts_code=ts_code, trade_date=trade_date, fields=fields)
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No daily price data found for {ts_code} on {trade_date}.")
        
        result_list = handle_df_output(df)
        return result_list[0] if result_list else None

    except HTTPException: # Re-raise
        raise
    except Exception as e:
        print(f"ERROR in get_daily_prices_api for {ts_code} on {trade_date}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch daily prices: {str(e)}")

@app_adapter.get("/stock/shareholder_count", summary="Get Shareholder Count for a Stock")
async def get_shareholder_count_api(
    ts_code: str = Query(..., description="股票代码 (例如: 000665.SZ)"),
    end_date: str = Query(..., description="截止日期 (YYYYMMDD, 例如: 20240930)") 
    # In the original server.py, end_date was optional and defaulted to latest.
    # For a direct API, making it mandatory for a specific period is often clearer.
    # If latest is desired, the client can determine current date or leave it to Tushare if API supports empty end_date for latest.
    # Tushare's stk_holdernumber typically requires enddate.
) -> Optional[Dict[str, Any]]:
    pro = initialize_pro_api()
    try:
        # The original tool used _fetch_latest_report_data. We can mimic its core goal:
        # get the data for the *specific* end_date, but ensure it's the latest announcement *for that end_date*.
        # Tushare's stk_holdernumber API might return multiple announcements for the same end_date if corrections were made.
        params = {
            'ts_code': ts_code, 
            'enddate': end_date, 
            'fields': 'ts_code,ann_date,enddate,holder_num'
        }
        df_holder = pro.stk_holdernumber(**params)

        if df_holder.empty:
            raise HTTPException(status_code=404, detail=f"No shareholder count data found for {ts_code} on {end_date}.")

        # Sort by ann_date (desc) to get the latest announcement for the given end_date
        df_holder_sorted = df_holder.sort_values(by='ann_date', ascending=False)
        latest_data_for_period = df_holder_sorted.head(1)
        
        result_list = handle_df_output(latest_data_for_period)
        return result_list[0] if result_list else None

    except HTTPException: # Re-raise
        raise
    except Exception as e:
        print(f"ERROR in get_shareholder_count_api for {ts_code} on {end_date}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch shareholder count: {str(e)}")

@app_adapter.get("/stock/daily_basic_info", summary="Get Daily Basic Information for a Stock")
async def get_daily_basic_info_api(
    ts_code: str = Query(..., description="股票代码 (例如: 000665.SZ)"),
    trade_date: str = Query(..., description="交易日期 (YYYYMMDD, 例如: 20240930)")
) -> Optional[Dict[str, Any]]:
    pro = initialize_pro_api()
    try:
        # Fields from original tool in server.py, plus a few common ones
        fields = ('ts_code,trade_date,close,pe,pb,dv_ratio,total_share,float_share,'
                  'free_share,total_mv,circ_mv,turnover_rate,volume_ratio') 
        df = pro.daily_basic(ts_code=ts_code, trade_date=trade_date, fields=fields)
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No daily basic info found for {ts_code} on {trade_date}.")
        
        result_list = handle_df_output(df)
        return result_list[0] if result_list else None

    except HTTPException: # Re-raise
        raise
    except Exception as e:
        print(f"ERROR in get_daily_basic_info_api for {ts_code} on {trade_date}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch daily basic info: {str(e)}")

@app_adapter.get("/stock/top_holders", summary="Get Top 10 Shareholders Information")
async def get_top_holders_api(
    ts_code: str = Query(..., description="股票代码 (例如: 000665.SZ)"),
    period: str = Query(..., description="报告期 (YYYYMMDD, 例如: 20240930)"),
    holder_type: str = Query('H', description="股东类型 ('H'=前十大股东, 'F'=前十大流通股东)", pattern="^(H|F)$")
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    if not period or len(period) != 8 or not period.isdigit(): # Basic validation
        raise HTTPException(status_code=400, detail="Invalid 'period' format. Expected YYYYMMDD.")

    try:
        api_to_call = pro.top10_holders if holder_type == 'H' else pro.top10_floatholders
        # Common fields for both holder types
        fields = 'ts_code,ann_date,end_date,holder_name,hold_amount,hold_ratio'
        df = api_to_call(ts_code=ts_code, period=period, fields=fields)
        
        if df.empty:
            return [] # Or raise 404 if preferred: HTTPException(status_code=404, detail=f"No top {holder_type} holders data found for {ts_code} for period {period}.")

        return handle_df_output(df.sort_values(by='hold_ratio', ascending=False)) # Sort by holding ratio

    except Exception as e:
        print(f"ERROR in get_top_holders_api for {ts_code}, period {period}, type {holder_type}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch top holders: {str(e)}")

@app_adapter.get("/index/constituents", summary="Get Index Constituents and Weights")
async def get_index_constituents_api(
    index_code: str = Query(..., description="指数代码 (例如: 000300.SH, 399300.SZ)"),
    # Tushare's index_weight is monthly. start_date and end_date define the month.
    trade_date: Optional[str] = Query(None, description="交易日期 (YYYYMMDD)，将用于确定月份。如果提供，将覆盖start/end_date。查询当月数据。"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYYMMDD格式, 例如: 20230901 for Sept data). Required if trade_date is not set."),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYYMMDD格式, 例如: 20230930 for Sept data). Required if trade_date is not set.")
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    
    query_params = {'index_code': index_code, 'fields': 'index_code,con_code,trade_date,weight'}

    if trade_date:
        if not (len(trade_date) == 8 and trade_date.isdigit()):
            raise HTTPException(status_code=400, detail="Invalid 'trade_date' format. Expected YYYYMMDD.")
        # Tushare index_weight uses start_date and end_date for the month.
        # If only trade_date is given, we might infer the month, but Tushare API expects start/end for month range.
        # For simplicity, if trade_date is given, let's use it as both start and end for that specific date's available data (if API allows)
        # OR, more correctly, determine the month from trade_date and set start/end to month boundaries.
        # The original server.py implies start_date and end_date should be month boundaries.
        # Let's make trade_date take precedence to query for a specific day's constituent list if Tushare supports it (often it's EOM)
        query_params['trade_date'] = trade_date # Using direct trade_date if pro.index_weight supports it.
                                             # If it strictly requires start/end for month, this needs adjustment.
                                             # The doc implies it is monthly data. Let's assume user wants a specific month if trade_date given.
        # Alternative for monthly based on trade_date:
        # from datetime import datetime
        # import calendar
        # dt_obj = datetime.strptime(trade_date, "%Y%m%d")
        # query_params['start_date'] = dt_obj.strftime("%Y%m01")
        # query_params['end_date'] = dt_obj.strftime("%Y%m") + str(calendar.monthrange(dt_obj.year, dt_obj.month)[1])

    elif start_date and end_date:
        if not (len(start_date) == 8 and start_date.isdigit() and len(end_date) == 8 and end_date.isdigit()):
            raise HTTPException(status_code=400, detail="Invalid 'start_date' or 'end_date' format. Expected YYYYMMDD.")
        query_params['start_date'] = start_date
        query_params['end_date'] = end_date
    else:
        raise HTTPException(status_code=400, detail="Either 'trade_date' or both 'start_date' and 'end_date' must be provided.")

    try:
        df = pro.index_weight(**query_params) 
        # Tushare returns data for each trade_date in the range if available, usually EOM for index_weight.
        # If multiple dates are returned, the client might want the latest or all.
        # For now, return all found within the specified range/date.
        if df.empty:
            return []
        
        # Add stock names
        # Create a unique list of con_codes to minimize calls to stock_basic
        # This can be slow if there are many constituents. Consider if this is always needed or optional.
        # con_codes = df['con_code'].unique()
        # if len(con_codes) > 0:
        #     df_names = pro.stock_basic(ts_code=','.join(con_codes), fields='ts_code,name')
        #     if not df_names.empty:
        #         df = pd.merge(df, df_names, left_on='con_code', right_on='ts_code', how='left')
        #         df.rename(columns={'name': 'con_name'}, inplace=True)
        #         df.drop(columns=['ts_code_y'], inplace=True, errors='ignore') # Drop extra ts_code from merge
        #         df.rename(columns={'ts_code_x': 'ts_code'}, inplace=True, errors='ignore')

        return handle_df_output(df.sort_values(by=['trade_date', 'weight'], ascending=[False, False]))

    except Exception as e:
        print(f"ERROR in get_index_constituents_api for {index_code}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch index constituents: {str(e)}")

@app_adapter.get("/index/global_quotes", summary="Get Global Index Quotes")
async def get_global_index_quotes_api(
    ts_code: str = Query(..., description="TS指数代码 (例如: XIN9, HSI)"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYYMMDD格式)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYYMMDD格式)"),
    trade_date: Optional[str] = Query(None, description="单个交易日期 (YYYYMMDD格式)")
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    if not trade_date and not (start_date and end_date):
        raise HTTPException(status_code=400, detail="Either 'trade_date' or both 'start_date' and 'end_date' must be provided.")
    if trade_date and (start_date or end_date):
        raise HTTPException(status_code=400, detail="Cannot provide 'trade_date' along with 'start_date'/'end_date'. Use one or the other.")

    try:
        params = {
            'ts_code': ts_code,
            'fields': 'ts_code,trade_date,open,close,high,low,pre_close,change,pct_chg,swing,vol,amount'
        }
        if trade_date:
            params['trade_date'] = trade_date
        elif start_date and end_date:
            params['start_date'] = start_date
            params['end_date'] = end_date
        
        df = pro.index_global(**params)
        if df.empty:
            return []
        
        return handle_df_output(df.sort_values(by='trade_date', ascending=True))

    except Exception as e:
        print(f"ERROR in get_global_index_quotes_api for {ts_code}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch global index quotes: {str(e)}")

@app_adapter.get("/stock/period_price_change", summary="Calculate Stock Price Change Over a Period")
async def get_period_price_change_api(
    ts_code: str = Query(..., description="股票代码 (例如: 000665.SZ)"),
    start_date: str = Query(..., description="区间开始日期 (YYYYMMDD, 例如: 20240701)"),
    end_date: str = Query(..., description="区间结束日期 (YYYYMMDD, 例如: 20240930)")
) -> Dict[str, Any]:
    pro = initialize_pro_api()
    try:
        # Fetch daily data for the given range
        df_daily = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date, fields='trade_date,close')

        if df_daily.empty or len(df_daily) < 1: # Need at least one day to get a price
            raise HTTPException(status_code=404, detail=f"No daily data found for {ts_code} in the range {start_date} to {end_date}.")

        # Data is typically returned in descending order of trade_date
        actual_end_trade_date = df_daily['trade_date'].iloc[0]
        actual_start_trade_date = df_daily['trade_date'].iloc[-1]
        
        end_close = pd.to_numeric(df_daily['close'].iloc[0], errors='coerce')
        start_close = pd.to_numeric(df_daily['close'].iloc[-1], errors='coerce')

        if pd.isna(start_close) or pd.isna(end_close):
            raise HTTPException(status_code=422, detail=f"Could not parse start or end closing price for {ts_code} between {actual_start_trade_date} and {actual_end_trade_date}.")

        price_change_pct = None
        if start_close != 0:
            price_change_pct = ((end_close - start_close) / start_close) * 100
        
        return {
            "ts_code": ts_code,
            "stock_name": imported_get_stock_name(pro, ts_code), # Use imported helper
            "requested_start_date": start_date,
            "requested_end_date": end_date,
            "actual_start_trade_date": actual_start_trade_date,
            "actual_end_trade_date": actual_end_trade_date,
            "start_close_price": start_close,
            "end_close_price": end_close,
            "price_change_percentage": price_change_pct
        }
    except HTTPException: # Re-raise
        raise
    except Exception as e:
        print(f"ERROR in get_period_price_change_api for {ts_code}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to calculate period price change: {str(e)}")

@app_adapter.get("/financial/balance_sheet", summary="Get Balance Sheet Data")
async def get_balance_sheet_api(
    ts_code: str = Query(..., description="股票代码 (例如: 300274.SZ)"),
    period: str = Query(..., description="报告期 (YYYYMMDD格式, 例如: 20231231)"),
    # report_type: Optional[str] = Query(None, description="报告类型 (1合并报表 2单季合并 3调整单季合并表等)"), # Tushare balancesheet has report_type
    # comp_type: Optional[str] = Query(None, description="公司类型 (1一般工商业 2银行 3保险 4券商)") # Tushare balancesheet has comp_type
) -> Optional[Dict[str, Any]]: # Usually one report for a specific period
    pro = initialize_pro_api()
    if not (len(period) == 8 and period.isdigit()):
        raise HTTPException(status_code=400, detail="Invalid 'period' format. Expected YYYYMMDD.")

    try:
        req_fields = (
            'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,total_share,cap_rese,undistr_porfit,'
            'surplus_rese,special_rese,money_cap,trad_asset,notes_receiv,accounts_receiv,oth_receiv,prepayment,'
            'inventories,total_cur_assets,total_assets,accounts_payable,adv_receipts,total_cur_liab,total_liab,'
            'lt_borr,total_hldr_eqy_exc_min_int,r_and_d_costs' # Added r_and_d_costs from original example
        )
        api_params = {'ts_code': ts_code, 'period': period, 'fields': req_fields}
        # if report_type: api_params['report_type'] = report_type
        # if comp_type: api_params['comp_type'] = comp_type

        # Use imported_fetch_latest_report_data to get the latest announcement for the given period
        df_bs = imported_fetch_latest_report_data(
            api_func=pro.balancesheet,
            result_period_field_name='end_date', # Field in result that matches 'period' query
            result_period_value=period,
            **api_params
        )

        if df_bs is None or df_bs.empty:
            raise HTTPException(status_code=404, detail=f"No balance sheet data found for {ts_code} for period {period}.")

        result_list = handle_df_output(df_bs.head(1)) # Should be one row
        return result_list[0] if result_list else None
    except HTTPException: # Re-raise
        raise
    except Exception as e:
        print(f"ERROR in get_balance_sheet_api for {ts_code}, period {period}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch balance sheet: {str(e)}")

@app_adapter.get("/financial/cash_flow", summary="Get Cash Flow Statement Data")
async def get_cash_flow_api(
    ts_code: str = Query(..., description="股票代码 (例如: 300274.SZ)"),
    period: str = Query(..., description="报告期 (YYYYMMDD格式, 例如: 20231231)")
    # report_type, comp_type can be added similarly if needed
) -> Optional[Dict[str, Any]]:
    pro = initialize_pro_api()
    if not (len(period) == 8 and period.isdigit()):
        raise HTTPException(status_code=400, detail="Invalid 'period' format. Expected YYYYMMDD.")
    try:
        req_fields = (
            'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,net_profit,finan_exp,c_fr_sale_sg,'
            'recp_tax_rends,n_depos_incr_fi,n_disp_subs_oth_biz,n_cashflow_act,st_cash_out_act,n_cashflow_inv_act,'
            'st_cash_out_inv_act,n_cashflow_fin_act,st_cash_out_fin_act,free_cashflow'
        )
        api_params = {'ts_code': ts_code, 'period': period, 'fields': req_fields}

        df_cf = imported_fetch_latest_report_data(
            api_func=pro.cashflow,
            result_period_field_name='end_date',
            result_period_value=period,
            **api_params
        )

        if df_cf is None or df_cf.empty:
            raise HTTPException(status_code=404, detail=f"No cash flow data found for {ts_code} for period {period}.")
        
        result_list = handle_df_output(df_cf.head(1))
        return result_list[0] if result_list else None
    except HTTPException: # Re-raise
        raise
    except Exception as e:
        print(f"ERROR in get_cash_flow_api for {ts_code}, period {period}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch cash flow statement: {str(e)}")

@app_adapter.get("/stock/pledge_detail", summary="Get Stock Pledge Statistics")
async def get_pledge_detail_api(
    ts_code: str = Query(..., description="股票代码 (例如: 002277.SZ)"),
    # Tushare pledge_stat does not take date params, it returns latest stats usually
    # The original tool did not take date params either. It returns a list of pledge stats over time.
    # Let's align with Tushare API `pledge_stat` which returns stats per end_date.
    end_date: Optional[str] = Query(None, description="截止日期 (YYYYMMDD, 可选, 某些接口可能按最新返回)") 
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    try:
        api_params = {'ts_code': ts_code, 'fields': 'ts_code,end_date,pledge_count,unrest_pledge,rest_pledge,total_share,pledge_ratio'}
        if end_date:
            if not (len(end_date) == 8 and end_date.isdigit()):
                raise HTTPException(status_code=400, detail="Invalid 'end_date' format. Expected YYYYMMDD.")
            api_params['end_date'] = end_date
            
        df = pro.pledge_stat(**api_params) # Using pledge_stat as in original server.py
        if df.empty:
            return []
        return handle_df_output(df.sort_values(by='end_date', ascending=False))
    except Exception as e:
        print(f"ERROR in get_pledge_detail_api for {ts_code}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch pledge details: {str(e)}")

@app_adapter.get("/financial/main_business_composition", summary="Get Main Business Composition")
async def get_fina_mainbz_api(
    ts_code: str = Query(..., description="股票代码 (例如: 000001.SZ)"),
    period: str = Query(..., description="报告期 (YYYYMMDD格式, 例如: 20231231)"),
    type: str = Query('P', description="构成类型 ('P'按产品, 'D'按地区, 'I'按行业)", pattern="^(P|D|I)$"),
    limit: int = Query(10, description="返回记录的条数上限", ge=1, le=50)
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    if not (len(period) == 8 and period.isdigit()):
        raise HTTPException(status_code=400, detail="Invalid 'period' format. Expected YYYYMMDD.")
    try:
        req_fields = 'ts_code,end_date,bz_item,bz_sales,bz_profit,bz_cost,curr_type,update_flag,bz_item_type' # Added bz_item_type
        df = pro.fina_mainbz(ts_code=ts_code, period=period, type=type, fields=req_fields)
        
        if df.empty:
            return []
        
        # The original tool had logic to calculate total_sales and ratio, which is good for context.
        # We can add this back if this API is meant to be more directly consumable with such derived fields.
        # For now, returning raw data sorted and limited.
        return handle_df_output(df.head(limit)) # Original server.py did not sort this one explicitly

    except Exception as e:
        print(f"ERROR in get_fina_mainbz_api for {ts_code}, period {period}, type {type}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch main business composition: {str(e)}")

@app_adapter.get("/financial/audit_opinion", summary="Get Financial Audit Opinion")
async def get_fina_audit_api(
    ts_code: str = Query(..., description="股票代码 (例如: 000001.SZ)"),
    period: str = Query(..., description="报告期 (YYYYMMDD格式, 例如: 20231231)")
) -> List[Dict[str, Any]]: # Tushare fina_audit can return multiple rows if there are multiple announcements/versions
    pro = initialize_pro_api()
    if not (len(period) == 8 and period.isdigit()):
        raise HTTPException(status_code=400, detail="Invalid 'period' format. Expected YYYYMMDD.")
    try:
        # Original server.py example had 'audit_fees' which is not in standard fina_audit fields.
        # Standard fields: ts_code,ann_date,end_date,audit_result,audit_agency,audit_sign
        req_fields = 'ts_code,ann_date,end_date,audit_result,audit_agency,audit_sign'
        df = pro.fina_audit(ts_code=ts_code, period=period, fields=req_fields)
        if df.empty:
            return []
        return handle_df_output(df.sort_values(by='ann_date', ascending=False))
    except Exception as e:
        print(f"ERROR in get_fina_audit_api for {ts_code}, period {period}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch financial audit opinion: {str(e)}")

@app_adapter.get("/market/top_institution_detail", summary="Get Dragon List (Longhubang) Institutional Details")
async def get_top_institution_detail_api(
    trade_date: str = Query(..., description="交易日期 (YYYYMMDD格式)"),
    ts_code: Optional[str] = Query(None, description="股票代码 (可选, 例如: 000001.SZ)")
) -> List[Dict[str, Any]]:
    pro = initialize_pro_api()
    try:
        params = {'trade_date': trade_date}
        if ts_code:
            params['ts_code'] = ts_code
        
        fields = 'trade_date,ts_code,exalter,buy_turnover,sell_turnover,net_buy_sell,buy_count,sell_count,inst_buy_turnover,inst_sell_turnover,inst_net_buy_sell' # Added more inst_ fields
        df = pro.top_inst(**params, fields=fields) # Tushare's top_inst for institutional details
        
        if not df.empty and 'ts_code' in df.columns: # Add stock names if ts_code is present
            # This adds a name column by looking up each ts_code. Can be slow if many rows.
            # Consider if this is critical for the API or if client can do this lookup.
            # df['name'] = df['ts_code'].apply(lambda x: imported_get_stock_name(pro, x) if pd.notna(x) else None)
            pass # For now, client can lookup name based on ts_code if needed.

        return handle_df_output(df)
        
    except Exception as e:
        print(f"ERROR in get_top_institution_detail_api for {trade_date}, ts_code {ts_code}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to fetch top institutional details: {str(e)}")

# --- Add more adapted endpoints here for other tools from server.py ---
# Example: get_daily_metrics, get_daily_prices, search_index, etc.
# Each would follow a similar pattern:
# 1. Define FastAPI route with Query/Body parameters.
# 2. Call initialize_pro_api().
# 3. Call the relevant pro.some_api_function(**params, fields=...).
# 4. Process DataFrame (sorting, limiting if needed).
# 5. Return handle_df_output(df) or a custom dict.
# 6. Include robust error handling.

if __name__ == "__main__":
    import uvicorn
    print("Starting Tushare API Adapter server on http://localhost:8001", file=sys.stderr)
    # initialize_pro_api() call removed from here, as lifespan handles it.
    uvicorn.run(app_adapter, host="0.0.0.0", port=8001, log_level="info") 