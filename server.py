import sys # Added for stderr output
import functools # Added for checking partial functions
from pathlib import Path
from typing import Optional, Callable, Any
import tushare as ts
from dotenv import load_dotenv, set_key
import pandas as pd
from datetime import datetime, timedelta
import traceback

from mcp.server.fastmcp import FastMCP
import os

from fastapi import FastAPI, HTTPException, Body # Added HTTPException, Body
import uvicorn # New import

# fastapi.staticfiles is not used, so I won't import it here.
# If FastMCP is not directly mountable as an ASGI app, this approach will need adjustment
# based on FastMCP's specific API for integration.

# Added for the workaround:
from starlette.requests import Request
from mcp.server.sse import SseServerTransport

print("DEBUG: debug_server.py starting...", file=sys.stderr, flush=True)

# --- Start of ENV_FILE and Helper Functions ---
ENV_FILE = Path.home() / ".tushare_mcp" / ".env"
print(f"DEBUG: ENV_FILE path resolved to: {ENV_FILE}", file=sys.stderr, flush=True)

def _get_stock_name(pro, ts_code: str) -> str:
    """Internal helper to get stock name, minimizing API calls."""
    try:
        stock_info = pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
        if not stock_info.empty:
            return stock_info.iloc[0]['name']
    except Exception as e:
        print(f"Warning: Failed to get stock name for {ts_code}: {e}", file=sys.stderr, flush=True)
    return ts_code

def _fetch_latest_report_data(
    api_func: Callable[..., pd.DataFrame],
    result_period_field_name: str, 
    result_period_value: str, 
    is_list_result: bool = False, # New parameter to indicate if multiple rows are expected for the latest announcement
    **api_params: Any
) -> Optional[pd.DataFrame]:
    """
    Internal helper to fetch report data.
    If is_list_result is True, it returns all rows matching the latest announcement date.
    Otherwise, it returns only the single latest announced record.
    """
    func_name = "Unknown API function"
    if isinstance(api_func, functools.partial):
        func_name = api_func.func.__name__
    elif hasattr(api_func, '__name__'):
        func_name = api_func.__name__

    print(f"DEBUG: _fetch_latest_report_data called for {func_name}, period: {result_period_value}, is_list: {is_list_result}", file=sys.stderr, flush=True)
    try:
        df = api_func(**api_params)
        if df.empty:
            print(f"DEBUG: _fetch_latest_report_data: API call {func_name} returned empty DataFrame for {api_params.get('ts_code')}", file=sys.stderr, flush=True)
            return None

        # Ensure 'ann_date' and the specified period field exist for sorting/filtering
        if 'ann_date' not in df.columns:
            print(f"Warning: _fetch_latest_report_data: 'ann_date' not in DataFrame columns for {func_name} on {api_params.get('ts_code')}. Returning raw df (or first row if not list).", file=sys.stderr, flush=True)
            return df if is_list_result else df.head(1)
        
        if result_period_field_name not in df.columns:
            print(f"Warning: _fetch_latest_report_data: Period field '{result_period_field_name}' not in DataFrame columns for {func_name} on {api_params.get('ts_code')}. Filtering by ann_date only.", file=sys.stderr, flush=True)
            # Sort by ann_date to get the latest announcement(s)
            df_sorted_by_ann = df.sort_values(by='ann_date', ascending=False)
            if df_sorted_by_ann.empty:
                return None
            latest_ann_date = df_sorted_by_ann['ann_date'].iloc[0]
            df_latest_ann = df_sorted_by_ann[df_sorted_by_ann['ann_date'] == latest_ann_date]
            return df_latest_ann # Return all rows for the latest announcement date

        # Filter by the specific report period first
        # Convert both to string for robust comparison, in case of type mismatches
        df_filtered_period = df[df[result_period_field_name].astype(str) == str(result_period_value)]

        if df_filtered_period.empty:
            print(f"DEBUG: _fetch_latest_report_data: No data found for period {result_period_value} after filtering by '{result_period_field_name}' for {func_name} on {api_params.get('ts_code')}. Original df had {len(df)} rows.", file=sys.stderr, flush=True)
            # Fallback: if strict period filtering yields nothing, but original df had data, 
            # it might be that ann_date is more reliable or the period was slightly off.
            # For now, let's return None if period match fails, to be strict.
            # Consider alternative fallback if needed, e.g. using latest ann_date from original df.
            return None

        # Sort by ann_date to get the latest announcement(s) for that specific period
        df_sorted_by_ann = df_filtered_period.sort_values(by='ann_date', ascending=False)
        if df_sorted_by_ann.empty: # Should not happen if df_filtered_period was not empty
            return None
        
        latest_ann_date = df_sorted_by_ann['ann_date'].iloc[0]
        df_latest_ann = df_sorted_by_ann[df_sorted_by_ann['ann_date'] == latest_ann_date]
        
        if is_list_result:
            print(f"DEBUG: _fetch_latest_report_data: Returning {len(df_latest_ann)} rows for latest announcement on {latest_ann_date} (list_result=True)", file=sys.stderr, flush=True)
            return df_latest_ann # Return all rows for the latest announcement date for this period
        else:
            # Return only the top-most row (which is the latest announcement for that period)
            print(f"DEBUG: _fetch_latest_report_data: Returning 1 row for latest announcement on {latest_ann_date} (list_result=False)", file=sys.stderr, flush=True)
            return df_latest_ann.head(1)

    except Exception as e:
        print(f"Error in _fetch_latest_report_data calling {func_name} for {api_params.get('ts_code', 'N/A')}, period {result_period_value}: {e}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return None
# --- End of MODIFIED _fetch_latest_report_data ---

# --- MCP Instance Creation ---
try:
    mcp = FastMCP("Tushare Tools Enhanced")
    print("DEBUG: FastMCP instance created for Tushare Tools Enhanced.", file=sys.stderr, flush=True)
except Exception as e:
    print(f"DEBUG: ERROR creating FastMCP: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    raise
# --- End of MCP Instance Creation ---

# --- FastAPI App Creation and Basic Endpoint ---
app = FastAPI(
    title="Tushare MCP API",
    description="Remote API for Tushare MCP tools via FastAPI.",
    version="0.0.1"
)

@app.get("/")
async def read_root():
    return {"message": "Hello World - Tushare MCP API is running!"}

# New API endpoint for setting up Tushare token
@app.post("/tools/setup_tushare_token", summary="Setup Tushare API token")
async def api_setup_tushare_token(payload: dict = Body(...)):
    """
    Sets the Tushare API token.
    Expects a JSON payload with a "token" key.
    Example: {"token": "your_actual_token_here"}
    """
    print(f"DEBUG: API /tools/setup_tushare_token called with payload: {{payload}}", file=sys.stderr, flush=True)
    token = payload.get("token")
    if not token or not isinstance(token, str):
        print(f"DEBUG: API /tools/setup_tushare_token - Missing or invalid token in payload.", file=sys.stderr, flush=True)
        raise HTTPException(status_code=400, detail="Missing or invalid 'token' in payload. Expected a JSON object with a 'token' string.")

    try:
        # Call your original tool function
        original_tool_function_output = setup_tushare_token(token=token) # This is your original @mcp.tool() function
        print(f"DEBUG: API /tools/setup_tushare_token - Original tool output: {{original_tool_function_output}}", file=sys.stderr, flush=True)
        return {"status": "success", "message": original_tool_function_output}
    except Exception as e:
        error_message = f"Error setting up token via API: {str(e)}"
        print(f"DEBUG: ERROR in api_setup_tushare_token: {{error_message}}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr) # Keep detailed server-side logs
        raise HTTPException(status_code=500, detail=error_message)

# --- End of FastAPI App Creation ---

# --- Start of Core Token Management Functions (to be kept) ---
def init_env_file():
    """初始化环境变量文件"""
    print("DEBUG: init_env_file called.", file=sys.stderr, flush=True)
    try:
        print(f"DEBUG: Attempting to create directory: {ENV_FILE.parent}", file=sys.stderr, flush=True)
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        print(f"DEBUG: Directory {ENV_FILE.parent} ensured.", file=sys.stderr, flush=True)
        if not ENV_FILE.exists():
            print(f"DEBUG: ENV_FILE {ENV_FILE} does not exist, attempting to touch.", file=sys.stderr, flush=True)
            ENV_FILE.touch()
            print(f"DEBUG: ENV_FILE {ENV_FILE} touched.", file=sys.stderr, flush=True)
        else:
            print(f"DEBUG: ENV_FILE {ENV_FILE} already exists.", file=sys.stderr, flush=True)
        load_dotenv(ENV_FILE)
        print("DEBUG: load_dotenv(ENV_FILE) called.", file=sys.stderr, flush=True)
    except Exception as e_fs:
        print(f"DEBUG: ERROR in init_env_file filesystem operations: {str(e_fs)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)

def get_tushare_token() -> Optional[str]:
    """获取Tushare token"""
    print("DEBUG: get_tushare_token called.", file=sys.stderr, flush=True)
    init_env_file()
    token = os.getenv("TUSHARE_TOKEN")
    print(f"DEBUG: get_tushare_token: os.getenv result: {'TOKEN_FOUND' if token else 'NOT_FOUND'}", file=sys.stderr, flush=True)
    return token

def set_tushare_token(token: str):
    """设置Tushare token"""
    print(f"DEBUG: set_tushare_token called with token: {'********' if token else 'None'}", file=sys.stderr, flush=True)
    init_env_file()
    try:
        set_key(ENV_FILE, "TUSHARE_TOKEN", token)
        print(f"DEBUG: set_key executed for ENV_FILE: {ENV_FILE}", file=sys.stderr, flush=True)
        ts.set_token(token)
        print("DEBUG: ts.set_token(token) executed.", file=sys.stderr, flush=True)
    except Exception as e_set_token:
        print(f"DEBUG: ERROR in set_tushare_token during set_key or ts.set_token: {str(e_set_token)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)

# --- End of Core Token Management Functions ---

# Tools and Prompts will be added here one by one from refer/server.py

@mcp.prompt()
def configure_token() -> str:
    """配置Tushare token的提示模板"""
    print("DEBUG: Prompt configure_token is being accessed/defined.", file=sys.stderr, flush=True)
    return """请提供您的Tushare API token。
您可以在 https://tushare.pro/user/token 获取您的token。
如果您还没有Tushare账号，请先在 https://tushare.pro/register 注册。

请输入您的token:"""

@mcp.tool()
def setup_tushare_token(token: str) -> str:
    """设置Tushare API token"""
    print(f"DEBUG: Tool setup_tushare_token called with token: {'********' if token else 'None'}", file=sys.stderr, flush=True)
    try:
        set_tushare_token(token)
        print("DEBUG: setup_tushare_token attempting ts.pro_api() call.", file=sys.stderr, flush=True)
        ts.pro_api()
        print("DEBUG: setup_tushare_token ts.pro_api() call successful.", file=sys.stderr, flush=True)
        return "Token配置成功！您现在可以使用Tushare的API功能了。"
    except Exception as e:
        print(f"DEBUG: ERROR in setup_tushare_token: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"Token配置失败：{str(e)}"

@mcp.tool()
def check_token_status() -> str:
    """检查Tushare token状态"""
    print("DEBUG: Tool check_token_status called.", file=sys.stderr, flush=True)
    token = get_tushare_token()
    if not token:
        print("DEBUG: check_token_status: No token found by get_tushare_token.", file=sys.stderr, flush=True)
        return "未配置Tushare token。请使用configure_token提示来设置您的token。"
    try:
        print("DEBUG: check_token_status attempting ts.pro_api() call.", file=sys.stderr, flush=True)
        ts.pro_api()
        print("DEBUG: check_token_status ts.pro_api() call successful.", file=sys.stderr, flush=True)
        return "Token配置正常，可以使用Tushare API。"
    except Exception as e:
        print(f"DEBUG: ERROR in check_token_status: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"Token无效或已过期：{str(e)}"

@mcp.tool()
def get_stock_basic_info(ts_code: str = "", name: str = "") -> str:
    """
    获取股票基本信息

    参数:
        ts_code: 股票代码（如：000001.SZ）
        name: 股票名称（如：平安银行）
    """
    print(f"DEBUG: Tool get_stock_basic_info called with ts_code: '{ts_code}', name: '{name}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    try:
        pro = ts.pro_api()
        filters = {}
        if ts_code:
            filters['ts_code'] = ts_code
        if name:
            filters['name'] = name

        df = pro.stock_basic(**filters)
        if df.empty:
            return "未找到符合条件的股票"

        result = []
        for _, row in df.iterrows():
            available_fields = row.index.tolist()
            info_parts = []
            if 'ts_code' in available_fields:
                info_parts.append(f"股票代码: {row['ts_code']}")
            if 'name' in available_fields:
                info_parts.append(f"股票名称: {row['name']}")
            optional_fields = {
                'area': '所属地区', 'industry': '所属行业', 'list_date': '上市日期',
                'market': '市场类型', 'exchange': '交易所', 'curr_type': '币种',
                'list_status': '上市状态', 'delist_date': '退市日期'
            }
            for field, label in optional_fields.items():
                if field in available_fields and not pd.isna(row[field]):
                    info_parts.append(f"{label}: {row[field]}")
            info = "\\n".join(info_parts)
            info += "\\n------------------------"
            result.append(info)
        return "\\n".join(result)
    except Exception as e:
        print(f"DEBUG: ERROR in get_stock_basic_info: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"查询失败：{str(e)}"

@mcp.tool()
def search_index(index_name: str, market: str = None, publisher: str = None, category: str = None) -> str:
    """
    根据指数名称搜索指数的基本信息，用于查找指数的TS代码。

    参数:
        index_name: 指数简称或包含在全称中的关键词 (例如: "沪深300", "A50")
        market: 交易所或服务商代码 (可选, 例如: CSI, SSE, SZSE, MSCI, OTH)
        publisher: 发布商 (可选, 例如: "中证公司", "申万", "MSCI")
        category: 指数类别 (可选, 例如: "规模指数", "行业指数")
    """
    print(f"DEBUG: Tool search_index called with name: '{index_name}', market: '{market}', publisher: '{publisher}', category: '{category}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not index_name:
        return "错误: 指数名称 (index_name) 是必需参数。"

    try:
        pro = ts.pro_api()
        query_params = {
            'name': index_name,
            'fields': 'ts_code,name,fullname,market,publisher,category,list_date'
        }
        if market:
            query_params['market'] = market
        if publisher:
            query_params['publisher'] = publisher
        if category:
            query_params['category'] = category
        
        # The 'name' parameter in index_basic acts as a keyword search against 'name' and 'fullname'
        # No need for complex df filtering if API handles keyword search well.
        df = pro.index_basic(**query_params)

        if df.empty:
            return f"未找到与 '{index_name}'相关的指数。尝试更通用或精确的关键词，或检查市场/发布商/类别参数。"

        results = [f"--- 指数搜索结果 for '{index_name}' ---"]
        # Limit results to avoid overly long output, e.g., top 20 matches
        # Sort by list_date (desc) and then ts_code to have some order if many results
        df_sorted = df.sort_values(by=['list_date', 'ts_code'], ascending=[False, True]).head(20)

        for _, row in df_sorted.iterrows():
            info_parts = [
                f"TS代码: {row.get('ts_code', 'N/A')}",
                f"简称: {row.get('name', 'N/A')}",
                f"全称: {row.get('fullname', 'N/A')}",
                f"市场: {row.get('market', 'N/A')}",
                f"发布方: {row.get('publisher', 'N/A')}",
                f"类别: {row.get('category', 'N/A')}",
                f"发布日期: {row.get('list_date', 'N/A')}"
            ]
            results.append("\n".join(info_parts))
            results.append("------------------------")
        
        if len(df) > 20:
            results.append(f"注意: 结果超过20条，仅显示前20条。请尝试使用 market, publisher 或 category 参数缩小范围。")

        return "\n".join(results)

    except Exception as e:
        print(f"DEBUG: ERROR in search_index for '{index_name}': {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"搜索指数 '{index_name}' 失败: {str(e)}"

@mcp.tool()
def get_index_list(ts_code: str = None, name: str = None, market: str = None, publisher: str = None, category: str = None) -> str:
    """
    获取指数基础信息列表。可以根据一个或多个条件进行筛选。
    例如，仅提供 market='CSI' 可以列出中证指数相关指数。

    参数:
        ts_code: 指数代码 (可选, 例如: 000300.SH)
        name: 指数简称或包含在全称中的关键词 (可选, 例如: "沪深300", "A50")
        market: 交易所或服务商代码 (可选, 例如: CSI, SSE, SZSE, MSCI, OTH)
        publisher: 发布商 (可选, 例如: "中证公司", "申万", "MSCI")
        category: 指数类别 (可选, 例如: "规模指数", "行业指数")
    """
    print(f"DEBUG: Tool get_index_list called with ts_code: '{ts_code}', name: '{name}', market: '{market}', publisher: '{publisher}', category: '{category}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"

    if not any([ts_code, name, market, publisher, category]):
        return "错误: 请至少提供一个查询参数 (ts_code, name, market, publisher, or category)。"

    try:
        pro = ts.pro_api()
        query_params = {}
        if ts_code:
            query_params['ts_code'] = ts_code
        if name:
            query_params['name'] = name
        if market:
            query_params['market'] = market
        if publisher:
            query_params['publisher'] = publisher
        if category:
            query_params['category'] = category
        
        query_params['fields'] = 'ts_code,name,fullname,market,publisher,category,list_date,base_date,base_point,weight_rule,desc,exp_date'
        
        df = pro.index_basic(**query_params)

        if df.empty:
            return f"未找到符合指定条件的指数。"

        results = [f"--- 指数列表查询结果 ---"]
        # Limit results to avoid overly long output, e.g., top 30 matches
        # Sort by list_date (desc) and then ts_code to have some order if many results
        df_sorted = df.sort_values(by=['market', 'list_date', 'ts_code'], ascending=[True, False, True]).head(30)

        for _, row in df_sorted.iterrows():
            info_parts = [
                f"TS代码: {row.get('ts_code', 'N/A')}",
                f"简称: {row.get('name', 'N/A')}",
                f"全称: {row.get('fullname', 'N/A')}",
                f"市场: {row.get('market', 'N/A')}",
                f"发布方: {row.get('publisher', 'N/A')}",
                f"类别: {row.get('category', 'N/A')}",
                f"发布日期: {row.get('list_date', 'N/A')}",
                f"基期: {row.get('base_date', 'N/A')}",
                f"基点: {row.get('base_point', 'N/A')}",
                f"加权方式: {row.get('weight_rule', 'N/A')}",
                # f"描述: {row.get('desc', 'N/A')}", # Description can be very long
                f"终止日期: {row.get('exp_date', 'N/A') if pd.notna(row.get('exp_date')) else 'N/A'}"
            ]
            results.append("\n".join(info_parts))
            results.append("------------------------")
        
        if len(df) > 30:
            results.append(f"注意: 结果超过30条，仅显示前30条（按市场、发布日期排序）。请提供更精确的查询参数以缩小范围。")

        return "\n".join(results)

    except Exception as e:
        error_msg_detail = f"ts_code={ts_code}, name={name}, market={market}, publisher={publisher}, category={category}"
        print(f"DEBUG: ERROR in get_index_list for {error_msg_detail}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取指数列表失败: {str(e)}"

@mcp.tool()
def search_stocks(keyword: str) -> str:
    """
    搜索股票

    参数:
        keyword: 关键词（可以是股票代码的一部分或股票名称的一部分）
    """
    print(f"DEBUG: Tool search_stocks called with keyword: '{keyword}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    try:
        pro = ts.pro_api()
        df = pro.stock_basic()
        mask = (df['ts_code'].str.contains(keyword, case=False, na=False)) | \
               (df['name'].str.contains(keyword, case=False, na=False))
        results_df = df[mask]
        if results_df.empty:
            return "未找到符合条件的股票"
        output = []
        for _, row in results_df.iterrows():
            output.append(f"{row['ts_code']} - {row['name']}")
        return "\\n".join(output)
    except Exception as e:
        print(f"DEBUG: ERROR in search_stocks: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"搜索失败：{str(e)}"

@mcp.tool()
def get_daily_metrics(ts_code: str, trade_date: str) -> str:
    """
    获取指定股票在特定交易日的主要行情指标（成交额、换手率、量比）。

    参数:
        ts_code: 股票代码 (例如: 300170.SZ)
        trade_date: 交易日期 (YYYYMMDD格式, 例如: 20240421)
    """
    print(f"DEBUG: Tool get_daily_metrics called with ts_code: '{ts_code}', trade_date: '{trade_date}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code) # Uses helper function

        # --- 获取日线行情数据 (用于成交额 amount) ---
        df_daily = pro.daily(ts_code=ts_code, trade_date=trade_date)
        amount_str = "未获取到"
        if not df_daily.empty:
            daily_data = df_daily.iloc[0]
            if 'amount' in daily_data and pd.notna(daily_data['amount']):
                amount_in_yuan_100m = daily_data['amount'] / 100000 # Tushare daily.amount is in thousands
                amount_str = f"{amount_in_yuan_100m:.4f} 亿元"
            else:
                amount_str = "未提供成交额数据"
        else:
            amount_str = "未获取到当日行情数据"

        # --- 获取日线基本指标 (用于换手率 turnover_rate, 量比 volume_ratio) ---
        df_basic = pro.daily_basic(ts_code=ts_code, trade_date=trade_date)
        turnover_rate_str = "未获取到"
        volume_ratio_str = "未获取到"
        if not df_basic.empty:
            basic_data = df_basic.iloc[0]
            if 'turnover_rate' in basic_data and pd.notna(basic_data['turnover_rate']):
                turnover_rate_str = f"{basic_data['turnover_rate']:.2f}%"
            else:
                turnover_rate_str = "未提供换手率数据"
            if 'volume_ratio' in basic_data and pd.notna(basic_data['volume_ratio']):
                volume_ratio_str = f"{basic_data['volume_ratio']:.2f}"
            else:
                volume_ratio_str = "未提供量比数据"
        else:
            turnover_rate_str = "未获取到当日指标数据"
            volume_ratio_str = "未获取到当日指标数据"

        results = [
            f"--- {stock_name} ({ts_code}) {trade_date} 行情指标 ---",
            f"成交额: {amount_str}",
            f"换手率: {turnover_rate_str}",
            f"量比: {volume_ratio_str}"
        ]
        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_daily_metrics: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取每日行情指标失败：{str(e)}"

@mcp.tool()
def get_daily_prices(ts_code: str, trade_date: str) -> str:
    """
    获取指定股票在特定交易日的开盘价、最高价、最低价和收盘价。

    参数:
        ts_code: 股票代码 (例如: 600126.SH)
        trade_date: 交易日期 (YYYYMMDD格式, 例如: 20250227)
    """
    print(f"DEBUG: Tool get_daily_prices called with ts_code: '{ts_code}', trade_date: '{trade_date}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        req_fields = 'ts_code,trade_date,open,high,low,close,pct_chg'
        df_daily = pro.daily(ts_code=ts_code, trade_date=trade_date, fields=req_fields)

        if df_daily.empty:
            return f"未找到 {stock_name} ({ts_code}) 在 {trade_date} 的日线行情数据。"

        price_data = df_daily.iloc[0]
        results = [f"--- {stock_name} ({ts_code}) {trade_date} 价格信息 ---"]
        price_fields = {
            'open': '开盘价', 'high': '最高价', 'low': '最低价',
            'close': '收盘价', 'pct_chg': '当日涨跌幅'
        }
        for field, label in price_fields.items():
            if field in price_data and pd.notna(price_data[field]):
                try:
                    numeric_value = pd.to_numeric(price_data[field])
                    unit = '元' if field in ['open', 'high', 'low', 'close'] else '%'
                    results.append(f"{label}: {numeric_value:.2f} {unit}")
                except (ValueError, TypeError):
                    unit = '元' if field in ['open', 'high', 'low', 'close'] else '%' # Ensure unit is defined for error case
                    results.append(f"{label}: (值非数字: {price_data[field]}) {unit}")
            else:
                unit = '元' if field in ['open', 'high', 'low', 'close'] else '%' # Ensure unit is defined for missing case
                results.append(f"{label}: 未提供 {unit}")
        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_daily_prices: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取每日价格数据失败：{str(e)}"

@mcp.tool()
def get_financial_indicator(
    ts_code: str, 
    period: str = None, 
    ann_date: str = None, 
    start_date: str = None, 
    end_date: str = None,
    limit: int = 10 # Max number of reports to return if multiple are found
) -> str:
    """
    获取A股上市公司历史财务指标数据。
    可以按报告期(period)、公告日期(ann_date)或公告日期范围(start_date, end_date)进行查询。
    必须提供 ts_code。
    必须提供以下条件之一：
    1. period (报告期)
    2. ann_date (公告日期)
    3. start_date 和 end_date (公告日期范围)
    返回匹配条件的所有财务报告期数据 (按报告期、公告日降序排列，最多显示 limit 条记录)。

    参数:
        ts_code: 股票代码 (例如: 600348.SH)
        period: 报告期 (可选, YYYYMMDD格式, 例如: 20231231 代表年报)
        ann_date: 公告日期 (可选, YYYYMMDD格式)
        start_date: 公告开始日期 (可选, YYYYMMDD格式, 与end_date一同使用)
        end_date: 公告结束日期 (可选, YYYYMMDD格式, 与start_date一同使用)
        limit: 返回记录的条数上限 (默认为10)
    """
    debug_params = f"ts_code='{ts_code}', period='{period}', ann_date='{ann_date}', start_date='{start_date}', end_date='{end_date}', limit={limit}"
    print(f"DEBUG: Tool get_financial_indicator (enhanced) called with {debug_params}.", file=sys.stderr, flush=True)

    if not get_tushare_token():
        return "请先配置Tushare token"
    if not ts_code:
        return "错误: 股票代码 (ts_code) 是必需的。"

    if not (period or ann_date or (start_date and end_date)):
        return "错误: 请至少提供 period, ann_date, 或 start_date 与 end_date 组合中的一组参数。"
    if (start_date and not end_date) or (not start_date and end_date):
        return "错误: start_date 和 end_date 必须同时提供。"

    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        
        api_params = {'ts_code': ts_code}
        if period:
            api_params['period'] = period
        if ann_date:
            api_params['ann_date'] = ann_date
        if start_date and end_date: # ann_date range
            api_params['start_date'] = start_date
            api_params['end_date'] = end_date

        # Enhanced list of fields including debt_to_assets
        req_fields = (
            'ts_code,ann_date,end_date,eps,dt_eps,'
            'grossprofit_margin,netprofit_margin,roe_yearly,roe_waa,roe_dt,'
            'n_income_attr_p,total_revenue,rd_exp,debt_to_assets,'
            'n_income_attr_p_yoy,dtprofit_yoy,tr_yoy,or_yoy,bps,ocfps,update_flag'
        )
        api_params['fields'] = req_fields
        
        df = pro.fina_indicator(**api_params)

        if df.empty:
            return f"未找到 {stock_name} ({ts_code}) 符合指定条件的财务指标数据。"

        # Sort by report end_date first (desc), then by announcement date (desc) to get latest announcements for latest periods
        df_sorted = df.sort_values(by=['end_date', 'ann_date'], ascending=[False, False])
        
        all_results_str = [f"--- {stock_name} ({ts_code}) 历史财务指标 (最多显示 {limit} 条) ---"]
        
        actual_limit = min(limit, len(df_sorted))
        if actual_limit == 0:
             return f"未找到 {stock_name} ({ts_code}) 符合指定条件的财务指标数据 (排序后为空)。"

        for i in range(actual_limit):
            indicator_data = df_sorted.iloc[i]
            current_period_end_date = indicator_data.get('end_date', 'N/A')
            current_ann_date = indicator_data.get('ann_date', 'N/A')
            report_header = f"报告期: {current_period_end_date}, 公告日期: {current_ann_date}"
            results_for_report = [report_header]

            def format_indicator(key, label, unit="%"):
                if key in indicator_data and pd.notna(indicator_data[key]):
                    value = indicator_data[key]
                    try:
                        numeric_value = pd.to_numeric(value)
                        if unit == "亿元":
                            # Tushare fina_indicator amounts are in Yuan, convert to 100 million Yuan
                            return f"{label}: {numeric_value / 100000000:.4f} {unit}"
                        elif unit == "元":
                            return f"{label}: {numeric_value:.4f} {unit}"
                        elif unit == "%" :
                            return f"{label}: {numeric_value:.2f}%"
                        else:
                            return f"{label}: {numeric_value}"
                    except (ValueError, TypeError):
                        return f"{label}: (值非数字: {value})"
                return f"{label}: 未提供"

            results_for_report.append(format_indicator('eps', '每股收益', unit='元'))
            results_for_report.append(format_indicator('dt_eps', '扣非每股收益', unit='元'))
            results_for_report.append(format_indicator('bps', '每股净资产', unit='元'))
            results_for_report.append(format_indicator('ocfps', '每股经营现金流', unit='元'))
            results_for_report.append(format_indicator('grossprofit_margin', '销售毛利率'))
            results_for_report.append(format_indicator('netprofit_margin', '销售净利率'))
            results_for_report.append(format_indicator('roe_yearly', '年化净资产收益率(ROE)'))
            results_for_report.append(format_indicator('roe_waa', '加权平均ROE'))
            results_for_report.append(format_indicator('roe_dt', '扣非加权平均ROE'))
            results_for_report.append(format_indicator('debt_to_assets', '资产负债率'))
            results_for_report.append(format_indicator('total_revenue', '营业总收入', unit='亿元'))
            results_for_report.append(format_indicator('n_income_attr_p', '归属母公司净利润', unit='亿元'))
            results_for_report.append(format_indicator('rd_exp', '研发费用', unit='亿元'))
            results_for_report.append(format_indicator('tr_yoy', '营业总收入同比增长率'))
            results_for_report.append(format_indicator('or_yoy', '营业收入同比增长率')) # Operating Revenue YoY
            results_for_report.append(format_indicator('n_income_attr_p_yoy', '归母净利润同比增长率'))
            results_for_report.append(format_indicator('dtprofit_yoy', '扣非净利润同比增长率'))
            results_for_report.append(f"更新标识: {indicator_data.get('update_flag', 'N/A')}")
            
            all_results_str.append("\n".join(results_for_report))
            if i < actual_limit - 1:
                 all_results_str.append("------------------------")
        
        return "\n".join(all_results_str)

    except Exception as e:
        print(f"DEBUG: ERROR in get_financial_indicator (enhanced) for {debug_params}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取财务指标失败：{str(e)}"

@mcp.tool()
def get_income_statement(ts_code: str, period: str, report_type: str = "1") -> str:
    """
    获取指定股票在特定报告期(累计)的利润表主要数据，并计算净利润同比增长率。

    参数:
        ts_code: 股票代码（如：000001.SZ）
        period: 报告期 (YYYYMMDD格式, 例如: 20240930 获取2024年三季报累计)
        report_type: 报告类型（默认为1，合并报表）
    """
    print(f"DEBUG: Tool get_income_statement called with ts_code: '{ts_code}', period: '{period}', report_type: '{report_type}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not period or len(period) != 8 or not period.isdigit():
         return "错误：请提供有效的 'period' 参数 (YYYYMMDD格式)。"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        req_fields = 'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,basic_eps,total_revenue,n_income_attr_p,sell_exp,admin_exp,fin_exp,rd_exp,update_flag'
        params_current = {
            'ts_code': ts_code, 'period': period, 'report_type': report_type, 'fields': req_fields
        }
        df_current_latest = _fetch_latest_report_data(
            pro.income, result_period_field_name='end_date', result_period_value=period, **params_current
        )
        if df_current_latest is None:
            return f"未找到 {stock_name} ({ts_code}) 在报告期 {period} 的利润表数据。"
        current_income_data = df_current_latest.iloc[0]
        current_profit = pd.to_numeric(current_income_data.get('n_income_attr_p'), errors='coerce')

        year = int(period[:4])
        last_year_period = f"{year - 1}{period[4:]}"
        params_previous = {
            'ts_code': ts_code, 'period': last_year_period, 'report_type': report_type, 'fields': 'n_income_attr_p,end_date,ann_date'
        }
        df_previous_latest = _fetch_latest_report_data(
            pro.income, result_period_field_name='end_date', result_period_value=last_year_period, **params_previous
        )
        previous_profit = None
        previous_profit_str = "未找到去年同期数据"
        if df_previous_latest is not None:
             previous_profit_raw = df_previous_latest.iloc[0].get('n_income_attr_p')
             if pd.notna(previous_profit_raw):
                previous_profit = pd.to_numeric(previous_profit_raw, errors='coerce')
                previous_profit_str = f"{previous_profit / 100000000:.4f} 亿元"
             else:
                 previous_profit_str = "去年同期净利润数据无效"
        profit_yoy_str = "无法计算 (缺少本期或去年同期数据)"
        if pd.notna(current_profit) and previous_profit is not None and pd.notna(previous_profit):
            if previous_profit == 0:
                profit_yoy_str = "去年同期为0，无法计算比率"
            elif previous_profit < 0:
                 profit_yoy = ((current_profit - previous_profit) / abs(previous_profit)) * 100
                 profit_yoy_str = f"{profit_yoy:.2f}%"
            else: 
                 profit_yoy = ((current_profit - previous_profit) / previous_profit) * 100
                 profit_yoy_str = f"{profit_yoy:.2f}%"
        results = [f"--- {stock_name} ({ts_code}) {period} 利润表数据 ---"]
        def format_value(key, unit="亿元"):
            data_source = current_income_data
            if key in data_source and pd.notna(data_source[key]):
                value = data_source[key]
                if unit == "亿元":
                    try: return f"{pd.to_numeric(value) / 100000000:.4f} {unit}"
                    except (ValueError, TypeError): return f"(值非数字: {value})"
                elif unit == "元":
                     try: return f"{pd.to_numeric(value):.4f} {unit}"
                     except (ValueError, TypeError): return f"(值非数字: {value})"
                else: return f"{value}"
            return "未提供"
        results.append(f"营业总收入: {format_value('total_revenue')}")
        results.append(f"归属母公司净利润: {format_value('n_income_attr_p')}")
        results.append(f"去年同期净利润 ({last_year_period}): {previous_profit_str}")
        results.append(f"净利润同比增长率: {profit_yoy_str}")
        results.append(f"销售费用: {format_value('sell_exp')}")
        results.append(f"管理费用: {format_value('admin_exp')}")
        results.append(f"财务费用: {format_value('fin_exp')}")
        results.append(f"研发费用: {format_value('rd_exp')}")
        results.append(f"基本每股收益: {format_value('basic_eps', unit='元')}")
        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_income_statement: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"查询利润表失败：{str(e)}"

@mcp.prompt()
def income_statement_query() -> str:
    """利润表查询提示模板"""
    print("DEBUG: Prompt income_statement_query is being accessed/defined.", file=sys.stderr, flush=True)
    return """请提供以下信息来查询利润表：

1. 股票代码（必填，如：000001.SZ）

2. 时间范围（可选）：
   - 开始日期（YYYYMMDD格式，如：20230101）
   - 结束日期（YYYYMMDD格式，如：20231231）

3. 报告类型（可选，默认为合并报表）：
   1 = 合并报表（默认）
   2 = 单季合并
   3 = 调整单季合并表
   4 = 调整合并报表
   5 = 调整前合并报表
   6 = 母公司报表
   7 = 母公司单季表
   8 = 母公司调整单季表
   9 = 母公司调整表
   10 = 母公司调整前报表
   11 = 母公司调整前合并报表
   12 = 母公司调整前报表

示例查询：
1. 查询最新报表：
   "查询平安银行(000001.SZ)的最新利润表"

2. 查询指定时间范围：
   "查询平安银行2023年的利润表"
   "查询平安银行2023年第一季度的利润表"

3. 查询特定报表类型：
   "查询平安银行的母公司报表"
   "查询平安银行2023年的单季合并报表"

请告诉我您想查询的内容："""

@mcp.tool()
def get_shareholder_count(ts_code: str, end_date: str = "") -> str:
    """
    获取上市公司在指定截止日期的股东户数。

    参数:
        ts_code: 股票代码 (例如: 000665.SZ)
        end_date: 截止日期 (YYYYMMDD, 例如: 20240930)
    """
    print(f"DEBUG: Tool get_shareholder_count called with ts_code: '{ts_code}', end_date: '{end_date}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not end_date:
        return "错误：请提供截止日期 (end_date)。"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        params = {
            'ts_code': ts_code, 'enddate': end_date, 'fields': 'ts_code,ann_date,enddate,holder_num'
        }
        df_holder_latest = _fetch_latest_report_data(
            pro.stk_holdernumber, 
            result_period_field_name='enddate', 
            result_period_value=end_date,
            **params
        )
        if df_holder_latest is None or df_holder_latest.empty:
            return f"未找到 {stock_name} ({ts_code}) 在 {end_date} 的股东户数数据。"
        holder_data = df_holder_latest.iloc[0]
        holder_num = holder_data.get('holder_num', None)
        ann_date_val = holder_data.get('ann_date', 'N/A')
        if pd.isna(holder_num):
            return f"获取到 {stock_name} ({ts_code}) 在 {end_date} 的记录，但股东户数 (holder_num) 字段为空或无效。公告日期: {ann_date_val}"
        try:
            holder_num_int = int(holder_num)
            holder_num_wan = holder_num_int / 10000
            return f"截至 {end_date}，{stock_name} ({ts_code}) 股东户数为: {holder_num_wan:.2f} 万户 (公告日期: {ann_date_val})"
        except (ValueError, TypeError):
            return f"获取到 {stock_name} ({ts_code}) 在 {end_date} 的股东户数数据，但无法转换为数字: {holder_num}。公告日期: {ann_date_val}"
    except Exception as e:
        print(f"DEBUG: ERROR in get_shareholder_count: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取股东户数失败：{str(e)}"

@mcp.tool()
def get_daily_basic_info(ts_code: str, trade_date: str) -> str:
    """
    获取指定股票在特定交易日的基本指标信息，如股本、市值等。

    参数:
        ts_code: 股票代码 (例如: 000665.SZ)
        trade_date: 交易日期 (YYYYMMDD, 例如: 20240930)
    """
    print(f"DEBUG: Tool get_daily_basic_info called with ts_code: '{ts_code}', trade_date: '{trade_date}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not trade_date:
        return "错误：请提供交易日期 (trade_date)。"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        req_fields = 'ts_code,trade_date,total_share,float_share,free_share,total_mv,circ_mv,pe,pb,dv_ratio'
        df_basic = pro.daily_basic(ts_code=ts_code, trade_date=trade_date, fields=req_fields)
        if df_basic.empty:
            return f"未找到 {stock_name} ({ts_code}) 在 {trade_date} 的每日基本指标数据。"
        basic_data = df_basic.iloc[0]
        results = [f"--- {stock_name} ({ts_code}) {trade_date} 基本指标 ---"]
        def format_basic(key, label, unit="万股"):
            if key in basic_data and pd.notna(basic_data[key]):
                value = basic_data[key]
                try:
                    numeric_value = pd.to_numeric(value)
                    if unit == "万股": return f"{label}: {numeric_value:.2f} {unit}"
                    elif unit == "万元": return f"{label}: {numeric_value:.2f} {unit}"
                    elif unit == "倍": return f"{label}: {numeric_value:.2f} {unit}"
                    elif unit == "%": return f"{label}: {numeric_value:.2f}%"
                    else: return f"{label}: {numeric_value}"
                except (ValueError, TypeError): return f"{label}: (值非数字: {value})"
            return f"{label}: 未提供"
        results.append(format_basic('total_share', '总股本'))
        results.append(format_basic('float_share', '流通股本'))
        results.append(format_basic('free_share', '自由流通股本'))
        results.append(format_basic('total_mv', '总市值', unit='万元'))
        results.append(format_basic('circ_mv', '流通市值', unit='万元'))
        results.append(format_basic('pe', '市盈率(PE)', unit='倍'))
        results.append(format_basic('pb', '市净率(PB)', unit='倍'))
        results.append(format_basic('dv_ratio', '股息率(TTM)', unit='%'))
        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_daily_basic_info: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取每日基本指标失败：{str(e)}"

@mcp.tool()
def get_top_holders(ts_code: str, period: str, holder_type: str = 'H') -> str:
    """
    获取上市公司前十大股东或前十大流通股东信息。

    参数:
        ts_code: 股票代码 (例如: 000665.SZ)
        period: 报告期 (YYYYMMDD, 例如: 20240930)
        holder_type: 股东类型 ('H'=前十大股东, 'F'=前十大流通股东, 默认为'H')
    """
    print(f"DEBUG: Tool get_top_holders called with ts_code: '{ts_code}', period: '{period}', holder_type: '{holder_type}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not period:
        return "错误：请提供报告期 (period)。"
    if holder_type not in ['H', 'F']:
        return "错误：holder_type 参数必须是 'H' (前十大股东) 或 'F' (前十大流通股东)。"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        api_func = pro.top10_holders if holder_type == 'H' else pro.top10_floatholders
        type_desc = "前十大股东" if holder_type == 'H' else "前十大流通股东"
        req_fields = 'ts_code,ann_date,end_date,holder_name,hold_amount,hold_ratio' 
        if holder_type == 'H': 
            req_fields += ',holder_type'
        params = {'ts_code': ts_code, 'period': period, 'fields': req_fields}
        df_holders_data = _fetch_latest_report_data(
            api_func, 
            result_period_field_name='end_date', 
            result_period_value=period, 
            is_list_result=True,  
            **params
        )
        if df_holders_data is None or df_holders_data.empty:
            return f"未找到 {stock_name} ({ts_code}) 在 {period} 的{type_desc}数据。"
        latest_ann_date = df_holders_data['ann_date'].iloc[0] if not df_holders_data.empty and 'ann_date' in df_holders_data.columns else 'N/A'
        results = [f"--- {stock_name} ({ts_code}) {period} {type_desc} (公告日期: {latest_ann_date}) ---"]
        for index, row in df_holders_data.iterrows(): 
            rank = index + 1 
            results.append(f"{rank}. 股东名称: {row.get('holder_name', 'N/A')}")
            hold_amount_wan = row.get('hold_amount', float('nan')) / 10000 
            hold_amount_str = f"{hold_amount_wan:.4f}" if pd.notna(hold_amount_wan) else 'N/A'
            hold_ratio_val = row.get('hold_ratio')
            hold_ratio_str = f"{hold_ratio_val:.2f}%" if pd.notna(hold_ratio_val) else 'N/A'
            results.append(f"   持有数量: {hold_amount_str} 万股")
            results.append(f"   占总股本比例: {hold_ratio_str}")
            if holder_type == 'H' and 'holder_type' in row and pd.notna(row['holder_type']):
                 results.append(f"   股东类型: {row['holder_type']}") 
            results.append("-" * 5)
        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_top_holders: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取{type_desc}失败：{str(e)}"

@mcp.tool()
def get_index_constituents(index_code: str, start_date: str, end_date: str) -> str:
    """
    获取指定指数在给定月份的成分股列表及其权重。
    Tushare API 指明这是月度数据。为获取特定月份数据，
    建议 start_date 和 end_date 分别设为目标月份的第一天和最后一天。

    参数:
        index_code: 指数代码 (例如: 000300.SH, 399300.SZ)
        start_date: 开始日期 (YYYYMMDD格式, 例如: 20230901)
        end_date: 结束日期 (YYYYMMDD格式, 例如: 20230930)
    """
    print(f"DEBUG: Tool get_index_constituents called for index: '{index_code}', start: '{start_date}', end: '{end_date}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not index_code or not start_date or not end_date:
        return "错误: index_code, start_date, 和 end_date 都是必需参数。"
    try:
        pro = ts.pro_api()
        
        index_name = index_code # Default to code
        try:
            # Attempt to fetch the index's display name
            index_basic_df = pro.index_basic(ts_code=index_code, fields='ts_code,name')
            if not index_basic_df.empty and 'name' in index_basic_df.columns:
                index_name = index_basic_df.iloc[0]['name']
        except Exception as e_idx_name:
            print(f"Warning: Failed to get index name for {index_code}: {e_idx_name}", file=sys.stderr, flush=True)

        # Fetch index weight data
        # Fields explicitly requested: index_code, con_code (constituent code), trade_date, weight
        df = pro.index_weight(index_code=index_code, start_date=start_date, end_date=end_date, fields='index_code,con_code,trade_date,weight')

        if df.empty:
            return f"未找到指数 {index_name} ({index_code}) 在 {start_date} 至 {end_date} 期间的成分股数据。"

        # Assuming trade_date is consistent for the month's data, take from the first row.
        record_trade_date = df['trade_date'].iloc[0] if 'trade_date' in df.columns and not df.empty else "未知"

        results = [f"--- {index_name} ({index_code}) 成分股及权重 (截至 {record_trade_date}, 查询区间 {start_date}-{end_date}) ---"]
        
        # Sort by weight in descending order for better readability
        df_sorted = df.sort_values(by='weight', ascending=False)

        for _, row in df_sorted.iterrows():
            con_code = row.get('con_code')
            weight = row.get('weight')
            
            if con_code is None: # Should not happen if API returns valid data
                continue

            stock_name = _get_stock_name(pro, con_code) # Use existing helper to get stock name

            weight_str = f"{weight:.4f}%" if pd.notna(weight) else "N/A" # Format weight as percentage string
            results.append(f"成分股: {con_code} ({stock_name}), 权重: {weight_str}")
        
        return "\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_index_constituents for {index_code}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取指数 {index_code} 成分股数据失败：{str(e)}"

@mcp.tool()
def get_global_index_quotes(ts_code: str, start_date: str = None, end_date: str = None, trade_date: str = None) -> str:
    """
    获取国际主要指数在指定日期范围或单个交易日的行情数据。

    参数:
        ts_code: TS指数代码 (例如: XIN9, HSI)
        start_date: 开始日期 (YYYYMMDD格式, 例如: 20240101)。如果提供了trade_date，此参数将被忽略。
        end_date: 结束日期 (YYYYMMDD格式, 例如: 20240131)。如果提供了trade_date，此参数将被忽略。
        trade_date: 单个交易日期 (YYYYMMDD格式, 例如: 20240115)。如果提供，将只查询该日数据。
    """
    print(f"DEBUG: Tool get_global_index_quotes called for ts_code: '{ts_code}', trade_date: '{trade_date}', start_date: '{start_date}', end_date: '{end_date}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not ts_code:
        return "错误: 指数代码 (ts_code) 是必需参数。"
    if not trade_date and not (start_date and end_date):
        return "错误: 请提供 trade_date 或同时提供 start_date 和 end_date。"

    try:
        pro = ts.pro_api()
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
            date_range_str = f"在 {trade_date}" if trade_date else f"在 {start_date} 至 {end_date} 期间"
            return f"未找到指数 {ts_code} {date_range_str} 的行情数据。"

        # 获取指数中文名用于显示，如果获取失败则用ts_code
        index_display_name = ts_code
        try:
            index_basics = pro.index_basic(ts_code=ts_code)
            if not index_basics.empty and 'name' in index_basics.columns:
                index_display_name = index_basics.iloc[0]['name'] + f" ({ts_code})"
            elif '.FXI' in ts_code or 'XIN9' in ts_code: # Hardcode for common ones if not in index_basic
                 idx_map = {"XIN9": "富时中国A50", "XIN9.FXI": "富时中国A50"}
                 index_display_name = idx_map.get(ts_code, ts_code) + f" ({ts_code})"

        except Exception as e_idx_name:
            print(f"Warning: Failed to get display name for index {ts_code}, using code. Error: {e_idx_name}", file=sys.stderr, flush=True)

        results = [f"--- {index_display_name} 行情数据 ---"]
        
        # Sort by trade_date, Tushare usually returns descending, but let's ensure ascending for multi-day reports
        df_sorted = df.sort_values(by='trade_date', ascending=True)

        for _, row in df_sorted.iterrows():
            info_parts = [
                f"交易日期: {row.get('trade_date', 'N/A')}",
                f"开盘点位: {row.get('open', 'N/A')}",
                f"收盘点位: {row.get('close', 'N/A')}",
                f"最高点位: {row.get('high', 'N/A')}",
                f"最低点位: {row.get('low', 'N/A')}",
                f"昨收盘点: {row.get('pre_close', 'N/A')}",
                f"涨跌点位: {row.get('change', 'N/A')}",
                f"涨跌幅: {row.get('pct_chg', 'N/A'):.2f}%" if pd.notna(row.get('pct_chg')) else "涨跌幅: N/A",
                f"振幅: {row.get('swing', 'N/A'):.2f}%" if pd.notna(row.get('swing')) else "振幅: N/A",
            ]
            # vol 和 amount 对很多国际指数可能为None或NaN，只在有效时显示
            if pd.notna(row.get('vol')):
                info_parts.append(f"成交量: {row.get('vol')}")
            if pd.notna(row.get('amount')):
                info_parts.append(f"成交额: {row.get('amount')}")
            results.append("\n".join(info_parts))
            results.append("------------------------")
        
        return "\n".join(results)

    except Exception as e:
        print(f"DEBUG: ERROR in get_global_index_quotes for {ts_code}: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取国际指数 {ts_code} 行情数据失败：{str(e)}"

@mcp.tool()
def get_period_price_change(ts_code: str, start_date: str, end_date: str) -> str:
    """
    计算指定股票在给定日期范围内的股价变动百分比。
    会自动查找范围内的实际首末交易日。

    参数:
        ts_code: 股票代码 (例如: 000665.SZ)
        start_date: 区间开始日期 (YYYYMMDD, 例如: 20240701)
        end_date: 区间结束日期 (YYYYMMDD, 例如: 20240930)
    """
    print(f"DEBUG: Tool get_period_price_change called with ts_code: '{ts_code}', start: '{start_date}', end: '{end_date}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not start_date or not end_date:
        return "错误：请提供完整的开始日期 (start_date) 和结束日期 (end_date)。"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        # Fetch daily data for the given range
        df_daily = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date, fields='trade_date,close')

        if df_daily.empty or len(df_daily) < 2:
            # Adjusted error message for clarity
            return f"未找到 {stock_name} ({ts_code}) 在 {start_date} 至 {end_date} 范围内的足够日线数据（需要至少两个交易日）来计算区间变动。"

        # Data is typically returned in descending order of trade_date by Tushare daily API
        # So, the first row is the end_date (or latest date in range) and last row is start_date (or earliest date in range)
        actual_end_trade_date = df_daily['trade_date'].iloc[0]
        actual_start_trade_date = df_daily['trade_date'].iloc[-1]
        
        end_close = pd.to_numeric(df_daily['close'].iloc[0], errors='coerce')
        start_close = pd.to_numeric(df_daily['close'].iloc[-1], errors='coerce')

        if pd.isna(start_close) or pd.isna(end_close) or start_close == 0:
            return f"无法计算 {stock_name} ({ts_code}) 在 {actual_start_trade_date}至{actual_end_trade_date} 的价格变动，开始或结束收盘价无效或为零。开始价: {start_close}, 结束价: {end_close}"

        price_change_pct = ((end_close - start_close) / start_close) * 100
        results = [
            f"--- {stock_name} ({ts_code}) 股价变动 ({start_date}至{end_date}) ---",
            f"实际区间首个交易日: {actual_start_trade_date}, 当日收盘价: {start_close:.2f} 元",
            f"实际区间最后交易日: {actual_end_trade_date}, 当日收盘价: {end_close:.2f} 元",
            f"区间涨跌幅: {price_change_pct:.2f}%"
        ]
        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_period_price_change: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"计算区间股价变动失败：{str(e)}"

@mcp.tool()
def get_balance_sheet(ts_code: str, period: str) -> str:
    """
    获取上市公司指定报告期的资产负债表主要数据。

    参数:
        ts_code: 股票代码 (例如: 300274.SZ)
        period: 报告期 (YYYYMMDD格式, 例如: 20240930)
    """
    print(f"DEBUG: Tool get_balance_sheet called with ts_code: '{ts_code}', period: '{period}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not period or len(period) != 8 or not period.isdigit():
         return "错误：请提供有效的 'period' 参数 (YYYYMMDD格式)。"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        req_fields = (
            'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,'
            'total_share,cap_rese,undistr_porfit,surplus_rese,special_rese,money_cap,'
            'trad_asset,notes_receiv,accounts_receiv,oth_receiv,prepayment,inventories,'
            'total_cur_assets,total_assets,accounts_payable,adv_receipts,total_cur_liab,'
            'total_liab,r_and_d_costs,lt_borr,total_hldr_eqy_exc_min_int' # total_hldr_eqy_exc_min_int is usually '股东权益合计(不含少数股东权益)'
        )
        params = {'ts_code': ts_code, 'period': period, 'fields': req_fields}
        
        # Use _fetch_latest_report_data, assuming we want the latest announcement for the period
        df_bs = _fetch_latest_report_data(
            pro.balancesheet, 
            result_period_field_name='end_date', 
            result_period_value=period,
            **params
        )

        if df_bs is None or df_bs.empty:
            return f"未找到 {stock_name} ({ts_code}) 在报告期 {period} 的资产负债表数据。"

        bs_data = df_bs.iloc[0]
        results = [f"--- {stock_name} ({ts_code}) {period} 资产负债表主要数据 ---"]
        latest_ann_date = bs_data.get('ann_date', 'N/A')
        results.append(f"(公告日期: {latest_ann_date})")

        def format_bs_value(key, label, unit="亿元"):
            if key in bs_data and pd.notna(bs_data[key]):
                value = bs_data[key]
                try:
                    numeric_value = pd.to_numeric(value)
                    if unit == "亿元": 
                        # Tushare balance sheet amounts are in Yuan, convert to 100 million Yuan
                        return f"{label}: {numeric_value / 100000000:.4f} {unit}"
                    elif unit == "元": # For per-share items if any (not typical for raw balances)
                        return f"{label}: {numeric_value:.4f} {unit}"
                    else: 
                        return f"{label}: {numeric_value}"
                except (ValueError, TypeError):
                    return f"{label}: (值非数字: {value})"
            return f"{label}: 未提供"

        results.append(format_bs_value('money_cap', '货币资金'))
        results.append(format_bs_value('accounts_receiv', '应收账款'))
        results.append(format_bs_value('inventories', '存货'))
        results.append(format_bs_value('total_cur_assets', '流动资产合计'))
        results.append(format_bs_value('total_assets', '资产总计'))
        results.append(format_bs_value('accounts_payable', '应付账款'))
        results.append(format_bs_value('total_cur_liab', '流动负债合计'))
        results.append(format_bs_value('lt_borr', '长期借款'))
        results.append(format_bs_value('total_liab', '负债合计'))
        results.append(format_bs_value('total_hldr_eqy_exc_min_int', '股东权益合计(不含少数股东权益)'))
        results.append(format_bs_value('cap_rese', '资本公积金'))
        results.append(format_bs_value('undistr_porfit', '未分配利润'))

        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_balance_sheet: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取资产负债表失败：{str(e)}"

@mcp.tool()
def get_cash_flow(ts_code: str, period: str) -> str:
    """
    获取上市公司指定报告期的现金流量表主要数据，特别是经营活动现金流净额。

    参数:
        ts_code: 股票代码 (例如: 300274.SZ)
        period: 报告期 (YYYYMMDD格式, 例如: 20240930)
    """
    print(f"DEBUG: Tool get_cash_flow called with ts_code: '{ts_code}', period: '{period}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    if not period or len(period) != 8 or not period.isdigit():
         return "错误：请提供有效的 'period' 参数 (YYYYMMDD格式)。"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        req_fields = (
            'ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,net_profit,finan_exp,'
            'c_fr_sale_sg,recp_tax_rends,n_depos_incr_fi,n_disp_subs_oth_biz,n_cashflow_act,'
            'st_cash_out_act,n_cashflow_inv_act,st_cash_out_inv_act,n_cashflow_fin_act,st_cash_out_fin_act,'
            'free_cashflow' 
        )
        params = {'ts_code': ts_code, 'period': period, 'fields': req_fields}
        df_cf = _fetch_latest_report_data(
            pro.cashflow, 
            result_period_field_name='end_date', 
            result_period_value=period,
            **params
        )
        if df_cf is None or df_cf.empty:
            return f"未找到 {stock_name} ({ts_code}) 在报告期 {period} 的现金流量表数据。"
        cf_data = df_cf.iloc[0]
        results = [f"--- {stock_name} ({ts_code}) {period} 现金流量表主要数据 ---"]
        latest_ann_date = cf_data.get('ann_date', 'N/A')
        results.append(f"(公告日期: {latest_ann_date})")
        def format_cf_value(key, label, unit="亿元"):
            if key in cf_data and pd.notna(cf_data[key]):
                value = cf_data[key]
                try:
                    numeric_value = pd.to_numeric(value)
                    if unit == "亿元": 
                        return f"{label}: {numeric_value / 100000000:.4f} {unit}"
                    else: 
                        return f"{label}: {numeric_value}"
                except (ValueError, TypeError):
                    return f"{label}: (值非数字: {value})"
            return f"{label}: 未提供"
        results.append(format_cf_value('c_fr_sale_sg', '销售商品、提供劳务收到的现金'))
        results.append(format_cf_value('n_cashflow_act', '经营活动产生的现金流量净额'))
        results.append(format_cf_value('n_cashflow_inv_act', '投资活动产生的现金流量净额'))
        results.append(format_cf_value('n_cashflow_fin_act', '筹资活动产生的现金流量净额'))
        results.append(format_cf_value('free_cashflow', '企业自由现金流量'))
        results.append(format_cf_value('net_profit', '净利润'))
        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_cash_flow: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取现金流量表失败：{str(e)}"

@mcp.tool()
def get_pledge_detail(ts_code: str) -> str:
    """
    获取指定股票的股权质押明细数据。

    参数:
        ts_code: 股票代码 (例如: 002277.SZ)
    """
    print(f"DEBUG: Tool get_pledge_detail called with ts_code: '{ts_code}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        # For pledge_detail, it returns a list of all pledge details, not typically tied to a single report period.
        # So, we call it directly and then sort if needed. _fetch_latest_report_data is not suitable here.
        df_detail = pro.pledge_detail(ts_code=ts_code)

        if df_detail.empty:
            return f"未找到 {stock_name} ({ts_code}) 的股权质押明细数据。"

        results = [f"--- {stock_name} ({ts_code}) 股权质押明细 (按最新公告日期、质押开始日降序) ---"]
        header = "股东名称 | 质押股份(万股) | 开始日 | 截止日 | 状态 | 公告日"
        results.append(header)
        results.append("-" * (len(header.replace(" | ", "")) + 2*header.count("|"))) # Dynamic separator length
        
        # Sort by announcement date, then by pledge start date, both descending
        df_detail_sorted = df_detail.sort_values(by=['ann_date', 'start_date'], ascending=[False, False])

        for _, row in df_detail_sorted.iterrows():
            holder = row.get('holder_name', 'N/A')
            pledge_amount_raw = row.get('pledge_amount') # Unit is Wan Gu (万股) directly from API
            pledge_amount_str = f"{pledge_amount_raw:.2f}" if pd.notna(pledge_amount_raw) else "N/A"
            
            start_date = row.get('start_date', 'N/A')
            end_date = row.get('end_date', 'N/A')
            status = row.get('status', 'N/A')
            ann_date = row.get('ann_date', 'N/A')
            results.append(f"{holder} | {pledge_amount_str} | {start_date} | {end_date} | {status} | {ann_date}")

        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_pledge_detail: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"获取股权质押明细失败：{str(e)}"

# --- Start of MCP SSE Workaround Integration ---
# Remove previous mounting attempt:
# # Mount the FastMCP SSE application.
# # The sse_app() method returns a Starlette application instance.
# mcp_sse_app = mcp.sse_app()
# app.mount("/sse", mcp_sse_app)
# print("DEBUG: FastMCP SSE app instance mounted at /sse", file=sys.stderr, flush=True)

MCP_BASE_PATH = "/sse" # The path where the MCP service will be available (e.g., https://.../sse)

print(f"DEBUG: Applying MCP SSE workaround for base path: {MCP_BASE_PATH}", file=sys.stderr, flush=True)

try:
    # 1. Initialize SseServerTransport.
    # The `messages_endpoint_path` is the path that the client will be told to POST messages to.
    # This path should be the full path, including our base path.
    # The SseServerTransport will handle POSTs to this path.
    messages_full_path = f"{MCP_BASE_PATH}/messages/"
    sse_transport = SseServerTransport(messages_full_path) # Directly pass the full path string
    print(f"DEBUG: SseServerTransport initialized; client will be told messages are at: {messages_full_path}", file=sys.stderr, flush=True)

    async def handle_mcp_sse_handshake(request: Request) -> None:
        """Handles the initial SSE handshake from the client."""
        print(f"DEBUG: MCP SSE handshake request received for: {request.url}", file=sys.stderr, flush=True)
        # request._send is a protected member, type: ignore is used.
        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send, # type: ignore 
        ) as (read_stream, write_stream):
            print(f"DEBUG: MCP SSE connection established for {MCP_BASE_PATH}. Starting McpServer.run.", file=sys.stderr, flush=True)
            # mcp is our FastMCP instance. _mcp_server is its underlying McpServer.
            await mcp._mcp_server.run(
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options(),
            )
            print(f"DEBUG: McpServer.run finished for {MCP_BASE_PATH}.", file=sys.stderr, flush=True)

    # 2. Add the route for the SSE handshake.
    # Clients will make a GET request to this endpoint to initiate the SSE connection.
    # e.g., GET https://mcp-api.chatbotbzy.top/sse
    app.add_route(MCP_BASE_PATH, handle_mcp_sse_handshake, methods=["GET"])
    print(f"DEBUG: MCP SSE handshake GET route added at: {MCP_BASE_PATH}", file=sys.stderr, flush=True)

    # 3. Mount the ASGI app from sse_transport to handle POSTed messages.
    # This will handle POST requests to https://mcp-api.chatbotbzy.top/sse/messages/
    app.mount(messages_full_path, sse_transport.handle_post_message)
    print(f"DEBUG: MCP SSE messages POST endpoint mounted at: {messages_full_path}", file=sys.stderr, flush=True)

    print(f"DEBUG: MCP SSE workaround for base path {MCP_BASE_PATH} applied successfully.", file=sys.stderr, flush=True)

except Exception as e_workaround:
    print(f"DEBUG: CRITICAL ERROR applying MCP SSE workaround: {str(e_workaround)}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
# --- End of MCP SSE Workaround Integration ---

if __name__ == "__main__":
    print("DEBUG: debug_server.py entering main section for FastAPI...", file=sys.stderr, flush=True)
    try:
        # mcp.run() # Commented out original MCP run
        print("DEBUG: Attempting to start uvicorn server...", file=sys.stderr, flush=True)
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
        print("DEBUG: uvicorn.run() completed (should not happen if server runs indefinitely).", file=sys.stderr, flush=True)
    except Exception as e_run:
        print(f"DEBUG: ERROR during uvicorn.run(): {e_run}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise
    except BaseException as be_run: # Catching BaseException like KeyboardInterrupt
        print(f"DEBUG: BASE EXCEPTION during uvicorn.run() (e.g., KeyboardInterrupt): {be_run}", file=sys.stderr, flush=True)
        # traceback.print_exc(file=sys.stderr) # Optional: might be too verbose for Ctrl+C
        # raise # Re-raise if you want the process to exit with an error code from the BaseException
    finally:
        print("DEBUG: debug_server.py finished.", file=sys.stderr, flush=True) 