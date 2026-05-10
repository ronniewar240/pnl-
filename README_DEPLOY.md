# Streamlit Trade Journal Starter

This is a deployable Streamlit starter version of the trading journal.

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Deploy to Streamlit Community Cloud

1. Create a GitHub repo.
2. Upload these files.
3. In Streamlit Cloud, deploy `streamlit_app.py`.

## Important

This starter uses SQLite by default. Streamlit Cloud storage can reset/rebuild, so for real production use move the database to PostgreSQL/Supabase.

## What is included

- CSV upload/import
- Duplicate protection
- Dashboard KPIs
- Monthly P&L calendar
- Platform P&L split: IBKR, NinjaTrader, Wealthsimple
- Trades table with buy/sell price
- Export CSV

For a full 1:1 migration, upload your latest Flask `app.py`/project zip and merge its custom parsers/routes into this Streamlit shell.
