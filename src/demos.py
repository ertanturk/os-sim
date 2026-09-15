"""Built-in demo programs and task loaders for OS simulator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.kernel import Kernel
    from src.ram import RAM


def load_counter_demo(ram: RAM, kernel: Kernel) -> int:
    """Load a counter / cooperative yield loop task using kernel page allocation.

    Task 0 continuously increments R1 by 1 and yields CPU via SYS_YIELD (0x01).
    """
    code = [0x03, 0x01, 0x10, 0x20, 0x03, 0x01, 0x05, 0x30, 0x40]
    task = kernel.load_task_code(
        name="Task_Counter",
        code=code,
        priority=1,
        partition_size=32,
        base_address=64,
    )
    return task["task_id"]


def load_rogue_demo(ram: RAM, kernel: Kernel) -> int:
    """Load a rogue writer task that attempts illegal memory access.

    Task 1 tries to write 0xAA into address 0x40 (Task 0's memory),
    triggering a hardware memory protection fault.
    """
    code = [0x03, 0xAA, 0x02, 0x40]
    task = kernel.load_task_code(
        name="Task_Rogue_Writer",
        code=code,
        priority=1,
        partition_size=32,
        base_address=96,
    )
    return task["task_id"]


def load_hello_demo(ram: RAM, kernel: Kernel, message: str = "Hello OS!") -> int:
    """Load a task that prints a string using the SYS_PRINT_STR system call."""
    base = 64
    str_addr = 80
    msg_bytes = message.encode("ascii", errors="replace")[:14] + b"\x00"
    length = len(msg_bytes) - 1
    code = [
        0x03,
        str_addr,
        0x20,
        0x03,
        length,
        0x21,
        0x03,
        kernel.SYS_PRINT_STR,
        0x05,
        0x03,
        0x00,
        0x20,
        0x03,
        kernel.SYS_EXIT,
        0x05,
    ]
    task = kernel.load_task_code(
        name="Task_Hello",
        code=code,
        priority=1,
        partition_size=32,
        base_address=base,
    )
    for i, b in enumerate(msg_bytes):
        kernel._write_task_byte(task, str_addr + i, b)
    return task["task_id"]


def load_math_demo(ram: RAM, kernel: Kernel) -> int:
    """Load a task that performs arithmetic calculations and prints the result via SYS_PRINT_NUM.

    Calculates: (15 + 25) * 2 = 80, prints 80, and exits.
    """
    code = [
        0x03,
        15,  # LOAD_IMM 15
        0x20,  # MOV R1, ACC
        0x03,
        25,  # LOAD_IMM 25
        0x10,  # ADD R1 (ACC = 15 + 25 = 40)
        0x20,  # MOV R1, ACC
        0x03,
        2,  # LOAD_IMM 2
        0x14,  # MUL R1 (ACC = 40 * 2 = 80)
        0x20,  # MOV R1, ACC (arg1 = 80)
        0x03,
        kernel.SYS_PRINT_NUM,  # LOAD_IMM 5 (SYS_PRINT_NUM)
        0x05,  # SYSCALL
        0x03,
        0,  # LOAD_IMM 0 (exit code)
        0x20,  # MOV R1, ACC
        0x03,
        kernel.SYS_EXIT,  # LOAD_IMM 2 (SYS_EXIT)
        0x05,  # SYSCALL
    ]
    task = kernel.load_task_code(
        name="Task_Math",
        code=code,
        priority=1,
        partition_size=32,
        base_address=64,
    )
    return task["task_id"]


def load_multitask_demo(ram: RAM, kernel: Kernel) -> tuple[int, int]:
    """Load two cooperative tasks that alternate execution using SYS_YIELD."""
    t0_code = [
        0x03,
        100,
        0x20,
        0x03,
        kernel.SYS_PRINT_NUM,
        0x05,  # Print 100
        0x03,
        kernel.SYS_YIELD,
        0x05,  # Yield to Task B
        0x03,
        101,
        0x20,
        0x03,
        kernel.SYS_PRINT_NUM,
        0x05,  # Print 101
        0x03,
        0,
        0x20,
        0x03,
        kernel.SYS_EXIT,
        0x05,  # Exit 0
    ]
    t1_code = [
        0x03,
        200,
        0x20,
        0x03,
        kernel.SYS_PRINT_NUM,
        0x05,  # Print 200
        0x03,
        kernel.SYS_YIELD,
        0x05,  # Yield to Task A
        0x03,
        201,
        0x20,
        0x03,
        kernel.SYS_PRINT_NUM,
        0x05,  # Print 201
        0x03,
        0,
        0x20,
        0x03,
        kernel.SYS_EXIT,
        0x05,  # Exit 0
    ]
    task0 = kernel.load_task_code(
        name="Task_A",
        code=t0_code,
        priority=1,
        partition_size=32,
        base_address=64,
    )
    task1 = kernel.load_task_code(
        name="Task_B",
        code=t1_code,
        priority=1,
        partition_size=32,
        base_address=96,
    )
    return task0["task_id"], task1["task_id"]


def load_all_demo(ram: RAM, kernel: Kernel) -> tuple[int, int]:
    """Load the full simulation suite with Task 0 (Counter) and Task 1 (Rogue Writer)."""
    pid0 = load_counter_demo(ram, kernel)
    pid1 = load_rogue_demo(ram, kernel)
    return pid0, pid1
