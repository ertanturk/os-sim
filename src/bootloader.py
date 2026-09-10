"""Bootloader for the operating system sim."""

from __future__ import annotations

from src.cpu import CPU
from src.kernel import Kernel
from src.ram import RAM


class Bootloader:
    def __init__(self, ram: RAM, cpu: CPU, kernel: Kernel):
        self.ram = ram
        self.cpu = cpu
        self.kernel = kernel

    def load_ivt(self) -> None:
        """Populate the Interrupt Vector Table (IVT) in low memory."""
        # Timer interrupt vector (0x00) -> Trampoline at 0x20
        self.ram.write(Kernel.IVT_TIMER_VECTOR, Kernel.ISR_TRAMPOLINE_ADDR)

        # Syscall vector (0x05) -> Handler address in RAM
        self.ram.write(Kernel.IVT_SYSCALL_VECTOR, Kernel.ISR_TRAMPOLINE_ADDR)

    def boot(self, max_steps: int | None = None) -> None:
        """Run the complete boot sequence and hand off control."""
        self.load_ivt()
        self.kernel.install_isr()
        self.kernel.start(max_steps=max_steps)
