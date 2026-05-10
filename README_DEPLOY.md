# Streamlit Trade Journal

This is a Streamlit conversion of your Flask trade journal project.

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy to Streamlit Community Cloud

1. Create a GitHub repository.
2. Upload these files.
3. In Streamlit Cloud, deploy `streamlit_app.py`.

## Important database note

This starter uses SQLite (`trades_streamlit.db`). That works locally and for demos, but Streamlit Cloud storage can reset. For a real production trading journal, migrate the database to PostgreSQL/Supabase.

## What is converted

- CSV upload imports for IBKR, Wealthsimple, NinjaTrader Performance CSV.
- Duplicate protection.
- Portfolio selector.
- Dashboard metrics.
- Monthly P&L calendar with IBKR / NinjaTrader / Wealthsimple platform totals.
- Trades table.
- Monthly analysis.
- CSV export.

## Folder automation note

Streamlit Cloud cannot read folders from your local computer. Folder auto-import can only work when running Streamlit locally on the same computer as the export folder. For cloud deployment, use the upload workflow.
