"""
pages/dashboard.py  —  Dashboard page (refactored from dash_app.py)
URL: /dashboard
Reads spss_path and meta_path from shared session stores.
"""
import os
import copy
from datetime import datetime

import dash
from dash import html, dcc, Input, Output, State, callback, no_update, ctx, MATCH, ALL
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go

from config_loader import ConfigLoader
from spss_reader import SPSSReader
from frequency_processor import FrequencyProcessor
from visualizer import ChartVisualizer
from filter_engine import FilterEngine

dash.register_page(__name__, path='/dashboard', title='Dashboard')


# ── Helpers (unchanged from dash_app.py) ──────────────────────────────────

def _coerce_value_label_keys(json_value_labels, column_data):
    if not json_value_labels:
        return json_value_labels
    sample = column_data.dropna()
    coerced = {}
    for k, v in json_value_labels.items():
        try:
            num = float(k)
            if num == int(num) and (sample.dtype.kind in ('i', 'u') or
                    (sample.dtype.kind == 'f' and (sample % 1 == 0).all())):
                coerced[int(num)] = v
            else:
                coerced[num] = v
        except (ValueError, TypeError):
            coerced[k] = v
    return coerced


def _build_single_freq_table(column_data, value_labels, total):
    import numpy as np
    value_counts = column_data.value_counts(dropna=False)
    if value_labels:
        ordered_values = list(value_labels.keys())
        labeled_set = set(value_labels.keys())
        extras = sorted([v for v in value_counts.index
                         if not pd.isna(v) and v not in labeled_set])
        ordered_values = ordered_values + extras
    else:
        ordered_values = sorted([v for v in value_counts.index if not pd.isna(v)])
    freq_table = []
    valid_total = 0
    for value in ordered_values:
        count = value_counts.get(value, 0)
        label = value_labels.get(value, str(value)) if value_labels else str(value)
        pct   = (count / total) * 100 if total > 0 else 0
        freq_table.append({'value': value, 'label': label, 'count': count,
                           'percentage': pct, 'is_missing': False})
        valid_total += count
    missing_count = 0
    for k in value_counts.index:
        if pd.isna(k):
            missing_count = value_counts[k]
            break
    if missing_count > 0:
        freq_table.append({'value': None, 'label': 'Missing',
                           'count': missing_count,
                           'percentage': (missing_count / total) * 100 if total > 0 else 0,
                           'is_missing': True})
    return freq_table, valid_total


def _process_single_variable(reader, data, var_name, var_label,
                              filter_info, config, json_value_labels=None):
    weighting_config  = config.get('weighting', {})
    weighting_enabled = weighting_config.get('enabled', False)
    if var_name not in data.columns:
        return None
    column_data = data[var_name]
    spss_value_labels = reader.get_value_labels(var_name)
    if json_value_labels:
        json_value_labels = _coerce_value_label_keys(json_value_labels, column_data)
    value_labels = json_value_labels if json_value_labels else spss_value_labels
    total = len(column_data)
    if weighting_enabled:
        try:
            from weight_calculator import WeightCalculator
            wc = WeightCalculator(data, weighting_config['weight_variable'])
            valid_data, _ = wc.get_valid_data_and_weights()
            wr = wc.calculate_weighted_frequencies_single(valid_data[var_name], value_labels)
            return {'var_name': var_name, 'var_label': var_label, 'type': 'single',
                    'weighted': True, 'total_unweighted': wr['total_unweighted'],
                    'total_weighted': wr['total_weighted'],
                    'valid_unweighted': wr['valid_unweighted'],
                    'valid_weighted': wr['valid_weighted'],
                    'freq_table': wr['freq_table'], 'filter_info': filter_info,
                    'weight_info': wc.get_validation_info(), 'weighting_warning': None}
        except Exception as e:
            warn = f"⚠ Weighting failed: {e}. Showing unweighted data."
            ft, vt = _build_single_freq_table(column_data, value_labels, total)
            return {'var_name': var_name, 'var_label': var_label, 'type': 'single',
                    'weighted': False, 'total_responses': total, 'valid_responses': vt,
                    'freq_table': ft, 'filter_info': filter_info, 'weighting_warning': warn}
    ft, vt = _build_single_freq_table(column_data, value_labels, total)
    return {'var_name': var_name, 'var_label': var_label, 'type': 'single',
            'weighted': False, 'total_responses': total, 'valid_responses': vt,
            'freq_table': ft, 'filter_info': filter_info, 'weighting_warning': None}


def _process_multi_variable(reader, data, var_name, var_label,
                             sub_variables, filter_info, config, sub_variable_labels=None):
    if sub_variable_labels is None:
        sub_variable_labels = {}
    weighting_config  = config.get('weighting', {})
    weighting_enabled = weighting_config.get('enabled', False)
    existing_vars = [sv for sv in sub_variables if sv in data.columns]
    if not existing_vars:
        return None
    df   = data[existing_vars].copy()
    base = int((df == 1).any(axis=1).sum())
    if base == 0:
        return None
    if weighting_enabled:
        try:
            from weight_calculator import WeightCalculator
            wc = WeightCalculator(data, weighting_config['weight_variable'])
            valid_data, _ = wc.get_valid_data_and_weights()
            sub_data_dict = {sv: valid_data[sv] for sv in existing_vars}
            wr = wc.calculate_weighted_frequencies_multi(sub_data_dict)
            for row in wr['freq_table']:
                sv = row['sub_var']
                row['label'] = (sub_variable_labels.get(sv)
                                or reader.get_variable_label(sv))
            return {'var_name': var_name, 'var_label': var_label, 'type': 'multi',
                    'weighted': True,
                    'total_unweighted': wr['total_unweighted'],
                    'total_weighted':   wr['total_weighted'],
                    'base_unweighted':  wr['base_unweighted'],
                    'base_weighted':    wr['base_weighted'],
                    'freq_table': wr['freq_table'], 'filter_info': filter_info,
                    'weight_info': wc.get_validation_info(), 'weighting_warning': None}
        except Exception as e:
            warn = f"⚠ Weighting failed: {e}. Showing unweighted data."
            ft = [{'sub_var': sv,
                   'label': sub_variable_labels.get(sv) or reader.get_variable_label(sv),
                   'count': int((df[sv] == 1).sum()),
                   'percentage': (int((df[sv] == 1).sum()) / base * 100) if base > 0 else 0}
                  for sv in existing_vars]
            return {'var_name': var_name, 'var_label': var_label, 'type': 'multi',
                    'weighted': False, 'base': base, 'total_respondents': len(df),
                    'freq_table': ft, 'filter_info': filter_info, 'weighting_warning': warn}
    ft = [{'sub_var': sv,
           'label': sub_variable_labels.get(sv) or reader.get_variable_label(sv),
           'count': int((df[sv] == 1).sum()),
           'percentage': (int((df[sv] == 1).sum()) / base * 100) if base > 0 else 0}
          for sv in existing_vars]
    return {'var_name': var_name, 'var_label': var_label, 'type': 'multi',
            'weighted': False, 'base': base, 'total_respondents': len(df),
            'freq_table': ft, 'filter_info': filter_info, 'weighting_warning': None}


def _create_chart_card(result, fig, var_idx):
    var_label = result['var_label']
    var_type  = result['type']
    weighted  = result.get('weighted', False)
    filter_info = result.get('filter_info')
    badges = [html.Span(f"Type: {var_type.upper()}", className="badge badge-type")]
    if var_type == 'single':
        bv = result.get('valid_weighted', 0) if weighted else result.get('valid_responses', 0)
        badges.append(html.Span(
            f"Base: {bv:.0f} (weighted)" if weighted else f"Base: {bv}",
            className="badge badge-base"))
    else:
        bv = result.get('base_weighted', 0) if weighted else result.get('base', 0)
        badges.append(html.Span(
            f"Base: {bv:.0f} (weighted)" if weighted else f"Base: {bv}",
            className="badge badge-base"))
    if weighted:
        badges.append(html.Span("⚖️ Weighted", className="badge badge-weighted"))
    if filter_info:
        badges.append(html.Span(f"🔍 {filter_info['name']}", className="badge badge-filter"))

    sort_ctrl = None
    if var_type == 'multi':
        sort_ctrl = html.Div([
            html.Label("Sort:", style={'fontSize': '12px', 'color': '#718096',
                                       'marginRight': '6px', 'fontWeight': '500'}),
            dcc.Dropdown(
                id={'type': 'multi-sort', 'index': var_idx},
                options=[{'label': 'As defined',  'value': 'defined'},
                         {'label': 'Count ↓',     'value': 'count_desc'},
                         {'label': 'Count ↑',     'value': 'count_asc'}],
                value='defined', clearable=False, searchable=False,
                style={'width': '140px', 'fontSize': '12px'})
        ], style={'display': 'flex', 'alignItems': 'center',
                  'marginLeft': 'auto', 'paddingRight': '4px'})

    result_store = (dcc.Store(id={'type': 'multi-result-store', 'index': var_idx}, data=result)
                    if var_type == 'multi' else None)
    graph_id = {'type': 'multi-chart', 'index': var_idx} if var_type == 'multi' else f'chart-{var_idx}'
    graph = dcc.Graph(figure=fig,
                      config={'displayModeBar': True,
                              'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                              'displaylogo': False},
                      className="chart-graph", id=graph_id)
    header_right = html.Div(
        [html.Div(badges, className="chart-badges"), sort_ctrl] if sort_ctrl
        else [html.Div(badges, className="chart-badges")],
        style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'flexWrap': 'wrap'})
    return html.Div([
        result_store,
        html.Div([html.H3(var_label, className="chart-title"), header_right],
                 className="chart-header",
                 style={'display': 'flex', 'justifyContent': 'space-between',
                        'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '8px'}),
        html.Div(result['weighting_warning'], className="weighting-warning-banner",
                 style={'background': '#FFF3CD', 'border': '1px solid #FFCA28',
                        'borderRadius': '4px', 'padding': '8px 12px',
                        'margin': '8px 0', 'color': '#856404', 'fontSize': '13px'}
                 ) if result.get('weighting_warning') else None,
        html.Div([graph], className="chart-body"),
    ], className="chart-card", id=f'var-section-{var_idx}')


# ── Data loader (cached per path pair) ────────────────────────────────────
_cache = {}   # keyed by paths+mtimes; invalidated when JSON changes on disk


def _load_data(spss_path, meta_path):
    # Include file mtimes so editing+saving the JSON always re-reads it
    try:
        spss_mtime = os.path.getmtime(spss_path)
        meta_mtime = os.path.getmtime(meta_path)
    except OSError:
        spss_mtime = meta_mtime = 0
    key = (spss_path, meta_path, spss_mtime, meta_mtime)
    if key in _cache:
        return _cache[key]

    loader = ConfigLoader(meta_path, spss_file_path=spss_path)
    config = loader.load()

    reader = SPSSReader(spss_path)
    if not reader.read():
        raise RuntimeError("Failed to read SPSS file")

    filter_sets   = config.get('filter_sets', {})
    global_filter = config.get('global_filter', None)
    weighting_cfg = config.get('weighting', {})
    variables_list = config.get('variables', [])

    processor = FrequencyProcessor(reader, filter_sets=filter_sets,
                                   global_filter=global_filter,
                                   weighting_config=weighting_cfg)
    result = (config, reader, processor, variables_list, filter_sets, global_filter)
    _cache[key] = result
    return result


# ── Layout (called on every page visit) ───────────────────────────────────
def layout():
    return html.Div([
        # Stores local to this page visit
        dcc.Store(id='dash-spss-path',  storage_type='session'),
        dcc.Store(id='dash-meta-path',  storage_type='session'),
        dcc.Store(id='store-theme',     data={'theme': 'corporate_blue'}),

        # Trigger load from shared stores on page load
        dcc.Location(id='dash-location', refresh=False),

        html.Div(id='dash-page-content'),
    ], className='page-wrapper')


# ── On page load: pull paths from shared stores, build full UI ────────────
@callback(
    Output('dash-page-content', 'children'),
    Input('dash-location',    'pathname'),
    State('store-spss-path',  'data'),
    State('store-meta-path',  'data'),
)
def render_dashboard(pathname, spss_path, meta_path):
    if pathname != '/dashboard':
        return no_update

    if not spss_path or not meta_path:
        return html.Div([
            html.Div([
                html.H2('No files loaded', style={'color': '#64748B'}),
                html.P('Please go back to Home and select your SPSS and config files.'),
                dcc.Link(html.Button('← Go to Home', className='btn-secondary'), href='/'),
            ], className='home-card', style={'textAlign': 'center', 'padding': '48px'}),
        ], className='home-container')

    try:
        config, reader, processor, variables_list, filter_sets, global_filter = \
            _load_data(spss_path, meta_path)
    except Exception as e:
        return html.Div([
            html.Div([
                html.H2('Failed to load data', style={'color': '#EF4444'}),
                html.P(str(e)),
                dcc.Link(html.Button('← Go to Home', className='btn-secondary'), href='/'),
            ], className='home-card', style={'padding': '48px'}),
        ], className='home-container')

    data_info  = reader.get_info()
    total_rows = data_info['n_rows'] if data_info else 0
    weighting_enabled = config.get('weighting', {}).get('enabled', False)
    weight_var = config.get('weighting', {}).get('weight_variable', 'N/A') if weighting_enabled else 'N/A'
    spss_name  = os.path.splitext(os.path.basename(spss_path))[0]

    var_options = [{'label': f"{v['label']} ({v['name']})", 'value': i,
                    'type': v['type'], 'config': v}
                   for i, v in enumerate(variables_list)]

    filter_options = [{'label': 'No Filter (All Data)', 'value': '__none__'}]
    if global_filter:
        filter_options.append({'label': f'⭐ {global_filter} (default)', 'value': global_filter})
    for fn in filter_sets:
        if fn != global_filter:
            filter_options.append({'label': fn, 'value': fn})
    default_filter = global_filter if global_filter else '__none__'

    return html.Div([
        dcc.Store(id='store-vars-list',    data=variables_list),
        dcc.Store(id='store-filter-sets',  data=filter_sets),
        dcc.Store(id='store-config',       data=config),
        dcc.Store(id='store-spss-path-local', data=spss_path),
        dcc.Store(id='store-meta-path-local', data=meta_path),

        # Header
        html.Div([
            html.Div([
                html.H1(f"📊 {spss_name}", className="dashboard-title"),
                html.P(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
                       className="dashboard-subtitle"),
            ], className="header-content"),
        ], className="dashboard-header"),

        html.Div([
            # Sidebar
            html.Div([
                html.Div([
                    html.H3("🎨 Chart Theme", className="sidebar-section-title"),
                    dcc.Dropdown(id='theme-dropdown',
                                 options=[{'label': '🔵 Corporate Blue', 'value': 'corporate_blue'},
                                          {'label': '💜 Modern',         'value': 'modern'},
                                          {'label': '🏢 Professional',   'value': 'professional'},
                                          {'label': '🌈 Vibrant',        'value': 'vibrant'}],
                                 value='corporate_blue', clearable=False,
                                 className="sidebar-dropdown"),
                ], className="sidebar-section"),
                html.Hr(className="sidebar-divider"),
                html.Div([
                    html.H3("🔍 Filters", className="sidebar-section-title"),
                    dcc.Dropdown(id='filter-dropdown',
                                 options=filter_options,
                                 value=default_filter, clearable=False,
                                 className="sidebar-dropdown"),
                ], className="sidebar-section"),
                html.Hr(className="sidebar-divider"),
                html.Div([
                    html.H3("📋 Variables", className="sidebar-section-title"),
                    dcc.Checklist(id='variable-checklist',
                                  options=var_options,
                                  value=list(range(len(variables_list))),
                                  className="sidebar-checklist"),
                ], className="sidebar-section"),
                html.Hr(className="sidebar-divider"),
                html.Div([
                    html.H3("ℹ️ Dataset Info", className="sidebar-section-title"),
                    html.Div([html.Span("Total Records: ", className="info-label"),
                               html.Span(f"{total_rows:,}", className="info-value")],
                              className="info-row"),
                    html.Div([html.Span("Weighting: ", className="info-label"),
                               html.Span("Enabled" if weighting_enabled else "Disabled",
                                         className="info-value")], className="info-row"),
                    html.Div([html.Span("Weight Var: ", className="info-label"),
                               html.Span(weight_var, className="info-value")],
                              className="info-row"),
                    html.Div([html.Span("Variables: ", className="info-label"),
                               html.Span(str(len(variables_list)), className="info-value")],
                              className="info-row"),
                    html.Div([html.Span("Filters: ", className="info-label"),
                               html.Span(str(len(filter_sets)), className="info-value")],
                              className="info-row"),
                    html.Hr(className="sidebar-divider"),
                    dcc.Link(html.Button('← Home', className='btn-secondary btn-sm'), href='/'),
                ], className="sidebar-section"),
            ], className="sidebar"),

            # Main content
            html.Div([
                html.Div([
                    html.Span("📈 ", className="status-icon"),
                    html.Span("Select variables and apply filters to view frequencies",
                               className="status-text"),
                    dcc.Loading(children=html.Div(id='loading-indicator',
                                                  className="loading-text"),
                                type="circle", color="#2E86AB"),
                ], className="status-bar"),
                html.Div(id='charts-container', className="charts-container"),
            ], className="main-content"),
        ], className="container"),

        html.Div([
            html.P("SPSS Frequency Dashboard | Market Research Data Processing",
                   className="footer-text"),
        ], className="dashboard-footer"),
    ], className="dashboard-wrapper")


# ── Theme store ────────────────────────────────────────────────────────────
@callback(
    Output('store-theme', 'data'),
    Input('theme-dropdown', 'value'),
    prevent_initial_call=True,
)
def update_theme(theme):
    return {'theme': theme}


# ── Main charts update ─────────────────────────────────────────────────────
@callback(
    Output('charts-container',  'children'),
    Output('loading-indicator', 'children'),
    Input('filter-dropdown',    'value'),
    Input('variable-checklist', 'value'),
    Input('store-theme',        'data'),
    Input('store-vars-list',    'data'),   # fires when render_dashboard populates it
    State('store-filter-sets',  'data'),
    State('store-config',       'data'),
    State('store-spss-path-local', 'data'),
    State('store-meta-path-local', 'data'),
    prevent_initial_call=True,
)
def update_charts(selected_filter, selected_vars, theme_data,
                  variables_list, filter_sets, config,
                  spss_path, meta_path):
    # variables_list now comes as Input (triggers re-run when stores populate)
    if not selected_vars or not spss_path or not meta_path:
        return [html.Div(html.P("⚠️ No variables selected.",
                                className="no-data-message"),
                         className="no-data-container")], ""

    try:
        _, reader, _, _, _, _ = _load_data(spss_path, meta_path)
    except Exception as e:
        return [html.Div(html.P(f"Error: {e}"), className="no-data-container")], ""

    theme = (theme_data or {}).get('theme', 'corporate_blue')
    viz   = ChartVisualizer(theme=theme)
    filter_name = selected_filter if selected_filter != '__none__' else None
    filter_sets = filter_sets or {}

    if filter_name and filter_name in filter_sets:
        fe = FilterEngine(reader.get_data(), variables_list or [])
        try:
            filtered_data, summary, stats = fe.apply_filter_set(
                filter_name, filter_sets[filter_name])
            filter_info = {'name': filter_name, 'summary': summary,
                           'stats': stats,
                           'is_global': (filter_name == (config or {}).get('global_filter'))}
        except Exception:
            filtered_data = reader.get_data()
            filter_info   = None
    else:
        filtered_data = reader.get_data()
        filter_info   = None

    chart_cards = []
    for var_idx in selected_vars:
        if var_idx >= len(variables_list or []):
            continue
        vc         = variables_list[var_idx]
        var_name   = vc.get('name')
        var_type   = vc.get('type')
        var_label  = vc.get('label', var_name)

        if var_type == 'single':
            result = _process_single_variable(
                reader, filtered_data, var_name, var_label,
                filter_info, config or {},
                json_value_labels=vc.get('value_labels'))
            if result:
                fig = viz.create_single_punch_chart(result, 'bar')
        elif var_type == 'multi':
            result = _process_multi_variable(
                reader, filtered_data, var_name, var_label,
                vc.get('sub_variables', []), filter_info, config or {},
                sub_variable_labels=vc.get('sub_variable_labels', {}))
            if result:
                fig = viz.create_multi_punch_chart(result)
        else:
            continue

        if result:
            chart_cards.append(_create_chart_card(result, fig, var_idx))

    if not chart_cards:
        return [html.Div(html.P("⚠️ No results generated.",
                                className="no-data-message"),
                         className="no-data-container")], ""

    status = f"✓ {len(chart_cards)} variable(s)"
    if filter_name:
        status += f" | Filter: {filter_name}"
    return chart_cards, status


# ── Multi-punch sort ───────────────────────────────────────────────────────
@callback(
    Output({'type': 'multi-chart',        'index': MATCH}, 'figure'),
    Input({'type': 'multi-sort',          'index': MATCH}, 'value'),
    State({'type': 'multi-result-store',  'index': MATCH}, 'data'),
    State('store-theme', 'data'),
    prevent_initial_call=True,
)
def sort_multi_chart(sort_value, stored_result, theme_data):
    if not stored_result:
        return no_update
    result = copy.deepcopy(stored_result)
    ft      = result['freq_table']
    weighted = result.get('weighted', False)
    key = 'weighted_count' if weighted else 'count'
    if sort_value == 'count_desc':
        ft.sort(key=lambda x: -x.get(key, 0))
    elif sort_value == 'count_asc':
        ft.sort(key=lambda x:  x.get(key, 0))
    result['freq_table'] = ft
    theme = (theme_data or {}).get('theme', 'corporate_blue')
    return ChartVisualizer(theme=theme).create_multi_punch_chart(result)
