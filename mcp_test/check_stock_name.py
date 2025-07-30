import tushare as ts
import pandas as pd
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import argparse
import traceback

# --- Start of Token Management (reused from server.py) ---
ENV_FILE = Path.home() / ".tushare_mcp" / ".env"

def init_env_file():
    """
    初始化环境文件目录和文件，确保它们存在。
    """
    if not ENV_FILE.parent.exists():
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch()
    load_dotenv(ENV_FILE)

def get_tushare_token() -> str | None:
    """
    从环境变量文件中获取 Tushare token。
    """
    init_env_file()
    return os.getenv("TUSHARE_TOKEN")
# --- End of Token Management ---


class StockNameConverter:
    """
    一个专门处理A股和港股股票代码与名称相互转换的类。
    """
    def __init__(self, token: str):
        if not token:
            raise ValueError("初始化需要有效的 Tushare token。")
        print("正在连接 Tushare API...", file=sys.stderr)
        self.pro = ts.pro_api(token)
        self._unified_df = None
        self._load_data()

    def _load_data(self):
        """
        从Tushare加载A股和港股的完整列表，并将其合并与缓存。
        """
        print("正在加载A股和港股列表数据，请稍候...", file=sys.stderr)
        try:
            # Fetch all listing statuses for A-shares
            ashare_df = self.pro.stock_basic(fields='ts_code,name')
            # Fetch all listing statuses for HK-shares to be comprehensive
            hk_l = self.pro.hk_basic(list_status='L', fields='ts_code,name')
            hk_d = self.pro.hk_basic(list_status='D', fields='ts_code,name')
            hk_p = self.pro.hk_basic(list_status='P', fields='ts_code,name')
            
            self._unified_df = pd.concat([ashare_df, hk_l, hk_d, hk_p], ignore_index=True)
            self._unified_df.drop_duplicates(subset=['ts_code'], keep='first', inplace=True)
            print(f"数据加载完成，共计 {len(self._unified_df)} 条记录。", file=sys.stderr)
        except Exception as e:
            print(f"从 Tushare 加载数据时发生错误: {e}", file=sys.stderr)
            sys.exit(1)

    def _normalize_code(self, code_query: str) -> list[str]:
        """
        将各种用户输入的代码格式标准化为Tushare的官方格式列表。
        例如: 'sz000001' -> ['000001.SZ']
              '000001'   -> ['000001.SZ', '000001.SH', '000001.HK']
              'hk00700'  -> ['00700.HK']
        """
        query = code_query.strip().lower()
        if query.startswith('sz') and '.' not in query:
            return [f"{query[2:]}.SZ".upper()]
        if query.startswith('sh') and '.' not in query:
            return [f"{query[2:]}.SH".upper()]
        if query.startswith('hk') and '.' not in query:
            # Tushare HK codes are 5 digits, 0-padded.
            return [f"{query[2:].zfill(5)}.HK".upper()]

        # 处理纯数字输入，可能对应A股或港股
        if query.isdigit():
            return [
                f"{query}.SZ".upper(),
                f"{query}.SH".upper(),
                f"{query.zfill(5)}.HK".upper() # 港股代码通常为5位
            ]

        # 默认输入已经是标准格式或需要直接传递
        return [query.upper()]

    def _format_code_for_display(self, ts_code: str) -> str:
        """
        将Tushare的官方代码格式化为用户要求的显示格式。
        例如: '000001.SZ' -> 'sz000001'
              '00700.HK' -> 'hk00700'
        """
        if ts_code.endswith('.SZ'):
            return f"sz{ts_code[:-3]}"
        if ts_code.endswith('.SH'):
            return f"sh{ts_code[:-3]}"
        if ts_code.endswith('.HK'):
            # Reformat to match the input file style like 'hk00700'
            return f"hk{ts_code[:-3]}"
        return ts_code

    def convert(self, query: str) -> str:
        """
        执行转换的核心方法。
        先按名称搜索，如果找不到，再按代码搜索。
        """
        query = query.strip()
        
        # 1. 按名称精确搜索
        result_df = self._unified_df[self._unified_df['name'] == query]
        if not result_df.empty:
            name = result_df.iloc[0]['name']
            code = result_df.iloc[0]['ts_code']
            return f"{name}({self._format_code_for_display(code)})"
            
        # 2. 如果按名称找不到，则尝试按代码搜索
        possible_codes = self._normalize_code(query)
        result_df = self._unified_df[self._unified_df['ts_code'].isin(possible_codes)]
        
        if not result_df.empty:
            # 对于纯数字的模糊输入，可能匹配到多个，按SZ, SH, HK的优先级返回第一个
            result_df['ts_code'] = pd.Categorical(result_df['ts_code'], categories=possible_codes, ordered=True)
            result_df = result_df.sort_values('ts_code')
            
            name = result_df.iloc[0]['name']
            code = result_df.iloc[0]['ts_code']
            return f"{name}({self._format_code_for_display(code)})"

        return f"查询失败：未找到与 '{query}' 匹配的股票。"


def main():
    """
    主函数，用于处理命令行调用。
    """
    parser = argparse.ArgumentParser(
        description="A/H股股票代码与名称转换工具。支持单个查询或批量文件处理。输出格式: stock_name(stock_code)。"
    )
    # Make query optional and add a file argument
    parser.add_argument("query", nargs='?', default=None, type=str, help="单个股票代码或名称。如果使用--file选项，则忽略此参数。")
    parser.add_argument("-f", "--file", type=str, help="包含股票代码/名称列表的文件的路径，每行一个。")
    
    args = parser.parse_args()

    if not args.query and not args.file:
        parser.print_help()
        sys.exit("\n错误：请提供单个查询或使用 --file 指定一个文件。")

    token = get_tushare_token()
    if not token:
        print("错误：Tushare token 未找到。请确保 ~/.tushare_mcp/.env 文件中已配置。", file=sys.stderr)
        sys.exit(1)

    try:
        # Initialize converter once to leverage caching
        converter = StockNameConverter(token)

        if args.file:
            print(f"--- 开始处理文件: {args.file} ---", file=sys.stderr)
            try:
                with open(args.file, 'r', encoding='utf-8') as f:
                    for line in f:
                        query = line.strip()
                        if query: # Skip empty lines
                            result = converter.convert(query)
                            print(result)
            except FileNotFoundError:
                print(f"错误: 文件未找到 -> {args.file}", file=sys.stderr)
                sys.exit(1)
            print(f"--- 文件处理完成: {args.file} ---", file=sys.stderr)

        elif args.query:
            result = converter.convert(args.query)
            print(result)

    except Exception as e:
        print(f"发生未知错误: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 