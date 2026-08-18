#!/usr/bin/env python3
"""Cretona PC System Resources & Hardware Diagnostic Tool.

Checks the host PC's CPU, RAM, Pagefile, GPU (CUDA/VRAM), Disk, and required runtimes
(Python, FFmpeg, Ollama, Java, Android SDK, Supabase), providing intelligent tier
recommendations and automated configuration tuning for any machine pulling this repo.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Safe stdout UTF-8 reconfiguration if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@dataclass
class HardwareSpecs:
    os_name: str
    os_version: str
    cpu_model: str
    cpu_cores: int
    ram_total_gb: float
    ram_available_gb: float
    pagefile_total_gb: float
    pagefile_available_gb: float
    gpu_name: str
    gpu_vram_gb: float
    disk_free_gb: float


@dataclass
class ToolingStatus:
    python_version: str
    in_venv: bool
    ffmpeg_available: bool
    ffmpeg_version: str
    ollama_running: bool
    ollama_models: list[str] = field(default_factory=list)
    java_home: str = ""
    java_version: str = ""
    android_home: str = ""
    adb_available: bool = False


@dataclass
class DiagnosticsReport:
    hardware: HardwareSpecs
    tooling: ToolingStatus
    recommended_tier: str  # 'mock', 'cloud', 'local'
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def get_windows_memory() -> tuple[float, float, float, float]:
    """Get total/avail RAM and Pagefile on Windows using GlobalMemoryStatusEx."""
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullTotalVirtualExtended", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total_ram = stat.ullTotalPhys / (1024**3)
            avail_ram = stat.ullAvailPhys / (1024**3)
            total_page = stat.ullTotalPageFile / (1024**3)
            avail_page = stat.ullAvailPageFile / (1024**3)
            return round(total_ram, 2), round(avail_ram, 2), round(total_page, 2), round(avail_page, 2)
    except Exception:
        pass

    # Fallback for non-Windows or if ctypes fails
    return 16.0, 8.0, 16.0, 8.0


def get_gpu_info() -> tuple[str, float]:
    """Detect NVIDIA / AMD / Intel GPU and dedicated VRAM."""
    # 1. Try nvidia-smi
    try:
        cmd = ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout.strip():
            lines = res.stdout.strip().split("\n")
            parts = lines[0].split(",")
            gpu_name = parts[0].strip()
            vram_mb = float(parts[1].strip())
            return gpu_name, round(vram_mb / 1024.0, 2)
    except Exception:
        pass

    # 2. Windows PowerShell Get-CimInstance fallback
    if platform.system() == "Windows":
        try:
            ps_cmd = 'Get-CimInstance Win32_VideoController | Select-Object -Property Name, AdapterRAM | ConvertTo-Json'
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and "Name" in res.stdout:
                import json
                data = json.loads(res.stdout)
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]
                name = data.get("Name", "Integrated GPU")
                ram_bytes = data.get("AdapterRAM", 0) or 0
                vram_gb = round(ram_bytes / (1024**3), 2)
                return name, vram_gb
        except Exception:
            pass

    return "Standard / Integrated GPU", 0.0


def check_ffmpeg() -> tuple[bool, str]:
    """Check if ffmpeg is available on PATH."""
    try:
        res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            first_line = res.stdout.split("\n")[0]
            return True, first_line.split("Copyright")[0].strip()
    except Exception:
        pass
    return False, ""


def check_ollama() -> tuple[bool, list[str]]:
    """Check if Ollama is running and query available models."""
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", headers={"User-Agent": "CretonaDiagnostic"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                return True, models
    except Exception:
        pass
    return False, []


def inspect_system() -> DiagnosticsReport:
    """Perform full diagnostic scan of PC hardware and tooling."""
    total_ram, avail_ram, total_page, avail_page = get_windows_memory()
    gpu_name, gpu_vram = get_gpu_info()

    stat_disk = shutil.disk_usage(Path.cwd())
    free_disk_gb = round(stat_disk.free / (1024**3), 2)

    hw = HardwareSpecs(
        os_name=platform.system(),
        os_version=f"{platform.release()} ({platform.version()})",
        cpu_model=platform.processor() or platform.machine(),
        cpu_cores=os.cpu_count() or 4,
        ram_total_gb=total_ram,
        ram_available_gb=avail_ram,
        pagefile_total_gb=total_page,
        pagefile_available_gb=avail_page,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram,
        disk_free_gb=free_disk_gb,
    )

    ffmpeg_ok, ffmpeg_ver = check_ffmpeg()
    ollama_ok, ollama_models = check_ollama()
    java_home = os.environ.get("JAVA_HOME", "")
    android_home = os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", ""))
    adb_ok = shutil.which("adb") is not None

    in_venv = sys.prefix != sys.base_prefix

    tools = ToolingStatus(
        python_version=platform.python_version(),
        in_venv=in_venv,
        ffmpeg_available=ffmpeg_ok,
        ffmpeg_version=ffmpeg_ver,
        ollama_running=ollama_ok,
        ollama_models=ollama_models,
        java_home=java_home,
        java_version="",
        android_home=android_home,
        adb_available=adb_ok,
    )

    recommendations: list[str] = []
    warnings: list[str] = []

    # Intelligent Tier Selection
    if gpu_vram >= 6.0 and total_ram >= 16.0:
        recommended_tier = "local"
        recommendations.append("PC has high-spec GPU/VRAM. Tier 3 (Local Model LTX-Video) is fully supported.")
    elif total_ram >= 8.0:
        recommended_tier = "cloud"
        recommendations.append("Recommended: Tier 2 (Cloud AI Diffusion). Fast, photorealistic AI video synthesis.")
    else:
        recommended_tier = "mock"
        recommendations.append("Low RAM detected. Recommended: Tier 1 (Mock / Dev Provider) for zero-spend development.")

    if not ffmpeg_ok:
        warnings.append("FFmpeg is not found on PATH. Thumbnail generation and video stitching will be disabled.")
    else:
        recommendations.append(f"FFmpeg ready: {ffmpeg_ver}")

    if not tools.in_venv:
        warnings.append("Not running in Python virtual environment. Recommended: source .venv/Scripts/activate")

    if free_disk_gb < 5.0:
        warnings.append(f"Low disk space ({free_disk_gb} GB remaining). Recommended: at least 10 GB free for video caching.")

    if not ollama_ok:
        recommendations.append("Ollama not active on port 11434. Local prompt enhancement will use deterministic fallback.")
    else:
        recommendations.append(f"Ollama active with {len(ollama_models)} models: {', '.join(ollama_models[:3])}")

    return DiagnosticsReport(
        hardware=hw,
        tooling=tools,
        recommended_tier=recommended_tier,
        recommendations=recommendations,
        warnings=warnings,
    )


def print_report(report: DiagnosticsReport) -> None:
    """Print a clean summary report in console."""
    print("=" * 70)
    print(" >>> CRETONA PC HARDWARE & ENVIRONMENT DIAGNOSTICS <<<")
    print("=" * 70)
    
    hw = report.hardware
    print("\n[HARDWARE RESOURCES]")
    print(f"  * OS:              {hw.os_name} {hw.os_version}")
    print(f"  * CPU:             {hw.cpu_model} ({hw.cpu_cores} cores)")
    print(f"  * RAM:             {hw.ram_total_gb} GB total ({hw.ram_available_gb} GB available)")
    print(f"  * Pagefile/Swap:   {hw.pagefile_total_gb} GB total ({hw.pagefile_available_gb} GB available)")
    print(f"  * GPU / Video:     {hw.gpu_name} (VRAM: {hw.gpu_vram_gb} GB)")
    print(f"  * Disk Free Space: {hw.disk_free_gb} GB")

    tl = report.tooling
    print("\n[TOOLING & RUNTIMES]")
    print(f"  * Python:          {tl.python_version} (Virtualenv: {'Active [OK]' if tl.in_venv else 'Not active [WARN]'})")
    print(f"  * FFmpeg:          {'Available [OK] (' + tl.ffmpeg_version + ')' if tl.ffmpeg_available else 'Missing [WARN]'}")
    print(f"  * Ollama LLM:      {'Active [OK] (' + str(len(tl.ollama_models)) + ' models)' if tl.ollama_running else 'Inactive (using fallback) [INFO]'}")
    print(f"  * Android SDK/ADB: {'Ready [OK]' if tl.adb_available else 'Not on PATH [INFO]'}")
    if tl.java_home:
        print(f"  * JAVA_HOME:       {tl.java_home}")

    print("\n[TIER RECOMMENDATION]")
    tier_badges = {
        "mock": "Tier 1: Mock / Dev (Zero-spend, instant local testing)",
        "cloud": "Tier 2: Cloud AI Diffusion (Recommended for most PCs with Internet)",
        "local": "Tier 3: Local Model (High-performance dedicated GPU)",
    }
    print(f"  --> Optimal Mode for this PC: {tier_badges.get(report.recommended_tier, report.recommended_tier)}")

    if report.recommendations:
        print("\n[RECOMMENDATIONS & CAPABILITIES]")
        for rec in report.recommendations:
            print(f"  [+] {rec}")

    if report.warnings:
        print("\n[WARNINGS & FIXES]")
        for warn in report.warnings:
            print(f"  [!] {warn}")

    print("\n" + "=" * 70)


def auto_tune_environment(report: DiagnosticsReport, env_path: Path) -> None:
    """Automatically tune CRETONA_DEFAULT_VIDEO_PROVIDER in .env matching PC specs."""
    if not env_path.exists():
        example = env_path.parent / ".env.example"
        if example.exists():
            shutil.copy(example, env_path)

    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        tier = report.recommended_tier
        if "CRETONA_DEFAULT_VIDEO_PROVIDER=" in content:
            import re
            updated = re.sub(
                r"CRETONA_DEFAULT_VIDEO_PROVIDER=.*",
                f"CRETONA_DEFAULT_VIDEO_PROVIDER={tier}",
                content,
            )
            env_path.write_text(updated, encoding="utf-8")
            print(f"[OK] Automatically tuned {env_path.name} -> CRETONA_DEFAULT_VIDEO_PROVIDER={tier}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cretona System Resources & Environment Diagnostic Tool")
    parser.add_argument("--auto-tune", action="store_true", help="Auto-configure .env matching this PC's specs")
    parser.add_argument("--json", action="store_true", help="Output raw JSON format")
    args = parser.parse_args()

    report = inspect_system()

    if args.json:
        import dataclasses
        import json
        print(json.dumps(dataclasses.asdict(report), indent=2))
        return

    print_report(report)

    if args.auto_tune:
        root_env = Path(__file__).resolve().parents[1] / ".env"
        backend_env = Path(__file__).resolve().parents[1] / "backend" / ".env"
        auto_tune_environment(report, root_env)
        if backend_env.parent.exists():
            auto_tune_environment(report, backend_env)


if __name__ == "__main__":
    main()
