"""
app.py - Single entry point for SPSS Frequency Dashboard.
Three pages: / (Home), /config (Config Builder), /dashboard (Dashboard)
"""
import argparse
import os
import sys
import threading
import webbrowser
import time

import dash
from dash import Dash, html, dcc, Input, Output
import dash_bootstrap_components as dbc


def resource_path(relative):
    """Resolve path — works normally and inside PyInstaller bundle."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


_frozen = hasattr(sys, '_MEIPASS')

app = Dash(
    __name__,
    use_pages=True,
    pages_folder=resource_path('pages') if _frozen else 'pages',
    assets_folder=resource_path('assets') if _frozen else 'assets',
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
    title='SPSS Frequency Dashboard',
)
server = app.server

app.layout = html.Div([
    dcc.Store(id='store-spss-path', storage_type='session', data=''),
    dcc.Store(id='store-meta-path', storage_type='session', data=''),

    # Top nav
    html.Nav([
        html.Div([
            html.Span('📊', style={'fontSize': '20px', 'marginRight': '8px'}),
            html.Span('SPSS Frequency Dashboard',
                      style={'fontWeight': '700', 'fontSize': '15px',
                             'color': '#1E293B', 'letterSpacing': '-0.01em'}),
        ], style={'display': 'flex', 'alignItems': 'center'}),
        html.Div([
            dcc.Link('🏠 Home', href='/',
                     id='nav-home', className='nav-link'),
        ], style={'display': 'flex', 'gap': '4px', 'alignItems': 'center'}),
    ], className='app-nav'),

    dash.page_container,
], id='app-root')


@app.callback(
    Output('nav-home', 'className'),
    Input('_pages_location', 'pathname'),
)
def update_nav(pathname):
    return 'nav-link nav-link-active' if pathname == '/' else 'nav-link'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',       type=int, default=8050)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()

    url = f'http://127.0.0.1:{args.port}'
    if not args.no_browser:
        def _open():
            time.sleep(1.5)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    print('=' * 60)
    print('SPSS FREQUENCY DASHBOARD')
    print(f'URL: {url}  |  Close this window to stop')
    print('=' * 60)
    app.run(host='127.0.0.1', port=args.port, debug=False,
            dev_tools_hot_reload=False)


if __name__ == '__main__':
    main()
