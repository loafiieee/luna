from __future__ import annotations

from backend.utils.platform import *
import subprocess
import re


def get_reserved_ports(proto: str = "tcp") -> list[tuple[int, int]]:
    """
    Returns list of (start, end) reserved port ranges
    """

    if proto not in {"tcp", "udp"}:
        raise ValueError(f"Unsupported protocol: {proto}")

    if is_windows():
        return _get_windows_reserved(proto)

    elif is_linux():
        return _get_linux_reserved()

    elif is_macos():
        return _get_macos_reserved()

    return []


# ---------------- WINDOWS ----------------

def _get_windows_reserved(proto: str) -> list[tuple[int, int]]:

    cmd = f'netsh int ipv4 show excludedportrange protocol={proto}'

    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    ranges = []

    # Example lines:
    # Start Port    End Port
    # ----------    --------
    # 5357          5357
    # 49692         49791

    for line in result.stdout.splitlines():

        match = re.search(r"(\d+)\s+(\d+)", line)

        if match:
            start, end = map(int, match.groups())
            ranges.append((start, end))

    return ranges


# ---------------- LINUX ----------------

def _get_linux_reserved() -> list[tuple[int, int]]:

    cmd = "cat /proc/sys/net/ipv4/ip_local_reserved_ports"

    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    ranges = []

    # Example:
    # 4000-4010,5000,6000-6010

    data = result.stdout.strip()

    if not data:
        return []

    for part in data.split(","):

        if "-" in part:
            start, end = map(int, part.split("-"))
        else:
            start = end = int(part)

        ranges.append((start, end))

    return ranges


# ---------------- MACOS ----------------

def _get_macos_reserved() -> list[tuple[int, int]]:

    cmd = "sysctl net.inet.ip.portrange.reservedhigh"

    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Example:
    # net.inet.ip.portrange.reservedhigh: 1023

    ranges = []

    match = re.search(r":\s*(\d+)", result.stdout)

    if match:
        high = int(match.group(1))

        # macOS reserves 1 -> reservedhigh
        ranges.append((1, high))

    return ranges
