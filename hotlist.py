import sys
from typing import Optional, Any, Callable
import tushare as ts
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv, set_key
from mcp.server.fastmcp import FastMCP
import os
import traceback
import uvicorn
from fastapi import FastAPI
from starlette.requests import Request
from mcp.server.sse import SseServerTransport

# --- Start of ENV_FILE and Helper Functions (Copied from server.py or made shared) ---
# It's better to have a shared utility module for these if you have multiple server files.
# For now, we'll include them directly for simplicity.

ENV_FILE_DIR_NAME = ".tushare_mcp"
ENV_FILE_NAME = ".env"

# Try to get home directory, fallback to current dir for restricted environments
try:
    APP_DATA_DIR = Path.home() / ENV_FILE_DIR_NAME
except RuntimeError: # pragma: no cover
    print(f"Warning: Could not determine home directory. Using current directory for .env file: {Path.cwd() / ENV_FILE_DIR_NAME}", file=sys.stderr, flush=True)
    APP_DATA_DIR = Path.cwd() / ENV_FILE_DIR_NAME

ENV_FILE = APP_DATA_DIR / ENV_FILE_NAME
print(f"DEBUG: hotlist.py: ENV_FILE path resolved to: {ENV_FILE}", file=sys.stderr, flush=True)

def init_env_file():
    """初始化环境变量文件"""
    print("DEBUG: hotlist.py: init_env_file called.", file=sys.stderr, flush=True)
    try:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not ENV_FILE.exists():
            ENV_FILE.touch()
        load_dotenv(ENV_FILE, override=True) # override=True ensures env vars from .env take precedence
        print(f"DEBUG: hotlist.py: load_dotenv(ENV_FILE) called. ENV_FILE exists: {ENV_FILE.exists()}", file=sys.stderr, flush=True)
    except Exception as e_fs:
        print(f"DEBUG: hotlist.py: ERROR in init_env_file filesystem operations: {str(e_fs)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)

def get_tushare_token() -> Optional[str]:
    """获取Tushare token"""
    print("DEBUG: hotlist.py: get_tushare_token called.", file=sys.stderr, flush=True)
    init_env_file() # Ensure .env is loaded
    token = os.getenv("TUSHARE_TOKEN")
    print(f"DEBUG: hotlist.py: get_tushare_token: os.getenv result: {'TOKEN_FOUND' if token else 'NOT_FOUND'}", file=sys.stderr, flush=True)
    return token

def set_tushare_token_in_env(token: str):
    """设置Tushare token到.env文件并加载到当前环境"""
    print(f"DEBUG: hotlist.py: set_tushare_token_in_env called with token: {'********' if token else 'None'}", file=sys.stderr, flush=True)
    init_env_file() # Ensure directory exists
    try:
        set_key(ENV_FILE, "TUSHARE_TOKEN", token, quote_mode='never')
        os.environ["TUSHARE_TOKEN"] = token # Also set in current process's env
        print(f"DEBUG: hotlist.py: Token set in {ENV_FILE} and os.environ.", file=sys.stderr, flush=True)
    except Exception as e_set_token:
        print(f"DEBUG: hotlist.py: ERROR in set_tushare_token_in_env: {str(e_set_token)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)

# --- End of Core Token Management Functions ---

# --- MCP Instance Creation ---
try:
    mcp = FastMCP("Tushare Hotlist Tools")
    print("DEBUG: hotlist.py: FastMCP instance created for Tushare Hotlist Tools.", file=sys.stderr, flush=True)
except Exception as e:
    print(f"DEBUG: hotlist.py: ERROR creating FastMCP: {e}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    raise
# --- End of MCP Instance Creation ---

# --- FastAPI App Creation (similar to server.py) ---
app = FastAPI(
    title="Tushare Hotlist MCP API",
    description="Remote API for Tushare Hotlist MCP tools via FastAPI.",
    version="0.0.1" # Or a suitable version
)

@app.get("/")
async def read_root():
    return {"message": "Hello World - Tushare Hotlist MCP API is running!"}
# --- End of FastAPI App Creation ---

# --- Tushare KPL Concept Tool Definition ---
@mcp.tool(
    name="hotlist_mcp_get_kpl_concept_list",
    description="获取开盘啦概念题材列表。可以根据交易日期、题材代码或题材名称进行筛选。"
)
def get_kpl_concept_list(
    trade_date: str = "",  # Changed from Optional[str] = None
    ts_code: str = "",     # Changed from Optional[str] = None
    name: str = ""         # Changed from Optional[str] = None
) -> str:
    """
    获取开盘啦概念题材列表。

    参数:
        trade_date: 交易日期 (YYYYMMDD格式, 例如: 20241014)
        ts_code: 题材代码 (xxxxxx.KP格式, 例如: 000111.KP)
        name: 题材名称 (例如: 化债概念)
    """
    # Log received parameters for debugging
    print(f"DEBUG: hotlist.py: get_kpl_concept_list called with trade_date='{trade_date}', ts_code='{ts_code}', name='{name}'", file=sys.stderr, flush=True)

    token = get_tushare_token()
    if not token:
        return "错误: Tushare token未配置。请先在 .tushare_mcp/.env 文件中配置 TUSHARE_TOKEN。"
    
    try:
        pro = ts.pro_api(token)
        if pro is None: # Should not happen if token is valid, but good practice
             raise Exception("Tushare API 初始化失败，请检查Token是否有效或网络连接。")

        api_params = {}
        if trade_date: # Only add if not an empty string
            api_params['trade_date'] = trade_date
        if ts_code:    # Only add if not an empty string
            api_params['ts_code'] = ts_code
        if name:       # Only add if not an empty string
            api_params['name'] = name
        
        # The Tushare doc for kpl_concept says all parameters are optional.
        # If api_params is empty, Tushare might return latest or all concepts, or an error.
        # It's generally good to inform the user if no specific filters are applied,
        # or handle it based on expected API behavior.
        if not api_params: 
            print("DEBUG: hotlist.py: No specific parameters provided to get_kpl_concept_list. Tushare API will use its default behavior.", file=sys.stderr, flush=True)
            # Depending on Tushare's behavior for kpl_concept with no params, 
            # you might want to return a message or fetch default data.
            # For now, let Tushare handle it, or return a message if it errors.
            # return "提示: 未提供具体查询参数，将尝试获取默认的开盘啦题材数据。" # Example message

        print(f"DEBUG: hotlist.py: Calling pro.kpl_concept with params: {api_params}", file=sys.stderr, flush=True)
        df = pro.kpl_concept(**api_params)

        if df.empty:
            query_desc = f"查询参数: trade_date='{trade_date}', ts_code='{ts_code}', name='{name}'" if api_params else "无特定查询参数"
            return f"未找到符合条件的开盘啦题材数据。{query_desc}"

        results = [f"--- 开盘啦题材库查询结果 ---"]
        if api_params:
            param_strings = [f"{k}='{v}'" for k, v in api_params.items()]
            results[0] += f" (查询: {', '.join(param_strings)})"
        else:
            results[0] += " (默认/最新)"

        # Limit output for brevity, e.g., top 20 results
        df_limited = df.head(20)

        for _, row in df_limited.iterrows():
            info_parts = [
                f"交易日期: {row.get('trade_date', 'N/A')}",
                f"题材代码: {row.get('ts_code', 'N/A')}",
                f"题材名称: {row.get('name', 'N/A')}",
                f"涨停数量: {row.get('z_t_num') if pd.notna(row.get('z_t_num')) else 'N/A'}", # z_t_num can be None
                f"排名上升位数: {row.get('up_num', 'N/A')}"
            ]
            results.append("\n".join(info_parts))
            results.append("------------------------")
        
        if len(df) > len(df_limited):
            results.append(f"注意: 结果超过 {len(df_limited)} 条，仅显示前 {len(df_limited)} 条。共有 {len(df)} 条数据。")

        return "\n".join(results)

    except Exception as e:
        error_msg_detail = f"trade_date='{trade_date}', ts_code='{ts_code}', name='{name}'"
        error_msg = f"获取开盘啦题材库数据失败: {str(e)}. 查询参数: {error_msg_detail}"
        print(f"DEBUG: hotlist.py: ERROR in get_kpl_concept_list: {error_msg}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        if "积分" in str(e) or "credits" in str(e).lower() or "权限" in str(e):
             return f"获取开盘啦题材库数据失败：Tushare积分不足或无权限访问此接口。({str(e)})"
        return error_msg

# --- End of Tushare KPL Concept Tool Definition ---

# --- Start of MCP SSE Workaround Integration (copied and adapted from server.py) ---
MCP_BASE_PATH = "/sse" # The path where the MCP service will be available

print(f"DEBUG: hotlist.py: Applying MCP SSE workaround for base path: {MCP_BASE_PATH}", file=sys.stderr, flush=True)

try:
    messages_full_path = f"{MCP_BASE_PATH}/messages/"
    sse_transport = SseServerTransport(messages_full_path)
    print(f"DEBUG: hotlist.py: SseServerTransport initialized; client will be told messages are at: {messages_full_path}", file=sys.stderr, flush=True)

    async def handle_mcp_sse_handshake(request: Request) -> None:
        print(f"DEBUG: hotlist.py: MCP SSE handshake request received for: {request.url}", file=sys.stderr, flush=True)
        async with sse_transport.connect_sse(
            request.scope,
            request.receive,
            request._send, # type: ignore 
        ) as (read_stream, write_stream):
            print(f"DEBUG: hotlist.py: MCP SSE connection established for {MCP_BASE_PATH}. Starting McpServer.run.", file=sys.stderr, flush=True)
            # Ensure 'mcp' here refers to the FastMCP instance created in hotlist.py
            await mcp._mcp_server.run(
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options(),
            )
            print(f"DEBUG: hotlist.py: McpServer.run finished for {MCP_BASE_PATH}.", file=sys.stderr, flush=True)

    app.add_route(MCP_BASE_PATH, handle_mcp_sse_handshake, methods=["GET"])
    print(f"DEBUG: hotlist.py: MCP SSE handshake GET route added at: {MCP_BASE_PATH}", file=sys.stderr, flush=True)

    app.mount(messages_full_path, sse_transport.handle_post_message)
    print(f"DEBUG: hotlist.py: MCP SSE messages POST endpoint mounted at: {messages_full_path}", file=sys.stderr, flush=True)

    print(f"DEBUG: hotlist.py: MCP SSE workaround for base path {MCP_BASE_PATH} applied successfully.", file=sys.stderr, flush=True)

except Exception as e_workaround:
    print(f"DEBUG: hotlist.py: CRITICAL ERROR applying MCP SSE workaround: {str(e_workaround)}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
# --- End of MCP SSE Workaround Integration ---

# Placeholder for main execution block if this file is run directly
if __name__ == "__main__":
    print("DEBUG: hotlist.py entering main section to start Uvicorn server...", file=sys.stderr, flush=True)
    try:
        print("DEBUG: hotlist.py: Starting Uvicorn server for Hotlist MCP (FastAPI app) on port 8001...", file=sys.stderr, flush=True)
        # Run the FastAPI app instance 'app', not 'mcp' directly
        uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
        print("DEBUG: hotlist.py: Uvicorn server for Hotlist MCP stopped.", file=sys.stderr, flush=True)
    except Exception as e_server:
        print(f"ERROR: hotlist.py: Failed to start or run Uvicorn server: {str(e_server)}", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        if isinstance(e_server, ImportError) and "uvicorn" in str(e_server).lower():
             print("Hint: Ensure 'uvicorn' is installed. You can install it with: pip install uvicorn[standard]", file=sys.stderr, flush=True)
    print("DEBUG: hotlist.py finished main section execution.", file=sys.stderr, flush=True)
