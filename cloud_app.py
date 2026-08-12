from datetime import datetime
from html import escape
import json
import os

import streamlit as st
import streamlit.components.v1 as components

from acclimatization import WORKER_STATUS_LABELS, evaluate_acclimatization
from metabolism import (
    calculate_calories_from_vo2,
    calculate_energy_keytel,
    estimate_vo2_by_hrr,
)
from multi_worker_store import (
    append_risk_event,
    get_device,
    get_worker,
    normalize_device_id,
    read_risk_events,
    register_manager_device,
    register_worker_device,
    touch_device,
    upsert_worker,
    worker_list,
)
from utils import get_risk_guidance, should_trigger_alert
from wbgt_risk import calculate_heat_risk


ADMIN_CODE = os.getenv("WGBT_ADMIN_CODE", "ADMIN-2026")


SEX_LABELS = {
    "male": "남성",
    "female": "여성",
}


def sex_label(sex):
    return SEX_LABELS.get(sex, sex)


def format_updated_at(updated_at):
    if not updated_at:
        return "저장된 외부 측정값 없음"

    try:
        return datetime.fromisoformat(updated_at).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(updated_at)


def metric_card(label, value, unit, tone="neutral", reference=None):
    reference_markup = ""
    if reference:
        reference_markup = f"<small>{escape(reference)}</small>"

    return (
        f'<article class="metric-card metric-{escape(tone)}">'
        f'<div class="metric-head"><p>{escape(label)}</p>{reference_markup}</div>'
        f"<strong>{escape(str(value))}</strong>"
        f"<span>{escape(unit)}</span>"
        "</article>"
    )


def risk_score_from_margin(margin):
    return max(0, min(100, ((4.0 - margin) / 8.0) * 100))


def format_margin(margin):
    return f"{margin:+.1f}"


def risk_scale(position):
    return (
        '<div class="risk-scale" aria-hidden="true">'
        '<div class="risk-meter">'
        '<div class="risk-track"></div>'
        f'<span class="risk-marker" style="left: {position:.1f}%"></span>'
        "</div>"
        '<div class="risk-scale-labels">'
        "<span><b>기준 여유 +4℃ 이상</b><small>위험 낮음</small></span>"
        "<span><b>기준 여유 -4℃ 이하</b><small>위험 높음</small></span>"
        "</div>"
        "</div>"
    )


def action_checklist(items):
    return (
        '<ul class="action-list">'
        + "".join(
            '<li>'
            f'<label class="action-check"><input type="checkbox" aria-label="{escape(item)}">'
            '<span class="check-icon" aria-hidden="true">&#10003;</span>'
            f'<strong>{escape(item)}</strong></label>'
            '</li>'
            for item in items
        )
        + "</ul>"
    )


def detail_disclosure(values):
    acclimatization = values["acclimatization"]
    rows = [
        ("VO2 추정값", f"{values['vo2']:.2f} ml/kg/min"),
        ("칼로리 소모량", f"{values['kcal']:.2f} kcal/min"),
        ("대사율", f"{values['metabolic_watts']:.0f} W"),
        (
            f"NIOSH {values['limit_type']} 기준 WBGT",
            f"{values['limit_wbgt']:.1f}℃",
        ),
        ("기준 여유", f"{values['margin']:.1f}℃"),
        (
            "순화 판정",
            f"{acclimatization['status_label']} / {values['limit_type']}",
        ),
        (
            "입력 프로필",
            f"{values['age']}세 / {values['weight']:g}kg / {sex_label(values['sex'])}",
        ),
    ]
    row_markup = "".join(
        f'<div class="detail-row"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'
        for label, value in rows
    )
    return (
        '<details class="detail-disclosure" data-testid="calculation-details">'
        "<summary>상세 데이터 확인</summary>"
        f'<section class="detail-list">{row_markup}</section>'
        "</details>"
    )


def apply_styles():
    st.markdown(
        """
        <style>
            :root {
                color-scheme: light;
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
                --done: #16a34a;
            }
            html, body, .stApp {
                background: var(--canvas) !important;
                color: var(--ink) !important;
                color-scheme: light !important;
            }
            .stApp { background: var(--canvas); color: var(--ink); }
            .block-container {
                max-width: 760px;
                padding-top: 1rem;
                padding-bottom: 2.2rem;
            }
            [data-testid="stHeader"] { background: transparent; }
            h1, h2, h3, p { letter-spacing: 0; }
            [data-testid="stForm"],
            [data-testid="stForm"] h1,
            [data-testid="stForm"] h2,
            [data-testid="stForm"] h3,
            [data-testid="stForm"] p,
            [data-testid="stForm"] label,
            [data-testid="stForm"] span:not(.check-icon),
            [data-testid="stForm"] small,
            [data-testid="stMarkdownContainer"] h1,
            [data-testid="stMarkdownContainer"] h2,
            [data-testid="stMarkdownContainer"] h3,
            [data-testid="stMarkdownContainer"] p {
                color: var(--ink) !important;
                opacity: 1 !important;
                -webkit-text-fill-color: var(--ink) !important;
            }
            .stTextInput label,
            .stNumberInput label,
            .stSelectbox label,
            .stCheckbox label,
            [data-testid="stTextInput"] label,
            [data-testid="stNumberInput"] label,
            [data-testid="stSelectbox"] label,
            [data-testid="stCheckbox"] label {
                color: var(--ink) !important;
                opacity: 1 !important;
                -webkit-text-fill-color: var(--ink) !important;
            }
            .stTextInput input,
            .stNumberInput input,
            [data-testid="stTextInput"] input,
            [data-testid="stNumberInput"] input,
            textarea,
            div[data-baseweb="input"],
            div[data-baseweb="select"] > div {
                background: #ffffff !important;
                border-color: var(--line) !important;
                color: var(--ink) !important;
                -webkit-text-fill-color: var(--ink) !important;
            }
            .stTextInput input::placeholder,
            .stNumberInput input::placeholder,
            textarea::placeholder {
                color: #667085 !important;
                opacity: 1 !important;
                -webkit-text-fill-color: #667085 !important;
            }
            .page-head {
                border-bottom: 1px solid var(--line);
                margin-bottom: 1rem;
                padding-bottom: 1rem;
            }
            .page-head p {
                color: var(--muted);
                font-size: 0.95rem;
                margin: 0 0 0.28rem;
            }
            .page-head h1 {
                color: var(--ink);
                font-size: 1.9rem;
                line-height: 1.2;
                margin: 0 0 0.45rem;
            }
            .page-head span {
                color: var(--muted);
                display: block;
                font-size: 0.98rem;
                line-height: 1.5;
            }
            .feed-status, .metric-card, .detail-card, .notice, [data-testid="stForm"] {
                background: var(--surface);
                border: 1px solid var(--line);
                border-radius: 8px;
            }
            .feed-status {
                align-items: center;
                display: flex;
                flex-wrap: wrap;
                gap: 0.55rem;
                justify-content: space-between;
                margin: 0 0 0.9rem;
                padding: 0.72rem 0.9rem;
            }
            .feed-status strong { color: var(--ink); font-size: 0.98rem; }
            .feed-status span { color: var(--muted); font-size: 0.88rem; }
            .role-strip {
                align-items: center;
                background: #ffffff;
                border: 1px solid var(--line);
                border-radius: 8px;
                display: flex;
                justify-content: space-between;
                margin-bottom: 0.9rem;
                padding: 0.72rem 0.9rem;
            }
            .role-strip strong { color: var(--ink); font-size: 0.96rem; }
            .role-strip span { color: var(--muted); font-size: 0.78rem; }
            .worker-identity {
                background: #ffffff;
                border: 1px solid var(--line);
                border-radius: 8px;
                margin: 0 0 0.8rem;
                padding: 0.9rem 1rem;
            }
            .worker-identity p {
                color: var(--muted);
                font-size: 0.84rem;
                margin: 0 0 0.25rem;
            }
            .worker-identity strong {
                color: var(--ink);
                display: block;
                font-size: 1.25rem;
                line-height: 1.3;
                margin-bottom: 0.25rem;
            }
            .worker-identity span {
                color: var(--muted);
                display: block;
                font-size: 0.9rem;
                line-height: 1.4;
            }
            .worker-card {
                background: #ffffff;
                border: 1px solid var(--line);
                border-left-width: 6px;
                border-radius: 8px;
                box-shadow: 0 8px 18px rgba(16, 24, 40, 0.045);
                min-height: 168px;
                padding: 0.9rem;
            }
            .worker-card p {
                color: var(--muted);
                font-size: 0.78rem;
                font-weight: 700;
                margin: 0 0 0.15rem;
            }
            .worker-card h3 {
                color: var(--ink);
                font-size: 1.15rem;
                line-height: 1.25;
                margin: 0 0 0.75rem;
            }
            .worker-card strong {
                display: block;
                font-size: 1.5rem;
                line-height: 1.15;
                margin-bottom: 0.45rem;
            }
            .worker-card span,
            .worker-card small {
                color: var(--muted);
                display: block;
                font-size: 0.86rem;
                line-height: 1.42;
            }
            .worker-card.risk-safe { border-left-color: var(--safe); }
            .worker-card.risk-caution { border-left-color: var(--caution); }
            .worker-card.risk-warning { border-left-color: var(--warning); }
            .worker-card.risk-danger { border-left-color: var(--danger); }
            .worker-card.risk-safe strong { color: var(--safe-text); }
            .worker-card.risk-caution strong { color: var(--caution-text); }
            .worker-card.risk-warning strong { color: var(--warning-text); }
            .worker-card.risk-danger strong { color: var(--danger-text); }
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
                0%, 100% { box-shadow: 0 0 0 0 rgba(180, 35, 24, 0.22); }
                50% { box-shadow: 0 0 0 6px rgba(180, 35, 24, 0.08); }
            }
            .risk-panel {
                background: var(--surface);
                border: 1px solid var(--line);
                border-top-width: 8px;
                border-radius: 8px;
                box-shadow: 0 10px 24px rgba(16, 24, 40, 0.05);
                margin: 0.2rem 0 0.8rem;
                padding: 1.05rem;
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
            .risk-header {
                align-items: flex-start;
                display: flex;
                gap: 1rem;
                justify-content: space-between;
            }
            .risk-margin {
                min-width: 7.2rem;
                text-align: right;
            }
            .risk-margin span {
                color: var(--muted);
                display: block;
                font-size: 0.78rem;
                font-weight: 700;
                margin-bottom: 0.18rem;
            }
            .risk-margin strong {
                color: var(--ink);
                display: inline;
                font-size: 2rem;
                line-height: 1;
            }
            .risk-margin-value {
                align-items: center;
                display: inline-flex;
                gap: 0.18rem;
                justify-content: flex-end;
                white-space: nowrap;
            }
            .risk-margin small {
                color: var(--muted);
                font-size: 0.82rem;
                font-weight: 700;
                margin-left: 0;
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
            .risk-panel .risk-margin-value strong {
                display: inline;
                font-size: 2rem;
                line-height: 1;
            }
            .risk-scale {
                margin: 0.7rem 0 0.95rem;
                position: relative;
            }
            .risk-meter {
                align-items: center;
                display: flex;
                height: 28px;
                position: relative;
            }
            .risk-track {
                background: linear-gradient(
                    90deg,
                    var(--safe) 0%,
                    var(--safe) 25%,
                    var(--caution) 25%,
                    var(--caution) 50%,
                    var(--warning) 50%,
                    var(--warning) 75%,
                    var(--danger) 75%,
                    var(--danger) 100%
                );
                border-radius: 999px;
                height: 12px;
                opacity: 0.92;
                width: 100%;
            }
            .risk-marker {
                background: #ffffff;
                border: 2px solid #101828;
                border-radius: 999px;
                box-shadow: 0 2px 8px rgba(16, 24, 40, 0.26);
                height: 26px;
                position: absolute;
                top: 50%;
                transform: translate(-50%, -50%);
                width: 8px;
            }
            .risk-scale-labels {
                color: var(--muted);
                display: flex;
                font-size: 0.74rem;
                justify-content: space-between;
                line-height: 1.25;
                margin-top: 0.46rem;
            }
            .risk-scale-labels span:last-child { text-align: right; }
            .risk-scale-labels b {
                color: #344054;
                display: block;
                font-size: 0.78rem;
            }
            .risk-scale-labels small {
                display: block;
                font-size: 0.72rem;
            }
            .risk-rest {
                align-items: center;
                display: flex;
                flex-wrap: wrap;
                gap: 0.45rem;
                margin: 0 0 0.55rem;
            }
            .risk-rest p { margin: 0; }
            .risk-rest span {
                background: #f7f9fb;
                border: 1px solid var(--line);
                border-radius: 999px;
                color: var(--ink);
                font-size: 0.92rem;
                font-weight: 700;
                padding: 0.35rem 0.58rem;
            }
            .risk-safe { border-left-color: var(--safe); }
            .risk-safe { border-top-color: var(--safe); }
            .risk-safe .risk-badge { background: #ecfccb; color: var(--safe-text); }
            .risk-caution { border-left-color: var(--caution); }
            .risk-caution { border-top-color: var(--caution); }
            .risk-caution .risk-badge { background: #fef9c3; color: var(--caution-text); }
            .risk-warning { border-left-color: var(--warning); }
            .risk-warning { border-top-color: var(--warning); }
            .risk-warning .risk-badge { background: #ffedd5; color: var(--warning-text); }
            .risk-danger { border-left-color: var(--danger); }
            .risk-danger { border-top-color: var(--danger); }
            .risk-danger .risk-badge { background: #fee2e2; color: var(--danger-text); }
            .risk-safe .risk-title h2 { color: var(--safe-text); }
            .risk-caution .risk-title h2 { color: var(--caution-text); }
            .risk-warning .risk-title h2 { color: var(--warning-text); }
            .risk-danger .risk-title h2 { color: var(--danger-text); }
            .risk-safe .risk-margin strong { color: var(--safe-text); }
            .risk-caution .risk-margin strong { color: var(--caution-text); }
            .risk-warning .risk-margin strong { color: var(--warning-text); }
            .risk-danger .risk-margin strong { color: var(--danger-text); }
            .action-heading {
                color: var(--muted);
                font-size: 0.88rem;
                font-weight: 700;
                margin: 0.8rem 0 0.45rem;
            }
            .action-list {
                display: grid;
                gap: 0.42rem;
                list-style: none;
                margin: 0;
                padding: 0;
            }
            .action-list li {
                align-items: flex-start;
                line-height: 1.45;
            }
            .action-check {
                align-items: flex-start;
                cursor: pointer;
                display: inline-flex;
                gap: 0.62rem;
                min-height: 1.5rem;
            }
            .action-check input {
                height: 1px;
                opacity: 0;
                pointer-events: none;
                position: absolute;
                width: 1px;
            }
            .action-list .check-icon {
                align-items: center;
                background: #ffffff;
                border: 1px solid #fecaca;
                border-radius: 999px;
                color: var(--danger);
                display: inline-flex;
                flex: 0 0 auto;
                font-size: 0.72rem;
                font-weight: 700;
                height: 1.16rem;
                justify-content: center;
                margin-top: 0.15rem;
                width: 1.16rem;
            }
            .action-check:hover .check-icon {
                box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.11);
            }
            .action-check input:checked + .check-icon {
                background: var(--done);
                border-color: var(--done);
                color: #ffffff;
            }
            .action-check input:checked ~ strong {
                color: #344054;
            }
            .action-list li strong {
                color: var(--ink);
                display: inline;
                font-size: 1rem;
            }
            .metric-grid, .detail-grid {
                display: grid;
                gap: 0.72rem;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                margin-bottom: 0.95rem;
            }
            .metric-card { min-height: 126px; padding: 0.9rem; }
            .metric-card p, .detail-card p {
                color: var(--muted);
                font-size: 0.88rem;
                margin: 0 0 0.42rem;
            }
            .metric-head {
                align-items: baseline;
                display: flex;
                gap: 0.55rem;
                justify-content: space-between;
                min-height: 1.6rem;
            }
            .metric-head small {
                color: var(--muted);
                flex: 0 0 auto;
                font-size: 0.76rem;
                line-height: 1.2;
                text-align: right;
                white-space: nowrap;
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
            .metric-heart strong { color: #b42318; }
            .metric-wbgt strong { color: #006d77; }
            .metric-workload strong { color: var(--ink); }
            .detail-card { min-height: 104px; padding: 0.9rem; }
            .detail-card strong {
                color: var(--ink);
                display: block;
                font-size: 1.18rem;
                line-height: 1.35;
                overflow-wrap: anywhere;
            }
            .detail-disclosure {
                background: var(--surface);
                border: 1px solid var(--line);
                border-radius: 8px;
                margin: 0.2rem 0 0.95rem;
                overflow: hidden;
            }
            .detail-disclosure summary {
                color: var(--ink);
                cursor: pointer;
                font-size: 1rem;
                font-weight: 800;
                list-style: none;
                padding: 1rem;
            }
            .detail-disclosure summary::-webkit-details-marker { display: none; }
            .detail-disclosure summary::after {
                content: "▼";
                float: right;
                font-size: 0.8rem;
                margin-top: 0.12rem;
            }
            .detail-disclosure[open] summary::after { content: "▲"; }
            .detail-list {
                border-top: 1px solid var(--line);
                display: grid;
                gap: 0.05rem;
                padding: 0.85rem 1rem 1rem;
            }
            .detail-row {
                align-items: baseline;
                display: grid;
                gap: 0.35rem;
                grid-template-columns: minmax(7.5rem, 0.9fr) minmax(0, 1.1fr);
                padding: 0.42rem 0;
            }
            .detail-row span {
                color: var(--muted);
                font-size: 0.95rem;
            }
            .detail-row strong {
                color: var(--ink);
                font-size: 1rem;
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
            [data-testid="stForm"] { padding: 1rem; }
            div[data-testid="stFormSubmitButton"] button {
                min-height: 2.8rem;
                width: 100%;
            }
            @media (max-width: 640px) {
                .block-container {
                    padding-left: 1rem;
                    padding-right: 1rem;
                    padding-top: 1.1rem;
                }
                .page-head h1 { font-size: 1.55rem; }
                .metric-grid { grid-template-columns: 1fr; }
                .detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                .metric-card { min-height: 96px; }
                .metric-card strong { font-size: 1.65rem; }
                .detail-row { grid-template-columns: 1fr; }
                .risk-header { align-items: flex-start; }
                .risk-margin { min-width: 5.8rem; }
                .risk-margin strong { font-size: 1.7rem; }
                .risk-scale-labels {
                    font-size: 0.68rem;
                    gap: 0.7rem;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_korean_translation_guard():
    components.html(
        """
        <script>
        (function() {
            try {
                const parentDoc = window.parent.document;
                const root = parentDoc.documentElement;
                root.setAttribute("lang", "ko");
                root.setAttribute("translate", "no");
                root.classList.add("notranslate");

                let googleMeta = parentDoc.querySelector('meta[name="google"]');
                if (!googleMeta) {
                    googleMeta = parentDoc.createElement("meta");
                    googleMeta.setAttribute("name", "google");
                    parentDoc.head.appendChild(googleMeta);
                }
                googleMeta.setAttribute("content", "notranslate");

                let languageMeta = parentDoc.querySelector('meta[http-equiv="Content-Language"]');
                if (!languageMeta) {
                    languageMeta = parentDoc.createElement("meta");
                    languageMeta.setAttribute("http-equiv", "Content-Language");
                    parentDoc.head.appendChild(languageMeta);
                }
                languageMeta.setAttribute("content", "ko");

                const markNoTranslate = () => {
                    const targets = parentDoc.querySelectorAll([
                        "body",
                        ".stApp",
                        "[data-testid='stAppViewContainer']",
                        "[data-testid='stMarkdownContainer']",
                        "[data-testid='stForm']",
                        "[data-testid='stTextInput']",
                        "[data-testid='stNumberInput']",
                        "[data-testid='stSelectbox']",
                        "[data-testid='stCheckbox']",
                        "[role='tab']",
                        "label",
                        "input",
                        "textarea",
                        "button",
                        "select",
                        "option"
                    ].join(","));
                    targets.forEach((element) => {
                        element.setAttribute("translate", "no");
                        element.classList.add("notranslate");
                    });
                };

                markNoTranslate();
                if (parentDoc.body && !parentDoc.body.dataset.wgbtTranslateGuard) {
                    parentDoc.body.dataset.wgbtTranslateGuard = "true";
                    new MutationObserver(markNoTranslate).observe(parentDoc.body, {
                        childList: true,
                        subtree: true
                    });
                }
            } catch (_) {}
        })();
        </script>
        """,
        height=0,
    )


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

    html = """
        <div id="alert-root"></div>
        <script>
        const payload = __PAYLOAD__;
        const root = document.getElementById("alert-root");
        const enabledKey = "wgbt-device-alert-enabled";
        const lastAlertKey = "wgbt-last-alert-key";

        function readStorage(key) {
            try { return window.localStorage.getItem(key); }
            catch (_) { return null; }
        }

        function writeStorage(key, value) {
            try { window.localStorage.setItem(key, value); }
            catch (_) {}
        }

        function notificationsSupported() {
            return "Notification" in window && window.isSecureContext;
        }

        function vibrate(pattern) {
            if ("vibrate" in navigator) {
                try { navigator.vibrate(pattern); } catch (_) {}
            }
        }

        function playAlertSound() {
            try {
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                if (!AudioContext) return;
                const context = new AudioContext();
                const gain = context.createGain();
                gain.gain.setValueAtTime(0.0001, context.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.22, context.currentTime + 0.03);
                gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.95);
                gain.connect(context.destination);
                [0, 0.28, 0.56].forEach((offset) => {
                    const oscillator = context.createOscillator();
                    oscillator.type = "sine";
                    oscillator.frequency.setValueAtTime(880, context.currentTime + offset);
                    oscillator.connect(gain);
                    oscillator.start(context.currentTime + offset);
                    oscillator.stop(context.currentTime + offset + 0.18);
                });
            } catch (_) {}
        }

        function sendBrowserNotification() {
            if (!notificationsSupported() || Notification.permission !== "granted") return;
            try {
                new Notification("온열 위험도 알림", {
                    body: payload.risk + " 단계입니다. 심박수 " + payload.heartRate + " bpm, WBGT " + Number(payload.wbgt).toFixed(1),
                    tag: "wgbt-risk-alert",
                    renotify: true,
                });
            } catch (_) {}
        }

        async function turnOnAlerts() {
            writeStorage(enabledKey, "true");
            if (notificationsSupported() && Notification.permission === "default") {
                try { await Notification.requestPermission(); } catch (_) {}
            }
            vibrate([80]);
            playAlertSound();
            render();
            maybeTriggerAlert(true);
        }

        function turnOffAlerts() {
            writeStorage(enabledKey, "false");
            vibrate([60]);
            render();
        }

        function maybeTriggerAlert(force=false) {
            const enabled = readStorage(enabledKey) === "true";
            if (!payload.managerAlert || !enabled) return;
            const previousKey = readStorage(lastAlertKey);
            if (!force && previousKey === payload.key) return;
            writeStorage(lastAlertKey, payload.key);
            vibrate([450, 160, 450, 160, 450]);
            playAlertSound();
            sendBrowserNotification();
        }

        function bellSvg(enabled) {
            const slash = enabled ? "" : '<line x1="4" y1="20" x2="20" y2="4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>';
            return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 17H9m9-2v-5a6 6 0 0 0-12 0v5l-2 2h16l-2-2ZM10 21h4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' + slash + '</svg>';
        }

        function render() {
            const enabled = readStorage(enabledKey) === "true";
            const label = enabled ? "휴대폰 알림 끄기" : "휴대폰 알림 켜기";
            root.innerHTML = `
                <style>
                    body { margin: 0; font-family: sans-serif; }
                    .alert-toggle {
                        align-items: center;
                        background: ${enabled ? "#101828" : "#ffffff"};
                        border: 1px solid ${enabled ? "#101828" : "#d7dee7"};
                        border-radius: 999px;
                        color: ${enabled ? "#ffffff" : "#526070"};
                        cursor: pointer;
                        display: inline-flex;
                        height: 42px;
                        justify-content: center;
                        margin: 0;
                        width: 42px;
                    }
                    .alert-toggle svg {
                        height: 21px;
                        width: 21px;
                    }
                    .alert-toggle:focus-visible {
                        outline: 3px solid rgba(16, 24, 40, 0.18);
                        outline-offset: 2px;
                    }
                </style>
                <button id="alert-toggle" class="alert-toggle" type="button" aria-label="${label}" title="${label}">
                    ${bellSvg(enabled)}
                </button>
            `;
            document.getElementById("alert-toggle").addEventListener("click", () => {
                if (readStorage(enabledKey) === "true") turnOffAlerts();
                else turnOnAlerts();
            });
        }

        render();
        maybeTriggerAlert(false);
        </script>
    """
    components.html(html.replace("__PAYLOAD__", payload_json), height=48)


def calculate_dashboard_values(measurement):
    heart_rate = measurement["heart_rate"]
    wbgt = measurement["wbgt"]
    age = measurement["age"]
    weight = measurement["weight"]
    sex = measurement["sex"]
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
    guidance = get_risk_guidance(
        risk=risk_result["risk"],
        margin=risk_result.get("margin"),
        workload=risk_result.get("workload"),
        acclimatized=acclimatization.get("acclimatized"),
        limit_type=risk_result.get("limit_type"),
    )
    return {
        "heart_rate": heart_rate,
        "wbgt": wbgt,
        "age": age,
        "weight": weight,
        "sex": sex,
        "vo2": vo2,
        "hrr_ratio": hrr_ratio,
        "hr_max": hr_max,
        "resting_hr": resting_hr,
        "kcal_from_vo2": kcal_from_vo2,
        "kcal": kcal,
        "risk": risk_result["risk"],
        "workload": risk_result["workload"],
        "metabolic_watts": risk_result["metabolic_watts"],
        "limit_type": risk_result["limit_type"],
        "limit_wbgt": risk_result["limit_wbgt"],
        "adjusted_wbgt": risk_result["adjusted_wbgt"],
        "margin": risk_result["margin"],
        "risk_score": risk_score_from_margin(risk_result["margin"]),
        "acclimatization": acclimatization,
        "guidance": guidance,
        "manager_alert": should_trigger_alert(risk_result["risk"]),
    }


def get_query_param(name):
    try:
        value = st.query_params.get(name)
    except Exception:
        value = st.experimental_get_query_params().get(name)

    if isinstance(value, list):
        return value[0] if value else None
    return value


def set_query_param(name, value):
    try:
        st.query_params[name] = value
    except Exception:
        current_params = st.experimental_get_query_params()
        current_params[name] = value
        st.experimental_set_query_params(**current_params)


def sync_device_id_to_browser(device_id):
    components.html(
        f"""
        <script>
        try {{
            window.localStorage.setItem("wgbt-device-id", {json.dumps(device_id)});
        }} catch (_) {{}}
        </script>
        """,
        height=0,
    )


def ensure_device_id():
    device_id = get_query_param("device_id")
    if device_id:
        device_id = normalize_device_id(device_id)
        st.session_state["device_id"] = device_id
        sync_device_id_to_browser(device_id)
        return device_id

    device_id = st.session_state.get("device_id")
    if not device_id:
        device_id = normalize_device_id("")
        st.session_state["device_id"] = device_id

    set_query_param("device_id", device_id)
    sync_device_id_to_browser(device_id)
    return device_id


def worker_label(worker):
    return f"{worker['worker_number']} · {worker['name']}"


def risk_rank(risk):
    return {"안전": 0, "주의": 1, "경고": 2, "위험": 3}.get(risk, -1)


def render_worker_detail(worker, values, title="작업자 상세 정보"):
    guidance = values["guidance"]
    heart_reference = f"안정 기준 {values['resting_hr']}"
    wbgt_reference = f"기준 {values['limit_wbgt']:.1f}℃"
    st.markdown(
        f"""
        <section class="worker-identity">
            <p>{escape(title)}</p>
            <strong>{escape(worker_label(worker))}</strong>
            <span>{values["age"]}세 / {values["weight"]:g}kg / {escape(sex_label(values["sex"]))} · {escape(values["acclimatization"]["status_label"])} / {escape(values["limit_type"])}</span>
        </section>
        <section class="risk-panel risk-{escape(guidance["tone"])}" data-testid="risk-panel">
            <div class="risk-header">
                <div>
                    <p>현재 위험도 단계</p>
                    <div class="risk-title">
                        <h2>{escape(values["risk"])}</h2>
                    </div>
                </div>
                <div class="risk-margin" aria-label="기준 여유">
                    <span>기준 여유</span>
                    <div class="risk-margin-value"><strong>{format_margin(values["margin"])}</strong><small>℃</small></div>
                </div>
            </div>
            {risk_scale(values["risk_score"])}
            <p class="action-heading">권장 대처</p>
            {action_checklist(guidance["action_items"])}
        </section>
        <section class="metric-grid" data-testid="primary-metrics">
            {metric_card("현재 심박수", values["heart_rate"], "bpm", "heart", heart_reference)}
            {metric_card("온열지수 (WBGT)", f"{values["wbgt"]:.1f}", "WBGT", "wbgt", wbgt_reference)}
            {metric_card("작업강도", values["workload"], "대사율 기준", "workload")}
        </section>
        {detail_disclosure(values)}
        """,
        unsafe_allow_html=True,
    )


def default_worker_values():
    return {
        "worker_id": "",
        "worker_number": "",
        "name": "",
        "heart_rate": 120,
        "wbgt": 28.0,
        "age": 25,
        "weight": 70.0,
        "sex": "male",
        "worker_status": "existing",
        "heat_exposure_days": 7,
        "absence_days": 0,
        "similar_heat_work": True,
    }


def render_worker_form(
    form_key,
    current=None,
    device_id=None,
    manager_mode=False,
    submit_label="저장",
):
    current = {**default_worker_values(), **(current or {})}
    sex_options = list(SEX_LABELS)
    worker_status_options = list(WORKER_STATUS_LABELS)

    with st.form(form_key):
        st.subheader("작업자 식별정보")
        id_columns = st.columns(2)
        with id_columns[0]:
            worker_number = st.text_input(
                "작업자 번호",
                value=current["worker_number"],
                disabled=bool(current.get("worker_id")) and not manager_mode,
                placeholder="예: W-001",
            )
        with id_columns[1]:
            name = st.text_input("이름", value=current["name"], placeholder="예: 김민수")

        st.subheader("측정값")
        measurement_columns = st.columns(2)
        with measurement_columns[0]:
            heart_rate = st.number_input(
                "현재 심박수",
                min_value=1,
                max_value=220,
                value=current["heart_rate"],
                step=1,
                help="단위: bpm",
            )
        with measurement_columns[1]:
            wbgt = st.number_input(
                "온열지수 (WBGT)",
                min_value=0.0,
                max_value=60.0,
                value=current["wbgt"],
                step=0.1,
                format="%.1f",
            )

        st.subheader("프로필")
        profile_columns = st.columns(3)
        with profile_columns[0]:
            age = st.number_input(
                "나이",
                min_value=1,
                max_value=120,
                value=current["age"],
                step=1,
            )
        with profile_columns[1]:
            weight = st.number_input(
                "체중",
                min_value=1.0,
                max_value=300.0,
                value=current["weight"],
                step=0.5,
                format="%.1f",
                help="단위: kg",
            )
        with profile_columns[2]:
            sex = st.selectbox(
                "성별",
                options=sex_options,
                index=sex_options.index(current["sex"]) if current["sex"] in sex_options else 0,
                format_func=SEX_LABELS.get,
            )

        st.subheader("순화 판정")
        acclimatization_columns = st.columns(2)
        with acclimatization_columns[0]:
            worker_status = st.selectbox(
                "작업자 상태",
                options=worker_status_options,
                index=worker_status_options.index(current["worker_status"])
                if current["worker_status"] in worker_status_options
                else 0,
                format_func=WORKER_STATUS_LABELS.get,
            )
            heat_exposure_days = st.number_input(
                "최근 14일 유사 더위 작업일수",
                min_value=0,
                max_value=14,
                value=current["heat_exposure_days"],
                step=1,
            )
        with acclimatization_columns[1]:
            absence_days = st.number_input(
                "연속 부재일수",
                min_value=0,
                max_value=365,
                value=current["absence_days"],
                step=1,
                help="휴가, 병가, 배치 전환 등 더운 작업에서 떨어진 기간",
            )
            similar_heat_work = st.checkbox(
                "최근 작업 강도가 오늘 작업과 유사함",
                value=current["similar_heat_work"],
            )

        acclimatization_preview = evaluate_acclimatization(
            worker_status=worker_status,
            heat_exposure_days=heat_exposure_days,
            absence_days=absence_days,
            similar_heat_work=similar_heat_work,
        )
        st.info(
            f"판정: {acclimatization_preview['status_label']} "
            f"({acclimatization_preview['limit_type']} 적용) · "
            f"{acclimatization_preview['summary']}"
        )

        submitted = st.form_submit_button(submit_label, type="primary")

    if submitted:
        try:
            existing = get_worker(worker_number)
            if (
                existing
                and not manager_mode
                and current.get("worker_id") != existing.get("worker_id")
                and existing.get("name") != name.strip()
            ):
                raise ValueError("이미 다른 이름으로 등록된 작업자 번호입니다. 번호를 확인해주세요.")

            payload = upsert_worker(
                worker_number=worker_number,
                name=name,
                heart_rate=heart_rate,
                wbgt=wbgt,
                age=age,
                weight=weight,
                sex=sex,
                worker_status=worker_status,
                heat_exposure_days=heat_exposure_days,
                absence_days=absence_days,
                similar_heat_work=similar_heat_work,
            )
            if device_id:
                register_worker_device(device_id, payload["worker_id"])

            values = calculate_dashboard_values(payload)
            event = append_risk_event(payload, values)
        except ValueError as error:
            st.error(str(error))
        else:
            st.success(
                f"저장 완료: {worker_label(payload)} / {payload['heart_rate']} bpm / "
                f"WBGT {payload['wbgt']:.1f} / {values['risk']} 단계"
            )
            if event:
                st.warning("경고 이상 위험 기록이 데이터센터에 저장되었습니다.")
            st.rerun()


def render_unregistered_app(device_id):
    st.markdown(
        """
        <header class="page-head">
            <p>미등록 기기</p>
            <h1>작업자 등록</h1>
            <span>처음 접속한 기기는 작업자로 등록됩니다. 관리자 노트북은 관리자 등록 코드를 입력해 권한을 부여하세요.</span>
        </header>
        """,
        unsafe_allow_html=True,
    )
    worker_tab, manager_tab = st.tabs(["작업자 등록", "관리자 등록"])
    with worker_tab:
        st.caption("이미 등록했던 작업자라면 같은 작업자 번호와 이름을 입력해 이 기기와 다시 연결할 수 있습니다.")
        render_worker_form(
            form_key="new-worker-form",
            device_id=device_id,
            submit_label="작업자로 등록",
        )
    with manager_tab:
        st.subheader("관리자 권한 등록")
        st.caption("관리자 노트북에서 최초 1회만 등록 코드를 입력합니다.")
        with st.form("manager-registration-form"):
            code = st.text_input("관리자 등록 코드", type="password")
            submitted = st.form_submit_button("관리자 권한 활성화", type="primary")
        if submitted:
            if code == ADMIN_CODE:
                register_manager_device(device_id)
                st.success("이 기기가 작업관리자 기기로 등록되었습니다.")
                st.rerun()
            else:
                st.error("관리자 등록 코드가 올바르지 않습니다.")


def render_worker_app(device):
    worker = get_worker(device.get("worker_id"))
    if not worker:
        st.warning("연결된 작업자 정보를 찾지 못했습니다. 작업자 정보를 다시 등록해주세요.")
        render_worker_form(
            form_key="reconnect-worker-form",
            device_id=device["device_id"],
            submit_label="기존/신규 작업자 연결",
        )
        return

    st.markdown(
        f"""
        <header class="page-head">
            <p>작업자 화면</p>
            <h1>{escape(worker_label(worker))}</h1>
            <span>현재 심박수와 WBGT를 입력하면 관리자 대시보드에 반영됩니다.</span>
        </header>
        """,
        unsafe_allow_html=True,
    )
    try:
        values = calculate_dashboard_values(worker)
    except ValueError as error:
        st.error(str(error))
        return

    render_device_alert_controls(
        risk=values["risk"],
        manager_alert=values["manager_alert"],
        heart_rate=values["heart_rate"],
        wbgt=values["wbgt"],
        updated_at=worker.get("updated_at"),
    )
    render_worker_detail(worker, values, title="내 현재 상태")
    st.divider()
    render_worker_form(
        form_key=f"worker-update-form-{worker['worker_id']}",
        current=worker,
        device_id=device["device_id"],
        submit_label="내 측정값 저장",
    )


def render_worker_status_card(worker, values):
    guidance = values["guidance"]
    updated = format_updated_at(worker.get("updated_at"))
    st.markdown(
        f"""
        <article class="worker-card risk-{escape(guidance["tone"])}">
            <div>
                <p>{escape(worker["worker_number"])}</p>
                <h3>{escape(worker["name"])}</h3>
            </div>
            <strong>{escape(values["risk"])}</strong>
            <span>HR {values["heart_rate"]} bpm · WBGT {values["wbgt"]:.1f}℃</span>
            <span>{escape(values["workload"])} · 기준 여유 {format_margin(values["margin"])}℃</span>
            <small>{escape(updated)}</small>
        </article>
        """,
        unsafe_allow_html=True,
    )
    if st.button("상세 보기", key=f"detail-{worker['worker_id']}", use_container_width=True):
        st.session_state["selected_worker_id"] = worker["worker_id"]


def render_manager_dashboard():
    workers = worker_list()
    st.markdown(
        """
        <header class="page-head">
            <p>작업관리자 대시보드</p>
            <h1>전체 작업자 위험도</h1>
            <span>등록된 작업자의 현재 위험도를 한 화면에서 확인하고, 카드를 선택해 상세 정보를 볼 수 있습니다.</span>
        </header>
        """,
        unsafe_allow_html=True,
    )
    if not workers:
        st.info("아직 등록된 작업자가 없습니다.")
        return

    calculated = []
    for worker in workers:
        try:
            values = calculate_dashboard_values(worker)
        except ValueError as error:
            st.error(f"{worker_label(worker)} 계산 오류: {error}")
            continue
        calculated.append((worker, values))

    alert_count = sum(1 for _, values in calculated if values["manager_alert"])
    danger_count = sum(1 for _, values in calculated if values["risk"] == "위험")
    warning_count = sum(1 for _, values in calculated if values["risk"] == "경고")
    summary_columns = st.columns(4)
    summary_columns[0].metric("등록 작업자", len(calculated))
    summary_columns[1].metric("경고 이상", alert_count)
    summary_columns[2].metric("경고", warning_count)
    summary_columns[3].metric("위험", danger_count)

    calculated.sort(key=lambda item: (-risk_rank(item[1]["risk"]), item[0]["worker_number"]))
    for index in range(0, len(calculated), 2):
        columns = st.columns(2)
        for column, item in zip(columns, calculated[index : index + 2]):
            with column:
                render_worker_status_card(*item)

    selected_id = st.session_state.get("selected_worker_id")
    if not selected_id and calculated:
        selected_id = calculated[0][0]["worker_id"]
        st.session_state["selected_worker_id"] = selected_id

    selected_worker = get_worker(selected_id) if selected_id else None
    if selected_worker:
        st.divider()
        try:
            selected_values = calculate_dashboard_values(selected_worker)
        except ValueError as error:
            st.error(str(error))
        else:
            render_worker_detail(selected_worker, selected_values)


def render_manager_worker_input():
    workers = worker_list()
    st.markdown(
        """
        <header class="page-head">
            <p>관리자 입력</p>
            <h1>작업자 등록 및 측정값 입력</h1>
            <span>작업자 식별정보, 고정 프로필, 현재 측정값을 한 창에서 등록하거나 수정합니다.</span>
        </header>
        """,
        unsafe_allow_html=True,
    )

    options = ["신규 작업자"] + [worker["worker_id"] for worker in workers]
    selected = st.selectbox(
        "입력 대상",
        options=options,
        format_func=lambda value: "신규 작업자" if value == "신규 작업자" else worker_label(get_worker(value)),
    )
    current = None if selected == "신규 작업자" else get_worker(selected)
    render_worker_form(
        form_key=f"manager-worker-form-{selected}",
        current=current,
        manager_mode=True,
        submit_label="작업자 정보 저장",
    )


def render_data_center():
    st.markdown(
        """
        <header class="page-head">
            <p>데이터센터</p>
            <h1>경고 이상 위험 기록</h1>
            <span>측정값 저장 시점에 경고 또는 위험으로 감지된 기록을 시간순으로 확인합니다.</span>
        </header>
        """,
        unsafe_allow_html=True,
    )
    events = read_risk_events()
    if not events:
        st.info("아직 저장된 경고/위험 기록이 없습니다.")
        return

    worker_names = sorted({f"{event['worker_number']} · {event['name']}" for event in events})
    filter_columns = st.columns(3)
    with filter_columns[0]:
        worker_filter = st.selectbox("작업자", ["전체"] + worker_names)
    with filter_columns[1]:
        risk_filter = st.selectbox("위험도", ["전체", "경고", "위험"])
    with filter_columns[2]:
        order = st.selectbox("정렬", ["최신순", "오래된순"])

    filtered = events
    if worker_filter != "전체":
        filtered = [
            event
            for event in filtered
            if f"{event['worker_number']} · {event['name']}" == worker_filter
        ]
    if risk_filter != "전체":
        filtered = [event for event in filtered if event["risk"] == risk_filter]

    filtered = sorted(
        filtered,
        key=lambda event: event.get("event_time", ""),
        reverse=order == "최신순",
    )
    rows = [
        {
            "시간": format_updated_at(event["event_time"]),
            "작업자": f"{event['worker_number']} · {event['name']}",
            "위험도": event["risk"],
            "심박수": f"{event['heart_rate']} bpm",
            "WBGT": f"{event['wbgt']:.1f}℃",
            "대사율": f"{event['metabolic_watts']:.0f} W",
            "작업강도": event["workload"],
            "기준 여유": f"{event['margin']:+.1f}℃",
            "적용 기준": event["limit_type"],
        }
        for event in filtered
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_manager_app(device):
    touch_device(device["device_id"])
    st.markdown(
        f"""
        <section class="role-strip">
            <strong>작업관리자 기기</strong>
            <span>device: {escape(device["device_id"][-8:])}</span>
        </section>
        """,
        unsafe_allow_html=True,
    )
    dashboard_tab, input_tab, data_tab = st.tabs(
        ["작업관리자 대시보드", "작업자 등록/측정 입력", "데이터센터"]
    )
    with dashboard_tab:
        render_manager_dashboard()
    with input_tab:
        render_manager_worker_input()
    with data_tab:
        render_data_center()


st.set_page_config(
    page_title="온열 위험도 2차",
    layout="centered",
    initial_sidebar_state="collapsed",
)
apply_styles()
apply_korean_translation_guard()

device_id = ensure_device_id()
device = get_device(device_id)

if device.get("role") == "manager":
    render_manager_app(device)
elif device.get("role") == "worker":
    touch_device(device_id)
    render_worker_app(device)
else:
    render_unregistered_app(device_id)
