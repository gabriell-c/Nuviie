"""Coleta de métricas do servidor via psutil."""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone

import django
import psutil


def _bytes_human(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


def collect_metrics() -> dict:
    boot = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    now = datetime.now(timezone.utc)
    uptime_seconds = int((now - boot).total_seconds())

    cpu_freq = psutil.cpu_freq()
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()

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

    return {
        'timestamp': now.isoformat(),
        'system': {
            'hostname': platform.node(),
            'os': platform.system(),
            'os_release': platform.release(),
            'os_version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor() or platform.machine(),
            'python_version': sys.version.split()[0],
            'django_version': django.get_version(),
            'boot_time': boot.isoformat(),
            'uptime_seconds': uptime_seconds,
            'uptime_h': f'{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m',
        },
        'cpu': {
            'percent': psutil.cpu_percent(interval=0.5),
            'count_logical': psutil.cpu_count(logical=True),
            'count_physical': psutil.cpu_count(logical=False),
            'freq_mhz': round(cpu_freq.current, 1) if cpu_freq else None,
            'freq_max_mhz': round(cpu_freq.max, 1) if cpu_freq else None,
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
        },
        'disks': disks,
        'network': {
            'bytes_sent': net.bytes_sent,
            'bytes_recv': net.bytes_recv,
            'packets_sent': net.packets_sent,
            'packets_recv': net.packets_recv,
            'bytes_sent_h': _bytes_human(net.bytes_sent),
            'bytes_recv_h': _bytes_human(net.bytes_recv),
            'interfaces': net_if,
        },
        'process': {
            'pid': proc.pid,
            'threads': proc.num_threads(),
            'memory_rss_h': _bytes_human(proc.memory_info().rss),
            'cpu_percent': proc.cpu_percent(interval=0.1),
        },
    }
