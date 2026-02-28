"""
validator.py - SPSS & Meta Configuration Validator

Validates that meta.json configuration matches the actual SPSS file structure.
Supports two modes:
- tkinter_mode=True: Skip spss_file_path check (Tkinter provides actual path)
- tkinter_mode=False: Validate everything including meta.json paths
"""

import os
import json
from typing import Tuple, List, Dict, Any

from config_loader import ConfigLoader
from spss_reader import SPSSReader


class SPSSMetaValidator:
    """Validates SPSS file against meta.json configuration"""
    
    def __init__(self, spss_path: str, meta_path: str):
        """
        Initialize validator
        
        Args:
            spss_path: Path to SPSS .sav file (from Tkinter or meta.json)
            meta_path: Path to meta.json configuration
        """
        self.spss_path = spss_path
        self.meta_path = meta_path
        self.reader = None
        self.config = None
        self.spss_columns = set()
    
    def validate(self, tkinter_mode: bool = False) -> Tuple[bool, List[str], List[str]]:
        """
        Run all validations
        
        Args:
            tkinter_mode: If True, skip checking spss_file_path from meta.json
                         (because Tkinter provides the actual path)
        
        Returns:
            tuple: (is_valid, errors, warnings)
        """
        errors = []
        warnings = []
        
        # Step 1: Check files exist
        file_errors = self._validate_files_exist(tkinter_mode=tkinter_mode)
        errors.extend(file_errors)
        
        if file_errors:
            return False, errors, warnings
        
        # Step 2: Load SPSS file
        spss_errors = self._load_spss()
        errors.extend(spss_errors)
        
        if spss_errors:
            return False, errors, warnings
        
        # Step 3: Load meta.json (pass tkinter_mode so file-path checks can be adjusted)
        config_errors = self._load_config(tkinter_mode=tkinter_mode)
        errors.extend(config_errors)
        
        if config_errors:
            return False, errors, warnings
        
        # Step 4: Validate variables exist in SPSS
        var_errors, var_warnings = self._validate_variables()
        errors.extend(var_errors)
        warnings.extend(var_warnings)
        
        # Step 5: Validate filter variables exist
        filter_errors, filter_warnings = self._validate_filters()
        errors.extend(filter_errors)
        warnings.extend(filter_warnings)
        
        # Step 6: Validate weight variable exists
        weight_errors, weight_warnings = self._validate_weighting()
        errors.extend(weight_errors)
        warnings.extend(weight_warnings)
        
        # Step 7: Additional warnings (best practices)
        practice_warnings = self._validate_best_practices()
        warnings.extend(practice_warnings)
        
        is_valid = len(errors) == 0
        return is_valid, errors, warnings
    
    def _validate_files_exist(self, tkinter_mode: bool = False) -> List[str]:
        """Check if both files exist"""
        errors = []
        
        # ⚠️ SKIP spss_file_path check in tkinter_mode - Tkinter already validated
        if not tkinter_mode:
            if self.config and 'spss_file_path' in self.config:
                spss_path = self.config['spss_file_path']
                if not os.path.exists(spss_path):
                    errors.append(f"SPSS file not found (from meta.json): {spss_path}")
        
        # Always check the actual SPSS path provided
        if not os.path.exists(self.spss_path):
            errors.append(f"SPSS file not found: {self.spss_path}")
        
        if not os.path.exists(self.meta_path):
            errors.append(f"Meta configuration not found: {self.meta_path}")
        
        return errors
    
    def _load_spss(self) -> List[str]:
        """Load SPSS file and extract column names"""
        errors = []
        
        try:
            self.reader = SPSSReader(self.spss_path)
            if not self.reader.read():
                errors.append(f"Failed to read SPSS file: {self.spss_path}")
                return errors
            
            # Get column names
            data = self.reader.get_data()
            if data is None or len(data.columns) == 0:
                errors.append("SPSS file contains no data columns")
                return errors
            
            self.spss_columns = set(data.columns)
            
        except Exception as e:
            errors.append(f"Error reading SPSS file: {str(e)}")
        
        return errors
    
    def _load_config(self, tkinter_mode: bool = False) -> List[str]:
        """Load and validate meta.json configuration"""
        errors = []
        
        try:
            loader = ConfigLoader(self.meta_path, spss_file_path=self.spss_path)
            self.config = loader.load()
            
            # Use existing validation from ConfigLoader (but skip file path checks in tkinter_mode)
            is_valid, validation_errors = loader.validate()

            # If running in tkinter mode, the launcher provides the SPSS path so
            # we should not treat missing spss_file_path (or not found) as fatal errors.
            if tkinter_mode and validation_errors:
                filtered = []
                for e in validation_errors:
                    # Remove messages that check for SPSS file path existence
                    if 'spss_file_path' in e or 'SPSS file not found' in e:
                        continue
                    filtered.append(e)
                validation_errors = filtered

            errors.extend(validation_errors)
            
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in meta.json: {str(e)}")
        except Exception as e:
            errors.append(f"Error loading meta.json: {str(e)}")
        
        return errors
    
    def _validate_variables(self) -> Tuple[List[str], List[str]]:
        """Validate that all variables in meta.json exist in SPSS"""
        errors = []
        warnings = []
        
        variables = self.config.get('variables', [])
        
        if not variables:
            warnings.append("No variables defined in meta.json")
            return errors, warnings
        
        for i, var in enumerate(variables):
            var_name = var.get('name')
            var_type = var.get('type')
            var_label = var.get('label', var_name)
            
            if not var_name:
                errors.append(f"Variable #{i+1}: Missing 'name' field")
                continue
            
            if not var_type:
                errors.append(f"Variable '{var_name}': Missing 'type' field")
                continue
            
            if var_type == 'single':
                if var_name not in self.spss_columns:
                    errors.append(f"Single-punch variable '{var_name}' ({var_label}) not found in SPSS file")
                else:
                    # Check if column has data
                    if self._check_empty_column(var_name):
                        warnings.append(f"Variable '{var_name}' ({var_label}) exists but contains no data")
            
            elif var_type == 'multi':
                sub_vars = var.get('sub_variables', [])
                
                if not sub_vars:
                    errors.append(f"Multi-punch variable '{var_name}': Missing 'sub_variables'")
                    continue
                
                missing_sub_vars = [sv for sv in sub_vars if sv not in self.spss_columns]
                
                if missing_sub_vars:
                    errors.append(f"Multi-punch variable '{var_name}' ({var_label}): sub-variables not found: {missing_sub_vars}")
                else:
                    # Check if at least one sub-variable has data
                    has_data = any(not self._check_empty_column(sv) for sv in sub_vars)
                    if not has_data:
                        warnings.append(f"Multi-punch variable '{var_name}' ({var_label}): all sub-variables exist but contain no data")
            
            else:
                warnings.append(f"Variable '{var_name}': Unknown type '{var_type}'")
        
        return errors, warnings
    
    def _validate_filters(self) -> Tuple[List[str], List[str]]:
        """Validate that filter variables exist in SPSS"""
        errors = []
        warnings = []
        
        filter_sets = self.config.get('filter_sets', {})
        global_filter = self.config.get('global_filter')
        
        # Check global filter exists
        if global_filter and global_filter not in filter_sets:
            errors.append(f"Global filter '{global_filter}' is not defined in filter_sets")
        
        # Check each filter's variables
        for filter_name, conditions in filter_sets.items():
            if not conditions:
                warnings.append(f"Filter '{filter_name}': No conditions defined")
                continue
            
            for var_name in conditions.keys():
                if var_name not in self.spss_columns:
                    errors.append(f"Filter '{filter_name}': variable '{var_name}' not found in SPSS file")
        
        return errors, warnings
    
    def _validate_weighting(self) -> Tuple[List[str], List[str]]:
        """Validate weight variable exists if weighting is enabled"""
        errors = []
        warnings = []
        
        weighting = self.config.get('weighting', {})
        enabled = weighting.get('enabled', False)
        
        if not enabled:
            return errors, warnings
        
        weight_var = weighting.get('weight_variable')
        
        if not weight_var:
            errors.append("Weighting is enabled but 'weight_variable' is not specified")
            return errors, warnings
        
        if weight_var not in self.spss_columns:
            errors.append(f"Weight variable '{weight_var}' not found in SPSS file")
        else:
            # Check for common weight issues
            try:
                weight_data = self.reader.get_data()[weight_var]
                
                if weight_data.isnull().all():
                    errors.append(f"Weight variable '{weight_var}' contains only missing values")
                elif (weight_data <= 0).all():
                    errors.append(f"Weight variable '{weight_var}' contains only zero or negative values")
                elif weight_data.min() <= 0:
                    warnings.append(f"Weight variable '{weight_var}' contains zero or negative values (may cause calculation issues)")
            except Exception as e:
                warnings.append(f"Could not validate weight variable: {str(e)}")
        
        return errors, warnings
    
    def _validate_best_practices(self) -> List[str]:
        """Check for best practice recommendations"""
        warnings = []
        
        variables = self.config.get('variables', [])
        
        if not variables:
            return warnings
        
        # Check for variables without labels
        unlabeled = [v.get('name') for v in variables if not v.get('label')]
        if unlabeled:
            warnings.append(f"{len(unlabeled)} variable(s) missing 'label' field: {unlabeled[:5]}{'...' if len(unlabeled) > 5 else ''}")
        
        # Check for duplicate variable names
        var_names = [v.get('name') for v in variables]
        duplicates = [name for name in var_names if var_names.count(name) > 1]
        if duplicates:
            warnings.append(f"Duplicate variable names found: {set(duplicates)}")
        
        # Check output file directory exists (only in non-tkinter mode)
        output_file = self.config.get('output_file', '')
        if output_file:
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                warnings.append(f"Output directory does not exist: {output_dir} (will be created)")
        
        return warnings
    
    def _check_empty_column(self, column_name: str) -> bool:
        """Check if a column is empty or contains only NaN"""
        try:
            data = self.reader.get_data()[column_name]
            return data.isnull().all() or (data == '').all()
        except:
            return True
    
    def get_spss_info(self) -> Dict[str, Any]:
        """Get SPSS file information"""
        if not self.reader:
            return {}
        
        data = self.reader.get_data()
        return {
            'total_rows': len(data),
            'total_columns': len(data.columns),
            'columns': list(data.columns),
            'memory_usage_mb': round(data.memory_usage(deep=True).sum() / 1024 / 1024, 2)
        }
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get meta.json configuration summary"""
        if not self.config:
            return {}
        
        return {
            'total_variables': len(self.config.get('variables', [])),
            'single_punch_count': sum(1 for v in self.config.get('variables', []) if v.get('type') == 'single'),
            'multi_punch_count': sum(1 for v in self.config.get('variables', []) if v.get('type') == 'multi'),
            'filter_sets_count': len(self.config.get('filter_sets', {})),
            'global_filter': self.config.get('global_filter'),
            'weighting_enabled': self.config.get('weighting', {}).get('enabled', False)
        }


def validate_configuration(spss_path: str, meta_path: str, tkinter_mode: bool = False) -> Tuple[bool, List[str], List[str], Dict, Dict]:
    """
    Convenience function to validate configuration
    
    Args:
        spss_path: Path to SPSS file
        meta_path: Path to meta.json
        tkinter_mode: If True, skip meta.json spss_file_path check
    
    Returns:
        tuple: (is_valid, errors, warnings, spss_info, config_summary)
    """
    validator = SPSSMetaValidator(spss_path, meta_path)
    is_valid, errors, warnings = validator.validate(tkinter_mode=tkinter_mode)
    
    return (
        is_valid,
        errors,
        warnings,
        validator.get_spss_info(),
        validator.get_config_summary()
    )