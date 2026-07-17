# Crypto Backtest System - 开发计划

> 基于 "ตาเล็ก วินโด้เก้าแปดเอสอี" 策略分析
> **策略**: Mean Reversion + DCA (RSI Signal) — 非 Martingale
> **时间框架**: 1m TF
> **回测数据**: OHLC 1m CSV，约 3 年历史

---

## 项目结构

```
crypto-backtest/
├── data/
│   ├── fetcher.py          # 下载 OHLC 1m 数据
│   └── store.py            # Parquet 存储管理
├── engine/
│   ├── indicators.py       # RSI 计算
│   ├── pattern_detector.py # 蜡烛图形态识别
│   ├── signal.py           # 信号逻辑
│   ├── order.py            # 订单引擎
│   ├── position.py         # 仓位管理
│   └── risk.py             # 风控
├── backtest/
│   ├── runner.py           # 回测主循环
│   └── portfolio.py        # 资金追踪
├── analytics/
│   ├── metrics.py          # 统计指标
│   └── report.py           # HTML 报告生成
├── config/
│   └── strategy.yaml       # 策略参数
├── docs/
│   └── STRATEGY_ANALYSIS.md # 策略完整分析
├── tests/
├── main.py                 # 入口
├── requirements.txt
└── README.md
```

---

## 开发阶段

### Phase 1: 数据管道 (第 1-2 天) ✅ 高优先级
| 任务 | 描述 | 状态 |
|------|------|------|
| 1.1 | 创建 `data/fetcher.py` - Binance/Bybit REST API 下载 1m K 线 | 🔴 待做 |
| 1.2 | 实现增量下载（断点续传） | 🔴 待做 |
| 1.3 | 创建 `data/store.py` - Parquet 读写 | 🔴 待做 |
| 1.4 | 数据验证：缺失 K 线检测、时间戳连续性 | 🔴 待做 |
| 1.5 | 下载 3 年历史数据（BTC, ETH, SOL） | 🔴 待做 |

**产出**: `data/parquet/{SYMBOL}/1m/{YEAR}.parquet`

---

### Phase 2: 信号引擎 (第 3-4 天) ✅ 高优先级
| 任务 | 描述 | 状态 |
|------|------|------|
| 2.1 | `engine/indicators.py` - RSI(14) 向量化计算 | 🔴 待做 |
| 2.2 | `engine/pattern_detector.py` - 核心形态识别 | 🔴 待做 |
| 2.2.1 | 识别：连续 5 根高位收盘 | 🔴 待做 |
| 2.2.2 | 识别：触碰→触碰→触碰 (2-3 根) | 🔴 待做 |
| 2.2.3 | 识别：K 线不收盘在最低点 | 🔴 待做 |
| 2.3 | `engine/signal.py` - Long/Short 信号合成 | 🔴 待做 |
| 2.4 | 单元测试：用已知数据验证 RSI + 形态 | 🔴 待做 |

**关键挑战**: Pattern Detector 是策略的"护城河"，需要精确复现帖子描述的形态

---

### Phase 3: 订单 + 仓位引擎 (第 5-7 天) ✅ 高优先级
| 任务 | 描述 | 状态 |
|------|------|------|
| 3.1 | `engine/order.py` - Maker 限价单逻辑 | 🔴 待做 |
| 3.1.1 | 挂单价 = 实时价 ± 0.05% | 🔴 待做 |
| 3.1.2 | 每分钟检查：价格偏移 → 取消重挂 | 🔴 待做 |
| 3.2 | `engine/position.py` - 仓位管理核心 | 🔴 待做 |
| 3.2.1 | BEP 动态计算（含手续费+资金费率） | 🔴 待做 |
| 3.2.2 | TP 逻辑：BEP + 0.2% | 🔴 待做 |
| 3.2.3 | DCA 逻辑：价格 < BEP × 0.997 → 加仓 | 🔴 待做 |
| 3.2.4 | Max Cap：$50K/对 | 🔴 待做 |
| 3.3 | `engine/risk.py` - 保证金/爆仓检查 | 🔴 待做 |

---

### Phase 4: 回测运行器 (第 8-9 天) ✅ 高优先级
| 任务 | 描述 | 状态 |
|------|------|------|
| 4.1 | `backtest/runner.py` - 事件驱动回测主循环 | 🔴 待做 |
| 4.1.1 | 时间推进：逐根 1m K 线 | 🔴 待做 |
| 4.1.2 | 状态机：无仓位 → 有仓位 → 平仓 | 🔴 待做 |
| 4.2 | `backtest/portfolio.py` - 权益曲线追踪 | 🔴 待做 |
| 4.2.1 | 记录每笔交易：开仓/平仓/加仓/取消 | 🔴 待做 |
| 4.2.2 | 计算实时 Equity + Unrealized PnL | 🔴 待做 |

---

### Phase 5: 分析 + 报告 (第 10 天) ✅ 高优先级
| 任务 | 描述 | 状态 |
|------|------|------|
| 5.1 | `analytics/metrics.py` - 核心指标 | 🔴 待做 |
| 5.1.1 | Win Rate / Trade Count / Avg Hold Time | 🔴 待做 |
| 5.1.2 | Max Drawdown / Sharpe / Sortino | 🔴 待做 |
| 5.1.3 | DCA 统计：平均加仓次数、最大加仓层数 | 🔴 待做 |
| 5.1.4 | Maker vs Taker 手续费影响分析 | 🔴 待做 |
| 5.2 | `analytics/report.py` - HTML 报告生成 | 🔴 待做 |
| 5.2.1 | Equity Curve 图表 | 🔴 待做 |
| 5.2.2 | Drawdown 图表 | 🔴 待做 |
| 5.2.3 | 月度/年度收益表 | 🔴 待做 |
| 5.2.4 | 交易分布图（时间、盈亏、持仓时长） | 🔴 待做 |

---

### Phase 6: 验证与优化 (第 11-12 天) 🟡 中优先级
| 任务 | 描述 | 状态 |
|------|------|------|
| 6.1 | 对照已知回测结果验证（-3.3% 到 -19.7% Drawdown） | 🔴 待做 |
| 6.2 | 参数敏感性分析（RSI 阈值、TP/DCA 百分比） | 🔴 待做 |
| 6.3 | Walk-Forward Analysis（滚动窗口验证） | 🔴 待做 |
| 6.4 | 性能优化：NumPy 向量化、Parquet 分区读取 | 🔴 待做 |
| 6.5 | 边界情况处理：资金费率、熔断、缺失数据 | 🔴 待做 |

---

## 里程碑

| 里程碑 | 目标日期 | 验收标准 |
|--------|----------|----------|
| M1: 数据就绪 | Day 2 | 3 个币种 × 3 年 1m 数据完整存储 |
| M2: 信号可运行 | Day 4 | 能在样本数据上产生信号，RSI 计算正确 |
| M3: 仓位闭环 | Day 7 | 能模拟开仓、DCA、TP、超时处理全流程 |
| M4: 完整回测 | Day 9 | 跑通 3 年数据，输出逐笔交易记录 |
| M5: 报告输出 | Day 10 | 生成 HTML 报告，含核心图表和指标 |
| M6: 交付验证 | Day 12 | Drawdown 与已知数据吻合，代码可维护 |

---

## 关键技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 语言 | Python 3.12 | 生态丰富，pandas/numpy 标配 |
| 回测框架 | 自研 | 策略逻辑太特殊（DCA+动态BEP+Maker刷新），现有框架难以支持 |
| 数据格式 | Parquet (按年分区) | 比 CSV 快 5-10x，列式压缩，支持谓词下推 |
| 计算方式 | NumPy 向量化 | 避免 Python 循环，1m 数据量大需高性能 |
| 配置管理 | YAML | 策略参数外置，便于实验 |
| 可视化 | Plotly | 交互式 HTML，适合 Web 报告 |

---

## 策略参数配置 (config/strategy.yaml)

```yaml
# 见 config/strategy.yaml
```

---

## 风险提示

1. **Pattern Detector 不完美** → 信号偏差 → 回测结果失真
2. **资金费率数据缺失** → BEP 计算不准 → DCA/TP 触发错误
3. **Maker 订单部分成交** → 实际回测中需模拟
4. **3 年数据 ≈ 150 万根/币种** → 内存管理需注意
5. **无止损策略** → 极端行情可能导致巨额浮亏

---

## 下一步行动

**立即开始 Phase 1.1**: 编写 `data/fetcher.py` 下载 Binance 1m K 线数据

```bash
cd /home/jakkrit/crypto-backtest
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install pandas numpy pyarrow requests pyyaml plotly
```

---

> 文档版本: 1.0
> 创建时间: 2026-07-17
> 维护者: Assistant