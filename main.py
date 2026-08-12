from datetime import datetime
from html import escape
import json

import streamlit as st
import streamlit.components.v1 as components

from acclimatization import evaluate_acclimatization
from measurement_store import read_measurement
from metabolism import (
    calculate_calories_from_vo2,
    calculate_energy_keytel,
    estimate_vo2_by_hrr,
)
from utils import get_risk_guidance, should_trigger_alert
from wbgt_risk import calculate_heat_risk


def metric_card(label, value, unit, tone="neutral"):
    return (
        f'<article class="metric-card metric-{escape(tone)}">'
        f"<p>{escape(label)}</p>"
        f"<strong>{escape(str(value))}</strong>"
        f"<span>{escape(unit)}</span>"
        "</article>"
    )


def measurement_status(measurement):
    updated_at = measurement.get("updated_at")
    if measurement.get("source") == "computer":
        if updated_at:
            try:
                updated_at = datetime.fromisoformat(updated_at).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
            return "PC 입력 반영", str(updated_at)
        return "PC 입력 반영", "갱신 시각 없음"

    if measurement.get("source") == "sample" and updated_at:
        return "샘플 데이터", f"샘플 시각 {updated_at}"

    return "기본 데이터", "저장된 외부 측정값 없음"


def sex_label(sex):
    return "남성" if sex == "male" else "여성"


def render_device_alert_controls(risk, manager_alert, heart_rate, wbgt, updated_at):
    payload = {
        "risk": risk,
        "managerAlert": manager_alert,
        "heartRate": heart_rate,
        "wbgt": wbgt,
        "updatedAt": updated_at or "no-time",
        "key": f"{updated_at or 'no-time'}-{risk}-{heart_rate}-{wbgt}",
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    components.html(
        f"""
        <div id="alert-root"></div>
        <script>
        const payload = {payload_json};
        const root = document.getElementById("alert-root");
        const enabledKey = "wgbt-device-alert-enabled";
        const lastAlertKey = "wgbt-last-alert-key";

        function readStorage(key) {{
            try {{ return window.localStorage.getItem(key); }}
            catch (_) {{ return null; }}
        }}

        function writeStorage(key, value) {{
            try {{ window.localStorage.setItem(key, value); }}
            catch (_) {{}}
        }}

        function notificationsSupported() {{
            return "Notification" in window && window.isSecureContext;
        }}

        function vibrate(pattern) {{
            if ("vibrate" in navigator) {{
                try {{ navigator.vibrate(pattern); }} catch (_) {{}}
            }}
        }}

        function playAlertSound() {{
            try {{
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                if (!AudioContext) return;
                const context = new AudioContext();
                const gain = context.createGain();
                gain.gain.setValueAtTime(0.0001, context.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.22, context.currentTime + 0.03);
                gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.95);
                gain.connect(context.destination);

                [0, 0.28, 0.56].forEach((offset) => {{
                    const oscillator = context.createOscillator();
                    oscillator.type = "sine";
                    oscillator.frequency.setValueAtTime(880, context.currentTime + offset);
                    oscillator.connect(gain);
                    oscillator.start(context.currentTime + offset);
                    oscillator.stop(context.currentTime + offset + 0.18);
                }});
            }} catch (_) {{}}
        }}

        function sendBrowserNotification() {{
            if (!notificationsSupported() || Notification.permission !== "granted") return;
            try {{
                new Notification("온열 위험도 알람", {{
                    body: `${{payload.risk}} 단계입니다. 심박수 ${{payload.heartRate}} bpm, WBGT ${{Number(payload.wbgt).toFixed(1)}}`,
                    tag: "wgbt-risk-alert",
                    renotify: true,
                }});
            }} catch (_) {{}}
        }}

        async function enableAlerts() {{
            writeStorage(enabledKey, "true");
            if (notificationsSupported() && Notification.permission === "default") {{
                try {{ await Notification.requestPermission(); }} catch (_) {{}}
            }}
            vibrate([80]);
            playAlertSound();
            render();
            maybeTriggerAlert(true);
        }}

        function maybeTriggerAlert(force=false) {{
            const enabled = readStorage(enabledKey) === "true";
            if (!payload.managerAlert || !enabled) return;
            const previousKey = readStorage(lastAlertKey);
            if (!force && previousKey === payload.key) return;
            writeStorage(lastAlertKey, payload.key);
            vibrate([450, 160, 450, 160, 450]);
            playAlertSound();
            sendBrowserNotification();
        }}

        function statusText() {{
            const enabled = readStorage(enabledKey) === "true";
            if (!enabled) return "알림을 받으려면 휴대폰에서 한 번 활성화하세요.";
            if (!notificationsSupported()) return "소리와 진동 알림 활성화됨 · OS 푸시는 HTTPS에서만 가능";
            if (Notification.permission === "granted") return "브라우저 알림, 소리, 진동 활성화됨";
            if (Notification.permission === "denied") return "브라우저 알림 차단됨 · 소리와 진동만 시도";
            return "소리와 진동 활성화됨 · 브라우저 알림 권한 대기";
        }}

        function render() {{
            const enabled = readStorage(enabledKey) === "true";
            const riskMessage = payload.managerAlert
                ? `${{payload.risk}} 단계 감지됨`
                : "위험 이상 단계가 아니면 알림을 울리지 않습니다.";
            root.innerHTML = `
                <style>
                    body {{ margin: 0; font-family: sans-serif; }}
                    .device-alert {{
                        background: ${{payload.managerAlert ? "#fff1f0" : "#ffffff"}};
                        border: 1px solid ${{payload.managerAlert ? "#b42318" : "#d7dee7"}};
                        border-radius: 8px;
                        box-sizing: border-box;
                        color: #101828;
                        padding: 12px 14px;
                    }}
                    .device-alert p {{
                        color: #526070;
                        font-size: 13px;
                        margin: 0 0 8px;
                    }}
                    .device-alert strong {{
                        color: ${{payload.managerAlert ? "#7a271a" : "#101828"}};
                        display: block;
                        font-size: 15px;
                        line-height: 1.4;
                        margin-bottom: 10px;
                    }}
                    .device-alert button {{
                        background: #101828;
                        border: 0;
                        border-radius: 6px;
                        color: white;
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 700;
                        min-height: 40px;
                        padding: 0 14px;
                        width: 100%;
                    }}
                    .device-alert button.enabled {{
                        background: #137a45;
                    }}
                </style>
                <section class="device-alert" aria-live="polite">
                    <p>휴대폰 알림 상태</p>
                    <strong>${{riskMessage}} · ${{statusText()}}</strong>
                    <button id="enable-alerts" class="${{enabled ? "enabled" : ""}}">
                        ${{enabled ? "알림 활성화됨" : "알림 활성화"}}
                    </button>
                </section>
            `;
            document.getElementById("enable-alerts").addEventListener("click", enableAlerts);
        }}

        render();
        maybeTriggerAlert(false);
        </script>
        """,
        height=132,
    )


st.set_page_config(
    page_title="온열 위험도 대시보드",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        :root {
            --ink: #101828;
            --muted: #526070;
            --line: #d7dee7;
            --surface: #ffffff;
            --canvas: #f4f7f9;
            --safe: #84cc16;
            --safe-text: #3f6212;
            --caution: #facc15;
            --caution-text: #854d0e;
            --warning: #f97316;
            --warning-text: #9a3412;
            --danger: #dc2626;
            --danger-text: #991b1b;
        }
        .stApp {
            background: var(--canvas);
            color: var(--ink);
        }
        .block-container {
            max-width: 820px;
            padding-top: 1.8rem;
            padding-bottom: 2.2rem;
        }
        [data-testid="stHeader"] {
            background: transparent;
        }
        h1, h2, h3, p {
            letter-spacing: 0;
        }
        .dashboard-head {
            margin-bottom: 1rem;
        }
        .dashboard-head p {
            color: var(--muted);
            font-size: 0.95rem;
            margin: 0 0 0.25rem;
        }
        .dashboard-head h1 {
            color: var(--ink);
            font-size: 1.85rem;
            line-height: 1.2;
            margin: 0 0 0.45rem;
        }
        .dashboard-head span {
            color: var(--muted);
            display: block;
            font-size: 0.98rem;
            line-height: 1.5;
        }
        .feed-shell {
            border-top: 1px solid var(--line);
            margin: 0 0 1rem;
            padding-top: 0.9rem;
        }
        .feed-shell h2 {
            color: var(--ink);
            font-size: 1rem;
            margin: 0 0 0.15rem;
        }
        .feed-shell p {
            color: var(--muted);
            font-size: 0.9rem;
            margin: 0 0 0.35rem;
        }
        .feed-status {
            align-items: center;
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            justify-content: space-between;
            margin: 0 0 0.9rem;
            padding: 0.72rem 0.9rem;
        }
        .feed-status strong {
            color: var(--ink);
            font-size: 0.98rem;
        }
        .feed-status span {
            color: var(--muted);
            font-size: 0.88rem;
        }
        .risk-panel {
            background: var(--surface);
            border: 1px solid var(--line);
            border-left-width: 8px;
            border-radius: 8px;
            margin: 0.7rem 0 0.9rem;
            padding: 1rem;
        }
        .manager-alert {
            animation: pulse-alert 1.4s ease-in-out infinite;
            background: #fff1f0;
            border: 2px solid #b42318;
            border-radius: 8px;
            color: #7a271a;
            margin: 0 0 0.9rem;
            padding: 0.9rem 1rem;
        }
        .manager-alert p {
            color: #7a271a;
            font-size: 0.86rem;
            font-weight: 700;
            margin: 0 0 0.32rem;
        }
        .manager-alert strong {
            color: #7a271a;
            display: block;
            font-size: 1.12rem;
            line-height: 1.45;
        }
        @keyframes pulse-alert {
            0%, 100% {
                box-shadow: 0 0 0 0 rgba(180, 35, 24, 0.22);
            }
            50% {
                box-shadow: 0 0 0 6px rgba(180, 35, 24, 0.08);
            }
        }
        .risk-panel p {
            color: var(--muted);
            font-size: 0.88rem;
            margin: 0 0 0.35rem;
        }
        .risk-title {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-bottom: 0.45rem;
        }
        .risk-title h2 {
            color: var(--ink);
            font-size: 1.65rem;
            line-height: 1.25;
            margin: 0;
        }
        .risk-badge {
            border-radius: 999px;
            border: 1px solid currentColor;
            font-size: 0.82rem;
            font-weight: 700;
            line-height: 1;
            padding: 0.45rem 0.62rem;
        }
        .risk-panel strong {
            color: var(--ink);
            display: block;
            font-size: 1.05rem;
            line-height: 1.55;
        }
        .risk-rest {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin: 0 0 0.55rem;
        }
        .risk-rest p {
            margin: 0;
        }
        .risk-rest span {
            background: #f7f9fb;
            border: 1px solid var(--line);
            border-radius: 999px;
            color: var(--ink);
            font-size: 0.92rem;
            font-weight: 700;
            padding: 0.35rem 0.58rem;
        }
        .risk-safe {
            border-left-color: var(--safe);
        }
        .risk-safe .risk-badge {
            background: #ecfccb;
            color: var(--safe-text);
        }
        .risk-caution {
            border-left-color: var(--caution);
        }
        .risk-caution .risk-badge {
            background: #fef9c3;
            color: var(--caution-text);
        }
        .risk-warning {
            border-left-color: var(--warning);
        }
        .risk-warning .risk-badge {
            background: #ffedd5;
            color: var(--warning-text);
        }
        .risk-danger {
            border-left-color: var(--danger);
        }
        .risk-danger .risk-badge {
            background: #fee2e2;
            color: var(--danger-text);
        }
        .metric-grid, .detail-grid {
            display: grid;
            gap: 0.72rem;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            margin-bottom: 0.95rem;
        }
        .metric-card, .detail-card, .notice {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
        }
        .metric-card {
            min-height: 126px;
            padding: 0.9rem;
        }
        .metric-card p, .detail-card p {
            color: var(--muted);
            font-size: 0.88rem;
            margin: 0 0 0.42rem;
        }
        .metric-card strong {
            color: var(--ink);
            display: block;
            font-size: 1.85rem;
            line-height: 1.2;
            margin-bottom: 0.25rem;
            overflow-wrap: anywhere;
        }
        .metric-card span {
            color: var(--muted);
            display: block;
            font-size: 0.92rem;
            line-height: 1.3;
        }
        .metric-heart strong {
            color: #b42318;
        }
        .metric-wbgt strong {
            color: #006d77;
        }
        .detail-card {
            min-height: 104px;
            padding: 0.9rem;
        }
        .detail-card strong {
            color: var(--ink);
            display: block;
            font-size: 1.18rem;
            line-height: 1.35;
            overflow-wrap: anywhere;
        }
        .notice {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.55;
            margin-top: 0.15rem;
            padding: 0.9rem;
        }
        @media (max-width: 640px) {
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
                padding-top: 1.1rem;
            }
            .dashboard-head h1 {
                font-size: 1.55rem;
            }
            .metric-grid {
                grid-template-columns: 1fr;
            }
            .detail-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .metric-card {
                min-height: 96px;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <header class="dashboard-head">
        <p>현장 관리자 대시보드</p>
        <h1>온열 위험도</h1>
        <span>PC 입력 페이지나 센서 입력기가 보낸 단일 작업자 값으로 위험 단계와 휴식 권고를 확인합니다.</span>
    </header>
    <section class="feed-shell">
        <h2>수신된 측정값</h2>
        <p>저장된 심박수와 온열지수(WBGT)를 읽어 대시보드를 갱신합니다.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

@st.experimental_fragment(run_every=2)
def render_live_dashboard():
    measurement = read_measurement()
    heart_rate = measurement["heart_rate"]
    wbgt = measurement["wbgt"]
    age = measurement["age"]
    weight = measurement["weight"]
    sex = measurement["sex"]
    status_title, status_detail = measurement_status(measurement)

    try:
        resting_hr = 65
        clothing_adjustment = 0.0
        acclimatization = evaluate_acclimatization(
            worker_status=measurement["worker_status"],
            heat_exposure_days=measurement["heat_exposure_days"],
            absence_days=measurement["absence_days"],
            similar_heat_work=measurement["similar_heat_work"],
        )

        vo2, hrr_ratio, hr_max = estimate_vo2_by_hrr(
            age=age,
            sex=sex,
            heart_rate=heart_rate,
            resting_hr=resting_hr,
        )

        kcal_from_vo2 = calculate_calories_from_vo2(vo2, weight)

        kcal = calculate_energy_keytel(
            heart_rate=heart_rate,
            weight=weight,
            age=age,
            sex=sex,
        )

        risk_result = calculate_heat_risk(
            wbgt=wbgt,
            kcal_min=kcal,
            acclimatized=acclimatization["acclimatized"],
            clothing_adjustment=clothing_adjustment,
        )

        risk = risk_result["risk"]
        workload = risk_result["workload"]
        metabolic_watts = risk_result["metabolic_watts"]
        limit_type = risk_result["limit_type"]
        limit_wbgt = risk_result["limit_wbgt"]
        adjusted_wbgt = risk_result["adjusted_wbgt"]
        margin = risk_result["margin"]

        guidance = get_risk_guidance(
            risk=risk,
            margin=margin,
            workload=workload,
            acclimatized=acclimatization["acclimatized"],
            limit_type=limit_type,
        )
        manager_alert = should_trigger_alert(risk)

    except ValueError as error:
        st.error(str(error))
        return

    alert_markup = ""
    if manager_alert:
        alert_markup = f"""
        <section class="manager-alert" data-testid="manager-alert" role="alert" aria-live="assertive">
            <p>작업관리자 알람</p>
            <strong>{escape(risk)} 단계입니다. 즉시 작업자 상태를 확인하고 휴식 조치를 지시하세요.</strong>
        </section>
        """

    render_device_alert_controls(
        risk=risk,
        manager_alert=manager_alert,
        heart_rate=heart_rate,
        wbgt=wbgt,
        updated_at=measurement.get("updated_at"),
    )

    st.markdown(
        f"""
        <section class="feed-status" data-testid="feed-status">
            <strong>{escape(status_title)}</strong>
            <span>{escape(status_detail)}</span>
        </section>
        {alert_markup}
        <section class="risk-panel risk-{escape(guidance["tone"])}" data-testid="risk-panel">
            <p>현재 위험도 단계</p>
            <div class="risk-title">
                <h2>{escape(risk)}</h2>
                <span class="risk-badge">{escape(limit_type)} 기준</span>
            </div>
            <div class="risk-rest">
                <p>권장 휴식 시간</p>
                <span>{escape(guidance["rest_time"])}</span>
            </div>
            <strong>{escape(guidance["action_text"])}</strong>
        </section>
        <section class="metric-grid" data-testid="primary-metrics">
            {metric_card("현재 심박수", heart_rate, "bpm", "heart")}
            {metric_card("온열지수 (WBGT)", f"{wbgt:.1f}", "WBGT", "wbgt")}
            {metric_card("권장 휴식 시간", guidance["rest_time"], "참고 권고")}
        </section>
        <section class="detail-grid" data-testid="calculation-details">
            <article class="detail-card">
                <p>작업강도</p>
                <strong>{escape(workload)}</strong>
            </article>
            <article class="detail-card">
                <p>VO2 추정값</p>
                <strong>{vo2:.2f} ml/kg/min</strong>
            </article>
            <article class="detail-card">
                <p>Keytel 기반 칼로리 소모량</p>
                <strong>{kcal:.2f} kcal/min</strong>
            </article>
            <article class="detail-card">
                <p>대사율</p>
                <strong>{metabolic_watts:.0f} W</strong>
            </article>
            <article class="detail-card">
                <p>NIOSH {escape(limit_type)} 기준 WBGT</p>
                <strong>{limit_wbgt:.1f} ℃</strong>
            </article>
            <article class="detail-card">
                <p>기준 여유</p>
                <strong>{margin:.1f} ℃</strong>
            </article>
            <article class="detail-card">
                <p>입력 프로필</p>
                <strong>{age}세 / {weight:g}kg / {sex_label(sex)}</strong>
            </article>
            <article class="detail-card">
                <p>순화 판정</p>
                <strong>{escape(acclimatization["status_label"])} / {escape(limit_type)}</strong>
            </article>
            <article class="detail-card">
                <p>판정 근거</p>
                <strong>{escape(acclimatization["summary"])}</strong>
            </article>
            <article class="detail-card">
                <p>적용 조건</p>
                <strong>{escape(acclimatization["status_label"])} / 보정 WBGT {adjusted_wbgt:.1f}℃</strong>
            </article>
            <article class="detail-card">
                <p>수분 섭취 권고</p>
                <strong>{escape(guidance["water_text"])}</strong>
            </article>
            <article class="detail-card">
                <p>관리 조치</p>
                <strong>{escape(guidance["control_text"])}</strong>
            </article>
        </section>
        <aside class="notice">
            이 화면은 제공된 WBGT 예시 로직에 따른 참고 대시보드입니다.
            현장 대응은 작업 조건, 민감군 여부, 증상, 공식 폭염 안내를 함께 확인하세요.
        </aside>
        """,
        unsafe_allow_html=True,
    )


render_live_dashboard()
