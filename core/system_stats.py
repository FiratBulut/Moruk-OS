#!/usr/bin/env python3
"""
System Stats: CPU & RAM Auslastung auslesen
Kann als Tool für Autonomy-Drosselung genutzt werden
"""

import os

def get_cpu_usage():
    """Liest CPU-Auslastung aus /proc/stat"""
    try:
        with open('/proc/stat', 'r') as f:
            line = f.readline()
            # cpu  user nice system idle iowait irq softirq steal guest guest_nice
            fields = line.split()
            # Summiere alle except idle
            total = sum(int(x) for x in fields[1:])
            idle = int(fields[4])
            # Einfacher Durchschnitt seit Systemstart
            return round(100 * (total - idle) / total, 1)
    except Exception:
        return -1

def get_ram_usage():
    """Liest RAM-Nutzung aus /proc/meminfo"""
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        
        mem_total = mem_available = 0
        
        for line in lines:
            if line.startswith('MemTotal:'):
                mem_total = int(line.split()[1]) * 1024  # KB -> Bytes
            elif line.startswith('MemAvailable:'):
                mem_available = int(line.split()[1]) * 1024
        
        # Verwendeter RAM = Total - Available (inkl. Buffers/Cache)
        # Real used: Total - Available (Linux gibt "available" inkl. Cache frei)
        mem_used = mem_total - mem_available
        
        percent = round(100 * mem_used / mem_total, 1) if mem_total > 0 else 0
        
        return {
            'percent': percent,
            'used_gb': round(mem_used / (1024**3), 2),
            'total_gb': round(mem_total / (1024**3), 2)
        }
    except Exception:
        return {'percent': -1, 'used_gb': 0, 'total_gb': 0}

def get_system_stats():
    """Gibt dict mit CPU und RAM zurück"""
    return {
        'cpu_percent': get_cpu_usage(),
        'ram': get_ram_usage()
    }

def get_load_average():
    """Liest Load Average (1, 5, 15 min)"""
    try:
        load1, load5, load15 = os.getloadavg()
        return {
            'load_1min': round(load1, 2),
            'load_5min': round(load5, 2),
            'load_15min': round(load15, 2)
        }
    except Exception:
        return {'load_1min': -1, 'load_5min': -1, 'load_15min': -1}

if __name__ == '__main__':
    import json
    stats = get_system_stats()
    stats['load'] = get_load_average()
    print(json.dumps(stats, indent=2))
