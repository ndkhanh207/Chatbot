import functools
import re
from collections.abc import Callable
from typing import Any

_PCIE_PATTERN = re.compile(r"pcie\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


@functools.lru_cache(maxsize=1024)
def normalize_socket(value: str) -> str:
    return re.sub(r"\s+", "", str(value)).upper() if value else ""


@functools.lru_cache(maxsize=1024)
def parse_pcie_gen(text: str) -> float | None:
    match = _PCIE_PATTERN.search(str(text)) if text else None
    return float(match.group(1)) if match else None


def _get_field(item: dict, *keys, default=None):
    return next((item[key] for key in keys if item.get(key) not in (None, "")), default)


def _category_items(items: list[dict], category: str) -> list[dict]:
    return [item for item in items if item.get("category") == category]


def check_cpu_main_compat(cpu: dict, main: dict) -> dict[str, Any]:
    cpu_socket = normalize_socket(_get_field(cpu, "socket", "socket_type", default=""))
    main_socket = normalize_socket(_get_field(main, "socket", "socket_type", default=""))
    socket_match = None if not cpu_socket or not main_socket else cpu_socket == main_socket
    is_compatible = socket_match

    return {
        "is_compatible": is_compatible,
        "status": "unknown" if socket_match is None else "compatible" if socket_match else "incompatible",
        "cpu_socket": cpu_socket or None,
        "mainboard_socket": main_socket or None,
        "socket_match": socket_match,
    }


def check_gpu_main_compat(gpu: dict, main: dict) -> dict[str, Any]:
    gpu_gen = parse_pcie_gen(_get_field(gpu, "interface", "pcie", default=""))
    main_gen = parse_pcie_gen(_get_field(main, "pcie", "interface", default=""))
    is_compatible = True if gpu_gen is not None and main_gen is not None else None
    return {
        "is_compatible": is_compatible,
        "status": "compatible" if is_compatible else "unknown",
        "gpu_pcie_gen": gpu_gen,
        "main_pcie_gen": main_gen,
        "backward_compatible": is_compatible,
        "bandwidth_limited": bool(is_compatible and gpu_gen > main_gen),
    }


def check_cpu_gpu_compat(cpu: dict, gpu: dict) -> dict[str, Any]:
    """The catalog has no direct CPU/GPU physical-compatibility field."""
    return {"is_compatible": None, "status": "not_directly_checkable"}


def _collect(
    inventory: list[dict],
    category: str,
    check: Callable[[dict], dict],
    *,
    require_compatible: bool = False,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    results = []
    for item in _category_items(inventory, category):
        result = check(item)
        if require_compatible and not result["is_compatible"]:
            continue
        results.append({"item": item, "compat": result})
    return results[:top_k]


def find_compatible_mainboards(cpu: dict, inventory: list[dict], top_k: int = 10):
    return _collect(
        inventory, "MAINBOARD", lambda main: check_cpu_main_compat(cpu, main),
        require_compatible=True, top_k=top_k,
    )


def find_compatible_cpus(main: dict, inventory: list[dict], top_k: int = 10):
    return _collect(
        inventory, "CPU", lambda cpu: check_cpu_main_compat(cpu, main),
        require_compatible=True, top_k=top_k,
    )


def find_compatible_gpus_for_main(main: dict, inventory: list[dict], top_k: int = 10):
    return _collect(inventory, "GPU", lambda gpu: check_gpu_main_compat(gpu, main), top_k=top_k)


def find_compatible_mains_for_gpu(gpu: dict, inventory: list[dict], top_k: int = 10):
    return _collect(inventory, "MAINBOARD", lambda main: check_gpu_main_compat(gpu, main), top_k=top_k)


def find_compatible_gpus_for_cpu(cpu: dict, inventory: list[dict], top_k: int = 10):
    return _collect(inventory, "GPU", lambda gpu: check_cpu_gpu_compat(cpu, gpu), top_k=top_k)


def find_compatible_cpus_for_gpu(gpu: dict, inventory: list[dict], top_k: int = 10):
    return _collect(inventory, "CPU", lambda cpu: check_cpu_gpu_compat(cpu, gpu), top_k=top_k)


def find_compatible_build(
    have_type: str,
    have_item: dict,
    inventory: list[dict],
    top_k: int = 5,
) -> dict[str, Any]:
    finders = {
        "cpu": {
            "mainboards": find_compatible_mainboards,
            "gpus": find_compatible_gpus_for_cpu,
        },
        "mainboard": {
            "cpus": find_compatible_cpus,
            "gpus": find_compatible_gpus_for_main,
        },
        "gpu": {
            "mainboards": find_compatible_mains_for_gpu,
            "cpus": find_compatible_cpus_for_gpu,
        },
    }
    if have_type not in finders:
        raise ValueError(f"have_type không hợp lệ: {have_type}. Phải là cpu/gpu/mainboard.")
    return {
        name: finder(have_item, inventory, top_k)
        for name, finder in finders[have_type].items()
    }
