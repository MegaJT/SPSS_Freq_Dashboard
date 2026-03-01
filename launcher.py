"""
launcher.py - Tkinter Launcher for SPSS Frequency Dashboard

Minimal UI for file selection and Dash app lifecycle management.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import socket
import os
import sys
import threading
import signal
import webbrowser
import time
from pathlib import Path
from datetime import datetime

from validator import validate_configuration


class DashboardLauncher:
    """Tkinter launcher for SPSS Frequency Dashboard"""
    
    def __init__(self):
        """Initialize the launcher UI"""
        self.root = tk.Tk()
        self.root.title("SPSS Frequency Dashboard Launcher")
        self.root.geometry("800x750")  
        self.root.minsize(800, 750)    # Minimum size for all content to be visible
        self.root.resizable(True, True)  # Allow resizing
        
        # Set window icon
        try:
            icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'app_icon.ico')
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception as e:
            print(f"⚠ Could not load icon: {e}")
        
        # Center window on screen
        self._center_window()
        
        # State variables
        self.spss_path = tk.StringVar()
        self.meta_path = tk.StringVar()
        self.dash_process = None
        self.dash_port = None
        self.is_running = False
        self.title_label = None
        # Config builder process state
        self.config_builder_process = None
        self.config_builder_port = None
        self.config_builder_running = False
        
        # Configure style
        self._configure_style()
        
        # Build UI
        self._build_ui()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _validate_before_launch(self):
        """Validate configuration before launching dashboard (uses validator)."""
        print("\n🔍 Validating configuration...")

        is_valid, errors, warnings, spss_info, config_summary = validate_configuration(
            self.spss_path.get(),
            self.meta_path.get(),
            tkinter_mode=True
        )

        if not is_valid:
            error_msg = "Validation Errors:\n\n" + "\n".join(f"• {e}" for e in errors)
            if warnings:
                error_msg += "\n\nWarnings:\n" + "\n".join(f"• {w}" for w in warnings)

            messagebox.showerror("Validation Failed", error_msg)
            self._update_status("Validation failed", "error")
            return False

        if warnings:
            warning_msg = "Warnings (dashboard will still launch):\n\n" + "\n".join(f"• {w}" for w in warnings)
            messagebox.showwarning("Validation Warnings", warning_msg)

        print("✅ Validation PASSED")
        self._update_status("Validation passed", "success")
        return True

    def _center_window(self):
        """Center window on screen"""
        self.root.update_idletasks()
        width = 800
        height = 750
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _configure_style(self):
        """Configure ttk styles for professional look"""
        style = ttk.Style()
        
        # Use clam theme for cleaner look
        style.theme_use('clam')
        
        # Configure colors
        style.configure('TFrame', background='#F7FAFC')
        style.configure('TLabel', background='#F7FAFC', foreground='#2D3748', font=('Segoe UI', 10))
        style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'), foreground='#1A202C')
        style.configure('Status.TLabel', font=('Segoe UI', 9), foreground='#718096')
        style.configure('Success.TLabel', foreground='#06A77D')
        style.configure('Error.TLabel', foreground='#E53E3E')
        style.configure('Running.TLabel', foreground='#2E86AB')
        
        style.configure('TButton', font=('Segoe UI', 10), padding=8)
        style.configure('Primary.TButton', font=('Segoe UI', 10, 'bold'), padding=10)
        
        style.configure('TEntry', padding=8, font=('Segoe UI', 10))
        style.map('TButton', 
            background=[('active', '#2E86AB'), ('disabled', '#CBD5E0')],
            foreground=[('disabled', '#718096')]
        )
    
    def _build_ui(self):
        """Build the UI components"""
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.title_label = ttk.Label(
            header_frame,
            text="📊 SPSS Frequency Dashboard",
            style='Header.TLabel'
        )
        self.title_label.pack(anchor=tk.W)
        
        subtitle_label = ttk.Label(
            header_frame,
            text="Select files and launch the interactive dashboard",
            style='TLabel'
        )
        subtitle_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # SPSS File Selection
        spss_frame = ttk.Frame(main_frame)
        spss_frame.pack(fill=tk.X, pady=8)
        
        ttk.Label(spss_frame, text="SPSS File (.sav):", style='TLabel').pack(anchor=tk.W, pady=(0, 5))
        
        spss_entry_frame = ttk.Frame(spss_frame)
        spss_entry_frame.pack(fill=tk.X)
        
        ttk.Entry(
            spss_entry_frame,
            textvariable=self.spss_path,
            width=50
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        ttk.Button(
            spss_entry_frame,
            text="Browse...",
            command=self._browse_spss
        ).pack(side=tk.RIGHT)
        
        # Update title and button states when SPSS file changes
        self.spss_path.trace('w', self._update_title_with_spss_name)
        self.spss_path.trace('w', self._update_config_btn_state)
        
        # Meta.json File Selection
        meta_frame = ttk.Frame(main_frame)
        meta_frame.pack(fill=tk.X, pady=8)
        
        ttk.Label(meta_frame, text="Meta Configuration (.json):", style='TLabel').pack(anchor=tk.W, pady=(0, 5))
        
        meta_entry_frame = ttk.Frame(meta_frame)
        meta_entry_frame.pack(fill=tk.X)
        
        ttk.Entry(
            meta_entry_frame,
            textvariable=self.meta_path,
            width=50
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        ttk.Button(
            meta_entry_frame,
            text="Browse...",
            command=self._browse_meta
        ).pack(side=tk.RIGHT)

        # Trace meta path to update config builder button state
        self.meta_path.trace('w', self._update_config_btn_state)
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Status Display (simplified)
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=8)
        
        self.status_label = ttk.Label(
            status_frame,
            text="Status: Ready",
            style='Status.TLabel'
        )
        self.status_label.pack(anchor=tk.W)
        
        self.port_label = ttk.Label(
            status_frame,
            text="",
            style='Status.TLabel'
        )
        self.port_label.pack(anchor=tk.W, pady=(3, 0))
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Config Builder Section
        config_frame = ttk.LabelFrame(main_frame, text="Config Builder", padding="10")
        config_frame.pack(fill=tk.X, pady=8)

        config_btn_frame = ttk.Frame(config_frame)
        config_btn_frame.pack(fill=tk.X)

        self.config_btn = ttk.Button(
            config_btn_frame,
            text="🔧 Build / Edit Config",
            command=self._launch_config_builder,
            state=tk.DISABLED
        )
        self.config_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_config_btn = ttk.Button(
            config_btn_frame,
            text="✖ Close Config Editor",
            command=self._shutdown_config_builder,
            state=tk.DISABLED
        )
        self.stop_config_btn.pack(side=tk.LEFT)

        self.config_status_label = ttk.Label(
            config_frame,
            text="Select an SPSS file to enable the config builder",
            style="Status.TLabel"
        )
        self.config_status_label.pack(anchor=tk.W, pady=(6, 0))

        # Action Buttons - Dashboard Controls
        dashboard_frame = ttk.LabelFrame(main_frame, text="Dashboard Controls", padding="10")
        dashboard_frame.pack(fill=tk.X, pady=8)
        
        dashboard_btn_frame = ttk.Frame(dashboard_frame)
        dashboard_btn_frame.pack(fill=tk.X)
        
        self.launch_btn = ttk.Button(
            dashboard_btn_frame,
            text="🚀 Launch Dashboard",
            command=self._launch_dashboard,
            style='Primary.TButton'
        )
        self.launch_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.shutdown_btn = ttk.Button(
            dashboard_btn_frame,
            text="🛑 Stop Server",
            command=self._shutdown_server,
            state=tk.DISABLED
        )
        self.shutdown_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.url_button = ttk.Button(
            dashboard_btn_frame,
            text="🌐 Open in Browser",
            command=self._open_in_browser,
            state=tk.DISABLED
        )
        self.url_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Export Section
        export_frame = ttk.LabelFrame(main_frame, text="Data Export", padding="10")
        export_frame.pack(fill=tk.X, pady=8)
        
        self.export_btn = ttk.Button(
            export_frame,
            text="📁 Generate TXT Export",
            command=self._generate_export
        )
        self.export_btn.pack(side=tk.LEFT)
        
        # Footer
        footer_frame = ttk.Frame(main_frame)
        footer_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(
            footer_frame,
            text=f"Version 1.0 | {datetime.now().strftime('%Y')}",
            style='Status.TLabel'
        ).pack(anchor=tk.CENTER)
    
    def _browse_spss(self):
        """Open file dialog for SPSS file"""
        filename = filedialog.askopenfilename(
            title="Select SPSS File",
            filetypes=[("SPSS Files", "*.sav"), ("All Files", "*.*")]
        )
        if filename:
            self.spss_path.set(filename)
            self._update_status("SPSS file selected", "success")
    
    def _browse_meta(self):
        """Open file dialog for meta.json file"""
        filename = filedialog.askopenfilename(
            title="Select Meta Configuration",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if filename:
            self.meta_path.set(filename)
            self._update_status("Meta file selected", "success")
    
    def _update_title_with_spss_name(self, *args):
        """Update title with SPSS filename when selected"""
        spss_path = self.spss_path.get()
        if spss_path:
            filename = os.path.basename(spss_path)
            # Remove .sav extension to get just the filename
            filename_without_ext = os.path.splitext(filename)[0]
            new_title = f"📊 {filename_without_ext} - Dashboard"
            self.title_label.config(text=new_title)
        else:
            self.title_label.config(text="📊 SPSS Frequency Dashboard")
    
    def _find_available_port(self):
        """Find an available port for Dash app"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def _update_status(self, message, status_type="info"):
        """Update status label with message and color"""
        self.status_label.config(text=f"Status: {message}")
        
        # Update style based on status type
        if status_type == "success":
            self.status_label.configure(style='Success.TLabel')
        elif status_type == "error":
            self.status_label.configure(style='Error.TLabel')
        elif status_type == "running":
            self.status_label.configure(style='Running.TLabel')
        else:
            self.status_label.configure(style='Status.TLabel')
        
        self.root.update_idletasks()
    
    def _validate_inputs(self):
        """Validate user inputs before launching"""
        errors = []
        
        if not self.spss_path.get():
            errors.append("SPSS file not selected")
        elif not os.path.exists(self.spss_path.get()):
            errors.append(f"SPSS file not found: {self.spss_path.get()}")
        
        if not self.meta_path.get():
            errors.append("Meta configuration not selected")
        elif not os.path.exists(self.meta_path.get()):
            errors.append(f"Meta file not found: {self.meta_path.get()}")
        
        return errors
    
    def _launch_dashboard(self):
        """Launch the Dash dashboard as subprocess"""
        # Hard block if config editor is open — never allow both simultaneously
        if self.config_builder_running:
            messagebox.showwarning(
                "Config Editor Open",
                "Please close the config editor before launching the dashboard."
            )
            return

        # Validate file selections exist
        errors = self._validate_inputs()
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            self._update_status("Validation failed", "error")
            return

        # Run SPSS/Meta validation BEFORE launch
        if not self._validate_before_launch():
            return

        # Find available port
        try:
            self.dash_port = self._find_available_port()
        except Exception as e:
            messagebox.showerror("Port Error", f"Could not find available port: {str(e)}")
            self._update_status("Port allocation failed", "error")
            return

        # Build launch command for dash_app
        try:
            python_exe = sys.executable or 'python'
            cmd = [python_exe, os.path.join(os.getcwd(), 'dash_app.py'),
                   '--spss-path', self.spss_path.get(),
                   '--meta-path', self.meta_path.get(),
                   '--port', str(self.dash_port)]

            # Start subprocess
            self.dash_process = subprocess.Popen(cmd)
            self.is_running = True
            self._update_ui_state(running=True)
            self._update_status(f"Server running on port {self.dash_port}", "running")
            
            # Display full URL
            url = f"http://localhost:{self.dash_port}"
            self.port_label.config(text=f"Dashboard URL: {url}")
            self.url_button.config(state=tk.NORMAL)
            
            # Auto-open browser after short delay (allow server to start)
            threading.Thread(target=self._auto_open_browser, daemon=True).start()

            # Monitor in background
            monitor_thread = threading.Thread(target=self._monitor_process, daemon=True)
            monitor_thread.start()

        except Exception as e:
            messagebox.showerror("Launch Error", f"Failed to start dashboard: {str(e)}")
            self._update_status("Launch failed", "error")

    def _shutdown_server(self):
        """Shutdown the running Dash server"""
        if self.dash_process and self.is_running:
            try:
                # Use terminate() on all platforms (more reliable, doesn't affect parent process)
                self.dash_process.terminate()
                
                # Wait for process to end gracefully
                try:
                    self.dash_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    # Force kill if not responding
                    self.dash_process.kill()
                    self.dash_process.wait(timeout=1)
                
            except Exception as e:
                messagebox.showwarning("Shutdown Warning", f"Error stopping server: {str(e)}")
            finally:
                self.dash_process = None
                self.is_running = False
                self._update_ui_state(running=False)
                self._update_status("Server stopped", "info")
                self.port_label.config(text="")
                self.url_button.config(state=tk.DISABLED)
        else:
            messagebox.showinfo("Info", "No server is currently running")
    
    def _update_config_btn_state(self, *args):
        """
        Enable config builder ONLY when:
          - SPSS file is selected and exists
          - No JSON config has been picked yet
        Disable it if a JSON is already loaded (user should use it separately),
        or if dashboard / editor is already running.
        """
        spss_ok = bool(self.spss_path.get() and os.path.exists(self.spss_path.get()))
        json_loaded = bool(self.meta_path.get())

        if self.config_builder_running or self.is_running:
            return  # States already locked — do not touch

        if spss_ok and not json_loaded:
            # This is the target state: SPSS chosen, no JSON yet
            self.config_btn.config(state=tk.NORMAL)
            self.config_status_label.config(
                text="No config selected — build one from your SPSS file"
            )
        elif spss_ok and json_loaded:
            # JSON is already loaded: builder not needed, keep disabled
            self.config_btn.config(state=tk.DISABLED)
            self.config_status_label.config(
                text="Config already loaded. Clear the JSON path to use the builder"
            )
        else:
            self.config_btn.config(state=tk.DISABLED)
            self.config_status_label.config(
                text="Select an SPSS file to enable the config builder"
            )

    def _launch_config_builder(self):
        """Launch the config builder as a subprocess"""
        # Block if dashboard or export is running
        if self.is_running:
            messagebox.showwarning(
                "Dashboard Running",
                "Please stop the dashboard before opening the config editor."
            )
            return

        if not self.spss_path.get() or not os.path.exists(self.spss_path.get()):
            messagebox.showerror("Error", "Please select a valid SPSS file first.")
            return

        try:
            self.config_builder_port = self._find_available_port()
        except Exception as e:
            messagebox.showerror("Port Error", f"Could not find available port: {e}")
            return

        try:
            python_exe = sys.executable or 'python'
            cmd = [
                python_exe,
                os.path.join(os.getcwd(), 'config_builder.py'),
                '--spss-path', self.spss_path.get(),
                '--port', str(self.config_builder_port)
            ]
            # Pass existing JSON path if one is loaded
            if self.meta_path.get() and os.path.exists(self.meta_path.get()):
                cmd += ['--meta-path', self.meta_path.get()]

            self.config_builder_process = subprocess.Popen(cmd)
            self.config_builder_running = True

            # Update UI — lock out dashboard and export while editor is open
            self.config_btn.config(state=tk.DISABLED)
            self.stop_config_btn.config(state=tk.NORMAL)
            self.launch_btn.config(state=tk.DISABLED)
            self.export_btn.config(state=tk.DISABLED)
            self.config_status_label.config(text="Config editor is open in browser...")
            self._update_status("Config editor running", "running")

            # Auto-open browser once ready
            threading.Thread(
                target=self._auto_open_config_builder, daemon=True
            ).start()

            # Monitor process — re-enable everything when it closes
            threading.Thread(
                target=self._monitor_config_builder, daemon=True
            ).start()

        except Exception as e:
            messagebox.showerror("Launch Error", f"Failed to start config editor: {e}")

    def _auto_open_config_builder(self):
        """Open browser for config builder once server is ready"""
        url = f"http://localhost:{self.config_builder_port}"
        max_wait = 30
        poll = 0.5
        for _ in range(int(max_wait / poll)):
            try:
                with socket.create_connection(("127.0.0.1", self.config_builder_port), timeout=1):
                    webbrowser.open(url)
                    print(f"✓ Opened config builder at {url}")
                    return
            except (ConnectionRefusedError, OSError):
                time.sleep(poll)
        print(f"⚠ Config builder did not start within {max_wait}s")

    def _monitor_config_builder(self):
        """Watch the config builder subprocess and clean up when it ends"""
        if self.config_builder_process:
            self.config_builder_process.wait()
            self.root.after(0, self._on_config_builder_ended)

    def _on_config_builder_ended(self):
        """Called on main thread when config builder process exits"""
        self.config_builder_process = None
        self.config_builder_running = False
        self.config_builder_port = None
        self.stop_config_btn.config(state=tk.DISABLED)
        self._update_status("Config editor closed", "info")
        # Re-evaluate all button states fresh
        self._update_ui_state(running=self.is_running)
        self._update_config_btn_state()

    def _shutdown_config_builder(self):
        """Manually stop the config builder from the launcher"""
        if self.config_builder_process and self.config_builder_running:
            try:
                self.config_builder_process.terminate()
                try:
                    self.config_builder_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.config_builder_process.kill()
                    self.config_builder_process.wait(timeout=1)
            except Exception as e:
                messagebox.showwarning("Warning", f"Error closing config editor: {e}")
            finally:
                self._on_config_builder_ended()
        else:
            messagebox.showinfo("Info", "Config editor is not running")

    def _update_ui_state(self, running=False):
        """Update button states based on dashboard running status"""
        if running:
            self.launch_btn.config(state=tk.DISABLED)
            self.shutdown_btn.config(state=tk.NORMAL)
            self.export_btn.config(state=tk.NORMAL)
            # Lock config builder while dashboard is running
            self.config_btn.config(state=tk.DISABLED)
            self.stop_config_btn.config(state=tk.DISABLED)
            self.config_status_label.config(
                text="Stop the dashboard before using the config builder"
            )
        else:
            self.launch_btn.config(state=tk.NORMAL)
            self.shutdown_btn.config(state=tk.DISABLED)
            self.export_btn.config(state=tk.NORMAL)
            # Re-evaluate config builder button fresh from file state
            self._update_config_btn_state()
    
    def _auto_open_browser(self):
        """Automatically open browser only after the server is confirmed ready"""
        url = f"http://localhost:{self.dash_port}"
        max_wait_seconds = 30
        poll_interval = 0.5

        for _ in range(int(max_wait_seconds / poll_interval)):
            try:
                with socket.create_connection(("127.0.0.1", self.dash_port), timeout=1):
                    # Server is accepting connections — safe to open browser
                    webbrowser.open(url)
                    print(f"✓ Opened browser at {url}")
                    return
            except (ConnectionRefusedError, OSError):
                time.sleep(poll_interval)

        # Server never became ready within the timeout
        print(f"⚠ Server did not become ready within {max_wait_seconds}s. Open manually: {url}")
    
    def _open_in_browser(self):
        """Open dashboard URL in browser (manual button click)"""
        if self.dash_port:
            url = f"http://localhost:{self.dash_port}"
            try:
                webbrowser.open(url)
            except Exception as e:
                messagebox.showerror("Error", f"Could not open browser: {str(e)}")
        else:
            messagebox.showwarning("Warning", "Dashboard is not running")
    
    def _monitor_process(self):
        """Monitor Dash subprocess and update UI when it closes"""
        if self.dash_process:
            self.dash_process.wait()
            
            # Update UI on main thread
            self.root.after(0, lambda: self._on_process_ended())
    
    def _on_process_ended(self):
        """Handle when Dash process ends unexpectedly"""
        self.is_running = False
        self._update_ui_state(running=False)
        self._update_status("Server closed", "info")
        self.port_label.config(text="")
    
    def _generate_export(self):
        """Generate TXT export using existing OutputWriter"""
        # Validate inputs
        errors = self._validate_inputs()
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return

        # Disable the button and show progress so the UI doesn't appear frozen
        self.export_btn.config(state=tk.DISABLED, text="⏳ Exporting...")
        self._update_status("Export in progress...", "running")
        self.root.update_idletasks()

        # Run the actual export on a background thread to keep the UI responsive
        threading.Thread(target=self._run_export_thread, daemon=True).start()

    def _run_export_thread(self):
        """Background thread: does the heavy lifting for export"""
        try:
            from config_loader import ConfigLoader
            from spss_reader import SPSSReader
            from frequency_processor import FrequencyProcessor
            from output_writer import OutputWriter

            # Load config
            loader = ConfigLoader(self.meta_path.get(), spss_file_path=self.spss_path.get())
            config = loader.load()
            is_valid, errors = loader.validate()

            if not is_valid:
                self.root.after(0, lambda: self._export_done(
                    success=False, message="Config Error:\n" + "\n".join(errors)
                ))
                return

            # Read SPSS
            self.root.after(0, lambda: self._update_status("Reading SPSS file...", "running"))
            reader = SPSSReader(self.spss_path.get())
            if not reader.read():
                self.root.after(0, lambda: self._export_done(
                    success=False, message="Failed to read SPSS file."
                ))
                return

            # Process variables
            self.root.after(0, lambda: self._update_status("Processing variables...", "running"))
            filter_sets = config.get('filter_sets', {})
            global_filter = config.get('global_filter', None)
            weighting_config = config.get('weighting', {})

            processor = FrequencyProcessor(
                reader,
                filter_sets=filter_sets,
                global_filter=global_filter,
                weighting_config=weighting_config
            )

            results = processor.process_all_variables(config['variables'])
            warnings = processor.get_warnings()

            if not results:
                self.root.after(0, lambda: self._export_done(
                    success=False, message="No results were generated."
                ))
                return

            # Write output
            self.root.after(0, lambda: self._update_status("Writing output file...", "running"))
            output_file = config['output_file']
            weight_var_name = weighting_config.get('weight_variable') if weighting_config.get('enabled') else None

            writer = OutputWriter(
                output_file,
                global_filter=global_filter,
                weight_variable=weight_var_name
            )

            if writer.write(results, warnings, filter_sets):
                self.root.after(0, lambda: self._export_done(
                    success=True, message=f"Output written to:\n{output_file}"
                ))
            else:
                self.root.after(0, lambda: self._export_done(
                    success=False, message="Failed to write output file."
                ))

        except Exception as e:
            import traceback
            traceback.print_exc()
            err_msg = str(e)
            self.root.after(0, lambda: self._export_done(
                success=False, message=f"Export failed:\n{err_msg}"
            ))

    def _export_done(self, success, message):
        """Called on the main thread when the export thread finishes"""
        # Restore button regardless of outcome
        self.export_btn.config(state=tk.NORMAL, text="📁 Generate TXT Export")

        if success:
            self._update_status("Export generated successfully", "success")
            messagebox.showinfo("Export Complete", message)
        else:
            self._update_status("Export failed", "error")
            messagebox.showerror("Export Error", message)
    
    def _on_closing(self):
        """Handle window close event"""
        running_items = []
        if self.is_running:
            running_items.append("Dashboard server")
        if self.config_builder_running:
            running_items.append("Config editor")

        if running_items:
            msg = ", ".join(running_items) + " is still running. Stop and exit?"
            if messagebox.askyesno("Confirm Exit", msg):
                if self.config_builder_running:
                    try:
                        self.config_builder_process.terminate()
                        self.config_builder_process.wait(timeout=2)
                    except Exception:
                        pass
                if self.is_running:
                    self._shutdown_server()
                self.root.destroy()
        else:
            self.root.destroy()
    
    def run(self):
        """Start the Tkinter main loop"""
        self.root.mainloop()


def main():
    """Entry point for launcher"""
    print("=" * 70)
    print("SPSS FREQUENCY DASHBOARD LAUNCHER")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    launcher = DashboardLauncher()
    launcher.run()


if __name__ == "__main__":
    main()