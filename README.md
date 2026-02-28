# ETF Momentum Strategy Backtesting System (FoolReveal)

这是一个基于 Streamlit 构建的 ETF 动量轮动策略回测与分析系统。该项目不仅复现了一个经典的动量轮动策略，还通过逆向工程与统计分析，对其参数进行了深度优化与稳健性验证。

## 🌟 核心功能

1.  **策略回测 (Strategy Backtest)**: 
    - 支持自定义时间区间、动量窗口、熔断阈值等参数。
    - 实时生成回测报告，包括收益曲线、回撤图及详细交易记录。
2.  **最新持仓 (Latest Holding)**: 
    - 一键获取 T+1 交易日的建议持仓信号。
    - 自动连接 Tushare 获取最新行情。
3.  **动量分析 (Momentum Analysis)**: 
    - 深度分析动量得分与未来收益的关系（验证“倒 U 型”曲线）。
4.  **参数分析 (Parameter Analysis)**: 
    - 基于全量历史数据的网格搜索结果。
    - 提供多维度指标（夏普、卡玛、胜率等）的交互式排序。
    - 可视化参数平原，帮助用户选择稳健参数，规避过拟合。

## 📂 目录结构

```
foolreveal/
├── Home.py                  # [主程序] 回测系统入口
├── pages/                   # [多页面支持]
│   ├── 1_Momentum_Analysis.py # 动量得分分布分析工具
│   └── 2_Parameter_Analysis.py# 参数统计与稳定性分析报告
├── data/                    # [数据中心]
│   ├── *_history.csv        # 所有 ETF 的历史行情数据
│   └── optimization_results.csv # 预计算的参数优化结果
├── scripts/                 # [内核] 存放各类分析与算法脚本
│   └── fine_tune_strategy.py # 用于生成优化结果的脚本
├── legacy_apps/             # [旧版存档] 旧版本代码
├── requirements.txt         # [依赖文件]
└── README.md                # [说明文档]
```

## 🚀 快速开始

### 本地运行

1.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **启动应用**:
    ```bash
    streamlit run Home.py
    ```

### 部署到 Streamlit Cloud

1.  将本项目推送到 GitHub。
2.  登录 [Streamlit Community Cloud](https://streamlit.io/cloud)。
3.  选择你的 GitHub 仓库。
4.  **Main file path** 填写 `Home.py`。
5.  点击 **Deploy**。

## 📊 数据说明

- **行情数据**: 来源于 Tushare Pro，已包含截至 2026-02-26 的历史数据。
- **优化数据**: `data/optimization_results.csv` 包含了 36 组不同参数组合在 8 年历史数据上的详细回测指标。

## 🛠️ 技术栈

- **前端**: Streamlit
- **数据处理**: Pandas, NumPy
- **可视化**: Plotly
- **统计分析**: SciPy
- **数据源**: Tushare

## 📄 许可证

MIT License
