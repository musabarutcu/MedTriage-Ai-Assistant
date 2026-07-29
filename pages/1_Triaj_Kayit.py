"""
pages/1_Triaj_Kayit.py
-----------------------
MedTriage — Triaj Kayıt Paneli

Hemşire/triaj personeli için hasta kayıt formu.
Form düzeni: TEK SÜTUN, tam genişlik, 3 ayrı kart bölümü.
Fonksiyonel mantık (kırmızı bayrak + AI + kuyruk ekleme) değişmedi.

⚠️ Bu form kayıt amaçlıdır, tıbbi tanı içermez.
"""

import sys
import logging
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.rules import check_red_flags
from shared.queue_store import add_patient, init_db
from shared.theme import (
    apply_theme,
    section_label_html,
    ktas_badge_html,
    red_flag_alert_html,
    ai_result_card_html,
)
from shared.header import render_header
from shared.footer import render_footer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sayfa yapılandırması
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="MedTriage AI Assistant",
    layout="wide",
    initial_sidebar_state="collapsed",
)

init_db()

# ---------------------------------------------------------------------------
# KVKK güvenlik kontrolü — onay yoksa ana sayfaya yönlendir
# ---------------------------------------------------------------------------
if not st.session_state.get("kvkk_accepted"):
    st.session_state.app_step = "kvkk"
    st.switch_page("app.py")
    st.stop()

# ---------------------------------------------------------------------------
# Session State başlangıç değerleri
# ---------------------------------------------------------------------------
if "big_font"         not in st.session_state: st.session_state.big_font         = False
if "form_submitted"   not in st.session_state: st.session_state.form_submitted   = False
if "last_queue_id"    not in st.session_state: st.session_state.last_queue_id    = None
if "voice_transcript" not in st.session_state: st.session_state.voice_transcript = ""


# ---------------------------------------------------------------------------
# MODEL YÜKLEME
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Model yükleniyor...")
def _load_model_bundle():
    try:
        from model.train_model import load_model_bundle
        return load_model_bundle()
    except FileNotFoundError:
        return None


def _get_prediction(input_dict: dict) -> dict | None:
    bundle = _load_model_bundle()
    if bundle is None:
        return None
    try:
        from model.train_model import predict_with_explanation
        return predict_with_explanation(input_dict, bundle)
    except Exception as e:
        logger.error(f"Tahmin hatasi: {e}")
        return None


# ---------------------------------------------------------------------------
# SES GİRDİSİ
# ---------------------------------------------------------------------------
def _render_voice_input() -> str | None:
    try:
        from streamlit_mic_recorder import mic_recorder
    except ImportError:
        st.caption("🎤 Ses girişi: `streamlit-mic-recorder` kurulu değil.")
        return None

    st.markdown(
        '<div style="font-family:var(--font-sans);font-size:0.8rem;'
        'color:var(--color-ink-secondary);margin-bottom:12px;line-height:1.55;">'
        '🎤 <strong style="color:var(--color-brand)">Mikrofona tıkla</strong> → şikayeti söyle → durdur'
        ' &nbsp;·&nbsp; Klavyeyle de yazabilirsiniz (ses opsiyonel)'
        ' &nbsp;·&nbsp; <strong style="color:var(--color-brand)">Sürekli dinleme yapılmaz</strong>'
        '</div>',
        unsafe_allow_html=True,
    )

    audio = mic_recorder(
        start_prompt="🎤 Kayıt Başlat",
        stop_prompt="⏹ Kayıt Durdur",
        just_once=True,
        use_container_width=False,
        key="mic_chief_complaint",
    )

    if audio is not None and audio.get("bytes"):
        st.info("🔄 Ses kaydı alındı. STT API entegre edin (Whisper/Google Speech). Şimdilik aşağıya yazabilirsiniz.")
        return None

    return None


# ---------------------------------------------------------------------------
# AĞRI RENK
# ---------------------------------------------------------------------------
def _pain_color(score: int) -> str:
    if score == 0:  return "var(--color-safe)"
    if score <= 3:  return "#8BC34A"
    if score <= 6:  return "var(--color-caution)"
    return "var(--color-critical)"


# ---------------------------------------------------------------------------
# FORM BÖLÜM KART YARDIMCISI
# ---------------------------------------------------------------------------
def _section_open(icon: str, title: str) -> None:
    """Form bölüm kartını açar (CSS: .form-section-card)."""
    st.markdown(
        f'<div class="form-section-card">'
        f'<div style="font-family:var(--font-sans);font-size:0.68rem;'
        f'font-weight:600;text-transform:uppercase;letter-spacing:0.1em;'
        f'color:var(--color-brand);margin-bottom:20px;">'
        f'{icon} &nbsp; {title}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _section_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# ANA SAYFA
# ---------------------------------------------------------------------------
def main() -> None:
    # ── Tema + Header ──────────────────────────────────────────────────────
    apply_theme(big_font=st.session_state.big_font)
    render_header("triaj")

    # ── Erişilebilirlik toggle ─────────────────────────────────────────────
    st.session_state.big_font = st.checkbox(
        "🔠 Büyük Font modu",
        value=st.session_state.big_font,
        key="big_font_toggle",
        help="Tüm etiket ve butonları büyütür",
    )

    # ── Model durumu ──────────────────────────────────────────────────────
    if _load_model_bundle() is None:
        st.warning(
            "⚠️ AI modeli yüklenmedi — sadece kırmızı bayrak kural motoru aktif. "
            "Etkinleştirmek için: `python model/train_model.py`"
        )

    # ── Önceki gönderim başarı mesajı ─────────────────────────────────────
    if st.session_state.form_submitted and st.session_state.last_queue_id:
        st.success(
            f"✅ Hasta kuyruğa eklendi — Sıra No: **#{st.session_state.last_queue_id}**  \n"
            "Doktor panelinden takip edebilirsiniz."
        )
        st.session_state.form_submitted = False

    # ═══════════════════════════════════════════════════════════════════════
    # FORM — tek bir st.form içinde, TEK SÜTUN düzeni
    # Her bölüm kendi .form-section-card kartında
    # ═══════════════════════════════════════════════════════════════════════
    with st.form(key="triage_form", clear_on_submit=True):

        # ── KART 1: Kimlik Bilgileri ────────────────────────────────────
        _section_open("👤", "Kimlik Bilgileri")

        age = st.number_input(
            "Yaş",
            min_value=0, max_value=120, value=40, step=1,
            help="Hastanın yaşı (0-120)",
        )

        gender = st.selectbox(
            "Cinsiyet",
            options=["Erkek", "Kadın", "Belirtilmedi"],
            index=0,
        )

        arrival_mode = st.selectbox(
            "Geliş Şekli",
            options=[
                "Yürüyerek", "Ambulans", "Helikopter",
                "Özel Araç", "Tekerlekli Sandalye",
                "Sedye / Taşınarak", "Diğer",
            ],
            index=0,
        )

        _section_close()

        # ── KART 2: Ana Başvuru Şikayeti ───────────────────────────────
        _section_open("💬", "Ana Başvuru Şikayeti")

        chief_complaint = st.text_input(
            "Ana Şikayet",
            value=st.session_state.voice_transcript,
            placeholder="Örn: göğüs ağrısı, nefes darlığı, baş dönmesi...",
            help="Hastanın başvuru nedenini kısaca yazın veya mikrofon butonunu kullanın",
            max_chars=500,
        )

        injury = st.selectbox(
            "Travma / Yaralanma",
            options=["Hayır", "Evet"],
            index=0,
            help="Hastada yaralanma veya travma var mı?",
        )

        has_pain = st.selectbox(
            "Ağrı Mevcut mu?",
            options=["Hayır", "Evet"],
            index=0,
        )

        _section_close()

        # ── KART 3: Vital Bulgular ──────────────────────────────────────
        _section_open("💗", "Vital Bulgular")

        sbp = st.number_input(
            "Sistolik Tansiyon (mmHg)",
            min_value=40, max_value=300, value=120, step=1,
            help="Büyük tansiyon değeri. Normal: 90-140 mmHg",
        )

        dbp = st.number_input(
            "Diyastolik Tansiyon (mmHg)",
            min_value=20, max_value=200, value=80, step=1,
            help="Küçük tansiyon değeri. Normal: 60-90 mmHg",
        )

        heart_rate = st.number_input(
            "Nabız (atım/dk)",
            min_value=20, max_value=300, value=80, step=1,
            help="Kalp atım hızı. Normal: 60-100 atım/dk",
        )

        resp_rate = st.number_input(
            "Solunum Hızı (nefes/dk)",
            min_value=4, max_value=60, value=16, step=1,
            help="Dakikada alınan nefes sayısı. Normal: 12-20",
        )

        temperature = st.number_input(
            "Vücut Isısı (°C)",
            min_value=25.0, max_value=45.0, value=36.6,
            step=0.1, format="%.1f",
            help="Ateş değeri. Normal: 36-37.5°C | Ateş: >38°C",
        )

        spo2 = st.number_input(
            "SpO2 — Oksijen Satürasyonu (%)",
            min_value=50, max_value=100, value=98, step=1,
            help="Periferik oksijen saturasyonu. Normal: ≥95% | Kritik: <90%",
        )

        pain_scale = st.slider(
            "Ağrı Skoru (NRS 0-10)",
            min_value=0, max_value=10, value=0, step=1,
            help="0=Ağrı yok | 1-3=Hafif | 4-6=Orta | 7-10=Şiddetli",
        )
        # Ağrı renk rozeti (pill şeklinde, semantik renk)
        pain_labels = {
            0: "Ağrı Yok", 1: "Çok Hafif", 2: "Hafif", 3: "Hafif",
            4: "Orta", 5: "Orta", 6: "Orta-Şiddetli",
            7: "Şiddetli", 8: "Şiddetli", 9: "Çok Şiddetli", 10: "Dayanılmaz",
        }
        pain_col = _pain_color(pain_scale)
        st.markdown(
            f'<div style="display:flex;margin-top:8px;margin-bottom:12px;">'
            f'<div style="font-family:var(--font-mono);font-weight:600;font-size:0.92rem;'
            f'color:{pain_col};background:{pain_col}18;padding:6px 18px;'
            f'border-radius:999px;border:1px solid {pain_col}40;">'
            f'{pain_scale}/10 &nbsp;·&nbsp; {pain_labels.get(pain_scale, "")}'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        mental_status = st.selectbox(
            "Mental Durum (AVPU)",
            options=[
                "1 — Alert (Uyanık ve Oryante)",
                "2 — Verbal (Sesli Uyarıya Yanıt)",
                "3 — Pain (Ağrılı Uyarıya Yanıt)",
                "4 — Unresponsive (Yanıtsız)",
            ],
            index=0,
            help="AVPU skalası: Alert → Verbal → Pain → Unresponsive",
        )
        mental_code = int(mental_status.split(" ")[0])

        _section_close()

        # ── Gönder butonu ──────────────────────────────────────────────
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "🏥  Triaj Kaydını Gönder",
            use_container_width=True,
            type="primary",
        )

    # ═══════════════════════════════════════════════════════════════════════
    # SES GİRDİSİ — form DIŞINDA (widget state uyumluluğu)
    # ═══════════════════════════════════════════════════════════════════════
    _section_open("🎤", "Ses ile Şikayet Girişi")
    st.markdown(
        '<span style="font-family:var(--font-sans);font-size:0.78rem;'
        'color:var(--color-ink-secondary);font-style:italic;">Opsiyonel — '
        'Sonucu \'Ana Şikayet\' alanına kopyalayabilirsiniz.</span>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="recording-active">', unsafe_allow_html=True)
    voice_text = _render_voice_input()
    st.markdown("</div>", unsafe_allow_html=True)
    _section_close()

    if voice_text:
        st.session_state.voice_transcript = voice_text
        st.rerun()

    # ═══════════════════════════════════════════════════════════════════════
    # FORM GÖNDERİM İŞLEMİ — iş mantığı değişmedi
    # ═══════════════════════════════════════════════════════════════════════
    if not submitted:
        render_footer()
        return

    if not chief_complaint.strip():
        st.error("❌ Ana şikayet alanı boş bırakılamaz.")
        render_footer()
        return

    arrival_mode_map = {
        "Yürüyerek": 1, "Ambulans": 2, "Helikopter": 3,
        "Özel Araç": 4, "Tekerlekli Sandalye": 5,
        "Sedye / Taşınarak": 6, "Diğer": 7,
    }

    vitals = {
        "sbp": sbp, "dbp": dbp, "heart_rate": heart_rate,
        "resp_rate": resp_rate, "temperature": temperature,
        "spo2": spo2, "mental_status": mental_code,
    }
    input_dict = {
        "age":           int(age),
        "gender":        1 if gender == "Erkek" else 2,
        "arrival_mode":  arrival_mode_map.get(arrival_mode, 1),
        "injury":        1 if injury == "Evet" else 2,
        "has_pain":      1 if has_pain == "Evet" else 0,
        "pain_scale":    float(pain_scale),
        "mental_status": mental_code,
        "sbp": float(sbp), "dbp": float(dbp),
        "heart_rate": float(heart_rate), "resp_rate": float(resp_rate),
        "temperature": float(temperature), "spo2": float(spo2),
        "patients_per_hour": 5,
    }

    # Sonuç başlığı
    st.markdown(
        '<div style="font-family:var(--font-sans);font-size:1.1rem;'
        'font-weight:600;color:var(--color-ink);margin:28px 0 20px;'
        'letter-spacing:-0.01em;">📊 &nbsp; Değerlendirme Sonucu</div>',
        unsafe_allow_html=True,
    )

    # ── Adım 1: Kırmızı bayrak ────────────────────────────────────────────
    with st.spinner("Kırmızı bayrak kontrolü..."):
        flag_result = check_red_flags(vitals, chief_complaint)

    if flag_result["red_flag"]:
        reasons = flag_result.get("all_reasons", [flag_result.get("reason", "")])
        st.markdown(
            red_flag_alert_html(
                reasons=reasons,
                explanation="Model atlandı — kural motoru öncelik aldı.",
            ),
            unsafe_allow_html=True,
        )
        ai_priority    = 1
        ai_explanation = f"Kırmızı bayrak tetiklendi. Neden: {flag_result['reason']}"
        red_flag_bool  = True
    else:
        st.success("✅ Kırmızı bayrak tespit edilmedi — AI değerlendirmesi başlıyor...")
        with st.spinner("AI modeli çalışıyor..."):
            prediction = _get_prediction(input_dict)

        if prediction:
            st.markdown(ai_result_card_html(prediction, lang="TR"), unsafe_allow_html=True)
            ai_priority    = prediction["ktas_level"]
            ai_explanation = prediction["explanation"]
        else:
            st.warning("⚠️ AI modeli kullanılamıyor. KTAS-3 (varsayılan) atandı.")
            ai_priority    = 3
            ai_explanation = "AI modeli yüklenmedi; varsayılan KTAS-3 atandı."
        red_flag_bool = False

    # ── Adım 2: Kuyruğa ekle ──────────────────────────────────────────────
    with st.spinner("Hasta kuyruğa ekleniyor..."):
        try:
            patient_id = add_patient(
                age=int(age), gender=gender,
                chief_complaint=chief_complaint.strip(),
                vitals=vitals, ai_priority=ai_priority,
                ai_explanation=ai_explanation, red_flag=red_flag_bool,
            )
            st.session_state.last_queue_id  = patient_id
            st.session_state.form_submitted = True
            st.session_state.voice_transcript = ""
        except Exception as e:
            st.error(f"❌ Kuyruğa ekleme hatası: {e}")
            logger.error(f"Kuyruk hatasi: {e}", exc_info=True)
            render_footer()
            return

    st.rerun()


if __name__ == "__main__" or True:
    main()
