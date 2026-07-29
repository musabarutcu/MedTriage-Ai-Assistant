"""
model/train_model.py
--------------------
KTAS triaj modeli eğitim scripti.

Üç model eğitir:
  (a) LogisticRegression  — tam yorumlanabilir baseline
  (b) RandomForestClassifier — güçlü ensemble, SHAP destekli
  (c) XGBClassifier  — birincil model (en yüksek doğruluk)

Model iyileştirme yöntemleri:
  - Feature engineering: shock_index, pulse_pressure, MAP, spo2_missing, pain_missing
  - SMOTE ile azınlık sınıf örneklemesi (KTAS-1 için)
  - XGBoost scale_pos_weight ile sınıf dengesizliği yapılması

Calıştırma:
    python model/train_model.py

Cıktı:
    model/triage_model.pkl    — Birincil model (XGBoost)
    model/baseline_model.pkl  — Baseline model (LogisticRegression)

⚠️ UYARI: Bu sistem bir karar destek aracıdır; kesin tanı koymaz.
"""

from __future__ import annotations

import sys
import logging
import warnings
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
import shap

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.impute import SimpleImputer

try:
    from xgboost import XGBClassifier
    _XGB_AVAILABLE = True
except ImportError:
    _XGB_AVAILABLE = False
    logger_tmp = logging.getLogger(__name__)
    logger_tmp.warning("XGBoost yuklu degil; RF birincil model olarak kullanilacak. "
                       "Kurmak icin: pip install xgboost")

try:
    from imblearn.over_sampling import SMOTE
    _SMOTE_AVAILABLE = True
except ImportError:
    _SMOTE_AVAILABLE = False

# Proje kökünü sys.path'e ekle (farklı çalışma dizinlerinden çağrı için)
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.load_ktas import load_ktas, get_feature_columns

warnings.filterwarnings("ignore", category=UserWarning)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
MODEL_DIR = Path(__file__).parent
PRIMARY_MODEL_PATH = MODEL_DIR / "triage_model.pkl"
BASELINE_MODEL_PATH = MODEL_DIR / "baseline_model.pkl"
EXPLAINER_PATH = MODEL_DIR / "shap_explainer.pkl"

KTAS_LEVEL_NAMES = {
    1: "Resüsitasyon (Hemen)",
    2: "Acil (≤15 dk)",
    3: "Acil-Değil (≤60 dk)",
    4: "Az Acil (≤120 dk)",
    5: "Acil Değil (≤240 dk)",
}

FEATURE_DISPLAY_NAMES = {
    "age":            "Yas",
    "sbp":            "Sistolik Tansiyon",
    "dbp":            "Diastolik Tansiyon",
    "heart_rate":     "Nabiz",
    "resp_rate":      "Solunum Hizi",
    "temperature":    "Ates",
    "spo2":           "SpO2 (Oksijen Saturasyonu)",
    "pain_scale":     "Agri Skoru",
    "gcs":            "GCS (Bilincskoru)",
    "gender":         "Cinsiyet",
    "arrival_mode":   "Gelis Sekli",
    "mental_status":  "Mental Durum",
    "injury":         "Travma/Yaralanma",
    # Muhendislik ozellikleri
    "shock_index":    "Sok Indeksi (HR/SBP)",
    "pulse_pressure": "Nabiz Basinci (SBP-DBP)",
    "map":            "Ort. Arteriyel Basinc",
    "spo2_missing":   "SpO2 Eksik Bayragi",
    "pain_missing":   "Agri Eksik Bayragi",
    "has_pain":       "Agri Mevcut",
    "patients_per_hour": "Saat basi hasta",
}

FEATURE_UNIT_MAP = {
    "sbp":          "mmHg",
    "dbp":          "mmHg",
    "heart_rate":   "atim/dk",
    "resp_rate":    "nefes/dk",
    "temperature":  "C",
    "spo2":         "%",
    "pain_scale":   "/10",
    "age":          "yas",
    "shock_index":  "",
    "pulse_pressure": "mmHg",
    "map":          "mmHg",
}


# ---------------------------------------------------------------------------
# Ön işleme
# ---------------------------------------------------------------------------

def preprocess(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    encoders: dict | None = None,
    fit: bool = True,
) -> tuple[np.ndarray, list[str], dict]:
    """
    DataFrame'i model girişi için hazırlar.

    Kategorik değişkenleri sayısallaştırır, özellik matrisini oluşturur.
    fit=True ise LabelEncoder'ları eğitir; fit=False ise mevcut encoder'ları kullanır
    (tahmin zamanı için).

    Parametreler
    ------------
    df : pd.DataFrame
        Temizlenmiş veri (load_ktas() çıktısı).
    feature_cols : list[str] | None
        Kullanılacak özellik sütunları. None ise get_feature_columns() kullanılır.
    encoders : dict | None
        fit=False ise kullanılacak mevcut LabelEncoder sözlüğü.
    fit : bool
        True → encoder'ları eğit ve döndür. False → mevcut encoder'ları kullan.

    Döndürür
    --------
    tuple[np.ndarray, list[str], dict]
        (X matrisi, özellik adları, encoder sözlüğü)
    """
    if feature_cols is None:
        feature_cols = get_feature_columns(df)

    # Yalnızca mevcut sütunları al
    feature_cols = [c for c in feature_cols if c in df.columns]

    if encoders is None:
        encoders = {}

    X_parts = []
    final_feature_names = []

    for col in feature_cols:
        series = df[col].copy()

        if pd.api.types.is_numeric_dtype(series):
            # Sayısal: direkt kullan
            arr = series.values.reshape(-1, 1).astype(float)
            X_parts.append(arr)
            final_feature_names.append(col)
        else:
            # Kategorik: LabelEncoding
            series = series.astype(str).fillna("bilinmiyor")
            if fit:
                le = LabelEncoder()
                le.fit(series)
                encoders[col] = le
            else:
                if col not in encoders:
                    logger.warning(f"'{col}' için encoder bulunamadı, atlanıyor.")
                    continue
                le = encoders[col]
                # Bilinmeyen kategoriler → 0
                known = set(le.classes_)
                series = series.apply(lambda x: x if x in known else le.classes_[0])

            arr = le.transform(series).reshape(-1, 1).astype(float)
            X_parts.append(arr)
            final_feature_names.append(col)

    X = np.hstack(X_parts) if X_parts else np.empty((len(df), 0))
    return X, final_feature_names, encoders


# ---------------------------------------------------------------------------
# Feature Engineering
# ---------------------------------------------------------------------------

def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Klinik anlam tasiyan turetilen ozellikler ekler.

    Bu ozellikler modelin daha anlamli sinyal yakalamasi icin kritiktir.
    Ham vital degerlerden hesaplanir, yeni bilgi icerir.

    Eklenen ozellikler
    ------------------
    shock_index    : HR / SBP  (>1.0 = ciddi sok riski, hematolojik acillerde kullanilir)
    pulse_pressure : SBP - DBP  (dar: <25 = kalp yetmezligi; genis: >60 = aort yetmezligi)
    map            : DBP + (SBP-DBP)/3  (ortalama arteriyel basinc, perfuzyon gostergesi)
    spo2_missing   : Saturation impute oncesi eksik miydi? (0/1) — eksik SpO2 klinik ipucu
    pain_missing   : NRS_pain impute oncesi eksik miydi? (0/1) — eksik agri skoru ipucu

    Parametreler
    ------------
    df : pd.DataFrame
        load_ktas() ciktisi (imputation oncesi cagrilmali).

    Dondurur
    --------
    pd.DataFrame
        Orijinal + muhendislik ozellikleri iceren DataFrame.
    """
    df = df.copy()

    # Eksik bayraklari ONCE hesapla (imputation sonrasi NaN kalmaz)
    df["spo2_missing"]  = df["spo2"].isna().astype(int)
    df["pain_missing"]  = df["pain_scale"].isna().astype(int)

    # SBP ve HR sayisallastir (imputation oncesi object olabilir)
    sbp = pd.to_numeric(df.get("sbp", np.nan), errors="coerce").fillna(120)
    dbp = pd.to_numeric(df.get("dbp", np.nan), errors="coerce").fillna(80)
    hr  = pd.to_numeric(df.get("heart_rate", np.nan), errors="coerce").fillna(80)

    df["shock_index"]    = (hr / sbp.replace(0, np.nan)).fillna(0.67)
    df["pulse_pressure"] = sbp - dbp
    df["map"]            = dbp + (sbp - dbp) / 3.0

    logger.info("Feature engineering tamamlandi: shock_index, pulse_pressure, "
                "map, spo2_missing, pain_missing eklendi.")
    return df


# ---------------------------------------------------------------------------
# Model eğitimi
# ---------------------------------------------------------------------------

def train_models(
    df: pd.DataFrame,
) -> tuple:
    """
    Uc model egitir: LogisticRegression (baseline), RandomForest ve XGBoost (birincil).

    Iyilestirmeler:
    - Feature engineering: shock_index, pulse_pressure, MAP, eksik bayragi
    - SMOTE: KTAS-1/2 azinlik siniflarini dengeler
    - XGBoost: sample_weight ile kritik sinif odaklanmasi
    - KTAS 1-2 recall'a ozellikle dikkat edilir (hayati onem).

    Parametreler
    ------------
    df : pd.DataFrame
        load_ktas() ile yuklenip add_engineered_features() uygulanmis veri.

    Dondurur
    --------
    tuple
        (primary_model, lr_pipeline, encoders, feature_names,
         shap_explainer, imputer, is_xgb)
    """
    logger.info("=" * 60)
    logger.info("MODEL EGITIMI BASLIYOR")
    logger.info("=" * 60)

    # Feature engineering uygula
    df = add_engineered_features(df)

    # Hedef degisken
    y = df["ktas_level"].values

    # On isleme
    X, feature_names, encoders = preprocess(df, fit=True)
    logger.info(f"Ozellik sayisi: {len(feature_names)} | Ornek sayisi: {len(X)}")
    logger.info(f"Ozellikler: {feature_names}")

    # KTAS dagilimi
    unique, counts = np.unique(y, return_counts=True)
    logger.info("KTAS dagilimi:")
    for ktas, cnt in zip(unique, counts):
        logger.info(f"  KTAS {ktas} ({KTAS_LEVEL_NAMES.get(ktas, '?')}): {cnt} hasta")


    # Train/test ayrımı (stratified)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    logger.info(f"Eğitim seti: {len(X_train)}, Test seti: {len(X_test)}")

    # ----------------------------------------------------------------
    # (a) Baseline: LogisticRegression
    # ----------------------------------------------------------------
    logger.info("\n--- (a) LogisticRegression (Baseline) ---")
    lr_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=42,
            multi_class="multinomial",
            solver="lbfgs",
        )),
    ])
    lr_pipeline.fit(X_train, y_train)
    y_pred_lr = lr_pipeline.predict(X_test)

    logger.info("LogisticRegression — Classification Report:")
    report_lr = classification_report(
        y_test, y_pred_lr,
        target_names=[f"KTAS-{i}" for i in sorted(np.unique(y))],
    )
    print(report_lr)

    # ----------------------------------------------------------------
    # (b) RandomForestClassifier
    # ----------------------------------------------------------------
    logger.info("\n--- (b) RandomForestClassifier ---")
    rf_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced",
            max_depth=12,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )),
    ])
    rf_pipeline.fit(X_train, y_train)
    y_pred_rf = rf_pipeline.predict(X_test)

    logger.info("RandomForestClassifier (tuned) — Classification Report:")
    print(classification_report(
        y_test, y_pred_rf,
        target_names=[f"KTAS-{i}" for i in sorted(np.unique(y))],
    ))

    # ----------------------------------------------------------------
    # (c) XGBoost — Birincil model (feature engineering + SMOTE ile)
    # ----------------------------------------------------------------
    logger.info("\n--- (c) XGBoost (Birincil Model) ---")

    # SMOTE: KTAS-1 ve KTAS-2 azinlik siniflarini dengele
    imp_for_smote = SimpleImputer(strategy="median")
    X_train_imp = imp_for_smote.fit_transform(X_train)
    X_test_imp  = imp_for_smote.transform(X_test)

    if _SMOTE_AVAILABLE:
        try:
            # k_neighbors: en kucuk sinif boyutundan kucuk olmali
            min_class_count = min(np.bincount(y_train)[1:])  # 0-indexed, KTAS 1-5
            k_neighbors = min(5, min_class_count - 1) if min_class_count > 1 else 1
            smote = SMOTE(random_state=42, k_neighbors=k_neighbors)
            X_train_res, y_train_res = smote.fit_resample(X_train_imp, y_train)
            logger.info(f"SMOTE uygulandı: {len(X_train)} → {len(X_train_res)} ornek")
        except Exception as e:
            logger.warning(f"SMOTE basarisiz ({e}), orijinal veri kullaniliyor.")
            X_train_res, y_train_res = X_train_imp, y_train
    else:
        logger.warning("imbalanced-learn yuklu degil, SMOTE atlanıyor.")
        X_train_res, y_train_res = X_train_imp, y_train

    if _XGB_AVAILABLE:
        # Sinif agirlikları: KTAS-1 en kritik, daha yuksek agirlik
        classes = np.unique(y_train)
        class_counts = np.bincount(y_train)[classes]
        max_count = class_counts.max()
        sample_weights = np.array([max_count / class_counts[np.where(classes == cls)[0][0]]
                                   for cls in y_train_res])

        xgb_clf = XGBClassifier(
            n_estimators=500,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            gamma=0.1,
            reg_alpha=0.1,
            reg_lambda=1.0,
            use_label_encoder=False,
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )
        # XGBoost 0-indexed sinif etiketleri bekler: KTAS 1-5 → 0-4
        y_train_xgb = y_train_res - 1
        y_test_xgb  = y_test - 1

        xgb_clf.fit(
            X_train_res, y_train_xgb,
            sample_weight=sample_weights,
            eval_set=[(X_test_imp, y_test_xgb)],
            verbose=False,
        )
        y_pred_xgb_raw = xgb_clf.predict(X_test_imp)
        y_pred_xgb = y_pred_xgb_raw + 1   # 0-4 → 1-5

        logger.info("XGBoost — Classification Report:")
        print(classification_report(
            y_test, y_pred_xgb,
            target_names=[f"KTAS-{i}" for i in sorted(np.unique(y))],
        ))
        primary_model = xgb_clf
        y_pred_primary = y_pred_xgb
        is_xgb = True
    else:
        logger.info("XGBoost mevcut degil; RF birincil model olarak kullanilacak.")
        primary_model  = rf_pipeline.named_steps["clf"]
        y_pred_primary = y_pred_rf
        is_xgb = False

    # ----------------------------------------------------------------
    # KTAS 1-2 recall karsilastirmasi (kritik metrik)
    # ----------------------------------------------------------------
    from sklearn.metrics import recall_score
    logger.info("\n--- Kritik Metrik: KTAS 1-2 Recall Karsilastirmasi ---")
    for ktas in [1, 2]:
        if ktas in np.unique(y):
            if (y_test == ktas).sum() > 0:
                r_lr  = recall_score(y_test == ktas, y_pred_lr == ktas, zero_division=0)
                r_rf  = recall_score(y_test == ktas, y_pred_rf == ktas, zero_division=0)
                r_pri = recall_score(y_test == ktas, y_pred_primary == ktas, zero_division=0)
                model_lbl = "XGB" if is_xgb else "RF "
                logger.info(f"  KTAS-{ktas} Recall → LR:{r_lr:.3f} | RF:{r_rf:.3f} | {model_lbl}:{r_pri:.3f}")

    # ----------------------------------------------------------------
    # Feature importances (birincil modelden)
    # ----------------------------------------------------------------
    if is_xgb:
        importances = xgb_clf.feature_importances_
    else:
        importances = rf_pipeline.named_steps["clf"].feature_importances_

    sorted_idx = np.argsort(importances)[::-1]
    logger.info("\n--- Feature Importances (Birincil Model) ---")
    for idx in sorted_idx[:12]:
        display = FEATURE_DISPLAY_NAMES.get(feature_names[idx], feature_names[idx])
        logger.info(f"  {display:<32}: {importances[idx]:.4f}")

    # ----------------------------------------------------------------
    # SHAP acıklanabilirlik katmani
    # ----------------------------------------------------------------
    logger.info("\nSHAP TreeExplainer hazırlanıyor...")
    try:
        if is_xgb:
            shap_explainer = shap.TreeExplainer(xgb_clf)
        else:
            shap_explainer = shap.TreeExplainer(rf_pipeline.named_steps["clf"])
        logger.info("SHAP TreeExplainer hazir.")
    except Exception as e:
        logger.warning(f"SHAP olusturulamadi: {e} — Sahte explainer kullanilacak.")
        shap_explainer = None

    # Imputer'i model bundle'ina gömecegiz (XGBoost pipeline kullanmiyor)
    return (primary_model, lr_pipeline, encoders, feature_names,
            shap_explainer, imp_for_smote, is_xgb)



# ---------------------------------------------------------------------------
# Tahmin + SHAP açıklaması
# ---------------------------------------------------------------------------

def predict_with_explanation(
    input_dict: dict,
    model_bundle: dict | None = None,
) -> dict:
    """
    Yeni bir hasta için KTAS tahmini yapar ve Türkçe açıklama üretir.

    Bu fonksiyon kural motorunu ÇAĞIRMAZ; kural kontrolü dışarıda yapılmalıdır.
    (Önce shared.rules.check_red_flags() çalıştırın.)

    Parametreler
    ------------
    input_dict : dict
        Hasta özellikleri sözlüğü. Örnek:
        {
            "age": 45, "gender": "erkek",
            "sbp": 90, "heart_rate": 115, "spo2": 92,
            "pain_scale": 7, "arrival_mode": "ambulans"
        }
    model_bundle : dict | None
        Eğitilmiş model paketi. None ise diskten yüklenir.

    Döndürür
    --------
    dict
        {
            "ktas_level": int,           # Tahmin edilen KTAS (1-5)
            "ktas_name": str,            # Türkçe KTAS açıklaması
            "confidence": float,         # Tahmin güveni (0-1)
            "explanation": str,          # Türkçe kısa açıklama
            "feature_contributions": dict # Özellik katkıları (isim: değer)
            "probabilities": dict        # Her KTAS için olasılıklar
        }

    Örnek
    -----
    >>> result = predict_with_explanation({"age": 45, "spo2": 93, "heart_rate": 112})
    >>> print(result["explanation"])
    'Nabız (112 atım/dk) ve SpO2 (%93) kombinasyonu nedeniyle öncelik yükseltildi.'
    """
    if model_bundle is None:
        model_bundle = load_model_bundle()

    primary_model = model_bundle["rf_pipeline"]  # XGB veya RF (geriye uyumluluk)
    encoders: dict = model_bundle["encoders"]
    feature_names: list[str] = model_bundle["feature_names"]
    shap_explainer = model_bundle["shap_explainer"]
    imputer: SimpleImputer = model_bundle.get("imputer")
    is_xgb: bool = model_bundle.get("is_xgb", False)

    # Girdiyi DataFrame'e cevir
    df_input = pd.DataFrame([input_dict])

    # Feature engineering uygula (egitimde uygulananla ayni)
    try:
        df_input = add_engineered_features(df_input)
    except Exception:
        pass  # Eski model bundle'larinda engineering olmayabilir

    # Model'in beklediği ama input_dict'te olmayan sutunlari NaN ile doldur
    for feat in feature_names:
        if feat not in df_input.columns:
            df_input[feat] = np.nan

    # On isleme (encoder mevcut, fit=False)
    X, _, _ = preprocess(df_input, feature_cols=feature_names,
                         encoders=encoders, fit=False)

    # Imputation
    if imputer is not None:
        X_imp = imputer.transform(X)
    elif hasattr(primary_model, "named_steps"):
        X_imp = primary_model.named_steps["imputer"].transform(X)
    else:
        X_imp = X

    # Tahmin
    if is_xgb:
        # XGBoost: 0-indexed sinif etiketleri
        pred_class_raw = primary_model.predict(X_imp)[0]
        pred_class = int(pred_class_raw) + 1   # 0-4 → 1-5
        pred_proba_raw = primary_model.predict_proba(X_imp)[0]
        classes_0indexed = np.arange(len(pred_proba_raw))
        classes = classes_0indexed + 1  # 0-4 → 1-5
        pred_proba = pred_proba_raw
    else:
        clf = primary_model.named_steps["clf"] if hasattr(primary_model, "named_steps") else primary_model
        pred_class = int(clf.predict(X_imp)[0])
        pred_proba = clf.predict_proba(X_imp)[0]
        classes = clf.classes_

    # Olasilik sozlugu
    prob_dict = {int(c): float(p) for c, p in zip(classes, pred_proba)}
    confidence = float(max(pred_proba))

    # ----------------------------------------------------------------
    # SHAP degerleri → ozellik katkılari
    # ----------------------------------------------------------------
    contributions = {}
    if shap_explainer is not None:
        try:
            shap_values = shap_explainer.shap_values(X_imp)
            if is_xgb:
                class_idx = int(pred_class) - 1  # 1-5 → 0-4
            else:
                class_idx = list(classes).index(pred_class)

            if isinstance(shap_values, list):
                sv = shap_values[class_idx][0]
            elif shap_values.ndim == 3:
                sv = shap_values[0, :, class_idx]
            else:
                sv = shap_values[0]

            contributions = {
                feature_names[i]: float(sv[i]) for i in range(len(feature_names))
            }
        except Exception as e:
            logger.warning(f"SHAP hesaplanamadi: {e}")

    # En onemli 3 ozellik (mutlak SHAP degerine gore)
    if contributions:
        top_features = sorted(contributions.items(),
                              key=lambda x: abs(x[1]), reverse=True)[:3]
    else:
        # SHAP yoksa feature importance'tan yedek
        top_features = []

    # ----------------------------------------------------------------
    # Turkce aciklama uretimi
    # ----------------------------------------------------------------
    explanation = _build_turkish_explanation(
        pred_class, input_dict, top_features, confidence
    )

    return {
        "ktas_level": int(pred_class),
        "ktas_name": KTAS_LEVEL_NAMES.get(int(pred_class), "Bilinmiyor"),
        "confidence": confidence,
        "explanation": explanation,
        "feature_contributions": contributions,
        "probabilities": prob_dict,
    }



def _build_turkish_explanation(
    ktas_level: int,
    input_dict: dict,
    top_features: list[tuple[str, float]],
    confidence: float,
) -> str:
    """
    En önemli özelliklere dayalı Türkçe, kısa açıklama cümlesi üretir.

    Parametreler
    ------------
    ktas_level : int
        Tahmin edilen KTAS seviyesi.
    input_dict : dict
        Orijinal hasta özellikleri.
    top_features : list[tuple[str, float]]
        En önemli (özellik adı, SHAP katkısı) çiftleri.
    confidence : float
        Tahmin güveni.

    Döndürür
    --------
    str
        Türkçe kısa açıklama.
    """
    parts = []
    for feat_name, shap_val in top_features:
        display = FEATURE_DISPLAY_NAMES.get(feat_name, feat_name)
        raw_val = input_dict.get(feat_name)
        unit = FEATURE_UNIT_MAP.get(feat_name, "")

        if raw_val is None:
            continue

        direction = "yükseltici" if shap_val > 0 else "düşürücü"

        # Sayısal değerleri biçimlendir
        if isinstance(raw_val, float):
            formatted_val = f"{raw_val:.1f}"
        else:
            formatted_val = str(raw_val)

        # Özel mesajlar — kritik vital bulgular için
        if feat_name == "spo2" and isinstance(raw_val, (int, float)) and raw_val < 94:
            parts.append(f"SpO2 (%{formatted_val}) düşük oksijen satürasyonu")
        elif feat_name == "heart_rate" and isinstance(raw_val, (int, float)) and raw_val > 100:
            parts.append(f"Nabız ({formatted_val} atım/dk) taşikardi")
        elif feat_name == "sbp" and isinstance(raw_val, (int, float)) and raw_val < 100:
            parts.append(f"Sistolik tansiyon ({formatted_val} mmHg) hipotansiyon")
        elif feat_name == "pain_scale" and isinstance(raw_val, (int, float)) and raw_val >= 7:
            parts.append(f"Yüksek ağrı skoru ({formatted_val}/10)")
        elif feat_name == "gcs" and isinstance(raw_val, (int, float)) and raw_val <= 12:
            parts.append(f"GCS ({formatted_val}) bilinç baskılanması")
        else:
            parts.append(f"{display} ({formatted_val}{(' ' + unit) if unit else ''})")

    if not parts:
        ktas_name = KTAS_LEVEL_NAMES.get(ktas_level, "")
        return f"Genel klinik tablo değerlendirilerek KTAS-{ktas_level} ({ktas_name}) önerildi."

    ktas_name = KTAS_LEVEL_NAMES.get(ktas_level, "")
    conf_pct = int(confidence * 100)

    if ktas_level <= 2:
        action = "nedeniyle öncelik yükseltildi"
    elif ktas_level == 3:
        action = "dikkate alınarak orta öncelik atandı"
    else:
        action = "göz önünde bulundurularak rutin triaj uygulandı"

    if len(parts) == 1:
        feature_text = parts[0]
    elif len(parts) == 2:
        feature_text = f"{parts[0]} ve {parts[1]} kombinasyonu"
    else:
        feature_text = f"{parts[0]}, {parts[1]} ve {parts[2]} kombinasyonu"

    return (
        f"{feature_text.capitalize()} {action}. "
        f"(Model güveni: %{conf_pct})"
    )


# ---------------------------------------------------------------------------
# Model kayıt / yükleme
# ---------------------------------------------------------------------------

def save_model_bundle(
    primary_model,
    lr_pipeline: Pipeline,
    encoders: dict,
    feature_names: list[str],
    shap_explainer,
    imputer: SimpleImputer,
    is_xgb: bool,
) -> None:
    """
    Egitilmis modeli ve yardimci bilesenleri diske kaydeder.

    Birincil model (XGBoost/RF) → model/triage_model.pkl
    Baseline model (LR)         → model/baseline_model.pkl
    """
    bundle = {
        "rf_pipeline": primary_model,  # Geriye uyumluluk icin ayni anahtar
        "encoders":     encoders,
        "feature_names": feature_names,
        "shap_explainer": shap_explainer,
        "imputer":       imputer,
        "is_xgb":        is_xgb,
    }
    joblib.dump(bundle, PRIMARY_MODEL_PATH)
    joblib.dump(lr_pipeline, BASELINE_MODEL_PATH)

    logger.info(f"Birincil model kaydedildi: {PRIMARY_MODEL_PATH}")
    logger.info(f"Baseline model kaydedildi: {BASELINE_MODEL_PATH}")



def load_model_bundle(model_path: Path | str | None = None) -> dict:
    """
    Daha önce kaydedilen model paketini yükler.

    Parametreler
    ------------
    model_path : Path | str | None
        Model dosyasının yolu. None ise varsayılan (model/triage_model.pkl).

    Döndürür
    --------
    dict
        predict_with_explanation() için gereken model paketi.
    """
    path = Path(model_path) if model_path else PRIMARY_MODEL_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Model dosyası bulunamadı: {path}\n"
            f"Lütfen önce 'python model/train_model.py' çalıştırın."
        )
    bundle = joblib.load(path)
    logger.info(f"Model yüklendi: {path}")
    return bundle


# ---------------------------------------------------------------------------
# Ana giriş noktası
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Veri yükleniyor...")
    try:
        df = load_ktas()
    except FileNotFoundError:
        logger.error(
            "KTAS veri seti bulunamadı!\n"
            "Lütfen data/ klasörüne .xlsx veya .csv formatında KTAS veri setini koyun.\n"
            "Kaynak önerisi: https://www.kaggle.com/datasets/llncss/ktas-dataset"
        )
        sys.exit(1)

    logger.info(f"Veri yüklendi: {df.shape[0]} satır, {df.shape[1]} sütun")

    # Modelleri egit
    primary_model, lr_pipeline, encoders, feature_names, shap_explainer, imputer, is_xgb = train_models(df)

    # Kaydet
    save_model_bundle(primary_model, lr_pipeline, encoders, feature_names,
                      shap_explainer, imputer, is_xgb)

    # ----------------------------------------------------------------
    # Örnek tahmin testi
    # ----------------------------------------------------------------
    logger.info("\n--- Ornek Tahmin Testi ---")
    test_patient = {
        "age":          55,
        "gender":       1,        # 1=Erkek (sayisal)
        "arrival_mode": 2,        # 2=Ambulans (sayisal)
        "injury":       2,        # 2=Hayir
        "has_pain":     1,
        "pain_scale":   8.0,
        "mental_status": 1,
        "sbp":          88.0,
        "dbp":          60.0,
        "heart_rate":   112.0,
        "resp_rate":    24.0,
        "temperature":  37.8,
        "spo2":         93.0,
        "patients_per_hour": 5,
    }

    try:
        bundle = load_model_bundle()
        result = predict_with_explanation(test_patient, bundle)
        print(f"\n{'='*55}")
        print(f"ÖRNEK HASTA TAHMİNİ")
        print(f"{'='*55}")
        print(f"KTAS Seviyesi : {result['ktas_level']} — {result['ktas_name']}")
        print(f"Güven         : %{result['confidence']*100:.1f}")
        print(f"Açıklama      : {result['explanation']}")
        print(f"\nOlasılıklar:")
        for ktas, prob in sorted(result["probabilities"].items()):
            bar = "█" * int(prob * 30)
            print(f"  KTAS-{ktas}: {bar:<30} %{prob*100:.1f}")
    except Exception as e:
        logger.warning(f"Örnek tahmin çalıştırılamadı: {e}")

    logger.info("\n✅ Model eğitimi ve kayıt tamamlandı.")
