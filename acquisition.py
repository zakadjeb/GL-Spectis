"""One persistent socket owns heartbeat and acquisition; never probes in parallel."""
import queue
import threading
import time
from spectis import Spectis


class Acquisition(threading.Thread):
    def __init__(self, events, device_factory=Spectis, check_interval=5, retry_interval=5):
        super().__init__(daemon=True)
        self.events = events
        self.commands = queue.Queue()
        self.cancel = threading.Event()
        self.shutdown = threading.Event()
        self.device_factory = device_factory
        self.check_interval = check_interval
        self.retry_interval = retry_interval

    def emit(self, kind, value):
        self.events.put((kind, value))

    def run(self):
        device = None
        host = None
        mode = None
        exposure, repeats = 10, 3
        next_check = 0
        while not self.shutdown.is_set():
            try:
                while True:
                    command, value = self.commands.get_nowait()
                    if command == 'connect':
                        if device:
                            device.close()
                        device, host, mode = None, value, None
                        self.emit('idle', None)
                        self.cancel.clear()
                        next_check = 0
                    elif command == 'disconnect':
                        host, mode = None, None
                        if device:
                            device.close()
                        device = None
                        self.cancel.clear()
                        self.emit('link', ('red', 'Disconnected'))
                        self.emit('idle', None)
                    elif command == 'start':
                        mode, exposure, repeats = value
                        self.cancel.clear()
                    elif command == 'stop':
                        mode = None
                        self.cancel.clear()
                        self.emit('idle', None)
            except queue.Empty:
                pass
            try:
                if host and device is None and time.monotonic() >= next_check:
                    self.emit('link', ('yellow', 'Connecting…'))
                    device = self.device_factory(host, on_activity=lambda t: self.emit('activity', t))
                    device.connect()
                    self.emit('link', ('green', f'Connected to {host} — configuration verified'))
                    next_check = time.monotonic()+self.check_interval
                if device and mode:
                    self.emit('begin', exposure*repeats)
                    result = device.measure(exposure, repeats, self.cancel)
                    if not self.cancel.is_set():
                        self.emit('measurement', result)
                    if mode == 'once':
                        mode = None
                        self.emit('idle', None)
                    next_check = time.monotonic()+self.check_interval
                elif device and time.monotonic() >= next_check:
                    device.check(self.cancel)
                    self.emit('link', ('green', 'Connected — heartbeat verified'))
                    next_check = time.monotonic()+self.check_interval
            except InterruptedError:
                mode = None
                if device:
                    device.close()
                device = None
                self.emit('idle', None)
                self.emit('link', ('yellow', 'Stopped; reconnecting for link checks'))
                next_check = time.monotonic()+2
            except Exception as exc:
                if device:
                    device.close()
                device = None
                mode = None
                self.emit('idle', None)
                self.emit('link', ('yellow', f'Link / acquisition error: {exc}; retrying link in 5 s'))
                self.emit('log', str(exc))
                next_check = time.monotonic()+self.retry_interval
            self.shutdown.wait(.1)
        if device:
            device.close()
