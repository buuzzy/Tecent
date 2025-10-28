import logging
import functools
import traceback
import sys
from typing import Any, Callable

# 配置全局日志记录器
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 创建日志处理器
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.INFO)

# 创建日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# 添加处理器到日志记录器
logger.addHandler(handler)

def log_debug(message: str):
    """统一的日志记录函数"""
    logger.info(message)

def handle_exception(func: Callable[..., Any]) -> Callable[..., Any]:
    """统一的异常处理装饰器"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            traceback.print_exc(file=sys.stderr)
            # 根据函数名返回相应的错误信息
            if func.__name__.startswith('get_') or func.__name__.startswith('search_'):
                return f"查询失败：{str(e)}"
            elif func.__name__.startswith('setup_') or func.__name__.startswith('set_'):
                return f"设置失败：{str(e)}"
            else:
                return f"操作失败：{str(e)}"
    return wrapper