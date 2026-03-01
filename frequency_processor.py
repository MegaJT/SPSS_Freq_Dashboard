import pandas as pd
from filter_engine import FilterEngine
from weight_calculator import WeightCalculator


class FrequencyProcessor:
    """Processes variables and calculates frequencies with filter support"""
    
    def __init__(self, spss_reader, filter_sets=None, global_filter=None, weighting_config=None):
        """
        Initialize frequency processor
        
        Args:
            spss_reader: SPSSReader instance with loaded data
            filter_sets: Dict of filter sets from meta.json (optional)
            global_filter: Name of global filter to apply (optional)
            weighting_config: Dict with weighting configuration (optional)
                             Format: {"enabled": true/false, "weight_variable": "WEIGHT"}
        """
        self.reader = spss_reader
        self.filter_sets = filter_sets or {}
        self.global_filter = global_filter
        self.weighting_config = weighting_config or {}
        self.results = []
        self.warnings = []
        self.filter_engine = None
        self.weight_calculator = None
        self.weighting_enabled = False
        
        # Initialize weighting if enabled
        if self.weighting_config.get('enabled', False):
            self._initialize_weighting()

    def _initialize_weighting(self):
        """Initialize weight calculator and validate weights"""
        weight_variable = self.weighting_config.get('weight_variable')
        
        if not weight_variable:
            self.warnings.append("Weighting enabled but no weight_variable specified. Weighting disabled.")
            return
        
        print(f"\nInitializing weighting with variable: {weight_variable}")
        
        try:
            self.weight_calculator = WeightCalculator(
                self.reader.get_data(),
                weight_variable
            )
            
            # Get and display weight validation info
            validation_info = self.weight_calculator.get_validation_info()
            weight_warnings = self.weight_calculator.get_warnings()
            
            # Add weight warnings to overall warnings
            if weight_warnings:
                print("\n⚠ WEIGHTING WARNINGS:")
                for warning in weight_warnings:
                    print(f"  - {warning}")
                    self.warnings.append(f"Weighting: {warning}")
            
            # Display validation statistics
            print(f"\nWeighting Statistics:")
            print(f"  Total respondents: {validation_info['total_respondents']}")
            print(f"  Valid weights: {validation_info['valid_count']}")
            print(f"  Excluded: {validation_info['excluded_count']}")
            print(f"  Sum of weights: {validation_info['sum_weights']:.2f}")
            print(f"  Effective sample size (ESS): {validation_info['ess']:.0f}")
            print(f"  Design effect (DEFF): {validation_info['deff']:.2f}")
            
            self.weighting_enabled = True
            
        except Exception as e:
            warning = f"Failed to initialize weighting: {str(e)}. Proceeding without weights."
            self.warnings.append(warning)
            print(f"  ⚠ {warning}")
            self.weighting_enabled = False        
    
    def process_all_variables(self, variables_config):
        """
        Process all variables from configuration
        
        Args:
            variables_config: List of variable configurations from meta.json
            
        Returns:
            list: List of frequency results
        """
        print("\n" + "="*50)
        print("PROCESSING VARIABLES")
        print("="*50)
        
        # Initialize filter engine with variables config (for multi-punch inference)
        self.filter_engine = FilterEngine(self.reader.get_data(), variables_config)
        
        for var_config in variables_config:
            var_name = var_config.get('name')
            var_type = var_config.get('type')
            var_label = var_config.get('label', var_name)
            
            print(f"\nProcessing: {var_name} ({var_type})")
            
            # Determine which filter to use
            filter_to_use = self._determine_filter(var_config)
            
            # Apply filter if needed
            if filter_to_use:
                filtered_data, filter_info = self._apply_filter(filter_to_use)
                
                # Check if filter resulted in data
                if len(filtered_data) == 0:
                    warning = f"Variable '{var_name}' skipped: Filter '{filter_to_use}' resulted in 0 respondents"
                    self.warnings.append(warning)
                    print(f"  ⚠ {warning}")
                    continue
                
                # Check for small sample warning
                if len(filtered_data) < 30:
                    warning = f"Small sample size for '{var_name}': n={len(filtered_data)} (filter: {filter_to_use})"
                    self.warnings.append(warning)
                    print(f"  ⚠ {warning}")
            else:
                filtered_data = self.reader.get_data()
                filter_info = None
            
            # Process based on type
            if var_type == 'single':
                json_value_labels = var_config.get('value_labels', None)
                result = self.process_single_punch(var_name, var_label, filtered_data, filter_info, json_value_labels)
            elif var_type == 'multi':
                sub_vars = var_config.get('sub_variables', [])
                sub_var_labels = var_config.get('sub_variable_labels', {})
                result = self.process_multi_punch(var_name, var_label, sub_vars, filtered_data, filter_info, sub_var_labels)
            else:
                self.warnings.append(f"Unknown variable type '{var_type}' for {var_name}")
                continue
            
            if result:
                self.results.append(result)
        
        return self.results
    
    def _determine_filter(self, var_config):
        """
        Determine which filter to use for a variable
        
        Args:
            var_config: Variable configuration dict
        
        Returns:
            str: Filter set name, or None if no filter
        """
        # Priority: variable filter_set > global_filter > none
        if 'filter_set' in var_config:
            return var_config['filter_set']
        elif self.global_filter:
            return self.global_filter
        else:
            return None
    
    def _apply_filter(self, filter_set_name):
        """
        Apply a filter set to the data
        
        Args:
            filter_set_name: Name of filter set
        
        Returns:
            tuple: (filtered_data, filter_info_dict)
        """
        if filter_set_name not in self.filter_sets:
            warning = f"Filter set '{filter_set_name}' not found in configuration"
            self.warnings.append(warning)
            print(f"  ⚠ {warning}")
            return self.reader.get_data(), None
        
        filter_conditions = self.filter_sets[filter_set_name]
        
        try:
            filtered_data, filter_summary, stats = self.filter_engine.apply_filter_set(
                filter_set_name, filter_conditions
            )
            
            # Build filter info for output
            filter_info = {
                'name': filter_set_name,
                'summary': filter_summary,
                'stats': stats,
                'is_global': (filter_set_name == self.global_filter)
            }
            
            print(f"  Filter: {filter_set_name}")
            print(f"    {stats['original_count']} → {stats['filtered_count']} respondents ({100 - stats['exclusion_rate']:.1f}%)")
            
            return filtered_data, filter_info
            
        except Exception as e:
            warning = f"Error applying filter '{filter_set_name}': {str(e)}"
            self.warnings.append(warning)
            print(f"  ⚠ {warning}")
            return self.reader.get_data(), None
    
    def process_single_punch(self, var_name, var_label, data, filter_info=None, json_value_labels=None):
        """
        Process a single-punch (single choice) variable
        
        Args:
            var_name: Variable name in SPSS
            var_label: Display label for the variable
            data: DataFrame to use (filtered or full)
            filter_info: Filter information dict (optional)
            
        Returns:
            dict: Frequency results or None if variable doesn't exist
        """
        # Check if variable exists
        if var_name not in data.columns:
            warning = f"Variable '{var_name}' not found in SPSS file. Skipped."
            self.warnings.append(warning)
            print(f"  ⚠ {warning}")
            return None
        
        # Get data and value labels.
        # JSON value_labels (if present) override SPSS value labels and also
        # define the display order (questionnaire order).
        column_data = data[var_name]
        spss_value_labels = self.reader.get_value_labels(var_name)
        value_labels = json_value_labels if json_value_labels else spss_value_labels

        # Check if weighting is enabled
        if self.weighting_enabled:
            # Apply weighting
            try:
                temp_calc = WeightCalculator(data, self.weighting_config['weight_variable'])
                valid_data, valid_weights = temp_calc.get_valid_data_and_weights()

                # Pass merged value_labels so weighted calc respects the same order
                weighted_result = temp_calc.calculate_weighted_frequencies_single(
                    valid_data[var_name],
                    value_labels
                )
                
                result = {
                    'var_name': var_name,
                    'var_label': var_label,
                    'type': 'single',
                    'weighted': True,
                    'total_unweighted': weighted_result['total_unweighted'],
                    'total_weighted': weighted_result['total_weighted'],
                    'valid_unweighted': weighted_result['valid_unweighted'],
                    'valid_weighted': weighted_result['valid_weighted'],
                    'freq_table': weighted_result['freq_table'],
                    'filter_info': filter_info,
                    'weight_info': temp_calc.get_validation_info()
                }
                
                print(f"  ✓ Processed (weighted). Valid: {result['valid_unweighted']} (unweighted) | "
                      f"{result['valid_weighted']:.1f} (weighted)")
                
            except Exception as e:
                warning = f"Error calculating weighted frequencies for '{var_name}': {str(e)}. Using unweighted."
                self.warnings.append(warning)
                print(f"  ⚠ {warning}")
                # Fall back to unweighted
                return self._process_single_punch_unweighted(var_name, var_label, data, filter_info, value_labels)
        else:
            # Unweighted calculation
            result = self._process_single_punch_unweighted(var_name, var_label, data, filter_info, value_labels)
        
        return result
    
    def _process_single_punch_unweighted(self, var_name, var_label, data, filter_info=None, value_labels=None):
        """Process single-punch without weighting.
        value_labels defines both labels and display order (questionnaire order).
        """
        column_data = data[var_name]
        if value_labels is None:
            value_labels = self.reader.get_value_labels(var_name)

        # Pre-compute counts once
        value_counts = column_data.value_counts(dropna=False)
        total = len(column_data)

        # Build frequency table in value_labels order, then append missing last.
        freq_table = []
        valid_total = 0

        if value_labels:
            ordered_values = list(value_labels.keys())
            # Any values in data but not in labels (edge case)
            labeled_set = set(value_labels.keys())
            extras = sorted([v for v in value_counts.index if not pd.isna(v) and v not in labeled_set])
            ordered_values = ordered_values + extras
        else:
            ordered_values = sorted([v for v in value_counts.index if not pd.isna(v)])

        for value in ordered_values:
            count = value_counts.get(value, 0)
            label = value_labels.get(value, str(value)) if value_labels else str(value)
            percentage = (count / total) * 100 if total > 0 else 0
            freq_table.append({
                'value': value,
                'label': label,
                'count': count,
                'percentage': percentage,
                'is_missing': False
            })
            valid_total += count

        # Always append missing last
        missing_count = value_counts.get(float('nan'), 0)
        if missing_count == 0:
            # pandas NaN key — try the actual NaN
            import numpy as np
            for k in value_counts.index:
                if pd.isna(k):
                    missing_count = value_counts[k]
                    break
        if missing_count > 0:
            percentage = (missing_count / total) * 100 if total > 0 else 0
            freq_table.append({
                'value': None,
                'label': 'Missing',
                'count': missing_count,
                'percentage': percentage,
                'is_missing': True
            })
        
        result = {
            'var_name': var_name,
            'var_label': var_label,
            'type': 'single',
            'weighted': False,
            'total_responses': total,
            'valid_responses': valid_total,
            'freq_table': freq_table,
            'filter_info': filter_info
        }
        
        print(f"  ✓ Processed. Valid responses: {valid_total}/{total}")
        return result
    
    def process_multi_punch(self, var_name, var_label, sub_variables, data, filter_info=None, sub_variable_labels=None):
        """
        Process a multi-punch (multiple choice) variable
        
        Args:
            var_name: Variable name (for display)
            var_label: Display label for the variable
            sub_variables: List of sub-variable names (binary columns)
            data: DataFrame to use (filtered or full)
            filter_info: Filter information dict (optional)
            sub_variable_labels: Dict mapping sub_variable names to custom labels (optional)
            
        Returns:
            dict: Frequency results or None if variables don't exist
        """
        if sub_variable_labels is None:
            sub_variable_labels = {}
        # Check which sub-variables exist
        existing_vars = []
        missing_vars = []
        
        for sub_var in sub_variables:
            if sub_var in data.columns:
                existing_vars.append(sub_var)
            else:
                missing_vars.append(sub_var)
        
        if missing_vars:
            warning = f"Sub-variables not found for '{var_name}': {', '.join(missing_vars)}"
            self.warnings.append(warning)
            print(f"  ⚠ {warning}")
        
        if not existing_vars:
            warning = f"No sub-variables found for '{var_name}'. Skipped."
            self.warnings.append(warning)
            print(f"  ⚠ {warning}")
            return None
        
        # Check if weighting is enabled
        if self.weighting_enabled:
            # Apply weighting
            try:
                # Create temporary weight calculator for filtered data
                temp_calc = WeightCalculator(data, self.weighting_config['weight_variable'])
                valid_data, valid_weights = temp_calc.get_valid_data_and_weights()
                
                # Prepare sub-data dict
                sub_data_dict = {sub_var: valid_data[sub_var] for sub_var in existing_vars}
                
                # Get labels for sub-variables
                for sub_var in sub_data_dict.keys():
                    # labels are retrieved later when building freq_table; nothing needed here
                
                    # Calculate weighted frequencies
                    weighted_result = temp_calc.calculate_weighted_frequencies_multi(sub_data_dict)
                
                # Add labels to freq_table - use sub_variable_labels if available, else reader
                for row in weighted_result['freq_table']:
                    sub_var = row['sub_var']
                    if sub_var in sub_variable_labels:
                        row['label'] = sub_variable_labels[sub_var]
                    else:
                        row['label'] = self.reader.get_variable_label(sub_var)
                
                result = {
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
                    'weight_info': temp_calc.get_validation_info()
                }
                
                print(f"  ✓ Processed (weighted). Base: {result['base_unweighted']} (unweighted) | "
                      f"{result['base_weighted']:.1f} (weighted)")
                
            except Exception as e:
                warning = f"Error calculating weighted frequencies for '{var_name}': {str(e)}. Using unweighted."
                self.warnings.append(warning)
                print(f"  ⚠ {warning}")
                # Fall back to unweighted
                return self._process_multi_punch_unweighted(var_name, var_label, sub_variables, data, filter_info, sub_variable_labels)
        else:
            # Unweighted calculation
            result = self._process_multi_punch_unweighted(var_name, var_label, sub_variables, data, filter_info, sub_variable_labels)
        
        return result
    
    def get_results(self):
        """Get all frequency results"""
        return self.results
    
    def get_warnings(self):
        """Get all warnings generated during processing"""
        return self.warnings


    def _process_multi_punch_unweighted(self, var_name, var_label, sub_variables, data, filter_info=None, sub_variable_labels=None):
        """Process multi-punch without weighting (original logic)"""
        if sub_variable_labels is None:
            sub_variable_labels = {}
        
        # Get existing sub-variables
        existing_vars = [sv for sv in sub_variables if sv in data.columns]
        
        if not existing_vars:
            return None
        
        # Get data for all sub-variables
        df = data[existing_vars].copy()
        
        # Calculate base: respondents who selected at least one option
        has_any_response = (df == 1).any(axis=1)
        base = has_any_response.sum()
        
        if base == 0:
            warning = f"No responses found for '{var_name}'. Skipped."
            self.warnings.append(warning)
            print(f"  ⚠ {warning}")
            return None
        
        # Calculate frequencies for each option
        freq_table = []
        
        for sub_var in existing_vars:
            # Get label for this sub-variable - prefer sub_variable_labels if available
            if sub_var in sub_variable_labels:
                label = sub_variable_labels[sub_var]
            else:
                label = self.reader.get_variable_label(sub_var)
            
            # Count how many selected this option (value = 1)
            count = (df[sub_var] == 1).sum()
            percentage = (count / base) * 100 if base > 0 else 0
            
            freq_table.append({
                'sub_var': sub_var,
                'label': label,
                'count': count,
                'percentage': percentage
            })
        
        # Order preserved from sub_variables list (questionnaire order)

        
        result = {
            'var_name': var_name,
            'var_label': var_label,
            'type': 'multi',
            'weighted': False,
            'base': base,
            'total_respondents': len(df),
            'freq_table': freq_table,
            'filter_info': filter_info
        }
        
        print(f"  ✓ Processed. Base (selected at least one): {base}/{len(df)}")
        return result

# Test function
if __name__ == "__main__":
    from spss_reader import SPSSReader
    
    # Test with a sample SPSS file
    reader = SPSSReader("data/test_survey.sav")
    
    if reader.read():
        # Define test filter sets
        test_filter_sets = {
            "males_only": {
                "Q1": {"eq": 1}
            },
            "young_only": {
                "Q2": {"in": [1, 2]}
            },
            "brand_a_users": {
                "Q3": {"any": ["Q3_1"]}
            }
        }
        
        # Test variables config
        test_vars = [
            {
                'name': 'Q1',
                'type': 'single',
                'label': 'Gender'
            },
            {
                'name': 'Q2',
                'type': 'single',
                'label': 'Age Group',
                'filter_set': 'males_only'  # Filter applied
            },
            {
                'name': 'Q3',
                'type': 'multi',
                'label': 'Brand Preference',
                'sub_variables': ['Q3_1', 'Q3_2', 'Q3_3'],
                'filter_set': 'young_only'  # Filter applied
            }
        ]
        
        # Initialize processor with filters
        processor = FrequencyProcessor(
            reader, 
            filter_sets=test_filter_sets,
            global_filter=None  # No global filter for this test
        )
        
        results = processor.process_all_variables(test_vars)
        
        print("\n" + "="*50)
        print("RESULTS SUMMARY")
        print("="*50)
        
        for result in results:
            print(f"\nVariable: {result['var_name']}")
            print(f"Type: {result['type']}")
            
            if result['filter_info']:
                filter_info = result['filter_info']
                print(f"Filter: {filter_info['name']}")
                print(f"  Stats: {filter_info['stats']['original_count']} → {filter_info['stats']['filtered_count']}")
            else:
                print("Filter: None")
            
            if result['type'] == 'single':
                print(f"Valid: {result['valid_responses']}/{result['total_responses']}")
            else:
                print(f"Base: {result['base']}/{result['total_respondents']}")
        
        # Show warnings
        warnings = processor.get_warnings()
        if warnings:
            print("\n" + "="*50)
            print("WARNINGS")
            print("="*50)
            for warning in warnings:
                print(f"⚠ {warning}")