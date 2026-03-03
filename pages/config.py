"""
pages/config.py  -  Config Builder page
URL: /config

config_builder.py is imported at startup so its module-level @callback
decorators register against the shared Dash app automatically.
create_app() returns just the layout (html.Div), not a Dash instance.
"""
import os
import dash
from dash import html, dcc, Input, Output, State, callback, no_update

import config_builder as _cb

dash.register_page(__name__, path="/config", title="Config Builder")


def layout():
    return html.Div([
        html.Div(id="cfg-page-content"),
    ], className="page-wrapper")


@callback(
    Output("cfg-page-content", "children"),
    Input("_pages_location",   "pathname"),
    State("store-spss-path",   "data"),
    State("store-meta-path",   "data"),
)
def render_config(pathname, spss_path, meta_path):
    if pathname != "/config":
        return no_update

    if not spss_path or not os.path.exists(spss_path):
        return html.Div([
            html.Div([
                html.H2("No SPSS file loaded", style={"color": "#64748B"}),
                html.P("Please go to Home and select an SPSS file first."),
                dcc.Link(
                    html.Button("Back to Home", className="btn-secondary"),
                    href="/",
                ),
            ], className="home-card",
               style={"textAlign": "center", "padding": "48px"}),
        ], className="home-container")

    try:
        return _cb.create_app(spss_path, meta_path or None)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return html.Div([
            html.Div([
                html.H2("Config Builder Error", style={"color": "#EF4444"}),
                html.P(str(e)),
                dcc.Link(
                    html.Button("Back to Home", className="btn-secondary"),
                    href="/",
                ),
            ], className="home-card", style={"padding": "48px"}),
        ], className="home-container")
