"""
config_builder.py - Visual Config Builder for SPSS Frequency Dashboard

Reads SPSS metadata and lets users:
  - See all variables auto-detected from the file
  - Rename labels
  - Group sub-variables into multi-punch sets
  - Define filter sets
  - Save the resulting JSON

Launched as a subprocess by launcher.py with --spss-path and --port.
Optional --meta-path loads an existing JSON for editing.
"""

import argparse
import json
import os
import sys
from datetime import datetime

import pyreadstat
from dash import Dash, html, dcc, Input, Output, State, ctx, ALL, no_update
import dash_bootstrap_components as dbc


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def parse_arguments():
    parser = argparse.ArgumentParser(description="SPSS Config Builder")
    parser.add_argument("--spss-path", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--meta-path", default=None,
                        help="Existing JSON to pre-populate (optional)")
    return parser.parse_args()


# ─────────────────────────────────────────────
# SPSS metadata reader
# ─────────────────────────────────────────────

# All SPSS format codes that indicate a date, time, or datetime variable.
# original_variable_types values always start with one of these prefixes
# (followed by digits for width, e.g. "DATE11", "ADATE10", "DATETIME23.6").
_SPSS_DATE_TIME_PREFIXES = (
    "DATE",      # dd-mmm-yyyy
    "ADATE",     # mm/dd/yyyy  (American)
    "EDATE",     # dd.mm.yyyy  (European)
    "JDATE",     # Julian      yyyyddd
    "SDATE",     # Sortable    yyyy/mm/dd
    "QYR",       # Quarter-Year
    "MOYR",      # Month-Year
    "WKYR",      # Week-Year
    "WKDAY",     # Day of week
    "MONTH",     # Month name
    "DATETIME",  # dd-mmm-yyyy hh:mm:ss
    "DTIME",     # dd hh:mm:ss
    "TIME",      # hh:mm:ss
    "MTIME",     # mm:ss
)


def _is_datetime_format(fmt_str):
    """Return True if the SPSS original_variable_types string is a date/time format."""
    if not fmt_str:
        return False
    upper = fmt_str.upper().strip()
    return any(upper.startswith(prefix) for prefix in _SPSS_DATE_TIME_PREFIXES)


def read_spss_meta(spss_path):
    """
    Return (column_names, column_labels, value_labels_map, excluded_vars).

    excluded_vars is a dict  {col_name: reason}  for variables that were
    filtered out (string or datetime) so the UI can show a summary.
    """
    _, meta = pyreadstat.read_sav(spss_path, metadataonly=True)

    readstat_types  = meta.readstat_variable_types   # {col: 'double'|'string'}
    original_types  = meta.original_variable_types   # {col: 'F8.2'|'A10'|'DATE11'|...}

    excluded = {}
    clean_names = []

    for col in meta.column_names:
        rtype = readstat_types.get(col, "")
        otype = original_types.get(col, "")

        if rtype == "string":
            excluded[col] = "string variable"
        elif _is_datetime_format(otype):
            excluded[col] = f"date/time variable ({otype})"
        else:
            clean_names.append(col)

    return (
        clean_names,
        meta.column_names_to_labels,
        meta.variable_value_labels,
        excluded,
    )


def auto_detect_variables(column_names, column_labels, value_labels_map=None):
    """
    Heuristically group variables:
    - Columns whose name ends with _1, _2 … and share a common prefix
      are treated as sub-variables of a multi-punch parent.
    - Everything else is single-punch.

    value_labels_map: {col_name: {value: label}} from pyreadstat metadata.
    Single-punch variables get their SPSS value_labels stored in the dict
    so users can edit/reorder them in the UI.

    Returns a list of variable dicts ready for the UI store.
    """
    import re

    # Map prefix → list of (full_name, suffix_int)
    multi_candidates = {}
    for col in column_names:
        m = re.match(r'^(.+?)_(\d+)$', col)
        if m:
            prefix, idx = m.group(1), int(m.group(2))
            multi_candidates.setdefault(prefix, []).append((col, idx))

    # Only treat as multi if there are at least 2 sub-variables
    multi_prefixes = {p for p, subs in multi_candidates.items() if len(subs) >= 2}

    used_as_sub = set()
    for prefix in multi_prefixes:
        for col, _ in multi_candidates[prefix]:
            used_as_sub.add(col)

    variables = []
    seen_prefixes = set()

    for col in column_names:
        label = column_labels.get(col, col)

        if col in used_as_sub:
            prefix = next(
                p for p in multi_prefixes
                if col in [c for c, _ in multi_candidates[p]]
            )
            if prefix not in seen_prefixes:
                seen_prefixes.add(prefix)
                subs = sorted(multi_candidates[prefix], key=lambda x: x[1])
                sub_names = [c for c, _ in subs]
                # Derive a label for the parent from the first sub's label or the prefix
                parent_label = column_labels.get(sub_names[0], prefix)
                # Strip trailing " - 1" / " 1" patterns that fieldwork tools add
                parent_label = re.sub(r'\s*[-–]\s*\d+\s*$', '', parent_label).strip()
                parent_label = re.sub(r'\s+\d+\s*$', '', parent_label).strip()

                variables.append({
                    "id": prefix,
                    "name": prefix,
                    "label": parent_label,
                    "type": "multi",
                    "sub_variables": sub_names,
                    "sub_variable_labels": {
                        c: column_labels.get(c, c) for c in sub_names
                    },
                    "value_labels": {},  # not used for multi
                    "included": True,
                })
        elif col not in used_as_sub:
            # Store SPSS value labels (as string keys for JSON serialisation).
            # These become both the display labels and the display order.
            spss_val_labels = {}
            if value_labels_map and col in value_labels_map:
                spss_val_labels = {
                    str(k): v for k, v in value_labels_map[col].items()
                }
            variables.append({
                "id": col,
                "name": col,
                "label": label,
                "type": "single",
                "sub_variables": [],
                "sub_variable_labels": {},
                "value_labels": spss_val_labels,
                "included": True,
            })

    return variables


def load_existing_config(meta_path, detected_vars):
    """
    Merge an existing JSON config into the detected variable list.
    Variables in the JSON override auto-detected labels/types/groupings.
    Variables NOT in JSON are still shown but marked included=False.
    """
    with open(meta_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    existing = {v["name"]: v for v in config.get("variables", [])}
    filter_sets = config.get("filter_sets", {})

    merged = []
    for var in detected_vars:
        name = var["name"]
        if name in existing:
            ev = existing[name]
            var["label"] = ev.get("label", var["label"])
            var["type"] = ev.get("type", var["type"])
            var["sub_variables"] = ev.get("sub_variables", var["sub_variables"])
            var["sub_variable_labels"] = ev.get(
                "sub_variable_labels", var["sub_variable_labels"]
            )
            # Load custom value_labels from JSON if present; otherwise keep SPSS-derived ones
            if "value_labels" in ev:
                var["value_labels"] = ev["value_labels"]
            var["included"] = True
        else:
            var["included"] = False
        merged.append(var)

    return merged, filter_sets


# ─────────────────────────────────────────────
# Layout helpers
# ─────────────────────────────────────────────

def _make_answer_option_rows(var, idx):
    """Build editable answer option rows for a variable.
    For single: editable value label text.
    For multi: editable sub-variable label text.
    Returns a list of Div rows or empty list.
    """
    rows = []
    is_multi = var["type"] == "multi"

    if is_multi:
        for sub_idx, sv in enumerate(var["sub_variables"]):
            sv_label = var["sub_variable_labels"].get(sv, sv)
            rows.append(
                html.Div(
                    [
                        html.Span(
                            sv,
                            style={
                                "fontFamily": "monospace",
                                "fontSize": "11px",
                                "color": "#94A3B8",
                                "minWidth": "130px",
                                "display": "inline-block",
                            },
                        ),
                        dcc.Input(
                            id={"type": "sub-label", "var_idx": idx, "sub_idx": sub_idx},
                            value=sv_label,
                            debounce=True,
                            placeholder=sv,
                            style={
                                "flex": "1",
                                "padding": "4px 8px",
                                "border": "1px solid #E2E8F0",
                                "borderRadius": "4px",
                                "fontSize": "12px",
                                "fontFamily": "'DM Sans', sans-serif",
                                "background": "#FAFAFA",
                                "color": "#1E293B",
                                "marginLeft": "8px",
                            },
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center", "marginBottom": "4px"},
                )
            )
    else:
        # Single-punch: value_labels is {str_code: label}
        for val_code, val_label in var.get("value_labels", {}).items():
            rows.append(
                html.Div(
                    [
                        html.Span(
                            val_code,
                            style={
                                "fontFamily": "monospace",
                                "fontSize": "11px",
                                "color": "#94A3B8",
                                "minWidth": "40px",
                                "display": "inline-block",
                            },
                        ),
                        dcc.Input(
                            id={"type": "val-label", "var_idx": idx, "val_code": val_code},
                            value=val_label,
                            debounce=True,
                            placeholder=val_code,
                            style={
                                "flex": "1",
                                "padding": "4px 8px",
                                "border": "1px solid #E2E8F0",
                                "borderRadius": "4px",
                                "fontSize": "12px",
                                "fontFamily": "'DM Sans', sans-serif",
                                "background": "#FAFAFA",
                                "color": "#1E293B",
                                "marginLeft": "8px",
                            },
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center", "marginBottom": "4px"},
                )
            )

    return rows


def make_variable_card(var, idx):
    """Render one variable row with editable title and answer options."""
    is_multi = var["type"] == "multi"
    badge_color = "#7C3AED" if is_multi else "#0369A1"
    badge_text = "MULTI" if is_multi else "SINGLE"
    included = var.get("included", True)

    answer_rows = _make_answer_option_rows(var, idx)

    return html.Div(
        [
            # ── Top row: checkbox / badge / var name / editable title ──
            html.Div(
                [
                    # Left cluster: checkbox + badge + var name
                    html.Div(
                        [
                            dcc.Checklist(
                                id={"type": "var-include", "index": idx},
                                options=[{"label": "", "value": "included"}],
                                value=["included"] if included else [],
                                style={"display": "inline-block", "marginRight": "8px"},
                            ),
                            html.Span(
                                badge_text,
                                style={
                                    "background": badge_color,
                                    "color": "white",
                                    "borderRadius": "4px",
                                    "padding": "2px 8px",
                                    "fontSize": "11px",
                                    "fontWeight": "600",
                                    "letterSpacing": "0.05em",
                                    "marginRight": "10px",
                                    "verticalAlign": "middle",
                                },
                            ),
                            html.Span(
                                var["name"],
                                style={
                                    "fontFamily": "monospace",
                                    "fontSize": "12px",
                                    "color": "#64748B",
                                    "marginRight": "10px",
                                },
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "minWidth": "260px"},
                    ),
                    # Right: editable question title
                    html.Div(
                        dcc.Input(
                            id={"type": "var-label", "index": idx},
                            value=var["label"],
                            debounce=True,
                            placeholder="Question label…",
                            style={
                                "width": "100%",
                                "padding": "6px 10px",
                                "border": "1px solid #CBD5E1",
                                "borderRadius": "6px",
                                "fontSize": "13px",
                                "fontFamily": "'DM Sans', sans-serif",
                                "background": "#FAFAFA",
                                "color": "#1E293B",
                                "outline": "none",
                            },
                        ),
                        style={"flex": "1", "marginLeft": "10px"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center"},
            ),
            # ── Answer options section ──────────────────────────────────
            html.Div(
                [
                    html.Div(
                        "Answer options" if not is_multi else "Sub-variables",
                        style={
                            "fontSize": "10px",
                            "fontWeight": "600",
                            "color": "#94A3B8",
                            "letterSpacing": "0.06em",
                            "textTransform": "uppercase",
                            "marginBottom": "6px",
                            "marginTop": "2px",
                        },
                    ),
                    html.Div(answer_rows),
                ],
                style={
                    "marginTop": "10px",
                    "marginLeft": "30px",
                    "paddingLeft": "12px",
                    "borderLeft": f"3px solid {'#EDE9FE' if is_multi else '#DBEAFE'}",
                },
            ) if answer_rows else None,
            # Hidden store for variable metadata (sub_variables list for multi)
            dcc.Store(
                id={"type": "var-meta", "index": idx},
                data={
                    "name": var["name"],
                    "type": var["type"],
                    "sub_variables": var["sub_variables"],
                    "sub_variable_labels": var["sub_variable_labels"],
                    "value_labels": var.get("value_labels", {}),
                },
            ),
        ],
        style={
            "padding": "12px 16px",
            "borderBottom": "1px solid #F1F5F9",
            "background": "white" if included else "#F8FAFC",
            "opacity": "1" if included else "0.5",
            "transition": "background 0.15s",
        },
        id={"type": "var-row", "index": idx},
    )


def make_filter_card(name, conditions, idx):
    """Render one filter row."""
    conditions_str = json.dumps(conditions, indent=None)
    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        name,
                        style={
                            "fontWeight": "600",
                            "fontSize": "13px",
                            "color": "#1E293B",
                            "minWidth": "180px",
                            "display": "inline-block",
                        },
                    ),
                    html.Span(
                        conditions_str,
                        style={
                            "fontFamily": "monospace",
                            "fontSize": "11px",
                            "color": "#64748B",
                            "flex": "1",
                            "marginLeft": "12px",
                            "wordBreak": "break-all",
                        },
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "flex": "1"},
            ),
            html.Button(
                "✕",
                id={"type": "remove-filter", "index": idx},
                n_clicks=0,
                style={
                    "background": "none",
                    "border": "none",
                    "color": "#EF4444",
                    "fontSize": "16px",
                    "cursor": "pointer",
                    "padding": "0 4px",
                    "marginLeft": "8px",
                },
            ),
            dcc.Store(
                id={"type": "filter-meta", "index": idx},
                data={"name": name, "conditions": conditions},
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "padding": "10px 16px",
            "borderBottom": "1px solid #F1F5F9",
            "background": "white",
        },
        id={"type": "filter-row", "index": idx},
    )


# ─────────────────────────────────────────────
# App factory
# ─────────────────────────────────────────────

def create_app(spss_path, meta_path=None):
    column_names, column_labels, value_labels_map, excluded_vars = read_spss_meta(spss_path)
    detected = auto_detect_variables(column_names, column_labels, value_labels_map)

    # Log excluded variables to console
    if excluded_vars:
        print(f"\n  Excluded {len(excluded_vars)} variable(s) from config builder:")
        for col, reason in excluded_vars.items():
            print(f"    x {col}  ({reason})")

    initial_filters = {}
    if meta_path and os.path.exists(meta_path):
        detected, initial_filters = load_existing_config(meta_path, detected)

    spss_name = os.path.splitext(os.path.basename(spss_path))[0]

    default_save_path = os.path.join(
        os.path.dirname(spss_path), f"{spss_name}.json"
    )
    if meta_path:
        default_save_path = meta_path

    total_in_spss = len(column_names) + len(excluded_vars)
    excluded_note = (
        f"  ·  {len(excluded_vars)} string/date variable(s) hidden"
        if excluded_vars else ""
    )
    header_subtitle = (
        f"{total_in_spss} variables in SPSS  ·  "
        f"{len(column_names)} numeric shown{excluded_note}"
    )

    app = Dash(
        __name__,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono&display=swap",
        ],
        suppress_callback_exceptions=True,
    )

    # ── layout ──────────────────────────────────────────────────────────────
    app.layout = html.Div(
        [
            # Stores
            dcc.Store(id="store-variables", data=detected),
            dcc.Store(id="store-filters", data=initial_filters),
            dcc.Store(id="store-save-path", data=default_save_path),
            dcc.Store(id="store-removed-filters", data=[]),

            # Header bar
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span(
                                        "⚙",
                                        style={"fontSize": "22px", "marginRight": "10px"},
                                    ),
                                    html.Span(
                                        f"Config Builder — {spss_name}",
                                        style={"fontWeight": "600", "fontSize": "17px"},
                                    ),
                                ],
                                style={"display": "flex", "alignItems": "center"},
                            ),
                            html.Span(
                                header_subtitle,
                                style={"fontSize": "12px", "color": "#94A3B8"},
                            ),
                        ],
                        style={
                            "display": "flex",
                            "justifyContent": "space-between",
                            "alignItems": "center",
                            "maxWidth": "1100px",
                            "margin": "0 auto",
                            "padding": "0 24px",
                        },
                    )
                ],
                style={
                    "background": "#0F172A",
                    "color": "white",
                    "padding": "16px 0",
                    "fontFamily": "'DM Sans', sans-serif",
                    "position": "sticky",
                    "top": "0",
                    "zIndex": "100",
                    "boxShadow": "0 2px 8px rgba(0,0,0,0.3)",
                },
            ),

            # Main body
            html.Div(
                [
                    # ── Left column: variables ──────────────────────
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.H2(
                                                "Variables",
                                                style={
                                                    "fontSize": "15px",
                                                    "fontWeight": "600",
                                                    "color": "#1E293B",
                                                    "margin": "0 0 2px 0",
                                                },
                                            ),
                                            html.Span(
                                                "Check to include · Edit label in the text box",
                                                style={"fontSize": "11px", "color": "#94A3B8"},
                                            ),
                                        ],
                                    ),
                                    # Global select / deselect
                                    html.Div(
                                        [
                                            dcc.Checklist(
                                                id="global-select-all",
                                                options=[{"label": " Select all", "value": "all"}],
                                                value=["all"],  # all selected by default
                                                style={"display": "inline-flex", "alignItems": "center"},
                                                inputStyle={"marginRight": "5px", "cursor": "pointer"},
                                                labelStyle={"fontSize": "12px", "color": "#475569", "cursor": "pointer", "fontWeight": "500"},
                                            ),
                                        ],
                                        style={"display": "flex", "alignItems": "center"},
                                    ),
                                ],
                                style={
                                    "padding": "12px 16px",
                                    "borderBottom": "2px solid #E2E8F0",
                                    "display": "flex",
                                    "justifyContent": "space-between",
                                    "alignItems": "center",
                                },
                            ),
                            html.Div(
                                [make_variable_card(v, i) for i, v in enumerate(detected)],
                                id="variable-list",
                                style={"overflowY": "auto", "maxHeight": "calc(100vh - 220px)"},
                            ),
                        ],
                        style={
                            "flex": "1",
                            "border": "1px solid #E2E8F0",
                            "borderRadius": "10px",
                            "background": "white",
                            "boxShadow": "0 1px 4px rgba(0,0,0,0.06)",
                            "overflow": "hidden",
                        },
                    ),

                    # ── Right column: filters + save ────────────────
                    html.Div(
                        [
                            # Filter builder
                            html.Div(
                                [
                                    html.H2(
                                        "Filter Sets",
                                        style={
                                            "fontSize": "15px",
                                            "fontWeight": "600",
                                            "color": "#1E293B",
                                            "margin": "0 0 4px 0",
                                        },
                                    ),
                                    html.Span(
                                        "Define named filters. Conditions use JSON syntax.",
                                        style={"fontSize": "11px", "color": "#94A3B8"},
                                    ),
                                ],
                                style={
                                    "padding": "16px",
                                    "borderBottom": "2px solid #E2E8F0",
                                },
                            ),

                            html.Div(
                                id="filter-list",
                                children=[
                                    make_filter_card(n, c, i)
                                    for i, (n, c) in enumerate(initial_filters.items())
                                ],
                                style={"maxHeight": "280px", "overflowY": "auto"},
                            ),

                            # Add filter form
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                "Filter Name",
                                                style={
                                                    "fontSize": "11px",
                                                    "fontWeight": "600",
                                                    "color": "#64748B",
                                                    "display": "block",
                                                    "marginBottom": "4px",
                                                },
                                            ),
                                            dcc.Input(
                                                id="new-filter-name",
                                                placeholder='e.g. "AGE 23-30"',
                                                debounce=False,
                                                style={
                                                    "width": "100%",
                                                    "padding": "7px 10px",
                                                    "border": "1px solid #CBD5E1",
                                                    "borderRadius": "6px",
                                                    "fontSize": "13px",
                                                    "fontFamily": "'DM Sans', sans-serif",
                                                },
                                            ),
                                        ],
                                        style={"flex": "1", "marginRight": "8px"},
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "Variable",
                                                style={
                                                    "fontSize": "11px",
                                                    "fontWeight": "600",
                                                    "color": "#64748B",
                                                    "display": "block",
                                                    "marginBottom": "4px",
                                                },
                                            ),
                                            dcc.Dropdown(
                                                id="new-filter-var",
                                                options=[
                                                    {"label": f"{c} — {column_labels.get(c,c)}", "value": c}
                                                    for c in column_names
                                                ],
                                                placeholder="Variable",
                                                clearable=True,
                                                style={"fontSize": "13px"},
                                            ),
                                        ],
                                        style={"flex": "1", "marginRight": "8px"},
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "Operator",
                                                style={
                                                    "fontSize": "11px",
                                                    "fontWeight": "600",
                                                    "color": "#64748B",
                                                    "display": "block",
                                                    "marginBottom": "4px",
                                                },
                                            ),
                                            dcc.Dropdown(
                                                id="new-filter-op",
                                                options=[
                                                    {"label": "equals (eq)", "value": "eq"},
                                                    {"label": "in list (in)", "value": "in"},
                                                    {"label": "between", "value": "between"},
                                                    {"label": "not missing", "value": "not_missing"},
                                                ],
                                                placeholder="Operator",
                                                clearable=True,
                                                style={"fontSize": "13px"},
                                            ),
                                        ],
                                        style={"flex": "1", "marginRight": "8px"},
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "Value(s)",
                                                style={
                                                    "fontSize": "11px",
                                                    "fontWeight": "600",
                                                    "color": "#64748B",
                                                    "display": "block",
                                                    "marginBottom": "4px",
                                                },
                                            ),
                                            dcc.Input(
                                                id="new-filter-value",
                                                placeholder="e.g. 1  or  1,2,3",
                                                debounce=False,
                                                style={
                                                    "width": "100%",
                                                    "padding": "7px 10px",
                                                    "border": "1px solid #CBD5E1",
                                                    "borderRadius": "6px",
                                                    "fontSize": "13px",
                                                    "fontFamily": "'DM Mono', monospace",
                                                },
                                            ),
                                        ],
                                        style={"flex": "1", "marginRight": "8px"},
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                "\u00a0",
                                                style={
                                                    "display": "block",
                                                    "marginBottom": "4px",
                                                    "fontSize": "11px",
                                                },
                                            ),
                                            html.Button(
                                                "+ Add",
                                                id="add-filter-btn",
                                                n_clicks=0,
                                                style={
                                                    "background": "#0F172A",
                                                    "color": "white",
                                                    "border": "none",
                                                    "borderRadius": "6px",
                                                    "padding": "7px 14px",
                                                    "fontSize": "13px",
                                                    "cursor": "pointer",
                                                    "fontFamily": "'DM Sans', sans-serif",
                                                    "whiteSpace": "nowrap",
                                                },
                                            ),
                                        ],
                                    ),
                                ],
                                style={
                                    "display": "flex",
                                    "alignItems": "flex-end",
                                    "padding": "12px 16px",
                                    "borderTop": "1px solid #F1F5F9",
                                    "background": "#F8FAFC",
                                },
                            ),

                            html.Div(
                                id="filter-error",
                                style={"padding": "0 16px", "color": "#EF4444", "fontSize": "12px"},
                            ),

                            # Save section
                            html.Div(
                                [
                                    html.Label(
                                        "Save path",
                                        style={
                                            "fontSize": "11px",
                                            "fontWeight": "600",
                                            "color": "#64748B",
                                            "display": "block",
                                            "marginBottom": "6px",
                                        },
                                    ),
                                    dcc.Input(
                                        id="save-path-input",
                                        value=default_save_path,
                                        debounce=True,
                                        style={
                                            "width": "100%",
                                            "padding": "8px 10px",
                                            "border": "1px solid #CBD5E1",
                                            "borderRadius": "6px",
                                            "fontSize": "12px",
                                            "fontFamily": "'DM Mono', monospace",
                                            "marginBottom": "10px",
                                        },
                                    ),
                                    html.Button(
                                        "💾  Save JSON",
                                        id="save-btn",
                                        n_clicks=0,
                                        style={
                                            "width": "100%",
                                            "background": "#059669",
                                            "color": "white",
                                            "border": "none",
                                            "borderRadius": "8px",
                                            "padding": "12px",
                                            "fontSize": "14px",
                                            "fontWeight": "600",
                                            "cursor": "pointer",
                                            "fontFamily": "'DM Sans', sans-serif",
                                            "letterSpacing": "0.02em",
                                        },
                                    ),
                                    html.Div(
                                        id="save-status",
                                        style={
                                            "marginTop": "10px",
                                            "fontSize": "13px",
                                            "textAlign": "center",
                                            "minHeight": "20px",
                                        },
                                    ),
                                ],
                                style={
                                    "padding": "16px",
                                    "borderTop": "2px solid #E2E8F0",
                                    "marginTop": "auto",
                                },
                            ),
                        ],
                        style={
                            "width": "420px",
                            "flexShrink": "0",
                            "border": "1px solid #E2E8F0",
                            "borderRadius": "10px",
                            "background": "white",
                            "boxShadow": "0 1px 4px rgba(0,0,0,0.06)",
                            "display": "flex",
                            "flexDirection": "column",
                            "overflow": "hidden",
                            "marginLeft": "20px",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "maxWidth": "1100px",
                    "margin": "24px auto",
                    "padding": "0 24px",
                    "fontFamily": "'DM Sans', sans-serif",
                    "alignItems": "flex-start",
                },
            ),
        ],
        style={"background": "#F1F5F9", "minHeight": "100vh"},
    )

    # ── callbacks ────────────────────────────────────────────────────────────

    @app.callback(
        Output("store-variables", "data"),
        Output("global-select-all", "value"),
        Input({"type": "var-include", "index": ALL}, "value"),
        Input({"type": "var-label", "index": ALL}, "value"),
        Input({"type": "sub-label", "var_idx": ALL, "sub_idx": ALL}, "value"),
        Input({"type": "val-label", "var_idx": ALL, "val_code": ALL}, "value"),
        State({"type": "var-meta", "index": ALL}, "data"),
        State("store-variables", "data"),
        prevent_initial_call=True,
    )
    def sync_variable_store(include_vals, label_vals, sub_label_vals, val_label_vals, meta_vals, current):
        """Keep store-variables in sync with all UI edits."""
        if not current:
            return no_update, no_update

        updated = list(current)

        # ── individual checkbox / label edits ────────────────────────────
        for i, (inc, lbl, meta) in enumerate(zip(include_vals, label_vals, meta_vals)):
            if i < len(updated):
                updated[i]["included"] = bool(inc)  # [] or ["included"]
                if lbl:
                    updated[i]["label"] = lbl

        # ── multi-punch sub-variable labels ──────────────────────────────
        for item in ctx.inputs_list[2]:
            v_idx = item["id"]["var_idx"]
            s_idx = item["id"]["sub_idx"]
            new_lbl = item.get("value")
            if new_lbl is None:
                continue
            if v_idx < len(updated):
                sv_list = updated[v_idx].get("sub_variables", [])
                if s_idx < len(sv_list):
                    sv_key = sv_list[s_idx]
                    updated[v_idx]["sub_variable_labels"][sv_key] = new_lbl

        # ── single-punch value labels ─────────────────────────────────────
        for item in ctx.inputs_list[3]:
            v_idx = item["id"]["var_idx"]
            val_code = item["id"]["val_code"]
            new_lbl = item.get("value")
            if new_lbl is None:
                continue
            if v_idx < len(updated):
                if "value_labels" not in updated[v_idx]:
                    updated[v_idx]["value_labels"] = {}
                updated[v_idx]["value_labels"][val_code] = new_lbl

        # ── mirror global checkbox: all=checked, none=unchecked, mixed=leave ──
        all_included = all(v.get("included", True) for v in updated)
        none_included = not any(v.get("included", True) for v in updated)
        if all_included:
            new_global = ["all"]
        elif none_included:
            new_global = []
        else:
            new_global = no_update

        return updated, new_global

    @app.callback(
        Output({"type": "var-include", "index": ALL}, "value"),
        Input("global-select-all", "value"),
        State("store-variables", "data"),
        prevent_initial_call=True,
    )
    def apply_global_select(global_sel, current):
        """Push global select/deselect into every individual checkbox."""
        if not current:
            return no_update
        target = ["included"] if bool(global_sel) else []
        return [target] * len(current)

    @app.callback(
        Output("store-filters", "data"),
        Output("filter-list", "children"),
        Output("filter-error", "children"),
        Output("new-filter-name", "value"),
        Output("new-filter-value", "value"),
        Input("add-filter-btn", "n_clicks"),
        Input({"type": "remove-filter", "index": ALL}, "n_clicks"),
        State("new-filter-name", "value"),
        State("new-filter-var", "value"),
        State("new-filter-op", "value"),
        State("new-filter-value", "value"),
        State("store-filters", "data"),
        State({"type": "filter-meta", "index": ALL}, "data"),
        prevent_initial_call=True,
    )
    def manage_filters(
        add_clicks, remove_clicks,
        fname, fvar, fop, fval,
        current_filters, filter_metas,
    ):
        triggered = ctx.triggered_id

        # ── Remove a filter ──────────────────────────────────────────────────
        if isinstance(triggered, dict) and triggered.get("type") == "remove-filter":
            rm_idx = triggered["index"]
            new_filters = {}
            for i, meta in enumerate(filter_metas):
                if i != rm_idx:
                    new_filters[meta["name"]] = meta["conditions"]
            cards = [
                make_filter_card(n, c, i)
                for i, (n, c) in enumerate(new_filters.items())
            ]
            return new_filters, cards, "", no_update, no_update

        # ── Add a filter ─────────────────────────────────────────────────────
        if triggered == "add-filter-btn":
            if not fname or not fname.strip():
                return no_update, no_update, "⚠ Filter name is required.", no_update, no_update
            if not fvar:
                return no_update, no_update, "⚠ Please select a variable.", no_update, no_update
            if not fop:
                return no_update, no_update, "⚠ Please select an operator.", no_update, no_update

            fname = fname.strip()

            # Parse value
            try:
                condition = _parse_filter_value(fop, fval)
            except ValueError as e:
                return no_update, no_update, f"⚠ {e}", no_update, no_update

            new_filters = dict(current_filters or {})
            new_filters[fname] = {fvar: condition}
            cards = [
                make_filter_card(n, c, i)
                for i, (n, c) in enumerate(new_filters.items())
            ]
            return new_filters, cards, "", "", ""

        return no_update, no_update, "", no_update, no_update

    @app.callback(
        Output("store-save-path", "data"),
        Input("save-path-input", "value"),
        prevent_initial_call=True,
    )
    def update_save_path(path):
        return path or default_save_path

    @app.callback(
        Output("save-status", "children"),
        Output("save-status", "style"),
        Input("save-btn", "n_clicks"),
        State("store-variables", "data"),
        State("store-filters", "data"),
        State("store-save-path", "data"),
        prevent_initial_call=True,
    )
    def save_config(n_clicks, variables, filters, save_path):
        if not n_clicks:
            return "", {}

        included = [
            v for v in (variables or []) if v.get("included", True)
        ]

        if not included:
            return (
                "⚠ No variables selected — nothing to save.",
                {"color": "#EF4444", "fontSize": "13px", "textAlign": "center", "marginTop": "10px"},
            )

        # Build JSON structure
        config_vars = []
        for v in included:
            entry = {
                "name": v["name"],
                "type": v["type"],
                "label": v["label"],
            }
            if v["type"] == "multi":
                entry["sub_variables"] = v["sub_variables"]
                entry["sub_variable_labels"] = v["sub_variable_labels"]
            elif v["type"] == "single":
                # Only write value_labels if the variable has them
                vl = v.get("value_labels", {})
                if vl:
                    entry["value_labels"] = vl
            config_vars.append(entry)

        config = {"variables": config_vars}
        if filters:
            config["filter_sets"] = filters

        # Ensure directory exists
        save_dir = os.path.dirname(save_path)
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            ts = datetime.now().strftime("%H:%M:%S")
            return (
                f"✅ Saved {len(config_vars)} variable(s) to {os.path.basename(save_path)} at {ts}. "
                f"Load this file in the launcher to use it.",
                {"color": "#059669", "fontSize": "12px", "textAlign": "center", "marginTop": "10px"},
            )
        except Exception as e:
            return (
                f"❌ Save failed: {e}",
                {"color": "#EF4444", "fontSize": "13px", "textAlign": "center", "marginTop": "10px"},
            )

    return app


# ─────────────────────────────────────────────
# Filter value parser
# ─────────────────────────────────────────────

def _parse_filter_value(operator, raw):
    """Convert raw text input into the operator dict the filter_engine expects.
    e.g. eq + "1"  →  {"eq": 1}
         in + "1,2" →  {"in": [1, 2]}
    """
    if operator == "not_missing":
        return {"not_missing": True}

    if not raw or not raw.strip():
        raise ValueError(f"A value is required for operator '{operator}'.")

    raw = raw.strip()

    if operator == "eq":
        try:
            val = int(raw)
        except ValueError:
            try:
                val = float(raw)
            except ValueError:
                val = raw
        return {"eq": val}

    if operator == "in":
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        result = []
        for p in parts:
            try:
                result.append(int(p))
            except ValueError:
                try:
                    result.append(float(p))
                except ValueError:
                    result.append(p)
        if not result:
            raise ValueError("'in' requires at least one value.")
        return {"in": result}

    if operator == "between":
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) != 2:
            raise ValueError("'between' requires exactly two comma-separated values.")
        result = []
        for p in parts:
            try:
                result.append(int(p))
            except ValueError:
                result.append(float(p))
        return {"between": result}

    return {operator: raw}


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("SPSS CONFIG BUILDER")
    print("=" * 60)

    args = parse_arguments()

    if not os.path.exists(args.spss_path):
        print(f"✗ SPSS file not found: {args.spss_path}")
        sys.exit(1)

    print(f"SPSS file : {args.spss_path}")
    if args.meta_path:
        print(f"Existing config: {args.meta_path}")
    print(f"Port      : {args.port}")

    app = create_app(args.spss_path, args.meta_path)

    print(f"\n✓ Config builder ready → http://localhost:{args.port}")
    print("Close this window or press Ctrl+C to stop.\n")

    app.run(
        host="127.0.0.1",
        port=args.port,
        debug=False,
        dev_tools_hot_reload=False,
    )


if __name__ == "__main__":
    main()
