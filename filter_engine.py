import pandas as pd
import numpy as np


class FilterEngine:
    """Applies filters to SPSS data based on filter conditions"""
    
    def __init__(self, data, variables_config):
        """
        Initialize the filter engine
        
        Args:
            data: pandas DataFrame with SPSS data
            variables_config: List of variable configurations from meta.json
                              (needed to resolve multi-punch variables)
        """
        self.data = data
        self.variables_config = variables_config
        self.multi_punch_map = self._build_multi_punch_map()
    
    def _build_multi_punch_map(self):
        """
        Build a mapping of multi-punch parent names to their sub-variables
        
        Returns:
            dict: {parent_name: [sub_var1, sub_var2, ...]}
        """
        mp_map = {}
        for var in self.variables_config:
            if var.get('type') == 'multi' and 'sub_variables' in var:
                parent_name = var['name']
                sub_vars = var['sub_variables']
                mp_map[parent_name] = sub_vars
        
        return mp_map
    
    def apply_filter_set(self, filter_set_name, filter_conditions):
        """
        Apply a filter set to the data
        
        Args:
            filter_set_name: Name of the filter set (for logging/output)
            filter_conditions: Dict of filter conditions
                              e.g., {"Q1": {"eq": 1}, "Q2": {"in": [1,2]}}
        
        Returns:
            tuple: (filtered_data, filter_summary, stats)
                - filtered_data: pandas DataFrame
                - filter_summary: dict with readable filter description
                - stats: dict with before/after counts
        """
        if not filter_conditions:
            # No filter conditions - return original data
            return self.data, {}, {
                'original_count': len(self.data),
                'filtered_count': len(self.data),
                'exclusion_rate': 0.0
            }
        
        # Start with all rows as True
        combined_mask = pd.Series([True] * len(self.data), index=self.data.index)
        filter_summary = {}
        
        # Apply each condition (AND logic between conditions)
        for var_name, condition in filter_conditions.items():
            # Apply the condition and get the mask
            mask, description = self._apply_condition(var_name, condition)
            
            # Combine with AND logic
            combined_mask = combined_mask & mask
            
            # Store description for summary
            filter_summary[var_name] = description
        
        # Apply the combined mask
        filtered_data = self.data[combined_mask].copy()
        
        # Calculate statistics
        original_count = len(self.data)
        filtered_count = len(filtered_data)
        exclusion_rate = ((original_count - filtered_count) / original_count * 100) if original_count > 0 else 0
        
        stats = {
            'original_count': original_count,
            'filtered_count': filtered_count,
            'excluded_count': original_count - filtered_count,
            'exclusion_rate': exclusion_rate
        }
        
        return filtered_data, filter_summary, stats
    
    def _apply_condition(self, var_name, condition):
        """
        Apply a single filter condition
        
        Args:
            var_name: Variable name
            condition: Dict with operator and value
                      e.g., {"eq": 1} or {"any": ["Q3_1", "Q3_2"]}
        
        Returns:
            tuple: (mask, description)
                - mask: pandas Series of booleans
                - description: readable string describing the filter
        """
        # Determine operator
        if not isinstance(condition, dict):
            raise ValueError(f"Filter condition for '{var_name}' must be a dict, got {type(condition)}")
        
        if len(condition) != 1:
            raise ValueError(f"Filter condition for '{var_name}' must have exactly one operator")
        
        operator = list(condition.keys())[0]
        value = condition[operator]
        
        # Check if this is a multi-punch operator
        multi_punch_operators = ['any', 'all', 'min_selected']
        
        if operator in multi_punch_operators:
            return self._apply_multi_punch_operator(var_name, operator, value)
        else:
            return self._apply_standard_operator(var_name, operator, value)
    
    def _apply_standard_operator(self, var_name, operator, value):
        """
        Apply standard operators (eq, in, between, not_missing)
        
        Args:
            var_name: Variable name
            operator: Operator string
            value: Value to compare against
        
        Returns:
            tuple: (mask, description)
        """
        # Check if variable exists
        if var_name not in self.data.columns:
            raise ValueError(f"Variable '{var_name}' not found in SPSS file")
        
        series = self.data[var_name]
        
        # Apply operator
        if operator == 'eq':
            # Equal to
            mask = (series == value) & series.notna()
            description = f"= {value}"
        
        elif operator == 'in':
            # In list (OR logic)
            if not isinstance(value, list):
                raise ValueError(f"'in' operator requires a list, got {type(value)}")
            mask = series.isin(value) & series.notna()
            description = f"IN {value}"
        
        elif operator == 'between':
            # Between range (inclusive)
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError(f"'between' operator requires a list of 2 values, got {value}")
            min_val, max_val = value
            mask = (series >= min_val) & (series <= max_val) & series.notna()
            description = f"BETWEEN {min_val} AND {max_val}"
        
        elif operator == 'not_missing':
            # Not missing
            if value is not True:
                raise ValueError(f"'not_missing' operator requires value=true, got {value}")
            mask = series.notna()
            description = "Not Missing"
        
        else:
            raise ValueError(f"Unknown operator '{operator}' for variable '{var_name}'")
        
        return mask, description
    
    def _apply_multi_punch_operator(self, var_name, operator, value):
        """
        Apply multi-punch operators (any, all, min_selected)
        
        Args:
            var_name: Parent variable name (e.g., "Q3")
            operator: Multi-punch operator
            value: Depends on operator:
                   - 'any'/'all': list of sub-variable names
                   - 'min_selected': integer
        
        Returns:
            tuple: (mask, description)
        """
        # Resolve sub-variables
        if operator in ['any', 'all']:
            # User explicitly provided sub-variables
            if not isinstance(value, list):
                raise ValueError(f"'{operator}' operator requires a list of sub-variables")
            sub_vars = value
        
        elif operator == 'min_selected':
            # Infer sub-variables from variable definition
            if var_name not in self.multi_punch_map:
                raise ValueError(
                    f"Cannot use 'min_selected' on '{var_name}': "
                    f"Variable not defined as type='multi' with sub_variables"
                )
            sub_vars = self.multi_punch_map[var_name]
            min_count = value
        
        else:
            raise ValueError(f"Unknown multi-punch operator '{operator}'")
        
        # Check all sub-variables exist
        for sub_var in sub_vars:
            if sub_var not in self.data.columns:
                raise ValueError(f"Sub-variable '{sub_var}' not found in SPSS file")
        
        # Get data for all sub-variables
        sub_data = self.data[sub_vars]
        
        # Apply operator
        if operator == 'any':
            # Selected ANY of these options (OR logic)
            # At least one sub-variable == 1
            mask = (sub_data == 1).any(axis=1)
            description = f"Selected ANY of {sub_vars}"
        
        elif operator == 'all':
            # Selected ALL of these options (AND logic)
            # All sub-variables == 1
            mask = (sub_data == 1).all(axis=1)
            description = f"Selected ALL of {sub_vars}"
        
        elif operator == 'min_selected':
            # Selected at least N options
            # Count how many sub-variables == 1
            count_selected = (sub_data == 1).sum(axis=1)
            mask = count_selected >= min_count
            description = f"Selected at least {min_count} option(s) from {sub_vars}"
        
        return mask, description
    
    def get_filter_info(self, filter_set_name, filter_summary, stats):
        """
        Get readable filter information for output
        
        Args:
            filter_set_name: Name of filter set
            filter_summary: Dict from apply_filter_set
            stats: Stats dict from apply_filter_set
        
        Returns:
            dict: Information for output writer
        """
        info = {
            'name': filter_set_name,
            'conditions': filter_summary,
            'original_count': stats['original_count'],
            'filtered_count': stats['filtered_count'],
            'excluded_count': stats['excluded_count'],
            'exclusion_rate': stats['exclusion_rate']
        }
        
        return info


# Test function
if __name__ == "__main__":
    # Create test data
    test_data = pd.DataFrame({
        'Q1': [1, 2, 1, 2, 1, 2, 1, 2, 1, 2],
        'Q2': [1, 2, 3, 1, 2, 3, 1, 2, None, 1],
        'Q3_1': [1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
        'Q3_2': [0, 1, 1, 0, 0, 1, 1, 0, 1, 0],
        'Q3_3': [1, 1, 0, 1, 0, 0, 1, 1, 0, 0],
    })
    
    test_vars_config = [
        {
            'name': 'Q3',
            'type': 'multi',
            'sub_variables': ['Q3_1', 'Q3_2', 'Q3_3']
        }
    ]
    
    # Initialize filter engine
    engine = FilterEngine(test_data, test_vars_config)
    
    print("="*60)
    print("TEST 1: Standard Filter (eq)")
    print("="*60)
    filter1 = {"Q1": {"eq": 1}}
    filtered1, summary1, stats1 = engine.apply_filter_set("males_only", filter1)
    print(f"Filter: {filter1}")
    print(f"Summary: {summary1}")
    print(f"Original: {stats1['original_count']}, Filtered: {stats1['filtered_count']}")
    print(f"Filtered data:\n{filtered1}")
    
    print("\n" + "="*60)
    print("TEST 2: Standard Filter (in)")
    print("="*60)
    filter2 = {"Q2": {"in": [1, 2]}}
    filtered2, summary2, stats2 = engine.apply_filter_set("young", filter2)
    print(f"Filter: {filter2}")
    print(f"Summary: {summary2}")
    print(f"Original: {stats2['original_count']}, Filtered: {stats2['filtered_count']}")
    
    print("\n" + "="*60)
    print("TEST 3: Multi-Punch Filter (any)")
    print("="*60)
    filter3 = {"Q3": {"any": ["Q3_1", "Q3_2"]}}
    filtered3, summary3, stats3 = engine.apply_filter_set("brand_ab", filter3)
    print(f"Filter: {filter3}")
    print(f"Summary: {summary3}")
    print(f"Original: {stats3['original_count']}, Filtered: {stats3['filtered_count']}")
    
    print("\n" + "="*60)
    print("TEST 4: Multi-Punch Filter (min_selected)")
    print("="*60)
    filter4 = {"Q3": {"min_selected": 2}}
    filtered4, summary4, stats4 = engine.apply_filter_set("multi_brand", filter4)
    print(f"Filter: {filter4}")
    print(f"Summary: {summary4}")
    print(f"Original: {stats4['original_count']}, Filtered: {stats4['filtered_count']}")
    
    print("\n" + "="*60)
    print("TEST 5: Combined Filter (AND logic)")
    print("="*60)
    filter5 = {
        "Q1": {"eq": 1},
        "Q3": {"any": ["Q3_1"]}
    }
    filtered5, summary5, stats5 = engine.apply_filter_set("male_brand_a", filter5)
    print(f"Filter: {filter5}")
    print(f"Summary: {summary5}")
    print(f"Original: {stats5['original_count']}, Filtered: {stats5['filtered_count']}")