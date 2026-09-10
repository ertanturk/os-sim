> [!NOTE]
> **Educational Disclaimer**: This project is a software simulation developed strictly for educational and instructional purposes, not a real operating system. It is engineered to teach computer systems architecture, CPU micro-architecture, memory protection, interrupt-driven context switching, assembly programming, and preemptive multitasking operating system design principles.

---

<p align="center">
  <img src="demo.gif" alt="OS Simulator Demo" width="850">
</p>

---

## Table of Contents

- [Overview](#overview)
- [CPU Architecture](#cpu-architecture)
    - [Architectural Overview & Data Paths](#architectural-overview--data-paths)
    - [Register Set](#register-set)
    - [Arithmetic Logic Unit (ALU) & Status Flags](#arithmetic-logic-unit-alu--status-flags)
    - [Hardware Memory Protection Unit (MPU)](#hardware-memory-protection-unit-mpu)
    - [Interrupt Vector Table (IVT) & Hardware Traps](#interrupt-vector-table-ivt--hardware-traps)
    - [Instruction Set Architecture (ISA) Reference](#instruction-set-architecture-isa-reference)
- [Operating System & Kernel Design](#operating-system--kernel-design)
    - [System Memory Map](#system-memory-map)
    - [Context Switching & ISR Mailbox Mechanism](#context-switching--isr-mailbox-mechanism)
    - [Process Control Block (PCB) & Task Lifecycle](#process-control-block-pcb--task-lifecycle)
    - [Preemptive Task Scheduler](#preemptive-task-scheduler)
    - [System Call ABI & Interface](#system-call-abi--interface)
- [Writing & Executing Code](#writing--executing-code)
    - [1. Interactive Assembly Studio (`asm`)](#1-interactive-assembly-studio-asm)
    - [2. Writing Raw Machine Code (`code`)](#2-writing-raw-machine-code-code)
    - [3. Running Assembly Source Files (`exec` / CLI)](#3-running-assembly-source-files-exec--cli)
    - [4. Disassembling RAM (`disasm`)](#4-disassembling-ram-disasm)
    - [Assembly Language Reference & Directives](#assembly-language-reference--directives)
- [Included Example Programs](#included-example-programs)
- [Quickstart & CLI Reference](#quickstart--cli-reference)
    - [Command-Line Options](#command-line-options)
    - [Interactive Shell Commands](#interactive-shell-commands)
- [Testing & Quality Assurance](#testing--quality-assurance)

---

## Overview

`os-sim` is a simulated 8-bit computer architecture and multitasking operating system built from first principles in Python. It models the core components of real computing hardware:

1. **Physical Memory Bus**: 256 bytes of byte-addressable Random Access Memory (RAM) with memory-mapped mailboxes and write hooks.
2. **8-bit Accumulator CPU**: A Von Neumann processor core with status flags (`Z`, `C`), hardware traps, dual-mode execution (Kernel Mode vs. User Mode), and cycle-based hardware timer interrupts.
3. **Hardware Memory Protection Unit (MPU)**: Hardware base and limit registers preventing user processes from tampering with protected kernel memory, ISR trampolines, or other user tasks.
4. **Interrupt Vector Table (IVT)**: Low-memory vectoring for timer interrupts, software traps (`SYSCALL`), and hardware exceptions.
5. **Preemptive Kernel**: Process Control Blocks (PCBs), priority round-robin task scheduling, an assembly context-switch trampoline, and an expanded system call interface.
6. **Two-Pass Assembler & Disassembler**: Complete environment allowing users to write, assemble, and execute custom assembly language and machine code tasks.

---

## CPU Architecture

### Architectural Overview & Data Paths

The CPU implements a classic **8-bit Accumulator Von Neumann Architecture** where code and data reside in a single unified physical address space. Instructions and data are fetched over a shared memory bus.

```
+===================================================================+
|                          CPU CORE                                 |
|                                                                   |
|   +-----------------------+     +-----------------------------+   |
|   |   Registers           |     |  Arithmetic Logic Unit      |   |
|   |   - ACC (Accumulator) |<--->|  - 8-bit Arithmetic/Logic   |   |
|   |   - R1  (GP Register) |     |  - Zero Flag  (Z)           |   |
|   |   - R2  (GP Register) |     |  - Carry Flag (C)           |   |
|   |   - PC  (Prog Counter)|     +-----------------------------+   |
|   |   - SP  (Stack Pointer)                   |                   |
|   +-----------------------+                   v                   |
|               |                 +-----------------------------+   |
|               v                 |  Memory Protection Unit     |   |
|   +-----------------------+     |  - Base Register            |   |
|   | Control & Decoding    |     |  - Limit Register           |   |
|   | - Fetch-Decode-Execute|<--->|  - Kernel / User Mode Ring  |   |
|   | - Trap / Fault Vector |     +-----------------------------+   |
|   +-----------------------+                   |                   |
+===============|===============================|===================+
                |                               |
                +---------------+---------------+
                                | (Address & Data Bus)
                                v
+===================================================================+
|                    PHYSICAL RAM (256 BYTES)                       |
|   0x00 - 0x1F : Interrupt Vector Table (IVT)                      |
|   0x20 - 0x2F : Context-Switch Assembly ISR Trampoline            |
|   0x30 - 0x3F : Kernel Idle Task (Low-Power Wait Loop)            |
|   0x40 - 0xF9 : User Space Partitions (Code, Heap, Stack)         |
|   0xFA - 0xFB : Preemptive Context Switch Mailboxes (Old/New SP)  |
|   0xFC - 0xFF : High RAM Reserved Space                           |
+===================================================================+
```

### Register Set

The processor provides five primary architectural registers:

| Register  | Width  | Purpose                                                                                                    |
| :-------- | :----- | :--------------------------------------------------------------------------------------------------------- |
| **`ACC`** | 8-bit  | **Accumulator**. Primary arithmetic and logical destination; holds syscall IDs and return values.          |
| **`R1`**  | 8-bit  | **General-Purpose Register 1**. Auxiliary operand; passes `arg1` to system calls.                          |
| **`R2`**  | 8-bit  | **General-Purpose Register 2**. Auxiliary operand; passes `arg2` to system calls.                          |
| **`PC`**  | 16-bit | **Program Counter**. Points to the address of the next instruction byte to fetch from RAM.                 |
| **`SP`**  | 8-bit  | **Stack Pointer**. Points to the current stack top in RAM; stack decrements on push and increments on pop. |

### Arithmetic Logic Unit (ALU) & Status Flags

The ALU performs 8-bit operations. Calculations produce an 8-bit result (`& 0xFF`) and update the **Status Flags Register**:

- **Zero Flag (`Z`)**: Set to `1` (True) when the resulting value in `ACC` is exactly `0x00`; cleared to `0` (False) otherwise. Used for conditional branching (`JZ`).
- **Carry Flag (`C`)**: Set to `1` (True) when an arithmetic operation overflows `0xFF` (addition, multiplication) or underflows below `0` (subtraction); cleared to `0` otherwise.

### Hardware Memory Protection Unit (MPU)

The CPU includes hardware memory bounds enforcement to isolate user tasks from each other and protect the kernel:

- **Base Register**: Stores the lowest physical address accessible to the current user task.
- **Limit Register**: Stores the upper physical address limit (`[Base, Limit)`) accessible to the current user task.
- **Kernel Mode vs. User Mode**:
    - In **Kernel Mode** (`kernel_mode = True`), the CPU has unrestricted access to all 256 bytes of RAM and can execute privileged instructions (`HALT`, `IRET`).
    - In **User Mode** (`kernel_mode = False`), any memory read, write, or instruction fetch outside `[Base, Limit)` immediately triggers an MPU hardware trap:
        - **`Segmentation Fault: Illegal Memory Write`**
        - **`Segmentation Fault: Illegal Memory Read`**
        - **`Segmentation Fault: Illegal Instruction Fetch`**
        - **`Privilege Violation`** (attempting to execute `HALT` or `IRET` from user space)
    - The Kernel intercepts these faults, prints diagnostic messages, terminates the offending task with exit code `255`, and schedules the next eligible task.

### Interrupt Vector Table (IVT) & Hardware Traps

Physical memory range `0x00` - `0x1F` is reserved for interrupt and exception vectors:

| Vector Address | Interrupt Name   | Description                                                                               |
| :------------- | :--------------- | :---------------------------------------------------------------------------------------- |
| **`0x00`**     | `timer`          | Hardware timer interrupt. Fires every 50 CPU instruction cycles to trigger preemption.    |
| **`0x01`**     | `keyboard`       | Reserved for user input / character device hardware interrupt.                            |
| **`0x02`**     | `divide_by_zero` | Math error trap triggered when an instruction divides by zero (`DIV R1` where `R1 == 0`). |
| **`0x03`**     | `invalid_opcode` | Triggered when an unrecognized or illegal instruction opcode is decoded.                  |
| **`0x04`**     | `page_fault`     | MPU memory protection boundary violation trap.                                            |
| **`0x05`**     | `syscall`        | Software interrupt generated by the `SYSCALL` instruction to request kernel services.     |

### Instruction Set Architecture (ISA) Reference

The CPU features an instruction set consisting of 1-byte and 2-byte instructions:

|   Opcode   | Mnemonic & Syntax            | Size | Flags | Cycles | Operation Description                                  |
| :--------: | :--------------------------- | :--: | :---: | :----: | :----------------------------------------------------- |
| **`0x00`** | `HALT` / `HLT`               |  1B  |   -   |   1    | Halt processor execution (Kernel Mode only).           |
| **`0x01`** | `LOAD <addr>` / `LD`         |  2B  |   Z   |   2    | `ACC = RAM[addr]`; update `Z`.                         |
| **`0x02`** | `STORE <addr>` / `ST`        |  2B  |   -   |   2    | `RAM[addr] = ACC`.                                     |
| **`0x03`** | `LOAD_IMM <val>` / `LDI`     |  2B  |   Z   |   2    | `ACC = val & 0xFF`; update `Z`.                        |
| **`0x05`** | `SYSCALL` / `INT 5`          |  1B  |   -   |   2    | Software interrupt: save frame, jump to vector `0x05`. |
| **`0x0F`** | `IRET`                       |  1B  | Z, C  |   2    | Return from interrupt: pop Flags, R2, R1, ACC, PC.     |
| **`0x10`** | `ADD R1`                     |  1B  | Z, C  |   1    | `ACC = (ACC + R1) & 0xFF`.                             |
| **`0x11`** | `ADD R2`                     |  1B  | Z, C  |   1    | `ACC = (ACC + R2) & 0xFF`.                             |
| **`0x12`** | `SUB R1`                     |  1B  | Z, C  |   1    | `ACC = (ACC - R1) & 0xFF`.                             |
| **`0x13`** | `SUB R2`                     |  1B  | Z, C  |   1    | `ACC = (ACC - R2) & 0xFF`.                             |
| **`0x14`** | `MUL R1`                     |  1B  | Z, C  |   1    | `ACC = (ACC * R1) & 0xFF`.                             |
| **`0x15`** | `MUL R2`                     |  1B  | Z, C  |   1    | `ACC = (ACC * R2) & 0xFF`.                             |
| **`0x16`** | `DIV R1`                     |  1B  |   Z   |   1    | `ACC = ACC // R1`; trap if `R1 == 0`.                  |
| **`0x17`** | `DIV R2`                     |  1B  |   Z   |   1    | `ACC = ACC // R2`; trap if `R2 == 0`.                  |
| **`0x18`** | `AND R1`                     |  1B  |   Z   |   1    | `ACC = ACC & R1`.                                      |
| **`0x19`** | `AND R2`                     |  1B  |   Z   |   1    | `ACC = ACC & R2`.                                      |
| **`0x1A`** | `OR R1`                      |  1B  |   Z   |   1    | `ACC = ACC \| R1`.                                     |
| **`0x1B`** | `OR R2`                      |  1B  |   Z   |   1    | `ACC = ACC \| R2`.                                     |
| **`0x1C`** | `XOR R1`                     |  1B  |   Z   |   1    | `ACC = ACC ^ R1`.                                      |
| **`0x1D`** | `XOR R2`                     |  1B  |   Z   |   1    | `ACC = ACC ^ R2`.                                      |
| **`0x1E`** | `NOT` / `NOT ACC`            |  1B  |   Z   |   1    | `ACC = (~ACC) & 0xFF`.                                 |
| **`0x20`** | `MOV R1, ACC`                |  1B  |   -   |   1    | `R1 = ACC`.                                            |
| **`0x21`** | `MOV R2, ACC`                |  1B  |   -   |   1    | `R2 = ACC`.                                            |
| **`0x22`** | `MOV ACC, R1`                |  1B  |   -   |   1    | `ACC = R1`.                                            |
| **`0x23`** | `MOV ACC, R2`                |  1B  |   -   |   1    | `ACC = R2`.                                            |
| **`0x24`** | `MOV R1, R2`                 |  1B  |   -   |   1    | `R1 = R2`.                                             |
| **`0x25`** | `MOV R2, R1`                 |  1B  |   -   |   1    | `R2 = R1`.                                             |
| **`0x26`** | `MOV SP, ACC`                |  1B  |   -   |   1    | `SP = ACC`.                                            |
| **`0x27`** | `MOV ACC, SP`                |  1B  |   -   |   1    | `ACC = SP`.                                            |
| **`0x30`** | `JUMP <addr>` / `JMP`        |  2B  |   -   |   2    | `PC = addr`.                                           |
| **`0x31`** | `JZ <addr>` / `JUMP_IF_ZERO` |  2B  |   -   |   2    | If `Z == 1`, `PC = addr`.                              |

---

## Operating System & Kernel Design

### System Memory Map

The physical memory layout is partitioned into distinct subsystems:

```
Address Range   Size    Subsystem / Region Function
---------------------------------------------------------------------------------
0x00 - 0x1F     32 B    Interrupt Vector Table (IVT) Vectors
0x20 - 0x2F     16 B    Context-Switch Assembly ISR Trampoline
0x30 - 0x3F     16 B    Kernel Idle Task (infinite benign yield loop)
0x40 - 0xF9     186 B   Dynamic User Process Partitions (Code, Heap, Stack)
0xFA            1 B     Mailbox: Outgoing Task Saved Stack Pointer (OLD_SP)
0xFB            1 B     Mailbox: Incoming Task Target Stack Pointer (NEW_SP)
0xFC - 0xFF     4 B     High RAM Reserved Buffer
```

### Context Switching & ISR Mailbox Mechanism

Context switches occur without Python-level register tampering by utilizing an in-memory **Assembly ISR Trampoline** located at `0x20`:

```assembly
; Address 0x20: Context Switch Trampoline
MOV ACC, SP         ; 0x27       Copy current SP into ACC
STORE 0xFA          ; 0x02 0xFA  Store outgoing SP into MAILBOX_OLD_SP
LOAD 0xFB           ; 0x01 0xFB  Read incoming SP from MAILBOX_NEW_SP
MOV SP, ACC         ; 0x26       Set Stack Pointer to incoming task's stack
IRET                ; 0x0F       Restore Flags, R2, R1, ACC, PC from stack
```

When a timer interrupt fires:

1. The CPU hardware pushes the outgoing task's context onto its stack: `PC`, `ACC`, `R1`, `R2`, `Flags` (5 bytes).
2. Execution jumps to `0x20` (the ISR trampoline).
3. The trampoline writes the outgoing `SP` to address `0xFA`.
4. Writing to `0xFA` fires a hardware memory hook in `RAM`, triggering `kernel.schedule()`.
5. The kernel scheduler selects the next task from the ready queue, configures the CPU's MPU `base_address` and `limit_address`, and writes the incoming task's `task_sp` to `0xFB`.
6. Control returns to the ISR trampoline, which loads the incoming SP and executes `IRET`, restoring the incoming task's state.

### Process Control Block (PCB) & Task Lifecycle

Every process is represented by a Process Control Block (PCB):

```python
PCB = {
    "task_id": 0,           # Unique Process Identifier (PID)
    "name": "Task_Name",    # Human-readable identifier
    "priority": 1,          # Scheduling priority (higher = prioritized)
    "state": TaskState,     # READY, RUNNING, SLEEPING, BLOCKED, TERMINATED
    "entry_point": 0x40,    # Instruction start address
    "base": 0x40,           # MPU Lower memory boundary
    "limit": 0x60,          # MPU Upper memory boundary
    "task_sp": 0x5B,        # Saved Stack Pointer
    "stack_top": 0x5F,      # Initial top of stack
    "sleep_ticks": 0,       # Ticks remaining for sleeping tasks
    "wait_pid": None,       # PID this task is blocked waiting on
    "exit_code": None,      # Return code after termination
}
```

```
     [Create Task]
           |
           v
       +-------+      Scheduler Pick
       | READY | -----------------------> +---------+
       +-------+                          | RUNNING |
           ^   <------------------------- +---------+
           |       Timer Preempt / Yield        |
           |                                    |
           | Wakeup / Target Exits              | SYS_SLEEP / SYS_WAIT
           |                                    v
     +------------+                      +-----------------+
     |  SLEEPING  |                      | BLOCKED/SLEEPING|
     +------------+                      +-----------------+
                                                |
                                                | SYS_EXIT / Fault
                                                v
                                         +--------------+
                                         |  TERMINATED  |
                                         +--------------+
```

### Preemptive Task Scheduler

The Kernel scheduler (`src.kernel.Scheduler`) supports three selectable policies:

- **`priority_round_robin`** _(Default)_: Partitions the ready queue by task priority; tasks with the highest priority share CPU time round-robin.
- **`round_robin`**: Pure round-robin scheduling across all ready tasks regardless of priority.
- **`fifo`**: First-In, First-Out queue ordering.

Timer ticks decrement `sleep_ticks` for sleeping tasks on every scheduling quantum. When all user tasks are sleeping, the kernel activates an internal low-power **Idle Task** at `0x30`.

### System Call ABI & Interface

User tasks invoke kernel services by loading the system call ID into `ACC`, passing arguments in `R1` and `R2`, and executing `SYSCALL` (or `INT 5`):

|    ID    | Syscall Constant | Arguments               | Return Value (ACC) | Description                                              |
| :------: | :--------------- | :---------------------- | :----------------: | :------------------------------------------------------- |
| **`1`**  | `SYS_YIELD`      | None                    |         -          | Voluntarily yields the remainder of the CPU timeslice.   |
| **`2`**  | `SYS_EXIT`       | `R1 = Exit code`        |         -          | Terminates the calling process with exit status code.    |
| **`3`**  | `SYS_SLEEP`      | `R1 = Ticks`            |        `0`         | Puts the calling task to sleep for N timer ticks.        |
| **`4`**  | `SYS_GETPID`     | None                    |       `PID`        | Returns the calling task's Process ID.                   |
| **`5`**  | `SYS_PRINT_NUM`  | `R1 = Number`           |        `0`         | Prints an 8-bit integer (`0-255`) to the kernel console. |
| **`6`**  | `SYS_PRINT_CHAR` | `R1 = ASCII`            |        `0`         | Prints a single ASCII character to the kernel console.   |
| **`7`**  | `SYS_PRINT_STR`  | `R1 = Addr, R2 = Len`   |       Length       | Prints string from RAM within MPU bounds.                |
| **`8`**  | `SYS_SPAWN`      | `R1 = Entry, R2 = Prio` |      New PID       | Allocates a partition and registers a child process.     |
| **`9`**  | `SYS_WAIT`       | `R1 = Target PID`       |     Exit Code      | Blocks calling task until target PID terminates.         |
| **`10`** | `SYS_KILL`       | `R1 = Target PID`       |    `0` or `255`    | Terminates a target task by PID.                         |
| **`11`** | `SYS_GET_TICKS`  | None                    |     Tick count     | Returns total elapsed system timer ticks.                |
| **`12`** | `SYS_ALLOC`      | `R1 = Bytes`            |     Heap Addr      | Allocates heap memory within the task partition.         |

---

## Writing & Executing Code

Users can write, assemble, and execute custom machine code and assembly programs directly in `os-sim` using four distinct methods:

### 1. Interactive Assembly Studio (`asm`)

Type `asm` in the interactive shell to open the multi-line assembly development environment:

```text
os-sim> asm
╭────────────────────────────── OS-SIM Assembly Studio ──────────────────────────────╮
│ Interactive Assembly Studio                                                        │
│ Enter assembly instructions line-by-line. Supports labels, directives, & syscalls. │
│ Target Memory Partition: [0x40, 0x60)                                              │
│                                                                                    │
│ Commands:                                                                          │
│   RUN    - Assemble code, create task, and execute simulation loop                 │
│   LOAD   - Assemble and register task into READY state (step manually)             │
│   LIST   - Show lines entered so far                                               │
│   CLEAR  - Empty current code buffer                                               │
│   HELP   - Display assembly instruction & syscall cheat sheet                      │
│   EXIT   - Return to OS shell without assembling                                   │
╰────────────────────────────────────────────────────────────────────────────────────╯

asm [0x40:01]> LOAD_IMM 15
asm [0x40:02]> MOV R1, ACC
asm [0x40:03]> LOAD_IMM 25
asm [0x40:04]> ADD R1
asm [0x40:05]> MOV R1, ACC
asm [0x40:06]> LOAD_IMM SYS_PRINT_NUM
asm [0x40:07]> SYSCALL
asm [0x40:08]> LOAD_IMM 0
asm [0x40:09]> MOV R1, ACC
asm [0x40:10]> LOAD_IMM SYS_EXIT
asm [0x40:11]> SYSCALL
asm [0x40:12]> RUN
```

The system assembles your code, displays a colorized bytecode listing, allocates an isolated memory partition, registers the task PCB, launches the scheduler, and prints console output:

```text
[Kernel Console] 40
Task Task_UserASM exited with code 0
✓ Simulation run finished (11 cycles executed). CPU Halted: True
```

### 2. Writing Raw Machine Code (`code`)

You can write raw machine code bytes directly in the shell using the `code` command:

```bash
os-sim> code MyCounter 0x03 0x01 0x10 0x20 0x03 0x01 0x05 0x30 0x40
✓ Loaded task 'MyCounter' (PID 0) @ [0x40, 0x60), Entry: 0x40, Size: 9 bytes.

os-sim> run 20
os-sim> step 5
```

### 3. Running Assembly Source Files (`exec` / CLI)

You can write `.asm` files in any text editor and execute them:

**From inside the interactive shell:**

```bash
os-sim> exec examples/hello.asm
os-sim> load-asm examples/fibonacci.asm
os-sim> step 10
```

**Directly from the terminal:**

```bash
# Assemble and run directly with output
uv run python cli.py asm examples/hello.asm --quick --batch

# Run via the main --asm option
uv run python cli.py --asm examples/math.asm --quick --batch
```

### 4. Disassembling RAM (`disasm`)

Inspect raw memory bytes decoded into assembly mnemonics:

```bash
os-sim> disasm 0x40 16
```

### Assembly Language Reference & Directives

The assembler supports standard assembly language features:

- **Labels**: `label_name:` defines an address. Can be referenced forward and backward (`JMP loop`, `LOAD_IMM msg`).
- **Comments**: Anywhere on a line using `;`, `//`, or `#`.
- **Numeric Literals**:
    - Decimal: `10`, `42`
    - Hexadecimal: `0x10`, `$10`, `10h`
    - Binary: `0b1010`, `%1010`
    - Character: `'A'`, `'\n'`
- **Directives**:
    - `.ORG <addr>`: Sets the assembly location counter / base address.
    - `DB <b0>, <b1>...` / `.BYTE`: Defines raw byte literals.
    - `.ASCII "string"`: Defines an ASCII string literal.
    - `.ASCIIZ "string"` / `.STRING`: Defines a null-terminated (`\0`) ASCII string.
    - `<NAME> EQU <val>` / `.EQU <NAME>, <val>`: Defines symbolic constants.
- **Built-in Symbols**: All syscalls (`SYS_YIELD`, `SYS_PRINT_NUM`, `SYS_PRINT_STR`, `SYS_EXIT`, etc.) and IVT constants (`IVT_TIMER`, `IVT_SYSCALL`) are built-in symbols.

---

## Included Example Programs

The `examples/` directory contains educational assembly programs:

### 1. `examples/hello.asm` - String Output System Call

Demonstrates loading string memory addresses into registers and invoking `SYS_PRINT_STR`:

```assembly
    LOAD_IMM msg            ; ACC = address of string
    MOV R1, ACC             ; R1 = arg1 (string address in RAM)
    LOAD_IMM 21             ; ACC = string length
    MOV R2, ACC             ; R2 = arg2 (string length)
    LOAD_IMM SYS_PRINT_STR  ; Syscall ID 7: SYS_PRINT_STR
    SYSCALL                 ; Invoke OS kernel trap

    LOAD_IMM 0              ; Exit code 0
    MOV R1, ACC             ; R1 = exit code
    LOAD_IMM SYS_EXIT       ; Syscall ID 2: SYS_EXIT
    SYSCALL                 ; Terminate task

msg:
    .ascii "Hello, OS Simulator!\n"
```

### 2. `examples/math.asm` - Arithmetic & ALU Calculations

Performs arithmetic `(15 + 25) * 2 = 80` and prints the output:

```assembly
    LOAD_IMM 15             ; ACC = 15
    MOV R1, ACC             ; R1 = 15
    LOAD_IMM 25             ; ACC = 25
    ADD R1                  ; ACC = 25 + 15 = 40
    MOV R1, ACC             ; R1 = 40

    LOAD_IMM 2              ; ACC = 2
    MUL R1                  ; ACC = 2 * 40 = 80
    MOV R1, ACC             ; R1 = 80 (arg1 for SYS_PRINT_NUM)

    LOAD_IMM SYS_PRINT_NUM  ; Syscall ID 5: SYS_PRINT_NUM
    SYSCALL                 ; Prints 80 to kernel console

    LOAD_IMM 0
    MOV R1, ACC
    LOAD_IMM SYS_EXIT
    SYSCALL
```

### 3. `examples/fibonacci.asm` - Iterative Sequence with Memory Variables

Demonstrates storing and loading RAM variables while computing the Fibonacci sequence:

```assembly
    LOAD_IMM 1
    STORE prev
    LOAD_IMM 1
    STORE curr

fib_loop:
    LOAD curr
    MOV R1, ACC
    LOAD_IMM SYS_PRINT_NUM
    SYSCALL

    LOAD prev
    MOV R1, ACC
    LOAD curr
    ADD R1
    STORE next

    LOAD curr
    STORE prev
    LOAD next
    STORE curr

    LOAD_IMM SYS_YIELD
    SYSCALL

    JMP fib_loop

prev: DB 0
curr: DB 0
next: DB 0
```

### 4. `examples/counter.asm` - Cooperative Multitasking Counter

Increments register `R1` and voluntarily yields CPU timeslices via `SYS_YIELD`:

```assembly
loop:
    LOAD_IMM 1
    ADD R1
    MOV R1, ACC
    LOAD_IMM SYS_YIELD
    SYSCALL
    JMP loop
```

### 5. `examples/rogue.asm` - Memory Protection Fault Demonstration

Attempts an illegal write into Kernel IVT memory space (`0x10`) to demonstrate MPU traps:

```assembly
    LOAD_IMM 0xEE
    STORE 0x10              ; Attempt write to protected kernel IVT vector
                            ; MPU traps this with Segmentation Fault!
    LOAD_IMM SYS_EXIT
    SYSCALL
```

---

## Quickstart & CLI Reference

### Command-Line Options

```bash
# Boot into interactive OS shell
uv run python cli.py

# Boot with custom broadcast banner text
uv run python cli.py --say "Welcome to Educational OS Simulator"

# Assemble and run an assembly file in batch mode
uv run python cli.py asm examples/hello.asm --quick --batch

# Launch interactive Assembly Studio
uv run python cli.py asm

# Run built-in demo suite in batch mode
uv run python cli.py demo all --quick --batch
```

### Interactive Shell Commands

Once booted, the `os-sim>` prompt supports the following commands:

| Command                    | Arguments                                       | Description                                                                                       |
| :------------------------- | :---------------------------------------------- | :------------------------------------------------------------------------------------------------ |
| **`help`** / **`?`**       |                                                 | Display command reference manual.                                                                 |
| **`status`**               |                                                 | Show OS subsystem health, ticks, cycle count, and task counts.                                    |
| **`cpu`**                  |                                                 | Display detailed CPU registers (`ACC`, `R1`, `R2`, `PC`, `SP`), flags (`Z`, `C`), and MPU bounds. |
| **`mem`** / **`ram`**      | `[start=0] [len=256]`                           | Inspect colored RAM hex dump with tagged memory regions.                                          |
| **`ps`** / **`tasks`**     |                                                 | List all Process Control Blocks (PCBs) and task lifecycle states.                                 |
| **`asm`**                  | `[name]`                                        | Launch the **Interactive Assembly Studio** to write and run code.                                 |
| **`code`**                 | `<name> <b0> <b1>...`                           | Load machine code bytes into a new task PCB and RAM partition.                                    |
| **`exec`** / **`run-asm`** | `<file.asm> [steps=100]`                        | Assemble an `.asm` file and execute immediately.                                                  |
| **`load-asm`**             | `<file.asm> [prio] [size]`                      | Assemble an `.asm` file and register task in `READY` state.                                       |
| **`disasm`**               | `[start=0x40] [len=16]`                         | Disassemble raw RAM bytes into human-readable instructions.                                       |
| **`demo`**                 | `<counter\|rogue\|hello\|math\|multitask\|all>` | Load a built-in demonstration task suite.                                                         |
| **`run`**                  | `[steps=100]`                                   | Execute the kernel preemptive multitasking loop.                                                  |
| **`step`**                 | `[count=1]`                                     | Execute 1 or more CPU instruction cycles.                                                         |
| **`load`**                 | `<addr> <b0> <b1>...`                           | Write raw machine code bytes to a specified RAM address.                                          |
| **`read`**                 | `<addr>`                                        | Read single byte value at specified RAM address.                                                  |
| **`write`**                | `<addr> <val>`                                  | Write single byte value to specified RAM address.                                                 |
| **`spawn`**                | `<name> <entry> [base] [size] [prio]`           | Forge and register a new task PCB.                                                                |
| **`kill`**                 | `<pid>`                                         | Terminate a task using `sys_kill`.                                                                |
| **`dmesg`** / **`logs`**   |                                                 | View kernel console output buffer from `SYS_PRINT_*` syscalls.                                    |
| **`say`**                  | `<text>`                                        | Animate typewriter text broadcast.                                                                |
| **`reboot`**               | `[custom_text]`                                 | Reset simulation and replay POST boot sequence.                                                   |
| **`clear`**                |                                                 | Clear the terminal display.                                                                       |
| **`exit`**                 |                                                 | Power down the operating system simulator.                                                        |
