"""
shared/auth.py
--------------
Basit rol tabanlı erişim katmanı.

NEDEN VAR?
----------
Revizyon öncesinde iki açık vardı:
  1. Doktor paneline `pages/2_Doktor_Paneli.py` adresiyle doğrudan
     girilebiliyordu; o sayfada KVKK onay kontrolü hiç yoktu
     (yalnızca triaj sayfasında vardı).
  2. `decision_log` tablosunda kararı verenin kim olduğu yazmıyordu.
     Aktörü olmayan bir denetim izi denetim izi değildir.

KAPSAM
------
Bu bir kimlik DOĞRULAMA sistemi değildir; parola yoktur ve olduğunu da
iddia etmez. Amaç, demo kolaylığını bozmadan (a) rolleri ayırmak,
(b) her karara bir isim iliştirmek. Gerçek bir hastane kurulumunda
buranın yerine kurumsal SSO gelmelidir.

Kullanım:
    from shared.auth import require_access, current_user

    require_access("doktor")      # sayfanın en başında
    user = current_user()         # {"role": "doktor", "name": "Dr. ..."}
"""

from __future__ import annotations

import streamlit as st

__all__ = [
    "ROLES", "ROLE_LABELS", "ROLE_HOME",
    "require_access", "current_user", "is_logged_in", "logout",
]

ROLES = ("hemsire", "doktor")

ROLE_LABELS = {
    "hemsire": "Triaj Hemşiresi",
    "doktor": "Hekim",
}

# Rolün varsayılan açılış sayfası
ROLE_HOME = {
    "hemsire": "pages/1_Triaj_Kayit.py",
    "doktor": "pages/2_Doktor_Paneli.py",
}

# Hangi sayfaya hangi roller girebilir.
# Hekim triaj formunu da görebilir (acil serviste olağan bir durum);
# hemşire ise doktor paneline giremez.
PAGE_ACCESS = {
    "triaj": ("hemsire", "doktor"),
    "doktor": ("doktor",),
}


def is_logged_in() -> bool:
    """Rol seçilmiş ve isim girilmiş mi?"""
    return bool(st.session_state.get("user_role")) and bool(
        st.session_state.get("user_name")
    )


def current_user() -> dict:
    """Aktif kullanıcı bilgisi. Oturum yoksa boş alanlar döner."""
    role = st.session_state.get("user_role", "")
    return {
        "role": role,
        "role_label": ROLE_LABELS.get(role, ""),
        "name": st.session_state.get("user_name", ""),
    }


def display_name() -> str:
    """Denetim kaydına yazılacak ad ('Dr. Ayşe Y. (Hekim)')."""
    user = current_user()
    if not user["name"]:
        return ""
    return f"{user['name']} ({user['role_label']})"


def logout() -> None:
    """Oturumu kapatır ve giriş ekranına döner."""
    for key in ("user_role", "user_name", "kvkk_accepted", "kvkk_timestamp"):
        st.session_state.pop(key, None)
    st.session_state.app_step = "kvkk"


def require_access(page: str) -> None:
    """
    Sayfanın en başında çağrılır. Üç kapıyı sırayla kontrol eder:

      1. KVKK onayı verilmiş mi?
      2. Rol seçilmiş mi?
      3. Bu rol bu sayfaya girebilir mi?

    Herhangi biri sağlanmazsa kullanıcı uygun yere yönlendirilir ve
    sayfanın geri kalanı çalıştırılmaz.

    Parametreler
    ------------
    page : str
        PAGE_ACCESS anahtarı — "triaj" veya "doktor".
    """
    # 1) KVKK kapısı — eskiden yalnızca triaj sayfasında vardı
    if not st.session_state.get("kvkk_accepted"):
        st.session_state.app_step = "kvkk"
        st.switch_page("app.py")
        st.stop()

    # 2) Rol kapısı
    if not is_logged_in():
        st.session_state.app_step = "role"
        st.switch_page("app.py")
        st.stop()

    # 3) Yetki kapısı
    allowed = PAGE_ACCESS.get(page, ROLES)
    role = st.session_state.get("user_role")
    if role not in allowed:
        st.error(
            f"Bu sayfaya erişim yetkiniz yok. "
            f"Geçerli rolünüz: **{ROLE_LABELS.get(role, role)}**. "
            f"Bu sayfa yalnızca "
            f"{', '.join(ROLE_LABELS[r] for r in allowed)} rolüne açıktır."
        )
        if st.button("← Kendi paneline dön", type="primary"):
            st.switch_page(ROLE_HOME.get(role, "pages/1_Triaj_Kayit.py"))
        st.stop()


def render_user_chip() -> str:
    """Sayfa başlığında gösterilecek küçük kullanıcı rozeti (HTML)."""
    user = current_user()
    if not user["name"]:
        return ""
    initial = user["name"].strip()[:1].upper()
    return (
        '<div style="display:flex;align-items:center;gap:8px;'
        'font-family:var(--font-sans);">'
        '<div style="width:28px;height:28px;border-radius:50%;'
        'background:var(--color-brand);color:#fff;display:flex;'
        'align-items:center;justify-content:center;font-size:12px;'
        f'font-weight:700;">{initial}</div>'
        '<div style="line-height:1.2;">'
        f'<div style="font-size:13px;font-weight:600;color:var(--color-ink);">'
        f'{user["name"]}</div>'
        f'<div style="font-size:12px;color:var(--color-ink-secondary);">'
        f'{user["role_label"]}</div>'
        '</div></div>'
    )
