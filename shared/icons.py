"""
shared/icons.py
---------------
Inline SVG ikon seti.

NEDEN EMOJİ DEĞİL?
------------------
Emoji (✅ ⚖️ 💗 ⊗ ●) yapısal ikon olarak kullanılamaz:

  1. Platforma göre farklı çizilir — Windows, macOS, Android'de aynı
     emoji tamamen başka görünür. Klinik bir arayüzde "kırmızı bayrak"
     işaretinin cihaza göre değişmesi kabul edilemez.
  2. Renk ve boyut kontrol edilemez; tasarım token'larına bağlanamaz.
     KTAS göstergesi bu yüzden 8px'lik bir "●" karakteri olarak
     kalmıştı — en kritik bilgi, en küçük öğe.
  3. Ekran okuyucular emojiyi ("beyaz ağır onay işareti") okur; bu
     bilgi taşımaz, gürültü üretir.

Buradaki ikonlar Lucide ikon setinin geometrisine dayanır (ISC lisans),
inline SVG olarak gömülüdür: dış bağımlılık yok, çevrimdışı çalışır,
`currentColor` üzerinden tasarım token'larını miras alır.

Kullanım
--------
    from shared.icons import icon

    icon("check", size=18, color="var(--color-safe-text)")
    icon("alert-triangle", size=16)                    # rengi miras alır
    icon("stethoscope", size=20, title="Muayene")      # erişilebilir ad

Erişilebilirlik
---------------
Varsayılan `aria-hidden="true"` — ikon yanında görünür metin varsa
doğru davranış budur (WCAG: dekoratif ikonlar erişilebilirlik ağacından
gizlenir). Tek başına anlam taşıyan ikonlarda `title=` verin; fonksiyon
o zaman `role="img"` ve `<title>` ekler.
"""

from __future__ import annotations

from html import escape

__all__ = ["icon", "ICON_PATHS", "ktas_dot"]

# Lucide geometrisi — 24x24 viewBox, stroke tabanlı, tutarlı 2px kalınlık
ICON_PATHS: dict[str, str] = {
    # ── Durum / geri bildirim ────────────────────────────────────────
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "check-circle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "alert-triangle": (
        '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z"/>'
        '<path d="M12 9v4"/><path d="M12 17h.01"/>'
    ),
    "alert-octagon": (
        '<path d="M7.86 2h8.28L22 7.86v8.28L16.14 22H7.86L2 16.14V7.86Z"/>'
        '<path d="M12 8v4"/><path d="M12 16h.01"/>'
    ),
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',

    # ── Klinik ───────────────────────────────────────────────────────
    "activity": '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
    "heart-pulse": (
        '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>'
        '<path d="M3.22 13H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"/>'
    ),
    "stethoscope": (
        '<path d="M11 2v2"/><path d="M5 2v2"/>'
        '<path d="M5 4v5a5 5 0 0 0 10 0V4"/>'
        '<path d="M10 14v3a4 4 0 0 0 8 0v-1"/>'
        '<circle cx="20" cy="10" r="2"/>'
    ),
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "message-square": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',

    # ── Eylem ────────────────────────────────────────────────────────
    "edit": (
        '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>'
        '<path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4Z"/>'
    ),
    "save": (
        '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
        '<path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>'
    ),
    "refresh": (
        '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>'
        '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>'
    ),
    "scale": (
        '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>'
        '<path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>'
        '<path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>'
    ),
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "arrow-left": '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',

    # ── Veri / gösterge ──────────────────────────────────────────────
    "trending-up": '<path d="M16 7h6v6"/><path d="m22 7-8.5 8.5-5-5L2 17"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "type": '<path d="M12 4v16"/><path d="M4 7V5h16v2"/><path d="M9 20h6"/>',
    "inbox": (
        '<path d="M22 12h-6l-2 3h-4l-2-3H2"/>'
        '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'
    ),
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
}

# Anlam taşıyan ikonların varsayılan erişilebilir adları
_DEFAULT_TITLES = {
    "alert-octagon": "Kırmızı bayrak",
    "alert-triangle": "Uyarı",
    "check-circle": "Onaylandı",
}


def icon(
    name: str,
    size: int = 16,
    color: str = "currentColor",
    title: str | None = None,
    stroke_width: float = 2,
    css_class: str = "",
) -> str:
    """
    Inline SVG ikon döndürür.

    Parametreler
    ------------
    name : str
        ICON_PATHS anahtarı. Bilinmeyen ad boş string döndürür — arayüz
        kırılmaz, yalnızca ikon çizilmez.
    size : int
        Piksel cinsinden kenar uzunluğu.
    color : str
        Herhangi bir CSS rengi; varsayılan `currentColor` üst öğeden miras alır.
    title : str | None
        Verilirse ikon anlam taşıyor kabul edilir: role="img" + <title>.
        Verilmezse dekoratif kabul edilir: aria-hidden="true".
    stroke_width : float
        Çizgi kalınlığı. Aynı görsel katmanda tutarlı tutun.
    css_class : str
        Ek CSS sınıfı.
    """
    path = ICON_PATHS.get(name)
    if path is None:
        return ""

    if title is None:
        title = _DEFAULT_TITLES.get(name)

    if title:
        a11y = f'role="img" aria-label="{escape(title)}"'
        title_el = f"<title>{escape(title)}</title>"
    else:
        a11y = 'aria-hidden="true" focusable="false"'
        title_el = ""

    cls = f' class="{escape(css_class)}"' if css_class else ""

    return (
        f'<svg{cls} xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round" {a11y} '
        f'style="display:inline-block;vertical-align:middle;flex-shrink:0;">'
        f"{title_el}{path}</svg>"
    )


def ktas_dot(color: str, size: int = 10, title: str | None = None) -> str:
    """
    KTAS seviye göstergesi — dolu daire.

    Eskiden 8px'lik bir "●" metin karakteriydi: font'a bağımlı, ölçeklenemez
    ve en kritik bilgi olmasına rağmen arayüzdeki en küçük öğe. Artık
    boyutu ve rengi token'lardan gelen bir SVG.
    """
    a11y = (f'role="img" aria-label="{escape(title)}"' if title
            else 'aria-hidden="true" focusable="false"')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 10 10" {a11y} '
        f'style="display:inline-block;vertical-align:middle;flex-shrink:0;">'
        f'{f"<title>{escape(title)}</title>" if title else ""}'
        f'<circle cx="5" cy="5" r="5" fill="{color}"/></svg>'
    )
