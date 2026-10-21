"""Tkinter monitor: persistent link checks, history, mean/SEM and spectral + CIE LSL."""
import csv
import math
import queue
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import AutoMinorLocator
from acquisition import Acquisition
from analysis_tools import CIE_CHANNELS, summarize, selection_xyY, xy_to_hex
from streaming import Publisher


class Monitor(tk.Tk):
    def __init__(self, auto_connect=True):
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
        self._build()
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
        self.figure.subplots_adjust(left=.14, right=.96, bottom=.18, top=.88)
        self.canvas = FigureCanvasTkAgg(self.figure, master=left)
        ttk.Label(left, text='Color preview: normalized sRGB approximation; not calibrated brightness.',
                  wraplength=600).pack(side='bottom', anchor='w')
        color_row = ttk.Frame(left)
        color_row.pack(side='bottom', fill='x', pady=10)
        self.swatch = tk.Label(color_row, width=10, height=3, background='#777777', text='N/A')
        self.swatch.pack(side='left', padx=(0, 12))
        ttk.Label(color_row, textvariable=self.color_text, justify='left').pack(side='left')
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        ttk.Label(right, text='Collected measurements — Ctrl/Shift-select to average',
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
            'Selection/averaging affects the preview and export only, never LSL.\n\n'
            'Stopping may leave an exposure running on the instrument. Wait for completion\n'
            'before restarting. History is kept for this session; export before closing.'
        )).grid(row=5, column=0, columnspan=2, sticky='w', pady=16)
        self.draw_empty()

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

    def add_measurement(self, m):
        self.latest = m
        index = len(self.history)
        self.history.append(m)
        self.history_tree.insert('', 'end', iid=str(index), values=(
            f'{index+1} · {time.strftime("%H:%M:%S")}',
            *(self.fmt(m.results.get(k)) for k in ('x2', 'y2', 'Y2'))))
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
            item = str(len(self.history)-1)
            self.history_tree.selection_set(item)
            self.history_tree.see(item)
            self.history_selected()

    def selected(self):
        return [self.history[int(i)] for i in self.history_tree.selection()]

    def history_selected(self, event=None):
        measurements = self.selected()
        if not measurements:
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
        self.selection_status.set(('Following latest. ' if self.follow_latest else 'History preview. ')+
                                  (f'Mean of {count} measurements ±1 SEM' if count > 1 else 'One measurement; SEM unavailable'))
        self.style_axes()
        x = info.wavelengths_nm
        if sem is not None:
            self.axes.fill_between(x, mean-sem, mean+sem, color='#9dcec9', alpha=.3, label='±1 SEM', zorder=2)
        self.axes.plot(x, mean, color='#5de0be', lw=1.8, label=f'Mean (n={count})' if count > 1 else 'Spectrum', zorder=3)
        self.axes.set_ylabel(info.unit, color='white')
        self.axes.set_title('Mean spectrum ± standard error' if count > 1 else 'Spectral measurement', color='white')
        legend = self.axes.legend(facecolor='#18283d', edgecolor='#65758b', fontsize=9)
        for text in legend.get_texts():
            text.set_color('white')
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

    def style_axes(self):
        a = self.axes
        a.clear()
        a.set_facecolor('#101b2c')
        a.tick_params(axis='both', which='both', colors='#e7edf4', labelsize=9)
        for spine in a.spines.values():
            spine.set_color('#9cabbc')
        a.set_xlabel('Wavelength (nm)', color='white')
        a.set_ylabel('Spectral value', color='white')
        a.xaxis.set_minor_locator(AutoMinorLocator(2))
        a.yaxis.set_minor_locator(AutoMinorLocator(2))
        a.set_axisbelow(True)
        a.grid(True, which='major', color='#d1d8e2', alpha=.35, linewidth=.7)
        a.grid(True, which='minor', color='#b4bfce', alpha=.15, linewidth=.5)

    def draw_empty(self, text='Waiting for measurements'):
        self.style_axes()
        self.axes.text(.5,.5,text,transform=self.axes.transAxes,ha='center',va='center',color='white',wrap=True)
        self.canvas.draw_idle()

    def export(self):
        measurements = self.selected()
        try:
            info, mean, sem = summarize(measurements)
        except ValueError as exc:
            messagebox.showinfo('Export', str(exc))
            return
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV','*.csv')])
        if not path:
            return
        try:
            with open(path,'w',newline='',encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(['wavelength_nm',f'mean_{info.unit}',f'SEM_{info.unit}','n'])
                for i,w in enumerate(info.wavelengths_nm):
                    writer.writerow([w,mean[i],sem[i] if sem is not None else '',len(measurements)])
        except OSError as exc:
            messagebox.showerror('Export failed', str(exc))

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
