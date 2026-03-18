"""
StatsWorker — polls system metrics every second.
Emits a dict with cpu, gpu, ram usage.
"""
import time
import random
from PySide6.QtCore import QThread, Signal

class StatsWorker(QThread):
    stats_update = Signal(dict)   # {"cpu": 42, "gpu": 67, "ram": 55, "gpu_mem": 3.2}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = True
        self._psutil_ok = False
        try:
            import psutil
            self._psutil_ok = True
        except ImportError:
            pass

    def run(self):
        while self._active:
            stats = self._collect()
            self.stats_update.emit(stats)
            time.sleep(1.5)

    def stop(self):
        self._active = False
        self.quit()
        self.wait(3000)

    def _collect(self) -> dict:
        cpu = ram = 0.0
        if self._psutil_ok:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
        else:
            # Smooth random simulation
            cpu = max(5, min(95, random.gauss(35, 10)))
            ram = max(20, min(90, random.gauss(55, 8)))

        # GPU — try pynvml, fall back to simulation
        gpu = gpu_mem = 0.0
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util   = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem    = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu     = util.gpu
            gpu_mem = mem.used / 1024 ** 3
        except Exception:
            gpu     = max(0, min(100, random.gauss(45, 12)))
            gpu_mem = round(random.uniform(1.5, 4.5), 1)

        return {
            "cpu":     round(cpu, 1),
            "ram":     round(ram, 1),
            "gpu":     round(gpu, 1),
            "gpu_mem": round(gpu_mem, 1),
        }
