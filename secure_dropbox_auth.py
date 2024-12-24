import os
import sys
import logging
import certifi
from dropbox import Dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
from config import get_dropbox_app_key, get_dropbox_app_secret, get_dropbox_refresh_token

class SecureDropboxAuth:
    def __init__(self):
        self.app_key = get_dropbox_app_key()
        self.app_secret = get_dropbox_app_secret()
        self.refresh_token = get_dropbox_refresh_token()

    def get_certifi_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.join(sys._MEIPASS, 'cacert.pem')
        return certifi.where()

    def get_dropbox_client(self):
        if not all([self.app_key, self.app_secret, self.refresh_token]):
            logging.error("Manglende Dropbox-legitimationsoplysninger")
            return None

        try:
            os.environ['REQUESTS_CA_BUNDLE'] = self.get_certifi_path()
            return Dropbox(
                oauth2_refresh_token=self.refresh_token,
                app_key=self.app_key,
                app_secret=self.app_secret
            )
        except Exception as e:
            logging.error(f"Fejl ved oprettelse af Dropbox-klient: {e}")
            return None

    def initiate_new_oauth_flow(self):
        auth_flow = DropboxOAuth2FlowNoRedirect(self.app_key, self.app_secret)
        authorize_url = auth_flow.start()
        print(f"1. Gå til: {authorize_url}")
        print("2. Klik 'Tillad' (du skal muligvis logge ind først)")
        print("3. Kopier autorisationskoden.")
        auth_code = input("Indtast autorisationskoden her: ").strip()

        try:
            oauth_result = auth_flow.finish(auth_code)
            self.refresh_token = oauth_result.refresh_token
            return self.get_dropbox_client()
        except Exception as e:
            logging.error(f"Fejl under OAuth-flow: {e}")
            return None