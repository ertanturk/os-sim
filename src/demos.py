"""Built-in demo programs and task loaders for OS simulator."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.kernel import Kernel
    from src.ram import RAM


def load_counter_demo(ram: RAM, kernel: Kernel) -> int:
    """Load a counter / cooperative yield loop task.

    Task 0 continuously increments R1 by 1 and yields CPU via SYS_YIELD (0x01).
    """
    # Bytecode:
    # 0x03, 0x01  -> LOAD_IMM 1
    # 0x10        -> ADD R1
    # 0x20        -> MOV R1, ACC
    # 0x03, 0x01  -> LOAD_IMM 1 (SYS_YIELD)
    # 0x05        -> SYSCALL
    # 0x30, 0x40  -> JUMP 0x40 (64)
    code = [0x03, 0x01, 0x10, 0x20, 0x03, 0x01, 0x05, 0x30, 0x40]
    base = 64
    limit = 96
    entry_point = 64
    stack_top = 95

    for i, byte in enumerate(code):
        ram.write(base + i, byte)

    kernel.create_task(
        task_id=0,
        name="Task_Counter",
        priority=1,
        entry_point=entry_point,
        stack_top=stack_top,
        base=base,
        limit=limit,
    )
    return 0


def load_rogue_demo(ram: RAM, kernel: Kernel) -> int:
    """Load a rogue writer task that attempts illegal memory access.

    Task 1 tries to write 0xAA into address 0x40 (Task 0's memory),
    triggering a hardware memory protection fault.
    """
    # Bytecode:
    # 0x03, 0xAA  -> LOAD_IMM 0xAA
    # 0x02, 0x40  -> STORE 0x40 (Illegal write outside [96, 128))
    code = [0x03, 0xAA, 0x02, 0x40]
    base = 96
    limit = 128
    entry_point = 96
    stack_top = 127

    for i, byte in enumerate(code):
        ram.write(base + i, byte)

    kernel.create_task(
        task_id=1,
        name="Task_Rogue_Writer",
        priority=1,
        entry_point=entry_point,
        stack_top=stack_top,
        base=base,
        limit=limit,
    )
    return 1


def load_hello_demo(ram: RAM, kernel: Kernel, message: str = "Hello OS!") -> int:
    """Load a task that prints a string using the SYS_PRINT_STR system call."""
    base = 64
    limit = 96
    entry_point = 64
    stack_top = 95
    str_addr = 80

    msg_bytes = message.encode("ascii", errors="replace")[:14] + b"\x00"
    for i, b in enumerate(msg_bytes):
        ram.write(str_addr + i, b)

    # Bytecode:
    # LOAD_IMM str_addr -> MOV R1, ACC
    # LOAD_IMM len(msg_bytes)-1 -> MOV R2, ACC
    # LOAD_IMM 7 (SYS_PRINT_STR) -> SYSCALL
    # LOAD_IMM 0 -> MOV R1, ACC
    # LOAD_IMM 2 (SYS_EXIT) -> SYSCALL
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

    for i, byte in enumerate(code):
        ram.write(base + i, byte)

    kernel.create_task(
        task_id=0,
        name="Task_Hello",
        priority=1,
        entry_point=entry_point,
        stack_top=stack_top,
        base=base,
        limit=limit,
    )
    return 0


def load_math_demo(ram: RAM, kernel: Kernel) -> int:
    """Load a task that performs arithmetic calculations and prints the result via SYS_PRINT_NUM.

    Calculates: (15 + 25) * 2 = 80, prints 80, and exits.
    """
    base = 64
    limit = 96
    entry_point = 64
    stack_top = 95

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

    for i, byte in enumerate(code):
        ram.write(base + i, byte)

    kernel.create_task(
        task_id=0,
        name="Task_Math",
        priority=1,
        entry_point=entry_point,
        stack_top=stack_top,
        base=base,
        limit=limit,
    )
    return 0


def load_multitask_demo(ram: RAM, kernel: Kernel) -> tuple[int, int]:
    """Load two cooperative tasks that alternate execution using SYS_YIELD."""
    # Task A at 64
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
    for i, b in enumerate(t0_code):
        ram.write(64 + i, b)

    # Task B at 96
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
    for i, b in enumerate(t1_code):
        ram.write(96 + i, b)

    kernel.create_task(0, "Task_A", 1, 64, 95, 64, 96)
    kernel.create_task(1, "Task_B", 1, 96, 127, 96, 128)
    return 0, 1


def load_all_demo(ram: RAM, kernel: Kernel) -> tuple[int, int]:
    """Load the full simulation suite with Task 0 (Counter) and Task 1 (Rogue Writer)."""
    pid0 = load_counter_demo(ram, kernel)
    pid1 = load_rogue_demo(ram, kernel)
    return pid0, pid1
