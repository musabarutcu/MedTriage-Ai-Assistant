# MedTriage — AI Destekli Triaj Karar Destek Sistemi

> ⚠️ **Bu proje bir portfolyo/eğitim demosudur; onaylı bir tıbbi cihaz değildir.**
> Sistem yalnızca karar desteği sağlar — nihai triaj kararı her zaman yetkili sağlık personelinin sorumluluğundadır.

## Ne Yapar?

MedTriage, hastane acil servisinde hemşire ve doktora hızlı, tutarlı bir **KTAS (Korean Triage and Acuity Scale)** seviyesi önerisi sunar:

- **Triaj Hemşiresi Formu** (`/Triaj_Kayit`): Vital bulgular ve şikayet girişi, kırmızı bayrak kontrolü, AI KTAS önerisi
- **Doktor Paneli** (`/Doktor_Paneli`): Bekleyen kuyruk, AI gerekçesi, KNN benzer geçmiş vakalar, onay/geçersiz kılma + audit trail

## Kurulum

```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. Veri setini data/ klasörüne koy
#    → data/ktas_raw.xlsx  (KTAS veri seti)
#    Kaynak: https://www.kaggle.com/datasets/llncss/ktas-dataset

# 3. Modeli eğit
python model/train_model.py

# 4. Uygulamayı başlat
streamlit run app.py
# → http://localhost:8501
```

## Proje Yapısı

```
medtriage/
├── app.py                   # Giriş noktası (karşılama ekranı)
├── requirements.txt
├── data/
│   ├── ktas_raw.xlsx        # KTAS veri seti (kullanıcı sağlar)
│   └── load_ktas.py         # Veri yükleme + temizleme
├── model/
│   ├── train_model.py       # Model eğitim scripti (XGBoost + SMOTE)
│   ├── triage_model.pkl     # Eğitilmiş model (eğitim sonrası oluşur)
│   └── baseline_model.pkl   # Baseline LR modeli
├── shared/
│   ├── queue_store.py       # SQLite hasta kuyruğu + audit log
│   └── rules.py             # Kırmızı bayrak kural motoru
└── pages/
    ├── 1_Triaj_Kayit.py     # Hemşire triaj giriş formu
    └── 2_Doktor_Paneli.py   # Doktor değerlendirme paneli
```

## Teknik Detaylar

| Özellik | Değer |
|:--------|:------|
| Veri seti | KTAS (1267 hasta, 24 özellik) |
| Birincil model | XGBoost + SMOTE örnekleme |
| Doğruluk | ~%67 (5-fold CV, 5 sınıf) |
| KTAS-1 Recall | %100 (kritik sınıf) |
| Açıklanabilirlik | SHAP TreeExplainer + Türkçe metin |
| Veritabanı | SQLite (WAL modu, çakışma önleme) |
| Ses girişi | streamlit-mic-recorder (STT entegrasyon yorumlu) |

## Uyarı

Bu sistem:
- Onaylı bir tıbbi cihaz **değildir**
- FDA / CE belgesi **yoktur**
- Gerçek klinik ortamda tek başına **kullanılamaz**
- Yalnızca eğitim ve araştırma amaçlıdır

**Geliştirici**: Musa Barutcu 
