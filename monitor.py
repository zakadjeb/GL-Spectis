"""Tkinter monitor: persistent link checks, history, mean/SEM and spectral + CIE LSL."""
import csv
import math
import queue
import time
import tkinter as tk
from pathlib import Path
import numpy as np
from tkinter import ttk, filedialog, messagebox, colorchooser
from matplotlib.colors import to_rgb, is_color_like
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import AutoMinorLocator
from acquisition import Acquisition
from analysis_tools import CIE_CHANNELS, summarize, selection_xyY, xy_to_hex
from streaming import Publisher
from measurement_csv import save_measurements, load_measurements
from preferences import read_settings, write_settings, validate_settings


class Monitor(tk.Tk):
    def __init__(self, auto_connect=True, config_path=None):
        super().__init__()
        self.title('GL Spectis | Spectra & color')
        width = min(1320, self.winfo_screenwidth()-40)
        height = min(870, self.winfo_screenheight()-90)
        self.geometry(f'{width}x{height}+15+15')
        self.minsize(min(1050, width), min(650, height))
        self.events = queue.Queue()
        self.publisher = Publisher()
        self.history = []
        self.latest = None
        self.follow_latest = True
        self.started = None
        self.last_activity = None
        self.link_color = 'red'
        self.busy = False
        self.requested_host = None
        self.closing = False
        self.host = tk.StringVar(value='172.20.10.2')
        self.exposure = tk.StringVar(value='10')
        self.repeats = tk.StringVar(value='3')
        self.status = tk.StringVar(value='Disconnected')
        self.details = tk.StringVar(value='No measurements received')
        self.elapsed = tk.StringVar(value='')
        self.link_age = tk.StringVar(value='No response yet')
        self.lsl_status = tk.StringVar(value='LSL stopped')
        self.selection_status = tk.StringVar(value='Following latest measurement')
        self.color_text = tk.StringVar(value='CIE values unavailable')
        self.plot_mode = tk.StringVar(value='mean')
        self.fixed_y = tk.BooleanVar(value=False)
        self.y_min = tk.StringVar(value='0')
        self.y_max = tk.StringVar(value='1')
        self.background_color = tk.StringVar(value='#101b2c')
        self.mean_color = tk.StringVar(value='#5de0be')
        self.palette = [tk.StringVar(value=c) for c in
                        ('#5de0be', '#ffb454', '#68b8ff', '#eb8fe8', '#ff7777', '#d5df70')]
        self.plot_options = dict(mode='mean', ylim=None, background='#101b2c',
                                 mean='#5de0be', palette=[v.get() for v in self.palette])
        self.config_path = Path(config_path) if config_path is not None else Path(__file__).with_name('settings.txt')
        config_error = None
        try:
            if self.config_path.exists():
                self.set_settings(read_settings(self.config_path))
        except (OSError, ValueError) as exc:
            config_error = str(exc)
        self._build()
        if config_error:
            self.add_log(f'Could not load settings.txt; using defaults: {config_error}')
        self.worker = Acquisition(self.events)
        self.worker.start()
        self.protocol('WM_DELETE_WINDOW', self.close_window)
        self.after(100, self.poll)
        if auto_connect:
            self.after(300, self.connect)

    def _build(self):
        tabs = ttk.Notebook(self)
        tabs.pack(fill='both', expand=True, padx=12, pady=12)
        main = ttk.Frame(tabs, padding=10)
        settings = ttk.Frame(tabs, padding=18)
        tabs.add(main, text='Monitor')
        tabs.add(settings, text='Settings & LSL')
        visualization = ttk.Frame(tabs, padding=18)
        tabs.add(visualization, text='Visualization')
        self.build_visualization(visualization)
        header = ttk.Frame(main)
        header.pack(fill='x')
        self.light = tk.Canvas(header, width=26, height=26, highlightthickness=0)
        self.light.pack(side='left', padx=(0, 8))
        self.bulb = self.light.create_oval(4, 4, 22, 22, fill='#dc4444', outline='')
        ttk.Label(header, textvariable=self.status, font=('Segoe UI', 12, 'bold')).pack(side='left')
        ttk.Label(main, textvariable=self.link_age).pack(anchor='w')
        ttk.Label(main, textvariable=self.details).pack(anchor='w', pady=3)
        ttk.Label(main, textvariable=self.elapsed).pack(anchor='w')
        controls = ttk.Frame(main)
        controls.pack(fill='x', pady=8)
        ttk.Button(controls, text='Connect / check link', command=self.connect).pack(side='left', padx=2)
        ttk.Button(controls, text='Disconnect', command=self.disconnect).pack(side='left', padx=2)
        self.acquire_buttons = []
        for label, mode in [('Measure once', 'once'), ('Start collecting', 'continuous')]:
            button = ttk.Button(controls, text=label, command=lambda m=mode: self.start(m))
            button.pack(side='left', padx=2)
            self.acquire_buttons.append(button)
        ttk.Button(controls, text='Stop collecting', command=self.stop).pack(side='left', padx=2)
        self.lsl_controls(controls, horizontal=True)
        ttk.Label(main, textvariable=self.lsl_status).pack(anchor='w', pady=(0, 7))
        self.log = tk.Text(main, height=3, state='disabled', wrap='word')
        self.log.pack(side='bottom', fill='x', pady=(10, 0))
        body = ttk.Panedwindow(main, orient='horizontal')
        body.pack(fill='both', expand=True)
        left, right = ttk.Frame(body), ttk.Frame(body, width=380)
        body.add(left, weight=3)
        body.add(right, weight=2)
        self.figure = Figure(figsize=(7, 4), dpi=100, facecolor='#101b2c')
        self.axes = self.figure.add_subplot(111)
        self.figure.subplots_adjust(left=.14, right=.96, bottom=.29, top=.88)
        self.canvas = FigureCanvasTkAgg(self.figure, master=left)
        ttk.Label(left, text='Color preview: normalized sRGB approximation; not calibrated brightness.',
                  wraplength=600).pack(side='bottom', anchor='w')
        color_row = ttk.Frame(left)
        color_row.pack(side='bottom', fill='x', pady=10)
        self.swatch = tk.Label(color_row, width=10, height=3, background='#777777', text='N/A')
        self.swatch.pack(side='left', padx=(0, 12))
        ttk.Label(color_row, textvariable=self.color_text, justify='left').pack(side='left')
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        ttk.Label(right, text='Collected measurements — Ctrl/Shift-select to compare',
                  font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self.history_tree = self.tree(right, ('time', 'x', 'y', 'Y'),
                                      ('Received', 'CIE x', 'CIE y', 'CIE Y'), 5)
        self.history_tree.bind('<<TreeviewSelect>>', self.history_selected)
        self.history_tree.bind('<ButtonPress-1>', lambda _: self.pause_follow())
        self.history_tree.bind('<KeyPress>', lambda _: self.pause_follow())
        actions = ttk.Frame(right)
        actions.pack(fill='x', pady=5)
        ttk.Button(actions, text='View the last', command=self.view_latest).pack(side='left')
        ttk.Button(actions, text='Export selected', command=self.export).pack(side='left', padx=6)
        ttk.Button(actions, text='Open CSV', command=self.open_csv).pack(side='left')
        removal = ttk.Frame(right)
        removal.pack(fill='x', pady=(0, 5))
        ttk.Button(removal, text='Remove selected', command=self.remove_selected).pack(side='left')
        ttk.Button(removal, text='Clear all', command=self.clear_measurements).pack(side='left', padx=6)
        ttk.Label(right, textvariable=self.selection_status, wraplength=380).pack(anchor='w', pady=4)
        ttk.Label(right, text='Spectrum values (selection mean and standard error)').pack(anchor='w')
        self.values_tree = self.tree(right, ('nm', 'mean', 'sem'), ('nm', 'Mean / value', 'SEM'), 4)
        ttk.Label(right, text='CIE / color values for the selection').pack(anchor='w', pady=(6, 0))
        self.cie_tree = self.tree(right, ('key', 'value'), ('Quantity', 'Value'), 3)
        self.setting_widgets = []
        for row, (label, variable) in enumerate([('Instrument IP address', self.host),
                                                ('Exposure per repeat (seconds)', self.exposure),
                                                ('Repeats per measurement', self.repeats)]):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky='w', pady=8)
            entry = ttk.Entry(settings, textvariable=variable, width=24)
            entry.grid(row=row, column=1, padx=15)
            self.setting_widgets.append(entry)
        stream_controls = ttk.Frame(settings)
        stream_controls.grid(row=3, column=0, columnspan=2, sticky='w', pady=15)
        self.lsl_controls(stream_controls, horizontal=True)
        ttk.Label(settings, textvariable=self.lsl_status).grid(row=4, column=0, columnspan=2, sticky='w')
        ttk.Label(settings, justify='left', text=(
            'Default: 10 seconds × 3 repeats ≈ 30 seconds plus transfer time.\n'
            'Fixed exposure; automatic exposure is off. Stop collecting to edit settings.\n\n'
            'Green: verified response. Yellow: error or response older than 10 seconds.\n'
            'Red: disconnected. Idle configuration checks run every 5 seconds.\n'
            'During exposure, incoming progress/data confirms the link on the same socket.\n'
            'Link recovery is automatic; collection must be restarted after an error.\n\n'
            'Start/Stop LSL is independent of acquisition and can be used while collecting.\n'
            'Streams: GL-Spectis (spectrum) and GL-Spectis-CIE (colorimetry).\n'
            'Both use the same host receipt timestamp; values are per completed measurement.\n'
            'CIE: x, y, Y, u, v, u′, v′, CCT. Missing values are NaN.\n'
            'Streams appear after the next new measurement; old history is never replayed.\n\n'
            'Multi-selection: arithmetic mean ±1 SEM across completed measurements.\n'
            'SEM = sample standard deviation / √n; requires at least two measurements.\n'
            'Device repeats are not treated as independent measurements.\n'
            'The multi-selection color averages XYZ, then converts to xyY.\n'
            'Averaging affects the preview only. Export saves every selected trial.\n'
            'Open CSV restores saved trials for viewing; it never replays them to LSL.\n\n'
            'Stopping may leave an exposure running on the instrument. Wait for completion\n'
            'before restarting. History is kept for this session; export before closing.'
        )).grid(row=5, column=0, columnspan=2, sticky='w', pady=16)
        config_controls = ttk.Frame(settings)
        config_controls.grid(row=6, column=0, columnspan=2, sticky='w')
        self.settings_buttons(config_controls)
        self.draw_empty()

    def build_visualization(self, parent):
        ttk.Label(parent, text='Selected measurements', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Radiobutton(parent, text='Mean spectrum with ±1 standard error',
                        variable=self.plot_mode, value='mean').pack(anchor='w', pady=4)
        ttk.Radiobutton(parent, text='Individual spectra overlaid',
                        variable=self.plot_mode, value='overlay').pack(anchor='w', pady=4)
        ttk.Checkbutton(parent, text='Fix the y-axis range', variable=self.fixed_y).pack(anchor='w', pady=(18, 6))
        bounds = ttk.Frame(parent)
        bounds.pack(anchor='w')
        for label, variable in [('Minimum', self.y_min), ('Maximum', self.y_max)]:
            ttk.Label(bounds, text=label).pack(side='left', padx=(0, 6))
            ttk.Entry(bounds, textvariable=variable, width=12).pack(side='left', padx=(0, 18))
        ttk.Label(parent, text='Limits use the spectrum’s displayed units. Values beyond the limits are clipped.').pack(anchor='w', pady=6)
        colors = ttk.Frame(parent)
        colors.pack(anchor='w', pady=12)
        for row, (label, variable) in enumerate([('Plot background', self.background_color),
                                                ('Mean / single spectrum', self.mean_color)]):
            ttk.Label(colors, text=label).grid(row=row, column=0, sticky='w', pady=4)
            self.color_button(colors, variable).grid(row=row, column=1, padx=12)
        ttk.Label(parent, text='Overlay line colors (repeat after six trials)').pack(anchor='w')
        palette_row = ttk.Frame(parent)
        palette_row.pack(anchor='w', pady=8)
        for variable in self.palette:
            self.color_button(palette_row, variable).pack(side='left', padx=(0, 8))
        ttk.Label(parent, text='Overlay legends identify each trial by its number in the measurement list.\n'
                  'The values table and color preview still summarize the selection.\n'
                  'These settings affect the plot only; CSV and LSL keep the original measurements.\n'
                  'Save settings to keep them for the next session.', justify='left').pack(anchor='w', pady=10)
        ttk.Button(parent, text='Apply visualization', command=self.apply_visualization).pack(anchor='w', pady=6)
        config_controls = ttk.Frame(parent)
        config_controls.pack(anchor='w', pady=8)
        self.settings_buttons(config_controls)
        ttk.Label(parent, text='Saved in settings.txt beside start_monitor.bat. Loaded automatically at startup.').pack(anchor='w')

    def settings_buttons(self, parent):
        ttk.Button(parent, text='Save settings', command=self.save_settings).pack(side='left', padx=(0, 8))
        ttk.Button(parent, text='Load settings', command=self.load_settings).pack(side='left')

    def current_settings(self):
        return validate_settings(dict(version=1, host=self.host.get().strip(),
            exposure_seconds=float(self.exposure.get()), repeats=int(self.repeats.get()),
            plot_mode=self.plot_mode.get(), fixed_y=self.fixed_y.get(),
            y_min=float(self.y_min.get()), y_max=float(self.y_max.get()),
            background_color=self.background_color.get(), mean_color=self.mean_color.get(),
            overlay_colors=[v.get() for v in self.palette]))

    def set_settings(self, data):
        validate_settings(data)
        for variable, key in [(self.host, 'host'), (self.exposure, 'exposure_seconds'),
                (self.repeats, 'repeats'), (self.plot_mode, 'plot_mode'), (self.fixed_y, 'fixed_y'),
                (self.y_min, 'y_min'), (self.y_max, 'y_max'),
                (self.background_color, 'background_color'), (self.mean_color, 'mean_color')]:
            variable.set(data[key])
        for variable, color in zip(self.palette, data['overlay_colors']):
            variable.set(color)
        self.plot_options = dict(mode=data['plot_mode'],
            ylim=(data['y_min'], data['y_max']) if data['fixed_y'] else None,
            background=data['background_color'], mean=data['mean_color'], palette=list(data['overlay_colors']))

    def save_settings(self):
        try:
            data = self.current_settings()
            write_settings(self.config_path, data)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Save settings', str(exc))
            return
        self.set_settings(data)
        self.history_selected()
        self.add_log(f'Settings saved to {self.config_path}')

    def load_settings(self):
        if self.busy:
            messagebox.showinfo('Load settings', 'Stop collection before loading connection and exposure settings.')
            return
        try:
            data = read_settings(self.config_path)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Load settings', str(exc))
            return
        self.set_settings(data)
        self.history_selected()
        self.add_log('Settings loaded. Click Connect / check link to apply a changed IP address.')

    def color_button(self, parent, variable):
        def foreground(color):
            r, g, b = to_rgb(color)
            return '#152030' if .2126*r + .7152*g + .0722*b > .55 else '#ffffff'
        button = tk.Button(parent, text=variable.get(), bg=variable.get(), fg=foreground(variable.get()), width=10)
        def refresh(*_):
            color = variable.get()
            button.configure(bg=color, text=color, fg=foreground(color))
        variable.trace_add('write', refresh)
        def choose():
            color = colorchooser.askcolor(variable.get(), parent=self, title='Choose plot color')[1]
            if color:
                variable.set(color)
                button.configure(bg=color, text=color, fg=foreground(color))
        button.configure(command=choose)
        return button

    def apply_visualization(self):
        try:
            limits = None
            if self.fixed_y.get():
                limits = (float(self.y_min.get()), float(self.y_max.get()))
                if not all(math.isfinite(v) for v in limits) or limits[0] >= limits[1]:
                    raise ValueError('Enter finite y-axis limits with minimum below maximum.')
            colors = [self.background_color.get(), self.mean_color.get(), *[v.get() for v in self.palette]]
            if not all(is_color_like(c) for c in colors):
                raise ValueError('Choose valid plot colors.')
        except ValueError as exc:
            messagebox.showerror('Visualization', str(exc))
            return
        self.plot_options = dict(mode=self.plot_mode.get(), ylim=limits, background=colors[0],
                                 mean=colors[1], palette=colors[2:])
        self.history_selected()

    def lsl_controls(self, parent, horizontal=False):
        ttk.Button(parent, text='Start LSL', command=self.start_lsl).pack(side='left', padx=3)
        ttk.Button(parent, text='Stop LSL', command=self.stop_lsl).pack(side='left', padx=3)

    def tree(self, parent, columns, labels, height):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=columns, show='headings', height=height, selectmode='extended')
        for col, label in zip(columns, labels):
            tree.heading(col, text=label)
            tree.column(col, width=85, minwidth=55, stretch=True)
        bar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        return tree

    def connect(self):
        if self.busy:
            return
        host = self.host.get().strip()
        if not host:
            messagebox.showerror('Connection', 'Enter an instrument IP address')
            return
        self.last_activity = None
        self.requested_host = host
        self.worker.commands.put(('connect', host))
        self.set_link('yellow', 'Connecting…')

    def disconnect(self):
        self.worker.cancel.set()
        self.worker.commands.put(('disconnect', None))
        self.stop_lsl()
        self.set_busy(False)
        self.set_link('red', 'Disconnected')

    def start(self, mode):
        if self.busy:
            return
        if self.host.get().strip() != self.requested_host:
            messagebox.showinfo('Connection', 'Click Connect / check link to apply the new IP address first.')
            return
        if self.link_color != 'green':
            messagebox.showinfo('Connection', 'Wait for a green connection indicator before collecting.')
            return
        try:
            exposure, repeats = float(self.exposure.get()), int(self.repeats.get())
            if not .0026 <= exposure <= 200 or not 1 <= repeats <= 250:
                raise ValueError('Exposure must be 0.0026–200 seconds; repeats 1–250')
        except ValueError as exc:
            messagebox.showerror('Settings', str(exc))
            return
        self.set_busy(True)
        self.worker.commands.put(('start', (mode, exposure, repeats)))

    def stop(self):
        self.worker.cancel.set()
        self.worker.commands.put(('stop', None))
        self.status.set('Stopping collection; link checks continue')

    def set_busy(self, busy):
        self.busy = busy
        for widget in self.acquire_buttons + self.setting_widgets:
            widget.configure(state='disabled' if busy else 'normal')
        if not busy:
            self.started = None

    def start_lsl(self):
        if self.publisher.enabled:
            return
        try:
            self.publisher.start()
            self.lsl_status.set('LSL ready — waiting for the next new measurement')
        except Exception as exc:
            messagebox.showerror('LSL', str(exc))

    def stop_lsl(self):
        self.publisher.stop()
        self.lsl_status.set('LSL stopped')

    def set_link(self, color, text):
        self.link_color = color
        self.light.itemconfigure(self.bulb, fill={'red':'#dc4444', 'green':'#2db56c', 'yellow':'#e4b72c'}[color])
        self.status.set(text)

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'link':
                    self.set_link(*value)
                    if value[0] != 'green':
                        self.add_log(value[1])
                elif kind == 'activity':
                    self.last_activity = value
                    self.set_link('green', 'Connected — receiving data' if self.busy else 'Connected — response received')
                elif kind == 'begin':
                    self.started = time.monotonic()
                    self.elapsed.set(f'Measuring: expected exposure {value:g} s')
                elif kind == 'measurement':
                    duration = time.monotonic()-self.started if self.started else 0
                    self.started = None
                    self.add_measurement(value)
                    self.elapsed.set(f'Last acquisition: {duration:.1f} seconds')
                    try:
                        if self.publisher.publish(value):
                            self.lsl_status.set(f'LSL active — {self.publisher.count} spectrum/CIE pairs published')
                    except Exception as exc:
                        self.stop_lsl()
                        self.lsl_status.set(f'LSL error: {exc}')
                        self.add_log(str(exc))
                elif kind == 'idle':
                    self.set_busy(False)
                elif kind == 'log':
                    self.add_log(value)
        except queue.Empty:
            pass
        if self.last_activity is not None:
            age = time.monotonic()-self.last_activity
            self.link_age.set(f'Last instrument response: {age:.1f} s ago')
            if age > 10 and self.link_color == 'green':
                self.set_link('yellow', 'No recent response — connection uncertain')
        if self.started:
            self.elapsed.set(f'Acquiring: {time.monotonic()-self.started:.1f} s elapsed')
        if self.closing and not self.worker.is_alive():
            self.destroy()
            return
        self.after(100, self.poll)

    @staticmethod
    def fmt(value):
        return f'{value:.6g}' if value is not None and math.isfinite(value) else 'N/A'

    def add_measurement(self, m, imported=False):
        if not imported:
            self.latest = m
        index = len(self.history)
        self.history.append(m)
        received = (time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(m.received_unix))
                    if m.received_unix is not None else f'LSL {m.received_at:.3f} s')
        self.history_tree.insert('', 'end', iid=str(index), values=(
            f'{index+1} · {received}'+(' [file]' if imported else ''),
            *(self.fmt(m.results.get(k)) for k in ('x2', 'y2', 'Y2'))))
        if imported:
            return
        self.details.set(f'Latest: {m.info.serial} | {len(m.values)} channels | '
                         f'battery {m.status.get("battery level", "?")}% | {len(self.history)} collected')
        self.add_log(f'Measurement {index+1} received: {len(m.values)} channels')
        if self.follow_latest:
            self.view_latest()
        else:
            self.selection_status.set(f'Browsing history — {len(self.history)} collected. Use “View the last” to follow live.')

    def pause_follow(self):
        self.follow_latest = False

    def view_latest(self):
        self.follow_latest = True
        if self.history:
            index = next((i for i in range(len(self.history)-1, -1, -1)
                          if self.history[i] is self.latest), len(self.history)-1)
            item = str(index)
            self.history_tree.selection_set(item)
            self.history_tree.see(item)
            self.history_selected()

    def selected(self):
        return [self.history[int(i)] for i in self.history_tree.selection()]

    def remove_selected(self):
        self.remove_measurements({int(i) for i in self.history_tree.selection()})

    def clear_measurements(self):
        self.remove_measurements(set(range(len(self.history))))

    def remove_measurements(self, indices):
        if not indices:
            return
        # Rebuild row IDs together with the list, keeping CSV/export indexing aligned.
        retained = [(m, self.history_tree.item(str(i), 'values'))
                    for i, m in enumerate(self.history) if i not in indices]
        self.history_tree.delete(*self.history_tree.get_children())
        self.history = [m for m, _ in retained]
        self.latest = None
        for i, (m, values) in enumerate(retained):
            label = values[0].split(' · ', 1)[-1]
            self.history_tree.insert('', 'end', iid=str(i), values=(f'{i+1} · {label}', *values[1:]))
            if not label.endswith(' [file]'):
                self.latest = m
        self.details.set(f'{len(self.history)} measurements in history')
        self.add_log(f'Removed {len(indices)} measurements from history; saved files are unchanged')
        if not self.history:
            self.follow_latest = True
            self.history_selected()
        elif self.follow_latest:
            self.view_latest()
        else:
            # Stay in browsing mode and show the closest surviving trial.
            item = str(min(min(indices), len(self.history)-1))
            self.history_tree.selection_set(item)
            self.history_tree.see(item)
            self.history_selected()

    def history_selected(self, event=None):
        measurements = self.selected()
        if not measurements:
            self.draw_empty('Select a measurement' if self.history else 'Waiting for measurements')
            self.values_tree.delete(*self.values_tree.get_children())
            self.cie_tree.delete(*self.cie_tree.get_children())
            self.swatch.configure(bg='#777777', text='N/A')
            self.color_text.set('CIE values unavailable')
            self.selection_status.set('No measurement selected' if self.history else 'Following latest measurement')
            return
        try:
            info, mean, sem = summarize(measurements)
        except ValueError as exc:
            self.selection_status.set(str(exc))
            self.draw_empty(str(exc))
            self.values_tree.delete(*self.values_tree.get_children())
            self.cie_tree.delete(*self.cie_tree.get_children())
            self.swatch.configure(bg='#777777', text='N/A')
            self.color_text.set('Incompatible selection')
            return
        count = len(measurements)
        overlay = self.plot_options['mode'] == 'overlay'
        self.selection_status.set(('Following latest. ' if self.follow_latest else 'History preview. ')+
                                  (f'{count} individual spectra; table shows mean/SEM' if overlay else
                                   f'Mean of {count} measurements ±1 SEM' if count > 1 else 'One measurement; SEM unavailable'))
        self.style_axes()
        x = info.wavelengths_nm
        if overlay:
            for item, m in zip(self.history_tree.selection(), measurements):
                index = int(item)
                self.axes.plot(m.info.wavelengths_nm, m.values, lw=1.6,
                               color=self.plot_options['palette'][index % len(self.palette)],
                               label=f'Trial {index+1}', zorder=3)
        else:
            if sem is not None:
                self.axes.fill_between(x, mean-sem, mean+sem, color=self.plot_options['mean'], alpha=.3, label='±1 SEM', zorder=2)
            self.axes.plot(x, mean, color=self.plot_options['mean'], lw=1.8, label=f'Mean (n={count})' if count > 1 else 'Spectrum', zorder=3)
        self.axes.set_ylabel(info.unit, color=self.plot_foreground)
        self.axes.set_title('Individual spectra' if overlay else 'Mean spectrum ± standard error' if count > 1 else 'Spectral measurement', color=self.plot_foreground)
        legend = self.axes.legend(facecolor=self.plot_options['background'], edgecolor='#65758b', fontsize=9)
        for text in legend.get_texts():
            text.set_color(self.plot_foreground)
        self.draw_wavelength_legend()
        self.canvas.draw_idle()
        self.values_tree.delete(*self.values_tree.get_children())
        for i, wavelength in enumerate(x):
            self.values_tree.insert('', 'end', values=(f'{wavelength:.3f}', f'{mean[i]:.6g}',
                                                       f'{sem[i]:.6g}' if sem is not None else 'N/A'))
        self.cie_tree.delete(*self.cie_tree.get_children())
        if count == 1:
            m = measurements[0]
            for key, label, unit in CIE_CHANNELS:
                self.cie_tree.insert('', 'end', values=(label, self.fmt(m.results.get(key))+' '+(unit or m.y_unit)))
        xyY = selection_xyY(measurements)
        if xyY is not None:
            x, y, Y = xyY
            color = xy_to_hex(x, y)
            self.swatch.configure(bg=color or '#777777', text='' if color else 'N/A')
            self.color_text.set(f'CIE 1931: x {x:.5f}   y {y:.5f}\nY {Y:.5g} {measurements[0].y_unit}'+
                                ('\nFrom mean XYZ of selection' if count > 1 else ''))
            if count > 1:
                for key, value in [('Mean XYZ → x', x), ('Mean XYZ → y', y), ('Mean Y', Y)]:
                    self.cie_tree.insert('', 'end', values=(key, f'{value:.6g}'))
        else:
            self.swatch.configure(bg='#777777', text='N/A')
            self.color_text.set('Color unavailable: missing or invalid CIE xyY')

    def draw_wavelength_legend(self):
        # Qualitative screen colors, not a colorimetric rendering of monochromatic light.
        anchors = np.array([380, 440, 490, 510, 550, 580, 610, 650, 780])
        colors = np.array([[85, 0, 150], [65, 40, 255], [0, 170, 255],
                           [0, 235, 190], [90, 230, 0], [255, 235, 0],
                           [255, 130, 0], [255, 30, 0], [130, 0, 0]]) / 255
        wavelength = np.linspace(380, 780, 801)
        gradient = np.stack([np.interp(wavelength, anchors, colors[:, c])
                             for c in range(3)], axis=1)[None, :, :]
        limits = self.axes.get_xlim()
        strip = self.axes.inset_axes([0, -.30, 1, .055], sharex=self.axes)
        strip.set_facecolor('#657080')
        strip.imshow(gradient, extent=(380, 780, 0, 1), aspect='auto', origin='lower')
        strip.set_xlim(limits)
        strip.set_ylim(0, 1)
        strip.tick_params(axis='both', which='both', bottom=False, top=False,
                          left=False, labelbottom=False, labelleft=False)
        for spine in strip.spines.values():
            spine.set_color('#9cabbc')
        strip.text(.5, -.65, 'Approximate wavelength colors · gray = outside visible range',
                   transform=strip.transAxes, ha='center', va='top', color=self.plot_foreground, fontsize=7)

    def style_axes(self):
        a = self.axes
        for child in list(a.child_axes):
            child.remove()
        a.clear()
        background = self.plot_options['background']
        r, g, b = to_rgb(background)
        self.plot_foreground = '#152030' if .2126*r + .7152*g + .0722*b > .55 else '#e7edf4'
        self.figure.set_facecolor(background)
        a.set_facecolor(background)
        a.tick_params(axis='both', which='both', colors=self.plot_foreground, labelsize=9)
        for spine in a.spines.values():
            spine.set_color('#9cabbc')
        a.set_xlabel('Wavelength (nm)', color=self.plot_foreground)
        a.set_ylabel('Spectral value', color=self.plot_foreground)
        if self.plot_options['ylim'] is not None:
            a.set_ylim(self.plot_options['ylim'])
        a.xaxis.set_minor_locator(AutoMinorLocator(2))
        a.yaxis.set_minor_locator(AutoMinorLocator(2))
        a.set_axisbelow(True)
        a.grid(True, which='major', color=self.plot_foreground, alpha=.35, linewidth=.7)
        a.grid(True, which='minor', color=self.plot_foreground, alpha=.15, linewidth=.5)

    def draw_empty(self, text='Waiting for measurements'):
        self.style_axes()
        self.axes.text(.5,.5,text,transform=self.axes.transAxes,ha='center',va='center',color=self.plot_foreground,wrap=True)
        self.canvas.draw_idle()

    def export(self):
        measurements = self.selected()
        if not measurements:
            messagebox.showinfo('Export', 'Select at least one measurement')
            return
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV','*.csv')])
        if not path:
            return
        try:
            save_measurements(path, measurements)
            self.add_log(f'Exported {len(measurements)} separate trials to {path}')
        except (OSError, ValueError) as exc:
            messagebox.showerror('Export failed', str(exc))

    def open_csv(self):
        path = filedialog.askopenfilename(filetypes=[('CSV', '*.csv')])
        if not path:
            return
        try:
            measurements = load_measurements(path)
        except (OSError, ValueError, csv.Error) as exc:
            messagebox.showerror('Open CSV failed', str(exc))
            return
        self.pause_follow()
        first = len(self.history)
        for m in measurements:
            self.add_measurement(m, imported=True)
        self.history_tree.selection_set(*(str(i) for i in range(first, len(self.history))))
        self.history_tree.see(str(first))
        self.history_selected()
        self.add_log(f'Opened {len(measurements)} saved trials from {path}; no LSL replay')

    def add_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', time.strftime('%H:%M:%S')+'  '+text+'\n')
        if int(self.log.index('end-1c').split('.')[0]) > 300:
            self.log.delete('1.0','50.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def close_window(self):
        self.closing = True
        self.publisher.stop()
        self.worker.cancel.set()
        self.worker.shutdown.set()
        self.status.set('Closing…')


if __name__ == '__main__':
    Monitor().mainloop()
