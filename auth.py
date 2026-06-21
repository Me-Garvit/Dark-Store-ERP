import hashlib
import hmac
import streamlit as st
from streamlit_cookies_controller import CookieController

_COOKIE_NAME = "ats_auth"
_COOKIE_TTL  = 7  # days


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def _expected_cookie_value() -> str:
    salt = st.secrets.get("ADMIN_SALT", "")
    user = st.secrets.get("ADMIN_USERNAME", "")
    return hmac.new(salt.encode(), user.encode(), hashlib.sha256).hexdigest()


def check_auth() -> bool:
    if st.session_state.get("authenticated", False):
        return True
    try:
        controller = CookieController()
        token = controller.get(_COOKIE_NAME)
        if token and token == _expected_cookie_value():
            st.session_state.authenticated = True
            return True
    except Exception:
        pass
    return False


def login_page():
    st.markdown("""
    <style>
      section.main > div { padding-top: 60px; }
      .login-title { font-size: 26px; font-weight: 700; color: #f1f5f9; margin-bottom: 4px; }
      .login-sub   { font-size: 14px; color: #64748b; margin-bottom: 28px; }
    </style>
    """, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown('<div class="login-title">Dark Store Tracker</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-sub">Admin access only. Enter your credentials to continue.</div>', unsafe_allow_html=True)

        username = st.text_input("Username", placeholder="admin")
        password = st.text_input("Password", type="password", placeholder="••••••••")

        if st.button("Login", type="primary", use_container_width=True):
            _verify(username, password)


def _verify(username: str, password: str):
    try:
        expected_user = st.secrets["ADMIN_USERNAME"]
        expected_hash = st.secrets["ADMIN_PASSWORD_HASH"]
        salt          = st.secrets["ADMIN_SALT"]
    except KeyError:
        st.error("Auth credentials not configured in secrets.toml.")
        return

    if username == expected_user and _hash(password, salt) == expected_hash:
        st.session_state.authenticated = True
        try:
            controller = CookieController()
            controller.set(_COOKIE_NAME, _expected_cookie_value(), max_age=_COOKIE_TTL * 86400)
        except Exception:
            pass
        st.rerun()
    else:
        st.error("Invalid username or password.")


def logout():
    st.session_state.authenticated = False
    try:
        controller = CookieController()
        controller.remove(_COOKIE_NAME)
    except Exception:
        pass
    st.rerun()
