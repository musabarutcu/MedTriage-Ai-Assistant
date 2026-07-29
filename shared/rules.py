"""
shared/rules.py
---------------
Kırmızı bayrak kural motoru.

Model çağrılmadan önce, vital bulgulara ve semptomlara dayalı olarak
hayati tehlike işaretlerini tespit eder. Bu kurallar klinik kanıta dayalı
eşik değerler kullanır.

⚠️ UYARI: Bu sistem bir karar destek aracıdır. Kesin tanı için sağlık
   personelinin değerlendirmesi şarttır.
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Semptom anahtar kelimeleri (Türkçe ve İngilizce karşılıklar)
# ---------------------------------------------------------------------------
_CHEST_PAIN_KEYWORDS = [
    "göğüs ağrısı", "gogus agrisi", "chest pain", "angina",
    "göğüste baskı", "sternum", "gögüs ağrısı",
]

_DYSPNEA_KEYWORDS = [
    "nefes darlığı", "nefes darliği", "nefes darl", "dyspnea",
    "shortness of breath", "solunum sıkıntısı", "nefes alamıyorum",
    "nefes güçlüğü", "dispne",
]

_CONSCIOUSNESS_KEYWORDS = [
    "bilinç kaybı", "bilincini yitirdi", "bayıldı", "baygınlık",
    "unconscious", "syncope", "senkop", "altered consciousness",
    "konfüzyon", "konfuzyon", "ajitasyon", "deliryum", "letarji",
    "glasgow", "gcs",  # GCS değeri düşükse zaten vital kontrolde yakalanır
    "cevapsız", "yanıtsız",
]


def _text_contains(text: str, keywords: list[str]) -> bool:
    """
    Metinde anahtar kelimelerden herhangi birinin geçip geçmediğini kontrol eder.
    Büyük/küçük harf ve Türkçe karakter farkına duyarsızdır.
    """
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


# ---------------------------------------------------------------------------
# Kural tanımları
# ---------------------------------------------------------------------------

def _rule_spo2_critical(vitals: dict) -> str | None:
    """
    SpO2 < 90 → Kritik hipoksi.
    Normal SpO2: 95-100. 90 altı solunumsal acil kabul edilir.
    """
    spo2 = vitals.get("spo2")
    if spo2 is not None:
        try:
            if float(spo2) < 90:
                return f"Kritik oksijen satürasyonu: SpO2 %{spo2} (<90)"
        except (TypeError, ValueError):
            pass
    return None


def _rule_chest_pain_dyspnea(vitals: dict, symptoms: str) -> str | None:
    """
    Göğüs ağrısı + nefes darlığı birlikteliği → Akut koroner sendrom / PE şüphesi.
    İki semptomun birlikte bulunması riski katlar.
    """
    has_chest_pain = _text_contains(symptoms, _CHEST_PAIN_KEYWORDS)
    has_dyspnea = _text_contains(symptoms, _DYSPNEA_KEYWORDS)
    if has_chest_pain and has_dyspnea:
        return "Göğüs ağrısı + nefes darlığı birlikteliği (AKS/PE şüphesi)"
    return None


def _rule_altered_consciousness(vitals: dict, symptoms: str) -> str | None:
    """
    Bilinç kaybı / düşük bilinç → Nörolojik veya sistemik acil.
    GCS ≤ 8 entübasyon eşiği, GCS ≤ 12 ciddi bozukluk.
    """
    # GCS değeri üzerinden kontrol
    gcs = vitals.get("gcs")
    if gcs is not None:
        try:
            if float(gcs) <= 12:
                return f"Düşük Glasgow Koma Skoru: GCS={gcs} (≤12)"
        except (TypeError, ValueError):
            pass

    # Mental status üzerinden kontrol
    mental = str(vitals.get("mental_status", "")).lower()
    altered_statuses = ["confused", "unconscious", "lethargic", "stupor",
                        "coma", "konfüze", "konfuze", "letarjik", "stupor",
                        "bilinçsiz", "bilincini yitirdi"]
    if any(s in mental for s in altered_statuses):
        return f"Değişmiş mental durum: '{vitals.get('mental_status')}'"

    # Semptom metni üzerinden kontrol
    if _text_contains(symptoms, _CONSCIOUSNESS_KEYWORDS):
        return "Semptomlar bilinç kaybı / değişmiş bilinç içeriyor"

    return None


def _rule_blood_pressure_critical(vitals: dict) -> str | None:
    """
    Sistolik kan basıncı < 90 → Şok; > 200 → Hipertansif kriz.
    Her ikisi de acil müdahale gerektirir.
    """
    sbp = vitals.get("sbp")
    if sbp is not None:
        try:
            sbp_val = float(sbp)
            if sbp_val < 90:
                return f"Hipotansiyon / Şok şüphesi: SKB={sbp_val} mmHg (<90)"
            if sbp_val > 200:
                return f"Hipertansif kriz: SKB={sbp_val} mmHg (>200)"
        except (TypeError, ValueError):
            pass
    return None


def _rule_heart_rate_critical(vitals: dict) -> str | None:
    """
    Nabız < 40 → Ciddi bradikardi (kalp bloğu şüphesi);
    Nabız > 150 → Ciddi taşikardi (SVT / VF öncesi şüphesi).
    """
    hr = vitals.get("heart_rate")
    if hr is not None:
        try:
            hr_val = float(hr)
            if hr_val < 40:
                return f"Ciddi bradikardi: Nabız={hr_val} atım/dk (<40)"
            if hr_val > 150:
                return f"Ciddi taşikardi: Nabız={hr_val} atım/dk (>150)"
        except (TypeError, ValueError):
            pass
    return None


# Tüm kural fonksiyonlarının listesi (genişletilebilir mimari)
_VITAL_RULES = [
    _rule_spo2_critical,
    _rule_blood_pressure_critical,
    _rule_heart_rate_critical,
    _rule_altered_consciousness,
]

_SYMPTOM_RULES = [
    _rule_chest_pain_dyspnea,
    _rule_altered_consciousness,
]


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def check_red_flags(vitals: dict, symptoms: str = "") -> dict:
    """
    Vital bulgular ve semptomlara göre kırmızı bayrak (red flag) kontrolü yapar.

    Bu fonksiyon, ML modeli çağrılmadan ÖNCE çalıştırılmalıdır.
    Herhangi bir kural tetiklenirse model atlanarak hasta en yüksek önceliğe
    (KTAS-1 eşdeğeri) alınmalıdır.

    Parametreler
    ------------
    vitals : dict
        Vital bulgular sözlüğü. Beklenen anahtarlar (hepsi opsiyonel):
        spo2, sbp, dbp, heart_rate, resp_rate, temperature, gcs, mental_status
    symptoms : str
        Başvuru şikayeti veya semptom metni (Türkçe veya İngilizce).

    Döndürür
    --------
    dict
        {
            "red_flag": bool,        # Herhangi bir kural tetiklenirse True
            "reason": str,           # Tetiklenen ilk kural açıklaması
            "all_reasons": list[str] # Tüm tetiklenen kuralların listesi
        }

    Örnek
    -----
    >>> result = check_red_flags({"spo2": 85, "heart_rate": 110}, "göğüs ağrısı")
    >>> result["red_flag"]
    True
    >>> result["reason"]
    'Kritik oksijen satürasyonu: SpO2 %85 (<90)'
    """
    triggered_reasons: list[str] = []

    # Vital tabanlı kurallar (semptomsuz)
    vital_rule_fns = [
        _rule_spo2_critical,
        _rule_blood_pressure_critical,
        _rule_heart_rate_critical,
    ]
    for rule_fn in vital_rule_fns:
        result = rule_fn(vitals)
        if result:
            triggered_reasons.append(result)
            logger.warning(f"Kırmızı bayrak tetiklendi: {result}")

    # Vital + semptom tabanlı kurallar
    symptom_rule_fns = [
        _rule_chest_pain_dyspnea,
        _rule_altered_consciousness,
    ]
    for rule_fn in symptom_rule_fns:
        result = rule_fn(vitals, symptoms)
        if result:
            # Bilinç kuralı hem vital hem semptomdan tetiklenebilir; tekrarı önle
            if result not in triggered_reasons:
                triggered_reasons.append(result)
                logger.warning(f"Kırmızı bayrak tetiklendi: {result}")

    if triggered_reasons:
        return {
            "red_flag": True,
            "reason": triggered_reasons[0],          # En kritik (ilk tetiklenen)
            "all_reasons": triggered_reasons,
        }

    return {
        "red_flag": False,
        "reason": "",
        "all_reasons": [],
    }


def format_red_flag_message(flag_result: dict) -> str:
    """
    check_red_flags() çıktısını kullanıcı arayüzünde gösterilecek
    Türkçe bir uyarı metnine dönüştürür.

    Parametreler
    ------------
    flag_result : dict
        check_red_flags() tarafından döndürülen sözlük.

    Döndürür
    --------
    str
        Arayüzde gösterilecek uyarı metni.
    """
    if not flag_result.get("red_flag"):
        return ""

    reasons = flag_result.get("all_reasons", [flag_result.get("reason", "")])
    lines = ["🚨 KIRMIZI BAYRAK — Acil Değerlendirme Gerekli"]
    lines.append("─" * 45)
    for r in reasons:
        lines.append(f"• {r}")
    lines.append("─" * 45)
    lines.append("ℹ️  Model atlandı. Lütfen hastayı derhal değerlendirin.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bağımsız test bloğu
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format="%(levelname)s | %(message)s")

    test_cases = [
        # (vitals, symptoms, beklenen_red_flag)
        ({"spo2": 85, "sbp": 120, "heart_rate": 90}, "", True),
        ({"spo2": 97, "sbp": 85, "heart_rate": 110}, "baş ağrısı", True),
        ({"spo2": 97, "sbp": 120, "heart_rate": 160}, "", True),
        ({"spo2": 97, "sbp": 120, "heart_rate": 90, "gcs": 10}, "", True),
        ({"spo2": 98, "sbp": 120, "heart_rate": 80}, "göğüs ağrısı ve nefes darlığı", True),
        ({"spo2": 98, "sbp": 120, "heart_rate": 80}, "baş ağrısı", False),
        ({"spo2": 97, "sbp": 210, "heart_rate": 90}, "", True),
    ]

    print("=" * 55)
    print("KIRMIZI BAYRAK KURAL MOTORU - TEST SONUCLARI")
    print("=" * 55)
    all_passed = True
    for i, (vitals, symptoms, expected) in enumerate(test_cases, 1):
        result = check_red_flags(vitals, symptoms)
        passed = result["red_flag"] == expected
        status = "[GECTI]" if passed else "[BASARISIZ]"
        if not passed:
            all_passed = False
        print(f"\nTest {i}: {status}")
        print(f"  Vitals: {vitals}, Symptoms: '{symptoms}'")
        print(f"  Beklenen: {expected} | Alinan: {result['red_flag']}")
        if result["all_reasons"]:
            print(f"  Nedenler: {result['all_reasons']}")

    print("\n" + "=" * 55)
    print("SONUC:", "Tum testler gecti [OK]" if all_passed else "Bazi testler basarisiz [HATA]")
