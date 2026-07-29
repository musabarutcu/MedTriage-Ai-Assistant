"""
app.py
------
MedTriage — Uygulama Giriş Noktası

Akış (oturum başına bir kez):
  1. Splash ekranı   → 1.8 sn fade-in animasyonu
  2. KVKK onay ekranı → checkbox + "Kabul Et" butonu
  3. Triaj Kayıt Paneli → st.switch_page()

⚠️ Bu sistem bir portfolyo/eğitim prototipidir.
   Gerçek tıbbi cihaz değildir.
"""

import sys
import time
import base64
from pathlib import Path
from datetime import datetime

import streamlit as st

_PROJECT_ROOT = Path(__file__).parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.theme import apply_theme
from shared.queue_store import init_db, log_consent

_ASSETS = _PROJECT_ROOT / "assets"

# ---------------------------------------------------------------------------
# Sayfa yapılandırması
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="MedTriage AI Assistant",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Veritabanı başlat
# ---------------------------------------------------------------------------
init_db()

# ---------------------------------------------------------------------------
# Tema enjeksiyon
# ---------------------------------------------------------------------------
apply_theme()

# ---------------------------------------------------------------------------
# Session State başlangıç değerleri
# ---------------------------------------------------------------------------
if "app_step" not in st.session_state:
    st.session_state.app_step = "splash"
if "kvkk_accepted" not in st.session_state:
    st.session_state.kvkk_accepted = False
if "kvkk_timestamp" not in st.session_state:
    st.session_state.kvkk_timestamp = None


# ---------------------------------------------------------------------------
# Logo yardımcısı
# ---------------------------------------------------------------------------
def _logo_b64(filename: str) -> str | None:
    """SVG dosyasını base64 döndürür."""
    p = _ASSETS / filename
    if p.exists():
        try:
            return base64.b64encode(p.read_bytes()).decode("utf-8")
        except Exception:
            return None
    return None


def _logo_img(filename: str, width: int) -> str:
    b64 = _logo_b64(filename)
    if b64:
        return (
            f'<img src="data:image/svg+xml;base64,{b64}" '
            f'width="{width}" style="display:block;" alt="MedTriage">'
        )
    # Fallback — metin logosu
    return (
        '<div style="font-family:var(--font-sans);font-weight:900;'
        f'font-size:{width//5}px;letter-spacing:-0.02em;">'
        '<span style="color:#1B2535">MED</span>'
        '<span style="color:#7A1F2B">TRIAGE</span></div>'
    )


# ---------------------------------------------------------------------------
# SPLASH EKRANI
# ---------------------------------------------------------------------------
def _render_splash() -> None:
    """
    Tam ekran karşılama splash ekranı.
    Sıralama (dikey üstten alta):
      1. Amblem (logo-emblem.svg, 255px — 3x boyut)
      2. Wordmark (logo-wordmark.svg, 280px)
      3. Hoş geldiniz başlığı ve alt başlığı
    Dengeli dikey boşluklar ve ortalanmış görünüm.
    """
    logo_emblem = _logo_img("logo-emblem.svg", width=255)
    logo_wordmark = _logo_img("logo-wordmark.svg", width=280)

    splash_html = f"""
<div class="splash-screen">
<div class="splash-content">
<div style="display:flex; justify-content:center; align-items:center; margin-bottom:16px;">
{logo_emblem}
</div>
<div style="display:flex; justify-content:center; align-items:center; margin-bottom:20px;">
{logo_wordmark}
</div>
<div class="splash-title">MedTriage sistemine hoş geldiniz</div>
<div class="splash-subtitle">Acil servis triaj karar destek platformu</div>
</div>
</div>
"""
    st.markdown(splash_html, unsafe_allow_html=True)




# ---------------------------------------------------------------------------
# KVKK / GİZLİLİK ONAY EKRANI
# ---------------------------------------------------------------------------
def _render_kvkk() -> None:
    """
    Gizlilik bildirimi onay ekranı.
    Giriş ekranı sayfanın ortasında ortalanmış durumdadır.
    Sözleşme metni ve altındaki onay kontrolleri tam hizada yer alır.
    """
    logo_html = _logo_img("logo-emblem.svg", width=50)

    # 3 sütunlu yapı ile sayfada ortalama ([1, 6, 1] oranı ile mükemmel 820px genişlik)
    _, center_col, _ = st.columns([1, 6, 1])

    with center_col:
        card_html = f"""
<div style="background:var(--color-surface); border-radius:16px; box-shadow:var(--shadow-card-hover); border-top:4px solid var(--color-brand); border-left:1px solid var(--color-border); border-right:1px solid var(--color-border); border-bottom:1px solid var(--color-border); padding:32px 36px 28px; margin-bottom:20px;">
<div style="display:flex; align-items:center; gap:16px; margin-bottom:20px;">
{logo_html}
<div>
<div style="font-family:var(--font-sans); font-size:1.25rem; font-weight:700; color:var(--color-ink); letter-spacing:-0.01em; margin-bottom:4px;">Veri Kullanımı ve Gizlilik Bildirimi</div>
<div style="font-family:var(--font-sans); font-size:0.8rem; color:var(--color-ink-secondary);">Devam etmeden önce lütfen aşağıdaki bildirimi okuyunuz.</div>
</div>
</div>

<div style="height:1px; background:var(--color-border); margin-bottom:20px;"></div>

<div style="font-family:var(--font-sans); font-size:0.84rem; color:var(--color-ink-secondary); line-height:1.6; margin-bottom:18px; background:rgba(122,31,43,0.04); padding:12px 16px; border-radius:8px; border-left:3px solid var(--color-brand);">
MedTriage, acil servis triaj sürecinde sağlık personeline karar destek sunmak amacıyla geliştirilmiş bir prototip platformdur. Bu platformu kullanmaya devam etmeden önce lütfen aşağıdaki bildirimi okuyunuz.
</div>

<div style="max-height:360px; overflow-y:auto; padding:20px 24px; background:var(--color-canvas); border-radius:10px; border:1px solid var(--color-border); font-family:var(--font-sans); font-size:0.83rem; color:var(--color-ink); line-height:1.65;">
<div style="margin-bottom:16px;"><strong style="color:var(--color-brand); font-size:0.88rem;">1. Platformun Niteliği</strong><br>MedTriage bir akademik/portfolyo prototipidir ve gerçek bir tıbbi cihaz veya onaylı klinik yazılım değildir. Sistem üzerinden sunulan öneriler yalnızca karar destek amaçlıdır; hiçbir şekilde tıbbi tanı, tedavi önerisi veya klinik karar yerine geçmez. Nihai değerlendirme ve karar sorumluluğu her koşulda yetkili sağlık personeline aittir.</div>

<div style="margin-bottom:16px;"><strong style="color:var(--color-brand); font-size:0.88rem;">2. Kullanılan Veriler</strong><br>Bu platformda kullanılan veri seti (KTAS — Korean Triage and Acuity Scale), akademik olarak yayınlanmış, anonimleştirilmiş ve açık erişimli bir kaynaktır. Platform, gerçek ve kimliği belirli hiçbir hasta verisini toplamaz, işlemez veya saklamaz.</div>

<div style="margin-bottom:16px;"><strong style="color:var(--color-brand); font-size:0.88rem;">3. Oturum İçi Veri İşleme</strong><br>Bu prototipte girilen bilgiler (test amaçlı örnek hasta girdileri dahil) yalnızca oturum süresi boyunca, yerel olarak işlenir. Bu veriler harici bir sunucuya aktarılmaz, üçüncü taraflarla paylaşılmaz ve oturum sonunda kalıcı olarak saklanmaz.</div>

<div style="margin-bottom:16px;"><strong style="color:var(--color-brand); font-size:0.88rem;">4. Gerçek Kurumsal Kullanım İçin Not</strong><br>Bu platformun gerçek bir hastane ortamında kullanılması durumunda; işlenecek kişisel sağlık verilerinin kapsamı, işlenme amacı, saklama süresi ile ilgili kişinin 6698 sayılı Kişisel Verilerin Korunması Kanunu ("KVKK") kapsamındaki hakları (bilgi talep etme, düzeltme, silme, işlemeye itiraz etme dahil) ayrıca ve açıkça belirtilecek, gerekli aydınlatma metni ve açık rıza süreçleri uygulanacaktır.</div>

<div style="margin-bottom:16px;"><strong style="color:var(--color-brand); font-size:0.88rem;">5. Karar Destek Sisteminin Sınırları</strong><br>Sistem, kritik/acil bulgularda (kırmızı bayrak kuralı) otomatik olarak devre dışı kalacak şekilde tasarlanmıştır; bu tür durumlarda öneri üretmez, doğrudan acil müdahale uyarısı gösterir. Sistemin ürettiği tüm öneriler, ilgili sağlık personeli tarafından onaylanabilir veya gerekçe belirtilerek geçersiz kılınabilir.</div>

<div><strong style="color:var(--color-brand); font-size:0.88rem;">6. Onay</strong><br>"Kabul Ediyorum" seçeneğini işaretleyerek ve devam ederek, bu bildirimi okuduğunuzu, içeriğini anladığınızı ve platformun bir prototip/karar destek aracı olduğunu kabul ettiğinizi beyan edersiniz.</div>
</div>
</div>
"""
        st.markdown(card_html, unsafe_allow_html=True)

        # Kart genişliği ile 100% hizanlanan Checkbox + Buton kapsayıcısı
        col_check, col_btn = st.columns([3, 2])

        with col_check:
            st.markdown("<div style='padding-top:6px;'>", unsafe_allow_html=True)
            accepted = st.checkbox(
                "Okudum, anladım ve kabul ediyorum",
                key="kvkk_checkbox",
            )
            st.markdown("</div>", unsafe_allow_html=True)

        with col_btn:
            if st.button(
                "Kabul Et ve Devam Et →",
                key="kvkk_accept_btn",
                type="primary",
                use_container_width=True,
                disabled=not accepted,
            ):
                try:
                    log_consent(panel="app")
                except Exception:
                    pass

                st.session_state.kvkk_accepted = True
                st.session_state.kvkk_timestamp = datetime.now().isoformat()
                st.session_state.app_step = "done"
                st.rerun()

        # Alt dipnot
        st.markdown(
            '<div style="height:16px"></div>'
            '<div style="font-family:var(--font-sans); font-size:0.72rem; '
            'color:var(--color-ink-tertiary); text-align:center; line-height:1.6;">'
            'MedTriage — Portfolyo/Eğitim Prototipi · '
            'Bu sistem onaylı bir tıbbi cihaz değildir.'
            '</div>',
            unsafe_allow_html=True,
        )



# ---------------------------------------------------------------------------
# ANA YÖNLENDIRME
# ---------------------------------------------------------------------------
step = st.session_state.app_step

if step == "splash":
    # ── SPLASH: Göster → 1.8sn bekle → KVKK'ya geç ──────────────────────
    _render_splash()
    time.sleep(1.8)
    st.session_state.app_step = "kvkk"
    st.rerun()

elif step == "kvkk":
    # ── KVKK: Onay formu ─────────────────────────────────────────────────
    _render_kvkk()

else:
    # ── DONE: Triaj Kayıt Paneline yönlendir ─────────────────────────────
    st.switch_page("pages/1_Triaj_Kayit.py")
