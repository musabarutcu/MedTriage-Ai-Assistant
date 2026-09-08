"""
tests/test_rules.py
-------------------
Kırmızı bayrak kural motorunun regresyon testleri.

Bu dosyanın varlık sebebi: motor sistemin ilan edilmiş güvenlik ağı.
Sessizce bozulursa yanıtsız hasta kuyrukta bekler. Aşağıdaki testlerin
ilk grubu, revizyon öncesi GERÇEKTEN KAÇAN vakalardır.

Çalıştırma:
    pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.rules import check_red_flags, format_red_flag_message, age_band

# Kural tetiklemeyen, tamamen normal erişkin vitalleri
NORMAL = {
    "age": 40, "spo2": 98, "sbp": 120, "dbp": 80,
    "heart_rate": 80, "resp_rate": 16, "temperature": 36.6,
    "mental_status": 1,
}


def _with(**overrides) -> dict:
    v = dict(NORMAL)
    v.update(overrides)
    return v


# ===========================================================================
# GRUP 1 — Revizyon öncesi kaçan vakalar (regresyon koruması)
# ===========================================================================

class TestPreviouslyMissedCases:
    """Bu vakaların hepsi eski motorda red_flag=False dönüyordu."""

    def test_unresponsive_patient_is_flagged(self):
        """AVPU-4 yanıtsız hasta. Eski motor: kaçırıyordu (int/str uyuşmazlığı)."""
        r = check_red_flags(_with(mental_status=4))
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 1

    def test_responds_only_to_pain_is_flagged(self):
        """AVPU-3. Eski motor: kaçırıyordu."""
        r = check_red_flags(_with(mental_status=3))
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 1

    def test_responds_to_verbal_is_flagged_as_ktas2(self):
        """AVPU-2 uyarı düzeyinde ama resüsitasyon değil."""
        r = check_red_flags(_with(mental_status=2))
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 2

    def test_alert_patient_is_not_flagged(self):
        """AVPU-1 normal — yanlış alarm üretmemeli."""
        assert check_red_flags(_with(mental_status=1))["red_flag"] is False

    def test_apnea_level_respiratory_rate_is_flagged(self):
        """Solunum 4/dk. Eski motor: solunum kuralı hiç yoktu."""
        r = check_red_flags(_with(resp_rate=4))
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 1

    def test_severe_tachypnea_is_flagged(self):
        """Solunum 45/dk. Eski motor: kaçırıyordu."""
        r = check_red_flags(_with(resp_rate=45))
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 2

    def test_hyperthermia_is_flagged(self):
        """Ateş 41.5°C. Eski motor: ateş kuralı hiç yoktu."""
        r = check_red_flags(_with(temperature=41.5))
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 1

    def test_severe_hypothermia_is_flagged(self):
        """32°C altı ağır hipotermi. Eski motor: kaçırıyordu."""
        r = check_red_flags(_with(temperature=31.0))
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 1

    def test_moderate_hypothermia_is_flagged(self):
        r = check_red_flags(_with(temperature=34.0))
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 2


# ===========================================================================
# GRUP 2 — Yaşa göre eşikler
# ===========================================================================

class TestAgeBandedThresholds:

    def test_age_band_boundaries(self):
        assert age_band(0.5) == "infant"
        assert age_band(1) == "toddler"
        assert age_band(5) == "toddler"
        assert age_band(6) == "child"
        assert age_band(12) == "child"
        assert age_band(13) == "adult"
        assert age_band(40) == "adult"

    def test_missing_age_defaults_to_adult(self):
        assert age_band(None) == "adult"
        assert age_band("abc") == "adult"
        assert check_red_flags({"heart_rate": 80})["age_band"] == "adult"

    def test_infant_heart_rate_150_is_normal(self):
        """1 yaş altında nabız 150 normaldir; erişkin eşiğiyle alarm verilmemeli."""
        r = check_red_flags({"age": 0.5, "heart_rate": 150})
        assert r["red_flag"] is False

    def test_adult_heart_rate_150_is_not_flagged_but_160_is(self):
        """Erişkin eşiği >150; sınır değeri kendisi tetiklememeli."""
        assert check_red_flags(_with(heart_rate=150))["red_flag"] is False
        assert check_red_flags(_with(heart_rate=160))["red_flag"] is True

    def test_infant_heart_rate_190_is_flagged(self):
        r = check_red_flags({"age": 0.5, "heart_rate": 190})
        assert r["red_flag"] is True

    def test_infant_respiratory_rate_40_is_normal(self):
        """Bebekte solunum 40/dk normal; erişkinde ciddi takipne."""
        assert check_red_flags({"age": 0.5, "resp_rate": 40})["red_flag"] is False
        assert check_red_flags({"age": 40, "resp_rate": 40})["red_flag"] is True

    def test_child_hypotension_threshold_is_lower(self):
        """8 yaşında SKB 88 normal sayılır; erişkinde şok eşiğinin altında."""
        assert check_red_flags({"age": 8, "sbp": 88})["red_flag"] is False
        assert check_red_flags({"age": 40, "sbp": 88})["red_flag"] is True


# ===========================================================================
# GRUP 3 — Sınır değerler
# ===========================================================================

class TestBoundaryValues:

    @pytest.mark.parametrize("spo2,flagged,ktas", [
        (91, False, None),
        (90, False, None),   # eşik "< 90", 90 dahil değil
        (89, True, 2),
        (85, True, 2),
        (84, True, 1),       # < 85 ağır hipoksi
    ])
    def test_spo2_thresholds(self, spo2, flagged, ktas):
        r = check_red_flags(_with(spo2=spo2))
        assert r["red_flag"] is flagged
        assert r["suggested_ktas"] == ktas

    @pytest.mark.parametrize("rr,flagged", [
        (9, False), (8, False), (7, True),
        (30, False), (31, True),
    ])
    def test_respiratory_rate_thresholds(self, rr, flagged):
        assert check_red_flags(_with(resp_rate=rr))["red_flag"] is flagged

    @pytest.mark.parametrize("sbp,flagged", [
        (91, False), (90, False), (89, True),
        (200, False), (201, True),
    ])
    def test_blood_pressure_thresholds(self, sbp, flagged):
        assert check_red_flags(_with(sbp=sbp))["red_flag"] is flagged

    def test_hypertensive_crisis_is_ktas2_not_ktas1(self):
        """Hipertansif kriz acildir ama resüsitasyon değildir — eski motor
        her kırmızı bayrağı KTAS-1'e sabitliyordu."""
        r = check_red_flags(_with(sbp=210))
        assert r["suggested_ktas"] == 2

    def test_shock_is_ktas1(self):
        assert check_red_flags(_with(sbp=70))["suggested_ktas"] == 1


# ===========================================================================
# GRUP 4 — GCS
# ===========================================================================

class TestGCS:

    @pytest.mark.parametrize("gcs,flagged,ktas", [
        (15, False, None),
        (13, False, None),
        (12, True, 2),
        (9, True, 2),
        (8, True, 1),
        (3, True, 1),
    ])
    def test_gcs_thresholds(self, gcs, flagged, ktas):
        r = check_red_flags(_with(gcs=gcs))
        assert r["red_flag"] is flagged
        assert r["suggested_ktas"] == ktas


# ===========================================================================
# GRUP 5 — Semptom tabanlı kurallar
# ===========================================================================

class TestSymptomRules:

    def test_chest_pain_alone_is_ktas2(self):
        r = check_red_flags(_with(), "göğüs ağrısı")
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 2

    def test_chest_pain_with_dyspnea_reports_combination(self):
        r = check_red_flags(_with(), "göğüs ağrısı ve nefes darlığı")
        assert r["red_flag"] is True
        assert any("AKS/PE" in x for x in r["all_reasons"])

    def test_altered_consciousness_in_text_is_ktas1(self):
        r = check_red_flags(_with(), "hasta bilinç kaybı yaşadı")
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 1

    def test_english_symptom_text_also_matches(self):
        """Veri seti İngilizce; aynı taksonomi her iki dili de karşılamalı."""
        assert check_red_flags(_with(), "mental change")["suggested_ktas"] == 1
        assert check_red_flags(_with(), "dyspnea")["suggested_ktas"] == 2

    def test_symptom_code_can_be_passed_directly(self):
        r = check_red_flags(_with(), "", symptom_code="seizure")
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 1

    def test_benign_symptom_is_not_flagged(self):
        assert check_red_flags(_with(), "baş ağrısı")["red_flag"] is False


# ===========================================================================
# GRUP 6 — Dayanıklılık: eksik / bozuk veri motoru çökertmemeli
# ===========================================================================

class TestRobustness:

    def test_empty_vitals(self):
        r = check_red_flags({})
        assert r["red_flag"] is False
        assert r["suggested_ktas"] is None

    @pytest.mark.parametrize("bad", [None, "", "abc", [], {}, float("nan")])
    def test_unparseable_values_are_skipped(self, bad):
        r = check_red_flags({"spo2": bad, "sbp": bad, "heart_rate": bad,
                             "resp_rate": bad, "temperature": bad})
        assert r["red_flag"] is False

    def test_string_numbers_are_accepted(self):
        """Vitaller JSON'dan string olarak gelebilir."""
        assert check_red_flags({"age": 40, "spo2": "85"})["red_flag"] is True

    def test_legacy_text_mental_status_still_works(self):
        """Eski kayıtlarda mental_status metin olabilir — geriye uyumluluk."""
        r = check_red_flags(_with(mental_status="unconscious"))
        assert r["red_flag"] is True
        assert r["suggested_ktas"] == 1


# ===========================================================================
# GRUP 7 — Sözleşme: dönüş yapısı ve önceliklendirme
# ===========================================================================

class TestReturnContract:

    def test_backward_compatible_keys_present(self):
        r = check_red_flags(_with(spo2=80))
        for key in ("red_flag", "reason", "all_reasons"):
            assert key in r
        assert r["reason"] == r["all_reasons"][0]

    def test_most_critical_rule_wins(self):
        """KTAS-1 (şok) ile KTAS-2 (taşikardi) birlikte tetiklenirse
        önerilen seviye 1 olmalı ve gerekçe listesi ikisini de içermeli."""
        r = check_red_flags(_with(sbp=70, heart_rate=170))
        assert r["suggested_ktas"] == 1
        assert len(r["all_reasons"]) >= 2
        assert "Hipotansiyon" in r["reason"]

    def test_no_duplicate_reasons(self):
        r = check_red_flags(_with(mental_status=4), "bilinç kaybı")
        assert len(r["all_reasons"]) == len(set(r["all_reasons"]))

    def test_format_message_empty_when_no_flag(self):
        assert format_red_flag_message(check_red_flags(_with())) == ""

    def test_format_message_lists_all_reasons(self):
        r = check_red_flags(_with(sbp=70, spo2=80))
        msg = format_red_flag_message(r)
        assert "KIRMIZI BAYRAK" in msg
        assert "KTAS-1" in msg
        for reason in r["all_reasons"]:
            assert reason in msg
