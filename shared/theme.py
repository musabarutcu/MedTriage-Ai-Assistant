"""
shared/theme.py
---------------
MedTriage Tasarım Sistemi — Apple ilhamlı, temiz ve klinik.

══════════════════════════════════════════════════════════════════
FONT ENTEGRASYONU (YÖNTEM B → YÖNTEM C sıralaması)
══════════════════════════════════════════════════════════════════
  YÖNTEM A (pip install geist-font) → BAŞARISIZ (PyPI'da mevcut değil)
  YÖNTEM B (git clone vercel/geist-font) → Deneniyor; başarılı olursa
    static/fonts/ klasörüne kopyalanır ve @font-face ile tanımlanır.
  YÖNTEM C (Google Fonts — Inter) → A ve B başarısız olursa fallback.
    Inter, Geist ile aynı neo-grotesque sans-serif ailesinden; göz
    büyüklüğü ve karakter oranları çok benzer. Apple-style tasarımda
    fark neredeyse ayırt edilemez.
  Şu anda: YÖNTEM C aktif (Inter + JetBrains Mono via Google Fonts)
  Geist woff2 dosyaları elde edilirse: _font_css() içindeki @import
  satırını değiştirip @font-face bloğunu ekle, font-family değerini
  'Geist' olarak güncelle.

══════════════════════════════════════════════════════════════════
KRİTİK RENK AYIRIMI — ASLA KARIŞTIRMA
══════════════════════════════════════════════════════════════════
  --color-brand    (#7A1F2B) : SADECE marka kimliği
                               → Butonlar, wordmark, logo, başlık aksanı
                               → Öncelik rozetlerinde KESİNLİKLE kullanılmaz

  --color-critical (#FF3B30) : SADECE klinik aciliyet sinyali
                               → KTAS-1 rozeti, kırmızı bayrak uyarısı
                               → Marka / buton renginde KESİNLİKLE kullanılmaz

  Bu ayrım kasıtlıdır: Bordo = MedTriage kimliği görüldüğünde
  "bu sistemin arayüzü" deriz; kırmızı = klinik tehlike sinyali görüldüğünde
  "bu hasta kritik" deriz. İki sinyalin karışması medikal güvenliği bozar.
══════════════════════════════════════════════════════════════════

Kullanım:
    from shared.theme import apply_theme, brand_header_html
    from shared.theme import ktas_badge_html, red_flag_alert_html
    from shared.theme import ai_result_card_html, patient_card_html
    from shared.theme import section_label_html, card_html, KTAS_CONFIG
"""

from __future__ import annotations
import streamlit as st

# ---------------------------------------------------------------------------
# YÖNTEM C: Google Fonts — Inter (sans) + JetBrains Mono (mono)
# Geist woff2 dosyaları temin edilirse bu URL'yi değiştir ve
# @font-face bloğunu _font_css() içine ekle.
# ---------------------------------------------------------------------------
_GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Inter:wght@400;500;600&"
    "family=JetBrains+Mono:wght@400;500;600&"
    "display=swap"
)

# ---------------------------------------------------------------------------
# KTAS KONFİGÜRASYONU — renk sistemiyle eşleşmiş
# --color-critical: SADECE KTAS-1 (resüsitasyon) için
# Diğer seviyeler kendi semantik rengiyle
# ---------------------------------------------------------------------------
KTAS_CONFIG: dict[int, dict] = {
    1: {
        "emoji":    "●",
        "color":    "#FF3B30",              # --color-critical — YALNIZCA KTAS-1
        "bg":       "rgba(255,59,48,0.10)",
        "label_tr": "Resüsitasyon",
        "label_en": "Resuscitation",
        "sub_tr":   "Hemen",
        "sub_en":   "Immediately",
    },
    2: {
        "emoji":    "●",
        "color":    "#FF9500",              # --color-warning
        "bg":       "rgba(255,149,0,0.12)",
        "label_tr": "Acil",
        "label_en": "Emergent",
        "sub_tr":   "≤15 dk",
        "sub_en":   "≤15 min",
    },
    3: {
        "emoji":    "●",
        "color":    "#8B6914",              # Koyu sarı (WCAG AA kontrast için)
        "bg":       "rgba(255,204,0,0.15)",
        "label_tr": "Acil-Değil",
        "label_en": "Urgent",
        "sub_tr":   "≤60 dk",
        "sub_en":   "≤60 min",
    },
    4: {
        "emoji":    "●",
        "color":    "#1A7D3F",              # --color-safe koyu tonu
        "bg":       "rgba(52,199,89,0.10)",
        "label_tr": "Az Acil",
        "label_en": "Less Urgent",
        "sub_tr":   "≤120 dk",
        "sub_en":   "≤120 min",
    },
    5: {
        "emoji":    "●",
        "color":    "#004BB5",              # --color-info koyu tonu (WCAG AA)
        "bg":       "rgba(0,113,227,0.10)",
        "label_tr": "Acil Değil",
        "label_en": "Non-Urgent",
        "sub_tr":   "≤240 dk",
        "sub_en":   "≤240 min",
    },
}

# ECG/nabız çizgisi SVG ikonu (--color-brand ile — marka ikonu)
_ECG_ICON_SVG = """\
<svg width="22" height="22" viewBox="0 0 24 24" fill="none"
     xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <path d="M2 12h3.5L8 5l4 14 3-9 2 4H22"
        stroke="#7A1F2B" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


# ---------------------------------------------------------------------------
# CSS BLOKLARI
# ---------------------------------------------------------------------------

def _font_css() -> str:
    """
    Font import bildirimleri.
    YÖNTEM C aktif: Google Fonts üzerinden Inter + JetBrains Mono.
    Geist woff2 elde edilirse:
      1. @import satırını kaldır
      2. @font-face { font-family: 'Geist'; src: url('../static/fonts/Geist-Regular.woff2') ... } ekle
      3. --font-sans değerini 'Geist' olarak güncelle
    """
    return f"@import url('{_GOOGLE_FONTS_URL}');\n"


def _root_css() -> str:
    """CSS custom property (tasarım token) tanımlamaları."""
    return """
:root {
    /* ── Tip Sistemi ──────────────────────────────────────────────── */
    /* YÖNTEM C: Inter (sans) + JetBrains Mono — Geist fallback  */
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, 'Cascadia Code', monospace;

    /* ── Marka Rengi ──────────────────────────────────────────────── */
    /* KULLANIM: SADECE butonlar, wordmark, logo, başlık aksanı       */
    /* ÖNCELIK ROZETLERİNDE KESİNLİKLE KULLANILMAZ                   */
    --color-brand:        #7A1F2B;
    --color-brand-hover:  #611620;
    --color-brand-subtle: rgba(122, 31, 43, 0.08);

    /* ── Klinik Öncelik Renkleri ──────────────────────────────────── */
    /* --color-critical: SADECE KTAS-1 rozeti ve kırmızı bayrak       */
    /* MARKA / BUTON renginde KESİNLİKLE KULLANILMAZ                  */
    --color-critical:  #FF3B30;
    --color-warning:   #FF9500;
    --color-caution:   #FFCC00;
    --color-safe:      #34C759;
    --color-info:      #0071E3;

    /* ── Metinler ─────────────────────────────────────────────────── */
    --color-ink:           #1D1D1F;
    --color-ink-secondary: #6E6E73;
    --color-ink-tertiary:  #AEAEB2;

    /* ── Yüzeyler ─────────────────────────────────────────────────── */
    --color-surface:      #FFFFFF;
    --color-canvas:       #F5F5F7;   /* Apple klasik açık gri — parlak beyaz değil */
    --color-border:       #E5E5EA;
    --color-border-strong:#C7C7CC;

    /* ── Gölgeler ─────────────────────────────────────────────────── */
    --shadow-card:       0 4px 24px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-card-hover: 0 10px 40px rgba(0,0,0,0.10), 0 2px 6px rgba(0,0,0,0.06);
    --shadow-button:     0 2px 8px rgba(122,31,43,0.28);

    /* ── Köşe Yarıçapları ─────────────────────────────────────────── */
    --radius-card:   20px;    /* Kartlar — hasta kartları, form konteynerleri */
    --radius-button: 6px;     /* Butonlar — keskin ve minimal                */
    --radius-badge:  999px;   /* Rozetler — tam pill şekli                   */
    --radius-input:  10px;    /* Form alanları                               */
    --radius-alert:  12px;    /* Uyarı kutuları                              */
}
"""


def _base_css() -> str:
    """Tüm uygulama için temel stil kuralları."""
    return """
/* ── Arka plan ve font ────────────────────────────────────────── */
html, body, .stApp {
    font-family: var(--font-sans) !important;
    background-color: var(--color-canvas) !important;
    color: var(--color-ink) !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
    line-height: 1.5;
}

/* ── Sayfa genişliği ve boşluklar ────────────────────────────── */
.main .block-container {
    padding: 2rem 3rem 5rem !important;
    max-width: 1300px !important;
    margin: 0 auto !important;
}

/* ── Streamlit varsayılan UI elemanları gizle ─────────────────── */
[data-testid="stHeader"]       { display: none !important; }
[data-testid="stToolbar"]      { display: none !important; }
[data-testid="stDecoration"]   { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
footer { display: none !important; }
#MainMenu { display: none !important; }

/* Sidebar ve sol navigasyonu gizle (header ile özel nav kullanılıyor) */
[data-testid="stSidebar"]         { display: none !important; }
[data-testid="collapsedControl"]  { display: none !important; }
[data-testid="stSidebarNav"]      { display: none !important; }
[data-testid="stSidebarNavItems"] { display: none !important; }
section[data-testid="stSidebar"]  { display: none !important; }

/* ── Form container (kart görünümü) ──────────────────────────── */
.form-section-card {
    background: var(--color-surface) !important;
    border-radius: var(--radius-card) !important;
    box-shadow: var(--shadow-card) !important;
    padding: 32px 36px !important;
    border: 1px solid var(--color-border) !important;
    margin-bottom: 36px !important;
}

[data-testid="stForm"] {
    background: var(--color-surface) !important;
    border-radius: var(--radius-card) !important;
    box-shadow: var(--shadow-card) !important;
    padding: 36px 40px !important;
    border: none !important;
    margin-bottom: 28px !important;
}

/* ── st.container(border=True) → apple kart stili ────────────── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    border-radius: var(--radius-card) !important;
    border: 1px solid var(--color-border) !important;
    background: var(--color-surface) !important;
    box-shadow: var(--shadow-card) !important;
    padding: 20px 24px !important;
}

/* ── Bölüm ayırıcı (divider) ─────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid var(--color-border) !important;
    margin: 2rem 0 !important;
}

/* ── Ses Kayıt Animasyonu ────────────────────────────────────── */
/* --color-critical kullanılır: kayıt = klinik alarm sinyali hissi */
@keyframes pulse-recording {
    0%   { box-shadow: 0 0 0 0   rgba(255, 59, 48, 0.45); }
    60%  { box-shadow: 0 0 0 12px rgba(255, 59, 48, 0.00); }
    100% { box-shadow: 0 0 0 0   rgba(255, 59, 48, 0.00); }
}
.recording-active button {
    animation: pulse-recording 1.8s infinite !important;
    border-color: var(--color-critical) !important;
    color: var(--color-critical) !important;
}

/* ── Kart hover efekti ────────────────────────────────────────── */
/* Hafif transition: all 200ms ease — abartılı animasyon yok      */
.med-card {
    background: var(--color-surface);
    border-radius: var(--radius-card);
    box-shadow: var(--shadow-card);
    padding: 28px 32px;
    margin-bottom: 20px;
    transition: box-shadow 200ms ease, transform 200ms ease;
    border: none;
}
.med-card:hover {
    box-shadow: var(--shadow-card-hover);
    transform: translateY(-2px);
}

/* ── Expander ─────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid var(--color-border) !important;
    border-radius: var(--radius-card) !important;
    background: var(--color-surface) !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    padding: 16px 24px !important;
    font-family: var(--font-sans) !important;
    font-weight: 500 !important;
    color: var(--color-ink) !important;
}

/* ── Kaydırma çubuğu ─────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--color-canvas); border-radius: 3px; }
::-webkit-scrollbar-thumb { background: var(--color-border-strong); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--color-ink-tertiary); }

/* ── Splash Ekranı ───────────────────────────────────────────── */
@keyframes splashIn {
    from { opacity: 0; transform: scale(0.92) translateY(10px); }
    to   { opacity: 1; transform: scale(1)    translateY(0px);  }
}
.splash-screen {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 78vh;
    text-align: center;
    background: linear-gradient(160deg, var(--color-canvas) 0%, rgba(122,31,43,0.04) 100%);
    border-radius: var(--radius-card);
}
.splash-content {
    animation: splashIn 0.75s ease-out forwards;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    padding: 60px 40px;
}
.splash-title {
    font-family: var(--font-sans);
    font-size: 1.4rem;
    font-weight: 600;
    color: var(--color-ink);
    margin: 8px 0 0;
    letter-spacing: -0.02em;
}
.splash-subtitle {
    font-family: var(--font-sans);
    font-size: 0.9rem;
    color: var(--color-ink-secondary);
    margin: 0;
}

/* ── KVKK Onay Ekranı ────────────────────────────────────────── */
.kvkk-card {
    background: var(--color-surface);
    border-radius: var(--radius-card);
    box-shadow: var(--shadow-card-hover);
    padding: 44px 52px;
    max-width: 700px;
    width: 100%;
    border-top: 4px solid var(--color-brand);
}
.kvkk-consent-text {
    font-family: var(--font-sans);
    font-size: 0.85rem;
    color: var(--color-ink);
    line-height: 1.75;
}
.kvkk-consent-text li { margin-bottom: 10px; }

/* KVKK checkbox — --color-brand ile işaretleme */
.kvkk-consent .stCheckbox > label {
    font-family: var(--font-sans) !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    color: var(--color-ink) !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
}

/* ── Form Bölüm Kartı (tek sütun form düzeninde her alt bölüm) ── */
.form-section-card {
    background: var(--color-surface);
    border-radius: var(--radius-card);
    box-shadow: var(--shadow-card);
    padding: 28px 32px;
    margin-bottom: 24px;
    border-left: 4px solid var(--color-brand);
}

/* Seçili hasta kartı — --color-brand sol kenar aksanı */
.patient-selected-accent {
    border-left: 4px solid var(--color-brand) !important;
}
"""


def _typography_css() -> str:
    """Başlık ve gövde metin stilleri."""
    return """
/* ── Form etiketleri (eyebrow text stili) ────────────────────── */
.stTextInput > label,
.stNumberInput > label,
.stSelectbox > label,
.stSlider > label,
.stTextArea > label,
.stCheckbox > label,
[data-testid="stWidgetLabel"] {
    font-family: var(--font-sans) !important;
    font-size: 0.7rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: var(--color-ink-secondary) !important;
    margin-bottom: 6px !important;
    line-height: 1.4 !important;
}

/* ── Metrik değerleri (monospace — tabular nums) ──────────────── */
[data-testid="stMetricValue"] {
    font-family: var(--font-mono) !important;
    font-size: 1.9rem !important;
    font-weight: 600 !important;
    color: var(--color-ink) !important;
    font-variant-numeric: tabular-nums;
    line-height: 1.2 !important;
}
[data-testid="stMetricLabel"] {
    font-family: var(--font-sans) !important;
    font-size: 0.68rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: var(--color-ink-secondary) !important;
}
[data-testid="stMetricDelta"] > div {
    font-family: var(--font-mono) !important;
    font-size: 0.78rem !important;
}

/* ── Markdown başlıkları ─────────────────────────────────────── */
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
    font-family: var(--font-sans) !important;
    color: var(--color-ink) !important;
    line-height: 1.2 !important;
    letter-spacing: -0.01em !important;
}
.stMarkdown h1 { font-weight: 600 !important; font-size: 1.6rem !important; }
.stMarkdown h2 { font-weight: 600 !important; font-size: 1.2rem !important; }
.stMarkdown h3 { font-weight: 500 !important; font-size: 1rem   !important; }

/* ── Caption metni ───────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] {
    font-family: var(--font-sans) !important;
    font-size: 0.75rem !important;
    color: var(--color-ink-secondary) !important;
    line-height: 1.5 !important;
}
"""


def _input_css() -> str:
    """Form eleman stilleri."""
    return """
/* ── Metin ve sayı girişleri ─────────────────────────────────── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea > div > div > textarea {
    font-family: var(--font-mono) !important;
    font-size: 0.88rem !important;
    border-radius: var(--radius-input) !important;
    border: 1px solid var(--color-border) !important;
    background-color: var(--color-surface) !important;
    color: var(--color-ink) !important;
    padding: 11px 14px !important;
    transition: border-color 150ms ease, box-shadow 150ms ease !important;
    line-height: 1.5 !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--color-brand) !important;
    box-shadow: 0 0 0 3px rgba(122,31,43,0.12) !important;
    outline: none !important;
}

/* ── Placeholder ─────────────────────────────────────────────── */
.stTextInput > div > div > input::placeholder,
.stTextArea > div > div > textarea::placeholder {
    color: var(--color-ink-tertiary) !important;
    font-style: italic;
}

/* ── Selectbox ───────────────────────────────────────────────── */
.stSelectbox > div > div {
    border-radius: var(--radius-input) !important;
    border: 1px solid var(--color-border) !important;
    background: var(--color-surface) !important;
    font-family: var(--font-sans) !important;
    font-size: 0.88rem !important;
    color: var(--color-ink) !important;
    transition: border-color 150ms ease !important;
}
.stSelectbox > div > div:focus-within {
    border-color: var(--color-brand) !important;
    box-shadow: 0 0 0 3px rgba(122,31,43,0.12) !important;
}

/* ── Number input ────────────────────────────────────────────── */
.stNumberInput > div > div > div > button {
    background: var(--color-canvas) !important;
    border: 1px solid var(--color-border) !important;
    color: var(--color-ink-secondary) !important;
    border-radius: 6px !important;
}
.stNumberInput > div > div > div > button:hover {
    background: var(--color-border) !important;
    color: var(--color-ink) !important;
}

/* ── Slider ──────────────────────────────────────────────────── */
.stSlider [data-testid="stTickBarMin"],
.stSlider [data-testid="stTickBarMax"] {
    font-family: var(--font-mono) !important;
    color: var(--color-ink-secondary) !important;
    font-size: 0.72rem !important;
}
.stSlider [data-testid="stThumbValue"] {
    font-family: var(--font-mono) !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    color: var(--color-brand) !important;
}
"""


def _button_css() -> str:
    """
    Buton stilleri.

    ┌─────────────────────────────────────────────────────────────┐
    │  Birincil (type='primary' / form submit):                   │
    │    --color-brand arka plan + beyaz metin                    │
    │    hover: --color-brand-hover + gölge + hafif yükselme      │
    │                                                             │
    │  İkincil (type='secondary' / diğer):                       │
    │    --color-surface arka plan + ince border + --color-ink    │
    │    hover: --color-canvas arka plan + border güçlenme        │
    └─────────────────────────────────────────────────────────────┘

    NOT: --color-brand SADECE buton arka planında kullanılır.
    Klinik öncelik (--color-critical) butonlarda ASLA kullanılmaz.
    """
    return """
/* ── Tüm butonlar — temel ───────────────────────────────────── */
.stButton > button,
.stFormSubmitButton > button {
    font-family: var(--font-sans) !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    border-radius: var(--radius-button) !important;
    padding: 12px 24px !important;
    transition: all 200ms ease !important;
    cursor: pointer !important;
    line-height: 1.4 !important;
    letter-spacing: 0.01em !important;
    white-space: nowrap !important;
}

/* ── Birincil buton: --color-brand ──────────────────────────── */
/* UYARI: --color-critical burada ASLA kullanılmaz              */
.stFormSubmitButton > button,
[data-testid="baseButton-primary"] {
    background: var(--color-brand) !important;
    color: #FFFFFF !important;
    border: none !important;
    box-shadow: none !important;
}
.stFormSubmitButton > button:hover,
[data-testid="baseButton-primary"]:hover {
    background: var(--color-brand-hover) !important;
    box-shadow: var(--shadow-button) !important;
    transform: translateY(-1px) !important;
}
.stFormSubmitButton > button:active,
[data-testid="baseButton-primary"]:active {
    transform: translateY(0) !important;
    box-shadow: none !important;
}

/* ── İkincil buton: surface ──────────────────────────────────── */
.stButton > button,
[data-testid="baseButton-secondary"] {
    background: var(--color-surface) !important;
    color: var(--color-ink) !important;
    border: 1px solid var(--color-border) !important;
    box-shadow: none !important;
}
.stButton > button:hover,
[data-testid="baseButton-secondary"]:hover {
    background: var(--color-canvas) !important;
    border-color: var(--color-border-strong) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
}
.stButton > button:active,
[data-testid="baseButton-secondary"]:active {
    transform: translateY(0) !important;
}
"""


def _alert_css() -> str:
    """Streamlit uyarı bileşenlerinin Apple stilinde yeniden yazılması."""
    return """
/* ── Başarı (success) ───────────────────────────────────────── */
div.stSuccess, .stSuccess {
    background: rgba(52, 199, 89, 0.08) !important;
    border-left: 4px solid var(--color-safe) !important;
    border-radius: 0 var(--radius-alert) var(--radius-alert) 0 !important;
    color: #1A7D3F !important;
    font-family: var(--font-sans) !important;
    padding: 14px 18px !important;
}
/* ── Hata (error): --color-critical — klinik uyarı ─────────── */
div.stError, .stError {
    background: rgba(255, 59, 48, 0.07) !important;
    border-left: 4px solid var(--color-critical) !important;
    border-radius: 0 var(--radius-alert) var(--radius-alert) 0 !important;
    color: #C41E3A !important;
    font-family: var(--font-sans) !important;
    padding: 14px 18px !important;
}
/* ── Uyarı (warning) ─────────────────────────────────────────── */
div.stWarning, .stWarning {
    background: rgba(255, 149, 0, 0.08) !important;
    border-left: 4px solid var(--color-warning) !important;
    border-radius: 0 var(--radius-alert) var(--radius-alert) 0 !important;
    color: #7A4500 !important;
    font-family: var(--font-sans) !important;
    padding: 14px 18px !important;
}
/* ── Bilgi (info) ────────────────────────────────────────────── */
div.stInfo, .stInfo {
    background: rgba(0, 113, 227, 0.07) !important;
    border-left: 4px solid var(--color-info) !important;
    border-radius: 0 var(--radius-alert) var(--radius-alert) 0 !important;
    color: #003D7A !important;
    font-family: var(--font-sans) !important;
    padding: 14px 18px !important;
}
/* ── Alert içindeki metinler ─────────────────────────────────── */
div.stSuccess p, div.stError p, div.stWarning p, div.stInfo p {
    font-family: var(--font-sans) !important;
    font-size: 0.875rem !important;
    line-height: 1.5 !important;
    margin: 0 !important;
}
"""


def _dataframe_css() -> str:
    """Tablo ve dataframe stilleri."""
    return """
/* ── Dataframe ───────────────────────────────────────────────── */
[data-testid="stDataFrame"] > div {
    border-radius: var(--radius-card) !important;
    border: 1px solid var(--color-border) !important;
    overflow: hidden !important;
    background: var(--color-surface) !important;
}
[data-testid="stDataFrame"] thead {
    background: var(--color-canvas) !important;
}
[data-testid="stDataFrame"] th {
    font-family: var(--font-sans) !important;
    font-size: 0.68rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: var(--color-ink-secondary) !important;
    padding: 10px 14px !important;
    border-bottom: 1px solid var(--color-border) !important;
}
[data-testid="stDataFrame"] td {
    font-family: var(--font-mono) !important;
    font-size: 0.82rem !important;
    color: var(--color-ink) !important;
    padding: 10px 14px !important;
    font-variant-numeric: tabular-nums !important;
    border-bottom: 1px solid var(--color-border) !important;
}
"""


def _big_font_css(enabled: bool) -> str:
    """Büyük font modu — erişilebilirlik için tüm metin öğesini ~%120 ölçekler."""
    if not enabled:
        return ""
    return """
/* ── Büyük Font Modu (erişilebilirlik) ────────────────────────── */
html { font-size: 118% !important; }
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea > div > div > textarea {
    font-size: 1.02rem !important;
    padding: 13px 16px !important;
}
.stButton > button, .stFormSubmitButton > button {
    font-size: 1rem !important;
    padding: 14px 28px !important;
}
[data-testid="stMetricValue"] { font-size: 2.3rem !important; }
.stTextInput > label,
.stNumberInput > label,
.stSelectbox > label,
.stSlider > label,
.stTextArea > label,
.stCheckbox > label,
[data-testid="stWidgetLabel"] {
    font-size: 0.82rem !important;
}
"""


# ---------------------------------------------------------------------------
# Ana enjeksiyon fonksiyonu
# ---------------------------------------------------------------------------

def apply_theme(big_font: bool = False) -> None:
    """
    Tüm CSS tokenlarını ve bileşenlerini Streamlit sayfasına enjekte eder.
    Her sayfa set_page_config()'den HEMEN SONRA bu fonksiyonu çağırmalı.

    Parametreler
    ------------
    big_font : bool
        True ise erişilebilirlik büyük font modu uygulanır.
    """
    css = "\n".join([
        _font_css(),
        _root_css(),
        _base_css(),
        _typography_css(),
        _input_css(),
        _button_css(),
        _alert_css(),
        _dataframe_css(),
        _big_font_css(big_font),
    ])
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    # Google Fonts link tag — bazı ortamlarda @import çalışmayabilir
    st.markdown(
        f'<link rel="preconnect" href="https://fonts.googleapis.com">'
        f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link href="{_GOOGLE_FONTS_URL}" rel="stylesheet">',
        unsafe_allow_html=True,
    )


import base64
from pathlib import Path

_ASSETS_DIR = Path(__file__).parent.parent / "assets"

def get_logo_wordmark_b64() -> str | None:
    """logo-wordmark.svg dosyasını base64 döndürür."""
    p = _ASSETS_DIR / "logo-wordmark.svg"
    if p.exists():
        try:
            return base64.b64encode(p.read_bytes()).decode("utf-8")
        except Exception:
            return None
    return None

def get_logo_emblem_b64() -> str | None:
    """logo-emblem.svg dosyasını base64 döndürür."""
    p = _ASSETS_DIR / "logo-emblem.svg"
    if p.exists():
        try:
            return base64.b64encode(p.read_bytes()).decode("utf-8")
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# HTML BİLEŞENLER
# ---------------------------------------------------------------------------

def brand_header_html(page_label: str) -> str:
    """
    Her sayfanın en üstünde görüntülenen marka header barı.

    Sol: ECG ikonu + 'MedTriage' wordmark (--color-brand, 600 weight, 20px)
    Sağ: Sayfa etiketi (küçük, ikincil renk, uppercase)
    Stil: --color-surface arka plan, --color-border alt sınır, gölge yok.

    Parametreler
    ------------
    page_label : str
        Sağ köşe sayfa etiketi metni.
    """
    wordmark_b64 = get_logo_wordmark_b64()
    if wordmark_b64:
        logo_html = f'<img src="data:image/svg+xml;base64,{wordmark_b64}" alt="MedTriage" style="height:28px; width:auto; display:block;" />'
    else:
        logo_html = '<span style="font-family:var(--font-sans); font-weight:700; font-size:20px; color:var(--color-brand);">MedTriage</span>'

    return (
        f'<div style="display:flex; align-items:center; justify-content:space-between; background:var(--color-surface); padding:16px 0; margin-bottom:24px; border-bottom:1px solid var(--color-border);">'
        f'<div style="display:flex; align-items:center; gap:12px;">'
        f'{logo_html}'
        f'</div>'
        f'<span style="font-family:var(--font-sans); font-size:11px; font-weight:500; text-transform:uppercase; letter-spacing:0.10em; color:var(--color-ink-secondary);">{page_label}</span>'
        f'</div>'
    )


def disclaimer_bar_html(text: str) -> str:
    """
    Sayfa genişliğinde sabit uyarı şeridi.
    Sol kenarda --color-warning aksanı, sade arka plan.
    """
    return f"""
<div style="
    background: rgba(255,149,0,0.06);
    border-left: 4px solid var(--color-warning);
    border-radius: 0 10px 10px 0;
    padding: 12px 20px;
    font-family: var(--font-sans);
    font-size: 0.82rem;
    font-weight: 400;
    color: #7A4500;
    line-height: 1.55;
    margin-bottom: 28px;
">{text}</div>
"""


def section_label_html(text: str) -> str:
    """
    Form bölüm başlığı — küçük, büyük harf, ikincil renk.
    Apple'ın 'eyebrow label' modeli.
    """
    return f"""
<div style="
    font-family: var(--font-sans);
    font-size: 0.68rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.10em;
    color: var(--color-ink-secondary);
    margin: 28px 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--color-border);
">{text}</div>
"""


def card_html(content: str, padding: str = "28px 32px",
              extra_style: str = "") -> str:
    """
    Gölge tabanlı beyaz kart konteyneri.
    border yok — ayrım yalnızca gölgeyle yapılır.
    hover: gölge büyür (200ms ease transition).
    """
    return f"""
<div class="med-card" style="padding: {padding}; {extra_style}">
    {content}
</div>
"""


def ktas_badge_html(ktas: int, lang: str = "TR",
                    show_time: bool = True) -> str:
    """
    Pill biçimli öncelik rozeti (border-radius: 999px).

    Renk sistemi:
      --color-critical → YALNIZCA KTAS-1
      Diğer seviyeler kendi semantik renkleriyle
      --color-brand → ASLA rozette kullanılmaz

    Parametreler
    ------------
    ktas : int        1–5
    lang : str        'TR' veya 'EN'
    show_time : bool  Bekleme süresi etiketini göster
    """
    cfg   = KTAS_CONFIG.get(ktas, KTAS_CONFIG[3])
    label = cfg["label_tr"] if lang == "TR" else cfg["label_en"]
    sub   = (cfg["sub_tr"] if lang == "TR" else cfg["sub_en"]) if show_time else ""
    return (
        f'<span style="'
        f'display:inline-flex;align-items:center;gap:5px;'
        f'background:{cfg["bg"]};'
        f'color:{cfg["color"]};'
        f'border-radius:var(--radius-badge);'
        f'padding:4px 10px;'
        f'font-family:var(--font-sans);'
        f'font-size:11px;font-weight:600;'
        f'letter-spacing:0.02em;'
        f'white-space:nowrap;'
        f'">'
        f'<span style="font-size:8px;line-height:1">●</span>'
        f'KTAS-{ktas} {label}' +
        (f'<span style="opacity:0.55;font-size:10px"> · {sub}</span>' if sub else "") +
        f'</span>'
    )


def red_flag_alert_html(reasons: list[str], explanation: str = "") -> str:
    """
    Kırmızı bayrak uyarı kutusu — Apple'ın 'destructive alert' stili.

    Tasarım:
      - Sol kenarda 4px --color-critical şerit (sakin, net — parlayan değil)
      - Açık kırmızı arka plan (rgba)
      - Koyu kırmızı metin (WCAG AA kontrast)

    NOT: --color-critical kullanılır, --color-brand ASLA kullanılmaz.
    """
    reasons_html = "".join(
        f'<li style="margin:6px 0;line-height:1.5;font-size:0.82rem;">{r}</li>'
        for r in reasons
    )
    expl_html = (
        f'<div style="margin-top:12px;font-size:0.75rem;color:#A02030;padding-top:10px;border-top:1px solid rgba(255,59,48,0.18);">{explanation}</div>'
        if explanation else ""
    )
    return f"""
<div style="background:rgba(255,59,48,0.06); border-left:4px solid var(--color-critical); border-radius:0 var(--radius-alert) var(--radius-alert) 0; padding:20px 24px; margin:16px 0; font-family:var(--font-sans);">
<div style="font-size:0.88rem; font-weight:600; color:#C41E3A; margin-bottom:10px; display:flex; align-items:center; gap:8px;">
<span style="font-size:18px; line-height:1;">⊗</span> Kırmızı Bayrak — Model Atlandı
</div>
<ul style="margin:0; padding-left:20px; color:#7A1020; list-style:disc;">{reasons_html}</ul>
{expl_html}
</div>
"""


def ai_result_card_html(result: dict, lang: str = "TR") -> str:
    """
    AI tahmin sonucu kartı — temiz, beyaz, hafif gölge.
    """
    ktas  = result["ktas_level"]
    cfg   = KTAS_CONFIG.get(ktas, KTAS_CONFIG[3])
    conf  = int(result["confidence"] * 100)
    expl  = result.get("explanation", "")
    badge = ktas_badge_html(ktas, lang, show_time=True)

    return (
        f'<div style="background:var(--color-surface); border-radius:var(--radius-card); box-shadow:var(--shadow-card); padding:24px 28px; margin:16px 0; border-left:5px solid {cfg["color"]}; transition:box-shadow 200ms ease;">'
        f'<div style="font-family:var(--font-sans); font-size:0.68rem; font-weight:500; text-transform:uppercase; letter-spacing:0.10em; color:var(--color-ink-secondary); margin-bottom:14px;">AI Triaj Önerisi</div>'
        f'<div style="display:flex; align-items:center; gap:14px; margin-bottom:14px; flex-wrap:wrap;">'
        f'{badge}'
        f'<span style="font-family:var(--font-mono); font-size:0.8rem; color:var(--color-ink-secondary); font-variant-numeric:tabular-nums;">Model Güveni: <strong style="color:var(--color-ink);">{conf}%</strong></span>'
        f'</div>'
        f'<div style="font-family:var(--font-sans); font-size:0.85rem; color:var(--color-ink-secondary); line-height:1.65; padding-top:14px; border-top:1px solid var(--color-border);">💡 {expl}</div>'
        f'</div>'
    )


def patient_card_html(
    p: dict,
    is_selected: bool = False,
    is_overdue: bool = False,
    wait_text: str = "",
    lang: str = "TR",
) -> str:
    """
    Kuyruk listesindeki hasta kartı.
    """
    border_color = (
        "var(--color-brand)"   if is_selected else
        "var(--color-warning)" if is_overdue  else
        "var(--color-border)"
    )
    border_width = "3px" if (is_selected or is_overdue) else "1px"
    bg_extra = (
        "background:rgba(122,31,43,0.03);" if is_selected else
        "background:rgba(255,149,0,0.04);" if is_overdue  else ""
    )
    shadow = "var(--shadow-card-hover)" if is_selected else "var(--shadow-card)"

    gender    = p.get("gender", "")
    complaint = str(p.get("chief_complaint", "—"))[:60]
    rf_dot = (
        '<span style="color:var(--color-critical);font-weight:700;margin-right:4px;font-size:14px;" title="Kırmızı Bayrak">⊗</span>'
        if p.get("red_flag") else ""
    )
    badge = ktas_badge_html(p['ai_priority'], lang, show_time=False)
    time_color = 'var(--color-warning)' if is_overdue else 'var(--color-ink-tertiary)'
    time_weight = '600' if is_overdue else '400'

    return (
        f'<div style="background:var(--color-surface); border-radius:14px; border:{border_width} solid {border_color}; box-shadow:{shadow}; padding:16px 20px; margin-bottom:10px; transition:all 200ms ease; {bg_extra}">'
        f'<div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">'
        f'{badge}'
        f'<span style="font-family:var(--font-mono); font-size:0.72rem; color:{time_color}; font-weight:{time_weight}; font-variant-numeric:tabular-nums;">{rf_dot}{wait_text}</span>'
        f'</div>'
        f'<div style="font-family:var(--font-sans); font-size:0.88rem; font-weight:600; color:var(--color-ink); margin-bottom:4px; line-height:1.3;">#{p["id"]} &nbsp;·&nbsp; {p.get("age","—")} yaş &nbsp;·&nbsp; {gender}</div>'
        f'<div style="font-family:var(--font-sans); font-size:0.8rem; color:var(--color-ink-secondary); line-height:1.45;">{complaint}</div>'
        f'</div>'
    )


def vital_chip_html(label: str, value: str, unit: str = "",
                    is_critical: bool = False) -> str:
    """
    Vital bulgu gösterge çipi.
    """
    val_color = "var(--color-critical)" if is_critical else "var(--color-ink)"
    bg_color  = "rgba(255,59,48,0.06)"  if is_critical else "var(--color-canvas)"
    border    = "1px solid rgba(255,59,48,0.20)" if is_critical else "1px solid var(--color-border)"
    unit_str  = f" <span style=\"font-size:0.7rem;font-weight:400;\">{unit}</span>" if unit else ""

    return (
        f'<div style="background:{bg_color}; border:{border}; border-radius:12px; padding:14px 18px; text-align:center; display:inline-flex; flex-direction:column; align-items:center; min-width:105px; flex:1;">'
        f'<div style="font-family:var(--font-sans); font-size:0.65rem; font-weight:600; text-transform:uppercase; letter-spacing:0.08em; color:var(--color-ink-secondary); margin-bottom:4px;">{label}</div>'
        f'<div style="font-family:var(--font-mono); font-size:1.15rem; font-weight:600; color:{val_color}; font-variant-numeric:tabular-nums; line-height:1.2;">{value}{unit_str}</div>'
        f'</div>'
    )

