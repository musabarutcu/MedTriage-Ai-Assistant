"""
model/train_model.py
--------------------
KTAS triaj modeli eğitim hattı.

MİMARİ KARARLAR (hepsi ölçüme dayalı — bkz. model/evaluate.py çıktısı)
----------------------------------------------------------------------
1. TEK PIPELINE — İmputasyon, one-hot kodlama ve model tek bir sklearn
   Pipeline'ı içinde. Böylece çapraz doğrulamada her katlama kendi
   medyanını hesaplar; veri sızıntısı YAPISAL OLARAK imkânsız hale gelir.
   (Eskiden imputasyon load_ktas() içinde, tüm veri üzerinde yapılıyordu.)

2. EKSİKLİK BİR SİNYALDİR — spo2_missing / pain_missing bayrakları
   imputasyondan ÖNCE hesaplanır. SpO2'nin %55'i, ağrı skorunun %44'ü
   eksik; "ölçülmemiş olması" başlı başına klinik bilgi taşır.
   (Eskiden bu bayraklar imputasyondan sonra hesaplandığı için hep 0'dı.)

3. SEMPTOM KODU — Serbest metin şikayet, shared/symptoms.py taksonomisi
   ile 26 kanonik koda indirgenip one-hot verilir. Ölçülen katkı:
   doğrulukta yaklaşık +6 puan.

4. SMOTE — Yalnızca eğitim katlamasında, Pipeline içinde. Eskiden SMOTE
   ile sample_weight birlikte uygulanıyordu; bu çifte dengeleme demekti.
   Artık yalnızca SMOTE var.

5. KALİBRASYON — Isotonic. Ham doğruluktan ~2 puan götürür ama güven
   skorunu ANLAMLI kılar: güven ≥0.60 bölgesinde doğruluk ~%85,
   ≥0.70 bölgesinde ~%90. Ürün bir "ikinci okuyucu" olduğu için
   modelin ne zaman bilmediğini bilmesi ham doğruluktan değerlidir.

Çalıştırma:
    python model/train_model.py

Çıktı:
    model/triage_model.pkl    — birincil model paketi
    model/baseline_model.pkl  — LogisticRegression baseline

⚠️ UYARI: Bu sistem bir karar destek aracıdır; kesin tanı koymaz.
"""

from __future__ import annotations

import sys
import logging
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.load_ktas import load_ktas, get_feature_columns
from shared.symptoms import label as symptom_label
from model.estimators import KTASXGBClassifier

try:
    from xgboost import XGBClassifier
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False

try:
    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline as ImbPipeline
    _SMOTE_AVAILABLE = True
except ImportError:
    _SMOTE_AVAILABLE = False

try:
    import shap
    _SHAP_AVAILABLE = True
except ImportError:
    _SHAP_AVAILABLE = False

warnings.filterwarnings("ignore", category=UserWarning)
logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent
PRIMARY_MODEL_PATH = MODEL_DIR / "triage_model.pkl"
BASELINE_MODEL_PATH = MODEL_DIR / "baseline_model.pkl"

SYMPTOM_COL = "symptom_code"

# Türetilen (mühendislik) özellikler — imputasyondan ÖNCE hesaplanır
ENGINEERED_FEATURES = [
    "shock_index", "pulse_pressure", "map", "spo2_missing", "pain_missing",
]

# Güven bandı eşikleri — model/evaluate.py ölçümlerinden türetilmiştir.
# Kalibre edilmiş olasılıklar üzerinde geçerlidir.
CONFIDENCE_HIGH = 0.60   # bu bandın üstünde doğruluk ~%85 (hemşire seviyesi)
CONFIDENCE_LOW = 0.40    # bu bandın altında model kendi kararına güvenmiyor

KTAS_LEVEL_NAMES = {
    1: "Resüsitasyon (Hemen)",
    2: "Acil (≤15 dk)",
    3: "Acil-Değil (≤60 dk)",
    4: "Az Acil (≤120 dk)",
    5: "Acil Değil (≤240 dk)",
}

FEATURE_DISPLAY_NAMES = {
    "age": "Yaş", "sbp": "Sistolik tansiyon", "dbp": "Diyastolik tansiyon",
    "heart_rate": "Nabız", "resp_rate": "Solunum hızı", "temperature": "Ateş",
    "spo2": "SpO2", "pain_scale": "Ağrı skoru", "gcs": "GCS",
    "gender": "Cinsiyet", "arrival_mode": "Geliş şekli",
    "mental_status": "Mental durum", "injury": "Travma", "has_pain": "Ağrı mevcut",
    "shock_index": "Şok indeksi (HR/SKB)", "pulse_pressure": "Nabız basıncı",
    "map": "Ortalama arteriyel basınç",
    "spo2_missing": "SpO2 ölçülmemiş", "pain_missing": "Ağrı skoru alınmamış",
    SYMPTOM_COL: "Başvuru şikayeti",
}

# Sayısal kodla saklanan kategorik özelliklerin okunur karşılıkları.
# Gerekçe metninde "travma (2)" yerine "travma (yok)" yazılmasını sağlar;
# kodlar KTAS veri setinin kendi kodlamasıdır.
CATEGORICAL_VALUE_LABELS: dict[str, dict[int, str]] = {
    "gender":        {1: "erkek", 2: "kadın"},
    "injury":        {1: "var", 2: "yok"},
    "has_pain":      {0: "yok", 1: "var"},
    "mental_status": {1: "alert", 2: "sesli uyarıya yanıtlı",
                      3: "ağrılı uyarıya yanıtlı", 4: "yanıtsız"},
    "arrival_mode":  {1: "yürüyerek", 2: "ambulans", 3: "helikopter",
                      4: "özel araç", 5: "tekerlekli sandalye",
                      6: "sedye", 7: "diğer"},
    "spo2_missing":  {0: "ölçüldü", 1: "ölçülmedi"},
    "pain_missing":  {0: "alındı", 1: "alınmadı"},
}

FEATURE_UNIT_MAP = {
    "sbp": "mmHg", "dbp": "mmHg", "heart_rate": "atım/dk", "resp_rate": "nefes/dk",
    "temperature": "°C", "spo2": "%", "pain_scale": "/10", "age": "yaş",
    "pulse_pressure": "mmHg", "map": "mmHg",
}


# ---------------------------------------------------------------------------
# Özellik hazırlama
# ---------------------------------------------------------------------------

def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Klinik anlam taşıyan türetilmiş özellikleri ekler.

    İMPUTASYONDAN ÖNCE çağrılmalıdır — eksiklik bayrakları ancak o zaman
    gerçek bilgi taşır.

    shock_index    : HR / SKB   (>1.0 ciddi şok riski)
    pulse_pressure : SKB - DKB  (dar <25 kalp yetmezliği; geniş >60 aort yetm.)
    map            : DKB + (SKB-DKB)/3  (perfüzyon göstergesi)
    spo2_missing   : SpO2 ölçülmemiş mi? (0/1)
    pain_missing   : Ağrı skoru alınmamış mı? (0/1)
    """
    df = df.copy()

    sbp = pd.to_numeric(df.get("sbp"), errors="coerce")
    dbp = pd.to_numeric(df.get("dbp"), errors="coerce")
    hr = pd.to_numeric(df.get("heart_rate"), errors="coerce")

    df["spo2_missing"] = (
        pd.to_numeric(df.get("spo2"), errors="coerce").isna().astype(int)
        if "spo2" in df.columns else 0
    )
    df["pain_missing"] = (
        pd.to_numeric(df.get("pain_scale"), errors="coerce").isna().astype(int)
        if "pain_scale" in df.columns else 0
    )

    df["shock_index"] = hr / sbp.replace(0, np.nan)
    df["pulse_pressure"] = sbp - dbp
    df["map"] = dbp + (sbp - dbp) / 3.0

    return df


def resolve_feature_columns(df: pd.DataFrame) -> list[str]:
    """Model girdisi olacak sütunlar (sıra deterministik, tekrarsız)."""
    cols = get_feature_columns(df) + ENGINEERED_FEATURES
    seen, out = set(), []
    for c in cols:
        if c in df.columns and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def build_pipeline(feature_columns: list[str], calibrate: bool = True) -> Pipeline:
    """
    Ön işleme + model hattını kurar.

    İmputasyon Pipeline'ın İÇİNDEDİR: çapraz doğrulamada her katlama kendi
    medyanını öğrenir, test katlamasından bilgi sızmaz.
    """
    numeric_cols = [c for c in feature_columns if c != SYMPTOM_COL]
    transformers = [("num", SimpleImputer(strategy="median"), numeric_cols)]
    if SYMPTOM_COL in feature_columns:
        transformers.append(
            ("sym", OneHotEncoder(handle_unknown="ignore"), [SYMPTOM_COL])
        )
    preprocessor = ColumnTransformer(transformers)

    xgb_params = dict(
        n_estimators=400, learning_rate=0.06, max_depth=6,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1, verbosity=0,
    )

    if not _XGB_AVAILABLE:
        raise ImportError(
            "XGBoost kurulu değil. Kurmak için: pip install xgboost"
        )

    estimator = KTASXGBClassifier(xgb_params)

    if _SMOTE_AVAILABLE:
        # SMOTE imblearn Pipeline içinde: yalnızca fit sırasında, yalnızca
        # eğitim katlamasında uygulanır. Tahmin sırasında devre dışıdır.
        estimator = ImbPipeline([
            ("smote", SMOTE(random_state=42, k_neighbors=3)),
            ("clf", estimator),
        ])
    else:
        logger.warning("imbalanced-learn yok — SMOTE atlanıyor.")

    if calibrate:
        estimator = CalibratedClassifierCV(estimator, method="isotonic", cv=3)

    return Pipeline([("pre", preprocessor), ("model", estimator)])


def prepare_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """load_ktas() çıktısını (X, y, feature_columns) üçlüsüne çevirir."""
    df = add_engineered_features(df)
    feature_columns = resolve_feature_columns(df)
    return df[feature_columns], df["ktas_level"].to_numpy(), feature_columns


# ---------------------------------------------------------------------------
# Eğitim
# ---------------------------------------------------------------------------

def train_models(df: pd.DataFrame) -> dict:
    """
    Birincil (kalibre XGBoost) ve baseline (LogisticRegression) modelleri eğitir.

    Döndürür
    --------
    dict
        save_model_bundle()'a verilebilecek model paketi.
    """
    logger.info("=" * 62)
    logger.info("MODEL EĞİTİMİ")
    logger.info("=" * 62)

    X, y, feature_columns = prepare_xy(df)
    logger.info("Örnek: %d | Özellik: %d", len(X), len(feature_columns))
    logger.info("Özellikler: %s", feature_columns)

    dist = pd.Series(y).value_counts().sort_index()
    for level, count in dist.items():
        logger.info("  KTAS-%s (%s): %d hasta",
                    level, KTAS_LEVEL_NAMES.get(int(level), "?"), count)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    logger.info("Eğitim: %d | Test: %d", len(X_train), len(X_test))

    # ── Birincil model ───────────────────────────────────────────────────
    logger.info("\n--- Birincil model: XGBoost + SMOTE + isotonic kalibrasyon ---")
    primary = build_pipeline(feature_columns, calibrate=True)
    primary.fit(X_train, y_train)
    y_pred = primary.predict(X_test)
    print(classification_report(y_test, y_pred, zero_division=0))

    # ── Baseline ─────────────────────────────────────────────────────────
    logger.info("--- Baseline: LogisticRegression ---")
    numeric_cols = [c for c in feature_columns if c != SYMPTOM_COL]
    baseline = Pipeline([
        ("pre", ColumnTransformer([
            ("num", Pipeline([
                ("imp", SimpleImputer(strategy="median")),
                ("sc", StandardScaler()),
            ]), numeric_cols),
            ("sym", OneHotEncoder(handle_unknown="ignore"), [SYMPTOM_COL]),
        ])),
        ("clf", LogisticRegression(class_weight="balanced", max_iter=2000,
                                   random_state=42)),
    ])
    baseline.fit(X_train, y_train)
    print(classification_report(y_test, baseline.predict(X_test), zero_division=0))

    # ── SHAP açıklayıcı ──────────────────────────────────────────────────
    explainer, shap_feature_names = _build_shap_explainer(primary, feature_columns)

    return {
        "pipeline": primary,
        "baseline": baseline,
        "feature_columns": feature_columns,
        "shap_explainer": explainer,
        "shap_feature_names": shap_feature_names,
        "classes": sorted(int(c) for c in np.unique(y)),
        "calibrated": True,
        "confidence_high": CONFIDENCE_HIGH,
        "confidence_low": CONFIDENCE_LOW,
    }


def _build_shap_explainer(pipeline: Pipeline, feature_columns: list[str]):
    """
    Kalibre edilmiş topluluğun içindeki ham XGBoost ağacı üzerinde
    TreeExplainer kurar.

    Kalibrasyon katmanı olasılıkları yeniden ölçekler ama ağacın öğrendiği
    katkı yapısını değiştirmez; bu yüzden açıklama ham ağaçtan üretilir.
    Başarısız olursa None döner ve açıklama metni SHAP'siz üretilir.
    """
    if not _SHAP_AVAILABLE:
        logger.warning("shap kurulu değil — açıklama SHAP'siz üretilecek.")
        return None, None

    try:
        model = pipeline.named_steps["model"]
        inner = model.calibrated_classifiers_[0].estimator
        if hasattr(inner, "named_steps"):
            inner = inner.named_steps["clf"]
        booster = inner.model_

        names = None
        try:
            names = list(pipeline.named_steps["pre"].get_feature_names_out())
        except Exception:
            names = None

        explainer = shap.TreeExplainer(booster)
        logger.info("SHAP TreeExplainer hazır.")
        return explainer, names
    except Exception as exc:
        logger.warning("SHAP açıklayıcı kurulamadı (%s) — SHAP'siz devam.", exc)
        return None, None


# ---------------------------------------------------------------------------
# Tahmin + açıklama
# ---------------------------------------------------------------------------

def predict_with_explanation(
    input_dict: dict,
    model_bundle: dict | None = None,
) -> dict:
    """
    Tek bir hasta için KTAS tahmini ve Türkçe gerekçe üretir.

    Kural motorunu ÇAĞIRMAZ — önce shared.rules.check_red_flags()
    çalıştırılmalıdır.

    Döndürür
    --------
    dict
        {
          "ktas_level": int, "ktas_name": str,
          "confidence": float,            # kalibre edilmiş olasılık
          "confidence_band": str,         # "high" | "medium" | "low"
          "explanation": str,
          "probabilities": dict[int, float],
          "feature_contributions": dict[str, float],
        }
    """
    if model_bundle is None:
        model_bundle = load_model_bundle()

    pipeline: Pipeline = model_bundle["pipeline"]
    feature_columns: list[str] = model_bundle["feature_columns"]

    # Girdi çerçevesini eğitimdeki sütun düzeniyle kur
    frame = add_engineered_features(pd.DataFrame([input_dict]))
    for col in feature_columns:
        if col not in frame.columns:
            frame[col] = np.nan
    if SYMPTOM_COL in feature_columns:
        frame[SYMPTOM_COL] = frame[SYMPTOM_COL].fillna("other").astype(str)
    X = frame[feature_columns]

    proba = pipeline.predict_proba(X)[0]
    classes = [int(c) for c in pipeline.classes_]
    best_idx = int(np.argmax(proba))
    ktas_level = classes[best_idx]
    confidence = float(proba[best_idx])

    high = model_bundle.get("confidence_high", CONFIDENCE_HIGH)
    low = model_bundle.get("confidence_low", CONFIDENCE_LOW)
    band = "high" if confidence >= high else ("low" if confidence < low else "medium")

    contributions = _shap_contributions(model_bundle, pipeline, X, best_idx)
    top_features = sorted(contributions.items(), key=lambda kv: abs(kv[1]),
                          reverse=True)[:3] if contributions else []

    return {
        "ktas_level": ktas_level,
        "ktas_name": KTAS_LEVEL_NAMES.get(ktas_level, "Bilinmiyor"),
        "confidence": confidence,
        "confidence_band": band,
        "explanation": _build_turkish_explanation(
            ktas_level, input_dict, top_features, confidence, band
        ),
        "probabilities": {c: float(p) for c, p in zip(classes, proba)},
        "feature_contributions": contributions,
    }


def _shap_contributions(bundle: dict, pipeline: Pipeline, X: pd.DataFrame,
                        class_idx: int) -> dict[str, float]:
    """SHAP katkılarını ham özellik adlarına eşleyerek döndürür."""
    explainer = bundle.get("shap_explainer")
    if explainer is None:
        return {}
    try:
        X_pre = pipeline.named_steps["pre"].transform(X)
        if hasattr(X_pre, "toarray"):
            X_pre = X_pre.toarray()
        values = explainer.shap_values(X_pre)

        if isinstance(values, list):
            row = np.asarray(values[class_idx])[0]
        elif np.asarray(values).ndim == 3:
            row = np.asarray(values)[0, :, class_idx]
        else:
            row = np.asarray(values)[0]

        names = bundle.get("shap_feature_names")
        if not names or len(names) != len(row):
            names = [f"f{i}" for i in range(len(row))]

        # One-hot semptom sütunlarını tek bir "şikayet" katkısında topla
        merged: dict[str, float] = {}
        for name, val in zip(names, row):
            clean = str(name).split("__", 1)[-1]
            if clean.startswith(f"{SYMPTOM_COL}_"):
                clean = SYMPTOM_COL
            merged[clean] = merged.get(clean, 0.0) + float(val)
        return merged
    except Exception as exc:
        logger.warning("SHAP hesaplanamadı: %s", exc)
        return {}


def _build_turkish_explanation(
    ktas_level: int,
    input_dict: dict,
    top_features: list[tuple[str, float]],
    confidence: float,
    band: str,
) -> str:
    """En etkili özelliklere dayalı kısa Türkçe gerekçe cümlesi üretir."""
    parts: list[str] = []
    for name, _shap_value in top_features:
        raw = input_dict.get(name)
        if raw is None or (isinstance(raw, float) and raw != raw):
            continue
        display = FEATURE_DISPLAY_NAMES.get(name, name)
        unit = FEATURE_UNIT_MAP.get(name, "")
        if name == SYMPTOM_COL:
            # Ham kod ("chest_pain") yerine okunur etiket ("Göğüs ağrısı")
            text = symptom_label(str(raw), "TR")
            unit = ""
        elif name in CATEGORICAL_VALUE_LABELS:
            # Kodlanmış kategorik: "travma (2)" değil "travma (yok)"
            try:
                text = CATEGORICAL_VALUE_LABELS[name].get(int(raw), str(raw))
            except (TypeError, ValueError):
                text = str(raw)
            unit = ""
        elif isinstance(raw, float):
            text = f"{raw:.1f}"
        else:
            text = str(raw)

        if name == "spo2" and isinstance(raw, (int, float)) and raw < 94:
            parts.append(f"düşük oksijen satürasyonu (SpO2 %{text})")
        elif name == "heart_rate" and isinstance(raw, (int, float)) and raw > 100:
            parts.append(f"taşikardi (nabız {text}/dk)")
        elif name == "sbp" and isinstance(raw, (int, float)) and raw < 100:
            parts.append(f"düşük tansiyon (SKB {text} mmHg)")
        elif name == "pain_scale" and isinstance(raw, (int, float)) and raw >= 7:
            parts.append(f"yüksek ağrı skoru ({text}/10)")
        else:
            parts.append(f"{display.lower()} ({text}{' ' + unit if unit else ''})")

    ktas_name = KTAS_LEVEL_NAMES.get(ktas_level, "")
    conf_pct = int(round(confidence * 100))

    if band == "low":
        suffix = (f" Model bu vakada kararsız (güven %{conf_pct}) — "
                  f"klinik değerlendirme belirleyicidir.")
    elif band == "high":
        suffix = f" (Model güveni %{conf_pct} — güvenilir bant)"
    else:
        suffix = f" (Model güveni %{conf_pct})"

    if not parts:
        return (f"Genel klinik tablo değerlendirilerek KTAS-{ktas_level} "
                f"({ktas_name}) önerildi.{suffix}")

    if ktas_level <= 2:
        action = "nedeniyle öncelik yükseltildi"
    elif ktas_level == 3:
        action = "dikkate alınarak orta öncelik atandı"
    else:
        action = "göz önünde bulundurularak rutin triaj uygulandı"

    if len(parts) == 1:
        feature_text = parts[0]
    elif len(parts) == 2:
        feature_text = f"{parts[0]} ve {parts[1]}"
    else:
        feature_text = f"{parts[0]}, {parts[1]} ve {parts[2]}"

    # .capitalize() dizenin geri kalanını küçültür ve "°C" gibi
    # birimleri bozar; yalnızca ilk karakteri büyütüyoruz.
    feature_text = feature_text[:1].upper() + feature_text[1:]
    return f"{feature_text} {action}.{suffix}"


# ---------------------------------------------------------------------------
# Kayıt / yükleme
# ---------------------------------------------------------------------------

def save_model_bundle(bundle: dict) -> None:
    """Model paketini diske yazar."""
    baseline = bundle.pop("baseline", None)
    joblib.dump(bundle, PRIMARY_MODEL_PATH)
    if baseline is not None:
        joblib.dump(baseline, BASELINE_MODEL_PATH)
        bundle["baseline"] = baseline
    logger.info("Birincil model kaydedildi: %s", PRIMARY_MODEL_PATH)
    logger.info("Baseline kaydedildi:      %s", BASELINE_MODEL_PATH)


def load_model_bundle(model_path: Path | str | None = None) -> dict:
    """
    Kaydedilmiş model paketini yükler.

    Eski sürüm paketleri ('rf_pipeline' anahtarlı) artık desteklenmez;
    özellik seti ve etiket düzeni değiştiği için sessizce yanlış tahmin
    üretmek yerine açık hata verilir.
    """
    path = Path(model_path) if model_path else PRIMARY_MODEL_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Model dosyası bulunamadı: {path}\n"
            f"Önce çalıştırın: python model/train_model.py"
        )
    bundle = joblib.load(path)
    if "pipeline" not in bundle:
        raise ValueError(
            f"Eski biçimde model paketi: {path}\n"
            f"Özellik seti değişti; modeli yeniden eğitin: "
            f"python model/train_model.py"
        )
    return bundle


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------

def _force_utf8_console() -> None:
    """
    Windows konsolu varsayılan olarak cp1254 kullanır ve Türkçe metinlerdeki
    '≤', 'ğ', 'ş' gibi karakterlerde UnicodeEncodeError verir. Script çıktısı
    tamamen Türkçe olduğu için giriş noktasında akışları UTF-8'e çeviriyoruz.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


if __name__ == "__main__":
    _force_utf8_console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        df = load_ktas()
    except FileNotFoundError:
        logger.error(
            "KTAS veri seti bulunamadı. data/ klasörüne .xlsx veya .csv koyun.\n"
            "Kaynak: https://www.kaggle.com/datasets/llncss/ktas-dataset"
        )
        sys.exit(1)

    bundle = train_models(df)
    save_model_bundle(bundle)

    logger.info("\n--- Örnek tahmin ---")
    sample = {
        "age": 55, "gender": 1, "arrival_mode": 2, "injury": 2,
        "has_pain": 1, "pain_scale": 8.0, "mental_status": 1,
        "sbp": 88.0, "dbp": 60.0, "heart_rate": 112.0,
        "resp_rate": 24.0, "temperature": 37.8, "spo2": 93.0,
        SYMPTOM_COL: "chest_pain",
    }
    result = predict_with_explanation(sample, bundle)
    print("=" * 58)
    print(f"KTAS      : {result['ktas_level']} — {result['ktas_name']}")
    print(f"Güven     : %{result['confidence'] * 100:.1f} ({result['confidence_band']})")
    print(f"Gerekçe   : {result['explanation']}")
    print("\nOlasılıklar:")
    for level, prob in sorted(result["probabilities"].items()):
        print(f"  KTAS-{level}: {'█' * int(prob * 30):<30} %{prob * 100:.1f}")

    logger.info("Eğitim tamamlandı. Dürüst değerlendirme için: "
                "python model/evaluate.py")
