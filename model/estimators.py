"""
model/estimators.py
-------------------
Özel sklearn tahmincileri.

NEDEN AYRI BİR MODÜL?
---------------------
Bu sınıflar eğitilmiş model paketinin içine pickle'lanır. Pickle, sınıfı
adıyla değil MODÜL YOLUYLA saklar. Sınıf train_model.py içinde tanımlı
olsaydı ve eğitim `python model/train_model.py` ile çalıştırılsaydı,
sınıf `__main__.KTASXGBClassifier` olarak kaydedilirdi; Streamlit
uygulaması modeli yüklemeye çalıştığında ise ortada `__main__` diye bir
modül olmadığı için AttributeError alırdı.

Sınıfı bağımsız bir modülde tutmak yolu (`model.estimators.…`) her
çağrı biçiminde sabitler.
"""

from __future__ import annotations

from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.preprocessing import LabelEncoder

__all__ = ["KTASXGBClassifier"]


class KTASXGBClassifier(ClassifierMixin, BaseEstimator):
    """
    XGBoost 0-tabanlı sınıf etiketi bekler; KTAS seviyeleri ise 1-5'tir.

    Bu adaptör dönüşümü tek bir yerde kapsüller. Eskiden bu `y - 1` / `+ 1`
    aritmetiği eğitim ve tahmin kodlarına elle serpiştirilmişti ve hata
    kaynağıydı.

    NOT: ClassifierMixin, MRO'da BaseEstimator'dan ÖNCE gelmelidir; aksi
    halde sklearn bu sınıfı regresör sanar ve CalibratedClassifierCV
    "Got a regressor" diyerek reddeder.
    """

    def __init__(self, params: dict | None = None):
        self.params = params

    def fit(self, X, y):
        from xgboost import XGBClassifier

        self.label_encoder_ = LabelEncoder().fit(y)
        self.model_ = XGBClassifier(**(self.params or {}))
        self.model_.fit(X, self.label_encoder_.transform(y))
        self.classes_ = self.label_encoder_.classes_
        return self

    def predict(self, X):
        return self.label_encoder_.inverse_transform(self.model_.predict(X))

    def predict_proba(self, X):
        return self.model_.predict_proba(X)
