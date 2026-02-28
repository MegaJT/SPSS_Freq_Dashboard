from datetime import datetime
import os
import textwrap


class OutputWriter:
    """Writes frequency results to TXT output files"""
    
    def __init__(self, output_file, output_format='txt', global_filter=None, weight_variable=None):
        """
        Initialize output writer

        Args:
            output_file: Path to output file
            output_format: Accepted for backwards compatibility; only 'txt' is supported
            global_filter: Name of global filter (optional, for display)
            weight_variable: Name of weight variable (optional, for display)
        """
        self.output_file = output_file
        self.global_filter = global_filter
        self.weight_variable = weight_variable
    
    def write(self, results, warnings=None, filter_sets=None):
        """
        Write results to TXT file

        Args:
            results: List of frequency results
            warnings: List of warning messages
            filter_sets: Dict of filter sets (for global filter display)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            return self._write_text(results, warnings, filter_sets)
        except Exception as e:
            print(f"✗ Error writing output: {str(e)}")
            return False
    
    def _write_text(self, results, warnings=None, filter_sets=None):
        """
        Write results in text format
        
        Args:
            results: List of frequency results
            warnings: List of warning messages
            filter_sets: Dict of filter sets
            
        Returns:
            bool: True if successful
        """
        with open(self.output_file, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 70 + "\n")
            f.write("FREQUENCY REPORT\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            # Global filter info (if applicable)
            if self.global_filter and filter_sets and self.global_filter in filter_sets:
                f.write(f"Global Filter: {self.global_filter}\n")
                global_conditions = filter_sets[self.global_filter]
                for var_name, condition in global_conditions.items():
                    f.write(f"  - {var_name}: {self._format_condition(condition)}\n")
            
            f.write("=" * 70 + "\n\n")
            
            # Warnings section (if any)
            if warnings:
                f.write("WARNINGS\n")
                f.write("-" * 70 + "\n")
                for warning in warnings:
                    f.write(f"⚠ {warning}\n")
                f.write("\n")
            
            # Results section
            for i, result in enumerate(results, 1):
                self._write_single_result_text(f, result, i)
                f.write("\n")
            
            # Footer
            f.write("=" * 70 + "\n")
            f.write(f"End of Report - {len(results)} variable(s) processed\n")
            f.write("=" * 70 + "\n")
        
        print(f"✓ Text report written to: {self.output_file}")
        return True
    
    def _format_condition(self, condition):
        """
        Format a filter condition for display
        
        Args:
            condition: Condition dict (e.g., {"eq": 1})
        
        Returns:
            str: Formatted string
        """
        if not isinstance(condition, dict):
            return str(condition)
        
        operator = list(condition.keys())[0]
        value = condition[operator]
        
        if operator == 'eq':
            return f"= {value}"
        elif operator == 'in':
            return f"IN {value}"
        elif operator == 'between':
            return f"BETWEEN {value[0]} AND {value[1]}"
        elif operator == 'not_missing':
            return "Not Missing"
        elif operator == 'any':
            return f"Selected ANY of {value}"
        elif operator == 'all':
            return f"Selected ALL of {value}"
        elif operator == 'min_selected':
            return f"Selected at least {value} option(s)"
        else:
            return f"{operator}: {value}"
    
    def _write_single_result_text(self, f, result, index):
        """
        Write a single variable result in text format
        
        Args:
            f: File handle
            result: Single variable result dictionary
            index: Variable number
        """
        var_name = result['var_name']
        var_label = result['var_label']
        var_type = result['type']
        filter_info = result.get('filter_info')
        weighted = result.get('weighted', False)
        
        # Variable header
        f.write(f"{index}. {var_label}\n")
        f.write(f"   Variable: {var_name} | Type: {var_type.upper()}\n")
        
        # Weighting information
        if weighted:
            weight_info = result.get('weight_info', {})
            weight_var = self.weight_variable or 'WEIGHT'
            f.write(f"   Weighting: ENABLED (Variable: {weight_var})\n")
        else:
            f.write("   Weighting: DISABLED\n")
        
        # Filter information
        if filter_info:
            filter_name = filter_info['name']
            is_global = filter_info.get('is_global', False)
            
            if is_global:
                f.write(f"   Filter: {filter_name} (Global)\n")
            else:
                f.write(f"   Filter: {filter_name}\n")
            
            # Filter details
            if filter_info.get('summary'):
                f.write("   Filter Details:\n")
                for var, description in filter_info['summary'].items():
                    f.write(f"     - {var}: {description}\n")
            
            # Dataset reduction stats
            stats = filter_info['stats']
            f.write(f"   Dataset: {stats['original_count']} → {stats['filtered_count']} ")
            f.write(f"({100 - stats['exclusion_rate']:.1f}%)\n")
            
            # Small sample warning
            if stats['filtered_count'] < 30:
                f.write(f"   ⚠ WARNING: Small sample size (n={stats['filtered_count']}). ")
                f.write("Results may not be reliable.\n")
        else:
            f.write("   Filter: NONE (All respondents)\n")
        
        f.write("-" * 80 + "\n")
        
        # Weighting statistics (if weighted)
        if weighted:
            weight_info = result.get('weight_info', {})
            f.write("Weighting Statistics:\n")
            f.write(f"  Respondents with valid weights: {weight_info.get('valid_count', 0)}")
            if weight_info.get('excluded_count', 0) > 0:
                f.write(f" ({weight_info['excluded_count']} excluded due to missing/invalid weights)")
            f.write("\n")
            f.write(f"  Sum of weights: {weight_info.get('sum_weights', 0):.2f}\n")
            f.write(f"  Effective sample size (ESS): {weight_info.get('ess', 0):.0f}\n")
            f.write(f"  Design effect (DEFF): {weight_info.get('deff', 1.0):.2f}\n")
            f.write("\n")
        
        # Write frequency table based on type and weighting
        if var_type == 'single':
            if weighted:
                self._write_single_punch_weighted_text(f, result)
            else:
                self._write_single_punch_text(f, result)
        elif var_type == 'multi':
            if weighted:
                self._write_multi_punch_weighted_text(f, result)
            else:
                self._write_multi_punch_text(f, result)
    
    def _write_single_punch_text(self, f, result):
        """Write single-punch results in text format with line wrapping for long labels"""
        total = result['total_responses']
        valid = result['valid_responses']
        
        f.write(f"Total Responses: {total}\n")
        f.write(f"Valid Responses: {valid}\n\n")
        
        # Table header
        f.write(f"{'Value':<50} {'Count':>10} {'Percentage':>12}\n")
        f.write("-" * 80 + "\n")
        
        # Frequency rows
        for row in result['freq_table']:
            label = row['label']
            count = row['count']
            percentage = row['percentage']
            
            # Wrap long labels
            if len(label) > 48:
                # Split label into multiple lines (max 48 chars per line)
                wrapped_lines = textwrap.wrap(label, width=48)
                
                # First line with count and percentage
                f.write(f"{wrapped_lines[0]:<50} {count:>10} {percentage:>11.1f}%\n")
                
                # Subsequent lines (indented, no count/percentage)
                for line in wrapped_lines[1:]:
                    f.write(f"  {line}\n")
            else:
                # Single line
                f.write(f"{label:<50} {count:>10} {percentage:>11.1f}%\n")
        
        # Total line
        f.write("-" * 80 + "\n")
        f.write(f"{'TOTAL':<50} {total:>10} {'100.0%':>12}\n")

    def _write_single_punch_weighted_text(self, f, result):
        """Write weighted single-punch results in text format"""
        total_unweighted = result['total_unweighted']
        total_weighted = result['total_weighted']
        valid_unweighted = result['valid_unweighted']
        valid_weighted = result['valid_weighted']
        
        f.write(f"Total Responses: {total_unweighted} (Unweighted) | {total_weighted:.1f} (Weighted)\n")
        f.write(f"Valid Responses: {valid_unweighted} (Unweighted) | {valid_weighted:.1f} (Weighted)\n\n")
        
        # Table header
        f.write(f"{'Value':<30} {'Unweighted':>12} {'Weighted':>12} {'Percentage':>12}\n")
        f.write("-" * 80 + "\n")
        
        # Frequency rows
        for row in result['freq_table']:
            label = row['label']
            unweighted_count = row['unweighted_count']
            weighted_count = row['weighted_count']
            percentage = row['percentage']
            
            # Wrap long labels
            if len(label) > 28:
                wrapped_lines = textwrap.wrap(label, width=28)
                # First line with counts
                f.write(f"{wrapped_lines[0]:<30} {unweighted_count:>12} {weighted_count:>12.1f} {percentage:>11.1f}%\n")
                # Subsequent lines (indented)
                for line in wrapped_lines[1:]:
                    f.write(f"  {line}\n")
            else:
                f.write(f"{label:<30} {unweighted_count:>12} {weighted_count:>12.1f} {percentage:>11.1f}%\n")
        
        # Total line
        f.write("-" * 80 + "\n")
        f.write(f"{'TOTAL':<30} {total_unweighted:>12} {total_weighted:>12.1f} {'100.0%':>12}\n")    
    
    def _write_multi_punch_text(self, f, result):
        """Write multi-punch results in text format with line wrapping for long labels"""
        base = result['base']
        total = result['total_respondents']
        
        f.write(f"Total Respondents: {total}\n")
        f.write(f"Base (selected at least one): {base}\n")
        f.write(f"Percentages calculated on base of {base}\n\n")
        
        # Table header
        f.write(f"{'Option':<50} {'Count':>10} {'Percentage':>12}\n")
        f.write("-" * 80 + "\n")
        
        # Frequency rows
        for row in result['freq_table']:
            label = row['label']
            count = row['count']
            percentage = row['percentage']
            
            # Wrap long labels
            if len(label) > 48:
                # Split label into multiple lines (max 48 chars per line)
                wrapped_lines = textwrap.wrap(label, width=48)
                
                # First line with count and percentage
                f.write(f"{wrapped_lines[0]:<50} {count:>10} {percentage:>11.1f}%\n")
                
                # Subsequent lines (indented, no count/percentage)
                for line in wrapped_lines[1:]:
                    f.write(f"  {line}\n")
            else:
                # Single line
                f.write(f"{label:<50} {count:>10} {percentage:>11.1f}%\n")
        
        f.write("-" * 80 + "\n")

    def _write_multi_punch_weighted_text(self, f, result):
        """Write weighted multi-punch results in text format"""
        total_unweighted = result['total_unweighted']
        total_weighted = result['total_weighted']
        base_unweighted = result['base_unweighted']
        base_weighted = result['base_weighted']
        
        f.write(f"Total Respondents: {total_unweighted} (Unweighted) | {total_weighted:.1f} (Weighted)\n")
        f.write(f"Base (selected at least one): {base_unweighted} (Unweighted) | {base_weighted:.1f} (Weighted)\n")
        f.write(f"Percentages calculated on base (weighted) of {base_weighted:.1f}\n\n")
        
        # Table header
        f.write(f"{'Option':<30} {'Unweighted':>12} {'Weighted':>12} {'Percentage':>12}\n")
        f.write("-" * 80 + "\n")
        
        # Frequency rows
        for row in result['freq_table']:
            label = row['label']
            unweighted_count = row['unweighted_count']
            weighted_count = row['weighted_count']
            percentage = row['percentage']
            
            # Wrap long labels
            if len(label) > 28:
                wrapped_lines = textwrap.wrap(label, width=28)
                # First line with counts
                f.write(f"{wrapped_lines[0]:<30} {unweighted_count:>12} {weighted_count:>12.1f} {percentage:>11.1f}%\n")
                # Subsequent lines (indented)
                for line in wrapped_lines[1:]:
                    f.write(f"  {line}\n")
            else:
                f.write(f"{label:<30} {unweighted_count:>12} {weighted_count:>12.1f} {percentage:>11.1f}%\n")
        
        f.write("-" * 80 + "\n")
        f.write("Note: Percentages sum to >100% as respondents could select multiple options\n")



# Test function
if __name__ == "__main__":
    sample_filter_sets = {
        "complete_surveys": {
            "Q1": {"not_missing": True},
            "Q2": {"not_missing": True}
        },
        "males_only": {
            "Q1": {"eq": 1}
        }
    }

    sample_results = [
        {
            'var_name': 'Q1',
            'var_label': 'Gender',
            'type': 'single',
            'total_responses': 1000,
            'valid_responses': 980,
            'freq_table': [
                {'value': 1, 'label': 'Male', 'count': 450, 'percentage': 45.0, 'is_missing': False},
                {'value': 2, 'label': 'Female', 'count': 530, 'percentage': 53.0, 'is_missing': False},
                {'value': None, 'label': 'Missing', 'count': 20, 'percentage': 2.0, 'is_missing': True}
            ],
            'filter_info': {
                'name': 'complete_surveys',
                'summary': {'Q1': 'Not Missing', 'Q2': 'Not Missing'},
                'stats': {
                    'original_count': 1200, 'filtered_count': 1000,
                    'excluded_count': 200, 'exclusion_rate': 16.67
                },
                'is_global': True
            }
        }
    ]

    sample_warnings = ["Variable 'Q7' not found in SPSS file. Skipped."]

    print("Testing text output...")
    writer_txt = OutputWriter('test_output_filtered.txt', global_filter='complete_surveys')
    writer_txt.write(sample_results, sample_warnings, sample_filter_sets)
    print("✓ Test file created: test_output_filtered.txt")
