"""
Memento-X 硬件检测模块

检测用户本地硬件能力，决定哪些工具可用、是否需要下载。
"""
import platform
import subprocess
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HardwareProfile:
    """硬件配置画像"""
    os_name: str = ""
    os_version: str = ""
    cpu_brand: str = ""
    cpu_cores: int = 0
    ram_gb: float = 0.0
    gpu_name: str = ""
    gpu_vram_gb: float = 0.0
    gpu_supports_metal: bool = False   # Apple Silicon
    gpu_supports_cuda: bool = False    # NVIDIA
    gpu_supports_opencl: bool = False  # AMD/Intel
    disk_free_gb: float = 0.0
    da_vinci_installed: bool = False

    @property
    def can_run_comfyui(self) -> bool:
        """ComfyUI 需要 >= 4GB 显存"""
        return self.gpu_vram_gb >= 4.0

    @property
    def can_run_sam2(self) -> bool:
        """SAM2 需要 >= 6GB 显存（Apple Silicon 统一内存也算）"""
        if self.gpu_supports_metal:
            return self.ram_gb >= 16
        return self.gpu_vram_gb >= 6.0

    @property
    def can_run_birefnet(self) -> bool:
        """BiRefNet 可在 CPU 上运行，但 GPU 更快"""
        return True

    @property
    def recommended_toolset(self) -> list[str]:
        """根据硬件推荐可用工具集"""
        tools = ["ffmpeg", "birefnet", "hyperframes"]
        if self.can_run_comfyui:
            tools.append("comfyui")
        if self.can_run_sam2:
            tools.append("sam2")
        if self.da_vinci_installed:
            tools.append("davinci")
        return tools


class HardwareDetector:
    """硬件检测器"""

    @staticmethod
    def detect() -> HardwareProfile:
        profile = HardwareProfile()

        # OS
        profile.os_name = platform.system()
        profile.os_version = platform.version()

        # CPU
        profile.cpu_cores = os.cpu_count() or 4
        if profile.os_name == "Darwin":
            try:
                result = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                        capture_output=True, text=True)
                profile.cpu_brand = result.stdout.strip()
            except Exception:
                profile.cpu_brand = "Apple Silicon"

            # RAM
            try:
                result = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                        capture_output=True, text=True)
                profile.ram_gb = int(result.stdout.strip()) / (1024 ** 3)
            except Exception:
                profile.ram_gb = 8.0
        elif profile.os_name == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            profile.cpu_brand = line.split(":", 1)[1].strip()
                            break
            except Exception:
                profile.cpu_brand = "Unknown"
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if "MemTotal" in line:
                            profile.ram_gb = int(line.split()[1]) / (1024 ** 2)
                            break
            except Exception:
                profile.ram_gb = 8.0
        elif profile.os_name == "Windows":
            profile.cpu_brand = platform.processor()
            try:
                import psutil
                profile.ram_gb = psutil.virtual_memory().total / (1024 ** 3)
            except ImportError:
                profile.ram_gb = 8.0

        # GPU
        HardwareDetector._detect_gpu(profile)

        # Disk
        try:
            import shutil
            usage = shutil.disk_usage(os.path.expanduser("~"))
            profile.disk_free_gb = usage.free / (1024 ** 3)
        except Exception:
            profile.disk_free_gb = 50.0

        # DaVinci Resolve
        profile.da_vinci_installed = HardwareDetector._check_davinci()

        return profile

    @staticmethod
    def _detect_gpu(profile: HardwareProfile):
        """检测 GPU 信息"""
        system = profile.os_name

        if system == "Darwin":
            # Apple Silicon: Metal
            try:
                result = subprocess.run(["system_profiler", "SPDisplaysDataType"],
                                        capture_output=True, text=True)
                for line in result.stdout.split("\n"):
                    if "Chipset Model" in line:
                        profile.gpu_name = line.split(":", 1)[1].strip()
                profile.gpu_supports_metal = "Apple" in profile.gpu_name or "M" in profile.gpu_name
                # 统一内存架构：VRAM 不单独计算，用 RAM 的一半
                profile.gpu_vram_gb = profile.ram_gb * 0.5
            except Exception:
                profile.gpu_name = "Apple GPU"

        elif system == "Linux":
            try:
                result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                                          "--format=csv,noheader,nounits"],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    parts = result.stdout.strip().split(",")
                    profile.gpu_name = parts[0].strip()
                    profile.gpu_vram_gb = float(parts[1].strip()) / 1024.0
                    profile.gpu_supports_cuda = True
                    return
            except Exception:
                pass

            # 尝试 AMD
            try:
                result = subprocess.run(["rocm-smi", "--showproductname"],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    profile.gpu_name = result.stdout.strip()
                    profile.gpu_supports_opencl = True
                    profile.gpu_vram_gb = 4.0  # 保守估计
                    return
            except Exception:
                pass

            profile.gpu_name = "Software Renderer"
            profile.gpu_vram_gb = 0.0

        elif system == "Windows":
            try:
                result = subprocess.run(["wmic", "path", "win32_VideoController", "get", "name"],
                                        capture_output=True, text=True, timeout=5)
                lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
                if len(lines) > 1:
                    profile.gpu_name = lines[1]
                if "NVIDIA" in profile.gpu_name:
                    profile.gpu_supports_cuda = True
                    profile.gpu_vram_gb = 4.0
            except Exception:
                profile.gpu_name = "Unknown GPU"

    @staticmethod
    def _check_davinci() -> bool:
        """检查 DaVinci Resolve 是否安装"""
        system = platform.system()
        paths = []
        if system == "Darwin":
            paths = ["/Applications/DaVinci Resolve/"]
        elif system == "Windows":
            paths = ["C:\\Program Files\\Blackmagic Design\\DaVinci Resolve\\"]
        elif system == "Linux":
            paths = ["/opt/resolve/"]
        return any(os.path.exists(p) for p in paths)


def detect() -> HardwareProfile:
    return HardwareDetector.detect()


if __name__ == "__main__":
    profile = detect()
    print(f"OS: {profile.os_name} {profile.os_version}")
    print(f"CPU: {profile.cpu_brand} ({profile.cpu_cores} cores)")
    print(f"RAM: {profile.ram_gb:.1f} GB")
    print(f"GPU: {profile.gpu_name} ({profile.gpu_vram_gb:.1f} GB VRAM)")
    print(f"Metal: {profile.gpu_supports_metal}, CUDA: {profile.gpu_supports_cuda}")
    print(f"Disk free: {profile.disk_free_gb:.1f} GB")
    print(f"DaVinci: {profile.da_vinci_installed}")
    print(f"Recommended tools: {profile.recommended_toolset}")