"""RAM (Random Access Memory) class for the OS simulator."""

from __future__ import annotations

from collections.abc import Callable


class RAM:
    def __init__(self, size: int = 256):
        # Initialize the RAM size of 256 bytes each adress is 8 bits (0-255)
        try:
            self.memory = [0] * size
        except MemoryError as e:
            raise MemoryError(f"Failed to allocate memory of size {size}") from e
        self.write_hooks: dict[int, list[Callable[[], None]]] = {}

    def add_write_hook(self, address: int, callback: Callable[[], None]) -> None:
        """Register a callback when a specific address is written."""
        self._check_address(address)
        self.write_hooks.setdefault(address, []).append(callback)

    def read(self, address: int) -> int:
        """Read a value from the RAM memory at the specified address."""
        self._check_address(address)
        return self.memory[address]

    def write(self, address: int, value: int):
        """Write a value to the RAM memory at the specified address."""
        self._check_address(address)
        # Mask the value to ensure it fits within 8 bits (0-255)
        self.memory[address] = value & 0xFF
        if address in self.write_hooks:
            for hook in self.write_hooks[address]:
                hook()

    def __str__(self) -> str:
        """Return a string representation of the RAM memory."""
        return str(self.memory)

    def _check_address(self, address: int) -> None:
        """Check if the address is within the bounds of the RAM memory."""
        if address < 0 or address >= len(self.memory):
            raise IndexError(f"Address ({address}) out of bounds. Capacity: {len(self.memory)}")
