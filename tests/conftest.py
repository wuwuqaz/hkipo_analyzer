"""共享测试 fixtures — 减少重复的内联数据定义。"""

import pytest
import tempfile
import shutil


@pytest.fixture
def base_ipo_data():
    """最小可用的 ipo_data 字典。"""
    return {
        'company_name': '测试公司',
        'hk_code': '09999',
        'margin_total': 100.0,
        'public_offer': 5.0,
        'over_sub_ratio': 50.0,
        'over_sub_ratio_source': 'forecast',
        'market_heat': '热门',
        'apply_start_date': '2026-01-01',
        'apply_end_date': '2026-01-08',
    }


@pytest.fixture
def base_prospectus_info():
    """最小可用的 prospectus_info 字典 — 一个盈利的 hardtech 公司。"""
    return {
        'sector': 'hardtech',
        'offer_price': 10.0,
        'lot_size': 100,
        'market_cap_hkd_million': 5000.0,
        'revenue': 500.0,
        'revenue_y1': 400.0,
        'net_profit': 50.0,
        'gross_margin': 40.0,
        'financial_currency': 'RMB',
        'profitable': True,
        'global_offer_shares': 100_000_000,
        'hk_offer_shares': 10_000_000,
        'shares_in_issue_post_listing': 500_000_000,
        'issuance_ratio_pct': 20.0,
        'public_offer_ratio_pct': 10.0,
        'entry_fee_hkd': 1010.0,
        'parse_success': True,
    }


@pytest.fixture
def tmp_output_dir() -> str:
    """使用 pytest 内置 tmp_path — 替代手动 tempfile.mkdtemp。"""
    d = tempfile.mkdtemp(prefix="hkipo_test_")
    yield d
    try:
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass
