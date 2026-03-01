"""
dash_app.py - Interactive SPSS Frequency Dashboard

Launches a Plotly Dash web application for interactive frequency analysis.
Accepts command-line arguments for SPSS file, meta.json, and port.
"""

import argparse
import sys
import os
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go

# Dash imports
from dash import Dash, html, dcc, Input, Output, State, ctx, MATCH, ALL
import dash_bootstrap_components as dbc

# Our modules
from config_loader import ConfigLoader
from spss_reader import SPSSReader
from frequency_processor import FrequencyProcessor
from output_writer import OutputWriter
from visualizer import ChartVisualizer
from filter_engine import FilterEngine


def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='SPSS Frequency Dashboard')
    parser.add_argument('--spss-path', required=True, help='Path to SPSS .sav file')
    parser.add_argument('--meta-path', required=True, help='Path to meta.json configuration')
    parser.add_argument('--port', type=int, required=True, help='Port for Dash server')
    return parser.parse_args()

def _create_error_app(errors, warnings, spss_info, config_summary, spss_path, meta_path):
    """Create Dash app showing validation errors"""
    
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.FLATLY],
        suppress_callback_exceptions=True
    )
    
    # Build error list items
    error_items = [
        html.Li(
            html.Div([
                html.Span("❌ ", className="error-icon"),
                html.Span(err, className="error-text")
            ], className="error-item-content")
        )
        for err in errors
    ]
    
    # Build warning list items
    warning_items = [
        html.Li(
            html.Div([
                html.Span("⚠️ ", className="warning-icon"),
                html.Span(warn, className="warning-text")
            ], className="warning-item-content")
        )
        for warn in warnings
    ]
    
    # Build info cards
    info_cards = []
    
    if spss_info:
        info_cards.append(
            html.Div([
                html.H4("📊 SPSS File Info", className="info-card-title"),
                html.Div([
                    html.Div([
                        html.Span("Total Rows:", className="info-label"),
                        html.Span(f"{spss_info.get('total_rows', 0):,}", className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Total Columns:", className="info-label"),
                        html.Span(f"{spss_info.get('total_columns', 0):,}", className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Memory Usage:", className="info-label"),
                        html.Span(f"{spss_info.get('memory_usage_mb', 0)} MB", className="info-value")
                    ], className="info-row")
                ], className="info-card-content")
            ], className="info-card")
        )
    
    if config_summary:
        info_cards.append(
            html.Div([
                html.H4("⚙️ Configuration Summary", className="info-card-title"),
                html.Div([
                    html.Div([
                        html.Span("Variables:", className="info-label"),
                        html.Span(f"{config_summary.get('total_variables', 0)}", className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Single-Punch:", className="info-label"),
                        html.Span(f"{config_summary.get('single_punch_count', 0)}", className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Multi-Punch:", className="info-label"),
                        html.Span(f"{config_summary.get('multi_punch_count', 0)}", className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Filter Sets:", className="info-label"),
                        html.Span(f"{config_summary.get('filter_sets_count', 0)}", className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Weighting:", className="info-label"),
                        html.Span("Enabled" if config_summary.get('weighting_enabled') else "Disabled", className="info-value")
                    ], className="info-row")
                ], className="info-card-content")
            ], className="info-card")
        )
    
    app.layout = html.Div([
        # Header
        html.Div([
            html.H1("⚠️ Configuration Validation Failed", className="error-page-title"),
            html.P("The dashboard cannot start due to configuration errors. Please fix the issues below and reload.",
                   className="error-page-subtitle")
        ], className="error-page-header"),
        
        # Main Content
        html.Div([
            # Errors Section (Always shown if errors exist)
            html.Div([
                html.H3(f"🚫 Errors ({len(errors)})", className="error-section-title"),
                html.P("These issues must be fixed before the dashboard can start:", className="error-section-desc"),
                html.Ul(error_items, className="error-list")
            ], className="error-section"),
            
            # Warnings Section (Only if warnings exist)
            html.Div([
                html.H3(f"⚡ Warnings ({len(warnings)})", className="warning-section-title"),
                html.P("These issues should be reviewed but won't prevent the dashboard from starting:",
                       className="warning-section-desc"),
                html.Ul(warning_items, className="warning-list")
            ], className="warning-section") if warnings else None,
            
            # Info Cards
            html.Div(info_cards, className="info-cards-container") if info_cards else None,
            
            # File Paths
            html.Div([
                html.H4("📁 File Paths", className="file-paths-title"),
                html.Div([
                    html.Div([
                        html.Span("SPSS File:", className="path-label"),
                        html.Span(spss_path, className="path-value", title=spss_path)
                    ], className="path-row"),
                    html.Div([
                        html.Span("Meta Config:", className="path-label"),
                        html.Span(meta_path, className="path-value", title=meta_path)
                    ], className="path-row")
                ], className="file-paths-content")
            ], className="file-paths-section"),
            
            # Action Buttons
            html.Div([
                html.Button(
                    "🔄 Reload Configuration",
                    id="reload-btn",
                    className="action-btn action-btn-primary",
                    n_clicks=0
                ),
                html.A(
                    "📋 Copy Error Report",
                    id="copy-errors-btn",
                    className="action-btn action-btn-secondary",
                    n_clicks=0
                ),
                dcc.Clipboard(
                    id="error-clipboard",
                    content="\n".join(errors),
                    className="hidden-clipboard"
                )
            ], className="action-buttons")
            
        ], className="error-page-content"),
        
        # Footer
        html.Div([
            html.P("SPSS Frequency Dashboard | Validation Error Page", className="error-footer-text"),
            html.P(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", className="error-footer-text")
        ], className="error-page-footer"),
        
        # Hidden store for reload trigger
        dcc.Store(id='store-paths', data={'spss_path': spss_path, 'meta_path': meta_path})
        
    ], className="error-page-wrapper")
    
    # Add reload callback
    @app.callback(
        Output('store-paths', 'data', allow_duplicate=True),
        Input('reload-btn', 'n_clicks'),
        prevent_initial_call=True
    )
    def trigger_reload(n_clicks):
        """Trigger page reload"""
        from dash import ctx, no_update
        if ctx.triggered_id == 'reload-btn':
            # Return same paths to trigger reload
            return {'spss_path': spss_path, 'meta_path': meta_path, 'reload': True}
        return no_update
    
    return app


def create_dashboard(spss_path, meta_path):
    """Create the Dash application instance"""
    
    # ✅ VALIDATE FIRST
    print("\n🔍 Validating configuration...")
    
    from validator import SPSSMetaValidator
    validator = SPSSMetaValidator(spss_path, meta_path)
    is_valid, errors, warnings = validator.validate(tkinter_mode=True)
    
    if not is_valid:
        print(f"\n❌ Validation FAILED with {len(errors)} error(s):")
        for error in errors:
            print(f"  - {error}")
        spss_info = validator.get_spss_info()
        config_summary = validator.get_config_summary()
        return _create_error_app(errors, warnings, spss_info, config_summary, spss_path, meta_path)
    
    print(f"\n✅ Validation PASSED")
    
    # ... rest of dashboard creation ...
    if warnings:
        print(f"⚠️  {len(warnings)} warning(s):")
        for warning in warnings:
            print(f"  - {warning}")
    
    # Load configuration and data
    config, reader, processor, variables_list, filter_sets, global_filter = _load_data(spss_path, meta_path)
    
    # Initialize visualizer
    theme = config.get('visualization', {}).get('theme', 'corporate_blue')
    visualizer = ChartVisualizer(theme=theme)
    
    # Build variable options for checkboxes
    var_options = []
    for i, var in enumerate(variables_list):
        var_options.append({
            'label': f"{var['label']} ({var['name']})",
            'value': i,
            'type': var['type'],
            'config': var
        })
    
    # Build filter options for dropdown
    filter_options = [{'label': 'No Filter (All Data)', 'value': '__none__'}]
    if global_filter:
        filter_options.append({'label': f'⭐ {global_filter} (Global Default)', 'value': global_filter})
    for filter_name in filter_sets.keys():
        if filter_name != global_filter:
            filter_options.append({'label': filter_name, 'value': filter_name})
    
    # Default filter selection
    default_filter = global_filter if global_filter else '__none__'
    
    # Default variable selection (all variables)
    default_variables = list(range(len(variables_list)))
    
    # Get SPSS and config info for display
    spss_info = validator.get_spss_info()
    config_summary = validator.get_config_summary()
    
    # Create Dash app instance
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.FLATLY],
        suppress_callback_exceptions=True
    )
    
    # Set app layout
    app.layout = _create_layout(
        var_options=var_options,
        filter_options=filter_options,
        default_filter=default_filter,
        default_variables=default_variables,
        config=config,
        reader=reader,
        processor=processor,
        visualizer=visualizer,
        variables_list=variables_list,
        filter_sets=filter_sets,
        spss_path=spss_path,
        meta_path=meta_path,
        spss_info=spss_info,
        config_summary=config_summary,
        warnings=warnings
    )
    
    # Register callbacks
    _register_callbacks(app, reader, processor, visualizer, variables_list, filter_sets, config, spss_path, meta_path)
    
    return app

def _load_data(spss_path, meta_path):
    """Load SPSS data and configuration"""
    print(f"\nLoading SPSS file: {spss_path}")
    print(f"Loading configuration: {meta_path}")
    
    # Load configuration and pass the SPSS path
    loader = ConfigLoader(meta_path, spss_file_path=spss_path)
    config = loader.load()
    is_valid, errors = loader.validate()
    
    if not is_valid:
        print(f"\n⚠ Configuration warnings:")
        for error in errors:
            print(f"  - {error}")
    
    # Read SPSS file
    reader = SPSSReader(spss_path)
    if not reader.read():
        raise Exception("Failed to read SPSS file")
    
    # Extract configuration
    filter_sets = config.get('filter_sets', {})
    global_filter = config.get('global_filter', None)
    weighting_config = config.get('weighting', {})
    variables_list = config.get('variables', [])
    
    # Initialize processor
    processor = FrequencyProcessor(
        reader,
        filter_sets=filter_sets,
        global_filter=global_filter,
        weighting_config=weighting_config
    )
    
    print(f"✓ Loaded {len(variables_list)} variables")
    print(f"✓ Loaded {len(filter_sets)} filter sets")
    if global_filter:
        print(f"✓ Global filter: {global_filter}")
    
    return config, reader, processor, variables_list, filter_sets, global_filter


def _create_layout(var_options, filter_options, default_filter, default_variables,
                   config, reader, processor, visualizer, variables_list, filter_sets,
                   spss_path, meta_path, spss_info, config_summary, warnings):
    """Create the Dash app layout"""
    
    # Get dataset info
    data_info = reader.get_info()
    total_rows = data_info['n_rows'] if data_info else 0
    
    # Weighting status
    weighting_enabled = config.get('weighting', {}).get('enabled', False)
    weight_var = config.get('weighting', {}).get('weight_variable', 'N/A') if weighting_enabled else 'N/A'
    
    return html.Div([
        # Custom CSS
        dcc.Store(id='store-data', data={
            'spss_path': spss_path,
            'meta_path': meta_path,
            'total_rows': total_rows
        }),
        
        # Color theme store
        dcc.Store(id='store-theme', data={'theme': 'corporate_blue'}),
        
        # Header
        html.Div([
            html.Div([
                html.H1(f"📊 {os.path.splitext(os.path.basename(spss_path))[0]} - Dashboard", className="dashboard-title"),
                html.P(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", className="dashboard-subtitle")
            ], className="header-content")
        ], className="dashboard-header"),
        
        # Main container
        html.Div([
            # Sidebar
            html.Div([
                # Theme Selection
                html.Div([
                    html.H3("🎨 Chart Theme", className="sidebar-section-title"),
                    html.Label("Select Color Scheme:", className="sidebar-label"),
                    dcc.Dropdown(
                        id='theme-dropdown',
                        options=[
                            {'label': '🔵 Corporate Blue', 'value': 'corporate_blue'},
                            {'label': '💜 Modern', 'value': 'modern'},
                            {'label': '🏢 Professional', 'value': 'professional'},
                            {'label': '🌈 Vibrant', 'value': 'vibrant'}
                        ],
                        value='corporate_blue',
                        clearable=False,
                        className="sidebar-dropdown"
                    )
                ], className="sidebar-section"),
                
                html.Hr(className="sidebar-divider"),
                
                # Filter Section
                html.Div([
                    html.H3("🔍 Filters", className="sidebar-section-title"),
                    html.Label("Apply Filter:", className="sidebar-label"),
                    dcc.Dropdown(
                        id='filter-dropdown',
                        options=filter_options,
                        value=default_filter,
                        clearable=False,
                        className="sidebar-dropdown"
                    )
                ], className="sidebar-section"),
                
                html.Hr(className="sidebar-divider"),
                
                # Variable Selection
                html.Div([
                    html.H3("📋 Variables", className="sidebar-section-title"),
                    html.Label("Select Variables to Display:", className="sidebar-label"),
                    dcc.Checklist(
                        id='variable-checklist',
                        options=var_options,
                        value=default_variables,
                        className="sidebar-checklist"
                    )
                ], className="sidebar-section"),
                
                html.Hr(className="sidebar-divider"),
                
                # Dataset Info
                html.Div([
                    html.H3("ℹ️ Dataset Info", className="sidebar-section-title"),
                    html.Div([
                        html.Span("Total Records: ", className="info-label"),
                        html.Span(f"{total_rows:,}", className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Weighting: ", className="info-label"),
                        html.Span("Enabled" if weighting_enabled else "Disabled", className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Weight Variable: ", className="info-label"),
                        html.Span(weight_var, className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Variables: ", className="info-label"),
                        html.Span(str(len(variables_list)), className="info-value")
                    ], className="info-row"),
                    html.Div([
                        html.Span("Filters: ", className="info-label"),
                        html.Span(str(len(filter_sets)), className="info-value")
                    ], className="info-row")
                ], className="sidebar-section"),
                
            ], className="sidebar"),
            
            # Main Content
            html.Div([
                # Status Bar
                html.Div([
                    html.Span("📈 ", className="status-icon"),
                    html.Span("Select variables and apply filters to view frequencies", className="status-text"),
                    dcc.Loading(
                        children=html.Div(id='loading-indicator', className="loading-text"),
                        type="circle",
                        color="#2E86AB"
                    )
                ], className="status-bar"),
                
                # Charts Container
                html.Div(id='charts-container', className="charts-container")
                
            ], className="main-content")
            
        ], className="container"),
        
        # Footer
        html.Div([
            html.P("SPSS Frequency Dashboard | Market Research Data Processing", className="footer-text"),
            html.P(f"Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", className="footer-text")
        ], className="dashboard-footer")
        
    ], className="dashboard-wrapper")


def _register_callbacks(app, reader, processor, visualizer, variables_list, filter_sets, config, spss_path, meta_path):
    """Register all Dash callbacks"""
    
    # Theme change callback - update store when theme dropdown changes
    @app.callback(
        Output('store-theme', 'data'),
        Input('theme-dropdown', 'value'),
        prevent_initial_call=False
    )
    def update_theme_store(selected_theme):
        """Store selected theme"""
        return {'theme': selected_theme}
    
    @app.callback(
        [Output('charts-container', 'children'),
         Output('loading-indicator', 'children')],
        [Input('filter-dropdown', 'value'),
         Input('variable-checklist', 'value'),
         Input('store-theme', 'data')],
        prevent_initial_call=False
    )
    def update_charts(selected_filter, selected_variables, theme_data):
        """Update charts based on filter, variable selection, and theme"""
        
        if not selected_variables:
            return [html.Div([
                html.P("⚠️ No variables selected. Please select at least one variable from the sidebar.",
                       className="no-data-message")
            ], className="no-data-container")], ""
        
        # Get selected theme from store
        selected_theme = theme_data.get('theme', 'corporate_blue') if theme_data else 'corporate_blue'
        theme_visualizer = ChartVisualizer(theme=selected_theme)
        
        # Get filter conditions
        filter_name = selected_filter if selected_filter != '__none__' else None
        filter_conditions = filter_sets.get(filter_name, {}) if filter_name else None
        
        # Apply filter to get filtered data
        if filter_conditions:
            filter_engine = FilterEngine(reader.get_data(), variables_list)
            try:
                filtered_data, filter_summary, stats = filter_engine.apply_filter_set(
                    filter_name, filter_conditions
                )
                filter_info = {
                    'name': filter_name,
                    'summary': filter_summary,
                    'stats': stats,
                    'is_global': (filter_name == config.get('global_filter'))
                }
            except Exception as e:
                filtered_data = reader.get_data()
                filter_info = None
        else:
            filtered_data = reader.get_data()
            filter_info = None
        
        # Generate charts for selected variables
        chart_cards = []
        
        for var_idx in selected_variables:
            if var_idx >= len(variables_list):
                continue
            
            var_config = variables_list[var_idx]
            var_name = var_config.get('name')
            var_type = var_config.get('type')
            var_label = var_config.get('label', var_name)
            sub_variables = var_config.get('sub_variables', [])
            sub_variable_labels = var_config.get('sub_variable_labels', {})
            
            # Process variable
            if var_type == 'single':
                json_value_labels = var_config.get('value_labels', None)
                result = _process_single_variable(
                    reader, filtered_data, var_name, var_label, filter_info, config,
                    json_value_labels=json_value_labels
                )
                if result:
                    fig = theme_visualizer.create_single_punch_chart(result, 'bar')
            elif var_type == 'multi':
                result = _process_multi_variable(
                    reader, filtered_data, var_name, var_label, sub_variables, filter_info, config, sub_variable_labels
                )
                if result:
                    fig = theme_visualizer.create_multi_punch_chart(result)
            else:
                continue

            if result:
                chart_card = _create_chart_card(result, fig, var_idx)
                chart_cards.append(chart_card)
        
        if not chart_cards:
            return [html.Div([
                html.P("⚠️ No results could be generated. Check variable names and data.",
                       className="no-data-message")
            ], className="no-data-container")], ""
        
        status_msg = f"✓ Displaying {len(chart_cards)} variable(s)"
        if filter_name:
            status_msg += f" | Filter: {filter_name}"
        
        return chart_cards, status_msg

    # ── Multi-punch per-chart sort callback ──────────────────────────────
    @app.callback(
        Output({'type': 'multi-chart', 'index': MATCH}, 'figure'),
        Input({'type': 'multi-sort', 'index': MATCH}, 'value'),
        State({'type': 'multi-result-store', 'index': MATCH}, 'data'),
        State('store-theme', 'data'),
        prevent_initial_call=True
    )
    def sort_multi_chart(sort_value, stored_result, theme_data):
        """Re-render a multi-punch chart with the chosen sort order."""
        if not stored_result:
            from dash import no_update
            return no_update

        import copy
        result = copy.deepcopy(stored_result)
        freq_table = result['freq_table']
        weighted = result.get('weighted', False)

        if sort_value == 'count_desc':
            key = 'weighted_count' if weighted else 'count'
            freq_table.sort(key=lambda x: -x.get(key, 0))
        elif sort_value == 'count_asc':
            key = 'weighted_count' if weighted else 'count'
            freq_table.sort(key=lambda x: x.get(key, 0))
        # 'defined' — keep original order, no sort needed

        result['freq_table'] = freq_table

        selected_theme = theme_data.get('theme', 'corporate_blue') if theme_data else 'corporate_blue'
        theme_visualizer = ChartVisualizer(theme=selected_theme)
        return theme_visualizer.create_multi_punch_chart(result)


def _build_single_freq_table(column_data, value_labels, total):
    """Build an ordered single-punch freq_table. Missing always last.
    value_labels defines both labels AND display order."""
    import numpy as np
    value_counts = column_data.value_counts(dropna=False)

    if value_labels:
        ordered_values = list(value_labels.keys())
        labeled_set = set(value_labels.keys())
        extras = sorted([v for v in value_counts.index if not pd.isna(v) and v not in labeled_set])
        ordered_values = ordered_values + extras
    else:
        ordered_values = sorted([v for v in value_counts.index if not pd.isna(v)])

    freq_table = []
    valid_total = 0
    for value in ordered_values:
        count = value_counts.get(value, 0)
        label = value_labels.get(value, str(value)) if value_labels else str(value)
        percentage = (count / total) * 100 if total > 0 else 0
        freq_table.append({
            'value': value, 'label': label, 'count': count,
            'percentage': percentage, 'is_missing': False
        })
        valid_total += count

    # Append missing last
    missing_count = 0
    for k in value_counts.index:
        if pd.isna(k):
            missing_count = value_counts[k]
            break
    if missing_count > 0:
        freq_table.append({
            'value': None, 'label': 'Missing',
            'count': missing_count,
            'percentage': (missing_count / total) * 100 if total > 0 else 0,
            'is_missing': True
        })
    return freq_table, valid_total


def _process_single_variable(reader, data, var_name, var_label, filter_info, config, json_value_labels=None):
    """Process a single-punch variable.
    json_value_labels: optional dict from JSON config that overrides SPSS labels
    and defines display order.
    """
    weighting_config = config.get('weighting', {})
    weighting_enabled = weighting_config.get('enabled', False)

    if var_name not in data.columns:
        return None

    column_data = data[var_name]
    spss_value_labels = reader.get_value_labels(var_name)
    # JSON labels take precedence — they also define display order
    value_labels = json_value_labels if json_value_labels else spss_value_labels
    total = len(column_data)

    if weighting_enabled:
        try:
            from weight_calculator import WeightCalculator
            temp_calc = WeightCalculator(data, weighting_config['weight_variable'])
            valid_data, _ = temp_calc.get_valid_data_and_weights()
            weighted_result = temp_calc.calculate_weighted_frequencies_single(
                valid_data[var_name], value_labels
            )
            return {
                'var_name': var_name, 'var_label': var_label,
                'type': 'single', 'weighted': True,
                'total_unweighted': weighted_result['total_unweighted'],
                'total_weighted': weighted_result['total_weighted'],
                'valid_unweighted': weighted_result['valid_unweighted'],
                'valid_weighted': weighted_result['valid_weighted'],
                'freq_table': weighted_result['freq_table'],
                'filter_info': filter_info,
                'weight_info': temp_calc.get_validation_info(),
                'weighting_warning': None
            }
        except Exception as e:
            print(f"  ⚠ Weighting failed for '{var_name}': {str(e)}. Falling back to unweighted.")
            weighting_warning = f"⚠ Weighting failed: {str(e)}. Showing unweighted data."
            freq_table, valid_total = _build_single_freq_table(column_data, value_labels, total)
            return {
                'var_name': var_name, 'var_label': var_label,
                'type': 'single', 'weighted': False,
                'total_responses': total, 'valid_responses': valid_total,
                'freq_table': freq_table, 'filter_info': filter_info,
                'weighting_warning': weighting_warning
            }

    # Unweighted
    freq_table, valid_total = _build_single_freq_table(column_data, value_labels, total)
    return {
        'var_name': var_name, 'var_label': var_label,
        'type': 'single', 'weighted': False,
        'total_responses': total, 'valid_responses': valid_total,
        'freq_table': freq_table, 'filter_info': filter_info,
        'weighting_warning': None
    }


def _process_multi_variable(reader, data, var_name, var_label, sub_variables, filter_info, config, sub_variable_labels=None):
    """Process a multi-punch variable"""
    if sub_variable_labels is None:
        sub_variable_labels = {}
    
    weighting_config = config.get('weighting', {})
    weighting_enabled = weighting_config.get('enabled', False)
    
    existing_vars = [sv for sv in sub_variables if sv in data.columns]
    
    if not existing_vars:
        return None
    
    df = data[existing_vars].copy()
    has_any_response = (df == 1).any(axis=1)
    base = has_any_response.sum()
    
    if base == 0:
        return None
    
    if weighting_enabled:
        try:
            from weight_calculator import WeightCalculator
            temp_calc = WeightCalculator(data, weighting_config['weight_variable'])
            valid_data, valid_weights = temp_calc.get_valid_data_and_weights()
            
            sub_data_dict = {sub_var: valid_data[sub_var] for sub_var in existing_vars}
            weighted_result = temp_calc.calculate_weighted_frequencies_multi(sub_data_dict)
            
            for row in weighted_result['freq_table']:
                sub_var = row['sub_var']
                if sub_var in sub_variable_labels:
                    row['label'] = sub_variable_labels[sub_var]
                else:
                    row['label'] = reader.get_variable_label(sub_var)
            
            return {
                'var_name': var_name,
                'var_label': var_label,
                'type': 'multi',
                'weighted': True,
                'total_unweighted': weighted_result['total_unweighted'],
                'total_weighted': weighted_result['total_weighted'],
                'base_unweighted': weighted_result['base_unweighted'],
                'base_weighted': weighted_result['base_weighted'],
                'freq_table': weighted_result['freq_table'],
                'filter_info': filter_info,
                'weight_info': temp_calc.get_validation_info(),
                'weighting_warning': None
            }
        except Exception as e:
            # Weighting failed — fall back to unweighted and surface the error to the user
            print(f"  ⚠ Weighting failed for '{var_name}': {str(e)}. Falling back to unweighted.")
            weighting_warning = f"⚠ Weighting failed: {str(e)}. Showing unweighted data."
            freq_table = []
            for sub_var in existing_vars:
                label = sub_variable_labels.get(sub_var) or reader.get_variable_label(sub_var)
                count = (df[sub_var] == 1).sum()
                percentage = (count / base) * 100 if base > 0 else 0
                freq_table.append({'sub_var': sub_var, 'label': label,
                                   'count': count, 'percentage': percentage})
            # Order preserved from sub_variables list (questionnaire order)
            return {
                'var_name': var_name,
                'var_label': var_label,
                'type': 'multi',
                'weighted': False,
                'base': base,
                'total_respondents': len(df),
                'freq_table': freq_table,
                'filter_info': filter_info,
                'weighting_warning': weighting_warning
            }

    # Unweighted fallback
    freq_table = []
    
    for sub_var in existing_vars:
        if sub_var in sub_variable_labels:
            label = sub_variable_labels[sub_var]
        else:
            label = reader.get_variable_label(sub_var)
        count = (df[sub_var] == 1).sum()
        percentage = (count / base) * 100 if base > 0 else 0
        
        freq_table.append({
            'sub_var': sub_var,
            'label': label,
            'count': count,
            'percentage': percentage
        })
    
    # Order preserved from sub_variables list (questionnaire order)
    
    return {
        'var_name': var_name,
        'var_label': var_label,
        'type': 'multi',
        'weighted': False,
        'base': base,
        'total_respondents': len(df),
        'freq_table': freq_table,
        'filter_info': filter_info,
        'weighting_warning': None
    }


def _create_chart_card(result, fig, var_idx):
    """Create a chart card component"""
    var_name = result['var_name']
    var_label = result['var_label']
    var_type = result['type']
    weighted = result.get('weighted', False)
    filter_info = result.get('filter_info')

    # Build metadata badges
    badges = []
    badges.append(html.Span(f"Type: {var_type.upper()}", className="badge badge-type"))

    if var_type == 'single':
        if weighted:
            base_val = result.get('valid_weighted', 0)
            badges.append(html.Span(f"Base: {base_val:.0f} (weighted)", className="badge badge-base"))
        else:
            base_val = result.get('valid_responses', 0)
            badges.append(html.Span(f"Base: {base_val}", className="badge badge-base"))
    else:
        if weighted:
            base_val = result.get('base_weighted', 0)
            badges.append(html.Span(f"Base: {base_val:.0f} (weighted)", className="badge badge-base"))
        else:
            base_val = result.get('base', 0)
            badges.append(html.Span(f"Base: {base_val}", className="badge badge-base"))

    if weighted:
        badges.append(html.Span("⚖️ Weighted", className="badge badge-weighted"))

    if filter_info:
        badges.append(html.Span(f"🔍 Filter: {filter_info['name']}", className="badge badge-filter"))

    # Sort control — only shown for multi-punch
    sort_control = None
    if var_type == 'multi':
        sort_control = html.Div([
            html.Label("Sort:", style={
                'fontSize': '12px', 'color': '#718096',
                'marginRight': '6px', 'fontWeight': '500'
            }),
            dcc.Dropdown(
                id={'type': 'multi-sort', 'index': var_idx},
                options=[
                    {'label': 'As defined', 'value': 'defined'},
                    {'label': 'Count ↓', 'value': 'count_desc'},
                    {'label': 'Count ↑', 'value': 'count_asc'},
                ],
                value='defined',
                clearable=False,
                searchable=False,
                style={
                    'width': '140px', 'fontSize': '12px',
                    'display': 'inline-block', 'verticalAlign': 'middle'
                }
            )
        ], style={
            'display': 'flex', 'alignItems': 'center',
            'marginLeft': 'auto', 'paddingRight': '4px'
        })

    # Store original freq_table for re-sort (only needed for multi)
    result_store = None
    if var_type == 'multi':
        result_store = dcc.Store(
            id={'type': 'multi-result-store', 'index': var_idx},
            data=result
        )

    # Convert Plotly figure to dcc.Graph
    graph_id = {'type': 'multi-chart', 'index': var_idx} if var_type == 'multi' else f'chart-{var_idx}'
    graph = dcc.Graph(
        figure=fig,
        config={
            'displayModeBar': True,
            'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
            'displaylogo': False
        },
        className="chart-graph",
        id=graph_id
    )

    header_right = html.Div(
        [html.Div(badges, className="chart-badges"), sort_control] if sort_control
        else [html.Div(badges, className="chart-badges")],
        style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'flexWrap': 'wrap'}
    )

    return html.Div([
        result_store,
        html.Div([
            html.H3(var_label, className="chart-title"),
            header_right
        ], className="chart-header", style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '8px'}),
        html.Div(
            result['weighting_warning'],
            className="weighting-warning-banner",
            style={
                'background': '#FFF3CD', 'border': '1px solid #FFCA28',
                'borderRadius': '4px', 'padding': '8px 12px',
                'margin': '8px 0', 'color': '#856404', 'fontSize': '13px'
            }
        ) if result.get('weighting_warning') else None,
        html.Div([graph], className="chart-body")
    ], className="chart-card", id=f'var-section-{var_idx}')


def main():
    """Main entry point"""
    print("=" * 70)
    print("SPSS FREQUENCY DASHBOARD")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Parse arguments
    args = parse_arguments()
    
    print(f"\nSPSS File: {args.spss_path}")
    print(f"Meta Config: {args.meta_path}")
    print(f"Port: {args.port}")
    
    # Validate files exist
    if not os.path.exists(args.spss_path):
        print(f"\n✗ Error: SPSS file not found: {args.spss_path}")
        sys.exit(1)
    
    if not os.path.exists(args.meta_path):
        print(f"\n✗ Error: Meta file not found: {args.meta_path}")
        sys.exit(1)
    
    # Create and run dashboard
    try:
        app = create_dashboard(args.spss_path, args.meta_path)
        
        print(f"\n{'=' * 70}")
        print("✓ DASHBOARD READY")
        print(f"{'=' * 70}")
        print(f"URL: http://localhost:{args.port}")
        print(f"\nPress Ctrl+C to stop the server")
        print("=" * 70 + "\n")
        
        app.run(
            host='127.0.0.1',
            port=args.port,
            debug=False,
            dev_tools_hot_reload=False
        )
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()