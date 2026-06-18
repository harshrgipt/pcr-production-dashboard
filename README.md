# PCR Production Dashboard

A Streamlit dashboard that fetches live PCR tyre production data from SAP and displays it at SKU / material level.

## What it shows

- Total tyres produced, scrap, and SKU count for the selected period
- Bar chart — top N SKUs by production quantity
- Daily production trend line
- Searchable SKU detail table with download (Excel / CSV)

## Requirements

- Python 3.9+
- SAP OData API access (Plant 1300, internal network)

## Setup

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

## Usage

1. Open the app in your browser (Streamlit will open it automatically)
2. Select **This Month** or pick a custom date range in the sidebar
3. Click **Fetch from SAP** — data loads directly from SAP with a live progress bar
4. Use the search box to filter by SKU, or filter by status
5. Download the result as Excel or CSV

## Data source

SAP OData API — Plant 1300, Material Type ZFGS (Finished Tyres), Material Group 1125 (PCR)

Production quantities shown are SAP-confirmed cured tyre output per SKU.
