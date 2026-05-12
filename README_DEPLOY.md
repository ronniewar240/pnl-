# Streamlit Trade Journal with Dropbox Auto-Import

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Dropbox secrets

Use a Dropbox refresh token for deployment. Add this in Streamlit Cloud → App settings → Secrets:

```toml
[dropbox]
app_key = "YOUR_DROPBOX_APP_KEY"
app_secret = "YOUR_DROPBOX_APP_SECRET"
refresh_token = "YOUR_DROPBOX_REFRESH_TOKEN"
folder = "/TradeJournalExports"
```

A plain access token can work only for quick testing because Dropbox access tokens are usually short-lived.

## How to get a Dropbox refresh token

1. Create a Dropbox app in the Dropbox developer console.
2. Give it file access for the folder/app scope you want.
3. Generate an OAuth authorization URL with `token_access_type=offline`.
4. Authorize the app.
5. Exchange the returned authorization code for a refresh token.
6. Put the refresh token, app key, and app secret into Streamlit secrets.

Once configured, go to the Dropbox auto-import page and click **Scan Dropbox Now**.


## Modern UI refresh

This version includes a cleaner Streamlit UI with a polished sidebar, hero headers, KPI cards, calendar styling, and Dropbox auto-import controls.
