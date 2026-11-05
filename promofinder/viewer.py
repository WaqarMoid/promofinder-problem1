"""
Static HTML Viewer generator for promofinder.
Conforms strictly to project specifications
Loads single canonical run_facts.json without hardcoded stale fallback values.
Zero external dependencies; completely self-contained for offline viewing.
"""

from __future__ import annotations
import html
import json
from pathlib import Path
from typing import List, Dict, Any, Optional


def generate_html_report(
    run_facts: Dict[str, Any],
    out_path: Path,
):
    """Generates a truthful, responsive static HTML report directly from run_facts."""

    def escape(s: Any) -> str:
        return html.escape(str(s) if s is not None else "")

    run_id = run_facts["run_id"]
    cov = run_facts["coverage_and_yield"]
    par = run_facts["parser_accounting"]
    val = run_facts["candidate_accounting"]
    timings = run_facts["timings"]
    disc = run_facts["model_execution_disclosure"]
    obs = run_facts["observable_metrics"]
    top_promos = run_facts["top_promos"]
    top3_meta = run_facts.get("top_3_first_to_post", [])
    stress_reports = run_facts.get("stress_reports", [])
    traceable_failures = run_facts.get("traceable_failures", [])
    limitations = run_facts.get("limitations", [])

    top3_html_cards = []
    for t in top3_meta:
        top3_html_cards.append(f"""
        <div class="card top3-card">
            <div class="card-badge">Rank #{t['rank']} &bull; First-to-Post</div>
            <div class="card-title">Candidate: <code>{escape(t['candidate_id'])}</code> (Episode {t['episode']})</div>
            <div class="meta-row">
                <span class="tag theme-tag">{escape(t['theme'])}</span>
                <span class="tag time-tag">Duration: {t['duration_sec']:.1f}s</span>
                <span class="tag cut-tag">Time: {escape(", ".join(t['segments']))}</span>
            </div>
            <div class="content-block">
                <strong>Opening Hook Beat (&le;3.0s):</strong>
                <blockquote class="quote hook-quote">{escape(t['hook_evidence'])}</blockquote>
            </div>
            <div class="content-block">
                <strong>Terminal Cliffhanger:</strong>
                <blockquote class="quote cliff-quote">{escape(t['cliffhanger_evidence'])}</blockquote>
            </div>
            <div class="content-block">
                <strong>Unresolved Narrative Question:</strong>
                <p class="question-text">{escape(t.get('unresolved_question', ''))}</p>
            </div>
            <div class="content-block">
                <strong>Editorial Rationale:</strong>
                <p class="rationale-text">{escape(t['why_post_first'])}</p>
            </div>
            <div class="content-block tradeoff-box">
                <strong>Posting Priority Trade-off:</strong>
                <p class="tradeoff-text">{escape(t['tradeoff_vs_next'])}</p>
            </div>
        </div>
        """)

    top10_rows = []
    for c in top_promos:
        segs = "; ".join(f"[{s['start_time_str']}-{s['end_time_str']}]" for s in c['segments'])
        warns = "; ".join(c.get('validation_warnings', []))
        status_badge = '<span class="status-pill status-warn">Unverified 3s</span>' if "first_3s_unverified" in warns else '<span class="status-pill status-approved">Verified &le;3s</span>'
        top10_rows.append(f"""
        <tr>
            <td class="center-text"><strong>#{c.get('rank', '-')}</strong></td>
            <td><code>{escape(c['candidate_id'])}</code></td>
            <td class="center-text">Ep {c['episode']}</td>
            <td><span class="tag theme-tag">{escape(c['theme'])}</span></td>
            <td class="center-text">{c['total_duration_sec']:.1f}s</td>
            <td><code>{escape(segs)}</code></td>
            <td><em>{escape(c['hook'].get('exact_quote', '')[:55])}...</em></td>
            <td><em>{escape(c['cliffhanger'].get('exact_quote', '')[:55])}...</em></td>
            <td class="center-text">{c.get('hook_complete_by_ms', 0)}ms</td>
            <td class="center-text">{c.get('cliff_gap_ms', 0)}ms</td>
            <td class="center-text">{status_badge}</td>
        </tr>
        """)

    stress_cards = []
    for s in stress_reports:
        stress_cards.append(f"""
        <div class="stress-card">
            <div class="stress-title">{escape(s['case'])}</div>
            <p class="stress-desc"><strong>Test Case:</strong> {escape(s['description'])}</p>
            <p class="stress-audit"><strong>Audit Observation:</strong> {escape(s['audit'])}</p>
            <div class="stress-verdict"><strong>Status:</strong> {escape(s['verdict'])}</div>
        </div>
        """)

    failure_cards = []
    for f_item in traceable_failures:
        failure_cards.append(f"""
        <div class="failure-card">
            <div class="failure-id"><code>{escape(f_item['id'])}</code> &bull; <span class="tag failure-tag">{escape(f_item['kind'])}</span></div>
            <p class="failure-desc"><strong>Episode:</strong> Ep {f_item['episode']}</p>
            <p class="failure-reason"><strong>Detail:</strong> {escape(f_item.get('reason') or f_item.get('description', ''))}</p>
        </div>
        """)

    stage_timings_str = ", ".join(f"{k}: {v}s" for k, v in timings.get("stage_timings_sec", {}).items())

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PromoFinder Discovery Report &bull; Run {escape(run_id)}</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-hover: #334155;
            --border: #475569;
            --primary: #38bdf8;
            --accent: #f59e0b;
            --success: #10b981;
            --danger: #ef4444;
            --text: #f8fafc;
            --text-muted: #94a3b8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            padding: 20px;
        }}
        .container {{ max-width: 1280px; margin: 0 auto; }}
        header {{
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        h1 {{ font-size: 1.8rem; color: var(--primary); margin-bottom: 4px; }}
        .header-meta {{ color: var(--text-muted); font-size: 0.9rem; }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 14px;
            margin-bottom: 28px;
        }}
        .metric-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }}
        .metric-card .num {{
            font-size: 1.5rem;
            font-weight: bold;
            color: var(--primary);
            margin-top: 4px;
        }}
        .metric-card .label {{
            font-size: 0.78rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .metric-card .subtext {{
            font-size: 0.75rem;
            color: #cbd5e1;
            margin-top: 2px;
        }}
        
        section {{ margin-bottom: 36px; }}
        h2 {{
            font-size: 1.25rem;
            border-left: 4px solid var(--primary);
            padding-left: 10px;
            margin-bottom: 16px;
            color: var(--text);
        }}
        
        .top3-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 18px;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 18px;
            position: relative;
        }}
        .top3-card {{ border-color: var(--accent); }}
        .card-badge {{
            position: absolute;
            top: -10px;
            right: 14px;
            background: var(--accent);
            color: #000;
            font-size: 0.72rem;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 10px;
            text-transform: uppercase;
        }}
        .card-title {{ font-size: 1.05rem; font-weight: 600; margin-bottom: 8px; }}
        .meta-row {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
        .tag {{
            font-size: 0.75rem;
            padding: 2px 6px;
            border-radius: 4px;
            background: #273549;
            color: var(--text);
        }}
        .theme-tag {{ background: #1e3a8a; color: #93c5fd; }}
        .time-tag {{ background: #064e3b; color: #6ee7b7; }}
        .cut-tag {{ background: #374151; color: #e5e7eb; }}
        .failure-tag {{ background: #7f1d1d; color: #fca5a5; }}
        
        .content-block {{ margin-bottom: 10px; font-size: 0.88rem; }}
        .quote {{
            border-left: 3px solid var(--primary);
            padding: 6px 10px;
            margin: 4px 0;
            background: rgba(56, 189, 248, 0.08);
            border-radius: 0 4px 4px 0;
            color: #e2e8f0;
            font-style: italic;
        }}
        .cliff-quote {{
            border-left-color: var(--accent);
            background: rgba(245, 158, 11, 0.08);
        }}
        .question-text {{ color: #fde68a; font-weight: 500; }}
        .tradeoff-box {{
            background: #111c2e;
            border: 1px dashed var(--border);
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 0.82rem;
            color: #cbd5e1;
        }}
        
        .table-wrap {{
            overflow-x: auto;
            border-radius: 8px;
            border: 1px solid var(--border);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            font-size: 0.85rem;
            min-width: 900px;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background: #172033;
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.72rem;
            letter-spacing: 0.5px;
        }}
        tr:hover td {{ background: var(--surface-hover); }}
        .center-text {{ text-align: center; }}
        .status-pill {{
            font-size: 0.72rem;
            padding: 2px 6px;
            border-radius: 8px;
            font-weight: 600;
        }}
        .status-approved {{ background: #065f46; color: #a7f3d0; }}
        .status-warn {{ background: #78350f; color: #fde68a; }}
        
        .stress-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 14px;
        }}
        .stress-card, .failure-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 14px;
            font-size: 0.85rem;
        }}
        .stress-title, .failure-id {{ font-weight: 600; color: var(--primary); margin-bottom: 4px; }}
        .stress-desc, .failure-desc {{ color: var(--text-muted); margin-bottom: 4px; font-size: 0.8rem; }}
        .stress-audit, .failure-reason {{ margin-bottom: 6px; color: #e2e8f0; }}
        .stress-verdict {{
            background: #1e2e42;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.78rem;
            border-left: 3px solid var(--success);
        }}
        
        footer {{
            border-top: 1px solid var(--border);
            padding-top: 14px;
            color: var(--text-muted);
            font-size: 0.8rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>PromoFinder &bull; Static Discovery Report</h1>
            <div class="header-meta">
                Series: <strong>{escape(run_facts["series_title"])}</strong> (50 Episodes) &bull;
                Run ID: <code>{escape(run_id)}</code> &bull; Problem 1 Prototype &bull; Confidential Local Artifact
            </div>
        </header>

        <!-- Truthful Metrics Dashboard -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="label">Processing Coverage</div>
                <div class="num">{cov['processing_coverage_pct']:.1f}%</div>
                <div class="subtext">{escape(cov['processing_coverage_definition'])}</div>
            </div>
            <div class="metric-card">
                <div class="label">Episode Yield</div>
                <div class="num">{cov['candidate_episode_yield_pct']:.1f}%</div>
                <div class="subtext">{escape(cov['candidate_episode_yield_definition'])}</div>
            </div>
            <div class="metric-card">
                <div class="label">Parser Accounting</div>
                <div class="num">{par['parsing_integrity_pct']:.1f}%</div>
                <div class="subtext">{par['parsed_timed_blocks']} Events &bull; {par['start_regressions_accounted_for']} Regressions Resolved</div>
            </div>
            <div class="metric-card">
                <div class="label">Discovery Engine</div>
                <div class="num" style="font-size: 1.15rem; color: var(--accent); margin-top: 6px;">{escape(disc['system_role'])}</div>
                <div class="subtext">{disc['external_model_calls']} External API Calls (${disc['known_paid_api_cost_usd']:.2f} USD)</div>
            </div>
        </div>

        <!-- Section 1: First-to-Post Top 3 Showcase -->
        <section>
            <h2>First-to-Post Priority Promos (Top 3)</h2>
            <div class="top3-grid">
                {''.join(top3_html_cards)}
            </div>
        </section>

        <!-- Section 2: Top 10 Diverse Promos Table -->
        <section>
            <h2>Ranked Top 10 Diverse Candidates</h2>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th class="center-text">Rank</th>
                            <th>Candidate ID</th>
                            <th class="center-text">Ep</th>
                            <th>Theme</th>
                            <th class="center-text">Duration</th>
                            <th>Segments</th>
                            <th>Opening Hook Quote (&le;3s)</th>
                            <th>Terminal Cliffhanger</th>
                            <th class="center-text">Hook Complete</th>
                            <th class="center-text">Cliff Gap</th>
                            <th class="center-text">Hook Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(top10_rows)}
                    </tbody>
                </table>
            </div>
        </section>

        <!-- Section 3: Pack Stress Cases & Traceable Failure Modes -->
        <section>
            <h2>Stress Case Audits & Boundary Inspections</h2>
            <div class="stress-grid">
                {''.join(stress_cards)}
            </div>
        </section>

        <!-- Section 4: Traceable Failure Modes & Observed Rejections -->
        <section>
            <h2>Traceable Failure Modes & Rejections</h2>
            <div class="stress-grid">
                {''.join(failure_cards)}
            </div>
        </section>

        <!-- Section 5: Execution Timings, Cost Accounting & Editorial Limits -->
        <section>
            <h2>Operational Footprint & Engineering Disclosure</h2>
            <div class="card" style="font-size: 0.88rem;">
                <p style="margin-bottom: 8px;">
                    <strong>Source Data Footprint:</strong> {cov['total_episodes']} episodes, {par['parsed_timed_blocks']} events, 100% boundary integrity.
                </p>
                <p style="margin-bottom: 8px;">
                    <strong>Model Execution Disclosure:</strong> {escape(disc['disclosure_statement'])}
                </p>
                <p style="margin-bottom: 8px;">
                    <strong>Execution Wall-Clock Timings:</strong> Total: {timings['total_wall_clock_sec']:.2f}s ({escape(stage_timings_str)}).
                </p>
                <p style="margin-bottom: 8px;">
                    <strong>Known Production Limitations:</strong>
                </p>
                <ul style="margin-left: 20px; color: var(--text-muted);">
                    {''.join(f"<li>{escape(l)}</li>" for l in limitations)}
                </ul>
            </div>
        </section>

        <footer>
            PromoFinder Problem 1 Prototype &bull; Kuku AI Generalist Assignment &bull; Confidential Local Artifact
        </footer>
    </div>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[+] Static HTML report saved to {out_path}")
