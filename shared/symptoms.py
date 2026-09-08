"""
shared/symptoms.py
------------------
Kanonik semptom taksonomisi — TEK DOĞRULUK KAYNAĞI.

Bu modül üç yeri birden besler ve böylece "form Türkçe / veri seti İngilizce"
uyuşmazlığını kökten çözer:

  1. Eğitim hattı  (data/load_ktas.py)      — dataset'in İngilizce serbest
                                              metnini kanonik koda normalize eder
  2. Triaj formu   (pages/1_Triaj_Kayit.py) — iki dilli açılır liste
  3. Kural motoru  (shared/rules.py)        — kırmızı bayrak eşleşmesi kırılgan
                                              "kelime metinde geçiyor mu" yerine
                                              kanonik koda dayanır

KTAS veri setinde 422 farklı serbest metin var ve aynı şey defalarca farklı
yazılmış: "abd pain" / "abd. pain" / "abdomen pain" / "pain, abdominal".
Aşağıdaki 26 kategori vakaların ~%84'ünü temiz şekilde kapsıyor.

⚠️ UYARI: Bu bir karar destek aracıdır; kesin tanı koymaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "Symptom", "SYMPTOMS", "OTHER_CODE",
    "normalize", "matches_code", "options", "label", "all_codes",
    "suggested_ktas_for", "is_high_acuity",
]

OTHER_CODE = "other"


@dataclass(frozen=True)
class Symptom:
    """Tek bir kanonik semptom kategorisi."""

    code: str
    label_tr: str
    label_en: str
    # Serbest metni bu koda eşleyen regex (TR + EN birlikte, küçük harf üzerinde)
    pattern: str
    # Semptom TEK BAŞINA hangi KTAS seviyesini ima eder? None = ima etmez.
    # Kural motoruna yalnızca bir taban sağlar; vital bulgular bunu ezebilir.
    suggested_ktas: int | None = None

    def matches(self, text: str) -> bool:
        return bool(re.search(self.pattern, text))


# ---------------------------------------------------------------------------
# Taksonomi
#
# SIRA ÖNEMLİDİR: ilk eşleşen kazanır. Spesifik olan genel olandan önce gelmeli.
# Örneğin "left chest pain" chest_pain'e düşmeli; extremity_pain kalıbındaki
# "arm|leg" ifadesine takılmamalı.
#
# suggested_ktas gerekçeleri:
#   1    -> hava yolu / bilinç / dolaşım doğrudan tehdit altında
#   2    -> zamana duyarlı, hızlı değerlendirme gerekir (AKS, inme, GİS kanama)
#   None -> tek başına aciliyet imasi yok; seviyeyi vital bulgular belirler
# ---------------------------------------------------------------------------
SYMPTOMS: list[Symptom] = [
    Symptom(
        "altered_mental", "Bilinç değişikliği", "Altered mental status",
        r"mental|conscious|confus|drowsy|stupor|coma|obtund"
        r"|bilinç|bilinc|konfüz|konfuz|letarj|dalgın|dalgin",
        suggested_ktas=1,
    ),
    Symptom(
        "seizure", "Nöbet / Konvülsiyon", "Seizure",
        r"seizure|convuls|epilep|post ?ictal"
        r"|nöbet|nobet|konvüls|konvuls|havale",
        suggested_ktas=1,
    ),
    Symptom(
        "neuro_deficit", "Nörolojik defisit (inme şüphesi)", "Neuro deficit / stroke",
        r"dysarthr|aphas|hemipar|hemipleg|paralys|facial palsy|stroke|cva"
        r"|felç|felc|inme|konuşma bozuk|konusma bozuk|yüz kaymas|yuz kaymas",
        suggested_ktas=2,
    ),
    Symptom(
        "dyspnea", "Nefes darlığı", "Dyspnea",
        r"dyspn|breath|respirat|wheez|asthma|copd|suffocat"
        r"|nefes darl|nefes güçl|nefes gucl|solunum sık|solunum sik"
        r"|nefes alam|dispne|hırılt|hirilt",
        suggested_ktas=2,
    ),
    Symptom(
        "chest_pain", "Göğüs ağrısı", "Chest pain",
        r"chest|angina|sternum|precordial"
        r"|göğüs|gogus|göğsüs|gögüs|kalp ağr|kalp agr",
        suggested_ktas=2,
    ),
    Symptom(
        "syncope", "Senkop / Bayılma", "Syncope",
        r"syncop|faint|collapse|black ?out"
        r"|senkop|bayıl|bayil|baygın|baygin",
        suggested_ktas=2,
    ),
    Symptom(
        "gi_bleed", "Gastrointestinal kanama", "GI bleeding",
        r"hematemesis|melena|hematochezia|gi bleed|coffee ground"
        r"|kan kusma|siyah dışk|siyah disk|makattan kan",
        suggested_ktas=2,
    ),
    Symptom(
        "palpitation", "Çarpıntı", "Palpitation",
        r"palpitat|arrhythm|tachycard|a-?fib|atrial fib"
        r"|çarpınt|carpint|ritim bozuk|aritmi",
        suggested_ktas=2,
    ),
    Symptom(
        "bleeding_other", "Kanama (diğer)", "Bleeding (other)",
        r"bleeding|hemorrhag|epistaxis|hemoptysis|vaginal bleed"
        r"|kanama|burun kanam|vajinal kanama",
        suggested_ktas=2,
    ),
    Symptom(
        "wound_trauma", "Yaralanma / Travma", "Wound / Trauma",
        r"wound|injur|laceration|abrasion|contusion|fracture|trauma|burn|bite"
        r"|amputat|dislocat|stab|gunshot"
        r"|yaralan|travma|kırık|kirik|yanık|yanik|kesik|ısırık|isirik|çıkık|cikik",
    ),
    Symptom(
        "abd_pain", "Karın ağrısı", "Abdominal pain",
        r"abd|epigastr|ruq|luq|rlq|llq|flank|abdomen|stomach ?ache|colic"
        r"|karın ağr|karin agr|mide ağr|mide agr|böğür|bogur|kolik",
    ),
    Symptom(
        "dizziness", "Baş dönmesi", "Dizziness",
        r"dizz|vertigo|lightheaded|unsteady"
        r"|baş dönmes|bas donmes|denge kayb|sersem",
    ),
    Symptom(
        "headache", "Baş ağrısı", "Headache",
        r"headache|\bha\b|h-?head|migraine|cephalgia"
        r"|baş ağr|bas agr|migren",
    ),
    Symptom(
        "fever", "Ateş", "Fever",
        r"fever|febrile|chill|pyrexia"
        r"|ateş|ates|titreme",
    ),
    Symptom(
        "vomiting", "Bulantı / Kusma", "Nausea / Vomiting",
        r"vomit|nausea|emesis|retching"
        r"|kusma|bulant",
    ),
    Symptom(
        "diarrhea", "İshal", "Diarrhea",
        r"diarrh|loose stool|dysentery"
        r"|ishal|sürgün|surgun",
    ),
    Symptom(
        "weakness", "Genel halsizlik", "General weakness",
        r"weakness|fatigue|malaise|lethargy"
        r"|halsiz|yorgun|bitkin|takats",
    ),
    Symptom(
        "back_pain", "Sırt / Bel ağrısı", "Back pain",
        r"back pain|low ?back|lumbago|sciatica"
        r"|sırt ağr|sirt agr|bel ağr|bel agr|siyatik",
    ),
    Symptom(
        "extremity_pain", "Ekstremite ağrısı", "Extremity pain",
        r"\bleg\b|\barm\b|knee|shoulder|ankle|wrist|hip|foot|hand|elbow|finger|toe"
        r"|bacak|kol ağr|kol agr|diz |omuz|bilek|kalça|kalca|ayak|el ağr|el agr"
        r"|dirsek|parmak",
    ),
    Symptom(
        "urinary", "İdrar yolu şikayeti", "Urinary complaint",
        r"dysuria|urin|hematuria|bladder|renal colic"
        r"|idrar|sidik|böbrek taş|bobrek tas",
    ),
    Symptom(
        "sore_throat", "Boğaz ağrısı", "Sore throat",
        r"throat|tonsil|pharyng|odynophag"
        r"|boğaz ağr|bogaz agr|bademcik|yutma ağr|yutma agr",
    ),
    Symptom(
        "cough", "Öksürük", "Cough",
        r"cough|sputum|phlegm|bronchit"
        r"|öksürük|oksuruk|balgam|bronşit|bronsit",
    ),
    Symptom(
        "rash", "Döküntü / Alerji", "Rash / Allergy",
        r"rash|urticar|pruritus|itch|allerg|hives|eczema"
        r"|döküntü|dokuntu|kaşınt|kasint|alerji|kurdeşen|kurdesen",
    ),
    Symptom(
        "edema", "Ödem / Şişlik", "Edema / Swelling",
        r"edema|oedema|swell|distension"
        r"|ödem|odem|şişlik|sislik|şişkinlik|siskinlik",
    ),
    Symptom(
        "eye", "Göz şikayeti", "Eye complaint",
        r"ocular|\beye\b|vision|visual|conjunctiv|corneal"
        r"|göz ağr|goz agr|görme|gorme|konjonktiv|kornea",
    ),
    Symptom(OTHER_CODE, "Diğer / Listede yok", "Other", r".*"),
]

_BY_CODE: dict[str, Symptom] = {s.code: s for s in SYMPTOMS}

# Tek başına yüksek aciliyet ima eden kodlar
_HIGH_ACUITY: dict[str, int] = {
    s.code: s.suggested_ktas for s in SYMPTOMS if s.suggested_ktas is not None
}


# ---------------------------------------------------------------------------
# Genel API
# ---------------------------------------------------------------------------

def normalize(text: str | None) -> str:
    """
    Serbest metni kanonik semptom koduna indirger.

    Boş veya eşleşmeyen metin için OTHER_CODE döner; asla istisna fırlatmaz,
    çünkü eğitim hattında veri setinin tamamı bu fonksiyondan geçer.

    >>> normalize("abd. pain")
    'abd_pain'
    >>> normalize("Nefes darlığı")
    'dyspnea'
    >>> normalize("")
    'other'
    """
    if not text:
        return OTHER_CODE
    t = str(text).strip().lower()
    if not t:
        return OTHER_CODE
    for s in SYMPTOMS:
        if s.code == OTHER_CODE:
            continue
        if s.matches(t):
            return s.code
    return OTHER_CODE


def matches_code(code: str, text: str | None) -> bool:
    """
    Metin, BELİRLİ bir semptom kodunun kalıbıyla eşleşiyor mu?

    normalize() 'ilk eşleşen kazanır' mantığıyla tek bir kod döndürür; bu
    yüzden "göğüs ağrısı ve nefes darlığı" gibi birden fazla semptom içeren
    metinlerde tek tek varlık sorgusu için bu fonksiyon kullanılmalıdır.

    >>> matches_code("chest_pain", "göğüs ağrısı ve nefes darlığı")
    True
    >>> matches_code("dyspnea", "göğüs ağrısı ve nefes darlığı")
    True
    """
    s = _BY_CODE.get(code)
    if s is None or not text:
        return False
    return s.matches(str(text).strip().lower())


def all_codes() -> list[str]:
    """Taksonomideki tüm kanonik kodlar (tanım sırası korunur)."""
    return [s.code for s in SYMPTOMS]


def label(code: str, lang: str = "TR") -> str:
    """Kodun görünen etiketi. Bilinmeyen kod kendisini döndürür."""
    s = _BY_CODE.get(code)
    if s is None:
        return code
    return s.label_tr if str(lang).upper() == "TR" else s.label_en


def options(lang: str = "TR") -> list[tuple[str, str]]:
    """
    Form açılır listesi için (kod, etiket) çiftleri.
    'other' her zaman en sonda kalır; geri kalanı etikete göre alfabetik.
    """
    body = [s for s in SYMPTOMS if s.code != OTHER_CODE]
    body.sort(key=lambda s: label(s.code, lang).lower())
    return [(s.code, label(s.code, lang)) for s in body] + [
        (OTHER_CODE, label(OTHER_CODE, lang))
    ]


def suggested_ktas_for(code: str) -> int | None:
    """Semptomun tek başına ima ettiği KTAS seviyesi (yoksa None)."""
    return _HIGH_ACUITY.get(code)


def is_high_acuity(code: str) -> bool:
    """Semptom tek başına yüksek aciliyet ima ediyor mu?"""
    return code in _HIGH_ACUITY
