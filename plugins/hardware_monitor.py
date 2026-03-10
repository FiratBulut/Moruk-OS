PLUGIN_CORE = True
PLUGIN_NAME = "hardware_monitor"
PLUGIN_DESCRIPTION = "Hardware monitoring: CPU temp, fan speeds, clock speeds, RAM. Uses lm-sensors + /proc."
PLUGIN_PARAMS = {"detail": "brief|full (default: brief)"}

import subprocess
import re


def _run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def execute(params):
    detail = params.get("detail", "brief")
    lines = ["Hardware Monitor", "-" * 40]

    cpu_model = _run("grep 'model name' /proc/cpuinfo | head -1 | cut -d: -f2").strip()
    cores = _run("nproc")
    if cpu_model:
        lines.append(f"CPU: {cpu_model} ({cores} cores)")

    freqs_raw = _run("grep 'cpu MHz' /proc/cpuinfo | awk '{print $4}'")
    if freqs_raw:
        freqs = [float(x) for x in freqs_raw.splitlines() if x]
        if freqs:
            avg = sum(freqs) / len(freqs) / 1000
            mx = max(freqs) / 1000
            lines.append(f"Clock: avg {avg:.2f} GHz / max {mx:.2f} GHz")

    load = _run("cat /proc/loadavg")
    if load:
        p = load.split()
        lines.append(f"Load: {p[0]} / {p[1]} / {p[2]} (1/5/15 min)")

    meminfo = _run("cat /proc/meminfo")
    mem_total = mem_avail = 0
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            mem_total = int(line.split()[1])
        elif line.startswith("MemAvailable:"):
            mem_avail = int(line.split()[1])
    if mem_total:
        used = (mem_total - mem_avail) / 1024 / 1024
        total = mem_total / 1024 / 1024
        lines.append(f"RAM: {used:.1f} GB used / {total:.1f} GB total")

    sensors = _run("sensors 2>/dev/null")
    if sensors:
        lines.append("\nTemperatures (lm-sensors):")
        for line in sensors.splitlines():
            ll = line.lower()
            if any(k in ll for k in ["tctl", "tdie", "core 0", "package", "cpu temp"]):
                m = re.search(r"[+]?([0-9]+\.?[0-9]*)\xb0C", line)
                if m:
                    t = float(m.group(1))
                    label = line.split(":")[0].strip()
                    status = "HOT" if t > 85 else "WARM" if t > 70 else "OK"
                    lines.append(f"  {label}: {t:.1f}C [{status}]")
            if "fan" in ll and "rpm" in ll:
                m = re.search(r"([0-9]+)\s+RPM", line)
                if m and int(m.group(1)) > 0:
                    label = line.split(":")[0].strip()
                    lines.append(f"  Fan {label}: {m.group(1)} RPM")
    else:
        thermal = _run(
            'for f in /sys/class/thermal/thermal_zone*/temp; do echo "$(($(cat $f)/1000))C"; done 2>/dev/null | head -5'
        )
        if thermal:
            lines.append("Temperatures (sysfs): " + ", ".join(thermal.splitlines()))

    if detail == "full":
        disk = _run("df -h / 2>/dev/null | tail -1")
        if disk:
            p = disk.split()
            if len(p) >= 5:
                lines.append(
                    f"\nDisk /: {p[2]} used / {p[1]} total ({p[3]} free, {p[4]})"
                )

    return {"success": True, "result": "\n".join(lines)}
