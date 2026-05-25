import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_api_token
from api.config import APIConfig
from api.deps import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/peers", tags=["peers"])


def _load_peer_data():
    from ipo_analyzer.peer_data import PeerDataStore
    store = PeerDataStore()
    return store.load()


def _build_peer_meta(data):
    from ipo_analyzer.peer_comps import _build_peer_meta as _build
    return _build(data) if data else {}


def _flatten_peers(data):
    from ipo_analyzer.peer_data import PeerDataStore
    store = PeerDataStore()
    return store.flatten_peers()


class PeerRefreshRequest(BaseModel):
    dry_run: bool = True
    stale_only: bool = True


class PeerRefreshResponse(BaseModel):
    dry_run: bool
    total: int
    processed: int
    updated: int
    skipped: int
    failed: int
    details: list[dict]


@router.get("/")
async def list_peers(
    sector: Optional[str] = None,
    subsector: Optional[str] = None,
    listed_only: bool = False,
    stale_only: bool = False,
    missing_ps_pe: bool = False,
):
    data = _load_peer_data()
    if not data:
        return {"peers": [], "total": 0}

    from ipo_analyzer.peer_data import PeerDataStore
    store = PeerDataStore()
    peers = store.flatten_peers()

    filtered = []
    for p in peers:
        if sector and p.get("sector") != sector:
            continue
        if subsector and p.get("subsector") != subsector:
            continue
        if listed_only and p.get("type") != "listed":
            continue
        if stale_only and not p.get("is_stale"):
            continue
        if missing_ps_pe and (p.get("ps") is not None and p.get("pe") is not None):
            continue
        filtered.append(p)

    # Build sector/subsector options
    sectors = sorted({p.get("sector") for p in peers if p.get("sector")})
    subsectors = sorted({p.get("subsector") for p in peers if p.get("subsector")})

    return {
        "peers": filtered,
        "total": len(filtered),
        "sectors": sectors,
        "subsectors": subsectors,
    }


@router.get("/meta")
async def get_peer_meta():
    data = _load_peer_data()
    meta = _build_peer_meta(data)
    return meta or {}


@router.post("/refresh")
async def refresh_peers(
    request: PeerRefreshRequest,
    _token: str = Depends(require_api_token),
    config: APIConfig = Depends(get_config),
):
    from ipo_analyzer.peer_data import PeerMetricsUpdater
    updater = PeerMetricsUpdater()

    try:
        result = updater.update_all(stale_only=request.stale_only, dry_run=request.dry_run)
        return PeerRefreshResponse(
            dry_run=request.dry_run,
            total=result.get("total", 0),
            processed=result.get("processed", 0),
            updated=result.get("updated", 0),
            skipped=result.get("skipped", 0),
            failed=result.get("failed", 0),
            details=result.get("details", []),
        )
    except Exception as e:
        logger.error(f"Peer refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Peer refresh failed: {e}")
