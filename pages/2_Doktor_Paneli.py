"""
pages/2_Doktor_Paneli.py
------------------------
MedTriage — Doktor Paneli
onayladığı / geçersiz kıldığı panel.

İçerik:
  - Canlı bekleme süreli hasta kuyruğu (öncelik sırası)
  - AI öneri + SHAP gerekçesi
  - KNN tabanlı benzer geçmiş vaka karşılaştırması
  - Onay / Geçersiz kılma (audit trail → decision_log)
  - Günlük özet metrikleri
  - TR / EN dil seçeneği

⚠️  Bu panel karar önerir, karar vermez.
    Nihai sorumluluk nöbetçi hekimdedir.
"""

from __future__ import annotations

import sys
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# ── Proje kökü ────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.queue_store import (
    get_queue, get_patient_by_id, update_patient_status,
    log_decision, get_decision_log, get_override_statistics, init_db,
)
from shared.theme import (
    apply_theme,
    brand_header_html,
    disclaimer_bar_html,
    section_label_html,
    card_html,
    ktas_badge_html,
    red_flag_alert_html,
    ai_result_card_html,
    patient_card_html,
    vital_chip_html,
    KTAS_CONFIG,
)
from shared.header import render_header
from shared.footer import render_footer

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DİL SÖZLÜĞÜ — değişmedi
# ─────────────────────────────────────────────────────────────────────────────
_LANG: dict[str, dict[str, str]] = {
    "TR": {
        "page_title":       "Doktor Paneli — MedTriage",
        "page_label":       "Doktor Paneli",
        "disclaimer":       "Bu panel karar önerir, karar vermez. Nihai sorumluluk nöbetçi hekimdedir.",
        "lang_label":       "Dil / Language",
        "queue_title":      "Bekleyen Hastalar",
        "no_patients":      "Kuyrukta bekleyen hasta yok.",
        "detail_title":     "Hasta Detayı",
        "waiting":          "dk bekliyor",
        "waiting_seconds":  "sn bekliyor",
        "ai_suggestion":    "AI Triaj Önerisi",
        "red_flag_note":    "Model atlandı — Kural tabanlı acil uyarı tetiklendi",
        "similar_cases":    "Benzer Geçmiş Vakalar (KNN)",
        "similar_caption":  "Eğitim verisindeki en yakın 3 vaka · Öklid mesafesi · Tanı aracı değil, bağlamsal referans",
        "approve_btn":      "✅  Onayla",
        "override_btn":     "✏️  Geçersiz Kıl",
        "override_note":    "Geçersiz Kılma Gerekçesi (zorunlu)",
        "override_placeholder": "Klinik gözlem, ek bulgu veya farklılık nedeninizi yazın...",
        "override_warning": "Geçersiz kılma gerekçesi boş bırakılamaz.",
        "approve_ok":       "✅ Onaylandı ve kuyruktan kaldırıldı.",
        "override_ok":      "✏️ Geçersiz kılındı ve karar günlüğüne eklendi.",
        "summary_title":    "Bugünkü Özet",
        "total_seen":       "Görülen Hasta",
        "approved_count":   "AI Onaylandı",
        "overridden_count": "Geçersiz Kılındı",
        "override_rate":    "Geçersiz Kılma Oranı",
        "vitals_header":    "Vital Bulgular",
        "demo_header":      "Demografik Bilgiler",
        "complaint_label":  "Şikayet",
        "age_label":        "Yaş",
        "gender_label":     "Cinsiyet",
        "sbp_label":        "Sistolik",
        "dbp_label":        "Diyastolik",
        "hr_label":         "Nabız",
        "rr_label":         "Solunum",
        "temp_label":       "Ateş",
        "spo2_label":       "SpO2",
        "pain_label":       "Ağrı",
        "mental_label":     "Mental",
        "ktas_col":         "KTAS",
        "dist_col":         "Benzerlik",
        "refresh_btn":      "↻ Yenile",
        "model_missing":    "AI modeli yüklenemedi — yalnızca kural tabanlı uyarılar aktif.",
        "confidence":       "Model Güveni",
        "gender_m":         "Erkek",
        "gender_f":         "Kadın",
        "gender_u":         "Belirtilmedi",
        "select_hint":      "Bir hasta seçin",
        "select_hint_sub":  "Sol taraftaki listeden hastaya tıklayın",
        "no_longer_queue":  "Bu hasta artık kuyrukta değil.",
        "recent_decisions": "Son Kararlar",
        "cancel_btn":       "İptal",
        "save_btn":         "💾  Kaydet",
        "karar_section":    "Karar",
    },
    "EN": {
        "page_title":       "Doctor Panel — MedTriage",
        "page_label":       "Doctor Panel",
        "disclaimer":       "This panel suggests, not decides. Final responsibility lies with the on-call physician.",
        "lang_label":       "Language / Dil",
        "queue_title":      "Waiting Patients",
        "no_patients":      "No patients waiting in queue.",
        "detail_title":     "Patient Detail",
        "waiting":          "min waiting",
        "waiting_seconds":  "sec waiting",
        "ai_suggestion":    "AI Triage Suggestion",
        "red_flag_note":    "Model skipped — Rule-based critical alert triggered",
        "similar_cases":    "Similar Historical Cases (KNN)",
        "similar_caption":  "Closest 3 cases from training data · Euclidean distance · Context only, not diagnostic",
        "approve_btn":      "✅  Approve",
        "override_btn":     "✏️  Override",
        "override_note":    "Override Reason (required)",
        "override_placeholder": "Describe your clinical observation or reason for override...",
        "override_warning": "Override reason cannot be empty.",
        "approve_ok":       "✅ Approved and removed from queue.",
        "override_ok":      "✏️ Overridden and logged to decision audit trail.",
        "summary_title":    "Today's Summary",
        "total_seen":       "Patients Seen",
        "approved_count":   "AI Approved",
        "overridden_count": "Overridden",
        "override_rate":    "Override Rate",
        "vitals_header":    "Vital Signs",
        "demo_header":      "Demographics",
        "complaint_label":  "Chief Complaint",
        "age_label":        "Age",
        "gender_label":     "Gender",
        "sbp_label":        "Systolic BP",
        "dbp_label":        "Diastolic BP",
        "hr_label":         "Heart Rate",
        "rr_label":         "Resp. Rate",
        "temp_label":       "Temperature",
        "spo2_label":       "SpO2",
        "pain_label":       "Pain",
        "mental_label":     "Mental",
        "ktas_col":         "KTAS",
        "dist_col":         "Similarity",
        "refresh_btn":      "↻ Refresh",
        "model_missing":    "AI model unavailable — only rule-based alerts active.",
        "confidence":       "Model Confidence",
        "gender_m":         "Male",
        "gender_f":         "Female",
        "gender_u":         "Unknown",
        "select_hint":      "Select a patient",
        "select_hint_sub":  "Click on a patient from the list on the left",
        "no_longer_queue":  "This patient is no longer in the queue.",
        "recent_decisions": "Recent Decisions",
        "cancel_btn":       "Cancel",
        "save_btn":         "💾  Save",
        "karar_section":    "Decision",
    },
}

MENTAL_TR = {1: "Alert", 2: "Verbal", 3: "Pain", 4: "Unresponsive"}

# ─────────────────────────────────────────────────────────────────────────────
# SAYFA KURULUMU
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MedTriage AI Assistant",
    layout="wide",
    initial_sidebar_state="collapsed",
)
init_db()

if "lang"                not in st.session_state: st.session_state.lang                = "TR"
if "selected_patient_id" not in st.session_state: st.session_state.selected_patient_id = None
if "show_override_form"  not in st.session_state: st.session_state.show_override_form  = False
if "action_msg"          not in st.session_state: st.session_state.action_msg          = None


def T(key: str) -> str:
    """Aktif dile göre çeviri döndürür."""
    return _LANG[st.session_state.lang].get(key, key)


# ─────────────────────────────────────────────────────────────────────────────
# MODEL YÜKLEME — değişmedi
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _load_bundle() -> dict | None:
    try:
        from model.train_model import load_model_bundle
        return load_model_bundle()
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def _load_training_data() -> pd.DataFrame | None:
    try:
        from data.load_ktas import load_ktas
        return load_ktas()
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCILAR — değişmedi
# ─────────────────────────────────────────────────────────────────────────────
def _waiting_minutes(timestamp_str: str) -> float:
    try:
        ts  = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        return (now - ts).total_seconds() / 60.0
    except Exception:
        return 0.0


def _format_waiting(minutes: float) -> str:
    if minutes < 1:
        return f"{int(minutes * 60)} {T('waiting_seconds')}"
    return f"{int(minutes)} {T('waiting')}"


def _gender_label(gender_raw: str) -> str:
    g = str(gender_raw).lower().strip()
    if g in ("1", "erkek", "male", "m"):         return T("gender_m")
    if g in ("2", "kadın", "kadin", "female", "f"): return T("gender_f")
    return T("gender_u")


# ─────────────────────────────────────────────────────────────────────────────
# KNN BENZİR VAKA — değişmedi
# ─────────────────────────────────────────────────────────────────────────────
_KNN_VITAL_COLS = ["sbp", "dbp", "heart_rate", "resp_rate", "temperature",
                   "spo2", "age", "pain_scale", "mental_status"]


def _find_similar_cases(vitals: dict, age: int, k: int = 3) -> pd.DataFrame | None:
    train_df = _load_training_data()
    if train_df is None or len(train_df) == 0:
        return None

    query = {}
    for col in _KNN_VITAL_COLS:
        if col in vitals:     query[col] = float(vitals[col])
        elif col == "age":    query[col] = float(age)
        else:                 query[col] = float("nan")

    available_cols = [c for c in _KNN_VITAL_COLS if c in train_df.columns]
    if not available_cols:
        return None

    X_train = train_df[available_cols].copy()
    q_vec   = np.array([query.get(c, float("nan")) for c in available_cols])
    stds    = X_train.std().replace(0, 1)
    X_norm  = (X_train - X_train.mean()) / stds
    q_norm  = (q_vec - X_train.mean().values) / stds.values

    valid_mask = X_norm.notna().all(axis=1)
    X_valid    = X_norm[valid_mask].values
    if len(X_valid) == 0:
        return None

    q_clean    = np.where(np.isnan(q_norm), 0.0, q_norm)
    distances  = np.sqrt(((X_valid - q_clean) ** 2).sum(axis=1))
    top_k_idx  = np.argsort(distances)[:k]
    valid_indices  = X_norm[valid_mask].index[top_k_idx]
    top_distances  = distances[top_k_idx]

    result_rows = []
    for i, (orig_idx, dist) in enumerate(zip(valid_indices, top_distances)):
        row = train_df.loc[orig_idx]
        result_rows.append({
            "#":             i + 1,
            "Yaş":           int(row.get("age", "—")),
            "SKB":           row.get("sbp", "—"),
            "HR":            row.get("heart_rate", "—"),
            "SpO2":          row.get("spo2", "—"),
            "NRS":           row.get("pain_scale", "—"),
            T("ktas_col"):   int(row.get("ktas_level", "—")),
            T("dist_col"):   f"{1/(1+dist):.2f}",
        })

    return pd.DataFrame(result_rows)


# ─────────────────────────────────────────────────────────────────────────────
# HASTA KARTI RENDER
# ─────────────────────────────────────────────────────────────────────────────
def _render_patient_card(p: dict, selected_id: int | None) -> bool:
    """
    Hasta kuyruğundaki tek kartı theme.patient_card_html ile render eder.
    Tıklama butonu altta yer alır.
    """
    wait_min    = _waiting_minutes(p["timestamp"])
    is_urgent   = wait_min > 10 and p["ai_priority"] >= 3
    is_selected = p["id"] == selected_id
    wait_txt    = _format_waiting(wait_min)

    st.markdown(
        patient_card_html(
            p,
            is_selected=is_selected,
            is_overdue=is_urgent,
            wait_text=wait_txt,
            lang=st.session_state.lang,
        ),
        unsafe_allow_html=True,
    )

    btn_label = f"#{p['id']} — {'Seç' if st.session_state.lang == 'TR' else 'Select'}"
    return st.button(
        btn_label,
        key=f"select_patient_{p['id']}",
        use_container_width=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# VITAL BULGULAR RENDER — vital_chip_html ile
# ─────────────────────────────────────────────────────────────────────────────
def _render_vitals_section(vitals: dict) -> None:
    """Vital bulguları chip kartları olarak gösterir."""
    sbp  = vitals.get("sbp",         "—")
    dbp  = vitals.get("dbp",         "—")
    hr   = vitals.get("heart_rate",  "—")
    rr   = vitals.get("resp_rate",   "—")
    temp = vitals.get("temperature", "—")
    spo2 = vitals.get("spo2",        "—")
    pain = vitals.get("pain_scale",  "—")
    mental_code = vitals.get("mental_status", 1)

    # Kritik eşik kontrolleri (klinik renk sinyali — --color-critical)
    def _is_crit_sbp(v):  return isinstance(v, (int, float)) and (v < 90 or v > 180)
    def _is_crit_hr(v):   return isinstance(v, (int, float)) and (v < 50 or v > 130)
    def _is_crit_spo2(v): return isinstance(v, (int, float)) and v < 90
    def _is_crit_rr(v):   return isinstance(v, (int, float)) and (v < 8 or v > 30)
    def _is_crit_temp(v): return isinstance(v, (int, float)) and (v < 35 or v > 39.5)
    def _is_crit_pain(v): return isinstance(v, (int, float)) and v >= 8

    chips_html = f"""
<div style="display:flex;flex-wrap:wrap;gap:12px;margin:12px 0 20px;">
    {vital_chip_html(T("sbp_label"),  f"{sbp}", "mmHg",  _is_crit_sbp(sbp))}
    {vital_chip_html(T("dbp_label"),  f"{dbp}", "mmHg",  False)}
    {vital_chip_html(T("hr_label"),   f"{hr}",  "bpm",   _is_crit_hr(hr))}
    {vital_chip_html(T("rr_label"),   f"{rr}",  "/dk",   _is_crit_rr(rr))}
    {vital_chip_html(T("temp_label"), f"{temp}", "°C",   _is_crit_temp(temp))}
    {vital_chip_html(T("spo2_label"), f"{spo2}", "%",    _is_crit_spo2(spo2))}
    {vital_chip_html(T("pain_label"), f"{pain}/10", "",  _is_crit_pain(pain))}
    {vital_chip_html(T("mental_label"), f"{mental_code} — {MENTAL_TR.get(int(mental_code) if str(mental_code).isdigit() else 1, 'Alert')}", "", int(str(mental_code)) >= 3 if str(mental_code).isdigit() else False)}
</div>
"""
    st.markdown(chips_html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# DETAY PANELİ
# ─────────────────────────────────────────────────────────────────────────────
def _render_detail_panel(patient: dict) -> None:
    """Seçili hastanın detay panelini render eder. İş mantığı değişmedi."""
    pid    = patient["id"]
    ktas   = patient["ai_priority"]
    vitals = patient.get("vitals", {})
    lang   = st.session_state.lang
    cfg    = KTAS_CONFIG.get(ktas, KTAS_CONFIG[3])

    # ── Başlık + KTAS rozeti ─────────────────────────────────────────────
    st.markdown(
        f"""
<div style="
    display:flex;align-items:center;justify-content:space-between;
    margin-bottom:20px;flex-wrap:wrap;gap:10px;
">
    <div>
        <div style="
            font-family:var(--font-sans);font-size:1rem;font-weight:600;
            color:var(--color-ink);line-height:1.3;
        ">{T("detail_title")} &nbsp;·&nbsp;
            <span style="font-family:var(--font-mono);color:var(--color-ink-secondary)">
                #{pid}
            </span>
        </div>
        <div style="
            font-family:var(--font-sans);font-size:0.78rem;
            color:var(--color-ink-secondary);margin-top:4px;
        ">{str(patient.get("chief_complaint", "—"))[:80]}</div>
    </div>
    {ktas_badge_html(ktas, lang, show_time=True)}
</div>
""",
        unsafe_allow_html=True,
    )

    # ── Demografik ───────────────────────────────────────────────────────
    st.markdown(section_label_html(T("demo_header")), unsafe_allow_html=True)
    dc1, dc2, dc3 = st.columns(3)
    dc1.metric(T("age_label"),      f"{patient.get('age', '—')} yıl")
    dc2.metric(T("gender_label"),   _gender_label(patient.get("gender", "")))
    dc3.metric(T("complaint_label"), str(patient.get("chief_complaint", "—"))[:35])

    # ── Vital Bulgular ─── yeni vital_chip_html bileşeni ──────────────
    st.markdown(section_label_html(T("vitals_header")), unsafe_allow_html=True)
    _render_vitals_section(vitals)

    # ── AI Önerisi ───────────────────────────────────────────────────────
    st.markdown(section_label_html(T("ai_suggestion")), unsafe_allow_html=True)

    if patient.get("red_flag"):
        reasons = [patient.get("ai_explanation", T("red_flag_note"))]
        st.markdown(
            red_flag_alert_html(
                reasons=reasons,
                explanation=T("red_flag_note"),
            ),
            unsafe_allow_html=True,
        )
    else:
        # Sahte result dict oluştur (ai_result_card_html için)
        fake_result = {
            "ktas_level":  ktas,
            "confidence":  0.0,   # Kuyrukta saklı değil, 0 göster
            "explanation": patient.get("ai_explanation", "—"),
        }
        st.markdown(
            ai_result_card_html(fake_result, lang=lang),
            unsafe_allow_html=True,
        )

    # ── Benzer geçmiş vakalar (KNN) ───────────────────────────────────────
    st.markdown(section_label_html(T("similar_cases")), unsafe_allow_html=True)
    with st.spinner("Benzer vakalar aranıyor..."):
        sim_df = _find_similar_cases(vitals, patient.get("age", 40))

    if sim_df is not None and not sim_df.empty:
        st.dataframe(sim_df, use_container_width=True, hide_index=True, height=145)
        st.caption(T("similar_caption"))
    else:
        st.info("Eğitim verisi yüklenemedi — benzer vaka karşılaştırması mevcut değil.")

    # ── Karar Butonları ───────────────────────────────────────────────────
    st.markdown(section_label_html(f"⚖️  {T('karar_section')}"), unsafe_allow_html=True)

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button(T("approve_btn"), key=f"approve_{pid}",
                     use_container_width=True, type="primary"):
            _handle_approve(patient)

    with btn_col2:
        if st.button(T("override_btn"), key=f"override_btn_{pid}",
                     use_container_width=True, type="secondary"):
            st.session_state.show_override_form = True

    if st.session_state.get("show_override_form"):
        _render_override_form(patient)


# ─────────────────────────────────────────────────────────────────────────────
# ONAY / GEÇERSİZ KILMA — iş mantığı değişmedi
# ─────────────────────────────────────────────────────────────────────────────
def _handle_approve(patient: dict) -> None:
    pid = patient["id"]
    try:
        log_decision(
            patient_id      = pid,
            ai_suggestion   = patient["ai_priority"],
            doctor_decision = "onaylandı",
            doctor_note     = "",
        )
        update_patient_status(pid, "görüldü")
        st.session_state.selected_patient_id = None
        st.session_state.show_override_form  = False
        st.session_state.action_msg = ("success", T("approve_ok"))
        st.rerun()
    except Exception as e:
        st.error(f"Hata: {e}")


def _render_override_form(patient: dict) -> None:
    """Geçersiz kılma gerekçesi formu — gerekçe zorunlu (iş mantığı korundu)."""
    pid = patient["id"]
    st.markdown(
        '<div style="height:1px;background:var(--color-border);margin:20px 0;"></div>',
        unsafe_allow_html=True,
    )

    # Geçersiz kılma kutusu — belirgin ama agresif değil
    st.markdown(
        f"""
<div style="
    background:rgba(255,149,0,0.05);
    border-left:4px solid var(--color-warning);
    border-radius:0 var(--radius-alert) var(--radius-alert) 0;
    padding:16px 20px;
    margin-bottom:16px;
    font-family:var(--font-sans);font-size:0.82rem;
    color:#7A4500;line-height:1.5;
">
    <strong>⚠️ Geçersiz Kılma</strong> — AI önerisi reddedilecek.
    Klinik gerekçenizi aşağıya yazın. Bu kayıt denetim günlüğüne eklenir.
</div>""",
        unsafe_allow_html=True,
    )

    reason = st.text_area(
        T("override_note"),
        placeholder=T("override_placeholder"),
        key=f"override_reason_{pid}",
        height=110,
    )
    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button(T("save_btn"), key=f"save_override_{pid}",
                     use_container_width=True, type="primary"):
            if not reason.strip():
                st.error(T("override_warning"))
            else:
                try:
                    log_decision(
                        patient_id      = pid,
                        ai_suggestion   = patient["ai_priority"],
                        doctor_decision = "geçersiz kılındı",
                        doctor_note     = reason.strip(),
                    )
                    update_patient_status(pid, "görüldü")
                    st.session_state.selected_patient_id = None
                    st.session_state.show_override_form  = False
                    st.session_state.action_msg = ("info", T("override_ok"))
                    st.rerun()
                except Exception as e:
                    st.error(f"Hata: {e}")
    with col_cancel:
        if st.button(T("cancel_btn"), key=f"cancel_override_{pid}",
                     use_container_width=True):
            st.session_state.show_override_form = False
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# GÜNLÜK ÖZET
# ─────────────────────────────────────────────────────────────────────────────
def _render_daily_summary() -> None:
    """Günün karar istatistiklerini metrik kartlar olarak gösterir."""
    st.markdown(
        f'<div style="font-family:var(--font-sans);font-size:1rem;font-weight:600;'
        f'color:var(--color-ink);margin-bottom:20px;letter-spacing:-0.01em;">'
        f'📈 &nbsp; {T("summary_title")}</div>',
        unsafe_allow_html=True,
    )

    stats         = get_override_statistics()
    approved      = stats["approved"]
    override      = stats["overridden"]
    rate          = stats["override_rate"]
    seen_patients = len(get_queue(status_filter="görüldü"))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(T("total_seen"),       seen_patients)
    c2.metric(T("approved_count"),   approved,
              delta=f"+{approved}" if approved > 0 else None)
    c3.metric(T("overridden_count"), override,
              delta=f"+{override}" if override > 0 else None,
              delta_color="inverse")
    c4.metric(T("override_rate"),    f"%{rate*100:.1f}")

    # Son kararlar tablosu
    logs = get_decision_log()[:5]
    if logs:
        st.markdown(
            f'<div style="font-family:var(--font-sans);font-size:0.72rem;'
            f'font-weight:500;text-transform:uppercase;letter-spacing:0.08em;'
            f'color:var(--color-ink-secondary);margin:24px 0 12px;">'
            f'{T("recent_decisions")}</div>',
            unsafe_allow_html=True,
        )
        log_df = pd.DataFrame(logs)[
            ["timestamp", "patient_id", "ai_suggestion", "doctor_decision", "doctor_note"]
        ].rename(columns={
            "timestamp":       "Zaman",
            "patient_id":      "Hasta #",
            "ai_suggestion":   "AI Öneri",
            "doctor_decision": "Doktor Kararı",
            "doctor_note":     "Not",
        })
        log_df = log_df.iloc[::-1].reset_index(drop=True)
        st.dataframe(log_df, use_container_width=True, hide_index=True, height=200)


# ─────────────────────────────────────────────────────────────────────────────
# ANA FONKSİYON
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    """Doktor panelinin ana render döngüsü."""

    # ── Tema enjeksiyonu ─────────────────────────────────────────────────
    apply_theme()

    # ── Header: marka + TR/EN toggle + yenile ────────────────────────────
    h_col, lang_col, refresh_col = st.columns([6, 1, 1.5])
    with h_col:
        st.markdown(
            brand_header_html(T("page_label")),
            unsafe_allow_html=True,
        )
    with lang_col:
        st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
        lang_choice = st.selectbox(
            T("lang_label"),
            options=["TR", "EN"],
            index=0 if st.session_state.lang == "TR" else 1,
            key="lang_select",
            label_visibility="collapsed",
        )
        if lang_choice != st.session_state.lang:
            st.session_state.lang = lang_choice
            st.rerun()
    with refresh_col:
        st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
        if st.button(T("refresh_btn"), use_container_width=True, type="secondary"):
            st.rerun()

    # ── Sabit uyarı şeridi ────────────────────────────────────────────────
    st.markdown(
        disclaimer_bar_html(f"⚠️  {T('disclaimer')}"),
        unsafe_allow_html=True,
    )

    # ── Eylem mesajı (onay / geçersiz kılma sonrası) ──────────────────────
    if st.session_state.action_msg:
        msg_type, msg_text = st.session_state.action_msg
        if msg_type == "success":
            st.success(msg_text)
        else:
            st.info(msg_text)
        st.session_state.action_msg = None

    # ── Model durumu ──────────────────────────────────────────────────────
    if _load_bundle() is None:
        st.warning(T("model_missing"))

    # ── Kuyruk ────────────────────────────────────────────────────────────
    queue = get_queue(status_filter="bekliyor")
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── İki sütun: kuyruk listesi | detay panel ───────────────────────────
    left_col, right_col = st.columns([2, 3], gap="large")

    with left_col:
        # Kuyruk başlığı + sayaç rozeti
        st.markdown(
            f'<div style="font-family:var(--font-sans);font-size:0.72rem;'
            f'font-weight:500;text-transform:uppercase;letter-spacing:0.08em;'
            f'color:var(--color-ink-secondary);margin-bottom:14px;'
            f'display:flex;align-items:center;gap:8px;">'
            f'{T("queue_title")} &nbsp;'
            f'<span style="background:rgba(122,31,43,0.10);color:var(--color-brand);'
            f'border-radius:999px;padding:2px 10px;font-size:11px;font-weight:700;">'
            f'{len(queue)}</span></div>',
            unsafe_allow_html=True,
        )

        if not queue:
            st.markdown(
                f'<div style="background:rgba(52,199,89,0.07);'
                f'border-left:4px solid var(--color-safe);'
                f'border-radius:0 12px 12px 0;padding:18px 20px;'
                f'font-family:var(--font-sans);font-size:0.85rem;color:#1A7D3F;">'
                f'✅ {T("no_patients")}</div>',
                unsafe_allow_html=True,
            )
        else:
            for p in queue:
                if _render_patient_card(p, st.session_state.selected_patient_id):
                    st.session_state.selected_patient_id = p["id"]
                    st.session_state.show_override_form  = False
                    st.rerun()

    with right_col:
        if st.session_state.selected_patient_id is None:
            # Boş durum — zarif bir placeholder
            st.markdown(
                f"""
<div style="
    display:flex;flex-direction:column;align-items:center;
    justify-content:center;padding:80px 24px;
    background:var(--color-surface);
    border-radius:var(--radius-card);
    box-shadow:var(--shadow-card);
    border:2px dashed var(--color-border);
">
    <div style="
        font-size:2.8rem;margin-bottom:16px;opacity:0.15;
        line-height:1;
    ">←</div>
    <div style="
        font-family:var(--font-sans);
        font-size:1rem;font-weight:600;
        color:var(--color-ink-secondary);
        margin-bottom:6px;
    ">{T("select_hint")}</div>
    <div style="
        font-family:var(--font-sans);
        font-size:0.82rem;
        color:var(--color-ink-tertiary);
    ">{T("select_hint_sub")}</div>
</div>
""",
                unsafe_allow_html=True,
            )
        else:
            patient = get_patient_by_id(st.session_state.selected_patient_id)
            if patient is None or patient.get("status") != "bekliyor":
                st.info(T("no_longer_queue"))
                st.session_state.selected_patient_id = None
            else:
                # Detay paneli: beyaz kart içinde
                st.markdown(
                    '<div style="'
                    'background:var(--color-surface);'
                    'border-radius:var(--radius-card);'
                    'box-shadow:var(--shadow-card);'
                    'padding:28px 32px;'
                    'border:none;">',
                    unsafe_allow_html=True,
                )
                _render_detail_panel(patient)
                st.markdown("</div>", unsafe_allow_html=True)

    # ── Günlük özet ───────────────────────────────────────────────────────
    st.markdown(
        '<div style="height:1px;background:var(--color-border);margin:36px 0 28px;"></div>',
        unsafe_allow_html=True,
    )
    _render_daily_summary()

    # ── Footer ────────────────────────────────────────────────────────────
    render_footer()


if __name__ == "__main__" or True:
    main()
