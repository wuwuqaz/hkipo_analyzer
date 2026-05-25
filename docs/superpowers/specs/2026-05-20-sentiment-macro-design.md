# 市场IPO情绪 + 宏观环境因子 设计文档

**日期：** 2026-05-20  
**状态：** 已确认  
**目标：** 新增市场IPO情绪跟踪和宏观环境因子，增强打新市场环境判断

---

## 一、背景与目标

根据行业最佳实践对比（中金研究强调"HIBOR+美元指数+恒指"三因子；多数券商跟踪近期IPO平均表现），接入此两维度可显著增强打新时机判断。

### 1.1 成功标准
- 数据源免费（yfinance API + 自有post_listing数据）
- 融入主题维度（theme_score），bonus/penalty方式调整
- 有缓存避免频繁请求外部API
- 不破坏现有测试

---

## 二、模块一：市场IPO情绪

**文件：** `ipo_analyzer/ipo_sentiment.py`

**数据来源：** `ipo_history.json` 中的 `post_listing.first_day_return`、`over_sub_ratio`、`is_break`

**实现：** 直接读取 `HistoryStore` 的数据，统计指定窗口内的表现。

**缓存：** 计算结果缓存12小时（与history文件mtime关联）。

### 输出结构

```python
{
    'sentiment_label': '火热' | '温和' | '冷清',
    'sentiment_bonus': int,           # -5 到 +5
    'avg_return_1m': Optional[float],
    'avg_return_3m': Optional[float],
    'break_rate_1m': Optional[float],
    'break_rate_3m': Optional[float],
    'ipo_count_1m': int,
    'ipo_count_3m': int,
    'confidence': 'history' | 'insufficient_data',
}
```

### 评分规则

| 条件 | Bonus | Label |
|------|-------|-------|
| 近1月平均首日 > 10% | +5 | 火热 |
| 5% ~ 10% | +3 | 偏热 |
| 0 ~ 5% | +1 | 温和 |
| -5% ~ 0 | -2 | 偏冷 |
| < -5% | -5 | 冷清 |
| 近1月样本 < 3 | 0 | 数据不足 |

---

## 三、模块二：宏观环境因子

**文件：** `ipo_analyzer/macro_factors.py`

**数据来源：** yfinance (已安装)

| 指标 | Ticker | 用法 |
|------|--------|------|
| 恒生指数 | `^HSI` | 20日涨跌幅 |
| HIBOR 1M | `^IRX` 或备用固定值 | 利率水平 |
| USD/HKD | `HKD=X` | 强弱 |

**缓存：** 计算结果缓存6小时（盘中变化慢）。

### 输出结构

```python
{
    'macro_label': '顺风' | '中性' | '逆风',
    'macro_bonus': int,              # -3 到 +3
    'hsi_20d_change': Optional[float],
    'hibor_1m': Optional[float],
    'usd_hkd': Optional[float],
    'confidence': 'live' | 'stale_cache' | 'unavailable',
}
```

### 评分规则

| 条件 | Bonus | Label |
|------|-------|-------|
| HSI 20日 > +3% + HIBOR < 5% | +3 | 顺风 |
| HSI 20日 > 0% | +1 | 偏顺风 |
| HSI 20日 0 ~ -3% | -1 | 偏逆风 |
| HSI 20日 < -3% | -3 | 逆风 |
| 数据不可用 | 0 | 中性 |

---

## 四、接入 scoring.py

**位置：** `_compute_raw_scores()` 方法中 theme_raw 计算后

```python
# 市场情绪 + 宏观附加分
sentiment = prospectus_info.get('ipo_sentiment', {})
macro = prospectus_info.get('macro_factors', {})
mkt_bonus = sentiment.get('sentiment_bonus', 0) + macro.get('macro_bonus', 0)
if mkt_bonus != 0:
    theme_raw += mkt_bonus
    theme_max += 10
```

---

## 五、调用点

在 `core.py` 的 `_analyze_single` 或 `analyze` 方法中，评分前注入：

```python
prospectus_info['ipo_sentiment'] = get_ipo_sentiment(history_store)
prospectus_info['macro_factors'] = get_macro_factors()
```

---

## 六、配置项

settings.py 新增：

```python
@dataclass
class SentimentMacroThresholds:
    sentiment_hot_threshold: float = 0.10
    sentiment_hot_bonus: int = 5
    sentiment_warm_threshold: float = 0.05
    sentiment_warm_bonus: int = 3
    sentiment_neutral_threshold: float = 0.0
    sentiment_neutral_bonus: int = 1
    sentiment_cool_bonus: int = -2
    sentiment_cold_bonus: int = -5
    min_samples_1m: int = 3
    macro_tailwind_threshold: float = 0.03
    macro_tailwind_bonus: int = 3
    macro_slight_tailwind_bonus: int = 1
    macro_headwind_threshold: float = -0.03
    macro_headwind_bonus: int = -3
    max_total_bonus: int = 10
```

---

## 七、测试

| 文件 | 测试数 | 覆盖 |
|------|--------|------|
| `tests/test_ipo_sentiment.py` | 5 | 火热/温和/冷清/数据不足/样本计算 |
| `tests/test_macro_factors.py` | 5 | 顺风/逆风/中性/缓存/不可用 |

---

## 八、验收标准

- [ ] 两个模块均可独立调用并返回正确结果
- [ ] 融入 scoring.py theme_score 维度
- [ ] 新增约10个单元测试全部通过
- [ ] 全量测试无回归
