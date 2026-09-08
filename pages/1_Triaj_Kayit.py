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
from shared.auth import require_access
from shared.icons import icon
from shared.symptoms import options as symptom_options, label as symptom_label

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
# Erişim kapısı — KVKK onayı + rol kontrolü (shared/auth.py)
# ---------------------------------------------------------------------------
require_access("triaj")

# ---------------------------------------------------------------------------
# Session State başlangıç değerleri
# ---------------------------------------------------------------------------
if "big_font"         not in st.session_state: st.session_state.big_font         = False
if "form_submitted"   not in st.session_state: st.session_state.form_submitted   = False
if "last_queue_id"    not in st.session_state: st.session_state.last_queue_id    = None


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
# FORM BÖLÜM KART YARDIMCISI
# ---------------------------------------------------------------------------
def _section_open(icon_name: str, title: str) -> None:
    """
    Form bölüm başlığı.

    Not: Bölüm başlığı bilinçli olarak bir "kart" DEĞİL, bir ayraç başlıktır.
    Streamlit her `st.markdown` çıktısını kendi kapsayıcısına sarar ve
    kapatılmamış etiketleri otomatik kapatır; dolayısıyla bir markdown
    çağrısıyla açılan <div>, sonraki widget'ları saramaz. Eskiden burada
    açılan `.form-section-card` kutusu bu yüzden boş bir beyaz kutu olarak
    çiziliyor, alanlar kutunun dışında kalıyordu. Form zaten tek bir beyaz
    kart (`stForm`) içinde olduğundan iç içe kart da gereksizdir.

    Başlık ikonu emoji değil inline SVG'dir: emoji platforma göre farklı
    çizilir, rengi ve boyutu tasarım token'larına bağlanamaz.
    """
    st.markdown(
        f'<div style="font-family:var(--font-sans);font-size:12px;'
        f'font-weight:600;text-transform:uppercase;letter-spacing:0.1em;'
        f'color:var(--color-brand);margin:8px 0 18px;padding-bottom:10px;'
        f'border-bottom:1px solid var(--color-border);'
        f'display:flex;align-items:center;gap:9px;">'
        f'{icon(icon_name, size=15, color="var(--color-brand)")}'
        f'<span>{title}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _section_close() -> None:
    """Bölümler arası nefes payı. (Kapatılacak bir kutu yok — bkz. _section_open.)"""
    st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# ANA SAYFA
# ---------------------------------------------------------------------------
def main() -> None:
    # ── Tema + Header ──────────────────────────────────────────────────────
    apply_theme(big_font=st.session_state.big_font)
    render_header("triaj")

    # ── Erişilebilirlik toggle ─────────────────────────────────────────────
    st.session_state.big_font = st.checkbox(
        "Büyük font modu",
        value=st.session_state.big_font,
        key="big_font_toggle",
        help="Tüm etiket ve butonları büyütür",
    )

    # ── Model durumu ──────────────────────────────────────────────────────
    if _load_model_bundle() is None:
        st.warning(
            "AI modeli yüklenmedi — sadece kırmızı bayrak kural motoru aktif. "
            "Etkinleştirmek için: `python model/train_model.py`"
        )

    # ── Önceki gönderim başarı mesajı ─────────────────────────────────────
    if st.session_state.form_submitted and st.session_state.last_queue_id:
        st.success(
            f"Hasta kuyruğa eklendi — Sıra No: **#{st.session_state.last_queue_id}**  \n"
            "Doktor panelinden takip edebilirsiniz."
        )
        st.session_state.form_submitted = False

    # ═══════════════════════════════════════════════════════════════════════
    # FORM — tek bir st.form içinde, TEK SÜTUN düzeni
    # Her bölüm kendi ayraç başlığıyla ayrılır
    # ═══════════════════════════════════════════════════════════════════════
    with st.form(key="triage_form", clear_on_submit=True):

        # ── KART 1: Kimlik Bilgileri ────────────────────────────────────
        _section_open("user", "Kimlik Bilgileri")

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
        _section_open("message-square", "Ana Başvuru Şikayeti")

        # Yapılandırılmış seçim — modele giden asıl sinyal.
        # Liste shared/symptoms.py'den gelir; aynı taksonomi eğitim
        # verisindeki İngilizce serbest metni de normalize eder, böylece
        # "form Türkçe / veri seti İngilizce" uyuşmazlığı ortadan kalkar.
        symptom_code = st.selectbox(
            "Ana Şikayet",
            options=[code for code, _ in symptom_options("TR")],
            format_func=lambda c: symptom_label(c, "TR"),
            index=None,
            placeholder="Şikayet seçiniz...",
            help="Hastanın başvuru nedenini listeden seçin. "
                 "Listede yoksa 'Diğer' seçip detay alanına yazın.",
        )

        complaint_detail = st.text_input(
            "Şikayet Detayı (opsiyonel)",
            placeholder="Örn: 2 saattir süren, sol kola yayılan baskı tarzında ağrı",
            help="Serbest metin. Kırmızı bayrak kuralları bu metni de tarar.",
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
        _section_open("heart-pulse", "Vital Bulgular")

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
        # NOT: Buraya eskiden ağrı skorunu renkli bir rozette tekrar eden
        # bir gösterge çiziliyordu. `st.form` içinde widget değişimi yeniden
        # çalıştırma tetiklemediğinden rozet her zaman formun yüklendiği andaki
        # değeri (0 — "Ağrı Yok") gösteriyordu: kaydırıcı 7'de dururken rozet
        # yeşil "0/10 · Ağrı Yok" yazıyordu. Klinik bir formda yanlış bilgi
        # gösteren bir bileşen, hiç göstermemekten kötüdür; kaldırıldı.
        # Kaydırıcı zaten seçili değeri tutamacın üzerinde gösteriyor.

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
            "Triaj Kaydını Gönder",
            icon=":material/local_hospital:",
            use_container_width=True,
            type="primary",
        )

    # ═══════════════════════════════════════════════════════════════════════
    # FORM GÖNDERİM İŞLEMİ
    # ═══════════════════════════════════════════════════════════════════════
    if not submitted:
        render_footer()
        return

    if not symptom_code:
        st.error("Ana şikayet seçilmeden triaj kaydı oluşturulamaz.")
        render_footer()
        return

    # Kuyrukta ve kural motorunda kullanılacak okunur şikayet metni
    chief_complaint = symptom_label(symptom_code, "TR")
    detail = complaint_detail.strip()
    if detail:
        chief_complaint = f"{chief_complaint} — {detail}"

    arrival_mode_map = {
        "Yürüyerek": 1, "Ambulans": 2, "Helikopter": 3,
        "Özel Araç": 4, "Tekerlekli Sandalye": 5,
        "Sedye / Taşınarak": 6, "Diğer": 7,
    }

    vitals = {
        "sbp": sbp, "dbp": dbp, "heart_rate": heart_rate,
        "resp_rate": resp_rate, "temperature": temperature,
        "spo2": spo2, "mental_status": mental_code,
        # Yaş, kural motorunun pediatrik eşikleri seçebilmesi için şart:
        # bebekte nabız 150 normaldir, erişkinde ciddi taşikardidir.
        "age": int(age),
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
        "symptom_code": symptom_code,
    }

    # Sonuç başlığı
    st.markdown(
        '<div style="font-family:var(--font-sans);font-size:1.1rem;'
        'font-weight:600;color:var(--color-ink);margin:28px 0 20px;'
        'letter-spacing:-0.01em;display:flex;align-items:center;gap:10px;">'
        + icon("activity", size=19, color="var(--color-brand)")
        + '<span>Değerlendirme Sonucu</span></div>',
        unsafe_allow_html=True,
    )

    # ── Adım 1: Kırmızı bayrak ────────────────────────────────────────────
    with st.spinner("Kırmızı bayrak kontrolü..."):
        flag_result = check_red_flags(vitals, detail, symptom_code=symptom_code)

    if flag_result["red_flag"]:
        reasons = flag_result.get("all_reasons", [flag_result.get("reason", "")])
        st.markdown(
            red_flag_alert_html(
                reasons=reasons,
                explanation="Model atlandı — kural motoru öncelik aldı.",
            ),
            unsafe_allow_html=True,
        )
        # Şiddet derecelendirmesi: eskiden her kırmızı bayrak KTAS-1'e
        # sabitleniyordu; apne ile hipertansif kriz aynı sayılıyordu.
        ai_priority    = flag_result.get("suggested_ktas") or 1
        ai_explanation = (f"Kırmızı bayrak (KTAS-{ai_priority} önerildi). "
                          f"Neden: {flag_result['reason']}")
        red_flag_bool  = True
        ai_confidence  = None      # Model çalışmadı; sahte güven gösterilmez
        rule_ktas      = ai_priority
    else:
        st.success("Kırmızı bayrak tespit edilmedi — AI değerlendirmesi başlıyor...")
        with st.spinner("AI modeli çalışıyor..."):
            prediction = _get_prediction(input_dict)

        if prediction:
            st.markdown(ai_result_card_html(prediction, lang="TR"), unsafe_allow_html=True)
            ai_priority    = prediction["ktas_level"]
            ai_explanation = prediction["explanation"]
            ai_confidence  = prediction["confidence"]
            if prediction.get("confidence_band") == "low":
                st.warning(
                    "Model bu vakada kararsız (düşük güven bandı). "
                    "Öneriyi bağlayıcı değil, ikinci görüş olarak değerlendirin."
                )
        else:
            st.warning("AI modeli kullanılamıyor. KTAS-3 (varsayılan) atandı.")
            ai_priority    = 3
            ai_explanation = "AI modeli yüklenmedi; varsayılan KTAS-3 atandı."
            ai_confidence  = None
        red_flag_bool = False
        rule_ktas     = None

    # ── Adım 2: Kuyruğa ekle ──────────────────────────────────────────────
    with st.spinner("Hasta kuyruğa ekleniyor..."):
        try:
            patient_id = add_patient(
                age=int(age), gender=gender,
                chief_complaint=chief_complaint.strip(),
                vitals=vitals, ai_priority=ai_priority,
                ai_explanation=ai_explanation, red_flag=red_flag_bool,
                ai_confidence=ai_confidence, symptom_code=symptom_code,
                rule_ktas=rule_ktas,
            )
            st.session_state.last_queue_id  = patient_id
            st.session_state.form_submitted = True
        except Exception as e:
            st.error(f"Kuyruğa ekleme hatası: {e}")
            logger.error(f"Kuyruk hatasi: {e}", exc_info=True)
            render_footer()
            return

    st.rerun()


# Streamlit her sayfayı doğrudan çalıştırır; koşula gerek yok.
# (Eskiden burada her zaman doğru olan `__name__ == "__main__" or True`
#  kalıbı vardı.)
main()
