"""
pages/home.py - Home page: file selection, validation, export.
Replaces launcher.py entirely.
"""
import os
import sys
import threading

import dash
from dash import html, dcc, Input, Output, State, callback, no_update, ctx
import dash_bootstrap_components as dbc

dash.register_page(__name__, path='/', title='Home')


# ── File dialog helper (uses hidden Tkinter root — no window shown) ────────
def _browse_file(filetypes):
    """Open OS native file picker. Returns path string or ''."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(filetypes=filetypes, parent=root)
        root.destroy()
        return path or ''
    except Exception:
        return ''


# ── Layout ─────────────────────────────────────────────────────────────────
layout = html.Div([

    html.Div([

        # ── Header ────────────────────────────────────────────────────────
        html.Div([
            html.H1('SPSS Frequency Dashboard',
                    style={'fontSize': '28px', 'fontWeight': '700',
                           'color': '#1E293B', 'margin': '0 0 4px 0'}),
            html.P('Select your data files to get started',
                   style={'color': '#64748B', 'fontSize': '14px', 'margin': '0'}),
        ], style={'marginBottom': '32px'}),

        # ── File selection card ────────────────────────────────────────────
        html.Div([
            html.Div([
                html.H2('Data Files', className='card-title'),
                html.P('Select the SPSS data file and JSON configuration',
                       style={'color': '#64748B', 'fontSize': '13px',
                              'margin': '0 0 20px 0'}),

                # SPSS file row
                html.Div([
                    html.Label('SPSS File (.sav)',  className='field-label'),
                    html.Div([
                        dcc.Input(id='input-spss-path',
                                  placeholder='Path to .sav file…',
                                  debounce=True,
                                  className='path-input'),
                        html.Button('Browse', id='btn-browse-spss',
                                    n_clicks=0, className='btn-browse'),
                    ], className='input-row'),
                ], className='field-group'),

                # JSON config row
                html.Div([
                    html.Label('Configuration (.json)', className='field-label'),
                    html.Div([
                        dcc.Input(id='input-meta-path',
                                  placeholder='Path to config .json file…',
                                  debounce=True,
                                  className='path-input'),
                        html.Button('Browse', id='btn-browse-meta',
                                    n_clicks=0, className='btn-browse'),
                    ], className='input-row'),
                ], className='field-group'),

                # Validation status
                html.Div(id='validation-status', style={'marginTop': '16px'}),

            ], className='home-card'),
        ]),

        # ── Action buttons ─────────────────────────────────────────────────
        html.Div([
            dcc.Link(
                html.Button('📈 Open Dashboard', id='btn-go-dashboard',
                            className='btn-primary', disabled=True),
                href='/dashboard', id='link-dashboard', style={'pointerEvents': 'none'}
            ),
            dcc.Link(
                html.Button('⚙ Build / Edit Config', id='btn-go-config',
                            className='btn-secondary', disabled=True),
                href='/config', id='link-config', style={'pointerEvents': 'none'}
            ),
            html.Button('📁 Export TXT', id='btn-export',
                        className='btn-secondary', disabled=True),
        ], className='action-row'),

        # Export status + download
        html.Div(id='export-status', style={'marginTop': '12px'}),
        dcc.Download(id='download-export'),

        # Hidden interval for async export polling
        dcc.Interval(id='export-poll', interval=500, n_intervals=0, disabled=True),
        dcc.Store(id='store-export-result', data=None),

    ], className='home-container'),
], className='page-wrapper')


# ── Browse SPSS ────────────────────────────────────────────────────────────
@callback(
    Output('input-spss-path', 'value'),
    Input('btn-browse-spss', 'n_clicks'),
    prevent_initial_call=True,
)
def browse_spss(n):
    path = _browse_file([('SPSS Files', '*.sav'), ('All Files', '*.*')])
    return path if path else no_update


# ── Browse JSON ────────────────────────────────────────────────────────────
@callback(
    Output('input-meta-path', 'value'),
    Input('btn-browse-meta', 'n_clicks'),
    prevent_initial_call=True,
)
def browse_meta(n):
    path = _browse_file([('JSON Files', '*.json'), ('All Files', '*.*')])
    return path if path else no_update


# ── Validate files + update shared stores + enable/disable buttons ─────────
@callback(
    Output('store-spss-path',  'data'),
    Output('store-meta-path',  'data'),
    Output('validation-status','children'),
    Output('btn-go-dashboard', 'disabled'),
    Output('btn-go-config',    'disabled'),
    Output('btn-export',       'disabled'),
    Output('link-dashboard',   'style'),
    Output('link-config',      'style'),
    Input('input-spss-path',   'value'),
    Input('input-meta-path',   'value'),
)
def validate_paths(spss_path, meta_path):
    spss = (spss_path or '').strip()
    meta = (meta_path or '').strip()

    enabled_link  = {}
    disabled_link = {'pointerEvents': 'none'}

    # Nothing entered yet
    if not spss and not meta:
        return '', '', '', True, True, True, disabled_link, disabled_link

    msgs = []

    spss_ok = bool(spss and os.path.exists(spss) and spss.lower().endswith('.sav'))
    meta_ok = bool(meta and os.path.exists(meta) and meta.lower().endswith('.json'))

    if spss and not spss_ok:
        msgs.append(('❌ SPSS file not found or not a .sav file', 'status-error'))
    elif spss_ok:
        msgs.append(('✅ SPSS file found', 'status-ok'))

    if meta and not meta_ok:
        msgs.append(('❌ JSON file not found or not a .json file', 'status-error'))
    elif meta_ok:
        msgs.append(('✅ Config file found', 'status-ok'))

    status_el = html.Div([
        html.Div(text, className=cls) for text, cls in msgs
    ])

    # Dashboard needs both files. Config builder only needs SPSS.
    dash_ok   = spss_ok and meta_ok
    config_ok = spss_ok

    return (
        spss if spss_ok else '',
        meta if meta_ok else '',
        status_el,
        not dash_ok,          # btn-go-dashboard disabled
        not config_ok,        # btn-go-config disabled
        not dash_ok,          # btn-export disabled
        enabled_link  if dash_ok   else disabled_link,
        enabled_link  if config_ok else disabled_link,
    )


# ── Export ─────────────────────────────────────────────────────────────────
@callback(
    Output('export-status',      'children'),
    Output('download-export',    'data'),
    Output('btn-export',         'disabled', allow_duplicate=True),
    Input('btn-export',          'n_clicks'),
    State('store-spss-path',     'data'),
    State('store-meta-path',     'data'),
    prevent_initial_call=True,
)
def run_export(n_clicks, spss_path, meta_path):
    if not n_clicks or not spss_path or not meta_path:
        return no_update, no_update, no_update

    try:
        from config_loader import ConfigLoader
        from spss_reader import SPSSReader
        from frequency_processor import FrequencyProcessor
        from output_writer import OutputWriter

        # Load config
        loader = ConfigLoader(meta_path, spss_file_path=spss_path)
        config = loader.load()
        is_valid, errors = loader.validate()
        if not is_valid:
            return html.Div('❌ Config errors: ' + '; '.join(errors),
                            className='status-error'), no_update, False

        # Read SPSS
        reader = SPSSReader(spss_path)
        if not reader.read():
            return html.Div('❌ Failed to read SPSS file.',
                            className='status-error'), no_update, False

        # Process
        filter_sets    = config.get('filter_sets', {})
        global_filter  = config.get('global_filter', None)
        weighting_cfg  = config.get('weighting', {})
        processor = FrequencyProcessor(
            reader,
            filter_sets=filter_sets,
            global_filter=global_filter,
            weighting_config=weighting_cfg,
        )
        results = processor.process_all_variables(config['variables'])
        if not results:
            return html.Div('❌ No results generated.',
                            className='status-error'), no_update, False

        # Write to a temp file then send as browser download
        import tempfile
        weight_var = (weighting_cfg.get('weight_variable')
                      if weighting_cfg.get('enabled') else None)
        spss_base = os.path.splitext(os.path.basename(spss_path))[0]
        filename  = f'{spss_base}_Frequencies.txt'

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt',
                                         delete=False, encoding='utf-8') as tmp:
            tmp_path = tmp.name

        writer = OutputWriter(
            tmp_path,
            global_filter=global_filter,
            weight_variable=weight_var,
        )
        writer.write(results, processor.get_warnings(), filter_sets)

        with open(tmp_path, 'r', encoding='utf-8') as f:
            content_str = f.read()
        os.unlink(tmp_path)

        return (
            html.Div(f'✅ Export ready — {filename}', className='status-ok'),
            dcc.send_string(content_str, filename),
            False,
        )

    except Exception as e:
        import traceback; traceback.print_exc()
        return (html.Div(f'❌ Export failed: {e}', className='status-error'),
                no_update, False)
