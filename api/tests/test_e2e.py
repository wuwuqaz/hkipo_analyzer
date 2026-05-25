import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_TOKEN = "test-api-token"


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    os.environ["STORAGE_BASE_PATH"] = tmpdir
    os.environ["HKIPO_API_TOKEN"] = TEST_TOKEN
    os.environ["HKIPO_REQUIRE_API_TOKEN"] = "true"

    import api.routers.analyze as analyze_router
    import api.workers.analyze_worker as analyze_worker
    from api.config import get_config
    from api.main import app
    from api.services.history_service import HistoryService

    config = get_config()
    history_svc = HistoryService(str(config.db_path))
    history_svc.init_db()

    def _write_result(job_id, stock_code, company_name):
        result_path = Path(tmpdir) / "results" / f"{job_id}.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(
                {
                    "company_name": company_name or "TestCo",
                    "hk_code": stock_code or "01234",
                    "score": 75,
                    "ipo_trade_score": 80,
                    "long_term_score": 60,
                    "subscription_recommendation": "积极申购",
                    "score_breakdown": {
                        "heat": {"score": 85, "label": "强", "detail": "超购 399x"},
                        "quality": {"score": 70, "label": "中", "detail": "质地尚可"},
                        "scale": {"score": 65, "label": "中", "detail": "规模中等"},
                        "cornerstone": {"score": 80, "label": "强", "detail": "基石优质"},
                    },
                    "prospectus_info": {
                        "offer_price": 10.0,
                        "lot_size": 500,
                        "market_cap_hkd_million": 5000,
                        "sector": "healthcare",
                        "valuation": {
                            "pe_ratio": 25.0,
                            "ps_ratio": 5.0,
                            "valuation_label": "合理",
                            "cash_runway_years": 3.5,
                        },
                        "risk_factors": {
                            "risks": {
                                "customer_concentration_risk": {
                                    "risk_level": "中",
                                    "evidence_sample": ["前五大客户占比 65%"],
                                }
                            }
                        },
                        "cornerstone_analysis": {
                            "score": 85,
                            "label": "优",
                            "cornerstone_pct": 45.5,
                            "cornerstone_investors": [
                                {"name": "GIC", "tier": "S", "offer_shares_pct": 15.2}
                            ],
                        },
                        "peer_comparison": {
                            "subsector": "biotech",
                            "valuation_position": "合理",
                            "relative_ps_premium_pct": 10,
                            "matched_peers": [
                                {"name": "Peer A", "type": "listed", "ps": 4.5, "pe": 22.0}
                            ],
                        },
                    },
                    "stock_quality": {
                        "score": 72,
                        "label": "良好",
                        "dimensions": {
                            "growth": {"label": "强", "detail": "收入增速 35%"},
                            "profitability": {"label": "中", "detail": "毛利率 55%"},
                            "valuation": {"label": "合理", "detail": "PE 25x"},
                            "risk": {"label": "中", "detail": "客户集中"},
                        },
                    },
                    "signal_breakdown": {
                        "real_money": {"strength": "强", "detail": "孖展 400亿"},
                        "cornerstone_quality": {"strength": "强", "detail": "S级机构参与"},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return str(result_path)

    def fake_run_upload(job_id, upload_path, stock_code, company_name):
        result_path = _write_result(job_id, stock_code, company_name)
        history_svc.update_job_status(job_id, "success", result_path=result_path)

    def fake_run_reanalyze(job_id, stock_code, company_name, historical_market_data):
        result_path = _write_result(job_id, stock_code, company_name)
        history_svc.update_job_status(job_id, "success", result_path=result_path)

    monkeypatch.setattr(analyze_worker, "run_upload_analysis", fake_run_upload)
    monkeypatch.setattr(analyze_router, "run_upload_analysis", fake_run_upload)
    monkeypatch.setattr(analyze_worker, "run_reanalyze", fake_run_reanalyze)
    monkeypatch.setattr(analyze_router, "run_reanalyze", fake_run_reanalyze)

    test_client = TestClient(app)
    yield test_client


def test_full_upload_to_result_flow(client):
    """E2E: upload PDF -> job created -> poll success -> fetch result."""
    pdf_bytes = b"%PDF-1.4 fake pdf content"
    upload_resp = client.post(
        "/api/analyze/upload",
        files={"pdf": ("test.pdf", pdf_bytes, "application/pdf")},
        data={"stock_code": "01234", "company_name": "TestCo"},
        headers=auth_headers(),
    )
    assert upload_resp.status_code == 200
    job = upload_resp.json()
    job_id = job["job_id"]
    assert job["status"] == "queued"

    status_resp = client.get(f"/api/analyze/jobs/{job_id}", headers=auth_headers())
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["status"] == "success"
    assert status["stock_code"] == "01234"
    assert status["company_name"] == "TestCo"

    result_resp = client.get(f"/api/analyze/jobs/{job_id}/result", headers=auth_headers())
    assert result_resp.status_code == 200
    data = result_resp.json()
    assert data["job_id"] == job_id
    result = data["result"]
    assert result["company_name"] == "TestCo"
    assert result["hk_code"] == "01234"
    assert isinstance(result["score"], (int, float))
    assert result["subscription_recommendation"] == "积极申购"
    assert "score_breakdown" in result
    assert "prospectus_info" in result


def test_full_reanalyze_to_result_flow(client):
    """E2E: reanalyze by stock code -> job created -> poll success -> fetch result."""
    reanalyze_resp = client.post(
        "/api/analyze/reanalyze",
        json={"stock_code": "09995", "company_name": "ReanalyzeCo"},
        headers=auth_headers(),
    )
    assert reanalyze_resp.status_code == 200
    job = reanalyze_resp.json()
    job_id = job["job_id"]
    assert job["status"] == "queued"

    status_resp = client.get(f"/api/analyze/jobs/{job_id}", headers=auth_headers())
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["status"] == "success"
    assert status["stock_code"] == "09995"
    assert status["company_name"] == "ReanalyzeCo"

    result_resp = client.get(f"/api/analyze/jobs/{job_id}/result", headers=auth_headers())
    assert result_resp.status_code == 200
    data = result_resp.json()
    assert data["job_id"] == job_id
    result = data["result"]
    assert result["company_name"] == "ReanalyzeCo"
    assert result["hk_code"] == "09995"
    assert isinstance(result["score"], (int, float))


def test_list_jobs_after_upload(client):
    """E2E: upload multiple PDFs -> list jobs -> verify order."""
    job_ids = []
    for i in range(3):
        resp = client.post(
            "/api/analyze/upload",
            files={"pdf": (f"test{i}.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={"stock_code": f"{i:05d}", "company_name": f"Co{i}"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        job_ids.append(resp.json()["job_id"])

    list_resp = client.get("/api/analyze/jobs", headers=auth_headers())
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] >= 3
    returned_ids = {j["job_id"] for j in data["jobs"]}
    for jid in job_ids:
        assert jid in returned_ids
