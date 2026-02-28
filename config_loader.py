import json
import os
from pathlib import Path


class ConfigLoader:
    """Loads and validates the meta.json configuration file"""
    
    def __init__(self, config_path='meta.json', spss_file_path=None):
        """
        Initialize the config loader
        
        Args:
            config_path: Path to meta.json file (default: 'meta.json' in current directory)
            spss_file_path: Optional path to SPSS file (for UI-selected files)
        """
        self.config_path = config_path
        self.spss_file_path = spss_file_path
        self.config = None
    
    def load(self):
        """
        Load the configuration file
        
        Returns:
            dict: Configuration dictionary
            
        Raises:
            FileNotFoundError: If meta.json doesn't exist
            json.JSONDecodeError: If meta.json is not valid JSON
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            print(f"✓ Configuration loaded from {self.config_path}")
            return self.config
            
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Invalid JSON in {self.config_path}: {str(e)}",
                e.doc, e.pos
            )
    
    def validate(self):
        """
        Validate the configuration structure
        
        Returns:
            tuple: (is_valid, error_messages)
        """
        if self.config is None:
            return False, ["Configuration not loaded. Call load() first."]
        
        errors = []
        
        # Use SPSS path from __init__ if provided (from UI selection)
        # Otherwise fall back to config's spss_file_path
        spss_path_to_use = self.spss_file_path or self.config.get('spss_file_path')
        
        # Check required fields (SPSS file selected via UI; output file optional)
        required_fields = ['variables']
        for field in required_fields:
            if field not in self.config:
                errors.append(f"Missing required field: '{field}'")
        
        # Validate SPSS file path if provided. SPSS file may be selected via UI later.
        if 'spss_file_path' in self.config and self.config['spss_file_path']:
            spss_path = self.config['spss_file_path']
            if not os.path.exists(spss_path):
                print(f"⚠ Warning: SPSS file not found (will be selected via UI): {spss_path}")
        
        # Validate variables
        if 'variables' in self.config:
            if not isinstance(self.config['variables'], list):
                errors.append("'variables' must be a list")
            else:
                for i, var in enumerate(self.config['variables']):
                    var_errors = self._validate_variable(var, i)
                    errors.extend(var_errors)
        
        # Validate filter_sets (if present)
        if 'filter_sets' in self.config:
            filter_errors = self._validate_filter_sets()
            errors.extend(filter_errors)
        
        # Note: global_filter, output_format, and visualization are now app-level settings
        # selected via UI - they are no longer required in the JSON configuration
        
        # Validate filter_set references in variables
        if 'variables' in self.config and 'filter_sets' in self.config:
            for i, var in enumerate(self.config['variables']):
                if 'filter_set' in var:
                    filter_set_name = var['filter_set']
                    if filter_set_name not in self.config['filter_sets']:
                        errors.append(
                            f"Variable {i+1} ({var.get('name', 'unnamed')}): "
                            f"filter_set '{filter_set_name}' not found in filter_sets"
                        )

        # Validate weighting (if present)
        if 'weighting' in self.config:
            weighting_errors = self._validate_weighting()
            errors.extend(weighting_errors)
        
        # Derive output_file name from SPSS filename when SPSS path is provided
        if spss_path_to_use:
            spss_dir = os.path.dirname(spss_path_to_use)
            base = os.path.splitext(os.path.basename(spss_path_to_use))[0]
            # Use capitalized pattern as requested: <SPSSNAME>_Frequencies.txt
            self.config['output_file'] = os.path.join(spss_dir, f"{base}_Frequencies.txt")
            print(f"✓ Set output_file to {self.config['output_file']} (derived from SPSS file name)")
        else:
            # No SPSS path available — keep existing output_file or set a sensible default
            if 'output_file' not in self.config or not self.config['output_file']:
                self.config['output_file'] = os.path.join('output', 'frequencies.txt')
                print(f"✓ Set output_file to {self.config['output_file']} (default)")

        # Ensure output directory exists
        output_dir = os.path.dirname(self.config['output_file'])
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                print(f"✓ Created output directory: {output_dir}")
            except Exception as e:
                errors.append(f"Could not create output directory: {str(e)}")
        
        if errors:
            return False, errors
        else:
            print("✓ Configuration validated successfully")
            return True, []
    
    def _validate_variable(self, var, index):
        """
        Validate a single variable configuration
        
        Args:
            var: Variable dict
            index: Variable index (for error messages)
        
        Returns:
            list: List of error messages
        """
        errors = []
        
        # Check variable has required fields
        if 'name' not in var:
            errors.append(f"Variable {index+1}: Missing 'name' field")
        if 'type' not in var:
            errors.append(f"Variable {index+1}: Missing 'type' field")
        elif var['type'] not in ['single', 'multi']:
            errors.append(f"Variable {index+1}: 'type' must be 'single' or 'multi'")
        
        # Multi-punch questions need sub_variables
        if var.get('type') == 'multi' and 'sub_variables' not in var:
            errors.append(
                f"Variable {index+1} ({var.get('name', 'unnamed')}): "
                "'multi' type requires 'sub_variables' field"
            )
        
        return errors
    
    def _validate_filter_sets(self):
        """
        Validate filter_sets configuration
        
        Returns:
            list: List of error messages
        """
        errors = []
        filter_sets = self.config.get('filter_sets', {})
        
        if not isinstance(filter_sets, dict):
            errors.append("'filter_sets' must be a dictionary")
            return errors
        
        # Validate each filter set
        for filter_name, filter_conditions in filter_sets.items():
            if not isinstance(filter_conditions, dict):
                errors.append(f"Filter set '{filter_name}': conditions must be a dictionary")
                continue
            
            # Validate each condition in the filter set
            for var_name, condition in filter_conditions.items():
                condition_errors = self._validate_filter_condition(
                    filter_name, var_name, condition
                )
                errors.extend(condition_errors)
        
        return errors
    
    def _validate_filter_condition(self, filter_name, var_name, condition):
        """
        Validate a single filter condition
        
        Args:
            filter_name: Name of the filter set
            var_name: Variable name
            condition: Condition dict (e.g., {"eq": 1})
        
        Returns:
            list: List of error messages
        """
        errors = []
        
        # Check condition is a dict
        if not isinstance(condition, dict):
            errors.append(
                f"Filter '{filter_name}', variable '{var_name}': "
                f"condition must be a dictionary, got {type(condition)}"
            )
            return errors
        
        # Check condition has exactly one operator
        if len(condition) != 1:
            errors.append(
                f"Filter '{filter_name}', variable '{var_name}': "
                f"condition must have exactly one operator, got {len(condition)}"
            )
            return errors
        
        operator = list(condition.keys())[0]
        value = condition[operator]
        
        # Validate operator
        valid_operators = ['eq', 'in', 'between', 'not_missing', 'any', 'all', 'min_selected']
        if operator not in valid_operators:
            errors.append(
                f"Filter '{filter_name}', variable '{var_name}': "
                f"unknown operator '{operator}'. Valid operators: {valid_operators}"
            )
            return errors
        
        # Validate value based on operator
        if operator == 'in':
            if not isinstance(value, list):
                errors.append(
                    f"Filter '{filter_name}', variable '{var_name}': "
                    f"operator 'in' requires a list value"
                )
        
        elif operator == 'between':
            if not isinstance(value, list) or len(value) != 2:
                errors.append(
                    f"Filter '{filter_name}', variable '{var_name}': "
                    f"operator 'between' requires a list of 2 values"
                )
        
        elif operator == 'not_missing':
            if value is not True:
                errors.append(
                    f"Filter '{filter_name}', variable '{var_name}': "
                    f"operator 'not_missing' requires value=true"
                )
        
        elif operator in ['any', 'all']:
            if not isinstance(value, list):
                errors.append(
                    f"Filter '{filter_name}', variable '{var_name}': "
                    f"operator '{operator}' requires a list of sub-variables"
                )
        
        elif operator == 'min_selected':
            if not isinstance(value, int) or value < 1:
                errors.append(
                    f"Filter '{filter_name}', variable '{var_name}': "
                    f"operator 'min_selected' requires a positive integer"
                )
            
            # Check if variable is defined as multi-punch
            # We'll do a deeper check during processing, but warn if suspicious
            if 'variables' in self.config:
                var_found = False
                for v in self.config['variables']:
                    if v.get('name') == var_name and v.get('type') == 'multi':
                        var_found = True
                        break
                
                if not var_found:
                    errors.append(
                        f"Filter '{filter_name}', variable '{var_name}': "
                        f"operator 'min_selected' used but variable not defined as type='multi' "
                        f"in variables list. This will cause a runtime error."
                    )
        
        return errors
    
    def _validate_weighting(self):
        """
        Validate weighting configuration
        
        Returns:
            list: List of error messages
        """
        errors = []
        
        if 'weighting' not in self.config:
            # Weighting is optional, no errors if not present
            return errors
        
        weighting = self.config['weighting']
        
        # Check structure
        if not isinstance(weighting, dict):
            errors.append("'weighting' must be a dictionary")
            return errors
        
        # Check 'enabled' field
        if 'enabled' not in weighting:
            errors.append("Weighting configuration missing 'enabled' field")
        elif not isinstance(weighting['enabled'], bool):
            errors.append("Weighting 'enabled' must be true or false")
        
        # If enabled, check for weight_variable
        if weighting.get('enabled', False):
            if 'weight_variable' not in weighting:
                errors.append("Weighting enabled but 'weight_variable' not specified")
            elif not isinstance(weighting['weight_variable'], str):
                errors.append("Weighting 'weight_variable' must be a string")
            elif not weighting['weight_variable'].strip():
                errors.append("Weighting 'weight_variable' cannot be empty")
        
        return errors
    
    def _validate_visualization(self):
        """
        Validate visualization configuration
        
        Returns:
            list: List of error messages
        """
        errors = []
        
        if 'visualization' not in self.config:
            # Visualization is optional
            return errors
        
        viz = self.config['visualization']
        
        # Check structure
        if not isinstance(viz, dict):
            errors.append("'visualization' must be a dictionary")
            return errors
        
        # Check 'enabled' field
        if 'enabled' not in viz:
            errors.append("Visualization configuration missing 'enabled' field")
        elif not isinstance(viz['enabled'], bool):
            errors.append("Visualization 'enabled' must be true or false")
        
        # If enabled, check for required fields
        if viz.get('enabled', False):
            if 'output_file' not in viz:
                errors.append("Visualization enabled but 'output_file' not specified")
            
            # Validate theme (optional, has default)
            if 'theme' in viz:
                valid_themes = ['corporate_blue', 'modern', 'professional', 'vibrant']
                if viz['theme'] not in valid_themes:
                    errors.append(f"Invalid theme '{viz['theme']}'. Valid: {valid_themes}")
            
            # Validate chart_types (optional, has defaults)
            if 'chart_types' in viz:
                if not isinstance(viz['chart_types'], dict):
                    errors.append("'chart_types' must be a dictionary")
                else:
                    if 'single_punch' in viz['chart_types']:
                        valid_single = ['bar', 'horizontal_bar', 'pie']
                        if viz['chart_types']['single_punch'] not in valid_single:
                            errors.append(f"Invalid single_punch chart type. Valid: {valid_single}")
                    
                    if 'multi_punch' in viz['chart_types']:
                        valid_multi = ['bar', 'horizontal_bar']  # Both allowed (horizontal_bar converts to bar)
                        if viz['chart_types']['multi_punch'] not in valid_multi:
                            errors.append(f"Invalid multi_punch chart type. Valid: {valid_multi}")
        
        return errors
    
    def get_config(self):
        """Get the loaded configuration"""
        return self.config


# Test function
if __name__ == "__main__":
    # Test the config loader with filters
    
    # Create a test config file with filters
    test_config = {
        "spss_file_path": "data/test_survey.sav",
        "output_file": "output/test_frequencies.txt",
        "output_format": "txt",
        "global_filter": "complete_surveys",
        "filter_sets": {
            "complete_surveys": {
                "Q1": {"not_missing": True},
                "Q2": {"not_missing": True}
            },
            "males_only": {
                "Q1": {"eq": 1}
            },
            "young_males": {
                "Q1": {"eq": 1},
                "Q2": {"in": [1, 2]}
            },
            "brand_a_users": {
                "Q3": {"any": ["Q3_1"]}
            },
            "multi_brand_users": {
                "Q3": {"min_selected": 2}
            }
        },
        "variables": [
            {
                "name": "Q1",
                "type": "single",
                "label": "Gender"
            },
            {
                "name": "Q3",
                "type": "multi",
                "label": "Brand Usage",
                "sub_variables": ["Q3_1", "Q3_2", "Q3_3"],
                "filter_set": "males_only"
            }
        ]
    }
    
    # Save test config
    with open('test_meta.json', 'w') as f:
        json.dump(test_config, f, indent=2)
    
    # Test loader
    loader = ConfigLoader('test_meta.json')
    
    try:
        config = loader.load()
        is_valid, errors = loader.validate()
        
        print("\n" + "="*60)
        print("VALIDATION RESULTS")
        print("="*60)
        
        if is_valid:
            print("✓ Configuration is valid!")
            
            if 'filter_sets' in config:
                print(f"\nFilter sets defined: {len(config['filter_sets'])}")
                for name in config['filter_sets'].keys():
                    print(f"  - {name}")
            
            if 'global_filter' in config:
                print(f"\nGlobal filter: {config['global_filter']}")
            
            print(f"\nVariables: {len(config['variables'])}")
            for var in config['variables']:
                filter_info = f" (filter: {var['filter_set']})" if 'filter_set' in var else ""
                print(f"  - {var['name']}: {var['type']}{filter_info}")
        
        else:
            print("✗ Configuration has errors:")
            for error in errors:
                print(f"  - {error}")
    
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
    
    finally:
        # Clean up test file
        import os
        if os.path.exists('test_meta.json'):
            os.remove('test_meta.json')