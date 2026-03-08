PLUGIN_NAME = "gpu_monitor"
PLUGIN_DESCRIPTION = "GPU monitoring: temperature, VRAM usage, GPU load. Supports AMD ROCm, sysfs, and NVIDIA."
PLUGIN_PARAMS = {"detail": "brief|full (default: brief)"}

import subprocess
import os
import re

def _run(cmd_list):
    try:
        r = subprocess.run(cmd_list, shell=False, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

def execute(params):
    detail = params.get("detail", "brief")
    lines = ["GPU Monitor", "-" * 40]

    # GPU Name via lspci
    lspci = _run(["lspci"])
    gpu_name = ""
    if lspci:
        for line in lspci.splitlines():
            l_lower = line.lower()
            if any(x in l_lower for x in ['vga', '3d', 'display']) and 'raphael' not in l_lower:
                gpu_name = line.split(":", 2)[-1].strip()
                break
    if gpu_name:
        lines.append(f"GPU: {gpu_name[:70]}")

    # Try ROCm
    rocm_smi = _run(["which", "rocm-smi"])
    if rocm_smi:
        temp_out = _run(["rocm-smi", "--showtemp"])
        if temp_out:
            m = re.search(r'([0-9]+\.[0-9]+)', temp_out)
            if m:
                t = float(m.group(1))
                status = "HOT" if t > 85 else "WARM" if t > 70 else "OK"
                lines.append(f"Temp: {t:.1f}C [{status}]")

        usage_out = _run(["rocm-smi", "--showuse"])
        if usage_out:
            m = re.search(r'([0-9]+%)', usage_out)
            if m:
                lines.append(f"Load: {m.group(1)}")

        vram_out = _run(["rocm-smi", "--showmeminfo", "vram"])
        if vram_out:
            used = re.search(r'Used:\s+([0-9]+)', vram_out)
            total = re.search(r'Total:\s+([0-9]+)', vram_out)
            if used and total:
                try:
                    used_gb = int(used.group(1)) / (1024**3)
                    total_gb = int(total.group(1)) / (1024**3)
                    lines.append(f"VRAM: {used_gb:.1f} GB / {total_gb:.1f} GB")
                except Exception:
                    lines.append(f"VRAM: {used.group(1)} / {total.group(1)} bytes")

        if detail == "full":
            power = _run(["rocm-smi", "--showpower"])
            m = re.search(r'([0-9]+\.[0-9]+W)', power)
            if m: lines.append(f"Power: {m.group(1)}")
            
            clock = _run(["rocm-smi", "--showclocks"])
            if clock:
                for line in clock.splitlines():
                    if '*' in line and 'sclk' in line:
                        parts = line.split()
                        if len(parts) >= 2: lines.append(f"Clock: {parts[1]}")

    else:
        # Fallback: sysfs
        busy_path = "/sys/class/drm/card0/device/gpu_busy_percent"
        if os.path.exists(busy_path):
            try:
                with open(busy_path, "r") as f:
                    lines.append(f"Load: {f.read().strip()}%")
            except Exception: pass

        vram_used_p = "/sys/class/drm/card0/device/mem_info_vram_used"
        vram_total_p = "/sys/class/drm/card0/device/mem_info_vram_total"
        if os.path.exists(vram_used_p) and os.path.exists(vram_total_p):
            try:
                with open(vram_used_p, "r") as f: u = int(f.read().strip())
                with open(vram_total_p, "r") as f: t = int(f.read().strip())
                lines.append(f"VRAM: {u/(1024**3):.1f} GB / {t/(1024**3):.1f} GB")
            except Exception: pass

        # NVIDIA fallback
        if len(lines) <= 2:
            nvidia = _run(["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"])
            if nvidia:
                parts = [p.strip() for p in nvidia.split(",")]
                if len(parts) >= 5:
                    lines[1] = f"GPU: {parts[0]}"
                    lines.append(f"Temp: {parts[1]}C")
                    lines.append(f"Load: {parts[2]}%")
                    lines.append(f"VRAM: {parts[3]}MB / {parts[4]}MB")

    if len(lines) <= 2:
        return {"success": False, "result": "No GPU monitoring data available."}

    return {"success": True, "result": "\n".join(lines)}
