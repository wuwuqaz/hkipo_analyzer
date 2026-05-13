"""同行库数据服务层 — 半动态同行数据管理与行情更新

组件:
- PeerDataStore: YAML 读写 + 备份 + 批量更新的内存操作
- YahooFinanceProvider: 通过 yfinance 获取行情，正确处理币种和单位
- PeerMetricsUpdater: 批量更新入口，批量备份+写入
"""

import os
import re
import shutil
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

_DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "peer_comps.yaml",
)

# ---------------------------------------------------------------------------
# YAML 工具 (懒加载)
# ---------------------------------------------------------------------------

def _get_yaml():
    try:
        import yaml as _y
        return _y
    except ImportError:
        return None


def _read_yaml(path):
    y = _get_yaml()
    if y is None:
        raise RuntimeError("pyyaml 未安装")
    with open(path, "r", encoding="utf-8") as f:
        return y.safe_load(f)


def _write_yaml(path, data):
    y = _get_yaml()
    if y is None:
        raise RuntimeError("pyyaml 未安装")
    with open(path, "w", encoding="utf-8") as f:
        y.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# 日期 / 数值 / ticker 辅助
# ---------------------------------------------------------------------------

def _parse_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _is_num(x):
    return isinstance(x, (int, float))


def normalize_ticker_for_yahoo(ticker):
    """统一转为 yfinance 可用的 Yahoo ticker"""
    if not ticker or ticker == "private":
        return None
    t = str(ticker).strip()
    # 港股
    if t.endswith('.HK'):
        return t
    if re.match(r'^\d{4,5}$', t):
        return f"{t}.HK"
    # A 股
    if t.endswith('.SH'):
        return t.replace('.SH', '.SS')
    if t.endswith('.SZ'):
        return t.replace('.SZ', '.SZ')  # already correct
    if re.match(r'^6\d{5}$', t):
        return f"{t}.SS"
    if re.match(r'^0\d{5}$', t) or re.match(r'^3\d{5}$', t):
        return f"{t}.SZ"
    # 美股 — 保持原样
    return t.upper()


# 静态汇率表 (HKD base)
_FX_TO_HKD = {
    "HKD": 1.0, "HKD/HKD": 1.0,
    "USD": 7.8, "USD/HKD": 7.8,
    "CNY": 1.08, "CNY/HKD": 1.08,
    "CNH": 1.08, "CNH/HKD": 1.08,
    "RMB": 1.08, "RMB/HKD": 1.08,
}


def get_fx_to_hkd(currency):
    """获取货币对港币汇率，无法识别返回 None"""
    if not currency:
        return None
    cur = str(currency).upper().strip().replace(" ", "")
    if '/' in cur:
        cur = cur.split('/')[0]
    return _FX_TO_HKD.get(cur)


def to_hkd_million(value, currency):
    """转换 value 为 HKD 百万元单位"""
    if not _is_num(value):
        return None
    fx = get_fx_to_hkd(currency)
    if fx is None:
        return None
    return round(value * fx / 1_000_000, 2)


# ---------------------------------------------------------------------------
# PeerDataStore
# ---------------------------------------------------------------------------

class PeerDataStore:
    """YAML 同行库的读写 + 批量操作"""

    def __init__(self, path=None):
        self.path = path or _DEFAULT_DATA_PATH
        self.backup_dir = os.path.join(os.path.dirname(self.path), "backups")

    def load(self):
        if not os.path.exists(self.path):
            return None
        return _read_yaml(self.path)

    def save(self, data):
        self.backup()
        _write_yaml(self.path, data)

    def backup(self):
        os.makedirs(self.backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(self.backup_dir, f"peer_comps_{ts}.yaml")
        try:
            shutil.copy2(self.path, dst)
            logger.info("备份: %s", dst)
        except Exception as e:
            logger.warning("备份失败: %s", e)

    # -- 遍历 --

    def iter_peers(self):
        data = self.load()
        if not data:
            return
        for sec_key, sec_data in data.items():
            if sec_key == "meta":
                continue
            for sub_key, sub_data in sec_data.items():
                if sub_key == "meta":
                    continue
                for peer in sub_data.get("peers", []):
                    yield sec_key, sub_key, peer

    def iter_listed_peers(self):
        for sec, sub, peer in self.iter_peers():
            if peer.get("type") == "listed":
                yield sec, sub, peer

    def get_stale_peers(self, stale_after_days=90):
        stale = []
        today = date.today()
        for sec, sub, peer in self.iter_listed_peers():
            if peer.get("needs_refresh"):
                stale.append((sec, sub, peer))
                continue
            lc = peer.get("last_checked_at")
            if lc:
                lc_dt = _parse_date(lc)
                if lc_dt and (today - lc_dt).days > stale_after_days:
                    stale.append((sec, sub, peer))
                    continue
            if peer.get("ps") is None and peer.get("pe") is None:
                stale.append((sec, sub, peer))
        return stale

    # -- 更新 (无自动 save) --

    @staticmethod
    def apply_metrics_to_peer(peer, metrics):
        """修改 peer dict（无 IO）"""
        today_str = date.today().isoformat()
        for field in ("market_cap_hkd_million", "revenue_million",
                      "net_profit_million", "ps", "pe",
                      "gross_margin_pct", "revenue_growth_pct"):
            if field in metrics and metrics[field] is not None:
                peer[field] = metrics[field]
        peer["source_date"] = today_str
        peer["last_checked_at"] = today_str
        peer["data_quality"] = metrics.get("data_quality", "moderate")
        peer["needs_refresh"] = bool(metrics.get("needs_refresh", False))
        if "update_error" in metrics:
            peer["update_error"] = metrics["update_error"]
        else:
            peer.pop("update_error", None)
        # 保留 currency 信息
        if "currency" in metrics:
            peer["currency"] = metrics["currency"]
        if "financial_currency" in metrics:
            peer["financial_currency"] = metrics["financial_currency"]

    @staticmethod
    def apply_metrics_to_data(data, ticker, metrics):
        """在 data dict 中找到对应 ticker 并更新，返回是否找到"""
        for sec_key, sec_data in data.items():
            if sec_key == "meta":
                continue
            for sub_key, sub_data in sec_data.items():
                if sub_key == "meta":
                    continue
                for peer in sub_data.get("peers", []):
                    if str(peer.get("ticker", "")).strip() != str(ticker).strip():
                        continue
                    PeerDataStore.apply_metrics_to_peer(peer, metrics)
                    return True
        return False

    # -- 单个写入（保持兼容） --

    def update_peer_metrics(self, ticker, metrics):
        """更新单个 ticker（会读取→修改→写回，适合单次操作）"""
        data = self.load()
        if not data:
            return False
        found = self.apply_metrics_to_data(data, ticker, metrics)
        if found:
            self.save(data)
        return found

    def flatten_peers(self):
        rows = []
        for sec, sub, peer in self.iter_peers():
            row = {
                "sector": sec,
                "subsector": sub,
                "name": peer.get("name", ""),
                "ticker": peer.get("ticker", ""),
                "type": peer.get("type", "unknown"),
                "ps": peer.get("ps"),
                "pe": peer.get("pe"),
                "market_cap_hkd_million": peer.get("market_cap_hkd_million"),
                "revenue_million": peer.get("revenue_million"),
                "net_profit_million": peer.get("net_profit_million"),
                "gross_margin_pct": peer.get("gross_margin_pct"),
                "revenue_growth_pct": peer.get("revenue_growth_pct"),
                "data_quality": peer.get("data_quality"),
                "needs_refresh": peer.get("needs_refresh", False),
                "last_checked_at": peer.get("last_checked_at"),
                "source_date": peer.get("source_date"),
                "currency": peer.get("currency"),
                "financial_currency": peer.get("financial_currency"),
                "update_error": peer.get("update_error"),
                "notes": peer.get("notes", ""),
            }
            rows.append(row)
        return rows


# ---------------------------------------------------------------------------
# YahooFinanceProvider — 正确处理币种和单位
# ---------------------------------------------------------------------------

class YahooFinanceProvider:
    """通过 yfinance 获取行情，用法如下:

    provider = YahooFinanceProvider()
    metrics = provider.fetch_metrics("2498.HK")
    # metrics 已包含 market_cap_hkd_million, revenue_million, ps, pe 等
    # 所有数值字段均为 HKD million 单位
    """

    def fetch_metrics(self, ticker: str) -> dict:
        empty = {
            "market_cap_hkd_million": None, "revenue_million": None,
            "net_profit_million": None, "ps": None, "pe": None,
            "gross_margin_pct": None, "revenue_growth_pct": None,
            "currency": None, "financial_currency": None,
            "source_date": date.today().isoformat(),
            "last_checked_at": date.today().isoformat(),
            "data_quality": "low", "needs_refresh": True,
        }

        if not ticker or ticker == "private":
            empty["update_error"] = "private ticker — 不获取行情"
            return empty

        yf_ticker = normalize_ticker_for_yahoo(ticker)
        if not yf_ticker:
            empty["update_error"] = f"无法转换为 Yahoo ticker: {ticker}"
            return empty

        try:
            import yfinance as _yf
        except ImportError:
            empty["update_error"] = "yfinance 未安装; pip install yfinance"
            return empty

        # 获取原始数据（对港股尝试去掉前导 0 重试）
        info = None
        tried_tickers = [yf_ticker]
        # 港股 03696.HK → 尝试 3696.HK, 0853.HK → 尝试 853.HK
        if yf_ticker.endswith('.HK') and yf_ticker.startswith('0'):
            alt = yf_ticker.lstrip('0')
            if alt != yf_ticker:
                tried_tickers.append(alt)
        for try_ticker in tried_tickers:
            try:
                stock = _yf.Ticker(try_ticker)
                info = stock.info or {}
                if info and (info.get("marketCap") or info.get("totalRevenue") or info.get("currency")):
                    break
                info = None
            except Exception:
                continue

        if info is None:
            empty["update_error"] = f"yfinance 获取 {yf_ticker} 失败（尝试 {tried_tickers}）"
            return empty

        # 币种判断
        currency = str(info.get("currency") or info.get("financialCurrency") or "").strip()
        financial_currency = str(info.get("financialCurrency") or currency).strip()
        if not currency:
            # 按 yahoo ticker 后缀推断
            if yf_ticker.endswith('.HK'):
                currency = "HKD"
                financial_currency = "HKD"
            elif yf_ticker.endswith('.SS') or yf_ticker.endswith('.SZ'):
                currency = "CNY"
                financial_currency = "CNY"
            else:
                currency = "USD"
                financial_currency = "USD"

        fx = get_fx_to_hkd(currency)
        if fx is None:
            empty["update_error"] = f"无法识别币种 {currency}"
            empty["currency"] = currency
            return empty

        # 提取原始值
        mkt_cap_raw = info.get("marketCap")
        rev_raw = info.get("totalRevenue")
        ni_raw = (info.get("netIncomeToCommon") or info.get("netIncomeToCompany")
                  or info.get("netIncome"))

        # 转换到 HKD million
        mkt_cap_hkd_m = to_hkd_million(mkt_cap_raw, currency)
        rev_hkd_m = to_hkd_million(rev_raw, financial_currency)
        ni_hkd_m = to_hkd_million(ni_raw, financial_currency)

        # 计算 PS / PE（两个都必须是 HKD 单位才能除）
        ps = round(mkt_cap_hkd_m / rev_hkd_m, 2) if _is_num(mkt_cap_hkd_m) and _is_num(rev_hkd_m) and rev_hkd_m > 0 else None
        pe = round(mkt_cap_hkd_m / ni_hkd_m, 2) if _is_num(mkt_cap_hkd_m) and _is_num(ni_hkd_m) and ni_hkd_m > 0 else None

        # 其他财务指标
        gm = info.get("grossMargins")
        gm_pct = round(gm * 100, 1) if _is_num(gm) else None

        rg = info.get("revenueGrowth")
        rg_pct = round(rg * 100, 1) if _is_num(rg) else None

        trailing_pe_raw = info.get("trailingPE")

        result = {
            "market_cap_hkd_million": mkt_cap_hkd_m,
            "revenue_million": rev_hkd_m,
            "net_profit_million": ni_hkd_m,
            "ps": ps,
            "pe": pe,
            "trailing_pe_raw": trailing_pe_raw,
            "gross_margin_pct": gm_pct,
            "revenue_growth_pct": rg_pct,
            "currency": currency,
            "financial_currency": financial_currency,
            "source_date": date.today().isoformat(),
            "last_checked_at": date.today().isoformat(),
            "data_quality": "high" if (_is_num(ps) or _is_num(pe)) else "low",
            "needs_refresh": False,
        }

        # 检查数据完整性
        has_valid = _is_num(mkt_cap_hkd_m) or _is_num(rev_hkd_m)
        if not has_valid:
            result["data_quality"] = "low"
            result["needs_refresh"] = True
            result["update_error"] = f"yfinance 返回 {yf_ticker} 关键数据缺失 (marketCap={mkt_cap_raw}, revenue={rev_raw})"

        return result


# ---------------------------------------------------------------------------
# PeerMetricsUpdater — 批量写入只备份一次
# ---------------------------------------------------------------------------

class PeerMetricsUpdater:
    """批量更新同行库中的行情数据

    写入模式：先 load → 在内存批量修改 → 统一 backup + save
    """

    def __init__(self, data_path=None):
        self.store = PeerDataStore(data_path)
        self.provider = YahooFinanceProvider()

    def update_all(self, stale_only=True, dry_run=True):
        return self._batch_update(stale_only=stale_only, dry_run=dry_run)

    def update_subsector(self, sector, subsector, dry_run=True):
        results = {"total": 0, "processed": 0, "previewed": 0,
                   "updated": 0, "skipped": 0, "failed": 0, "details": []}
        data = self.store.load()
        if not data:
            return results
        sec_data = data.get(sector, {})
        sub_data = sec_data.get(subsector, {})
        peers = sub_data.get("peers", [])
        results["total"] = len(peers)
        for peer in peers:
            ticker = peer.get("ticker", "")
            if not ticker or ticker == "private":
                results["skipped"] += 1
                continue
            r = self._fetch_one(ticker, dry_run)
            if not dry_run and not r.get("failed"):
                self.store.apply_metrics_to_data(data, ticker, r.get("metrics", {}))
            results["updated"] += r.get("updated", 0)
            results["failed"] += r.get("failed", 0)
            results["previewed"] += r.get("previewed", 0)
            results["details"].append(r)

        results["processed"] = results["total"] - results["skipped"]
        if not dry_run and results["updated"] > 0:
            self.store.save(data)

        return results

    def update_ticker(self, ticker, dry_run=True):
        r = self._fetch_one(ticker, dry_run)
        if not dry_run and not r.get("failed"):
            self.store.update_peer_metrics(ticker, r.get("metrics", {}))
        return r

    # -- 内部 --

    def _batch_update(self, stale_only, dry_run):
        results = {"total": 0, "processed": 0, "previewed": 0,
                   "updated": 0, "skipped": 0, "failed": 0, "details": []}

        if stale_only:
            peers = self.store.get_stale_peers()
        else:
            peers = list(self.store.iter_listed_peers())

        results["total"] = len(peers)

        data = self.store.load() if not dry_run else None
        for sec, sub, peer in peers:
            ticker = peer.get("ticker", "")
            if not ticker or ticker == "private":
                results["skipped"] += 1
                continue
            r = self._fetch_one(ticker, dry_run)
            if not dry_run and not r.get("failed") and data:
                self.store.apply_metrics_to_data(data, ticker, r.get("metrics", {}))
            results["updated"] += r.get("updated", 0)
            results["failed"] += r.get("failed", 0)
            results["previewed"] += r.get("previewed", 0)
            results["details"].append(r)

        results["processed"] = results["total"] - results["skipped"]
        if not dry_run and results["updated"] > 0 and data is not None:
            self.store.save(data)

        return results

    def _fetch_one(self, ticker, dry_run):
        try:
            metrics = self.provider.fetch_metrics(ticker)
        except Exception as e:
            return {"ticker": ticker, "updated": 0, "failed": 1, "previewed": 1, "error": str(e),
                    "warning": str(e) if not _is_num(getattr(e, 'args', [None])[0]) else None}

        r = {
            "ticker": ticker,
            "metrics": metrics,
            "market_cap": metrics.get("market_cap_hkd_million"),
            "revenue": metrics.get("revenue_million"),
            "ps": metrics.get("ps"),
            "pe": metrics.get("pe"),
            "data_quality": metrics.get("data_quality"),
            "needs_refresh": metrics.get("needs_refresh"),
            "currency": metrics.get("currency"),
            "financial_currency": metrics.get("financial_currency"),
        }

        if metrics.get("update_error"):
            r["failed"] = 0  # 仍标记为已处理
            r["updated"] = 1 if not dry_run else 0
            r["previewed"] = 1
            r["warning"] = metrics["update_error"]
        else:
            r["failed"] = 0
            r["updated"] = 1 if not dry_run else 0
            r["previewed"] = 1

        return r
