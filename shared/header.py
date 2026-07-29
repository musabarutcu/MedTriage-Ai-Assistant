"""
shared/header.py
-----------------
MedTriage — Paylaşımlı navigasyon header bileşeni.

Her sayfanın başında render_header(current_page) çağrılır.
Logo: assets/logo-full.svg (inline SVG / base64 img olarak gömülür).
Panel geçişi: st.switch_page() ile gerçekleşir.

Kullanım:
    from shared.header import render_header
    render_header("triaj")   # veya "doktor"
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

_ASSETS = Path(__file__).parent.parent / "assets"

# ---------------------------------------------------------------------------
# Yardımcı — logo okuma
# ---------------------------------------------------------------------------

def _read_svg_b64(filename: str) -> str | None:
    """
    SVG dosyasını base64 olarak döndürür.
    Dosya bulunamazsa None döner (fallback devreye girer).
    """
    p = _ASSETS / filename
    if p.exists():
        try:
            content = p.read_bytes()
            return base64.b64encode(content).decode("utf-8")
        except Exception:
            return None
    return None


def _logo_img_html(filename: str, height: int) -> str:
    """
    SVG dosyasını <img> etiketi olarak döndürür.
    Bulunamazsa metin fallback kullanır.
    """
    b64 = _read_svg_b64(filename)
    if b64:
        return (
            f'<img src="data:image/svg+xml;base64,{b64}" '
            f'height="{height}" '
            f'style="display:block;vertical-align:middle;" '
            f'alt="MedTriage Logo">'
        )
    # Metin fallback — logo dosyası henüz eklenmemişse
    return (
        '<span style="'
        'font-family:var(--font-sans);font-weight:800;font-size:1.15rem;'
        'color:var(--color-brand);letter-spacing:-0.02em;'
        '">Med<span style="color:#1B2535">Triage</span></span>'
    )


# ---------------------------------------------------------------------------
# Header render
# ---------------------------------------------------------------------------

_PAGE_META: dict[str, tuple[str, str, str]] = {
    # key → (panel label, nav button text, target page path)
    "triaj": (
        "Triaj Kayıt",
        "Doktor Paneline Geç →",
        "pages/2_Doktor_Paneli.py",
    ),
    "doktor": (
        "Doktor Paneli",
        "← Triaj Paneline Geç",
        "pages/1_Triaj_Kayit.py",
    ),
}


def render_header(current_page: str) -> None:
    """
    Paylaşımlı navigasyon header'ını render eder.

    Parametreler
    ------------
    current_page : str
        "triaj" veya "doktor" — aktif paneli belirler.
        Buna göre nav butonu ve panel etiketi otomatik ayarlanır.
    """
    page_label, btn_text, btn_target = _PAGE_META.get(
        current_page, ("", "", "")
    )
    logo_html = _logo_img_html("logo-wordmark.svg", height=28)

    # ── Layout: Logo | Label (orta-sağ) | Nav Butonu ─────────────────────
    logo_col, label_col, btn_col = st.columns([4, 2.5, 2])

    with logo_col:
        st.markdown(
            f'<div style="display:flex;align-items:center;padding:10px 0 12px;">'
            f'{logo_html}</div>',
            unsafe_allow_html=True,
        )

    with label_col:
        st.markdown(
            f"""
<div style="
    display:flex;align-items:center;justify-content:flex-end;
    height:56px;
">
    <div style="
        font-family:var(--font-sans);
        font-size:0.7rem;font-weight:600;
        text-transform:uppercase;letter-spacing:0.1em;
        color:var(--color-brand);
        padding-bottom:3px;
        border-bottom:2px solid var(--color-brand);
        white-space:nowrap;
    ">{page_label}</div>
</div>
""",
            unsafe_allow_html=True,
        )

    with btn_col:
        st.markdown(
            '<div style="display:flex;align-items:center;justify-content:flex-end;height:56px;">',
            unsafe_allow_html=True,
        )
        if btn_target:
            if st.button(
                btn_text,
                key=f"nav_btn_{current_page}",
                use_container_width=True,
                type="secondary",
            ):
                st.switch_page(btn_target)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Alt ayırıcı çizgi ────────────────────────────────────────────────
    st.markdown(
        '<div style="height:1px;background:var(--color-border);margin-bottom:20px;"></div>',
        unsafe_allow_html=True,
    )
