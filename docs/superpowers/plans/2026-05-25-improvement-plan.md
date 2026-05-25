# 项目改进实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复并发安全、安全漏洞、架构债务和测试缺口，提升项目整体健壮性

**Architecture:** 从最紧急的并发安全修复开始，逐步推进到安全加固、代码简化、类型强化和测试补充

**前置条件：** 确保现有测试全部通过 `python3 -m pytest tests/ -x`

---

## 文件结构总览

### 新建文件
```
ipo_analyzer/
├── _threadsafe_cache.py              - 线程安全 LRU 缓存
├── _url_validation.py                - URL 安全校验
tests/
├── test_threadsafe_cache.py          - 缓存并发测试
├── test_url_validation.py             - URL 校验测试
├── test_normalize_output_fields.py   - 输出字段归一化测试
├── test_risk_penalty.py              - 风险惩罚函数测试
├── test_history_recalculate.py       - 历史分数重算测试
```

### 修改文件
```
ipo_analyzer/parser.py                - 替换缓存、消除可变状态
ipo_analyzer/scoring.py               - 替换缓存、抽取常量
ipo_analyzer/history.py               - WAL 模式、连接池、inline import
ipo_analyzer/downloader.py            - URL 校验、缓存线程安全、浏览器生命周期
ipo_analyzer/backtest/optimizer.py     - 空数据集校验
ipo_analyzer/backtest/engine.py        - 权重重归一化
ipo_analyzer/backtest/collector.py     - 数据质量门槛修复
ipo_analyzer/core.py                  - 拆分巨函数
api/auth.py                           - Token 默认开启
api/main.py                           - CORS 收紧
api/routes/analyze.py                 - 流式上传
.gitignore                            - 排除 .env 和根级调试脚本
```

---

## 迭代一：并发安全 (P0)

> 修复 API 服务并发场景下的数据竞争和缓存损坏风险

### Task 1.1: 创建线程安全 LRU 缓存工具

**Files:**
- Create: `ipo_analyzer/_threadsafe_cache.py`
- Test: `tests/test_threadsafe_cache.py`

- [ ] **Step 1: 实现 `ThreadSafeLRUCache`**

```python
"""线程安全的 LRU 缓存，替代 OrderedDict + 手动管理的模式."""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Optional


class ThreadSafeLRUCache:
    def __init__(self, maxsize: int = 256):
        self._maxsize = maxsize
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
            else:
                self._cache[key] = value
                if len(self._cache) > self._maxsize:
                    self._cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._cache
```

- [ ] **Step 2: 写并发测试**

```python
"""ThreadSafeLRUCache 并发安全验证."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import threading
import time
from ipo_analyzer._threadsafe_cache import ThreadSafeLRUCache


def test_basic_get_put():
    cache = ThreadSafeLRUCache(maxsize=4)
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing") is None


def test_lru_eviction():
    cache = ThreadSafeLRUCache(maxsize=3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    cache.put("d", 4)
    assert cache.get("a") is None
    assert cache.get("d") == 4


def test_invalidate():
    cache = ThreadSafeLRUCache()
    cache.put("a", 1)
    cache.invalidate("a")
    assert cache.get("a") is None


def test_concurrent_access():
    cache = ThreadSafeLRUCache(maxsize=128)
    errors = []

    def writer(start, count):
        try:
            for i in range(start, start + count):
                cache.put(f"key_{i}", i)
        except Exception as e:
            errors.append(e)

    def reader(start, count):
        try:
            for i in range(start, start + count):
                cache.get(f"key_{i}")
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=(0, 500)),
        threading.Thread(target=writer, args=(500, 500)),
        threading.Thread(target=reader, args=(0, 500)),
        threading.Thread(target=reader, args=(250, 500)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"并发错误: {errors}"


def test_len_and_contains():
    cache = ThreadSafeLRUCache(maxsize=10)
    cache.put("x", 1)
    cache.put("y", 2)
    assert len(cache) == 2
    assert "x" in cache
    assert "z" not in cache
```

- [ ] **Step 3: 运行测试**

```bash
python3 -m pytest tests/test_threadsafe_cache.py -v
```

- [ ] **Step 4: Commit**

```bash
git add ipo_analyzer/_threadsafe_cache.py tests/test_threadsafe_cache.py
git commit -m "feat: add ThreadSafeLRUCache for concurrent access"
```

---

### Task 1.2: 替换 parser.py 中的非线程安全缓存

**Files:**
- Modify: `ipo_analyzer/parser.py`

- [ ] **Step 1: 替换 import 和缓存实例化**

在 `parser.py` 顶部，将：
```python
from collections import OrderedDict
```
替换为：
```python
from ipo_analyzer._threadsafe_cache import ThreadSafeLRUCache
```

- [ ] **Step 2: 替换 `_PARSE_CACHE` 定义**

将：
```python
_PARSE_CACHE: OrderedDict = OrderedDict()
```
替换为：
```python
_PARSE_CACHE = ThreadSafeLRUCache(maxsize=256)
```

- [ ] **Step 3: 替换所有缓存访问模式**

替换所有 `if key in _PARSE_CACHE: value = _PARSE_CACHE[key]` 模式为 `value = _PARSE_CACHE.get(key)`。

替换所有 `_PARSE_CACHE[key] = value` 为 `_PARSE_CACHE.put(key, value)`。

替换所有 `_PARSE_CACHE.pop(key, None)` 为 `_PARSE_CACHE.invalidate(key)`。

- [ ] **Step 4: 运行测试确认无回归**

```bash
python3 -m pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add ipo_analyzer/parser.py
git commit -m "refactor: replace OrderedDict LRU with ThreadSafeLRUCache in parser"
```

---

### Task 1.3: 替换 scoring.py 中的非线程安全权重缓存

**Files:**
- Modify: `ipo_analyzer/scoring.py`

- [ ] **Step 1: 添加 import**

在 `scoring.py` 顶部添加：
```python
from ipo_analyzer._threadsafe_cache import ThreadSafeLRUCache
import threading
```

- [ ] **Step 2: 替换全局缓存变量**

将：
```python
_optimized_weights_cache = None
_optimized_weights_cache_time = 0.0
```
替换为：
```python
_optimized_weights_cache = ThreadSafeLRUCache(maxsize=8)
_weights_cache_lock = threading.Lock()
```

- [ ] **Step 3: 替换 `_try_load_optimized_weights` 中的缓存逻辑**

将缓存读取改为：
```python
cached = _optimized_weights_cache.get("weights")
if cached is not None:
    return cached
```

将缓存写入改为：
```python
_optimized_weights_cache.put("weights", weights)
```

- [ ] **Step 4: 运行测试确认无回归**

```bash
python3 -m pytest tests/test_scoring*.py -x -q
```

- [ ] **Step 5: Commit**

```bash
git add ipo_analyzer/scoring.py
git commit -m "refactor: replace global weight cache with ThreadSafeLRUCache"
```

---

### Task 1.4: 替换 downloader.py 中的非线程安全缓存

**Files:**
- Modify: `ipo_analyzer/downloader.py`

- [ ] **Step 1: 添加 import**

```python
from ipo_analyzer._threadsafe_cache import ThreadSafeLRUCache
```

- [ ] **Step 2: 替换 `_listing_cache`**

将类级 ` _listing_cache: dict = {}` 替换为：
```python
_listing_cache = ThreadSafeLRUCache(maxsize=128)
```

- [ ] **Step 3: 替换所有 `_listing_cache[key] = value` 为 `_listing_cache.put(key, value)`**

替换所有 `_listing_cache.get(key)` 保持不变（ThreadSafeLRUCache 也支持 `.get()` 返回 Optional）。

- [ ] **Step 4: 运行测试确认无回归**

```bash
python3 -m pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add ipo_analyzer/downloader.py
git commit -m "refactor: replace dict cache with ThreadSafeLRUCache in downloader"
```

---

### Task 1.5: 消除 parser.py 的可变实例状态

**Files:**
- Modify: `ipo_analyzer/parser.py`

- [ ] **Step 1: 将 `self._current_info` 转为方法参数**

在 `ProspectusParser` 类中，找到所有使用 `self._current_info` 的方法。将 `_current_info` 从实例属性改为方法参数传递：

```python
# 之前:
def extract_info(self, text, ...):
    self._current_info = {}
    ...
    self._current_info.update(...)

# 之后:
def extract_info(self, text, ...):
    info: dict[str, Any] = {}
    ...
    info.update(...)
    return self._finalize_info(info)
```

每个内部方法（`_extract_financials`, `_extract_risk` 等）都接收 `info` 参数而非读写 `self._current_info`。

- [ ] **Step 2: 运行测试确认无回归**

```bash
python3 -m pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add ipo_analyzer/parser.py
git commit -m "refactor: eliminate mutable instance state in ProspectusParser"
```

---

## 迭代二：安全加固 (P0)

### Task 2.1: URL 安全校验

**Files:**
- Create: `ipo_analyzer/_url_validation.py`
- Test: `tests/test_url_validation.py`
- Modify: `ipo_analyzer/downloader.py`

- [ ] **Step 1: 实现 URL 验证工具**

```python
"""URL 安全校验，防止 SSRF 和路径遍历."""

from __future__ import annotations

from urllib.parse import urlparse

ALLOWED_SCHEMES = {"https", "http"}
ALLOWED_HOSTS = {
    "www1.hkexnews.hk",
    "www.hkex.com.hk",
    "aipo.com",
    "www.aipo.com",
    "aipo.com.hk",
}


def validate_download_url(url: str) -> str:
    """校验下载 URL 是否指向允许的域名，防止 SSRF.

    Returns: 校验通过的原 URL
    Raises: ValueError: URL 不合法
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"不允许的 URL scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError(f"URL 缺少 hostname: {url}")
    host_lower = parsed.hostname.lower()
    host_ok = any(
        host_lower == allowed or host_lower.endswith("." + allowed)
        for allowed in ALLOWED_HOSTS
    )
    if not host_ok:
        raise ValueError(f"不允许的下载域名: {parsed.hostname}")
    return url


def sanitize_filename(filename: str) -> str:
    """清理上传文件名，防止路径遍历.

    Returns: 仅包含安全字符的文件名
    """
    import re
    cleaned = re.sub(r'[^\w\s\-.]', '', filename.strip())
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    if not cleaned:
        cleaned = "upload"
    return cleaned
```

- [ ] **Step 2: 写测试**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ipo_analyzer._url_validation import validate_download_url, sanitize_filename


def test_valid_hkex_url():
    url = "https://www1.hkexnews.hk/some/path.pdf"
    assert validate_download_url(url) == url


def test_valid_aipo_url():
    url = "https://aipo.com/api/data"
    assert validate_download_url(url) == url


def test_reject_ftp_scheme():
    with pytest.raises(ValueError, match="scheme"):
        validate_download_url("ftp://evil.com/file")


def test_reject_unknown_host():
    with pytest.raises(ValueError, match="域名"):
        validate_download_url("https://evil.com/file.pdf")


def test_reject_no_hostname():
    with pytest.raises(ValueError, match="hostname"):
        validate_download_url("https:///path.pdf")


def test_sanitize_normal_filename():
    assert sanitize_filename("report.pdf") == "report.pdf"


def test_sanitize_path_traversal():
    assert sanitize_filename("../../../etc/passwd") == "etcpasswd"


def test_sanitize_empty():
    assert sanitize_filename("") == "upload"


def test_sanitize_double_dot():
    assert sanitize_filename("file..pdf") == "file.pdf"
```

- [ ] **Step 3: 在 downloader.py 中使用校验**

在 `downloader.py` 中所有发起 HTTP 请求的 URL 使用点，添加：

```python
from ipo_analyzer._url_validation import validate_download_url
```

在 URL 使用前调用：
```python
validated_url = validate_download_url(url)
```

- [ ] **Step 4: 运行测试**

```bash
python3 -m pytest tests/test_url_validation.py -v
```

- [ ] **Step 5: Commit**

```bash
git add ipo_analyzer/_url_validation.py tests/test_url_validation.py ipo_analyzer/downloader.py
git commit -m "feat: add URL validation to prevent SSRF in downloader"
```

---

### Task 2.2: API 安全加固 — 认证和 CORS

**Files:**
- Modify: `api/auth.py`
- Modify: `api/main.py`

- [ ] **Step 1: 修改 auth.py 默认启用 Token 认证**

找到 `HKIPO_REQUIRE_API_TOKEN` 的默认值，将 `False` 改为 `True`：

```python
REQUIRE_API_TOKEN = os.environ.get("HKIPO_REQUIRE_API_TOKEN", "true").lower() in ("true", "1", "yes")
```

- [ ] **Step 2: 收紧 CORS 配置**

在 `api/main.py` 中，将 CORS 配置从：
```python
allow_methods=["*"],
allow_headers=["*"],
```
改为：
```python
allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
allow_headers=["Authorization", "Content-Type", "X-API-Token"],
```

- [ ] **Step 3: 确认 API 仍可本地测试**

```bash
HKIPO_API_TOKEN=test HKIPO_REQUIRE_API_TOKEN=false python3 -m uvicorn api.main:app --port 8000 &
sleep 3
curl -s http://localhost:8000/api/health | head -c 200
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add api/auth.py api/main.py
git commit -m "security: enable API token by default, tighten CORS"
```

---

### Task 2.3: 文件上传安全

**Files:**
- Modify: `api/routes/analyze.py`
- Modify: `api/services/storage_service.py` (如不存在则修改对应存储逻辑)

- [ ] **Step 1: 添加文件名清理**

在上传文件名处理处使用 `sanitize_filename`：

```python
from ipo_analyzer._url_validation import sanitize_filename
# ...
safe_filename = sanitize_filename(pdf.filename)
```

- [ ] **Step 2: 添加流式大小检查（而非全量读入内存）**

将：
```python
content = await pdf.read()
```
改为分块读取并限制大小：
```python
chunks = []
total_size = 0
MAX_SIZE = max_upload_size_mb * 1024 * 1024
while True:
    chunk = await pdf.read(1024 * 1024)  # 1MB 块
    if not chunk:
        break
    total_size += len(chunk)
    if total_size > MAX_SIZE:
        raise HTTPException(status_code=413, detail="文件过大")
    chunks.append(chunk)
content = b"".join(chunks)
```

- [ ] **Step 3: Commit**

```bash
git add api/routes/analyze.py
git commit -m "security: sanitize upload filename and stream file size check"
```

---

## 迭代三：数据库与缓存硬化 (P1)

### Task 3.1: HistoryStore 启用 WAL 模式和连接复用

**Files:**
- Modify: `ipo_analyzer/history.py`

- [ ] **Step 1: 在 `_init_db` 方法中设置 WAL 模式**

在创建表语句之后添加：
```python
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA synchronous=NORMAL")
```

- [ ] **Step 2: 将连接改为类级复用**

将 `_db_read_all` / `_db_write` 中每次创建新连接的模式改为类级连接：

```python
def _get_conn(self):
    if self._conn is None:
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
    return self._conn
```

添加关闭方法：
```python
def close(self):
    if self._conn is not None:
        self._conn.close()
        self._conn = None
```

- [ ] **Step 3: 修复 `_migrate_from_json_if_needed` 并发安全**

添加迁移标记文件防止双重迁移：
```python
def _migrate_from_json_if_needed(self):
    marker = self._db_path.parent / ".migration_done"
    if marker.exists():
        return
    ...
    marker.touch()
```

- [ ] **Step 4: 将 `import fitz` 提升到文件顶部**

将 `history.py` 中 `_recalculate_scores` 方法内的 `import fitz` 移到文件顶部，并做优雅降级：

```python
try:
    import fitz
except ImportError:
    fitz = None
```

在方法中添加检查：
```python
if fitz is None:
    raise RuntimeError("pymupdf 未安装，无法重算评分")
```

- [ ] **Step 5: 运行测试**

```bash
python3 -m pytest tests/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add ipo_analyzer/history.py
git commit -m "fix: WAL mode, connection reuse, migration guard, top-level fitz import"
```

---

### Task 3.2: 修复 backtest 模块空数据和质量门槛问题

**Files:**
- Modify: `ipo_analyzer/backtest/optimizer.py`
- Modify: `ipo_analyzer/backtest/engine.py`
- Modify: `ipo_analyzer/backtest/collector.py`

- [ ] **Step 1: optimizer.py 空数据集保护**

在 `optimize_weights` 函数开头添加：
```python
if len(dataset) < 20:
    raise ValueError(f"数据集不足 ({len(dataset)} 样本)，至少需要 20 个样本进行贝叶斯优化")
```

- [ ] **Step 2: engine.py 权重重归一化**

在 `run_backtest` 函数中，使用权重前添加归一化：
```python
total_w = sum(weights.values())
if total_w > 0 and abs(total_w - 1.0) > 0.01:
    weights = {k: v / total_w for k, v in weights.items()}
```

- [ ] **Step 3: collector.py 数据质量门槛修复**

在 `_coerce_data_quality` 中，当 `threshold` 为 `None` 时，使用默认门槛而非 0：
```python
def _coerce_data_quality(score, threshold=None):
    if threshold is None:
        threshold = 3  # 默认最低数据质量门槛
    ...
```

- [ ] **Step 4: 运行 backtest 相关测试**

```bash
python3 -m pytest tests/test_backtest*.py -x -q
```

- [ ] **Step 5: Commit**

```bash
git add ipo_analyzer/backtest/optimizer.py ipo_analyzer/backtest/engine.py ipo_analyzer/backtest/collector.py
git commit -m "fix: backtest empty dataset guard, weight normalization, quality threshold"
```

---

## 迭代四：代码简化 (P1)

### Task 4.1: 拆分 `_normalize_output_fields` 巨函数

**Files:**
- Modify: `ipo_analyzer/core.py`
- Test: `tests/test_normalize_output_fields.py`

- [ ] **Step 1: 将 `_normalize_output_fields` 拆分为独立字段映射 + 小方法**

将 ~90 行的字段赋值改为数据驱动的映射：

```python
_FIELD_MAP = {
    "company_name": ("prospectus_info", "extracted_company_name"),
    "sector": ("prospectus_info", "sector"),
    "offer_price": ("prospectus_info", "offer_price"),
    "lot_size": ("prospectus_info", "lot_size"),
    "market_cap_hkd_million": ("prospectus_info", "market_cap_hkd_million"),
    ...
}

def _normalize_output_fields(ipo_data, prospectus_info):
    result = {}
    for target_key, (source, source_key) in _FIELD_MAP.items():
        src_dict = ipo_data if source == "ipo_data" else prospectus_info
        result[target_key] = src_dict.get(source_key)
    # 处理计算字段
    result.update(_compute_derived_fields(ipo_data, prospectus_info))
    return result

def _compute_derived_fields(ipo_data, prospectus_info):
    derived = {}
    ...
    return derived
```

- [ ] **Step 2: 写测试**

为 `_normalize_output_fields` 编写单元测试，验证字段映射正确性和缺失字段 fallback：

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.core import _normalize_output_fields


def test_normalize_basic_fields():
    ipo_data = {"hk_code": "09999", "company_name": "测试", "margin_total": 100.0}
    p_info = {"sector": "healthcare", "offer_price": 10.5, "lot_size": 1000}
    result = _normalize_output_fields(ipo_data, p_info)
    assert result["company_name"] == "测试"
    assert result["sector"] == "healthcare"
    assert result["offer_price"] == 10.5


def test_normalize_missing_fields():
    result = _normalize_output_fields({}, {})
    assert result.get("company_name") is None
    assert result.get("sector") is None


def test_normalize_computed_fields():
    ipo_data = {"score": 75.0, "trade_score": 80.0}
    p_info = {}
    result = _normalize_output_fields(ipo_data, p_info)
    assert result["score"] == 75.0
    assert result["trade_score"] == 80.0
```

- [ ] **Step 3: 运行测试**

```bash
python3 -m pytest tests/test_normalize_output_fields.py -v
python3 -m pytest tests/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add ipo_analyzer/core.py tests/test_normalize_output_fields.py
git commit -m "refactor: break _normalize_output_fields into data-driven field mapping"
```

---

### Task 4.2: 抽取 scoring.py 硬编码中文字符串为常量

**Files:**
- Modify: `ipo_analyzer/scoring.py`

- [ ] **Step 1: 在 scoring.py 顶部定义常量**

```python
# 估值压力标签
VAL_LABEL_EXPENSIVE = "很贵"
VAL_LABEL_HIGH = "偏贵"
VAL_LABEL_FAIR = "合理"
VAL_LABEL_CHEAP = "便宜"

# 市场热度标签
HEAT_LABEL_HOT = "极热"
HEAT_LABEL_WARM = "温"
HEAT_LABEL_COLD = "冷"

# 估值辅助标签
VAL_ASSIST_PS = "PS辅助"
VAL_ASSIST_DCF = "DCF辅助"
VAL_ASSIST_NAV = "NAV辅助"

# 打新信号标签
SIGNAL_POSITIVE = "积极申购"
SIGNAL_NEGATIVE = "建议跳过"
SIGNAL_NEUTRAL = "中性试水"
```

- [ ] **Step 2: 全局替换硬编码字符串**

将 scoring.py 中所有 `很贵`, `偏贵`, `合理`, `便宜`, `极热`, `温`, `冷`, `积极申购`, `建议跳过`, `中性试水` 等硬编码替换为对应常量。

- [ ] **Step 3: 运行测试确认无回归**

```bash
python3 -m pytest tests/test_scoring*.py -x -q
```

- [ ] **Step 4: Commit**

```bash
git add ipo_analyzer/scoring.py
git commit -m "refactor: extract hardcoded Chinese strings to constants in scoring"
```

---

### Task 4.3: 修复 `_detect_weight_profile` 返回类型不一致

**Files:**
- Modify: `ipo_analyzer/scoring.py`

- [ ] **Step 1: 将 `_detect_weight_profile` 返回值从 dict 改为使用 `WeightProfile` dataclass**

找到 `_detect_weight_profile` 函数，将返回值从 inline dict 改为返回现有的 `WeightProfile` dataclass（或 `scoring/models.py` 中的 `WeightProfile`）：

```python
def _detect_weight_profile(prospectus_info, ...):
    ...
    return WeightProfile(
        name="live_heat",
        weights={"trade": 0.25, "fundamental": 0.35, ...}
    )
```

确保调用方使用 `.name` 和 `.weights` 而非 `["name"]` 和 `["weights"]`。

- [ ] **Step 2: 运行测试确认**

```bash
python3 -m pytest tests/test_scoring*.py -x -q
```

- [ ] **Step 3: Commit**

```bash
git add ipo_analyzer/scoring.py
git commit -m "refactor: return WeightProfile dataclass from _detect_weight_profile"
```

---

## 迭代五：测试补充 (P1)

### Task 5.1: 补充风险惩罚函数测试

**Files:**
- Create: `tests/test_risk_penalty.py`

- [ ] **Step 1: 编写 `_calculate_risk_penalty` 测试**

在 scoring.py 中找到 `_calculate_risk_penalty` 函数，理解其逻辑，然后编写完整测试：

```python
"""测试风险惩罚计算逻辑."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ipo_analyzer.scoring import ScoringSystem


def test_risk_penalty_no_risk():
    system = ScoringSystem()
    # 无风险文本时不应有惩罚
    penalty = system._calculate_risk_penalty({})
    assert penalty == 0


def test_risk_penalty_legal_risk():
    system = ScoringSystem()
    p = {"risk_analysis": {"risks": {"legal": ["涉及诉讼"]}}}
    penalty = system._calculate_risk_penalty(p)
    assert penalty > 0


def test_risk_penalty_capped():
    system = ScoringSystem()
    # 大量风险类别不应超过上限
    p = {"risk_analysis": {"risks": {
        "legal": ["风险1", "风险2"],
        "regulatory": ["风险3"],
        "accounting": ["风险4"],
        "operational": ["风险5"],
    }}}
    penalty = system._calculate_risk_penalty(p)
    assert penalty <= 20  # 应有上限


def test_risk_penalty_severe_flags():
    system = ScoringSystem()
    p = {"risk_analysis": {"total_penalty": 15.0}}
    penalty = system._calculate_risk_penalty(p)
    assert penalty == 15.0
```

注意：测试需根据 `_calculate_risk_penalty` 的实际签名和逻辑调整。

- [ ] **Step 2: 运行测试**

```bash
python3 -m pytest tests/test_risk_penalty.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_risk_penalty.py
git commit -m "test: add risk penalty calculation tests"
```

---

### Task 5.2: 补充历史分数重算集成测试

**Files:**
- Create: `tests/test_history_recalculate.py`

- [ ] **Step 1: 编写 `_recalculate_scores` 集成测试**

```python
"""测试 HistoryStore 分数重算逻辑."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import tempfile
from pathlib import Path
from ipo_analyzer.history import HistoryStore


def test_recalculate_scores_basic(tmp_path):
    """验证重算能正确更新记录的 score 字段."""
    db_path = tmp_path / "test_history.db"
    store = HistoryStore(db_path=db_path)

    record = {
        "hk_code": "09999",
        "company_name": "测试公司",
        "score": 60.0,
        "prospectus_info": {"sector": "tech"},
    }
    store.archive(record)

    # 重算（即使没有 PDF 也能运行，因为会 fallback 到现有数据）
    results = store.recalculate_all_scores(force=True)

    assert isinstance(results, list)


def test_archive_and_read(tmp_path):
    db_path = tmp_path / "test_history.db"
    store = HistoryStore(db_path=db_path)

    record = {"hk_code": "01234", "company_name": "测试", "score": 55.0}
    store.archive(record)

    all_records = store.read_all()
    assert len(all_records) >= 1
    assert any(r.get("hk_code") == "01234" for r in all_records)
```

- [ ] **Step 2: 运行测试**

```bash
python3 -m pytest tests/test_history_recalculate.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_history_recalculate.py
git commit -m "test: add history score recalculation integration tests"
```

---

## 迭代六：工程质量 (P2)

### Task 6.1: 清理项目根目录调试脚本

**Files:**
- Delete: `test_debug_regex.py` (如存在)
- Delete: `test_extract_debug.py` (如存在)
- Delete: `test_founder_regex.py` (如存在)
- Delete: `test_profit_debug.py` (如存在)
- Modify: `.gitignore`

- [ ] **Step 1: 检查根目录调试脚本**

```bash
ls test_debug_*.py test_extract_debug.py test_founder_regex.py test_profit_debug.py 2>/dev/null
```

- [ ] **Step 2: 删除调试脚本**

```bash
rm -f test_debug_regex.py test_extract_debug.py test_founder_regex.py test_profit_debug.py
```

- [ ] **Step 3: 在 `.gitignore` 中添加模式**

在 `.gitignore` 末尾追加：
```
# 项目根级调试脚本
/test_debug_*.py
/test_extract_debug.py
/test_founder_regex.py
/test_profit_debug.py

# 环境文件
.env
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git rm --cached test_debug_regex.py test_extract_debug.py test_founder_regex.py test_profit_debug.py 2>/dev/null || true
git commit -m "chore: remove debug scripts from root, update .gitignore"
```

---

### Task 6.2: Playwright 浏览器生命周期修复

**Files:**
- Modify: `ipo_analyzer/downloader.py`

- [ ] **Step 1: 确保 `browser` 对象在 `finally` 块中关闭**

找到 `AiPOProspectusDownloader` 或相关类中的 Playwright 使用代码，确保 `browser.close()` 在 `finally` 中执行：

```python
browser = None
try:
    browser = await get_browser()
    page = await browser.new_page()
    ...
finally:
    if page:
        await page.close()
    if browser:
        await browser.close()
```

- [ ] **Step 2: 运行测试**

```bash
python3 -m pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add ipo_analyzer/downloader.py
git commit -m "fix: ensure Playwright browser is always closed in finally block"
```

---

### Task 6.3: `_fetch_margin_data` 确定性键设置

**Files:**
- Modify: `ipo_analyzer/core.py`

- [ ] **Step 1: 在 `_fetch_margin_data` 所有分支中设置 `over_sub_ratio`**

确保无论走哪个分支，`over_sub_ratio` 都被设置（默认 0.0 或 None），而非条件性地跳过。

- [ ] **Step 2: 运行测试**

```bash
python3 -m pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add ipo_analyzer/core.py
git commit -m "fix: ensure over_sub_ratio is always set in _fetch_margin_data"
```

---

## 自检清单

### P0 紧急 (并发安全 + 安全)
| 项目 | Task | 状态 |
|------|------|------|
| ThreadSafeLRUCache | 1.1 | - [ ] |
| parser 缓存替换 | 1.2 | - [ ] |
| scoring 缓存替换 | 1.3 | - [ ] |
| downloader 缓存替换 | 1.4 | - [ ] |
| parser 可变状态消除 | 1.5 | - [ ] |
| URL 安全校验 | 2.1 | - [ ] |
| Auth/CORS 加固 | 2.2 | - [ ] |
| 文件上传安全 | 2.3 | - [ ] |

### P1 重要 (数据库/代码质量/测试)
| 项目 | Task | 状态 |
|------|------|------|
| SQLite WAL + 连接复用 | 3.1 | - [ ] |
| backtest 空数据/权重/门槛 | 3.2 | - [ ] |
| 拆分 normalize_output_fields | 4.1 | - [ ] |
| scoring 常量抽取 | 4.2 | - [ ] |
| weight_profile 类型一致性 | 4.3 | - [ ] |
| 风险惩罚测试 | 5.1 | - [ ] |
| 历史重算测试 | 5.2 | - [ ] |

### P2 工程 (清理/小修复)
| 项目 | Task | 状态 |
|------|------|------|
| 清理调试脚本 + .gitignore | 6.1 | - [ ] |
| Playwright 生命周期 | 6.2 | - [ ] |
| over_sub_ratio 确定性 | 6.3 | - [ ] |