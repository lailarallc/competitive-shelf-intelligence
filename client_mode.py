"""Client-mode CLI for competitive-shelf-intelligence.

Analyze a client's own shelf/pricing observations — price positioning (own brand
vs competitors, per ounce) and out-of-stock rate — validated, never committed,
never deployed. The demo Dash app is untouched.

Provenance is HONEST and explicit: the deliverable states where the data came
from (a required, client-attested `provenance` note in engagement.yml) and the
observation window. This tool never presents data as scraped/collected that
wasn't — synthetic-presented-as-scraped can't survive into a client deliverable.

Usage:
    python client_mode.py --config engagement.yml --input client-data/shelf.csv \
        --out client-output [--final]
"""

from __future__ import annotations

import argparse
import collections
import html
import json
from pathlib import Path

from lailara_engagement import (
    ColumnSpec,
    PreflightSpec,
    build_provenance,
    load_config,
    read_table,
    run_preflight,
    validation_status_label,
    write_report,
)
from lailara_engagement import palette as P
from lailara_engagement.provenance import Provenance

TOOL = "competitive-shelf-intelligence"
TOOL_VERSION = "1.0"
_IN_STOCK_TRUE = {"true", "1", "yes", "y", "in stock", "in_stock", "instock", "available"}


def _spec() -> PreflightSpec:
    return PreflightSpec(
        tool=TOOL, version=TOOL_VERSION,
        columns=[
            ColumnSpec(name="retailer", dtype="string", required=True,
                       description="retailer/store the observation is from", spec_ref="INPUT-SPEC §1"),
            ColumnSpec(name="brand", dtype="string", required=True,
                       description="product brand", spec_ref="INPUT-SPEC §1"),
            ColumnSpec(name="product", dtype="string", required=True,
                       description="product/listing name", spec_ref="INPUT-SPEC §1"),
            ColumnSpec(name="price", dtype="number", required=True, not_negative=True,
                       description="observed shelf price (dollars)", spec_ref="INPUT-SPEC §1"),
            ColumnSpec(name="pack_weight_oz", dtype="number", required=True, not_negative=True,
                       description="pack weight (oz) for price-per-oz", spec_ref="INPUT-SPEC §1"),
            ColumnSpec(name="observed_date", dtype="date", required=True,
                       description="date of the shelf observation", spec_ref="INPUT-SPEC §1"),
            ColumnSpec(name="in_stock", dtype="string", required=False, allow_blank=True,
                       description="in stock true/false (for OOS rate)"),
        ],
    )


def _num(v) -> float:
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return 0.0


def run(config_path: str, input_path: str, out_dir: str, *, final: bool = False) -> dict:
    config = load_config(config_path)
    read = read_table(input_path)
    report = run_preflight(read, _spec(), config)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    provenance = build_provenance(
        tool=TOOL, tool_version=TOOL_VERSION, inputs=[read], config=config,
        validation_status=validation_status_label(report.status, report.n_warnings))

    own_brand = (config.basis.get("own_brand") or config.client_name or "").strip()
    data_provenance = (config.raw.get("provenance") or config.basis.get("provenance") or "").strip()

    findings_ok = report.passed
    if not data_provenance:
        # Honest provenance is mandatory: refuse to produce a competitive-shelf
        # deliverable without an explicit, client-attested data source.
        from lailara_engagement import Finding
        report.findings.append(Finding(
            severity="error", category="missing-provenance",
            message=("engagement.yml is missing a `provenance` note — competitive-shelf "
                     "data must carry an explicit, client-attested source (how/when it was "
                     "collected). This tool never presents data as scraped that wasn't."),
            spec_ref="INPUT-SPEC §2"))
        report.status = "failed"
        report.passed = False
        findings_ok = False

    if not report.passed:
        paths = write_report(report, config, str(out), provenance=provenance,
                             draft=not final, basename="data-readiness-report",
                             title="Competitive-Shelf Data Readiness Report")
        return {"status": "blocked", "readiness_report": paths["html"]}

    m = report.column_mapping
    frame = read.frame

    def col(name):
        r = m.get(name)
        return frame[r] if r else None

    by_retailer = collections.defaultdict(lambda: {"own": [], "comp": []})
    in_stock_col = col("in_stock")
    n_obs = len(frame)
    in_stock_yes = in_stock_total = 0
    dates = []
    for i in range(n_obs):
        retailer = str(col("retailer").iloc[i]).strip()
        brand = str(col("brand").iloc[i]).strip()
        price = _num(col("price").iloc[i]); oz = _num(col("pack_weight_oz").iloc[i])
        ppo = (price / oz) if oz else None
        dates.append(str(col("observed_date").iloc[i]).strip())
        is_own = own_brand and brand.casefold() == own_brand.casefold()
        if ppo is not None:
            by_retailer[retailer]["own" if is_own else "comp"].append(ppo)
        if in_stock_col is not None:
            v = str(in_stock_col.iloc[i]).strip()
            if v:
                in_stock_total += 1
                if v.casefold() in _IN_STOCK_TRUE:
                    in_stock_yes += 1

    def avg(xs):
        return round(sum(xs) / len(xs), 4) if xs else None

    rows = []
    for r, d in sorted(by_retailer.items()):
        own = avg(d["own"]); comp = avg(d["comp"])
        gap = round(own - comp, 4) if (own is not None and comp is not None) else None
        rows.append({"retailer": r, "own_price_per_oz": own, "competitor_price_per_oz": comp,
                     "gap_per_oz": gap, "own_n": len(d["own"]), "comp_n": len(d["comp"])})

    oos_rate = round(1 - in_stock_yes / in_stock_total, 4) if in_stock_total else None
    summary = {
        "own_brand": own_brand,
        "provenance": data_provenance,
        "observation_window": {"first": min(dates) if dates else None, "last": max(dates) if dates else None},
        "observations": n_obs,
        "by_retailer": rows,
        "oos_rate": oos_rate,
    }
    json_dir = out / "json"; json_dir.mkdir(parents=True, exist_ok=True)
    (json_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report_path = out / "competitive-shelf-summary.html"
    report_path.write_text(_summary_html(config, summary, provenance, draft=not final), encoding="utf-8")
    return {"status": "ok", "observations": n_obs, "retailers": len(rows),
            "report": str(report_path), "summary_json": str(json_dir / "summary.json"),
            "n_warnings": report.n_warnings}


def _summary_html(config, s, provenance: Provenance, *, draft: bool) -> str:
    esc = html.escape
    ow = s["observation_window"]

    def _ppo(v):
        return "—" if v is None else f"${v:,.3f}/oz"

    def _gap(v):
        return "—" if v is None else (f"+${v:,.3f}" if v >= 0 else f"-${abs(v):,.3f}")

    rows = "".join(
        f"<tr><td>{esc(r['retailer'])}</td><td class=num>{_ppo(r['own_price_per_oz'])}</td>"
        f"<td class=num>{_ppo(r['competitor_price_per_oz'])}</td><td class=num>{_gap(r['gap_per_oz'])}</td>"
        f"<td class=num>{r['own_n']}/{r['comp_n']}</td></tr>"
        for r in s["by_retailer"])
    oos = "—" if s["oos_rate"] is None else f"{s['oos_rate']*100:.1f}%"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>Competitive Shelf — {esc(config.client_name)}</title><style>{_css(draft)}</style></head>
<body class="{' ll-draft' if draft else ''}"><main class=ll-page>
<header class=ll-header>
  <div class=ll-eyebrow>Lailara LLC · Competitive Shelf Intelligence</div>
  <h1 class=ll-title>Price Positioning</h1>
  <div class=ll-client>
    <div><span class=ll-k>Client</span> {esc(config.client_name)}</div>
    <div><span class=ll-k>Own brand</span> {esc(s['own_brand'])}</div>
    <div><span class=ll-k>Observed</span> {esc(str(ow['first']))} to {esc(str(ow['last']))}</div>
    <div><span class=ll-k>Observations</span> {s['observations']:,}</div>
  </div>
</header>
<section class=ll-provenance-note style="background:{P.LL_SG_SURFACE};color:{P.LL_SG_DARK};padding:12px 16px;border-radius:2px;margin-bottom:24px;font-size:13px">
  <strong>Data provenance:</strong> {esc(s['provenance'])}
</section>
<section class=ll-banner>
  <div class=ll-score>{len(s['by_retailer'])} retailers</div>
  <div>own-brand vs competitor price per ounce{'' if s['oos_rate'] is None else f' · {oos} out of stock'}</div>
</section>
<section class=ll-section>
  <h2 class=ll-h2>Price per ounce by retailer</h2>
  <table class=ll-table><thead><tr><th>Retailer</th><th>Own $/oz</th><th>Competitor $/oz</th>
  <th>Gap</th><th>Own/Comp obs</th></tr></thead><tbody>{rows}</tbody></table>
  <p class=ll-note>Price per ounce = observed price / pack weight. Gap = own − competitor
  average (positive = priced above the competitive set). Figures reflect only the
  observations in the provided file, over the window above.</p>
</section>
{provenance.to_html()}
</main></body></html>"""


def _css(draft: bool) -> str:
    draft_css = (
        ".ll-draft::before{content:'DRAFT';position:fixed;top:50%;left:50%;"
        "transform:translate(-50%,-50%) rotate(-32deg);font-family:var(--s);"
        "font-size:22vw;font-weight:700;color:rgba(204,16,10,.06);z-index:0;"
        "pointer-events:none;white-space:nowrap}" if draft else ""
    )
    return f"""
:root{{--s:{P.LL_SERIF};--f:{P.LL_SANS}}}*{{box-sizing:border-box}}
body{{margin:0;background:{P.LL_CANVAS};color:{P.LL_TEXT};font-family:var(--f);line-height:1.6}}
.ll-page{{position:relative;z-index:1;max-width:{P.LL_MAX_WIDTH};margin:0 auto;padding:48px 24px}}
.ll-header{{border-bottom:1px solid {P.LL_GRIDLINE};padding-bottom:24px;margin-bottom:24px}}
.ll-eyebrow{{font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:{P.LL_RED};font-weight:600}}
.ll-title{{font-family:var(--s);font-weight:700;color:{P.LL_INK};font-size:34px;margin:8px 0 16px}}
.ll-client{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px 24px;font-size:14px}}
.ll-k{{display:block;color:{P.LL_TEXT_SEC};font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
.ll-banner{{border-radius:2px;padding:16px 20px;margin-bottom:32px;background:{P.LL_HK_SURFACE};color:{P.LL_HK_DARK}}}
.ll-score{{font-family:var(--s);font-weight:700;font-size:22px}}
.ll-section{{margin:0 0 32px}}
.ll-h2{{font-family:var(--s);font-weight:700;color:{P.LL_INK};font-size:22px;
margin:0 0 12px;padding-bottom:6px;border-bottom:1px solid {P.LL_GRIDLINE}}}
.ll-note{{font-size:13px;color:{P.LL_TEXT_SEC};margin-top:8px}}
.ll-table{{width:100%;border-collapse:collapse;font-size:14px}}
.ll-table th{{text-align:left;background:{P.LL_CHICAGO};color:#fff;padding:8px 12px}}
.ll-table td{{padding:8px 12px;border-bottom:1px solid {P.LL_GRIDLINE}}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.ll-provenance{{margin-top:40px;background:{P.LL_CARD_BG};color:{P.LL_CARD_TEXT};
padding:20px 24px;border-radius:2px;font-size:13px}}
.ll-prov-title{{font-family:var(--s);font-weight:700;font-size:16px;margin-bottom:8px}}
.ll-provenance div{{margin-bottom:4px;color:{P.LL_CARD_SUBTITLE}}}
.ll-provenance strong{{color:{P.LL_CARD_TEXT}}}
.ll-prov-inputs{{width:100%;border-collapse:collapse;margin-top:8px}}
.ll-prov-inputs th{{text-align:left;border-bottom:1px solid rgba(255,255,255,.12);padding:4px 8px;color:{P.LL_CARD_MUTED}}}
.ll-prov-inputs td{{padding:4px 8px;border-bottom:1px solid rgba(255,255,255,.08);color:{P.LL_CARD_SUBTITLE}}}
.ll-prov-brand{{margin-top:12px;font-family:var(--s);color:{P.LL_CARD_MUTED}}}
{draft_css}
@media print{{body{{background:#fff}}}}
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="competitive-shelf-intelligence client mode")
    ap.add_argument("--config", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="client-output")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args(argv)
    result = run(args.config, args.input, args.out, final=args.final)
    if result["status"] == "blocked":
        print(f"BLOCKED — data not ready. See {result['readiness_report']}")
        return 3
    print(f"analyzed {result['observations']:,} observations across {result['retailers']} retailers")
    print(f"report -> {result['report']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
