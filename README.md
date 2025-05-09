# <Tushare_MCP>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<该项目基于zhewenzhang（OJO）的开源项目 tushare_MCP 进行了优化。原本是想校验金融资讯中的数据是否准确，后续认为能做为一个 MCP 提供服务>

## ✨ 主要特性

*   **全面的股票数据查询：**
    *   提供股票基本信息、实时行情（日线、指标）、历史股价变动查询。
    *   支持通过股票代码或名称进行智能搜索。
*   **深度财务数据分析：**
    *   获取上市公司详细财务报表，包括利润表、资产负债表、现金流量表。
    *   查询关键财务指标数据。
*   **指数与市场数据覆盖：**
    *   支持主流指数的基本信息查询、成分股获取及全球指数行情。
*   **股东及公司基本面信息：**
    *   查询股东户数、十大股东信息、每日股本市值以及股权质押明细。
*   **安全的 Token 管理与便捷的 API 访问：**
    *   提供安全的 Tushare Token 配置与状态检查机制。
    *   通过 FastAPI 封装，提供标准化的 HTTP API 接口，方便与其他应用集成。
*   **MCP 协议兼容：**
    *   保持与 MCP 协议的兼容性，支持与特定 AI 助手平台的集成。
*   继承自原版 `tushare_MCP` 的核心工具交互逻辑（见下方致谢）。

## 🚀 快速开始

### 环境要求

*   Python 3.8+
*   有效的 Tushare Pro 账号和 API Token (获取地址: [Tushare Pro Token 申请页面](https://tushare.pro/user/token)，请自行注册)

### 安装步骤

1.  **克隆仓库：**
    ```bash
    git clone <你的 GitHub 仓库 HTTPS 或 SSH链接>
    cd <你的项目目录名>
    ```

2.  **创建并激活虚拟环境 (推荐)：**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate   # Windows
    ```

3.  **安装依赖：**
    ```bash
    pip install -r requirements.txt
    ```

### 配置 Tushare Token

本项目需要 Tushare API Token 才能正常工作。你有以下几种方式配置 Token：

1.  **通过 `.env` 文件 (推荐，安全)：**
    *   在项目根目录下创建一个名为 `.env` 的文件 (此文件已被 `.gitignore` 忽略，不会提交到版本库)。
    *   在 `.env` 文件中添加以下内容，并将 `<你的TUSHARE_TOKEN>` 替换为你的真实 Token：
        ```
        TUSHARE_TOKEN=<你的TUSHARE_TOKEN>
        ```
2.  **通过环境变量：**
    在运行 `server.py` 之前，设置名为 `TUSHARE_TOKEN` 的环境变量。
    ```bash
    export TUSHARE_TOKEN="<你的TUSHARE_TOKEN>" # Linux/macOS
    # set TUSHARE_TOKEN="<你的TUSHARE_TOKEN>"   # Windows (cmd)
    # $env:TUSHARE_TOKEN="<你的TUSHARE_TOKEN>" # Windows (PowerShell)
    ```

### 启动服务

```bash
python server.py
```
服务将在 `<默认端口号，例如：8000，或根据你的 server.py 实际情况填写>` 启动。

## 📖 使用示例 (API 端点)

<这里详细列出你的项目提供的 API 端点、请求方法、参数以及示例响应。如果与原版 tushare_MCP 的 API 有变化，务必清晰说明。>

### 示例 1: 获取股票基本信息
```
GET /stock_basic?ts_code=000001.SZ
```
或
```
GET /stock_basic?name=平安银行
```

### 示例 2: <你修改或新增的 API 功能>
```
<请求方法> <端点路径>?<参数>
```

<...>

## 🐳 Docker 支持 (可选)

如果你的项目支持 Docker (看起来是的，因为有 `Dockerfile`)：
```bash
# 构建 Docker 镜像
docker build -t <你的镜像名> .

# 运行 Docker 容器 (记得传递 TUSHARE_TOKEN)
docker run -e TUSHARE_TOKEN="<你的TUSHARE_TOKEN>" -p <主机端口>:<容器端口> <你的镜像名>
```

## 🛠️ 与 MCP 平台集成 (smithery.yaml)

项目包含 `smithery.yaml` 文件，用于与支持模型上下文协议 (MCP) 的平台（例如 Claude 的早期工具使用方式）集成。它定义了项目的构建和启动配置，依赖于 `TUSHARE_TOKEN` 环境变量的设置。

## 🤝 贡献指南

<如果你希望他人贡献，可以添加此部分。>
欢迎提交 Issues 和 Pull Requests！在提交代码前，请确保：
*   代码遵循 PEP8 规范。
*   添加了必要的测试。
*   更新了相关文档。

## ❤️ 致谢 (Acknowledgements)

本项目基于 [zhewenzhang/tushare_MCP](https://github.com/zhewenzhang/tushare_MCP) 项目进行了修改和扩展。非常感谢原作者的开源贡献！

原项目核心功能包括：
*   股票基础信息查询
*   智能股票搜索
*   财务报表分析 (部分继承或修改)
*   安全的Token管理 (部分继承或修改)

## 📄 开源许可证 (License)

本项目采用 **MIT License**。详情请见 [LICENSE](LICENSE) 文件。

## 🎯 使用场景

1. **投资研究**
   ```
   "帮我查找所有新能源相关的股票"
   "查询比亚迪的基本信息"
   "获取平安银行2023年的利润表"
   ```

2. **财务分析**
   ```
   "查看腾讯控股最新一期合并报表"
   "对比阿里巴巴近三年的利润变化"
   "分析小米集团的季度利润趋势"
   ```

3. **行业分析**
   ```
   "列出所有医药行业的股票"
   "查找深圳地区的科技公司"
   ```

4. **报表查询**
   ```
   "查询平安银行2023年第一季度的利润表"
   "获取比亚迪的母公司报表"
   "查看茅台近5年的年度利润表"
   ```

## 🛠️ 技术特点

- 基于MCP协议，支持与Claude等AI助手自然对话
- 实时连接Tushare Pro数据源
- 智能错误处理和提示
- 支持并发请求处理
- 数据缓存优化

## 📦 安装说明

### 环境要求
- Python 3.8+
- Tushare Pro账号和API Token

### 快速开始

1. 安装包
```bash
git clone https://github.com/zhewenzhang/tushare_MCP.git
cd tushare_MCP
pip install -r requirements.txt
```

2. 启动服务
```bash
python server.py
```

3. 在Claude中安装
```bash
mcp install server.py
```

## 🔑 首次配置

1. **获取Token**
   - 访问 [Tushare Token页面](https://tushare.pro/user/token)
   - 登录获取API Token

2. **配置Token**
   ```
   对Claude说：请帮我配置Tushare token
   ```

3. **验证配置**
   ```
   对Claude说：请检查token状态
   ```

## 📚 API参考

### 工具函数

1. **股票查询**
```python
get_stock_basic_info(ts_code="", name="")
# 示例：get_stock_basic_info(ts_code="000001.SZ")
```

2. **股票搜索**
```python
search_stocks(keyword="")
# 示例：search_stocks(keyword="新能源")
```

3. **利润表查询**
```python
get_income_statement(ts_code="", start_date="", end_date="", report_type="1")
# 示例：get_income_statement(ts_code="000001.SZ", start_date="20230101", end_date="20231231")
```

4. **Token管理**
```python
setup_tushare_token(token="")
check_token_status()
```

## 🔒 数据安全

- Token存储：用户主目录下的`.tushare_mcp/.env`
- 环境变量：使用python-dotenv安全管理
- 数据传输：HTTPS加密

## 🤝 贡献指南

欢迎提交Issue和Pull Request！

## 📄 开源协议

MIT License - 详见 [LICENSE](LICENSE) 文件 

## 本地环境说明
Python 环境是由操作系统或外部工具（比如 Homebrew）管理的。为了保护系统级的 Python 安装，直接使用 pip3 install 来安装包到全局环境通常是不被允许的。需要通过激活虚拟环境（前提是创建虚拟环境）来完成

   python3 -m venv venv
   source venv/bin/activate


## cloudflare 服务说明
cloudflared 安装命令：
brew install cloudflared && 
sudo cloudflared service install eyJhIjoiNmQ0YzM1ODQ2ZTQxMzliYTU3NDUzYWRiZWEyOWVmOTkiLCJ0IjoiNjA5NTY4MjQtM2JiZS00ODNiLWEyM2EtZDZmMjE3M2IyZTI1IiwicyI6Ill6UXdNV1k0WmprdE5qSTFOUzAwWmpBeUxXSXpZMkl0Wm1RME5HSTFOekl5WXpkaiJ9

tunnels 启用命令：
sudo cloudflared service install eyJhIjoiNmQ0YzM1ODQ2ZTQxMzliYTU3NDUzYWRiZWEyOWVmOTkiLCJ0IjoiNjA5NTY4MjQtM2JiZS00ODNiLWEyM2EtZDZmMjE3M2IyZTI1IiwicyI6Ill6UXdNV1k0WmprdE5qSTFOUzAwWmpBeUxXSXpZMkl0Wm1RME5HSTFOekl5WXpkaiJ9

tunnels 卸载命令：
sudo cloudflared service uninstall

## 新增 mcp 工具后需要重启持久化服务

停止服务：
launchctl unload ~/Library/LaunchAgents/com.nakocai.tushare-mcp-api.plist

启动服务：
launchctl load ~/Library/LaunchAgents/com.nakocai.tushare-mcp-api.plist