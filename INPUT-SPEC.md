# INPUT-SPEC — competitive-shelf-intelligence (client mode)

What to hand the tool in a client engagement. One shelf-observation file (one row
per product observation), CSV or XLSX. Derived from the price-snapshot schema the
queries consume (`app/data.py`), not the README.

## Required columns

| Canonical | Type | Used for |
|---|---|---|
| `retailer` | string | Retailer/store the observation is from. §1 |
| `brand` | string | Product brand (own vs competitor set). §1 |
| `product` | string | Product/listing name. §1 |
| `price` | number ≥ 0 | Observed shelf price (dollars). §1 |
| `pack_weight_oz` | number ≥ 0 | Pack weight (oz) → price per ounce. §1 |
| `observed_date` | date | Date of the shelf observation (defines the window). §1 |

## Optional column

| Canonical | Type | Unlocks |
|---|---|---|
| `in_stock` | true/false | Out-of-stock rate. Absent → OOS omitted. |

## Honest provenance (required — §2)

Competitive-shelf data must carry an **explicit, client-attested source**. Client
mode **refuses to run** without a `provenance` note in `engagement.yml` — this tool
never presents data as scraped/collected that wasn't (synthetic-presented-as-scraped
cannot survive into a client deliverable):

```yaml
provenance: "In-store price audits conducted by the client, Jan 2026 — client-collected."
as_of_date: "2026-01-31"        # analysis anchor; NEVER today's date
basis:
  own_brand: "Meridian"          # which brand is "own" vs the competitive set
```

The provenance note is printed prominently on the deliverable.

## Run

```bash
pip install -e ../engagement-template/lib
python client_mode.py --config engagement.yml --input client-data/shelf.csv \
    --out client-output [--final]
```

Output to `client-output/` (gitignored): a branded, provenance-footed,
DRAFT-watermarked `competitive-shelf-summary.html` (own-brand vs competitor price
per ounce by retailer, gap, OOS rate — with the observation window + the attested
provenance) + `json/summary.json`; or a Data Readiness Report if a required column
or the provenance note is missing. The demo Dash app is never edited (golden-locked).
