"""Runtime container for coordinators and auth manager."""

from __future__ import annotations

from dataclasses import dataclass

from .auth import SignalKAuthManager
from .coordinator import SignalKCoordinator, SignalKDiscoveryCoordinator


@dataclass
class SignalKRuntimeData:
    coordinator: SignalKCoordinator
    discovery: SignalKDiscoveryCoordinator
    auth: SignalKAuthManager
