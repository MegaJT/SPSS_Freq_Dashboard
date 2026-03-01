import pandas as pd
import numpy as np


class WeightCalculator:
    """Handles weighted frequency calculations and weight validation"""
    
    def __init__(self, data, weight_variable):
        """
        Initialize weight calculator
        
        Args:
            data: pandas DataFrame with SPSS data
            weight_variable: Name of weight variable column
        """
        self.data = data
        self.weight_variable = weight_variable
        self.weights = None
        self.valid_mask = None
        self.validation_info = {}
        self.warnings = []
        
        # Validate and prepare weights
        self._validate_and_prepare_weights()
    
    def _validate_and_prepare_weights(self):
        """Validate weight variable and prepare for calculations"""
        
        # Check if weight variable exists
        if self.weight_variable not in self.data.columns:
            raise ValueError(f"Weight variable '{self.weight_variable}' not found in SPSS file")
        
        # Get weights
        self.weights = self.data[self.weight_variable].copy()
        
        # Validate weights
        total_respondents = len(self.weights)
        
        # Count missing weights
        missing_count = self.weights.isna().sum()
        if missing_count > 0:
            self.warnings.append(
                f"{missing_count} respondent(s) have missing weights and will be excluded"
            )
        
        # Count invalid weights (≤ 0)
        invalid_count = ((self.weights <= 0) & self.weights.notna()).sum()
        if invalid_count > 0:
            self.warnings.append(
                f"{invalid_count} respondent(s) have invalid weights (≤0) and will be excluded"
            )
        
        # Create valid weight mask
        self.valid_mask = (
            self.weights.notna() & 
            (self.weights > 0) & 
            (self.weights < float('inf'))
        )
        
        valid_weights = self.weights[self.valid_mask]
        valid_count = len(valid_weights)
        excluded_count = total_respondents - valid_count
        
        # Check for extreme weights
        if valid_count > 0:
            min_weight = valid_weights.min()
            max_weight = valid_weights.max()
            mean_weight = valid_weights.mean()
            
            ratio = max_weight / min_weight if min_weight > 0 else float('inf')
            
            if ratio > 10:
                self.warnings.append(
                    f"Extreme weight variation detected: "
                    f"min={min_weight:.2f}, max={max_weight:.2f}, ratio={ratio:.1f}"
                )
            
            # Check average weight
            if abs(mean_weight - 1.0) > 0.1:
                self.warnings.append(
                    f"Average weight is {mean_weight:.2f} (expected ~1.0)"
                )
            
            # Calculate ESS
            sum_weights = valid_weights.sum()
            sum_weights_squared = (valid_weights ** 2).sum()
            ess = (sum_weights ** 2) / sum_weights_squared if sum_weights_squared > 0 else 0
            deff = valid_count / ess if ess > 0 else 1.0
            
            # Store validation info
            self.validation_info = {
                'total_respondents': total_respondents,
                'valid_count': valid_count,
                'excluded_count': excluded_count,
                'missing_count': missing_count,
                'invalid_count': invalid_count,
                'sum_weights': sum_weights,
                'min_weight': min_weight,
                'max_weight': max_weight,
                'mean_weight': mean_weight,
                'ess': ess,
                'deff': deff
            }
        else:
            raise ValueError(
                f"No valid weights found in '{self.weight_variable}'. "
                f"All {total_respondents} respondents have missing or invalid weights."
            )
    
    def get_valid_data_and_weights(self):
        """
        Get data and weights with invalid weights filtered out
        
        Returns:
            tuple: (filtered_data, filtered_weights)
        """
        filtered_data = self.data[self.valid_mask].copy()
        filtered_weights = self.weights[self.valid_mask].copy()
        
        return filtered_data, filtered_weights
    
    def calculate_weighted_frequencies_single(self, series, value_labels=None):
        """
        Calculate weighted frequencies for a single-punch variable
        
        Args:
            series: pandas Series with variable data (already filtered by valid weights)
            value_labels: Dict mapping values to labels (optional)
        
        Returns:
            dict: Weighted frequency results
        """
        # Get valid weights for this series
        valid_weights = self.weights[self.valid_mask]
        
        # Align series with valid weights (in case series is already filtered)
        if len(series) != len(valid_weights):
            # Series is already filtered, get corresponding weights
            valid_weights = valid_weights[series.index]
        
        # Calculate weighted and unweighted totals
        total_unweighted = len(series)
        total_weighted = valid_weights.sum()
        
        # Build frequency table in value_labels order (questionnaire order).
        # If value_labels provided, iterate its keys; otherwise fall back to
        # sorted unique values so order is at least deterministic.
        if value_labels:
            ordered_values = [v for v in value_labels.keys() if v in series.values]
            # Append any values present in data but not in value_labels (edge case)
            labeled_set = set(value_labels.keys())
            extras = [v for v in series.dropna().unique() if v not in labeled_set]
            ordered_values = ordered_values + sorted(extras)
        else:
            ordered_values = sorted(series.dropna().unique())

        freq_table = []
        valid_unweighted = 0
        valid_weighted = 0.0

        for value in ordered_values:
            # Unweighted count
            mask = (series == value)
            unweighted_count = mask.sum()
            
            # Weighted count
            weighted_count = valid_weights[mask].sum()
            
            # Percentage (weighted)
            percentage = (weighted_count / total_weighted * 100) if total_weighted > 0 else 0
            
            # Get label
            if value_labels and value in value_labels:
                label = value_labels[value]
            else:
                label = str(value)
            
            freq_table.append({
                'value': value,
                'label': label,
                'unweighted_count': int(unweighted_count),
                'weighted_count': float(weighted_count),
                'percentage': float(percentage),
                'is_missing': False
            })
            
            valid_unweighted += unweighted_count
            valid_weighted += weighted_count
        
        # Add missing values if any
        missing_mask = series.isna()
        missing_unweighted = missing_mask.sum()
        
        if missing_unweighted > 0:
            missing_weighted = valid_weights[missing_mask].sum()
            missing_percentage = (missing_weighted / total_weighted * 100) if total_weighted > 0 else 0
            
            freq_table.append({
                'value': None,
                'label': 'Missing',
                'unweighted_count': int(missing_unweighted),
                'weighted_count': float(missing_weighted),
                'percentage': float(missing_percentage),
                'is_missing': True
            })
        
        # Missing row already appended last — order preserved from value_labels

        
        return {
            'total_unweighted': int(total_unweighted),
            'total_weighted': float(total_weighted),
            'valid_unweighted': int(valid_unweighted),
            'valid_weighted': float(valid_weighted),
            'freq_table': freq_table
        }
    
    def calculate_weighted_frequencies_multi(self, sub_data_dict):
        """
        Calculate weighted frequencies for multi-punch variables
        
        Args:
            sub_data_dict: Dict mapping sub_var_name to pandas Series
        
        Returns:
            dict: Weighted frequency results
        """
        # Get valid weights
        valid_weights = self.weights[self.valid_mask]
        
        # Combine sub-variables into DataFrame
        sub_data = pd.DataFrame(sub_data_dict)
        
        # Align with valid weights
        if len(sub_data) != len(valid_weights):
            valid_weights = valid_weights[sub_data.index]
        
        # Calculate totals
        total_unweighted = len(sub_data)
        total_weighted = valid_weights.sum()
        
        # Calculate base (respondents who selected at least one)
        has_any_response = (sub_data == 1).any(axis=1)
        base_unweighted = has_any_response.sum()
        base_weighted = valid_weights[has_any_response].sum()
        
        # Build frequency table for each sub-variable
        freq_table = []
        
        for sub_var, series in sub_data.items():
            # Unweighted count
            unweighted_count = (series == 1).sum()
            
            # Weighted count
            weighted_count = valid_weights[series == 1].sum()
            
            # Percentage based on base_weighted (respondents who selected at least one)
            # This matches the unweighted calculation and ensures dashboard/export consistency
            percentage = (weighted_count / base_weighted * 100) if base_weighted > 0 else 0
            
            freq_table.append({
                'sub_var': sub_var,
                'unweighted_count': int(unweighted_count),
                'weighted_count': float(weighted_count),
                'percentage': float(percentage)
            })
        
        # Order preserved from sub_data_dict (questionnaire order)

        
        return {
            'total_unweighted': int(total_unweighted),
            'total_weighted': float(total_weighted),
            'base_unweighted': int(base_unweighted),
            'base_weighted': float(base_weighted),
            'freq_table': freq_table
        }
    
    def get_validation_info(self):
        """Get weight validation information"""
        return self.validation_info
    
    def get_warnings(self):
        """Get weight validation warnings"""
        return self.warnings


# Test function
if __name__ == "__main__":
    # Create test data with weights
    np.random.seed(42)
    
    test_data = pd.DataFrame({
        'Q1': [1, 2, 1, 2, 1, 2, 1, 2, 1, 2] * 10,
        'Q2': [1, 2, 3, 1, 2, 3, 1, 2, None, 1] * 10,
        'Q3_1': [1, 0, 1, 0, 1, 0, 1, 0, 1, 0] * 10,
        'Q3_2': [0, 1, 1, 0, 0, 1, 1, 0, 1, 0] * 10,
        'Q3_3': [1, 1, 0, 1, 0, 0, 1, 1, 0, 0] * 10,
        'WEIGHT': np.random.uniform(0.5, 2.0, 100)
    })
    
    # Add some missing and invalid weights
    test_data.loc[5, 'WEIGHT'] = None  # Missing
    test_data.loc[10, 'WEIGHT'] = 0    # Invalid (zero)
    test_data.loc[15, 'WEIGHT'] = -0.5  # Invalid (negative)
    
    print("="*70)
    print("TEST: Weight Calculator")
    print("="*70)
    
    # Initialize calculator
    try:
        calc = WeightCalculator(test_data, 'WEIGHT')
        
        # Show validation info
        print("\nValidation Info:")
        info = calc.get_validation_info()
        for key, value in info.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        
        # Show warnings
        print("\nWarnings:")
        for warning in calc.get_warnings():
            print(f"  ⚠ {warning}")
        
        # Get valid data
        valid_data, valid_weights = calc.get_valid_data_and_weights()
        print(f"\nValid data: {len(valid_data)} rows")
        
        # Test single-punch calculation
        print("\n" + "="*70)
        print("TEST: Single-Punch Weighted Frequencies")
        print("="*70)
        
        value_labels = {1: 'Male', 2: 'Female'}
        result = calc.calculate_weighted_frequencies_single(
            valid_data['Q1'],
            value_labels
        )
        
        print(f"\nTotal: {result['total_unweighted']} (unweighted) | "
              f"{result['total_weighted']:.1f} (weighted)")
        print(f"Valid: {result['valid_unweighted']} (unweighted) | "
              f"{result['valid_weighted']:.1f} (weighted)")
        
        print(f"\n{'Value':<15} {'Unweighted':>12} {'Weighted':>12} {'Percentage':>12}")
        print("-"*55)
        for row in result['freq_table']:
            print(f"{row['label']:<15} {row['unweighted_count']:>12} "
                  f"{row['weighted_count']:>12.1f} {row['percentage']:>11.1f}%")
        
        # Test multi-punch calculation
        print("\n" + "="*70)
        print("TEST: Multi-Punch Weighted Frequencies")
        print("="*70)
        
        sub_data_dict = {
            'Q3_1': valid_data['Q3_1'],
            'Q3_2': valid_data['Q3_2'],
            'Q3_3': valid_data['Q3_3']
        }
        
        result = calc.calculate_weighted_frequencies_multi(sub_data_dict)
        
        print(f"\nTotal: {result['total_unweighted']} (unweighted) | "
              f"{result['total_weighted']:.1f} (weighted)")
        print(f"Base: {result['base_unweighted']} (unweighted) | "
              f"{result['base_weighted']:.1f} (weighted)")
        
        print(f"\n{'Option':<15} {'Unweighted':>12} {'Weighted':>12} {'Percentage':>12}")
        print("-"*55)
        for row in result['freq_table']:
            print(f"{row['sub_var']:<15} {row['unweighted_count']:>12} "
                  f"{row['weighted_count']:>12.1f} {row['percentage']:>11.1f}%")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()