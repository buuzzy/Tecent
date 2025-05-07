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
def get_financial_indicator(ts_code: str, period: str) -> str:
    """
    获取指定股票在特定报告期的主要财务指标。

    参数:
        ts_code: 股票代码 (例如: 600348.SH)
        period: 报告期 (YYYYMMDD格式, 例如: 20240930 代表 2024年三季报)
    """
    print(f"DEBUG: Tool get_financial_indicator called with ts_code: '{ts_code}', period: '{period}'.", file=sys.stderr, flush=True)
    if not get_tushare_token():
        return "请先配置Tushare token"
    try:
        pro = ts.pro_api()
        stock_name = _get_stock_name(pro, ts_code)
        req_fields = 'ts_code,ann_date,end_date,grossprofit_margin,netprofit_margin,roe_yearly,roe_waa,roe_dt,n_income_attr_p,total_revenue,rd_exp,n_income_attr_p_yoy,dtprofit_yoy,tr_yoy,or_yoy,bps'
        df = pro.fina_indicator(ts_code=ts_code, period=period, fields=req_fields)
        if df.empty:
            return f"未找到 {stock_name} ({ts_code}) 在 {period} 的财务指标数据。请检查代码和报告期是否正确。"
        indicator_data = df.iloc[0]
        results = [f"--- {stock_name} ({ts_code}) {period} 财务指标 ---"]
        def format_indicator(key, label, unit="%"):
            if key in indicator_data and pd.notna(indicator_data[key]):
                value = indicator_data[key]
                try:
                    numeric_value = pd.to_numeric(value)
                    if unit == "亿元":
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
        results.append(format_indicator('grossprofit_margin', '销售毛利率'))
        results.append(format_indicator('netprofit_margin', '销售净利率'))
        results.append(format_indicator('roe_yearly', '净资产收益率(ROE, 年化)'))
        results.append(format_indicator('roe_waa', '净资产收益率(ROE, 加权平均)'))
        results.append(format_indicator('roe_dt', '净资产收益率(ROE, 扣非)'))
        results.append(format_indicator('n_income_attr_p', '归属母公司净利润', unit='亿元'))
        results.append(format_indicator('total_revenue', '营业总收入', unit='亿元'))
        results.append(format_indicator('rd_exp', '研发费用', unit='亿元'))
        results.append(format_indicator('n_income_attr_p_yoy', '归母净利润同比增长率'))
        results.append(format_indicator('dtprofit_yoy', '扣非净利润同比增长率'))
        results.append(format_indicator('tr_yoy', '营业总收入同比增长率'))
        results.append(format_indicator('or_yoy', '营业收入同比增长率'))
        results.append(format_indicator('bps', '每股净资产', unit='元'))
        if len(results) <= 1: 
            return f"从 {stock_name} ({ts_code}) {period} 的财务指标数据中未能提取到常用指标，可能接口返回字段有变化或数据缺失。检查请求字段：{req_fields}"
        return "\\n".join(results)
    except Exception as e:
        print(f"DEBUG: ERROR in get_financial_indicator: {str(e)}", file=sys.stderr, flush=True)
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

if __name__ == "__main__":
    print("DEBUG: debug_server.py entering main...", file=sys.stderr, flush=True)
    try:
        mcp.run()
        print("DEBUG: mcp.run() completed (should not happen).", file=sys.stderr, flush=True)
    except Exception as e_run:
        print(f"DEBUG: ERROR during mcp.run(): {e_run}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise
    except BaseException as be_run:
        print(f"DEBUG: BASE EXCEPTION during mcp.run(): {be_run}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise
    finally:
        print("DEBUG: debug_server.py finished.", file=sys.stderr, flush=True) 