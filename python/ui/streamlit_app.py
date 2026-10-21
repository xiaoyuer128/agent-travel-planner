"""
Streamlit 前端 —— 交互式行程规划界面。

运行方式:
  cd python
  streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from models.schemas import TravelPlanState, TravelStyle, UserPreferences
from orchestrator.pipeline import TravelPlanningPipeline

st.set_page_config(page_title="智能旅行规划", page_icon="✈️", layout="wide")


# ━━━━━━━━━━━━━━━━━━ 全局样式 ━━━━━━━━━━━━━━━━━━

CUSTOM_CSS = """
<style>
.block-container { max-width: 1180px; padding-top: 1.2rem; padding-bottom: 3rem; }
[data-testid="stAppViewContainer"] { background: #f4f7fb; }

html, body, p, span, div, label {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

/* Hero 横幅 */
.hero {
  background: linear-gradient(120deg, #16324f 0%, #1f4e8c 45%, #4a5fd0 100%);
  border-radius: 20px;
  padding: 32px 42px;
  color: #fff;
  margin-bottom: 10px;
  box-shadow: 0 12px 32px rgba(31, 78, 140, 0.28);
}
.hero h1 { color: #fff; font-size: 2.15rem; margin: 0 0 8px 0; letter-spacing: 0.5px; }
.hero .sub { font-size: 1.02rem; opacity: 0.92; margin: 0 0 18px 0; }
.hero .badge {
  display: inline-block; background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.30);
  padding: 6px 15px; border-radius: 999px; margin-right: 8px; font-size: 0.85rem;
}

/* 通用卡片 */
.card {
  background: #fff; border-radius: 16px; padding: 20px 22px;
  box-shadow: 0 4px 18px rgba(30, 58, 95, 0.08);
  border: 1px solid #eef1f7; margin-bottom: 14px;
}
.card h3 { margin: 0 0 12px 0; color: #1e3a5f; }

/* 目的地标题 */
.dest-title { font-size: 1.75rem; font-weight: 800; color: #1e3a5f; }
.dest-country { font-size: 1.05rem; color: #6b7c93; margin-left: 6px; }

/* 标签 */
.tag { display: inline-block; background: #eef4ff; color: #2b5cae; border-radius: 8px;
       padding: 3px 11px; font-size: 0.82rem; margin: 2px 5px 2px 0; }
.tag-warn { background: #fff4e6; color: #c46a08; }
.tag-green { background: #e8f7ef; color: #1a7f4b; }

/* 评分条 */
.bar { background: #eef1f7; border-radius: 999px; height: 9px; overflow: hidden; margin: 5px 0 2px; }
.bar > div { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #3a6fd8, #6a5fdf); }

/* Metric 卡 */
.metric-row { display: flex; gap: 12px; margin: 8px 0; }
.metric { flex: 1; background: #f7f9fd; border-radius: 14px; padding: 15px 18px; border: 1px solid #eef1f7; }
.metric .label { font-size: 0.82rem; color: #7c8aa0; }
.metric .value { font-size: 1.45rem; font-weight: 800; color: #1e3a5f; margin-top: 3px; }
.metric .delta { font-size: 0.85rem; }

/* 时间线 */
.timeline-item { display: flex; gap: 14px; padding: 13px 0; border-bottom: 1px dashed #e7ecf4; align-items: flex-start; }
.timeline-item:last-child { border-bottom: none; }
.slot { font-size: 0.78rem; color: #fff; border-radius: 8px; padding: 4px 9px;
        display: inline-block; min-width: 54px; text-align: center; font-weight: 600; }
.slot.morning { background: #f0a020; }
.slot.afternoon { background: #3a6fd8; }
.slot.evening { background: #7a5fd0; }
.act-name { font-weight: 600; color: #1e3a5f; }
.act-meta { font-size: 0.85rem; color: #7c8aa0; }

/* 航班 / 酒店 行 */
.row-between { display: flex; justify-content: space-between; align-items: center;
               border-bottom: 1px solid #f0f3f8; padding: 9px 0; }
.row-between:last-child { border-bottom: none; }

/* 星级 */
.stars { color: #f5b301; letter-spacing: 1px; }
.gray { color: #dfe4ec; }

/* 预算进度条 */
.budget-bar { height: 16px; border-radius: 999px; background: #eef1f7; overflow: hidden; margin: 10px 0; }
.budget-bar > div { height: 100%; border-radius: 999px; }

/* 页脚 */
.footer { text-align: center; color: #a8b4c6; font-size: 0.8rem; margin-top: 22px; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━ 工具函数 ━━━━━━━━━━━━━━━━━━

STYLE_ZH = {
    "comfort": "舒适", "budget": "经济", "luxury": "豪华",
    "adventure": "探险", "cultural": "文化", "relaxation": "休闲",
}
SEASON_ZH = {"spring": "春", "summer": "夏", "autumn": "秋", "winter": "冬"}
COST_ZH = {"low": "低消费", "medium": "中消费", "high": "高消费"}
SLOT = {"morning": ("morning", "🌅 上午"), "afternoon": ("afternoon", "☀️ 下午"), "evening": ("evening", "🌙 晚上")}
CAT = {
    "sightseeing": "🏛️ 观光", "food": "🍜 美食",
    "experience": "🎭 体验", "transport": "🚆 交通",
}


def money(x: float) -> str:
    return f"¥{x:,.0f}"


def t_time(iso: str) -> str:
    return iso.split("T")[1][:5] if "T" in iso else iso


def stars(n: float) -> str:
    n = max(0, min(5, float(n)))
    full = int(round(n))
    return f'<span class="stars">{"★" * full}<span class="gray">{"☆" * (5 - full)}</span></span>'


def season_zh(s: str) -> str:
    return "/".join(SEASON_ZH.get(x.strip(), x) for x in s.split(",") if x.strip()) or "全年"


def html(html_str: str) -> None:
    # 压缩换行与行首缩进，避免被 markdown 解析为缩进代码块导致 HTML 被当作文本显示
    compact = re.sub(r"\n\s*", " ", html_str).strip()
    st.markdown(compact, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━ 渲染函数 ━━━━━━━━━━━━━━━━━━

def render_destination(state: TravelPlanState) -> None:
    d = state.selected_destination
    if not d:
        return
    tags = "".join(
        f'<span class="tag">{COST_ZH.get(d.cost_level, d.cost_level)}</span>'
        f'<span class="tag">最佳季节 {season_zh(d.best_season)}</span>'
        f'<span class="tag {"tag-green" if not d.visa_required else "tag-warn"}">'
        f'{"免签/落地签" if not d.visa_required else "需签证"}</span>'
    )
    highlights = "".join(f'<span class="tag">{h}</span>' for h in d.highlights)
    safety = max(0.0, min(10.0, d.safety_score))
    html(f"""
    <div class="card">
      <div class="dest-title">{d.city}<span class="dest-country">{d.country}</span></div>
      <div style="margin:6px 0 10px;color:#4a5a70;">{d.description}</div>
      <div style="margin:8px 0;">{tags}</div>
      <div style="margin:10px 0 4px;">
        <span style="font-size:.82rem;color:#7c8aa0;">安全评分</span>
        <span style="float:right;font-size:.82rem;font-weight:700;color:#1e3a5f;">{d.safety_score:.1f} / 10</span>
        <div class="bar"><div style="width:{safety * 10:.0f}%"></div></div>
      </div>
      <div style="margin-top:8px;">{highlights}</div>
    </div>
    """)


def render_flights(state: TravelPlanState) -> None:
    fr = state.flight_result
    if not fr:
        return
    cards = ""
    if fr.recommended_outbound:
        o = fr.recommended_outbound
        cards += (
            f'<div class="metric"><div class="label">去程推荐</div>'
            f'<div class="value">{o.airline} {o.flight_no}</div>'
            f'<div class="delta">{t_time(o.departure_time)} → {t_time(o.arrival_time)} · {o.duration_hours:.1f}h · {o.stops} 中转</div>'
            f'<div class="value" style="color:#2b5cae;">{money(o.price)}</div></div>'
        )
    if fr.recommended_return:
        r = fr.recommended_return
        cards += (
            f'<div class="metric"><div class="label">返程推荐</div>'
            f'<div class="value">{r.airline} {r.flight_no}</div>'
            f'<div class="delta">{t_time(r.departure_time)} → {t_time(r.arrival_time)} · {r.duration_hours:.1f}h · {r.stops} 中转</div>'
            f'<div class="value" style="color:#2b5cae;">{money(r.price)}</div></div>'
        )
    if cards:
        html(f'<div class="metric-row">{cards}</div>')

    # 备选航班
    for label, flights in (("去程", fr.outbound_flights), ("返程", fr.return_flights)):
        if not flights:
            continue
        rows = "".join(
            f'<div class="row-between">'
            f'<span style="font-weight:600;color:#1e3a5f;">{f.airline} {f.flight_no}</span>'
            f'<span style="color:#7c8aa0;font-size:.85rem;">{t_time(f.departure_time)} → {t_time(f.arrival_time)} · {f.duration_hours:.1f}h · {f.stops}停</span>'
            f'<span style="font-weight:700;color:#1e3a5f;">{money(f.price)}</span>'
            f'</div>'
            for f in flights
        )
        html(f'<div class="card"><h3>🛫 {label}航班</h3>{rows}</div>')

    html(f'<div style="font-size:.9rem;color:#4a5a70;">航班总费用：<b>{money(fr.total_flight_cost)}</b></div>')


def render_hotels(state: TravelPlanState) -> None:
    hr = state.hotel_result
    if not hr:
        return
    if hr.recommended:
        h = hr.recommended
        html(f"""
        <div class="metric-row">
          <div class="metric"><div class="label">推荐酒店</div>
            <div class="value" style="font-size:1.2rem;">{h.name}</div>
            <div class="delta">{stars(h.star_rating)} · 评分 {h.user_rating:.1f}/10 · 距市中心 {h.distance_to_center_km:.1f}km</div>
            <div class="value" style="color:#2b5cae;">{money(h.price_per_night)}/晚 × {hr.total_nights} 晚</div>
          </div>
        </div>
        """)
    rows = "".join(
        f'<div class="row-between">'
        f'<span style="font-weight:600;color:#1e3a5f;">{h.name} {stars(h.star_rating)}</span>'
        f'<span style="color:#7c8aa0;font-size:.85rem;">{", ".join(h.amenities[:4])}</span>'
        f'<span style="font-weight:700;color:#1e3a5f;">{money(h.price_per_night)}/晚</span>'
        f'</div>'
        for h in hr.hotels
    )
    html(f'<div class="card"><h3>🏨 全部酒店（{len(hr.hotels)} 家）</h3>{rows}</div>')
    html(f'<div style="font-size:.9rem;color:#4a5a70;">酒店总费用：<b>{money(hr.total_hotel_cost)}</b></div>')


def render_itinerary(state: TravelPlanState) -> None:
    ar = state.activity_result
    if not ar:
        return
    for day in ar.day_plans:
        items = ""
        for act in day.activities:
            slot_cls, slot_label = SLOT.get(act.time_slot, ("", act.time_slot))
            cat_label = CAT.get(act.category, act.category)
            price_str = "免费" if act.price <= 0 else money(act.price)
            items += f"""
            <div class="timeline-item">
              <div style="flex-shrink:0;"><span class="slot {slot_cls}">{slot_label}</span></div>
              <div>
                <div class="act-name">{act.name} <span style="color:#7c8aa0;font-weight:400;">· {cat_label}</span></div>
                <div class="act-meta">{act.duration_hours:.1f} 小时 · {price_str}
                  {f' · 评分 {act.rating:.1f}' if act.rating else ''}</div>
              </div>
            </div>
            """
        html(f'<div class="card"><h3 style="margin-bottom:4px;">📅 {day.date}</h3>'
             f'<div style="font-size:.82rem;color:#7c8aa0;margin-bottom:4px;">当日花费 {money(day.day_cost)}</div>{items}</div>')


def render_budget(state: TravelPlanState) -> None:
    bb = state.budget_breakdown
    if not bb:
        return
    total = bb.total_cost
    budget = max(bb.budget, 1)
    used_pct = min(100.0, total / budget * 100)
    bar_color = "#1a9e63" if bb.is_within_budget else "#e05555"
    within_txt = "✅ 预算内" if bb.is_within_budget else f"⚠️ 超预算 {money(bb.over_budget_amount)}"
    html(f"""
    <div class="metric-row">
      <div class="metric"><div class="label">航班</div><div class="value">{money(bb.flight_cost)}</div></div>
      <div class="metric"><div class="label">酒店</div><div class="value">{money(bb.hotel_cost)}</div></div>
      <div class="metric"><div class="label">活动</div><div class="value">{money(bb.activity_cost)}</div></div>
    </div>
    <div class="card">
      <h3 style="margin-bottom:2px;">💰 预算使用情况</h3>
      <div style="display:flex;justify-content:space-between;align-items:baseline;">
        <span style="font-size:1.6rem;font-weight:800;color:#1e3a5f;">{money(total)}</span>
        <span style="color:#7c8aa0;">总预算 {money(budget)}</span>
      </div>
      <div class="budget-bar"><div style="width:{used_pct:.1f}%;background:{bar_color};"></div></div>
      <div style="display:flex;justify-content:space-between;font-size:.85rem;color:#7c8aa0;">
        <span>{used_pct:.0f}% 已使用</span>
        <span style="font-weight:700;color:{bar_color};">{within_txt}</span>
      </div>
    </div>
    """)
    if state.adjustment_round > 0:
        st.info(f"经过 {state.adjustment_round} 轮预算自动调整")
    if bb.suggestions:
        html('<div class="card"><h3>💡 预算优化建议</h3>' +
             "".join(f'<div style="padding:4px 0;color:#4a5a70;">· {s}</div>' for s in bb.suggestions) +
             '</div>')


def render_empty() -> None:
    html("""
    <div class="card">
      <h3>🏗️ 如何工作</h3>
      <div style="color:#4a5a70;line-height:1.9;">
        用户输入 → <b>Preference Agent</b> → <b>Destination Agent</b><br>
        → <b>Flight + Hotel + Activity</b>（三 Agent 并行搜索）<br>
        → <b>Budget Agent</b>（预算校验，超预算自动循环调整）→ 输出最终行程
      </div>
    </div>
    """)

    agents = [
        ("🎯", "Preference Agent", "收集用户偏好：预算 / 风格 / 时间 / 禁忌"),
        ("🌍", "Destination Agent", "推荐目的地：季节 / 签证 / 安全 / 性价比"),
        ("✈️", "Flight Agent", "搜索航班、比价、推荐最优组合"),
        ("🏨", "Hotel Agent", "搜索酒店，匹配偏好与房型"),
        ("🎡", "Activity Agent", "生成每日行程与活动安排"),
        ("💰", "Budget Agent", "预算追踪，超预算自动降级调整"),
    ]
    cols = st.columns(3)
    for i, (icon, name, desc) in enumerate(agents):
        with cols[i % 3]:
            html(f"""
            <div class="card" style="text-align:center;padding:18px 14px;">
              <div style="font-size:2rem;">{icon}</div>
              <div style="font-weight:700;color:#1e3a5f;margin:6px 0 2px;">{name}</div>
              <div style="font-size:.82rem;color:#7c8aa0;">{desc}</div>
            </div>
            """)


# ━━━━━━━━━━━━━━━━━━ 页面主体 ━━━━━━━━━━━━━━━━━━

html("""
<div class="hero">
  <h1>✈️ 智能旅行规划</h1>
  <p class="sub">6 个 AI Agent 协作，输入预算与偏好，一键生成完整行程</p>
  <div>
    <span class="badge">⚡ 6-Agent 协作</span>
    <span class="badge">🔀 并行搜索</span>
    <span class="badge">💰 智能预算控制</span>
  </div>
</div>
""")

left, right = st.columns([1, 1.85])

with left:
    st.markdown("#### 📝 旅行偏好")
    default_start = date.today() + timedelta(days=7)
    default_end = default_start + timedelta(days=4)

    with st.form("pref_form"):
        budget = st.number_input("总预算（¥）", min_value=1000, max_value=500000, value=10000, step=1000)
        departure = st.text_input("出发城市", value="北京")
        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("出发日期", value=default_start)
        with c2:
            end_date = st.date_input("返回日期", value=default_end)
        style = st.selectbox(
            "旅行风格",
            list(STYLE_ZH.keys()),
            format_func=lambda x: STYLE_ZH[x],
        )
        travelers = st.number_input("出行人数", min_value=1, max_value=10, value=1)
        interests = st.multiselect("兴趣标签", ["美食", "历史", "艺术", "自然", "购物", "摄影", "运动"],
                                   default=["美食", "历史"])
        notes = st.text_area("额外备注", placeholder="例：不吃辣、需要无障碍设施…")

        submitted = st.form_submit_button("🚀 开始规划", type="primary", use_container_width=True)

    if submitted:
        if end_date < start_date:
            st.error("返回日期不能早于出发日期")
        else:
            with st.spinner("6 个 Agent 正在协作规划您的行程…"):
                prefs = UserPreferences(
                    budget=float(budget),
                    travel_style=TravelStyle(style),
                    departure_city=departure,
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                    num_travelers=travelers,
                    interests=interests,
                    notes=notes,
                )
                pipeline = TravelPlanningPipeline()
                state = asyncio.run(pipeline.run(prefs))
                st.session_state["plan_state"] = state

with right:
    state: TravelPlanState | None = st.session_state.get("plan_state")
    if state is None:
        st.info("👈 请在左侧填写旅行偏好，然后点击「开始规划」")
        render_empty()
    else:
        st.success("行程规划完成！")
        render_destination(state)

        tab1, tab2, tab3, tab4 = st.tabs(["🛫 航班", "🏨 酒店", "📅 每日行程", "💰 预算"])
        with tab1:
            render_flights(state)
        with tab2:
            render_hotels(state)
        with tab3:
            render_itinerary(state)
        with tab4:
            render_budget(state)

        if state.error_messages:
            for msg in state.error_messages:
                st.warning(msg)

html('<div class="footer">多 Agent 智能旅游行程规划系统 · 6-Agent Pipeline + 并行搜索 + 预算循环</div>')