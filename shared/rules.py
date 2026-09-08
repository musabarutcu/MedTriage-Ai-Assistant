"""
shared/rules.py
---------------
Kırmızı bayrak kural motoru.

Model çağrılmadan ÖNCE çalışır. Hayati tehlike işaretlerini deterministik
eşiklerle yakalar; tetiklenirse model atlanır ve hasta doğrudan yüksek
önceliğe alınır.

Bu motor sistemin güvenlik ağıdır: ML modeli belirsizken bile burası
kesin ve denetlenebilir davranmak zorundadır. Bu yüzden tüm eşikler
tests/test_rules.py ile kilitlenmiştir.

TASARIM NOTLARI
---------------
1. YAŞA GÖRE EŞİK — Erişkin eşikleri çocukta yanlıştır: 1 yaşındaki bir
   bebekte nabız 150 normaldir, erişkinde ciddi taşikardidir. Yaş verilmezse
   erişkin bandına düşülür (en yaygın acil servis hastası).

2. ŞİDDET DERECELENDİRMESİ — Her kural kendi KTAS seviyesini önerir.
   Apne (KTAS-1) ile hipertansif kriz (KTAS-2) aynı şey değildir.
   Birden fazla kural tetiklenirse en kritik olan (en küçük sayı) kazanır.

3. EŞİKLER ALARM SEVİYESİDİR, "NORMAL DIŞI" DEĞİL — Amaç her anormal değeri
   işaretlemek değil, hayati tehlikeyi yakalamak. Aksi halde alarm yorgunluğu
   oluşur ve motor işlevsizleşir.

⚠️ UYARI: Bu sistem bir karar destek aracıdır. Kesin tanı için sağlık
   personelinin değerlendirmesi şarttır.
"""

from __future__ import annotations

import logging

from shared.symptoms import (
    normalize as _normalize_symptom,
    matches_code,
    suggested_ktas_for,
)

logger = logging.getLogger(__name__)

__all__ = ["check_red_flags", "format_red_flag_message", "age_band", "AGE_BANDS"]


# ---------------------------------------------------------------------------
# Yaş bantları ve eşikler
#
# Kaynak niteliğinde referans aralıklar (PALS / APLS pediatrik vital değerleri
# ve erişkin acil triaj eşikleri) temel alınmıştır. Değerler kasıtlı olarak
# alarm ucundadır — bkz. tasarım notu 3.
# ---------------------------------------------------------------------------
AGE_BANDS: dict[str, dict] = {
    # bant adı -> üst yaş sınırı (KAPSAM DIŞI) ve alarm eşikleri
    "infant": {
        "age_below": 1,      # 0 - <1 yaş
        "hr_low":    90,   "hr_high":  180,
        "rr_low":    20,   "rr_high":   70,
        "sbp_low":   70,   "sbp_high": 180,
        "temp_low":  36.0, "temp_high": 41.0,
        "label_tr":  "bebek (<1 yaş)",
    },
    "toddler": {
        "age_below": 6,      # 1 - <6 yaş
        "hr_low":    70,   "hr_high":  160,
        "rr_low":    15,   "rr_high":   50,
        "sbp_low":   75,   "sbp_high": 190,
        "temp_low":  35.0, "temp_high": 41.0,
        "label_tr":  "küçük çocuk (1-5 yaş)",
    },
    "child": {
        "age_below": 13,     # 6 - <13 yaş
        "hr_low":    50,   "hr_high":  140,
        "rr_low":    12,   "rr_high":   40,
        "sbp_low":   85,   "sbp_high": 195,
        "temp_low":  35.0, "temp_high": 41.0,
        "label_tr":  "çocuk (6-12 yaş)",
    },
    "adult": {  # 13+ ve yaş bilinmiyorsa varsayılan
        "age_below": float("inf"),
        "hr_low":    40,   "hr_high":  150,
        "rr_low":     8,   "rr_high":   30,
        "sbp_low":   90,   "sbp_high": 200,
        "temp_low":  35.0, "temp_high": 41.0,
        "label_tr":  "erişkin",
    },
}

_BAND_ORDER = ["infant", "toddler", "child", "adult"]

# SpO2 yaştan bağımsızdır
_SPO2_CRITICAL = 90.0   # < 90  -> kırmızı bayrak
_SPO2_SEVERE   = 85.0   # < 85  -> KTAS-1

# Bilinç (AVPU) — form 1..4 arası int gönderir
_AVPU_ALERT        = 1   # Alert
_AVPU_VERBAL       = 2   # Sesli uyarıya yanıt
_AVPU_PAIN         = 3   # Ağrılı uyarıya yanıt
_AVPU_UNRESPONSIVE = 4   # Yanıtsız

_AVPU_LABEL = {
    _AVPU_ALERT:        "Alert (uyanık)",
    _AVPU_VERBAL:       "Verbal (sesli uyarıya yanıt)",
    _AVPU_PAIN:         "Pain (yalnızca ağrılı uyarıya yanıt)",
    _AVPU_UNRESPONSIVE: "Unresponsive (yanıtsız)",
}

# Metinsel mental durum ifadeleri (geriye uyumluluk — eski kayıtlar ve
# serbest metin girişleri hâlâ bu formatta gelebilir)
_ALTERED_MENTAL_TEXT = [
    "confused", "unconscious", "lethargic", "stupor", "coma", "obtunded",
    "konfüze", "konfuze", "letarjik", "bilinçsiz", "bilincsiz",
    "bilincini yitirdi", "yanıtsız", "yanitsiz", "cevapsız", "cevapsiz",
]


def age_band(age) -> str:
    """
    Yaşa karşılık gelen bant adını döndürür.
    Yaş yoksa veya çözümlenemezse 'adult' (en güvenli varsayılan) döner.
    """
    if age is None:
        return "adult"
    try:
        a = float(age)
    except (TypeError, ValueError):
        return "adult"
    if a < 0:
        return "adult"
    for name in _BAND_ORDER:
        if a < AGE_BANDS[name]["age_below"]:
            return name
    return "adult"


def _num(value):
    """Sayıya çevirir; çevrilemezse None döner (kural sessizce atlanır)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


# ---------------------------------------------------------------------------
# Kurallar
#
# Her kural (reason: str, suggested_ktas: int) veya None döndürür.
# ---------------------------------------------------------------------------

def _rule_spo2(vitals: dict, th: dict) -> tuple[str, int] | None:
    """SpO2 < 90 kritik hipoksi; < 85 resüsitasyon düzeyi."""
    spo2 = _num(vitals.get("spo2"))
    if spo2 is None or spo2 >= _SPO2_CRITICAL:
        return None
    if spo2 < _SPO2_SEVERE:
        return (f"Ağır hipoksi: SpO2 %{spo2:.0f} (<{_SPO2_SEVERE:.0f})", 1)
    return (f"Kritik oksijen satürasyonu: SpO2 %{spo2:.0f} (<{_SPO2_CRITICAL:.0f})", 2)


def _rule_blood_pressure(vitals: dict, th: dict) -> tuple[str, int] | None:
    """Sistolik basınç: bant altı -> şok (KTAS-1); bant üstü -> hipertansif kriz (KTAS-2)."""
    sbp = _num(vitals.get("sbp"))
    if sbp is None:
        return None
    if sbp < th["sbp_low"]:
        return (f"Hipotansiyon / şok şüphesi: SKB={sbp:.0f} mmHg "
                f"(<{th['sbp_low']}, {th['label_tr']})", 1)
    if sbp > th["sbp_high"]:
        return (f"Hipertansif kriz: SKB={sbp:.0f} mmHg "
                f"(>{th['sbp_high']}, {th['label_tr']})", 2)
    return None


def _rule_heart_rate(vitals: dict, th: dict) -> tuple[str, int] | None:
    """Nabız: bant altı ciddi bradikardi (KTAS-1); bant üstü ciddi taşikardi (KTAS-2)."""
    hr = _num(vitals.get("heart_rate"))
    if hr is None:
        return None
    if hr < th["hr_low"]:
        return (f"Ciddi bradikardi: Nabız={hr:.0f}/dk "
                f"(<{th['hr_low']}, {th['label_tr']})", 1)
    if hr > th["hr_high"]:
        return (f"Ciddi taşikardi: Nabız={hr:.0f}/dk "
                f"(>{th['hr_high']}, {th['label_tr']})", 2)
    return None


def _rule_respiratory_rate(vitals: dict, th: dict) -> tuple[str, int] | None:
    """
    Solunum hızı: bant altı hipoventilasyon/apne eşiği (KTAS-1);
    bant üstü ciddi takipne (KTAS-2).

    Bu kural önceki sürümde HİÇ YOKTU — solunum 4/dk olan hasta
    kırmızı bayraksız geçiyordu.
    """
    rr = _num(vitals.get("resp_rate"))
    if rr is None:
        return None
    if rr < th["rr_low"]:
        return (f"Hipoventilasyon / apne riski: Solunum={rr:.0f}/dk "
                f"(<{th['rr_low']}, {th['label_tr']})", 1)
    if rr > th["rr_high"]:
        return (f"Ciddi takipne: Solunum={rr:.0f}/dk "
                f"(>{th['rr_high']}, {th['label_tr']})", 2)
    return None


def _rule_temperature(vitals: dict, th: dict) -> tuple[str, int] | None:
    """
    Ateş: > 41 hipertermi (KTAS-1); < bant alt sınırı hipotermi.
    32°C altı ağır hipotermi -> KTAS-1.

    Bu kural da önceki sürümde yoktu.
    """
    temp = _num(vitals.get("temperature"))
    if temp is None:
        return None
    if temp > th["temp_high"]:
        return (f"Hipertermi: Ateş={temp:.1f}°C (>{th['temp_high']:.0f})", 1)
    if temp < 32.0:
        return (f"Ağır hipotermi: Ateş={temp:.1f}°C (<32)", 1)
    if temp < th["temp_low"]:
        return (f"Hipotermi: Ateş={temp:.1f}°C "
                f"(<{th['temp_low']:.0f}, {th['label_tr']})", 2)
    return None


def _rule_consciousness(vitals: dict, th: dict) -> tuple[str, int] | None:
    """
    Bilinç düzeyi — GCS, AVPU (int) veya metinsel ifade üzerinden.

    ÖNCEKİ SÜRÜMDEKİ KRİTİK HATA: Form AVPU'yu int (1-4) gönderiyor,
    kural ise yalnızca metin arıyordu. Bu yüzden YANITSIZ hasta
    kırmızı bayrak almıyordu. Artık her iki tip de kabul ediliyor.
    """
    gcs = _num(vitals.get("gcs"))
    if gcs is not None:
        if gcs <= 8:
            return (f"Ağır bilinç baskılanması: GCS={gcs:.0f} (≤8, entübasyon eşiği)", 1)
        if gcs <= 12:
            return (f"Bilinç baskılanması: GCS={gcs:.0f} (≤12)", 2)

    raw = vitals.get("mental_status")

    # AVPU sayısal kod
    avpu = _num(raw)
    if avpu is not None and _AVPU_ALERT <= avpu <= _AVPU_UNRESPONSIVE:
        code = int(avpu)
        if code >= _AVPU_PAIN:
            return (f"Değişmiş bilinç düzeyi: AVPU-{code} — {_AVPU_LABEL[code]}", 1)
        if code == _AVPU_VERBAL:
            return (f"Değişmiş bilinç düzeyi: AVPU-{code} — {_AVPU_LABEL[code]}", 2)
        return None  # AVPU-1 Alert: normal

    # Metinsel ifade (geriye uyumluluk)
    if raw is not None:
        text = str(raw).lower()
        for phrase in _ALTERED_MENTAL_TEXT:
            if phrase in text:
                return (f"Değişmiş mental durum: '{raw}'", 1)

    return None


_VITAL_RULES = (
    _rule_consciousness,
    _rule_spo2,
    _rule_respiratory_rate,
    _rule_blood_pressure,
    _rule_heart_rate,
    _rule_temperature,
)


# ---------------------------------------------------------------------------
# Semptom tabanlı kurallar
# ---------------------------------------------------------------------------

def _symptom_rules(symptom_code: str, symptoms_text: str) -> list[tuple[str, int]]:
    """
    Kanonik semptom koduna ve serbest metne dayalı kurallar.

    Eşleşme artık kırılgan "kelime metinde geçiyor mu" kontrolü yerine
    shared.symptoms taksonomisi üzerinden yapılır; böylece form (Türkçe)
    ve veri seti (İngilizce) aynı kod uzayında buluşur.
    """
    out: list[tuple[str, int]] = []

    from shared.symptoms import label as _label

    # 1) Semptom tek başına yüksek aciliyet ima ediyor mu?
    ktas = suggested_ktas_for(symptom_code)
    if ktas is not None:
        out.append((f"Yüksek aciliyetli şikayet: {_label(symptom_code, 'TR')}", ktas))

    # 2) Göğüs ağrısı + nefes darlığı birlikteliği (AKS / PE şüphesi).
    #    Tek tek her biri zaten KTAS-2; birlikteliği açıkça belgelenir.
    text = symptoms_text or ""
    has_chest = symptom_code == "chest_pain" or matches_code("chest_pain", text)
    has_dyspnea = symptom_code == "dyspnea" or matches_code("dyspnea", text)
    if has_chest and has_dyspnea:
        out.append(("Göğüs ağrısı + nefes darlığı birlikteliği (AKS/PE şüphesi)", 2))

    return out


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def check_red_flags(
    vitals: dict,
    symptoms: str = "",
    symptom_code: str | None = None,
) -> dict:
    """
    Vital bulgular ve semptomlara göre kırmızı bayrak kontrolü yapar.

    ML modeli çağrılmadan ÖNCE çalıştırılmalıdır. Herhangi bir kural
    tetiklenirse model atlanır ve hasta `suggested_ktas` seviyesine alınır.

    Parametreler
    ------------
    vitals : dict
        Vital bulgular. Tanınan anahtarlar (hepsi opsiyonel):
        spo2, sbp, dbp, heart_rate, resp_rate, temperature, gcs,
        mental_status (AVPU 1-4 int ya da metin), age.
        `age` verilirse eşikler yaş bandına göre seçilir.
    symptoms : str
        Başvuru şikayeti serbest metni (Türkçe veya İngilizce).
    symptom_code : str | None
        shared.symptoms kanonik kodu. Verilmezse `symptoms` metninden türetilir.

    Döndürür
    --------
    dict
        {
            "red_flag":       bool,       # herhangi bir kural tetiklendi mi
            "reason":         str,        # en kritik kuralın açıklaması
            "all_reasons":    list[str],  # tetiklenen tüm kurallar
            "suggested_ktas": int | None, # önerilen KTAS (1 veya 2); yoksa None
            "triggered":      list[dict], # [{"reason": ..., "ktas": ...}, ...]
            "age_band":       str,        # kullanılan eşik bandı
        }

    Örnek
    -----
    >>> r = check_red_flags({"mental_status": 4}, "")
    >>> r["red_flag"], r["suggested_ktas"]
    (True, 1)
    >>> check_red_flags({"spo2": 97, "sbp": 120, "heart_rate": 80})["red_flag"]
    False
    """
    band_name = age_band(vitals.get("age"))
    th = AGE_BANDS[band_name]

    triggered: list[dict] = []
    seen: set[str] = set()

    def _add(reason: str, ktas: int) -> None:
        if reason in seen:
            return
        seen.add(reason)
        triggered.append({"reason": reason, "ktas": int(ktas)})
        logger.warning("Kırmızı bayrak tetiklendi [KTAS-%s]: %s", ktas, reason)

    # Vital tabanlı kurallar
    for rule_fn in _VITAL_RULES:
        result = rule_fn(vitals, th)
        if result:
            _add(*result)

    # Semptom tabanlı kurallar
    code = symptom_code or _normalize_symptom(symptoms)
    for reason, ktas in _symptom_rules(code, symptoms):
        _add(reason, ktas)

    if not triggered:
        return {
            "red_flag": False,
            "reason": "",
            "all_reasons": [],
            "suggested_ktas": None,
            "triggered": [],
            "age_band": band_name,
        }

    # En kritik olan (en küçük KTAS) öne alınır; eşitlikte tetiklenme sırası korunur
    triggered.sort(key=lambda t: t["ktas"])
    return {
        "red_flag": True,
        "reason": triggered[0]["reason"],
        "all_reasons": [t["reason"] for t in triggered],
        "suggested_ktas": triggered[0]["ktas"],
        "triggered": triggered,
        "age_band": band_name,
    }


def format_red_flag_message(flag_result: dict) -> str:
    """
    check_red_flags() çıktısını arayüzde gösterilecek Türkçe uyarı metnine
    dönüştürür.
    """
    if not flag_result.get("red_flag"):
        return ""

    reasons = flag_result.get("all_reasons") or [flag_result.get("reason", "")]
    ktas = flag_result.get("suggested_ktas")

    lines = ["🚨 KIRMIZI BAYRAK — Acil Değerlendirme Gerekli"]
    if ktas:
        lines.append(f"Önerilen öncelik: KTAS-{ktas}")
    lines.append("─" * 45)
    lines.extend(f"• {r}" for r in reasons)
    lines.append("─" * 45)
    lines.append("ℹ️  Model atlandı. Lütfen hastayı derhal değerlendirin.")
    return "\n".join(lines)
