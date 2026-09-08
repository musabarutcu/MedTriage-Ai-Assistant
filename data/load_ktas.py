"""
data/load_ktas.py
-----------------
KTAS (Korean Triage and Acuity Scale) veri setini yükleyen ve temizleyen modül.
Desteklenen format: .xlsx ve .csv
"""

import re
import sys
import logging
import pandas as pd
import numpy as np
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.symptoms import normalize as normalize_symptom

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sütun adı eşleme sözlüğü
# Ham veri setindeki Türkçe/Korece/tutarsız sütun adlarını standart
# İngilizce snake_case karşılıklarına çevirir.
# Eşleşme: küçük harf + boşluk/özel karakter normalize edildikten sonra aranır.
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {
    # ── ktas_raw.xlsx gerçek sütun adları (öncelikli eşlemeler) ──
    "sex": "gender",
    "age": "age",
    "arrival mode": "arrival_mode",
    "injury": "injury",
    "chief_complain": "chief_complaint",
    "chief complain": "chief_complaint",
    "mental": "mental_status",
    "pain": "has_pain",           # 0/1 flag (ağrı var mı)
    "nrs_pain": "pain_scale",     # Numeric Rating Scale 0-10
    "sbp": "sbp",
    "dbp": "dbp",
    "hr": "heart_rate",
    "rr": "resp_rate",
    "bt": "temperature",          # Body Temperature
    "saturation": "spo2",
    "ktas_rn": "nurse_ktas",
    "ktas_expert": "ktas_level",   # BİRİNCİL HEDEF: uzman triaj etiketi
    "diagnosis in ed": "diagnosis",
    "patients number per hour": "patients_per_hour",
    "length of stay_min": "los_min",
    "ktas duration_min": "ktas_duration_min",
    "error_group": "error_group",
    "mistriage": "mistriage",
    "disposition": "disposition",
    "group": "group",

    # ── Türkçe / alternatif isimler ──
    "yaş": "age",
    "yas": "age",
    "gender": "gender",
    "cinsiyet": "gender",
    "chief complaint": "chief_complaint",
    "chiefcomplaint": "chief_complaint",
    "şikayet": "chief_complaint",
    "sikayet": "chief_complaint",
    "başvuru nedeni": "chief_complaint",
    "basvuru nedeni": "chief_complaint",
    "diagnosis": "diagnosis",
    "tanı": "diagnosis",
    "tani": "diagnosis",
    "systolic": "sbp",
    "sistolik": "sbp",
    "sistolik kan basıncı": "sbp",
    "diastolic": "dbp",
    "diastolik": "dbp",
    "heart rate": "heart_rate",
    "heartrate": "heart_rate",
    "nabız": "heart_rate",
    "nabiz": "heart_rate",
    "pulse": "heart_rate",
    "respiratory rate": "resp_rate",
    "respiratoryrate": "resp_rate",
    "solunum hızı": "resp_rate",
    "solunum hizi": "resp_rate",
    "temperature": "temperature",
    "temp": "temperature",
    "ateş": "temperature",
    "ates": "temperature",
    "spo2": "spo2",
    "oxygen saturation": "spo2",
    "o2 sat": "spo2",
    "oksijen satürasyonu": "spo2",
    "pain scale": "pain_scale",
    "ağrı": "pain_scale",
    "agri": "pain_scale",
    "mental status": "mental_status",
    "mentalstatus": "mental_status",
    "bilinç": "mental_status",
    "bilinc": "mental_status",
    "gcs": "gcs",
    "ktas": "ktas_level",
    "ktas level": "ktas_level",
    "ktas_level": "ktas_level",
    "triage level": "ktas_level",
    "triaj seviyesi": "ktas_level",
    "nurse ktas": "nurse_ktas",
    "nurse_ktas": "nurse_ktas",
    "hemşire ktas": "nurse_ktas",
    "arrivalmode": "arrival_mode",
    "geliş şekli": "arrival_mode",
    "gelis sekli": "arrival_mode",
}

# Sayısal ve kategorik sütunlar (temizlik stratejisi için)
NUMERIC_COLS = [
    "age", "sbp", "dbp", "heart_rate", "resp_rate",
    "temperature", "spo2", "pain_scale", "gcs", "has_pain",
    "ktas_level", "nurse_ktas", "mental_status", "gender",
    "arrival_mode", "injury", "patients_per_hour",
    "los_min", "ktas_duration_min", "error_group", "mistriage",
    "disposition", "group",
]
CATEGORICAL_COLS = ["chief_complaint", "diagnosis"]


def _normalize_colname(name: str) -> str:
    """Ham sütun adını normalleştir: küçük harf, boşlukları koru, özel char sil."""
    name = str(name).lower().strip()
    name = re.sub(r"[^a-z0-9ğüşıöç_ ]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame sütunlarını COLUMN_MAP kullanarak standart isimlere çevirir.
    Eşleşmeyen sütunlar orijinal adlarıyla (snake_case dönüştürülmüş) kalır.
    """
    rename_dict = {}
    for col in df.columns:
        normalized = _normalize_colname(col)
        if normalized in COLUMN_MAP:
            rename_dict[col] = COLUMN_MAP[normalized]
        else:
            # Snake_case'e dönüştür: boşlukları _ ile değiştir
            snake = re.sub(r"[^a-z0-9ğüşıöç_]", "_", normalized)
            snake = re.sub(r"_+", "_", snake).strip("_")
            rename_dict[col] = snake
    return df.rename(columns=rename_dict)


def _determine_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hedef değişkeni (ktas_level) belirler.
    ktas_raw.xlsx'te: KTAS_expert (uzman etiketi) → birincil hedef.
    Yoksa KTAS_RN (hemşire etiketi) → yedek.
    """
    if "ktas_level" in df.columns and df["ktas_level"].notna().sum() > 0:
        logger.info("Hedef degisken: 'ktas_level' (KTAS_expert) kullaniliyor.")
        return df
    elif "nurse_ktas" in df.columns and df["nurse_ktas"].notna().sum() > 0:
        logger.info("'ktas_level' bulunamadi; hedef olarak 'nurse_ktas' (KTAS_RN) kullaniliyor.")
        df["ktas_level"] = df["nurse_ktas"]
        return df
    else:
        raise ValueError(
            "Veri setinde 'ktas_level' veya 'nurse_ktas' sutunu bulunamadi. "
            "Lutfen COLUMN_MAP'e dogru eslemeyi ekleyin."
        )


def _impute_missing(df: pd.DataFrame) -> pd.DataFrame:
    """
    Eksik değerleri doldurur:
    - Sayısal sütunlar → medyan
    - Kategorik sütunlar → mod (en sık değer)
    Her iki adımda ne kadar değer doldurulduğu loglanır.
    """
    for col in df.columns:
        missing = df[col].isna().sum()
        if missing == 0:
            continue

        if col in NUMERIC_COLS or pd.api.types.is_numeric_dtype(df[col]):
            fill_val = df[col].median()
            df[col] = df[col].fillna(fill_val)
            logger.debug(f"  {col}: {missing} eksik değer → medyan ({fill_val:.2f}) ile dolduruldu")
        else:
            mode_series = df[col].mode()
            fill_val = mode_series.iloc[0] if not mode_series.empty else "bilinmiyor"
            df[col] = df[col].fillna(fill_val)
            logger.debug(f"  {col}: {missing} eksik değer → mod ('{fill_val}') ile dolduruldu")

    return df


def _clean_vitals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fizyolojik olarak imkansız değerleri NaN'a çevirir (imputation öncesi çağrılır).
    Kabul edilebilir aralıklar klinik referans değerlere dayanmaktadır.
    """
    ranges = {
        "age":         (0, 120),
        "sbp":         (40, 300),
        "dbp":         (20, 200),
        "heart_rate":  (20, 300),
        "resp_rate":   (4, 60),
        "temperature": (25.0, 45.0),
        "spo2":        (50, 100),
        "pain_scale":  (0, 10),
        "gcs":         (3, 15),
        "ktas_level":  (1, 5),
    }
    for col, (lo, hi) in ranges.items():
        if col in df.columns:
            mask = (df[col] < lo) | (df[col] > hi)
            count = mask.sum()
            if count > 0:
                df.loc[mask, col] = np.nan
                logger.debug(f"  {col}: {count} değer aralık dışı → NaN yapıldı")
    return df


def load_ktas(
    file_path: str | Path | None = None,
    impute: bool = False,
) -> pd.DataFrame:
    """
    KTAS veri setini yükler, sütun adlarını standartlaştırır ve temizler.

    Parametreler
    ------------
    file_path : str | Path | None
        Veri dosyasının yolu (.xlsx veya .csv).
        None verilirse data/ klasöründe ilk .xlsx veya .csv dosyasını arar.

    Döndürür
    --------
    pd.DataFrame
        Temizlenmiş ve standartlaştırılmış DataFrame.
        'ktas_level' sütunu hedef değişkendir (1=en acil, 5=en az acil).

    Örnek
    -----
    >>> df = load_ktas("data/KTAS_Dataset.xlsx")
    >>> df.columns.tolist()
    ['age', 'gender', 'chief_complaint', 'sbp', 'dbp', 'heart_rate', ...]
    """
    # Dosya yolu belirle
    if file_path is None:
        data_dir = Path(__file__).parent
        candidates = list(data_dir.glob("*.xlsx")) + list(data_dir.glob("*.csv"))
        if not candidates:
            raise FileNotFoundError(
                f"data/ klasöründe .xlsx veya .csv dosyası bulunamadı: {data_dir}"
            )
        file_path = candidates[0]
        logger.info(f"Otomatik bulunan veri dosyası: {file_path}")

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Veri dosyası bulunamadı: {file_path}")

    # Yükleme
    logger.info(f"Veri yükleniyor: {file_path}")
    if file_path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, engine="openpyxl")
    elif file_path.suffix.lower() == ".csv":
        df = pd.read_csv(file_path, encoding="utf-8-sig")  # BOM'u da destekle
    else:
        raise ValueError(f"Desteklenmeyen dosya formatı: {file_path.suffix}")

    original_shape = df.shape
    logger.info(f"Ham veri: {original_shape[0]} satır, {original_shape[1]} sütun")

    # Tamamen boş satırları ve sütunları sil
    df.dropna(how="all", inplace=True)
    df.dropna(axis=1, how="all", inplace=True)

    # Sütun adı standartlaştırma
    df = _map_columns(df)

    # Sayısal sütunları dönüştür (karışık tip olabilir)
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Aralık dışı değerleri temizle
    df = _clean_vitals(df)

    # Hedef değişkeni belirle
    df = _determine_target(df)

    # Hedefi olmayan satırlar eğitilemez — doldurulmaz, düşürülür.
    # (Hedefi impute etmek uydurma etiket üretmek demektir.)
    missing_target = df["ktas_level"].isna().sum()
    if missing_target:
        logger.warning("%d satırda hedef (ktas_level) yok → düşürüldü", missing_target)
        df = df[df["ktas_level"].notna()].copy()
    df["ktas_level"] = df["ktas_level"].astype(int)

    # Kanonik semptom kodu — serbest metni modele sokulabilir hale getirir.
    # shared/symptoms.py tek doğruluk kaynağıdır; form da aynı kodları üretir.
    if "chief_complaint" in df.columns:
        df["symptom_code"] = df["chief_complaint"].map(normalize_symptom)
        covered = (df["symptom_code"] != "other").mean()
        logger.info("Semptom kodu türetildi — taksonomi kapsamı: %%%.1f", covered * 100)

    # ------------------------------------------------------------------
    # IMPUTATION VARSAYILAN OLARAK YAPILMAZ.
    #
    # Eskiden burada tüm veri setinin medyanı ile doldurma yapılıyordu.
    # İki ayrı soruna yol açıyordu:
    #   1. Train/test ayrımından önce hesaplandığı için veri sızıntısı,
    #   2. Eksiklik bilgisi yok oluyordu — oysa SpO2'nin %54'ü, ağrı
    #      skorunun %44'ü eksik ve "ölçülmemiş olması" başlı başına
    #      klinik bir sinyal.
    # Doldurma artık eğitim Pipeline'ının içinde, yalnızca eğitim
    # katlaması üzerinde yapılıyor.
    #
    # impute=True yalnızca imputasyon isteyen tüketiciler içindir
    # (ör. KNN benzer vaka mesafesi).
    # ------------------------------------------------------------------
    if impute:
        logger.info("Eksik değer imputasyonu başlıyor (impute=True)...")
        df = _impute_missing(df)

    final_shape = df.shape
    logger.info(
        f"Veri temizleme tamamlandı: {final_shape[0]} satır, "
        f"{final_shape[1]} sütun (orijinal: {original_shape})"
    )
    logger.info(f"KTAS seviye dağılımı:\n{df['ktas_level'].value_counts().sort_index()}")

    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """
    Model eğitimi için kullanılacak özellik sütunlarını döndürür.
    Hedef değişkeni, ID'leri ve Türkçe serbest metin sütunlarını hariç tutar.

    Parametreler
    ------------
    df : pd.DataFrame
        load_ktas() tarafından döndürülen temizlenmiş DataFrame.

    Döndürür
    --------
    list[str]
        Model girdi özelliklerinin listesi.
    """
    exclude = {
        # Hedef / yedek hedef
        "ktas_level", "nurse_ktas",
        # Serbest metin — yerine kanonik 'symptom_code' kullanilir
        "chief_complaint", "diagnosis",
        # Cikarim sirasinda formda sabit 5 kodlanmis; egitim/cikarim
        # dagilim uyusmazligi yaratir.
        "patients_per_hour",
        # Veri sizintisi: sadece ED sonrasi bilinen degiskenler
        "los_min", "ktas_duration_min", "mistriage", "error_group",
        "disposition",
        # ID / gruplama
        "id", "patient_id", "group",
    }
    return [c for c in df.columns if c not in exclude]


if __name__ == "__main__":
    # Bağımsız test için
    logging.basicConfig(level=logging.DEBUG,
                        format="%(levelname)s | %(name)s | %(message)s")
    try:
        df = load_ktas()
        print("\nTemizlenmiş veri başlığı:")
        print(df.head())
        print("\nSütunlar:", df.columns.tolist())
        print("\nEksik değer özeti:")
        print(df.isna().sum())
    except FileNotFoundError as e:
        print(f"[TEST] Veri dosyası bulunamadı: {e}")
        print("[TEST] data/ klasörüne KTAS veri setini (.xlsx veya .csv) koyun.")
