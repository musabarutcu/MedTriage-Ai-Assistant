"""
shared/queue_store.py
---------------------
SQLite tabanlı paylaşılan durum yönetimi.

Üç tablo içerir:
  1. patient_queue  — Aktif triaj kuyruğu
  2. decision_log   — AI önerisi ile doktor kararı karşılaştırma günlüğü
                     (etik/hesap verebilirlik gereksinimi için KRİTİK)
  3. consent_log    — KVKK/gizlilik onay kaydı (her oturum açılışında)

SQLite kullanımı sayesinde ek kurulum gerektirmez; tek dosyada saklanır.
Çoklu Streamlit sekmeleri aynı dosyaya güvenle yazabilir (WAL modu etkin).

⚠️ UYARI: Bu sistem bir karar destek aracıdır. Kesin tanı koymaz.
      MedTriage — Portfolyo/Eğitim Prototipi.
"""

from __future__ import annotations

import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Veritabanı yolu (proje kök dizinine göre)
# ---------------------------------------------------------------------------
_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "medtriage.db"


def log_consent(panel: str = "app", db_path: Path | str | None = None) -> int:
    """
    KVKK/Gizlilik onay kaydını veritabanına ekler.

    Parametreler
    ------------
    panel : str
        Onayın yapıldığı panel veya sayfa (varsayılan: 'app').
    db_path : Path | str | None
        DB yolu.

    Döndürür
    --------
    int
        Oluşturulan consent_log kaydının id'si.
    """
    db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
    init_db(db_path)
    now_iso = datetime.now().isoformat()
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO consent_log (timestamp, panel)
            VALUES (?, ?)
            """,
            (now_iso, panel),
        )
        return cursor.lastrowid


# ---------------------------------------------------------------------------
# Yardımcı: bağlantı yöneticisi
# ---------------------------------------------------------------------------

@contextmanager
def _get_conn(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """
    SQLite bağlantısını context manager olarak açar ve kapatır.
    WAL modu yazma çakışmalarını azaltır (çok sekmeli Streamlit için).
    """
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row  # Sütun ismiyle erişim sağlar
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tablo oluşturma
# ---------------------------------------------------------------------------

def init_db(db_path: Path | str | None = None) -> Path:
    """
    SQLite veritabanını ve gerekli tabloları oluşturur.
    Tablolar zaten mevcutsa (IF NOT EXISTS) yeniden oluşturmaz.

    Parametreler
    ------------
    db_path : Path | str | None
        Veritabanı dosyası yolu. None ise varsayılan yol kullanılır.

    Döndürür
    --------
    Path
        Kullanılan veritabanı dosyasının yolu.
    """
    db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with _get_conn(db_path) as conn:
        # ----------------------------------------------------------------
        # Tablo 1: patient_queue
        # Aktif triaj kuyruğunu tutar.
        # vitals → JSON string olarak saklanır (esnek şema).
        # ----------------------------------------------------------------
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_queue (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        TEXT    NOT NULL,
                age              INTEGER,
                gender           TEXT,
                chief_complaint  TEXT,
                vitals           TEXT,           -- JSON: {"sbp":120, "spo2":98, ...}
                ai_priority      INTEGER,         -- KTAS seviyesi (1-5)
                ai_explanation   TEXT,            -- AI'ın Türkçe gerekçesi
                red_flag         INTEGER NOT NULL DEFAULT 0,  -- 0/1 boolean
                status           TEXT    NOT NULL DEFAULT 'bekliyor'
                    CHECK(status IN ('bekliyor', 'görüldü', 'transfer edildi'))
            )
        """)

        # ----------------------------------------------------------------
        # Tablo 2: decision_log
        # Etik/hesap verebilirlik gereksinimi: Her AI önerisi ile doktorun
        # kararı karşılaştırmalı olarak loglanır. Bu tablo silinmemelidir.
        # ----------------------------------------------------------------
        conn.execute("""
            CREATE TABLE IF NOT EXISTS decision_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id       INTEGER NOT NULL,
                ai_suggestion    INTEGER,         -- AI'ın önerdiği KTAS seviyesi
                doctor_decision  TEXT    NOT NULL
                    CHECK(doctor_decision IN ('onaylandı', 'geçersiz kılındı')),
                doctor_note      TEXT,            -- Doktorun gerekçesi / notu
                timestamp        TEXT    NOT NULL,
                FOREIGN KEY (patient_id) REFERENCES patient_queue(id)
            )
        """)

        # ----------------------------------------------------------------
        # Tablo 3: consent_log
        # KVKK/Gizlilik onay kaydı — hesap verebilirlik için.
        # Her oturum başında kullanıcının onayı buraya yazılır.
        # ----------------------------------------------------------------
        conn.execute("""
            CREATE TABLE IF NOT EXISTS consent_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT    NOT NULL,
                panel     TEXT    NOT NULL DEFAULT 'app'
            )
        """)

        # İndeksler — kuyruğu sık sorgulayacağız
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_queue_status
            ON patient_queue(status, timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_log_patient
            ON decision_log(patient_id)
        """)

    logger.info(f"Veritabanı hazır: {db_path}")
    return db_path


# ---------------------------------------------------------------------------
# patient_queue işlemleri
# ---------------------------------------------------------------------------

def add_patient(
    age: int,
    gender: str,
    chief_complaint: str,
    vitals: dict,
    ai_priority: int,
    ai_explanation: str,
    red_flag: bool,
    db_path: Path | str | None = None,
) -> int:
    """
    Triaj kuyruğuna yeni hasta ekler.

    Parametreler
    ------------
    age : int
        Hastanın yaşı.
    gender : str
        Hastanın cinsiyeti ('erkek', 'kadın', 'diğer').
    chief_complaint : str
        Ana başvuru şikayeti.
    vitals : dict
        Vital bulgular sözlüğü ({"sbp": 120, "spo2": 98, ...}).
    ai_priority : int
        AI'ın önerdiği KTAS seviyesi (1=en acil, 5=en az acil).
    ai_explanation : str
        AI'ın Türkçe gerekçe açıklaması.
    red_flag : bool
        Kırmızı bayrak tetiklendi mi?
    db_path : Path | str | None
        Veritabanı yolu (None ise varsayılan).

    Döndürür
    --------
    int
        Yeni eklenen hastanın veritabanı ID'si.
    """
    db_path = _resolve_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")

    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO patient_queue
                (timestamp, age, gender, chief_complaint, vitals,
                 ai_priority, ai_explanation, red_flag, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'bekliyor')
            """,
            (now, age, gender, chief_complaint,
             json.dumps(vitals, ensure_ascii=False),
             ai_priority, ai_explanation, int(red_flag)),
        )
        patient_id = cursor.lastrowid

    logger.info(f"Yeni hasta eklendi: ID={patient_id}, KTAS={ai_priority}, "
                f"Kırmızı Bayrak={red_flag}")
    return patient_id


def get_queue(
    status_filter: str | None = "bekliyor",
    db_path: Path | str | None = None,
) -> list[dict]:
    """
    Hasta kuyruğunu döndürür.

    Parametreler
    ------------
    status_filter : str | None
        Filtre: 'bekliyor', 'görüldü', 'transfer edildi', veya None (tümü).
    db_path : Path | str | None
        Veritabanı yolu.

    Döndürür
    --------
    list[dict]
        Her hasta bir dict; vitals alanı JSON'dan Python dict'e dönüştürülmüş.
        Liste ai_priority'ye göre sıralıdır (1 en önce).
    """
    db_path = _resolve_db(db_path)

    with _get_conn(db_path) as conn:
        if status_filter:
            rows = conn.execute(
                """
                SELECT * FROM patient_queue
                WHERE status = ?
                ORDER BY ai_priority ASC, timestamp ASC
                """,
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM patient_queue
                ORDER BY ai_priority ASC, timestamp ASC
                """
            ).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        try:
            d["vitals"] = json.loads(d["vitals"]) if d["vitals"] else {}
        except json.JSONDecodeError:
            d["vitals"] = {}
        d["red_flag"] = bool(d["red_flag"])
        result.append(d)

    return result


def update_patient_status(
    patient_id: int,
    new_status: str,
    db_path: Path | str | None = None,
) -> bool:
    """
    Hastanın durum bilgisini günceller.

    Parametreler
    ------------
    patient_id : int
        Güncellenecek hastanın ID'si.
    new_status : str
        Yeni durum: 'bekliyor', 'görüldü', veya 'transfer edildi'.
    db_path : Path | str | None
        Veritabanı yolu.

    Döndürür
    --------
    bool
        Güncelleme başarılı ise True, hasta bulunamazsa False.
    """
    valid_statuses = {"bekliyor", "görüldü", "transfer edildi"}
    if new_status not in valid_statuses:
        raise ValueError(f"Geçersiz durum: '{new_status}'. "
                         f"Geçerli değerler: {valid_statuses}")

    db_path = _resolve_db(db_path)
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "UPDATE patient_queue SET status = ? WHERE id = ?",
            (new_status, patient_id),
        )
        updated = cursor.rowcount > 0

    if updated:
        logger.info(f"Hasta {patient_id} durumu güncellendi: '{new_status}'")
    else:
        logger.warning(f"Hasta bulunamadı: ID={patient_id}")
    return updated


def get_patient_by_id(
    patient_id: int,
    db_path: Path | str | None = None,
) -> dict | None:
    """
    Belirtilen ID'ye sahip hastayı döndürür.

    Parametreler
    ------------
    patient_id : int
        Sorgulanacak hastanın ID'si.
    db_path : Path | str | None
        Veritabanı yolu.

    Döndürür
    --------
    dict | None
        Hasta verisi veya bulunamazsa None.
    """
    db_path = _resolve_db(db_path)
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM patient_queue WHERE id = ?", (patient_id,)
        ).fetchone()

    if row is None:
        return None
    d = dict(row)
    try:
        d["vitals"] = json.loads(d["vitals"]) if d["vitals"] else {}
    except json.JSONDecodeError:
        d["vitals"] = {}
    d["red_flag"] = bool(d["red_flag"])
    return d


# ---------------------------------------------------------------------------
# decision_log işlemleri
# ---------------------------------------------------------------------------

def log_decision(
    patient_id: int,
    ai_suggestion: int,
    doctor_decision: str,
    doctor_note: str = "",
    db_path: Path | str | None = None,
) -> int:
    """
    Doktorun kararını ve AI önerisini karar günlüğüne kaydeder.

    Bu kayıt ETİK/HESAP VEREBİLİRLİK açısından KRİTİKTİR.
    AI'ın ne önerdiği ile doktorun ne kararladığını karşılaştırmalı tutar.
    Modelin zamanla kalibrasyon değerlendirmesi için de kullanılır.

    Parametreler
    ------------
    patient_id : int
        Karara konu olan hastanın ID'si.
    ai_suggestion : int
        AI'ın önerdiği KTAS seviyesi (1-5).
    doctor_decision : str
        Doktorun kararı: 'onaylandı' veya 'geçersiz kılındı'.
    doctor_note : str
        Doktorun gerekçesi veya ek notu (isteğe bağlı).
    db_path : Path | str | None
        Veritabanı yolu.

    Döndürür
    --------
    int
        Yeni log kaydının ID'si.
    """
    valid_decisions = {"onaylandı", "geçersiz kılındı"}
    if doctor_decision not in valid_decisions:
        raise ValueError(f"Geçersiz karar: '{doctor_decision}'. "
                         f"Geçerli değerler: {valid_decisions}")

    db_path = _resolve_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")

    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO decision_log
                (patient_id, ai_suggestion, doctor_decision, doctor_note, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (patient_id, ai_suggestion, doctor_decision, doctor_note, now),
        )
        log_id = cursor.lastrowid

    logger.info(
        f"Karar günlüğüne eklendi: Log ID={log_id}, Hasta={patient_id}, "
        f"AI={ai_suggestion}, Doktor='{doctor_decision}'"
    )
    return log_id


def get_decision_log(
    patient_id: int | None = None,
    db_path: Path | str | None = None,
) -> list[dict]:
    """
    Karar günlüğünü döndürür.

    Parametreler
    ------------
    patient_id : int | None
        Belirli bir hastanın kayıtlarını getirmek için hasta ID'si.
        None ise tüm günlük döndürülür.
    db_path : Path | str | None
        Veritabanı yolu.

    Döndürür
    --------
    list[dict]
        Karar günlüğü kayıtları.
    """
    db_path = _resolve_db(db_path)
    with _get_conn(db_path) as conn:
        if patient_id is not None:
            rows = conn.execute(
                "SELECT * FROM decision_log WHERE patient_id = ? ORDER BY timestamp",
                (patient_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM decision_log ORDER BY timestamp DESC"
            ).fetchall()

    return [dict(row) for row in rows]


def get_override_statistics(db_path: Path | str | None = None) -> dict:
    """
    AI kararlarının doktor tarafından kaç kez onaylandığı / geçersiz kılındığı
    istatistiğini döndürür. Model kalibrasyon takibi için kullanılır.

    Parametreler
    ------------
    db_path : Path | str | None
        Veritabanı yolu.

    Döndürür
    --------
    dict
        {
            "total": int,
            "approved": int,
            "overridden": int,
            "override_rate": float  (0.0 - 1.0)
        }
    """
    db_path = _resolve_db(db_path)
    with _get_conn(db_path) as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN doctor_decision='onaylandı' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN doctor_decision='geçersiz kılındı' THEN 1 ELSE 0 END) as overridden
            FROM decision_log
        """).fetchone()

    total = row["total"] or 0
    approved = row["approved"] or 0
    overridden = row["overridden"] or 0
    override_rate = overridden / total if total > 0 else 0.0

    return {
        "total": total,
        "approved": approved,
        "overridden": overridden,
        "override_rate": override_rate,
    }


# ---------------------------------------------------------------------------
# consent_log işlemleri
# ---------------------------------------------------------------------------

def log_consent(
    panel: str = "app",
    db_path: Path | str | None = None,
) -> int:
    """
    Kullanıcının KVKK/gizlilik onayını veritabanına kaydeder.

    Her oturum başında, kullanıcı 'Kabul Et ve Devam Et' düğmesine
    bastığında bu fonksiyon çağrılır. Bu kayıt hesap verebilirlik
    anlatısının bir parçasıdır ve demo/sunum için kanıt sağlar.

    Parametreler
    ------------
    panel : str
        Onay hangi ekranda verildi (varsayılan: 'app' giriş ekranı).
    db_path : Path | str | None
        Veritabanı yolu.

    Döndürür
    --------
    int
        Yeni consent_log kaydının ID'si.
    """
    db_path = _resolve_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")

    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO consent_log (timestamp, panel) VALUES (?, ?)",
            (now, panel),
        )
        consent_id = cursor.lastrowid

    logger.info(f"KVKK onayı kaydedildi: ID={consent_id}, Panel='{panel}'")
    return consent_id


# ---------------------------------------------------------------------------
# Yardımcı
# ---------------------------------------------------------------------------

def _resolve_db(db_path: Path | str | None) -> Path:
    """
    Veritabanı yolunu çözümler; None ise varsayılanı kullanır ve
    gerekirse tabloları oluşturur.
    """
    if db_path is None:
        return init_db(_DEFAULT_DB_PATH)
    p = Path(db_path)
    if not p.exists():
        return init_db(p)
    return p


# ---------------------------------------------------------------------------
# Bağımsız test bloğu
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile
    import os

    logging.basicConfig(level=logging.DEBUG,
                        format="%(levelname)s | %(message)s")

    # Geçici DB ile test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = Path(f.name)

    try:
        print("\n=== queue_store.py BAĞIMSIZ TEST ===\n")
        init_db(test_db)

        # Hasta ekle
        pid1 = add_patient(
            age=45, gender="erkek",
            chief_complaint="göğüs ağrısı ve nefes darlığı",
            vitals={"sbp": 90, "heart_rate": 115, "spo2": 92},
            ai_priority=1, ai_explanation="Kritik: SpO2 düşük + taşikardi",
            red_flag=True, db_path=test_db
        )
        pid2 = add_patient(
            age=32, gender="kadın",
            chief_complaint="baş ağrısı",
            vitals={"sbp": 130, "heart_rate": 82, "spo2": 98},
            ai_priority=3, ai_explanation="Orta öncelik: Vital bulgular stabil",
            red_flag=False, db_path=test_db
        )
        print(f"✅ İki hasta eklendi: ID={pid1}, ID={pid2}")

        # Kuyruğu sorgula
        queue = get_queue(status_filter="bekliyor", db_path=test_db)
        print(f"✅ Kuyrukta {len(queue)} hasta (bekliyor):")
        for p in queue:
            print(f"   ID={p['id']} | KTAS={p['ai_priority']} | "
                  f"Şikayet={p['chief_complaint']} | Kırmızı Bayrak={p['red_flag']}")

        # Durum güncelle
        update_patient_status(pid1, "görüldü", db_path=test_db)
        print(f"✅ Hasta {pid1} 'görüldü' olarak güncellendi")

        # Karar logla
        log_id = log_decision(
            patient_id=pid1, ai_suggestion=1,
            doctor_decision="onaylandı",
            doctor_note="Klinik tablo AI önerisiyle uyumlu",
            db_path=test_db
        )
        log_decision(
            patient_id=pid2, ai_suggestion=3,
            doctor_decision="geçersiz kılındı",
            doctor_note="Hastanın subjektif ağrısı daha yüksek; KTAS 2'ye yükseltildi",
            db_path=test_db
        )
        print(f"✅ İki karar loglandı (log ID={log_id})")

        # İstatistik
        stats = get_override_statistics(db_path=test_db)
        print(f"\n✅ İstatistikler: {stats}")
        print(f"   Override oranı: %{stats['override_rate']*100:.1f}")

        print("\n=== TÜM TESTLER BAŞARILI ✅ ===")

    finally:
        os.unlink(test_db)
