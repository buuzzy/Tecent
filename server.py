import sys
import traceback
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import tushare as ts
import pandas as pd
import uvicorn  # <-- 关键修复：添加此行导入 uvicorn
from dotenv import load_dotenv, set_key
from fastapi import FastAPI, HTTPException, Body

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from mcp.server.sse import SseServerTransport

# --- Environment and Helper Functions ---
ENV_FILE = Path("/tmp") / ".tushare_env"

def init_env_file():
    """Initializes the environment file and its directory."""
    try:
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not ENV_FILE.exists():
            ENV_FILE.touch()
        load_dotenv(ENV_FILE)
    except Exception as e:
        print(f"ERROR in init_env_file: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

def get_tushare_token() -> Optional[str]:
    """Retrieves the Tushare token from the environment."""
    init_env_file()
    return os.getenv("TUSHARE_TOKEN")

def set_tushare_token(token: str):
    """Sets the Tushare token in the environment file and tushare config."""
    init_env_file()
    try:
        set_key(ENV_FILE, "TUSHARE_TOKEN", token)
        ts.set_token(token)
    except Exception as e:
        print(f"ERROR in set_tushare_token: {e}", file=sys.stderr)

def _get_stock_name(pro_api_instance, ts_code: str) -> str:
    """Helper function to get stock name from ts_code."""
    if not pro_api_instance:
        return ts_code
    try:
        df_basic = pro_api_instance.stock_basic(ts_code=ts_code, fields='ts_code,name')
        if not df_basic.empty:
            return df_basic.iloc[0]['name']
    except Exception as e:
        print(f"Warning: Failed to get stock name for {ts_code}: {e}", file=sys.stderr)
    return ts_code

# --- MCP and FastAPI App Initialization ---
try:
    mcp = FastMCP("Tushare Tools New")
except Exception as e:
    print(f"ERROR creating FastMCP: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    raise

app = FastAPI(
    title="Tushare MCP API (New)",
    description="A streamlined remote API for Tushare MCP tools via FastAPI.",
    version="0.1.0"
)

# --- Core Tools ---

@mcp.prompt()
def configure_token() -> str:
    """Provides a prompt template for configuring the Tushare token."""
    return """请提供您的Tushare API token。
您可以在 https://tushare.pro/user/token 获取您的token。
如果您还没有Tushare账号，请先在 https://tushare.pro/register 注册。

请输入您的token:"""

@mcp.tool()
def setup_tushare_token(token: str) -> str:
    """
    Sets and verifies the Tushare API token.
    """
    print(f"DEBUG: Tool setup_tushare_token called.", file=sys.stderr)
    if not token or not isinstance(token, str):
        return "Token无效，请输入一个有效的字符串。"
    try:
        set_tushare_token(token)
        # Verify the token by making a simple API call
        ts.pro_api(token)
        return "Token配置成功！您现在可以使用Tushare的API功能了。"
    except Exception as e:
        print(f"ERROR in setup_tushare_token: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"Token配置失败：{e}"

@mcp.tool()
def check_token_status() -> str:
    """
    Checks the status and validity of the configured Tushare token.
    """
    print("DEBUG: Tool check_token_status called.", file=sys.stderr)
    token = get_tushare_token()
    if not token:
        return "未配置Tushare token。请使用 setup_tushare_token 来设置您的token。"
    
    try:
        # Explicitly use the token to verify it
        ts.pro_api(token)
        return "Token配置正常，可以使用Tushare API。"
    except Exception as e:
        print(f"ERROR in check_token_status: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"Token无效或已过期。错误信息: {e}"

@mcp.tool()
def get_stock_basic_info(ts_code: str = "", name: str = "") -> str:
    """
    获取股票基本信息

    参数:
        ts_code: 股票代码（如：000001.SZ）
        name: 股票名称（如：平安银行）
    """
    print(f"DEBUG: Tool get_stock_basic_info called with ts_code: '{ts_code}', name: '{name}'.", file=sys.stderr)
    token_value = get_tushare_token()
    if not token_value:
        return "错误：Tushare token 未配置或无法获取。请使用 setup_tushare_token 配置。"

    try:
        pro = ts.pro_api(token_value)
        query_params = {}
        if ts_code:
            query_params['ts_code'] = ts_code
        if name:
            query_params['name'] = name

        # select a compact set of useful fields
        fields = 'ts_code,name,area,industry,list_date,market,exchange,list_status,delist_date'
        df = pro.stock_basic(**query_params, fields=fields)

        if df is None or df.empty:
            return "未找到符合条件的股票"

        results = []
        # limit output size to avoid extremely long responses
        df_limited = df.head(50)
        for _, row in df_limited.iterrows():
            parts = []
            if 'ts_code' in row and pd.notna(row.get('ts_code')):
                parts.append(f"股票代码: {row['ts_code']}")
            if 'name' in row and pd.notna(row.get('name')):
                parts.append(f"股票名称: {row['name']}")
            optional = {
                'area': '所属地区', 'industry': '所属行业', 'list_date': '上市日期',
                'market': '市场类型', 'exchange': '交易所', 'list_status': '上市状态', 'delist_date': '退市日期'
            }
            for k, label in optional.items():
                if k in row and pd.notna(row.get(k)):
                    parts.append(f"{label}: {row[k]}")
            parts.append("------------------------")
            results.append("\n".join(parts))

        if len(df) > 50:
            results.append("注意: 结果超过50条，仅显示前50条。如需精确查找请提供 ts_code 或更具体的 name。")

        return "\n".join(results)

    except Exception as e:
        print(f"ERROR in get_stock_basic_info: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return f"查询失败：{e}"

@mcp.tool()
def get_money_flow_for_past_days(ts_code: str, days: int = 30) -> str:
    """
    获取指定股票在过去N天内的累计资金净流入情况。
    注意：此接口需要2000 Tushare积分。

    参数:
        ts_code: 股票代码 (例如: 000001.SZ)
        days: 查询最近多少天的数据 (默认为30天)
    """
    print(f"DEBUG: Tool get_money_flow_for_past_days called with ts_code: '{ts_code}', days: {days}.", file=sys.stderr, flush=True)
    token_value = get_tushare_token()
    if not token_value:
        return "错误：Tushare token 未配置。请先进行配置。"

    try:
        pro = ts.pro_api(token_value)
        stock_name = _get_stock_name(pro, ts_code)

        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        end_date_str = end_date.strftime('%Y%m%d')
        start_date_str = start_date.strftime('%Y%m%d')

        # 调用API
        df = pro.moneyflow(ts_code=ts_code, start_date=start_date_str, end_date=end_date_str)

        if df.empty:
            return f"在 {start_date_str} 到 {end_date_str} 期间未找到 {stock_name} ({ts_code}) 的资金流向数据。"

        # 计算总净流入
        total_net_vol = df['net_mf_vol'].sum()
        total_net_amount = df['net_mf_amount'].sum()

        # 格式化输出 (已移除总结部分)
        results = [
            f"--- {stock_name} ({ts_code}) 最近 {days} 天资金流向统计 ---",
            f"查询区间: {start_date_str} 至 {end_date_str}",
            f"累计净流入量: {total_net_vol:,.0f} 手",
            f"累计净流入额: {total_net_amount:,.2f} 万元"
        ]

        return "\n".join(results)

    except Exception as e:
        print(f"DEBUG: ERROR in get_money_flow_for_past_days: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"查询资金流向失败：{str(e)}"


@mcp.tool()
def get_top10_holders(ts_code: str, period: str = None) -> str:
    """
    获取上市公司前十大股东数据，包括持有数量和占总股本比例。
    注意：此接口需要2000 Tushare积分。

    参数:
        ts_code: 股票代码 (例如: 600000.SH)
        period: 报告期 (YYYYMMDD格式，例如: 20231231)。如果未提供，则获取最新数据。
    """
    print(f"DEBUG: Tool get_top10_holders called with ts_code: '{ts_code}', period: {period}.", file=sys.stderr, flush=True)
    token_value = get_tushare_token()
    if not token_value:
        return "错误：Tushare token 未配置。请先进行配置。"

    try:
        pro = ts.pro_api(token_value)
        stock_name = _get_stock_name(pro, ts_code)

        # 准备API参数
        params = {'ts_code': ts_code}
        if period:
            params['period'] = period

        # 调用API
        df = pro.top10_holders(**params)

        if df.empty:
            return f"未找到 {stock_name} ({ts_code}) 的前十大股东数据。"

        # 获取最新的报告期
        latest_end_date = df['end_date'].iloc[0]
        df_latest = df[df['end_date'] == latest_end_date]

        # 格式化输出
        header = f"--- {stock_name} ({ts_code}) 报告期 {latest_end_date} 前十大股东 ---"
        results = [header]
        for _, row in df_latest.iterrows():
            holder_info = (
                f"股东名称: {row['holder_name']}\n"
                f"  - 持有数量: {row['hold_amount']:,.0f} 股\n"
                f"  - 占总股本比例: {row['hold_ratio']:.2f}%"
            )
            results.append(holder_info)

        return "\n".join(results)

    except Exception as e:
        print(f"DEBUG: ERROR in get_top10_holders: {str(e)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        return f"查询前十大股东失败：{str(e)}"


# --- FastAPI Endpoints ---
@app.get("/")
async def read_root():
    return {"message": "Hello World - Tushare MCP API (New) is running!"}

@app.post("/tools/setup_tushare_token", summary="Setup Tushare API token")
async def api_setup_tushare_token(payload: dict = Body(...)):
    """
    Sets the Tushare API token via a REST endpoint.
    Expects a JSON payload: {"token": "your_actual_token_here"}
    """
    token = payload.get("token")
    if not token or not isinstance(token, str):
        raise HTTPException(
            status_code=400, 
            detail="Missing or invalid 'token' in payload. Expected a JSON object with a 'token' string."
        )

    try:
        # Call the original tool function
        result_message = setup_tushare_token(token=token)
        if "配置成功" in result_message:
            return {"status": "success", "message": result_message}
        else:
            # Propagate the failure message from the tool
            raise HTTPException(status_code=401, detail=result_message)
    except Exception as e:
        error_message = f"An unexpected error occurred while setting up the token: {e}"
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status_code=500, detail=error_message)

# --- Start of MCP SSE Workaround Integration ---
MCP_BASE_PATH = "/mcp" # The path where the MCP service will be available

try:
    messages_full_path = f"{MCP_BASE_PATH}/messages/"
    sse_transport = SseServerTransport(messages_full_path)

    async def handle_mcp_sse_handshake(request: Request) -> None:
        """Handles the initial SSE handshake from the client."""
        # request._send is a protected member, type: ignore is used.
        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send, # type: ignore
        ) as (read_stream, write_stream):
            await mcp._mcp_server.run(
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options(),
            )

    app.add_route(MCP_BASE_PATH, handle_mcp_sse_handshake, methods=["GET"])
    app.mount(messages_full_path, sse_transport.handle_post_message)

except Exception as e_workaround:
    print(f"DEBUG: CRITICAL ERROR applying MCP SSE workaround: {str(e_workaround)}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
# --- End of MCP SSE Workaround Integration ---


# --- Server Execution ---
if __name__ == "__main__":
    # To run this server: uvicorn server.py:app --host 0.0.0.0 --port 8000 --reload
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)