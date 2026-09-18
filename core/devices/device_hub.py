"""Device Hub and Hardware Capability Probe for JARVIS OS.

Provides cross-platform device capability detection, hardware profiling (CPU, RAM,
GPU/Metal/CUDA/DirectML, VRAM, Storage), and agent node registration with bounded
in-memory caching.
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GpuInfo(BaseModel):
    """Normalized GPU hardware descriptor."""

    name: str = "Unknown GPU"
    backend: str = "none"  # "metal", "cuda", "directml", "rocm", "none"
    vram_total_mb: float = 0.0
    vram_available_mb: float = 0.0
    is_integrated: bool = True


class DeviceCapability(BaseModel):
    """Normalized hardware and capability profile of a JARVIS device."""

    device_id: str = "local-host"
    device_name: str = "Host Device"
    os_type: str = "unknown"  # "windows", "darwin", "linux"
    os_release: str = ""
    os_version: str = ""
    architecture: str = ""
    cpu_model: str = "Generic CPU"
    cpu_cores_logical: int = 1
    cpu_cores_physical: int = 1
    ram_total_mb: float = 0.0
    ram_available_mb: float = 0.0
    storage_total_gb: float = 0.0
    storage_free_gb: float = 0.0
    gpus: list[GpuInfo] = Field(default_factory=list)
    has_microphone: bool = True
    has_speakers: bool = True
    supported_features: list[str] = Field(default_factory=list)
    connected_agents: list[str] = Field(default_factory=list)
    last_probed_at: float = Field(default_factory=time.time)


class DeviceProbe:
    """Probes local host hardware without requiring heavy third-party packages."""

    @classmethod
    def probe_cpu(cls) -> tuple[str, int, int]:
        """Detect CPU model, logical cores, and physical cores."""
        logical = os.cpu_count() or 1
        physical = max(1, logical // 2)
        model = platform.processor() or "Generic CPU"
        system = platform.system().lower()

        try:
            if system == "darwin":
                # 1. Try Intel/AMD brand string (works on Intel Macs)
                try:
                    out = subprocess.check_output(
                        ["sysctl", "-n", "machdep.cpu.brand_string"],
                        stderr=subprocess.DEVNULL, timeout=1,
                    ).decode().strip()
                    if out and out != "arm":
                        model = out
                except Exception:
                    out = ""

                # 2. On Apple Silicon, brand_string is empty — parse hw.model instead
                if not model or model in ("arm", "Generic CPU"):
                    try:
                        hw_model = subprocess.check_output(
                            ["sysctl", "-n", "hw.model"],
                            stderr=subprocess.DEVNULL, timeout=1,
                        ).decode().strip()
                        # Map Apple model identifiers like Mac16,10 to chip name
                        # Try system_profiler for human-readable chip name
                        sp_out = subprocess.check_output(
                            ["system_profiler", "SPHardwareDataType"],
                            stderr=subprocess.DEVNULL, timeout=3,
                        ).decode()
                        for line in sp_out.splitlines():
                            if "Chip" in line or "Processor Name" in line:
                                chip = line.split(":", 1)[-1].strip()
                                if chip:
                                    model = chip
                                    break
                        if not model or model in ("arm", "Generic CPU"):
                            # Final fallback: construct from architecture
                            model = f"Apple Silicon ({hw_model})" if hw_model else "Apple Silicon"
                    except Exception:
                        if platform.machine() == "arm64":
                            model = "Apple Silicon"

                # 3. Physical core count
                try:
                    phys_out = subprocess.check_output(
                        ["sysctl", "-n", "hw.physicalcpu"],
                        stderr=subprocess.DEVNULL, timeout=1,
                    ).decode().strip()
                    if phys_out.isdigit():
                        physical = int(phys_out)
                except Exception:
                    pass

            elif system == "linux":
                if os.path.exists("/proc/cpuinfo"):
                    with open("/proc/cpuinfo", "r") as f:
                        for line in f:
                            if "model name" in line:
                                model = line.split(":", 1)[1].strip()
                                break
            elif system == "windows":
                model = os.environ.get("PROCESSOR_IDENTIFIER", model)
        except Exception as exc:
            logger.debug("CPU probe detail query failed: %s", exc)

        return model, logical, physical

    @classmethod
    def probe_ram(cls) -> tuple[float, float]:
        """Return (total_mb, available_mb) of system RAM."""
        system = platform.system().lower()
        total_mb = 0.0
        avail_mb = 0.0

        try:
            if system == "darwin":
                out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], stderr=subprocess.DEVNULL, timeout=1).decode().strip()
                if out.isdigit():
                    total_mb = round(int(out) / (1024 * 1024), 1)

                vm_out = subprocess.check_output(["vm_stat"], stderr=subprocess.DEVNULL, timeout=1).decode()
                page_size = 16384 if platform.machine() == "arm64" else 4096
                pages_free = 0
                pages_inactive = 0
                pages_purgeable = 0
                pages_speculative = 0
                pages_wired = 0

                for line in vm_out.splitlines():
                    if "page size of" in line:
                        import re
                        m = re.search(r"page size of (\d+) bytes", line)
                        if m:
                            page_size = int(m.group(1))
                    elif "Pages free:" in line:
                        pages_free = int(line.split(":")[1].strip().rstrip("."))
                    elif "Pages inactive:" in line:
                        pages_inactive = int(line.split(":")[1].strip().rstrip("."))
                    elif "Pages purgeable:" in line:
                        pages_purgeable = int(line.split(":")[1].strip().rstrip("."))
                    elif "Pages speculative:" in line:
                        pages_speculative = int(line.split(":")[1].strip().rstrip("."))
                    elif "Pages wired down:" in line:
                        pages_wired = int(line.split(":")[1].strip().rstrip("."))

                # Available memory on macOS: free + inactive + purgeable + speculative
                avail_bytes = (pages_free + pages_inactive + pages_purgeable + pages_speculative) * page_size
                avail_mb = round(avail_bytes / (1024 * 1024), 1)
                # Or total minus wired down as upper bound
                wired_mb = round((pages_wired * page_size) / (1024 * 1024), 1)
                max_usable = max(avail_mb, total_mb - wired_mb)
                avail_mb = round(max(avail_mb, max_usable * 0.8), 1)

            elif system == "linux" and os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", "r") as f:
                    meminfo = {}
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            meminfo[parts[0].strip()] = parts[1].strip()
                    if "MemTotal" in meminfo:
                        total_kb = int(meminfo["MemTotal"].split()[0])
                        total_mb = round(total_kb / 1024, 1)
                    if "MemAvailable" in meminfo:
                        avail_kb = int(meminfo["MemAvailable"].split()[0])
                        avail_mb = round(avail_kb / 1024, 1)

            elif system == "windows":
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
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
                total_mb = round(stat.ullTotalPhys / (1024 * 1024), 1)
                avail_mb = round(stat.ullAvailPhys / (1024 * 1024), 1)
        except Exception as exc:
            logger.debug("RAM probe failed: %s", exc)
            total_mb = 8192.0
            avail_mb = 4096.0

        return total_mb, avail_mb

    @classmethod
    def probe_gpus(cls, ram_total_mb: float) -> list[GpuInfo]:
        """Detect GPU acceleration (Metal on macOS Apple Silicon, CUDA, DirectML)."""
        system = platform.system().lower()
        gpus: list[GpuInfo] = []

        # 1. macOS Apple Silicon Metal
        if system == "darwin":
            is_arm = platform.machine() == "arm64"
            if is_arm:
                gpus.append(GpuInfo(
                    name="Apple Silicon Integrated GPU (Metal)",
                    backend="metal",
                    vram_total_mb=round(ram_total_mb * 0.75, 1),  # Apple Unified Memory architecture
                    vram_available_mb=round(ram_total_mb * 0.5, 1),
                    is_integrated=True,
                ))
            else:
                gpus.append(GpuInfo(
                    name="macOS Graphics (Intel)",
                    backend="metal",
                    vram_total_mb=1536.0,
                    vram_available_mb=1024.0,
                    is_integrated=True,
                ))
            return gpus

        # 2. Check nvidia-smi (CUDA on Linux / Windows)
        try:
            nvsmi = shutil.which("nvidia-smi")
            if nvsmi:
                cmd = [nvsmi, "--query-gpu=gpu_name,memory.total,memory.free", "--format=csv,noheader,nounits"]
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2).decode().strip()
                for line in out.splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        name = parts[0]
                        total_vram = float(parts[1])
                        free_vram = float(parts[2])
                        gpus.append(GpuInfo(
                            name=name,
                            backend="cuda",
                            vram_total_mb=total_vram,
                            vram_available_mb=free_vram,
                            is_integrated=False,
                        ))
        except Exception:
            pass

        # 3. Windows DirectML / DirectX detection
        if system == "windows" and not gpus:
            gpus.append(GpuInfo(
                name="DirectML Capable GPU",
                backend="directml",
                vram_total_mb=round(ram_total_mb * 0.5, 1),
                vram_available_mb=round(ram_total_mb * 0.25, 1),
                is_integrated=True,
            ))

        if not gpus:
            gpus.append(GpuInfo(
                name="CPU Software Renderer",
                backend="none",
                vram_total_mb=0.0,
                vram_available_mb=0.0,
                is_integrated=True,
            ))

        return gpus

    @classmethod
    def probe_storage(cls) -> tuple[float, float]:
        """Return (total_gb, free_gb) of primary disk."""
        try:
            root_path = os.path.abspath(os.sep)
            usage = shutil.disk_usage(root_path)
            total_gb = round(usage.total / (1024 ** 3), 1)
            free_gb = round(usage.free / (1024 ** 3), 1)
            return total_gb, free_gb
        except Exception:
            return 0.0, 0.0


class DeviceHub:
    """Central Device Registry and Hardware Manager for JARVIS OS."""

    def __init__(self, cache_ttl_seconds: float = 30.0) -> None:
        self._cache_ttl = cache_ttl_seconds
        self._last_probe_time: float = 0.0
        self._cached_profile: DeviceCapability | None = None
        self._connected_agents: set[str] = set()

    def register_agent(self, agent_id: str) -> None:
        """Register a connected agent node (e.g. WindowsAgent)."""
        self._connected_agents.add(agent_id)
        if self._cached_profile:
            self._cached_profile.connected_agents = sorted(list(self._connected_agents))

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister a disconnected agent node."""
        self._connected_agents.discard(agent_id)
        if self._cached_profile:
            self._cached_profile.connected_agents = sorted(list(self._connected_agents))

    def get_device_capability(self, force_refresh: bool = False) -> DeviceCapability:
        """Retrieve host hardware profile with cached TTL."""
        now = time.time()
        if not force_refresh and self._cached_profile is not None and (now - self._last_probe_time < self._cache_ttl):
            return self._cached_profile

        cpu_model, logical_cores, physical_cores = DeviceProbe.probe_cpu()
        ram_total, ram_avail = DeviceProbe.probe_ram()
        gpus = DeviceProbe.probe_gpus(ram_total)
        storage_total, storage_free = DeviceProbe.probe_storage()

        features = [
            "local_inference",
            "screen_awareness",
            "voice_io",
            "virtual_cursor",
            "persistent_memory",
        ]
        if any(g.backend in ("metal", "cuda", "directml") for g in gpus):
            features.append("hardware_acceleration")

        # Build a stable unique device_id using node name
        node = platform.node().lower().replace(" ", "-") or "local-host"
        # Truncate to keep IDs short and clean
        device_id = f"host-{node[:24]}"

        profile = DeviceCapability(
            device_id=device_id,
            device_name=platform.node() or "Local Host",
            os_type=platform.system().lower(),
            os_release=platform.release(),
            os_version=platform.version(),
            architecture=platform.machine(),
            cpu_model=cpu_model,
            cpu_cores_logical=logical_cores,
            cpu_cores_physical=physical_cores,
            ram_total_mb=ram_total,
            ram_available_mb=ram_avail,
            storage_total_gb=storage_total,
            storage_free_gb=storage_free,
            gpus=gpus,
            has_microphone=True,
            has_speakers=True,
            supported_features=features,
            connected_agents=sorted(list(self._connected_agents)),
            last_probed_at=now,
        )

        self._cached_profile = profile
        self._last_probe_time = now
        return profile
