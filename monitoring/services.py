"""Coleta avançada de métricas do servidor via psutil + hardware (Windows/Linux)."""

from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache

import django
import psutil

# Cache para calcular velocidade de leitura/escrita do disco
_io_prev: dict | None = None
_io_prev_ts: float | None = None
_hw_cache: dict | None = None
_hw_cache_ts: float = 0
_HW_TTL = 300  # segundos

MEMORY_TYPE_MAP = {
    0: 'Desconhecido',
    1: 'Other',
    2: 'DRAM',
    17: 'SDRAM',
    20: 'DDR',
    21: 'DDR2',
    22: 'DDR2 FB-DIMM',
    24: 'DDR3',
    26: 'DDR4',
    34: 'DDR5',
}


def _bytes_human(n: float) -> str:
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


def _bytes_per_sec_human(n: float) -> str:
    return f'{_bytes_human(n)}/s'


def _run_cmd(cmd: list[str], timeout: int = 8) -> str:
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=flags,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ''


def _powershell_json(script: str) -> list | dict | None:
    if platform.system() != 'Windows':
        return None
    wrapped = f'@({script}) | ConvertTo-Json -Compress'
    out = _run_cmd(['powershell', '-NoProfile', '-Command', wrapped])
    if not out:
        return None
    try:
        import json
        data = json.loads(out)
        if isinstance(data, dict):
            return [data]
        return data
    except Exception:
        return None


def _collect_cpu_hardware() -> dict:
    info = {
        'brand': platform.processor() or platform.machine(),
        'arch': platform.machine(),
        'physical_cores': psutil.cpu_count(logical=False) or 0,
        'logical_cores': psutil.cpu_count(logical=True) or 0,
        'threads': psutil.cpu_count(logical=True) or 0,
        'max_freq_mhz': None,
        'current_freq_mhz': None,
    }

    if platform.system() == 'Windows':
        rows = _powershell_json(
            'Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, '
            'NumberOfLogicalProcessors, MaxClockSpeed, CurrentClockSpeed, ThreadCount'
        )
        if rows and rows[0]:
            row = rows[0]
            info['brand'] = (row.get('Name') or info['brand']).strip()
            info['physical_cores'] = int(row.get('NumberOfCores') or info['physical_cores'])
            info['logical_cores'] = int(row.get('NumberOfLogicalProcessors') or info['logical_cores'])
            info['threads'] = int(row.get('ThreadCount') or info['logical_cores'])
            if row.get('MaxClockSpeed'):
                info['max_freq_mhz'] = int(row['MaxClockSpeed'])
            if row.get('CurrentClockSpeed'):
                info['current_freq_mhz'] = int(row['CurrentClockSpeed'])
    else:
        try:
            with open('/proc/cpuinfo', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.lower().startswith('model name'):
                        info['brand'] = line.split(':', 1)[1].strip()
                        break
        except OSError:
            pass

    freq = psutil.cpu_freq()
    if freq:
        info['current_freq_mhz'] = info['current_freq_mhz'] or round(freq.current, 0)
        info['max_freq_mhz'] = info['max_freq_mhz'] or round(freq.max, 0)

    return info


def _collect_ram_modules() -> list[dict]:
    modules: list[dict] = []

    if platform.system() == 'Windows':
        rows = _powershell_json(
            'Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed, '
            'ConfiguredClockSpeed, MemoryType, Manufacturer, PartNumber, SMBIOSMemoryType'
        )
        if rows:
            for row in rows:
                cap = int(row.get('Capacity') or 0)
                mem_type_code = int(row.get('SMBIOSMemoryType') or row.get('MemoryType') or 0)
                speed = int(row.get('ConfiguredClockSpeed') or row.get('Speed') or 0)
                modules.append({
                    'capacity_h': _bytes_human(cap),
                    'capacity_bytes': cap,
                    'speed_mhz': speed,
                    'type': MEMORY_TYPE_MAP.get(mem_type_code, f'Tipo {mem_type_code}' if mem_type_code else 'Desconhecido'),
                    'manufacturer': (row.get('Manufacturer') or '').strip() or '—',
                    'part_number': (row.get('PartNumber') or '').strip() or '—',
                })
    else:
        # Linux — tenta dmidecode (pode falhar sem root)
        out = _run_cmd(['dmidecode', '-t', 'memory'], timeout=10)
        if out and 'Permission denied' not in out:
            blocks = re.split(r'\nHandle ', out)
            for block in blocks:
                if 'Memory Device' not in block:
                    continue
                size_m = re.search(r'Size:\s*(\d+)\s*MB', block)
                if not size_m or 'No Module Installed' in block:
                    continue
                speed_m = re.search(r'Speed:\s*(\d+)\s*MT/s', block) or re.search(r'Configured Memory Speed:\s*(\d+)\s*MT/s', block)
                type_m = re.search(r'Type:\s*(DDR\S+)', block)
                cap = int(size_m.group(1)) * 1024 * 1024
                modules.append({
                    'capacity_h': _bytes_human(cap),
                    'capacity_bytes': cap,
                    'speed_mhz': int(speed_m.group(1)) if speed_m else 0,
                    'type': type_m.group(1) if type_m else 'Desconhecido',
                    'manufacturer': '—',
                    'part_number': '—',
                })

    return modules


def _collect_storage_hardware() -> list[dict]:
    drives: list[dict] = []

    if platform.system() == 'Windows':
        rows = _powershell_json(
            'Get-CimInstance Win32_DiskDrive | Select-Object Model, Size, MediaType, InterfaceType'
        )
        if rows:
            for row in rows:
                size = int(row.get('Size') or 0)
                drives.append({
                    'model': (row.get('Model') or 'Disco').strip(),
                    'size_h': _bytes_human(size) if size else '—',
                    'media_type': (row.get('MediaType') or row.get('InterfaceType') or '—').strip(),
                    'interface': (row.get('InterfaceType') or '—').strip(),
                })

    return drives


def get_hardware_info() -> dict:
    global _hw_cache, _hw_cache_ts
    now = time.time()
    if _hw_cache and (now - _hw_cache_ts) < _HW_TTL:
        return _hw_cache

    cpu = _collect_cpu_hardware()
    ram_modules = _collect_ram_modules()
    storage_devices = _collect_storage_hardware()

    total_ram_modules = sum(m.get('capacity_bytes', 0) for m in ram_modules)
    ram_types = sorted({m['type'] for m in ram_modules if m.get('type')})
    ram_speeds = sorted({m['speed_mhz'] for m in ram_modules if m.get('speed_mhz')})

    _hw_cache = {
        'cpu': cpu,
        'ram_modules': ram_modules,
        'ram_summary': {
            'total_from_modules_h': _bytes_human(total_ram_modules) if total_ram_modules else None,
            'types': ram_types,
            'speeds_mhz': ram_speeds,
            'slots_used': len(ram_modules),
        },
        'storage_devices': storage_devices,
    }
    _hw_cache_ts = now
    return _hw_cache


def _disk_io_rates() -> tuple[list[dict], dict]:
    global _io_prev, _io_prev_ts
    now = time.time()
    rates: list[dict] = []
    totals = {'read_bytes_per_sec': 0, 'write_bytes_per_sec': 0}

    try:
        counters = psutil.disk_io_counters(perdisk=True)
    except Exception:
        counters = None

    if not counters:
        try:
            c = psutil.disk_io_counters()
            if c:
                counters = {'TOTAL': c}
        except Exception:
            counters = {}

    if _io_prev and _io_prev_ts and counters:
        dt = max(now - _io_prev_ts, 0.001)
        for name, cur in counters.items():
            prev = _io_prev.get(name)
            if not prev:
                continue
            read_bps = max(0, (cur.read_bytes - prev.read_bytes) / dt)
            write_bps = max(0, (cur.write_bytes - prev.write_bytes) / dt)
            rates.append({
                'disk': name,
                'read_bps': read_bps,
                'write_bps': write_bps,
                'read_h': _bytes_per_sec_human(read_bps),
                'write_h': _bytes_per_sec_human(write_bps),
                'read_total_h': _bytes_human(cur.read_bytes),
                'write_total_h': _bytes_human(cur.write_bytes),
            })
            totals['read_bytes_per_sec'] += read_bps
            totals['write_bytes_per_sec'] += write_bps

    _io_prev = counters
    _io_prev_ts = now

    totals['read_h'] = _bytes_per_sec_human(totals['read_bytes_per_sec'])
    totals['write_h'] = _bytes_per_sec_human(totals['write_bytes_per_sec'])
    return rates, totals


def _top_processes(limit: int = 12) -> dict:
    psutil.cpu_percent(interval=0.2)
    procs: list[dict] = []

    for p in psutil.process_iter(['pid', 'name', 'username', 'memory_info']):
        try:
            mem = p.info.get('memory_info')
            rss = mem.rss if mem else 0
            io = None
            try:
                io = p.io_counters()
            except (psutil.Error, AttributeError):
                pass

            procs.append({
                'pid': p.info['pid'],
                'name': p.info.get('name') or '—',
                'user': (p.info.get('username') or '—').split('\\')[-1],
                'memory_bytes': rss,
                'memory_h': _bytes_human(rss),
                'memory_mb': round(rss / (1024 * 1024), 1),
                'cpu_percent': round(p.cpu_percent(interval=0), 1),
                'read_bytes': io.read_bytes if io else 0,
                'write_bytes': io.write_bytes if io else 0,
                'read_h': _bytes_human(io.read_bytes) if io else '—',
                'write_h': _bytes_human(io.write_bytes) if io else '—',
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    by_memory = sorted(procs, key=lambda x: x['memory_bytes'], reverse=True)[:limit]
    by_cpu = sorted(procs, key=lambda x: x['cpu_percent'], reverse=True)[:limit]
    by_disk = sorted(
        [p for p in procs if p['read_bytes'] + p['write_bytes'] > 0],
        key=lambda x: x['read_bytes'] + x['write_bytes'],
        reverse=True,
    )[:limit]

    return {
        'by_memory': by_memory,
        'by_cpu': by_cpu,
        'by_disk': by_disk,
        'total': len(procs),
    }


def collect_metrics() -> dict:
    boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    now = datetime.now(timezone.utc)
    uptime_seconds = int((now - boot).total_seconds())

    cpu_freq = psutil.cpu_freq()
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    per_cpu = psutil.cpu_percent(interval=0.3, percpu=True)

    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                'device': part.device,
                'mountpoint': part.mountpoint,
                'fstype': part.fstype,
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent': usage.percent,
                'total_h': _bytes_human(usage.total),
                'used_h': _bytes_human(usage.used),
                'free_h': _bytes_human(usage.free),
            })
        except (PermissionError, OSError):
            continue

    net = psutil.net_io_counters()
    net_if = []
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, addr_list in addrs.items():
            st = stats.get(name)
            net_if.append({
                'name': name,
                'is_up': st.isup if st else False,
                'speed_mbps': st.speed if st else 0,
                'addresses': [
                    {'family': str(a.family), 'address': a.address}
                    for a in addr_list if a.address
                ],
            })
    except Exception:
        pass

    proc = psutil.Process(os.getpid())
    hardware = get_hardware_info()
    disk_io_rates, disk_io_totals = _disk_io_rates()
    top_procs = _top_processes()

    return {
        'timestamp': now.isoformat(),
        'system': {
            'hostname': platform.node(),
            'os': platform.system(),
            'os_release': platform.release(),
            'os_version': platform.version(),
            'machine': platform.machine(),
            'processor': hardware['cpu']['brand'],
            'python_version': sys.version.split()[0],
            'django_version': django.get_version(),
            'boot_time': boot.isoformat(),
            'uptime_seconds': uptime_seconds,
            'uptime_h': f'{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m',
        },
        'hardware': hardware,
        'cpu': {
            'percent': round(sum(per_cpu) / len(per_cpu), 1) if per_cpu else psutil.cpu_percent(interval=0),
            'per_core': [round(p, 1) for p in per_cpu],
            'count_logical': hardware['cpu']['logical_cores'],
            'count_physical': hardware['cpu']['physical_cores'],
            'threads': hardware['cpu']['threads'],
            'brand': hardware['cpu']['brand'],
            'freq_mhz': hardware['cpu'].get('current_freq_mhz') or (round(cpu_freq.current, 1) if cpu_freq else None),
            'freq_max_mhz': hardware['cpu'].get('max_freq_mhz') or (round(cpu_freq.max, 1) if cpu_freq else None),
            'load_avg': list(os.getloadavg()) if hasattr(os, 'getloadavg') else None,
        },
        'memory': {
            'total': vm.total,
            'available': vm.available,
            'used': vm.used,
            'percent': vm.percent,
            'total_h': _bytes_human(vm.total),
            'used_h': _bytes_human(vm.used),
            'available_h': _bytes_human(vm.available),
            'swap_total_h': _bytes_human(swap.total),
            'swap_used_h': _bytes_human(swap.used),
            'swap_percent': swap.percent,
            'modules': hardware['ram_modules'],
            'summary': hardware['ram_summary'],
        },
        'disks': disks,
        'disk_io': {
            'per_disk': disk_io_rates,
            'totals': disk_io_totals,
        },
        'network': {
            'bytes_sent': net.bytes_sent,
            'bytes_recv': net.bytes_recv,
            'packets_sent': net.packets_sent,
            'packets_recv': net.packets_recv,
            'bytes_sent_h': _bytes_human(net.bytes_sent),
            'bytes_recv_h': _bytes_human(net.bytes_recv),
            'interfaces': net_if,
        },
        'processes': top_procs,
        'process': {
            'pid': proc.pid,
            'name': proc.name(),
            'threads': proc.num_threads(),
            'memory_rss_h': _bytes_human(proc.memory_info().rss),
            'cpu_percent': round(proc.cpu_percent(interval=0.1), 1),
        },
    }
