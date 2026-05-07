"""同行库管理页面 — Streamlit UI"""

import os
import logging

logger = logging.getLogger(__name__)

try:
    import streamlit as st
except ImportError:
    st = None


def _format(v, suffix=""):
    if v is None or v == "":
        return "--"
    if isinstance(v, (int, float)):
        fv = float(v)
        if '.' in suffix and suffix.endswith('%'):
            return f"{fv:.1f}{suffix}"
        return f"{fv:.2f}{suffix}" if fv != int(fv) else f"{int(fv)}{suffix}"
    return str(v)


def _data_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "peer_comps.yaml",
    )


class PeerAdminPage:
    def __init__(self):
        self._store = None
        self._updater = None

    @property
    def store(self):
        if self._store is None:
            from ipo_analyzer.peer_data import PeerDataStore
            self._store = PeerDataStore()
        return self._store

    @property
    def updater(self):
        if self._updater is None:
            from ipo_analyzer.peer_data import PeerMetricsUpdater
            self._updater = PeerMetricsUpdater()
        return self._updater

    def render(self):
        if st is None:
            return
        st.markdown("""
        <div style="background:linear-gradient(135deg,#1e293b 0%,#334155 100%);border-radius:20px;padding:24px 32px;color:white;margin-bottom:24px;">
            <h1 style="color:white;font-size:26px;margin:0;">🧩 同行库管理</h1>
            <p style="color:#94a3b8;margin:4px 0 0;font-size:14px;">
                管理同行对比数据库 · 更新行情数据 · 查看过期标记
            </p>
        </div>
        """, unsafe_allow_html=True)

        from ipo_analyzer.peer_comps import _load_peer_data, _build_peer_meta
        raw = _load_peer_data()
        meta = _build_peer_meta(raw) if raw else {}

        if not raw:
            st.warning("同行数据库未加载，请确认 data/peer_comps.yaml 存在")
            return

        # ---- Meta 信息 ----
        with st.expander("📋 数据库元信息", expanded=False):
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                st.metric("数据日期", meta.get("peer_data_source_date", "--"))
            with c2:
                st.metric("最近检查", meta.get("peer_data_last_checked_at", "--"))
            with c3:
                st.metric("数据质量", meta.get("peer_data_quality", "--"))
            with c4:
                age = meta.get("peer_data_age_days", "?")
                stale = meta.get("peer_data_is_stale", False)
                st.metric("数据年龄", f"{age} 天",
                          delta="⚠ 已过期" if stale else "✓ 有效")
            with c5:
                st.metric("过期阈值", f"{meta.get('peer_data_stale_after_days', 90)} 天")

            update_script = (raw or {}).get("meta", {}).get("update_script", "--")
            st.caption(f"**更新脚本**: `{update_script}`")
            st.caption(f"**数据路径**: `{_data_path()}`")
            if meta.get("peer_data_is_stale"):
                st.warning("⚠ 同行数据已过期，建议刷新")

        # ---- 更新按钮（两阶段：预览 → 确认写入） ----
        st.markdown("---")
        st.markdown("**🔄 行情更新**")
        confirm_write = st.checkbox("我确认要写入并覆盖同行库动态指标", key="peer_write_confirm")

        col_preview_stale, col_write_stale, col_preview_all, col_write_all = st.columns(4)
        with col_preview_stale:
            if st.button("👁 预览过期同行", use_container_width=True):
                with st.spinner("dry-run 预览过期..."):
                    r = self.updater.update_all(stale_only=True, dry_run=True)
                    st.session_state["peer_preview_result"] = r
                    st.session_state["peer_preview_type"] = "stale"
        with col_write_stale:
            if st.button("✅ 写入过期同行", use_container_width=True, disabled=not confirm_write):
                with st.spinner("正在写入过期同行..."):
                    try:
                        r = self.updater.update_all(stale_only=True, dry_run=False)
                        st.success(f"已写入: 更新{r['updated']} 跳过{r['skipped_private']} 失败{r['failed']}")
                    except Exception as e:
                        st.warning(f"⚠ 更新失败: {e}")
        with col_preview_all:
            if st.button("👁 预览全部同行", use_container_width=True):
                with st.spinner("dry-run 预览全部..."):
                    r = self.updater.update_all(stale_only=False, dry_run=True)
                    st.session_state["peer_preview_result"] = r
                    st.session_state["peer_preview_type"] = "all"
        with col_write_all:
            if st.button("✅ 写入全部同行", use_container_width=True, disabled=not confirm_write):
                with st.spinner("正在写入全部同行..."):
                    try:
                        r = self.updater.update_all(stale_only=False, dry_run=False)
                        st.success(f"已写入: 更新{r['updated']} 跳过{r['skipped_private']} 失败{r['failed']}")
                    except Exception as e:
                        st.warning(f"⚠ 更新失败: {e}")

        # 展示预览结果
        if "peer_preview_result" in st.session_state and st.session_state["peer_preview_result"]:
            r = st.session_state["peer_preview_result"]
            ptype = st.session_state.get("peer_preview_type", "?")
            previewed = r.get("previewed", 0)
            updated = r.get("updated", 0)
            failed = r.get("failed", 0)
            title = f"📋 预览结果 ({ptype}): 已预览{previewed} 失败{failed}"
            with st.expander(title, expanded=True):
                st.caption(f"总处理: {r.get('total', 0)} | 已预览: {previewed} | 失败: {failed}")
                for d in r.get("details", []):
                    t = d.get("ticker", "?")
                    if d.get("failed"):
                        st.caption(f"  ⚠ {t}: {d.get('error') or d.get('warning', '')}"[:120])
                    else:
                        ps = d.get("ps") or d.get("metrics", {}).get("ps", "--")
                        pe = d.get("pe") or d.get("metrics", {}).get("pe", "--")
                        dq = d.get("data_quality") or d.get("metrics", {}).get("data_quality", "?")
                        nr = d.get("needs_refresh") or d.get("metrics", {}).get("needs_refresh", False)
                        warn = d.get("warning")
                        st.caption(
                            f"  ✓ {t}: PS={ps} PE={pe} 质量={dq} {'[需刷新]' if nr else ''}"
                            + (f" ⚠{warn}" if warn else "")
                        )

        # ---- YAML 下载 ----
        st.markdown("---")
        yaml_path = _data_path()
        if os.path.exists(yaml_path):
            with open(yaml_path, "rb") as f:
                st.download_button("📥 下载 peer_comps.yaml", f.read(),
                                   "peer_comps.yaml", "application/x-yaml")
        else:
            st.warning("peer_comps.yaml 未找到")

        # ---- 筛选 ----
        st.markdown("---")
        st.markdown("**🔍 同行库数据**")
        sub_col1, sub_col2, sub_col3, sub_col4, sub_col5, sub_col6 = st.columns(6)
        flatten = self.store.flatten_peers()
        sectors = sorted(set(r["sector"] for r in flatten))
        subsectors = sorted(set(r["subsector"] for r in flatten))

        with sub_col1:
            sel_sector = st.selectbox("行业", [""] + sectors)
        with sub_col2:
            sub_opts = [""] + [s for s in subsectors
                               if not sel_sector
                               or s in {r["subsector"] for r in flatten if r["sector"] == sel_sector}]
            sel_subsector = st.selectbox("细分赛道", sub_opts)
        with sub_col3:
            only_listed = st.checkbox("仅上市")
        with sub_col4:
            need_refresh = st.checkbox("需刷新")
        with sub_col5:
            missing_ps_pe = st.checkbox("缺PS/PE")
        with sub_col6:
            low_quality = st.checkbox("低质量")

        # ---- 表格 ----
        filtered = list(flatten)
        if sel_sector:
            filtered = [r for r in filtered if r["sector"] == sel_sector]
        if sel_subsector:
            filtered = [r for r in filtered if r["subsector"] == sel_subsector]
        if only_listed:
            filtered = [r for r in filtered if r["type"] == "listed"]
        if need_refresh:
            filtered = [r for r in filtered if r.get("needs_refresh")]
        if missing_ps_pe:
            filtered = [r for r in filtered if r["type"] == "listed"
                        and r.get("ps") is None and r.get("pe") is None]
        if low_quality:
            filtered = [r for r in filtered if r.get("data_quality") == "low"]

        if not filtered:
            st.info("无匹配记录")
            return

        st.markdown(f"**{len(filtered)}** 条记录")
        import pandas as pd
        df_rows = []
        for r in filtered:
            df_rows.append({
                "行业": r["sector"],
                "赛道": r["subsector"],
                "名称": r["name"],
                "代码": r["ticker"],
                "类型": r["type"],
                "PS": _format(r["ps"]),
                "PE": _format(r["pe"]),
                "市值(HKD M)": _format(r["market_cap_hkd_million"]),
                "收入(HKD M)": _format(r["revenue_million"]),
                "净利(HKD M)": _format(r["net_profit_million"]),
                "毛利率": _format(r["gross_margin_pct"], "%"),
                "收入增速": _format(r["revenue_growth_pct"], "%"),
                "数据来源": r.get("source_date", "--") or "--",
                "币种": r.get("currency") or "--",
                "财表币种": r.get("financial_currency") or "--",
                "数据质量": r.get("data_quality", "--") or "--",
                "需刷新": "⚠" if r.get("needs_refresh") else "—",
                "最近检查": r.get("last_checked_at", "--") or "--",
                "错误": r.get("update_error", "") or "",
            })
        df = pd.DataFrame(df_rows)
        st.dataframe(df, use_container_width=True, hide_index=True,
                     height=min(500, len(df) * 36 + 50))
