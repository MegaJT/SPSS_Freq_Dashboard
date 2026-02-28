import pyreadstat
import pandas as pd


class SPSSReader:
    """Reads SPSS files and extracts data with metadata"""
    
    def __init__(self, file_path):
        """
        Initialize SPSS reader
        
        Args:
            file_path: Path to the .sav file
        """
        self.file_path = file_path
        self.data = None
        self.metadata = None
        self.value_labels = None
        self.column_names = None
        self.column_labels = None
    
    def read(self):
        """
        Read the SPSS file
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            print(f"\nReading SPSS file: {self.file_path}")
            
            # Read SPSS file with metadata
            self.data, self.metadata = pyreadstat.read_sav(self.file_path)
            
            # Extract useful metadata
            self.value_labels = self.metadata.variable_value_labels 
            self.column_names = self.metadata.column_names
            self.column_labels = self.metadata.column_names_to_labels 
            
            print(f"✓ Successfully read SPSS file")
            print(f"  Rows: {len(self.data)}")
            print(f"  Columns: {len(self.data.columns)}")
            
            return True
            
        except FileNotFoundError:
            print(f"✗ Error: SPSS file not found: {self.file_path}")
            return False
        except Exception as e:
            print(f"✗ Error reading SPSS file: {str(e)}")
            return False
    
    def get_data(self):
        """Get the data DataFrame"""
        return self.data
    
    def get_variable_label(self, var_name):
        """
        Get the label for a variable
        
        Args:
            var_name: Variable name
            
        Returns:
            str: Variable label or the variable name if no label exists
        """
        if self.column_labels and var_name in self.column_labels:
            return self.column_labels[var_name]
        return var_name
    
    def get_value_labels(self, var_name):
        """
        Get value labels for a variable
        
        Args:
            var_name: Variable name
            
        Returns:
            dict: Dictionary mapping values to labels, or None if no labels exist
        
        Example:
            {1: 'Male', 2: 'Female'} for a gender variable
        """
        if self.value_labels and var_name in self.value_labels:
            return self.value_labels[var_name]
        return None
    
    def variable_exists(self, var_name):
        """
        Check if a variable exists in the dataset
        
        Args:
            var_name: Variable name to check
            
        Returns:
            bool: True if variable exists, False otherwise
        """
        return var_name in self.data.columns
    
    def get_column_data(self, var_name):
        """
        Get data for a specific column
        
        Args:
            var_name: Variable name
            
        Returns:
            pandas.Series: Column data, or None if variable doesn't exist
        """
        if self.variable_exists(var_name):
            return self.data[var_name]
        return None
    
    def get_info(self):
        """
        Get summary information about the SPSS file
        
        Returns:
            dict: Summary information
        """
        if self.data is None:
            return None
        
        return {
            'file_path': self.file_path,
            'n_rows': len(self.data),
            'n_columns': len(self.data.columns),
            'columns': list(self.data.columns),
            'has_value_labels': self.value_labels is not None
        }


# Test function
if __name__ == "__main__":
    # Test the SPSS reader
    import sys
    
    if len(sys.argv) > 1:
        spss_file = sys.argv[1]
    else:
        spss_file = "data/survey.sav"  # Default test file
    
    reader = SPSSReader(spss_file)
    
    if reader.read():
        print("\n" + "="*50)
        print("SPSS FILE INFORMATION")
        print("="*50)
        
        info = reader.get_info()
        print(f"File: {info['file_path']}")
        print(f"Rows: {info['n_rows']}")
        print(f"Columns: {info['n_columns']}")
        
        print("\nFirst 5 columns:")
        for i, col in enumerate(info['columns'][:5]):
            label = reader.get_variable_label(col)
            print(f"  {col}: {label}")
        
        # Show value labels for first column (if exists)
        if info['columns']:
            first_col = info['columns'][0]
            value_labels = reader.get_value_labels(first_col)
            if value_labels:
                print(f"\nValue labels for '{first_col}':")
                for value, label in value_labels.items():
                    print(f"  {value}: {label}")