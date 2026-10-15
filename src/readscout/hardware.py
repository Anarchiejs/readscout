"""Detect GPU memory and RAM, and recommend models from catalog.json.

Detection is best effort and always overridable in the setup page (VRAM 6-24 GB, RAM 16-64 GB).
"""
import ctypes
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass

from .paths import PACKAGE

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
DEFAULT_CTX = 32768


@dataclass
class Hardware:
    vram_gb: float
    ram_gb: float
    gpu: str
    source: str          # how VRAM was found: nvidia-smi, rocm-smi, apple-unified, registry, none
    os: str


def _run(cmd, timeout=10) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return ''


def ram_gb() -> float:
    if sys.platform == 'win32':
        class MemStatus(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong), ('ullTotalPhys', ctypes.c_ulonglong),
                        ('ullAvailPhys', ctypes.c_ulonglong), ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong), ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
        st = MemStatus()
        st.dwLength = ctypes.sizeof(MemStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullTotalPhys / 2**30
    if sys.platform == 'darwin':
        out = _run(['sysctl', '-n', 'hw.memsize'])
        return int(out.strip() or 0) / 2**30
    try:
        with open('/proc/meminfo') as f:
            kb = int(re.search(r'MemTotal:\s+(\d+)', f.read())[1])
        return kb / 2**20
    except (OSError, TypeError):
        return 0.0


def _windows_registry_vram() -> tuple[float, str]:
    """Works for AMD/Intel too, unlike WMI AdapterRAM which caps at 4 GB."""
    import winreg
    best, name = 0.0, ''
    base = r'SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                sub = winreg.EnumKey(k, i)
                try:
                    with winreg.OpenKey(k, sub) as d:
                        size = winreg.QueryValueEx(d, 'HardwareInformation.qwMemorySize')[0]
                        desc = winreg.QueryValueEx(d, 'DriverDesc')[0]
                        if size / 2**30 > best:
                            best, name = size / 2**30, desc
                except OSError:
                    continue
    except OSError:
        pass
    return best, name


def detect() -> Hardware:
    ram = ram_gb()
    os_name = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux')
    if shutil.which('nvidia-smi'):
        out = _run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'])
        rows = [r.rsplit(',', 1) for r in out.strip().splitlines() if ',' in r]
        if rows:
            return Hardware(round(sum(float(m) for _, m in rows) / 1024, 1), round(ram, 1), ', '.join(n.strip() for n, _ in rows), 'nvidia-smi', os_name)
    if shutil.which('rocm-smi'):
        out = _run(['rocm-smi', '--showmeminfo', 'vram', '--json'])
        try:
            cards = json.loads(out)
            total = sum(int(v.get('VRAM Total Memory (B)', 0)) for v in cards.values())
            if total:
                return Hardware(round(total / 2**30, 1), round(ram, 1), 'AMD GPU', 'rocm-smi', os_name)
        except (ValueError, AttributeError):
            pass
    if sys.platform == 'darwin' and _run(['uname', '-m']).strip() == 'arm64':
        # Apple silicon: the GPU can use about two thirds of the unified memory by default.
        return Hardware(round(ram * 0.66, 1), round(ram, 1), 'Apple silicon (unified memory)', 'apple-unified', os_name)
    if sys.platform == 'win32':
        vram, name = _windows_registry_vram()
        if vram:
            return Hardware(round(vram, 1), round(ram, 1), name, 'registry', os_name)
    return Hardware(0.0, round(ram, 1), 'no GPU detected', 'none', os_name)


def catalog() -> dict:
    return json.loads((PACKAGE / 'catalog.json').read_text(encoding='utf-8'))


def recommend(vram_gb: float, ram_gb: float) -> dict:
    """Pick the fast and quality models whose memory rules fit this machine (first match wins)."""
    cat = catalog()
    picks = {}
    for tier in ('fast', 'quality'):
        for rule in cat['tiers'][tier]:
            if vram_gb >= rule.get('min_vram_gb', 0) and ram_gb >= rule.get('min_ram_gb', 0) \
                    and vram_gb + ram_gb >= rule.get('min_total_gb', 0):
                picks[tier] = {**cat['models'][rule['model']], 'model': rule['model'], 'why': rule['why'], 'ctx': rule.get('ctx', DEFAULT_CTX)}
                break
    if 'quality' not in picks and 'fast' in picks:
        picks['quality'] = {**picks['fast'], 'why': 'Not enough memory for a bigger model: the fast model is used for both tiers.'}
    return picks


def models_config(rec: dict) -> dict:
    """The `models` section of the config for a recommendation: model name and context size per tier."""
    return {tier: {'name': r['model'], 'ctx': r.get('ctx', DEFAULT_CTX)} for tier, r in rec.items()}


def ensure_config() -> None:
    """First run: write a config whose models fit this machine, instead of generic defaults."""
    from . import paths
    if paths.config_file().exists():
        return
    cfg = paths.load_config()
    hw = detect()
    rec = recommend(hw.vram_gb, hw.ram_gb)
    cfg['models'] = models_config(rec)
    paths.save_config(cfg)


def as_dict(hw: Hardware) -> dict:
    return asdict(hw)
