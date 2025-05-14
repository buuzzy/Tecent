# Tushare_MCP

<div align="center">

**基于 Model Context Protocol (MCP) 的智能股票数据助手**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)

</div>

<br>

该项目基于 Tushare 的金融数据接口进行开发，支持的能力包括：

1、工具调用，比方说股票的行情数据、更深度的财务数据以及指数数据等。

2、提供安全的 Tushare Token 配置与状态检查机制。

3、通过 FastAPI 封装，提供标准化的 HTTP API 接口，方便与其他应用集成。

<br>
为了方便大家体验，我已经完成了在线部署，你可以使用下面的代码进行体验：

```{
  "mcpServers": {
    "Tushare_Tools(Normal)": {
      "url": "https://mcp-api.chatbotbzy.top/sse",
      "type": "sse"
    }
  }
}
```

[👉使用 cherry studio 快速体验教程](https://doc.weixin.qq.com/doc/w3_AbQAFgbhALUCN01st0nWWQfyyiN0f?scode=AJEAIQdfAAo9jULS9NAbQAFgbhALU)

## ✨ 已支持能力
*   **全面的股票数据查询：**
    *   提供股票基本信息、实时行情（日线、指标）、历史股价变动查询。
    *   支持通过股票代码或名称进行智能搜索。

<br>

*   **深度财务数据分析：**
    *   获取上市公司详细财务报表，包括利润表、资产负债表、现金流量表。
    *   查询关键财务指标数据。

<br>

*   **指数与市场数据覆盖：**
    *   支持主流指数的基本信息查询、成分股获取及全球指数行情。

<br>

*   **股东及公司基本面信息：**
    *   查询股东户数、十大股东信息、每日股本市值以及股权质押明细。

## ❌ 未支持能力
* 资金、板块、概念数据和成分股
* 公告、研报等资讯类数据
* 技术面、历史、实时分钟数据

由于这部分数据在 Tushare 需要单独开通权限或收费，故暂未添加

## 🚀 快速开始

### 环境要求

*   Python 3.8+
*   Tushare 账号和 API Token (获取地址: [Tushare Pro Token 申请页面](https://tushare.pro/user/token)，请自行注册)

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
在 AI IDE 软件中（如 Cursor 或 Trae） 的 MCP 服务中添加对应的 Servers

## 📄 开源协议

MIT License - 详见 [LICENSE](LICENSE) 文件 

## 本地环境说明
Python 环境是由操作系统或外部工具（比如 Homebrew）管理的。为了保护系统级的 Python 安装，直接使用 pip3 install 来安装包到全局环境通常是不被允许的。需要通过激活虚拟环境（前提是创建虚拟环境）来完成

   ```bash
   python3 -m venv venv
   ```
   
   ```bash
   source venv/bin/activate
   ```
