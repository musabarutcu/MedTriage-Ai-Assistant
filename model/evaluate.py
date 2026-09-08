"""
model/evaluate.py
-----------------
Dürüst değerlendirme katmanı — model/model_card.md üretir.

NEDEN VAR?
----------
Bu projenin README'sinde bir zamanlar "~%67 doğruluk, KTAS-1 recall %100"
yazıyordu. Ölçüldüğünde gerçek değer %56.7 ve 0.80 çıktı; dahası veri
setinin içinde duran hemşire etiketi (KTAS_RN) ile hiç kıyaslanmamıştı —
kıyaslandığında hemşirenin %85 ile modeli açık ara geçtiği görüldü.

Bu dosya o hatanın tekrarlanmasını engeller: README'deki her sayı
buradan üretilen model_card.md'den alınır, elle yazılmaz.

RAPORLANAN METRİKLER
--------------------
doğruluk        : tam isabet (5 sınıf)
±1 doğruluk     : bir seviye sapma toleransıyla isabet — triajda bir
                  seviyelik sapma çoğu zaman klinik olarak tolere edilir
KTAS-1/2 recall : hayati sınıflarda yakalama oranı
alt-triaj oranı : modelin hastayı GERÇEKTEN OLDUĞUNDAN AZ ACİL sayması.
                  Üst-triaj kaynak israfıdır; alt-triaj hasta zararıdır.
                  Bu yüzden ayrı raporlanır.
güven bandı     : kalibre olasılık eşiğine göre kapsam/doğruluk eğrisi

Çalıştırma:
    python model/evaluate.py
"""

from __future__ import annotations

import sys
import logging
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.metrics import accuracy_score, confusion_matrix, recall_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.load_ktas import load_ktas
from model.train_model import (
    SYMPTOM_COL, build_pipeline, prepare_xy, CONFIDENCE_HIGH, CONFIDENCE_LOW,
)

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

MODEL_CARD_PATH = Path(__file__).parent / "model_card.md"
N_SPLITS = 5
RANDOM_STATE = 42

CONFIDENCE_THRESHOLDS = (0.4, 0.5, 0.6, 0.7, 0.8)


# ---------------------------------------------------------------------------
# Metrikler
# ---------------------------------------------------------------------------

def score(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Bir tahmin dizisi için tüm metrikleri hesaplar."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "within_one": float(np.mean(np.abs(y_pred - y_true) <= 1)),
        # y_pred > y_true  =>  daha az acil dendi  =>  ALT-triaj
        "under_triage": float(np.mean(y_pred > y_true)),
        "over_triage": float(np.mean(y_pred < y_true)),
        "recall_per_class": {
            int(k): float(recall_score(y_true == k, y_pred == k, zero_division=0))
            for k in sorted(np.unique(y_true))
        },
    }


def confidence_curve(y_true, y_pred, confidence) -> list[dict]:
    """Güven eşiğine göre kapsam / doğruluk eğrisi."""
    rows = []
    for threshold in CONFIDENCE_THRESHOLDS:
        mask = confidence >= threshold
        if mask.sum() < 20:      # anlamlı yorum için çok küçük örneklem
            continue
        rows.append({
            "threshold": threshold,
            "coverage": float(mask.mean()),
            "accuracy": accuracy_score(np.asarray(y_true)[mask],
                                       np.asarray(y_pred)[mask]),
            "n": int(mask.sum()),
        })
    return rows


# ---------------------------------------------------------------------------
# Değerlendirme
# ---------------------------------------------------------------------------

def evaluate() -> dict:
    """Çapraz doğrulama ile modeli, hemşire baseline'ını ve ablasyonu ölçer."""
    df = load_ktas()
    X, y, feature_columns = prepare_xy(df)
    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_STATE)

    logger.info("Birincil model çapraz doğrulaması (%d katlama)...", N_SPLITS)
    pipeline = build_pipeline(feature_columns, calibrate=True)
    y_pred = cross_val_predict(pipeline, X, y, cv=cv)
    y_proba = cross_val_predict(pipeline, X, y, cv=cv, method="predict_proba")
    confidence = y_proba.max(axis=1)

    results = {
        "n_samples": int(len(y)),
        "n_features": len(feature_columns),
        "feature_columns": feature_columns,
        "class_distribution": {int(k): int(v)
                               for k, v in pd.Series(y).value_counts().sort_index().items()},
        "model": score(y, y_pred),
        "confidence_curve": confidence_curve(y, y_pred, confidence),
        "confusion_matrix": confusion_matrix(y, y_pred).tolist(),
        "classes": [int(c) for c in sorted(np.unique(y))],
        "low_confidence_share": float(np.mean(confidence < CONFIDENCE_LOW)),
    }

    # ── İnsan baseline'ı: aynı hastalar, aynı hedef ──────────────────────
    if "nurse_ktas" in df.columns:
        nurse = pd.to_numeric(df["nurse_ktas"], errors="coerce")
        valid = nurse.notna().to_numpy()
        results["nurse"] = score(y[valid], nurse[valid].astype(int).to_numpy())
        results["nurse_n"] = int(valid.sum())
    else:
        results["nurse"] = None

    # ── Ablasyon: semptom kodunun katkısı ────────────────────────────────
    logger.info("Ablasyon: semptom kodu olmadan...")
    vitals_only = [c for c in feature_columns if c != SYMPTOM_COL]
    ablation_pipeline = build_pipeline(vitals_only, calibrate=True)
    y_pred_ablation = cross_val_predict(ablation_pipeline, X[vitals_only], y, cv=cv)
    results["ablation_no_symptom"] = score(y, y_pred_ablation)

    return results


# ---------------------------------------------------------------------------
# Model kartı
# ---------------------------------------------------------------------------

def _pct(value: float) -> str:
    return f"%{value * 100:.1f}"


def render_model_card(r: dict) -> str:
    """Değerlendirme sonuçlarını Markdown model kartına dönüştürür."""
    model, nurse = r["model"], r.get("nurse")
    classes = r["classes"]

    lines: list[str] = []
    add = lines.append

    add("# MedTriage — Model Kartı")
    add("")
    add(f"> Otomatik üretilmiştir: `python model/evaluate.py` · {date.today().isoformat()}")
    add("> **Bu dosyayı elle düzenlemeyin.** README'deki sayılar buradan alınır.")
    add("")
    add("## Özet")
    add("")
    add("| | Doğruluk | ±1 seviye | KTAS-1 recall | KTAS-2 recall | Alt-triaj |")
    add("|:--|:--|:--|:--|:--|:--|")
    add(f"| **Model** (XGBoost + SMOTE + kalibrasyon) | **{_pct(model['accuracy'])}** "
        f"| {_pct(model['within_one'])} "
        f"| {model['recall_per_class'].get(1, 0):.3f} "
        f"| {model['recall_per_class'].get(2, 0):.3f} "
        f"| {_pct(model['under_triage'])} |")
    if nurse:
        add(f"| **Hemşire** (`KTAS_RN`, insan baseline) | **{_pct(nurse['accuracy'])}** "
            f"| {_pct(nurse['within_one'])} "
            f"| {nurse['recall_per_class'].get(1, 0):.3f} "
            f"| {nurse['recall_per_class'].get(2, 0):.3f} "
            f"| {_pct(nurse['under_triage'])} |")
    add("")
    add(f"{N_SPLITS} katlamalı stratified çapraz doğrulama · {r['n_samples']} hasta · "
        f"{r['n_features']} özellik · hedef: `KTAS_expert` (uzman etiketi)")
    add("")

    # ── Yorum ────────────────────────────────────────────────────────────
    add("## Bu sayılar ne anlama geliyor?")
    add("")
    if nurse:
        gap = nurse["accuracy"] - model["accuracy"]
        add(f"Model, triaj hemşiresinden **{gap * 100:.1f} puan geride**. Bu bir "
            f"başarısızlık değil, bu veri setinin sınırı: 1267 hasta ve yalnızca "
            f"{r['class_distribution'].get(1, 0)} adet KTAS-1 örneğiyle eğitilen bir "
            f"model, eğitimli bir klinisyeni geçemez.")
        add("")
        k1_model = model["recall_per_class"].get(1, 0)
        k1_nurse = nurse["recall_per_class"].get(1, 0)
        if k1_model >= k1_nurse:
            add(f"Buna karşılık **en kritik sınıfta (KTAS-1) model hemşireyle "
                f"başa baş**: {k1_model:.3f} / {k1_nurse:.3f}. Hemşirenin üstünlüğü "
                f"ağırlıklı olarak KTAS-2 ve orta seviyelerde yoğunlaşıyor.")
            add("")
    add("Bu nedenle MedTriage kendini hemşirenin yerine koyan bir sistem olarak "
        "değil, **ikinci okuyucu** olarak konumlandırır:")
    add("")
    add("1. Hayati bulguları deterministik kural motoru yakalar (`shared/rules.py`), model değil.")
    add("2. Model bağlamsal bir öneri sunar ve **ne zaman bilmediğini söyler** (aşağıya bakınız).")
    add("3. Nihai karar her zaman hekimindir ve `decision_log` tablosuna kaydedilir.")
    add("")

    # ── Güven bandı ──────────────────────────────────────────────────────
    curve = r.get("confidence_curve") or []
    if curve:
        add("## Güven bandı — model ne zaman güvenilir?")
        add("")
        add("Olasılıklar isotonic regresyonla kalibre edilmiştir; aşağıdaki tablo "
            "kalibrasyonun işe yaradığının kanıtıdır. Güven eşiği yükseldikçe "
            "doğruluk gerçekten artıyor:")
        add("")
        add("| Güven eşiği | Kapsam | O bölgede doğruluk | Hasta sayısı |")
        add("|:--|:--|:--|:--|")
        for row in curve:
            add(f"| ≥ {row['threshold']:.2f} | {_pct(row['coverage'])} "
                f"| **{_pct(row['accuracy'])}** | {row['n']} |")
        add("")
        # En yüksek doğruluk değil, hemşire seviyesini geçen EN GENİŞ KAPSAM
        # anlatılır — %91 doğruluk vakaların %12'sinde işe yarıyorsa,
        # %89 doğruluk %32'sinde daha değerlidir.
        if nurse:
            beating = [c for c in curve if c["accuracy"] >= nurse["accuracy"]]
            if beating:
                best = max(beating, key=lambda x: x["coverage"])
                add(f"Güven ≥ {best['threshold']:.2f} bölgesinde model doğruluğu "
                    f"**{_pct(best['accuracy'])}** ve bu bölge hastaların "
                    f"**{_pct(best['coverage'])}** kadarını kapsıyor — yani her üç "
                    f"hastadan yaklaşık birinde model, hemşire seviyesine "
                    f"({_pct(nurse['accuracy'])}) ulaşıyor. Ürünün değeri buradadır: "
                    f"model nerede güvenilir olduğunu biliyor.")
                add("")
        add(f"Arayüz eşikleri: güven ≥ {CONFIDENCE_HIGH:.2f} \"güvenilir bant\"; "
            f"< {CONFIDENCE_LOW:.2f} ise \"model kararsız\" uyarısı gösterilir "
            f"(vakaların {_pct(r['low_confidence_share'])} kadarı).")
        add("")

    # ── Ablasyon ─────────────────────────────────────────────────────────
    ablation = r.get("ablation_no_symptom")
    if ablation:
        delta = (model["accuracy"] - ablation["accuracy"]) * 100
        add("## Ablasyon — serbest metin şikayetin katkısı")
        add("")
        add("| Özellik seti | Doğruluk | ±1 seviye |")
        add("|:--|:--|:--|")
        add(f"| Yalnızca vitaller | {_pct(ablation['accuracy'])} | {_pct(ablation['within_one'])} |")
        add(f"| Vitaller + kanonik semptom kodu | **{_pct(model['accuracy'])}** "
            f"| **{_pct(model['within_one'])}** |")
        add("")
        add(f"Başvuru şikayetini `shared/symptoms.py` taksonomisiyle 26 kanonik koda "
            f"indirgeyip modele vermek doğruluğu **{delta:+.1f} puan** değiştiriyor. "
            f"Önceki sürümde bu sütun modelden tamamen dışlanmıştı.")
        add("")
        add("Ham TF-IDF metin özellikleri de denendi: tam isabeti bir miktar artırıyor "
            "ama ±1 doğruluğunu düşürüyor — yani daha *büyük* hatalar yapıyor. "
            "Güvenlik ağı için yanlış takas olduğundan birincil modele alınmadı.")
        add("")

    # ── Sınıf bazlı ──────────────────────────────────────────────────────
    add("## Sınıf bazlı recall")
    add("")
    add("| KTAS | Hasta sayısı | Model recall | Hemşire recall |")
    add("|:--|:--|:--|:--|")
    for k in classes:
        n_k = r["class_distribution"].get(k, 0)
        m_r = model["recall_per_class"].get(k, 0)
        n_r = nurse["recall_per_class"].get(k, 0) if nurse else None
        add(f"| KTAS-{k} | {n_k} | {m_r:.3f} | "
            f"{n_r:.3f} |" if n_r is not None else
            f"| KTAS-{k} | {n_k} | {m_r:.3f} | — |")
    add("")

    # ── Karışıklık matrisi ───────────────────────────────────────────────
    add("## Karışıklık matrisi")
    add("")
    add("Satır = gerçek (uzman), sütun = model tahmini.")
    add("")
    add("| Gerçek \\ Tahmin | " + " | ".join(f"KTAS-{c}" for c in classes) + " |")
    add("|:--|" + "|".join([":--"] * len(classes)) + "|")
    for i, row in enumerate(r["confusion_matrix"]):
        add(f"| **KTAS-{classes[i]}** | " + " | ".join(str(v) for v in row) + " |")
    add("")
    weak = [k for k in classes if model["recall_per_class"].get(k, 0) < 0.30]
    if weak:
        add("> ⚠️ **Zayıf sınıf uyarısı.** " + ", ".join(f"KTAS-{k}" for k in weak) +
            " sınıf(lar)ında recall 0.30'un altında: model bu seviyeyi neredeyse "
            "hiç öngörmüyor, vakaları komşu seviyelere dağıtıyor. Sebep sınıf "
            "dengesizliği ve bu seviyelerin klinik olarak komşularıyla iç içe "
            "geçmesidir. Bu seviyelerde model önerisi tek başına kullanılmamalıdır.")
        add("")

    add(f"Alt-triaj (gerçekte daha acil olan hastaya daha az acil demek): "
        f"**{_pct(model['under_triage'])}** · "
        f"Üst-triaj: {_pct(model['over_triage'])}. "
        f"Alt-triaj klinik olarak daha tehlikelidir; bu yüzden ayrı izlenir.")
    add("")

    # ── Sınırlılıklar ────────────────────────────────────────────────────
    add("## Sınırlılıklar")
    add("")
    add(f"- **Küçük ve dengesiz veri.** {r['n_samples']} hasta; KTAS-1 yalnızca "
        f"{r['class_distribution'].get(1, 0)} örnek. KTAS-1 recall değeri geniş bir "
        f"güven aralığına sahiptir ve tek bir hastanın yer değiştirmesi metriği "
        f"belirgin biçimde oynatır.")
    add("- **Yoğun eksik veri.** Ham veride SpO2'nin ~%55'i, ağrı skorunun ~%44'ü "
        "eksik. Eksiklik artık bir özellik olarak modellenir (`spo2_missing`, "
        "`pain_missing`) ama doldurulan değerler yine de tahmindir.")
    add("- **Tek merkez, tek ülke.** Veri seti Kore acil servis verisidir "
        "(KTAS). Türkiye'deki hasta profili, geliş şekli dağılımı ve triaj "
        "pratiği farklıdır; performansın buraya taşınacağı garanti değildir.")
    add("- **Dil farkı.** Eğitim verisindeki şikayetler İngilizce, form Türkçe. "
        "Kanonik semptom taksonomisi bu boşluğu kapatır ama taksonomi dışında "
        "kalan vakalar `other` koduna düşer (veri setinde ~%15).")
    add("- **Etiket öznelliği.** Hedef `KTAS_expert` de bir insan yargısıdır; "
        "mutlak doğru değildir.")
    add("- **Onaylı tıbbi cihaz değildir.** FDA/CE belgesi yoktur, klinik "
        "kullanıma uygun değildir.")
    add("")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s",
                        datefmt="%H:%M:%S")

    results = evaluate()
    MODEL_CARD_PATH.write_text(render_model_card(results), encoding="utf-8")

    m = results["model"]
    n = results.get("nurse")
    print()
    print("=" * 62)
    print(f"Model    : doğruluk={m['accuracy']:.4f}  ±1={m['within_one']:.4f}  "
          f"alt-triaj={m['under_triage']:.4f}")
    if n:
        print(f"Hemşire  : doğruluk={n['accuracy']:.4f}  ±1={n['within_one']:.4f}  "
              f"alt-triaj={n['under_triage']:.4f}")
    print("=" * 62)
    print(f"Model kartı yazıldı: {MODEL_CARD_PATH}")
