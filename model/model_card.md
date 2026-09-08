# MedTriage — Model Kartı

> Otomatik üretilmiştir: `python model/evaluate.py` · 2026-09-08
> **Bu dosyayı elle düzenlemeyin.** README'deki sayılar buradan alınır.

## Özet

| | Doğruluk | ±1 seviye | KTAS-1 recall | KTAS-2 recall | Alt-triaj |
|:--|:--|:--|:--|:--|:--|
| **Model** (XGBoost + SMOTE + kalibrasyon) | **%67.9** | %94.6 | 0.615 | 0.486 | %16.4 |
| **Hemşire** (`KTAS_RN`, insan baseline) | **%85.3** | %98.5 | 0.577 | 0.832 | %10.3 |

5 katlamalı stratified çapraz doğrulama · 1267 hasta · 19 özellik · hedef: `KTAS_expert` (uzman etiketi)

## Bu sayılar ne anlama geliyor?

Model, triaj hemşiresinden **17.4 puan geride**. Bu bir başarısızlık değil, bu veri setinin sınırı: 1267 hasta ve yalnızca 26 adet KTAS-1 örneğiyle eğitilen bir model, eğitimli bir klinisyeni geçemez.

Buna karşılık **en kritik sınıfta (KTAS-1) model hemşireyle başa baş**: 0.615 / 0.577. Hemşirenin üstünlüğü ağırlıklı olarak KTAS-2 ve orta seviyelerde yoğunlaşıyor.

Bu nedenle MedTriage kendini hemşirenin yerine koyan bir sistem olarak değil, **ikinci okuyucu** olarak konumlandırır:

1. Hayati bulguları deterministik kural motoru yakalar (`shared/rules.py`), model değil.
2. Model bağlamsal bir öneri sunar ve **ne zaman bilmediğini söyler** (aşağıya bakınız).
3. Nihai karar her zaman hekimindir ve `decision_log` tablosuna kaydedilir.

## Güven bandı — model ne zaman güvenilir?

Olasılıklar isotonic regresyonla kalibre edilmiştir; aşağıdaki tablo kalibrasyonun işe yaradığının kanıtıdır. Güven eşiği yükseldikçe doğruluk gerçekten artıyor:

| Güven eşiği | Kapsam | O bölgede doğruluk | Hasta sayısı |
|:--|:--|:--|:--|
| ≥ 0.40 | %92.5 | **%70.3** | 1172 |
| ≥ 0.50 | %71.0 | **%77.4** | 899 |
| ≥ 0.60 | %50.9 | **%83.6** | 645 |
| ≥ 0.70 | %32.0 | **%89.4** | 406 |
| ≥ 0.80 | %12.4 | **%91.1** | 157 |

Güven ≥ 0.70 bölgesinde model doğruluğu **%89.4** ve bu bölge hastaların **%32.0** kadarını kapsıyor — yani her üç hastadan yaklaşık birinde model, hemşire seviyesine (%85.3) ulaşıyor. Ürünün değeri buradadır: model nerede güvenilir olduğunu biliyor.

Arayüz eşikleri: güven ≥ 0.60 "güvenilir bant"; < 0.40 ise "model kararsız" uyarısı gösterilir (vakaların %7.5 kadarı).

## Ablasyon — serbest metin şikayetin katkısı

| Özellik seti | Doğruluk | ±1 seviye |
|:--|:--|:--|
| Yalnızca vitaller | %60.0 | %92.0 |
| Vitaller + kanonik semptom kodu | **%67.9** | **%94.6** |

Başvuru şikayetini `shared/symptoms.py` taksonomisiyle 26 kanonik koda indirgeyip modele vermek doğruluğu **+7.9 puan** değiştiriyor. Önceki sürümde bu sütun modelden tamamen dışlanmıştı.

Ham TF-IDF metin özellikleri de denendi: tam isabeti bir miktar artırıyor ama ±1 doğruluğunu düşürüyor — yani daha *büyük* hatalar yapıyor. Güvenlik ağı için yanlış takas olduğundan birincil modele alınmadı.

## Sınıf bazlı recall

| KTAS | Hasta sayısı | Model recall | Hemşire recall |
|:--|:--|:--|:--|
| KTAS-1 | 26 | 0.615 | 0.577 |
| KTAS-2 | 220 | 0.486 | 0.832 |
| KTAS-3 | 487 | 0.758 | 0.821 |
| KTAS-4 | 459 | 0.786 | 0.915 |
| KTAS-5 | 75 | 0.093 | 0.840 |

## Karışıklık matrisi

Satır = gerçek (uzman), sütun = model tahmini.

| Gerçek \ Tahmin | KTAS-1 | KTAS-2 | KTAS-3 | KTAS-4 | KTAS-5 |
|:--|:--|:--|:--|:--|:--|
| **KTAS-1** | 16 | 6 | 4 | 0 | 0 |
| **KTAS-2** | 3 | 107 | 85 | 23 | 2 |
| **KTAS-3** | 0 | 35 | 369 | 81 | 2 |
| **KTAS-4** | 0 | 12 | 81 | 361 | 5 |
| **KTAS-5** | 0 | 1 | 24 | 43 | 7 |

> ⚠️ **Zayıf sınıf uyarısı.** KTAS-5 sınıf(lar)ında recall 0.30'un altında: model bu seviyeyi neredeyse hiç öngörmüyor, vakaları komşu seviyelere dağıtıyor. Sebep sınıf dengesizliği ve bu seviyelerin klinik olarak komşularıyla iç içe geçmesidir. Bu seviyelerde model önerisi tek başına kullanılmamalıdır.

Alt-triaj (gerçekte daha acil olan hastaya daha az acil demek): **%16.4** · Üst-triaj: %15.7. Alt-triaj klinik olarak daha tehlikelidir; bu yüzden ayrı izlenir.

## Sınırlılıklar

- **Küçük ve dengesiz veri.** 1267 hasta; KTAS-1 yalnızca 26 örnek. KTAS-1 recall değeri geniş bir güven aralığına sahiptir ve tek bir hastanın yer değiştirmesi metriği belirgin biçimde oynatır.
- **Yoğun eksik veri.** Ham veride SpO2'nin ~%55'i, ağrı skorunun ~%44'ü eksik. Eksiklik artık bir özellik olarak modellenir (`spo2_missing`, `pain_missing`) ama doldurulan değerler yine de tahmindir.
- **Tek merkez, tek ülke.** Veri seti Kore acil servis verisidir (KTAS). Türkiye'deki hasta profili, geliş şekli dağılımı ve triaj pratiği farklıdır; performansın buraya taşınacağı garanti değildir.
- **Dil farkı.** Eğitim verisindeki şikayetler İngilizce, form Türkçe. Kanonik semptom taksonomisi bu boşluğu kapatır ama taksonomi dışında kalan vakalar `other` koduna düşer (veri setinde ~%15).
- **Etiket öznelliği.** Hedef `KTAS_expert` de bir insan yargısıdır; mutlak doğru değildir.
- **Onaylı tıbbi cihaz değildir.** FDA/CE belgesi yoktur, klinik kullanıma uygun değildir.

