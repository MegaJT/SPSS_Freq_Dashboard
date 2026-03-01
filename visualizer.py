import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import textwrap


class ChartVisualizer:
    """Creates beautiful, professional charts for frequency data"""
    
    # Professional color schemes
    COLOR_SCHEMES = {
        'corporate_blue': {
            'primary': '#2E86AB',
            'secondary': '#A23B72',
            'accent': '#F18F01',
            'success': '#06A77D',
            'neutral': '#5C677D',
            'gradient': ['#2E86AB', '#3D9DC6', '#4DB4E0', '#5CCBFB']
        },
        'modern': {
            'primary': '#667EEA',
            'secondary': '#764BA2',
            'accent': '#F093FB',
            'success': '#4FACFE',
            'neutral': '#9BA4B4',
            'gradient': ['#667EEA', '#764BA2', '#F093FB', '#4FACFE']
        },
        'professional': {
            'primary': '#1A5F7A',
            'secondary': '#159895',
            'accent': '#57C5B6',
            'success': '#002B5B',
            'neutral': '#7E8A97',
            'gradient': ['#002B5B', '#1A5F7A', '#159895', '#57C5B6']
        },
        'vibrant': {
            'primary': '#FF6B6B',
            'secondary': '#4ECDC4',
            'accent': '#FFE66D',
            'success': '#95E1D3',
            'neutral': '#536976',
            'gradient': ['#FF6B6B', '#4ECDC4', '#95E1D3', '#FFE66D']
        }
    }
    
    def __init__(self, theme='corporate_blue', show_values=True):
        """
        Initialize chart visualizer
        
        Args:
            theme: Color scheme name (default: 'corporate_blue')
            show_values: Show values on bars/slices (default: True)
        """
        self.theme = self.COLOR_SCHEMES.get(theme, self.COLOR_SCHEMES['corporate_blue'])
        self.show_values = show_values
        
        # Base layout configuration for all charts
        self.base_layout = {
            'font': {
                'family': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
                'size': 13,
                'color': '#2D3748'
            },
            'paper_bgcolor': '#FFFFFF',
            'plot_bgcolor': '#F7FAFC',
            'margin': {'l': 250, 'r': 40, 't': 20, 'b': 60},
            'hovermode': 'closest',
            'hoverlabel': {
                'bgcolor': 'white',
                'font_size': 13,
                'font_family': 'Arial'
            }
        }
    
    def _wrap_labels(self, labels, max_width=30):
        """
        Wrap long labels to multiple lines
        
        Args:
            labels: List of label strings
            max_width: Maximum characters per line (default: 30)
        
        Returns:
            List of wrapped labels with <br> for line breaks
        """
        wrapped = []
        for label in labels:
            if len(label) > max_width:
                # Wrap text
                lines = textwrap.wrap(label, width=max_width)
                wrapped.append('<br>'.join(lines))
            else:
                wrapped.append(label)
        return wrapped
    
    def create_single_punch_chart(self, result, chart_type='bar'):
        """
        Create chart for single-punch question
        
        Args:
            result: Frequency result dictionary
            chart_type: 'bar' (horizontal) or 'pie'
        
        Returns:
            plotly figure
        """
        weighted = result.get('weighted', False)
        
        # Extract data (exclude missing values for main chart)
        freq_table = [row for row in result['freq_table'] if not row.get('is_missing', False)]
        
        labels = [row['label'] for row in freq_table]
        
        if weighted:
            values = [row['weighted_count'] for row in freq_table]
            percentages = [row['percentage'] for row in freq_table]
        else:
            values = [row['count'] for row in freq_table]
            percentages = [row['percentage'] for row in freq_table]
        
        if chart_type == 'pie':
            return self._create_pie_chart(labels, values, percentages, result['var_label'])
        else:  # default horizontal bar
            return self._create_horizontal_bar(labels, values, percentages, result['var_label'], weighted)
    
    def create_multi_punch_chart(self, result):
        """
        Create chart for multi-punch question (horizontal bar)
        
        Args:
            result: Frequency result dictionary
        
        Returns:
            plotly figure (horizontal bar chart)
        """
        weighted = result.get('weighted', False)
        
        labels = [row['label'] for row in result['freq_table']]
        
        if weighted:
            values = [row['weighted_count'] for row in result['freq_table']]
            percentages = [row['percentage'] for row in result['freq_table']]
        else:
            values = [row['count'] for row in result['freq_table']]
            percentages = [row['percentage'] for row in result['freq_table']]
        
        return self._create_horizontal_bar(labels, values, percentages, result['var_label'], weighted)
    
    def _create_horizontal_bar(self, labels, values, percentages, title, weighted=False):
        """Create horizontal bar chart. Order is determined by the caller."""

        labels_sorted = list(labels)
        values_sorted = list(values)
        percentages_sorted = list(percentages)

        # Wrap long labels
        wrapped_labels = self._wrap_labels(labels_sorted, max_width=30)
        
        # Create custom colors with gradient
        colors = self._generate_gradient_colors(len(labels_sorted))
        
        fig = go.Figure()
        
        # Create hover text and text labels
        if weighted:
            hover_text = [f"<b>{label}</b><br>Count: {v:.1f}<br>Percentage: {p:.1f}%" 
                          for label, v, p in zip(labels_sorted, values_sorted, percentages_sorted)]
            text_labels = [f"{v:.1f} ({p:.1f}%)" for v, p in zip(values_sorted, percentages_sorted)]
        else:
            hover_text = [f"<b>{label}</b><br>Count: {v}<br>Percentage: {p:.1f}%" 
                          for label, v, p in zip(labels_sorted, values_sorted, percentages_sorted)]
            text_labels = [f"{v} ({p:.1f}%)" for v, p in zip(values_sorted, percentages_sorted)]
        
        fig.add_trace(go.Bar(
            y=wrapped_labels,  # Labels on Y-axis (horizontal bar)
            x=values_sorted,   # Values on X-axis (horizontal bar)
            orientation='h',   # HORIZONTAL orientation
            marker=dict(
                color=colors,
                line=dict(color=colors, width=1.5)
            ),
            text=text_labels,
            textposition='outside',
            textfont=dict(size=11, color=self.theme['primary']),
            hovertext=hover_text,
            hoverinfo='text'
        ))
        
        # Dynamic height based on number of items
        base_height_per_item = 50
        chart_height = max(400, len(labels_sorted) * base_height_per_item)
        
        fig.update_layout(
            **self.base_layout,
            title=None,
            xaxis={
                'title': 'Count',
                'showgrid': True,
                'gridwidth': 1,
                'gridcolor': '#E2E8F0',
                'showline': False,
                'tickfont': {'size': 11}
            },
            yaxis={
                'title': '',
                'showgrid': False,
                'showline': True,
                'linewidth': 1,
                'linecolor': '#E2E8F0',
                'tickfont': {'size': 11},
                'automargin': True
            },
            height=chart_height,
            showlegend=False
        )
        
        return fig
    
    def _create_pie_chart(self, labels, values, percentages, title):
        """Create modern pie/donut chart"""
        
        colors = self._generate_gradient_colors(len(labels))
        
        fig = go.Figure()
        
        fig.add_trace(go.Pie(
            labels=labels,
            values=values,
            marker=dict(
                colors=colors,
                line=dict(color='white', width=3)
            ),
            textinfo='label+percent',
            textfont=dict(size=13, color='white'),
            hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>',
            hole=0.4  # Creates donut chart
        ))
        
        fig.update_layout(
            **self.base_layout,
            title=None,
            height=500,
            showlegend=True,
            legend={
                'orientation': 'v',
                'yanchor': 'middle',
                'y': 0.5,
                'xanchor': 'left',
                'x': 1.05,
                'bgcolor': 'rgba(255, 255, 255, 0.8)',
                'bordercolor': '#E2E8F0',
                'borderwidth': 1
            }
        )
        
        return fig
    
    def _generate_gradient_colors(self, n):
        """Generate gradient colors from theme"""
        if n == 1:
            return [self.theme['primary']]
        
        gradient = self.theme['gradient']
        
        if n <= len(gradient):
            return gradient[:n]
        
        # Interpolate colors for more items
        colors = []
        step = len(gradient) / n
        for i in range(n):
            idx = int(i * step) % len(gradient)
            colors.append(gradient[idx])
        
        return colors


# Test function
if __name__ == "__main__":
    # Create test data with long labels
    test_result_single = {
        'var_name': 'Q1',
        'var_label': 'Gender Distribution',
        'type': 'single',
        'weighted': False,
        'total_responses': 1000,
        'valid_responses': 980,
        'freq_table': [
            {'value': 1, 'label': 'Male', 'count': 450, 'percentage': 45.9, 'is_missing': False},
            {'value': 2, 'label': 'Female', 'count': 530, 'percentage': 54.1, 'is_missing': False},
            {'value': None, 'label': 'Missing', 'count': 20, 'percentage': 2.0, 'is_missing': True}
        ]
    }
    
    test_result_multi = {
        'var_name': 'Q3',
        'var_label': 'Brand Usage (Select All That Apply)',
        'type': 'multi',
        'weighted': False,
        'base': 800,
        'total_respondents': 1000,
        'freq_table': [
            {'sub_var': 'Q3_1', 'label': 'Brand A - Premium Quality Products for Discerning Customers', 'count': 350, 'percentage': 43.75},
            {'sub_var': 'Q3_2', 'label': 'Brand B - Affordable Options for Budget-Conscious Shoppers', 'count': 420, 'percentage': 52.5},
            {'sub_var': 'Q3_3', 'label': 'Brand C - Luxury Experience', 'count': 280, 'percentage': 35.0},
            {'sub_var': 'Q3_4', 'label': 'Brand D - Value for Money', 'count': 180, 'percentage': 22.5}
        ]
    }
    
    print("Testing horizontal bar charts...")
    viz = ChartVisualizer(theme='corporate_blue')
    
    # Single-punch horizontal bar
    fig1 = viz.create_single_punch_chart(test_result_single, 'bar')
    fig1.write_html("test_horizontal_single.html")
    print("✓ Created: test_horizontal_single.html")
    
    # Multi-punch horizontal bar with long labels
    fig2 = viz.create_multi_punch_chart(test_result_multi)
    fig2.write_html("test_horizontal_multi.html")
    print("✓ Created: test_horizontal_multi.html")
    
    print("\n✓ Test charts created! Open the HTML files in your browser.")
    print("  All charts should be HORIZONTAL bars with wrapped labels.")