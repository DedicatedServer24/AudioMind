"""Login/Logout-Logik mit streamlit-authenticator."""

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader


def load_auth_config() -> dict:
    """Lädt die Auth-Konfiguration aus config.yaml."""
    with open("config.yaml") as f:
        return yaml.load(f, Loader=SafeLoader)


def create_authenticator(config: dict) -> stauth.Authenticate:
    """Erstellt das Authenticator-Objekt."""
    return stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )


def show_login(authenticator: stauth.Authenticate):
    """Zeigt das Login-Formular und verarbeitet den Login."""
    try:
        authenticator.login()
    except Exception as e:
        st.error(e)

    if st.session_state.get("authentication_status") is False:
        st.error("Benutzername oder Passwort falsch.")
    elif st.session_state.get("authentication_status") is None:
        st.warning("Bitte Benutzername und Passwort eingeben.")
