"""
Moruk OS Plugin: System Info v2.0
Fixed: locale-independent parsing, correct CPU/GPU/RAM/Disk.
"""

PLUGIN_CORE = True
PLUGIN_NAME = "system_info"
PLUGIN_DESCRIPTION = "Shows system info: CPU, RAM, disk usage, uptime"
PLUGIN_PARAMS = '{"detail": "brief|full (default: brief)"}'
PLUGIN_VERSION = "2.0"


def execute(params: dict) -> dict:
    import subprocess

    def run(cmd):
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""

    detail = params.get("detail", "brief")
    info = []

    try:
        # Uptime
        uptime = run("uptime -p")
        if uptime:
            info.append(f"Uptime: {uptime}")

        # RAM - /proc/meminfo (locale-independent)
        meminfo = run("cat /proc/meminfo")
        mem_total = mem_avail = 0
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable:"):
                mem_avail = int(line.split()[1]) // 1024
        mem_used = mem_total - mem_avail
        info.append(f"RAM: {mem_used/1024:.1f} GB used / {mem_total/1024:.1f} GB total ({mem_avail/1024:.1f} GB free)")

        # Disk
        disk = run("df -h / | tail -1")
        if disk:
            parts = disk.split()
            if len(parts) >= 5:
                info.append(f"Disk: {parts[2]} used / {parts[1]} total ({parts[3]} free, {parts[4]} full)")

        if detail == "full":
            # CPU model
            cpu = run("grep 'model name' /proc/cpuinfo | head -1 | cut -d: -f2")
            if cpu:
                info.append(f"CPU: {cpu.strip()}")

            # CPU cores
            cores = run("nproc")
            if cores:
                info.append(f"CPU cores: {cores}")

            # GPU (exclude integrated Raphael)
            gpu = run("lspci | grep -i vga | grep -iv 'raphael' | head -1 | cut -d: -f3")
            if gpu:
                info.append(f"GPU: {gpu.strip()}")

            # Load
            load = run("cat /proc/loadavg")
            if load:
                info.append(f"Load avg: {load}")

            # OS
            os_name = run("grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"'")
            if os_name:
                info.append(f"OS: {os_name}")

            # Python
            py = run("python3 --version")
            if py:
                info.append(f"Python: {py}")

        return {"success": True, "result": "\n".join(info)}

    except Exception as e:
        return {"success": False, "result": f"Error: {str(e)}"}
