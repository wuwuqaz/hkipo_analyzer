# CLAUDE.md — 项目上下文

> 最后更新: 2026-05-20

## 项目概述

港股 IPO 打新分析器 (hkipo_analyzer) v0.5.3-alpha。自动获取港股招股 IPO 列表 → 下载招股书 PDF → 解析财务数据 → 多维度评分 → 输出报告。FastAPI + Next.js 全栈。

## 核心模块速查

| 模块 | 职责 |
|------|------|
| `ipo_analyzer/core.py` | 主编排管道：下载 → 解析 → 分析 → 评分 → 输出 |
| `ipo_analyzer/scoring.py` | ScoringSystem 五维加权评分 + 严格打新评分 |
| `ipo_analyzer/models.py` | IPOData / ProspectusInfo 等核心 dataclass (2700+ 行) |
| `ipo_analyzer/settings.py` | 分层 dataclass 配置，`SETTINGS` 单例访问 |
| `ipo_analyzer/history.py` | HistoryStore，基于 `temp/ipo_history.json` + `temp/reanalysis/` |
| `ipo_analyzer/downloader.py` | AiPO 孖展数据 + HKEX 招股书 PDF 下载 |
| `ipo_analyzer/parser.py` | PDF → 结构化数据提取 |
| `ipo_analyzer/backtest/` | 🆕 回测框架 & 贝叶斯权重优化 |

## 数据存储约定

- **历史记录**: `temp/ipo_history.json` (JSON 数组)
- **重新分析**: `temp/reanalysis/{code}_latest.json` + 时间戳版本
- **回测数据**: `data/backtest.db` (SQLite)
- **优化权重**: `data/optimized_weights.yaml`
- **上传文件**: `storage/uploads/`
- **前端构建**: `frontend/.next/`

## 评分权重体系

### 默认权重 (settings.py → ScoringWeights)

| 场景 | trade | fundamental | valuation | theme | data_quality |
|------|-------|-------------|-----------|-------|-------------|
| live_heat (有孖展) | 25% | 35% | 25% | 10% | 5% |
| prospectus_only | 15% | 40% | 25% | 15% | 5% |

### 优化权重 (data/optimized_weights.yaml)

通过回测框架的贝叶斯优化自动生成，scoring.py 自动加载。不存在时回退默认权重。

---

## 2026-05-20 新增: 回测框架 & 贝叶斯权重优化

### 背景

项目此前权重基于经验设定，缺少数据验证。本次新增系统化的回测和优化能力。

### 新增文件

```
ipo_analyzer/backtest/
├── __init__.py          # 模块导出
├── __main__.py          # python -m 入口
├── models.py            # BacktestRecord / BacktestResult / OptimizationResult
├── collector.py         # 从 ipo_history.json + reanalysis/ 提取样本
├── engine.py            # 评分回放 + Spearman IC + 十分位分析
├── metrics.py           # 多目标函数 (胜率+期望收益-回撤) + LOO CV
├── optimizer.py         # GP+EI 贝叶斯优化 (纯 numpy, 零新依赖)
├── store.py             # SQLite 持久化
└── cli.py               # run / optimize / report / status 子命令
```

### 修改文件

| 文件 | 改动 |
|------|------|
| `settings.py` | 新增 `BacktestSettings` 配置类 |
| `scoring.py` | `_detect_weight_profile()` 集成 `_try_load_optimized_weights()` |
| `__main__.py` | 注册 `backtest` 子命令 |

### CLI 使用

```bash
python -m ipo_analyzer.backtest status           # 查看样本数
python -m ipo_analyzer.backtest run               # 用默认权重跑回测
python -m ipo_analyzer.backtest optimize           # 贝叶斯搜索最优权重
python -m ipo_analyzer.backtest report --compare   # 对比默认 vs 优化
```

### 当前状态

- ✅ 25 新增测试通过
- ✅ 262 原有测试零回归
- ⚠️ `temp/ipo_history.json` 暂无 post_listing 数据 → 0 有效样本 → optimize 暂不可运行
- 📋 等待新股上市后 post_listing 数据积累，样本自然增长后即可优化

---

## 后续计划 (Backlog)

### 🔴 高优先级

1. **保荐人/承销商战绩分析** — 新增 sponsor_analyzer.py
   - 从招股书提取保荐人信息
   - 建立保荐人历史战绩数据库 (首日涨跌/破发率)
   - 纳入评分体系 (建议权重 5-10%)

2. **定价价差指标** — 新增 pricing_gap.py
   - 发行价 vs 招股价区间中值偏离
   - 华泰研究: 价差<20% 时机构认可度高
   - 纳入交易热度维度

### 🟡 中优先级

3. **市场整体 IPO 情绪** — 新增 ipo_sentiment.py
   - 过去1-3个月 IPO 平均首日回报
   - 市场破发率趋势
   - 过热/过冷预警

4. **宏观环境因子** — 新增 macro_factors.py
   - Hibor 利率 / 美元指数 / 恒生指数表现
   - 中金研究: 弱美元+低Hibor = IPO活跃
   - 通过 yfinance 免费获取

### 🟢 低优先级

5. **回拨机制影响分析** — 超购触发回拨后散户/机构持仓比例变化
6. **卖出时机建议** — 基于历史同类 IPO 首日/3日/入通窗口收益路径
7. **甲组/乙组策略差异化** — 红鞋机制下不同资金量最优策略
8. **融资打新成本收益** — 孖展利息 vs 中签率 vs 预期收益
9. **禁售期解禁日历** — 基石 6 个月锁定到期抛压预警
