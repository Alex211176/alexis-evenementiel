"""
Génère un refresh token Dropbox (accès hors-ligne) pour le App folder.

    pip install dropbox
    python get_refresh_token.py
"""

from dropbox import DropboxOAuth2FlowNoRedirect


def main() -> None:
    app_key = input("App key Dropbox : ").strip()
    app_secret = input("App secret Dropbox : ").strip()

    flow = DropboxOAuth2FlowNoRedirect(
        app_key, consumer_secret=app_secret, token_access_type="offline"
    )
    print("\n1) Ouvre cette URL, connecte-toi et autorise :\n")
    print("   " + flow.start() + "\n")
    code = input("2) Colle le code d'autorisation ici : ").strip()

    try:
        result = flow.finish(code)
    except Exception as exc:  # noqa: BLE001
        print("\nÉchec : " + str(exc))
        return

    print("\n--- À coller dans config.json ou dans Render ---")
    print("AE_DROPBOX_APP_KEY       =", app_key)
    print("AE_DROPBOX_APP_SECRET    =", app_secret)
    print("AE_DROPBOX_REFRESH_TOKEN =", result.refresh_token)


if __name__ == "__main__":
    main()
