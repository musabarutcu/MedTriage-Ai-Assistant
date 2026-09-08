"""
shared/footer.py
-----------------
MedTriage — Paylaşımlı kurumsal footer bileşeni.

Her sayfanın sonunda render_footer() çağrılır.
İçerik:
  - Üstte ince --color-brand aksan çizgisi
  - Sol: logo-wordmark.svg + telif hakkı
  - Orta: Gizlilik / Kullanım Şartları linkleri
  - Alt satır: küçük gri yasal disclaimer

NOT: Disclaimer artık üstte turuncu uyarı kutusu DEĞİL —
     burada küçük gri yasal dipnot olarak gösterilir.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).parent.parent / "assets"


def _read_svg_b64(filename: str) -> str | None:
    p = _ASSETS / filename
    if p.exists():
        try:
            return base64.b64encode(p.read_bytes()).decode("utf-8")
        except Exception:
            return None
    return None


def _wordmark_html(height: int = 22) -> str:
    b64 = _read_svg_b64("logo-wordmark.svg")
    if b64:
        return (
            f'<img src="data:image/svg+xml;base64,{b64}" '
            f'height="{height}" style="display:block;opacity:0.8;" '
            f'alt="MedTriage">'
        )
    return (
        '<span style="font-family:var(--font-sans);font-weight:800;'
        'font-size:0.85rem;color:var(--color-ink-secondary);'
        'letter-spacing:-0.01em;">MedTriage</span>'
    )


def render_footer() -> None:
    """
    Kurumsal footer'ı render eder.
    Her sayfanın en sonunda çağrılmalıdır.
    """
    wordmark_html = _wordmark_html(height=20)

    footer_html = f"""
<div style="margin-top: 60px; border-top: 3px solid var(--color-brand); background: var(--color-canvas); padding: 36px 0 28px; font-family: var(--font-sans);">
<div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:20px; margin-bottom:16px;">
<div>
{wordmark_html}
<div style="font-size:0.76rem; color:var(--color-ink-tertiary); margin-top:6px; letter-spacing:0.01em;">© 2026 MedTriage — Tüm hakları saklıdır</div>
</div>
<div style="display:flex; gap:28px; align-items:center; flex-wrap:wrap;">
<span style="color:var(--color-ink-secondary); font-size:0.78rem;">Gizlilik Politikası</span>
<span style="color:var(--color-ink-secondary); font-size:0.78rem;">Kullanım Şartları</span>
<span style="color:var(--color-ink-secondary); font-size:0.78rem;">Destek</span>
<span style="color:var(--color-ink-secondary); font-size:0.78rem;">Hakkında</span>
</div>
</div>
<div style="font-size:0.75rem; color:var(--color-ink-tertiary); line-height:1.65; padding-top:14px; border-top:1px solid var(--color-border); max-width:900px;">
MedTriage bir tıbbi tanı aracı değildir; yalnızca acil servis sağlık personeline karar destek önerisi sunar. Nihai triaj kararı her zaman yetkili sağlık personelinin sorumluluğundadır. Bu sistem bir portfolyo / eğitim prototipidir ve onaylı bir tıbbi cihaz değildir.
<span style="opacity:0.6; margin-left:8px;">KTAS Veri Seti · XGBoost · SHAP · Streamlit</span>
</div>
</div>
"""
    st.markdown(footer_html, unsafe_allow_html=True)

