"""Interactive CLI and OS simulator emulator with startup animation and shell."""

from __future__ import annotations

import shlex
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from src.assembler import (
    AssemblyError,
    AssemblyResult,
    assemble,
    disassemble,
)
from src.bootloader import Bootloader
from src.cpu import CPU
from src.demos import (
    load_all_demo,
    load_counter_demo,
    load_hello_demo,
    load_math_demo,
    load_multitask_demo,
    load_rogue_demo,
)
from src.kernel import PCB, Kernel, TaskState
from src.ram import RAM

console = Console()
app = typer.Typer(
    help="OS Simulator - 8-bit Operating System emulator CLI.",
    invoke_without_command=True,
)

ASCII_BANNER = r"""
 ██████╗ ███████╗      ███████╗██╗███╗   ███╗
██╔═══██╗██╔════╝      ██╔════╝██║████╗ ████║
██║   ██║███████╗█████╗███████╗██║██╔████╔██║
██║   ██║╚════██║╚════╝╚════██║██║██║╚██╔╝██║
╚██████╔╝███████║      ███████║██║██║ ╚═╝ ██║
 ╚═════╝ ╚══════╝      ╚══════╝╚═╝╚═╝     ╚═╝
"""


def parse_int(val: str) -> int:
    """Parse integer from hex (0x..) or decimal string."""
    clean = val.strip()
    if clean.lower().startswith("0x"):
        return int(clean, 16)
    return int(clean)


def typewriter_text(
    text: str,
    delay: float = 0.02,
    style: str = "bold green",
    console_instance: Console | None = None,
) -> None:
    """Simulate typewriter animation for text display."""
    target_console = console_instance or console
    for char in text:
        target_console.print(char, end="", style=style)
        if delay > 0:
            time.sleep(delay)
    target_console.print()


class OSSimulatorSession:
    """Encapsulates the state and operations of an active OS simulation session."""

    def __init__(self, speed: float = 1.0, animate: bool = True):
        self.speed = speed
        self.animate = animate
        self.ram = RAM(256)
        self.cpu = CPU(self.ram)
        self.kernel = Kernel(self.ram, self.cpu)
        self.bootloader = Bootloader(self.ram, self.cpu, self.kernel)
        self.is_booted: bool = False
        self.is_started: bool = False

    def _sleep(self, seconds: float) -> None:
        """Helper to sleep taking speed multiplier and animation flag into account."""
        if not self.animate or self.speed <= 0:
            return
        time.sleep(max(0.0, seconds / self.speed))

    def play_startup_animation(self, custom_text: str | None = None) -> None:
        """Render OS boot sequence with POST checks, loading bar, and user text."""
        # Render centered ASCII banner and system subtitle
        banner_text = Text.assemble(
            (ASCII_BANNER.strip("\n"), "bold cyan"),
            ("\n\n[ 8-Bit Architecture Educational Operating System Simulator ]\n", "bold green"),
            justify="center",
        )
        banner_panel = Panel(
            Align.center(banner_text),
            border_style="bright_blue",
            subtitle="[dim]Kernel Version 0.0.1 (x86_8-bit Von Neumann)[/dim]",
            subtitle_align="center",
        )
        console.print(banner_panel)
        self._sleep(0.3)

        # Execute hardware power-on self-test checks
        post_checks = [
            ("Detecting 8-Bit Accumulator CPU Core", "2 Registers (R1, R2) + ACC + SP + PC [OK]"),
            ("Probing Physical Memory Bus", f"{len(self.ram.memory)} Bytes RAM Initialized [OK]"),
            ("Testing Arithmetic Logic Unit (ALU)", "Zero (Z) and Carry (C) Flags Verified [OK]"),
            ("Initializing Interrupt Vector Table", "IVT Vectors Configured at 0x00 [OK]"),
            ("Writing Assembly ISR Trampoline", "Context-Switch Trampoline Installed @ 0x20 [OK]"),
            ("Configuring Preemptive Scheduler", "Priority Round-Robin Policy Engaged [OK]"),
            ("Setting Up Kernel Memory Bounds", "Protected Range [0x00 - 0x3F] Locked [OK]"),
        ]

        console.print("[bold yellow]>>> Initiating Hardware Power-On Self-Test (POST)...[/bold yellow]")
        for stage, status in post_checks:
            self._sleep(0.08)
            console.print(f"  [bold blue]•[/bold blue] {stage:<42} [bold green]{status}[/bold green]")

        # Run bootstrapping progress animation
        boot_msg = custom_text if custom_text else "OS-SIM Operating System Ready"
        console.print()

        if self.animate and self.speed > 0:
            with Progress(
                SpinnerColumn("dots", style="bold cyan"),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(bar_width=40, style="blue", complete_style="bold green"),
                TaskProgressColumn(),
                console=console,
                transient=False,
            ) as progress:
                load_task = progress.add_task("[cyan]Bootstrapping Kernel Subsystems...", total=100)
                stages = [
                    (25, "[cyan]Binding Interrupt Service Routines..."),
                    (50, "[cyan]Mounting Virtual Process Space..."),
                    (75, "[cyan]Setting up Hardware Mailboxes (0xFA, 0xFB)..."),
                    (100, f"[bold green]{boot_msg}"),
                ]
                for target, desc in stages:
                    progress.update(load_task, description=desc)
                    while progress.tasks[0].completed < target:
                        self._sleep(0.03)
                        progress.advance(load_task, 5)
        else:
            console.print(f"[bold green]✓ Kernel Loaded:[bold green] {boot_msg}")

        # Render centered user broadcast message banner
        if custom_text:
            console.print()
            user_text = Text(custom_text, style="bold yellow", justify="center")
            user_msg_panel = Panel(
                Align.center(user_text),
                title="[bold magenta]>>> USER BROADCAST TEXT <<<[/bold magenta]",
                title_align="center",
                border_style="yellow",
            )
            console.print(user_msg_panel)

        # Initialize IVT and install kernel ISR
        self.bootloader.load_ivt()
        self.kernel.install_isr()
        self.is_booted = True

        self._sleep(0.2)
        console.print("\n[bold green]✓ Operating System successfully booted into interactive mode![/bold green]\n")

    def show_status(self) -> None:
        """Display summary table of the OS state."""
        table = Table(title="OS-SIM System Status", border_style="cyan")
        table.add_column("Subsystem", style="bold yellow")
        table.add_column("Configuration / Current State", style="bold white")

        table.add_row("CPU Architecture", "8-bit Accumulator with GP Registers (R1, R2)")
        table.add_row("Execution Privilege", "KERNEL MODE" if self.cpu.kernel_mode else "USER MODE")
        table.add_row("CPU Status", "[bold red]HALTED[/bold red]" if self.cpu.halted else "[bold green]ACTIVE[/bold green]")
        table.add_row("CPU Cycles", str(self.cpu.cycle_count))
        table.add_row("System Ticks", str(self.kernel.system_ticks))
        table.add_row("Total RAM", f"{len(self.ram.memory)} Bytes")
        table.add_row("Active Tasks", str(len([t for t in self.kernel.tasks if t['state'] != TaskState.TERMINATED])))
        table.add_row("Terminated Tasks", str(len(self.kernel.terminated_tasks)))
        table.add_row("Scheduler Policy", self.kernel.scheduler.policy.value)
        console.print(table)

    def show_cpu(self) -> None:
        """Display detailed CPU registers, flags, and memory bounds."""
        reg_table = Table(title="CPU Register State", border_style="green")
        reg_table.add_column("Register", style="bold cyan")
        reg_table.add_column("Hex", style="bold yellow")
        reg_table.add_column("Decimal", style="bold white")
        reg_table.add_column("Binary", style="dim")

        for reg, val in self.cpu.registers.items():
            reg_table.add_row(
                reg,
                f"0x{val:02X}",
                str(val),
                f"{val:08b}" if reg != "PC" else f"{val:016b}",
            )
        console.print(reg_table)

        flag_table = Table(title="ALU Status Flags", border_style="magenta")
        flag_table.add_column("Flag", style="bold cyan")
        flag_table.add_column("Status", style="bold white")
        flag_table.add_column("Meaning", style="dim")

        flag_table.add_row("Z (Zero)", "1 (TRUE)" if self.cpu.flags["Z"] else "0 (FALSE)", "Set when ALU result is 0")
        flag_table.add_row("C (Carry)", "1 (TRUE)" if self.cpu.flags["C"] else "0 (FALSE)", "Set on ALU arithmetic overflow/underflow")
        console.print(flag_table)

        bounds_table = Table(title="Hardware Memory Protection Unit (MPU)", border_style="yellow")
        bounds_table.add_column("Property", style="bold cyan")
        bounds_table.add_column("Value", style="bold white")
        bounds_table.add_row("Base Address", f"0x{self.cpu.base_address:02X} ({self.cpu.base_address})")
        bounds_table.add_row("Limit Address", f"0x{self.cpu.limit_address:02X} ({self.cpu.limit_address})")
        bounds_table.add_row("Kernel Mode", str(self.cpu.kernel_mode))
        bounds_table.add_row("Interrupts Enabled", str(self.cpu.interrupts_enabled))
        console.print(bounds_table)

    def show_memory(self, start: int = 0, length: int = 256) -> None:
        """Display colored hex dump of RAM."""
        start = max(0, min(start, len(self.ram.memory) - 1))
        end = min(len(self.ram.memory), start + length)

        table = Table(
            title=f"RAM Hex Dump (0x{start:02X} - 0x{end - 1:02X})",
            border_style="blue",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Offset", style="bold yellow")
        for i in range(16):
            table.add_column(f"{i:02X}", justify="center")
        table.add_column("ASCII", justify="left", style="bold green")
        table.add_column("Region Tag", justify="left")

        for row_base in range(start, end, 16):
            row_vals: list[str] = []
            ascii_chars: list[str] = []

            for col in range(16):
                addr = row_base + col
                if addr < end:
                    b = self.ram.read(addr)
                    # Color based on memory map regions
                    if addr < 0x20:
                        row_vals.append(f"[cyan]{b:02X}[/cyan]")
                    elif addr < 0x30:
                        row_vals.append(f"[magenta]{b:02X}[/magenta]")
                    elif addr < 0x40:
                        row_vals.append(f"[blue]{b:02X}[/blue]")
                    elif addr in (Kernel.MAILBOX_OLD_SP, Kernel.MAILBOX_NEW_SP):
                        row_vals.append(f"[yellow]{b:02X}[/yellow]")
                    elif addr >= 0xFC:
                        row_vals.append(f"[dim red]{b:02X}[/dim red]")
                    else:
                        row_vals.append(f"[green]{b:02X}[/green]" if b != 0 else f"[dim]{b:02X}[/dim]")

                    ascii_chars.append(chr(b) if 32 <= b <= 126 else ".")
                else:
                    row_vals.append("  ")
                    ascii_chars.append(" ")

            # Tag region
            if row_base < 0x20:
                tag = "[cyan]IVT Vectors[/cyan]"
            elif row_base < 0x30:
                tag = "[magenta]ISR Trampoline[/magenta]"
            elif row_base < 0x40:
                tag = "[blue]Idle Task[/blue]"
            elif row_base >= 0xF0:
                tag = "[yellow]Mailbox / High RAM[/yellow]"
            else:
                tag = "[green]User Space[/green]"

            table.add_row(f"0x{row_base:02X}:", *row_vals, "".join(ascii_chars), tag)

        console.print(table)
        console.print("[dim]Regions: [cyan]IVT (0x00-1F)[/cyan] | [magenta]ISR (0x20-2F)[/magenta] | [blue]Idle (0x30-3F)[/blue] | [green]User (0x40-F9)[/green] | [yellow]Mailbox (0xFA-FB)[/yellow][/dim]")

    def show_tasks(self) -> None:
        """Display list of active and terminated tasks."""
        table = Table(title="Process Table (PCB)", border_style="magenta")
        table.add_column("PID", style="bold cyan", justify="right")
        table.add_column("Name", style="bold white")
        table.add_column("Priority", justify="right")
        table.add_column("State", style="bold")
        table.add_column("SP", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Memory Bounds [Base, Limit)", style="yellow")
        table.add_column("Sleep / Wait", style="dim")
        table.add_column("Exit Code", style="bold red")

        all_tasks = self.kernel.tasks + self.kernel.terminated_tasks
        if not all_tasks:
            console.print("[yellow]No tasks currently registered in the Kernel.[/yellow]")
            return

        for t in all_tasks:
            state = t["state"]
            if state == TaskState.RUNNING:
                state_str = "[bold green]RUNNING[/bold green]"
            elif state == TaskState.READY:
                state_str = "[cyan]READY[/cyan]"
            elif state == TaskState.SLEEPING:
                state_str = "[yellow]SLEEPING[/yellow]"
            elif state == TaskState.BLOCKED:
                state_str = "[magenta]BLOCKED[/magenta]"
            else:
                state_str = "[dim red]TERMINATED[/dim red]"

            extra = ""
            if t["sleep_ticks"] > 0:
                extra = f"Sleep: {t['sleep_ticks']}t"
            elif t["wait_pid"] is not None:
                extra = f"Wait: PID {t['wait_pid']}"

            table.add_row(
                str(t["task_id"]),
                t["task_name"],
                str(t["task_priority"]),
                state_str,
                f"0x{t['task_sp']:02X}",
                f"0x{t['entry_point']:02X}",
                f"[0x{t['base']:02X}, 0x{t['limit']:02X})",
                extra,
                str(t["exit_code"]) if t["exit_code"] is not None else "-",
            )
        console.print(table)

    def load_demo(self, demo_name: str) -> None:
        """Load a built-in demonstration task suite."""
        name = demo_name.lower().strip()
        if name in ("counter", "count"):
            pid = load_counter_demo(self.ram, self.kernel)
            console.print(f"[bold green]Loaded 'counter' demo (Task {pid}) at 0x40. Continuously increments R1 and yields.[/bold green]")
        elif name in ("rogue", "fault"):
            pid = load_rogue_demo(self.ram, self.kernel)
            console.print(f"[bold green]Loaded 'rogue' demo (Task {pid}) at 0x60. Attempts illegal memory write to trigger fault.[/bold green]")
        elif name in ("hello", "print"):
            pid = load_hello_demo(self.ram, self.kernel, "Hello OS!")
            console.print(f"[bold green]Loaded 'hello' demo (Task {pid}) at 0x40. Invokes SYS_PRINT_STR syscall.[/bold green]")
        elif name in ("math", "alu"):
            pid = load_math_demo(self.ram, self.kernel)
            console.print(f"[bold green]Loaded 'math' demo (Task {pid}) at 0x40. Computes (15 + 25) * 2 = 80 and prints it.[/bold green]")
        elif name in ("multitask", "coop"):
            p1, p2 = load_multitask_demo(self.ram, self.kernel)
            console.print(f"[bold green]Loaded 'multitask' demo (Tasks {p1} & {p2}). Alternates execution via SYS_YIELD.[/bold green]")
        elif name in ("all", "suite"):
            p1, p2 = load_all_demo(self.ram, self.kernel)
            console.print(f"[bold green]Loaded 'all' demo suite (Task {p1}: Counter, Task {p2}: Rogue Writer).[/bold green]")
        else:
            console.print(f"[red]Unknown demo '{demo_name}'. Available: counter, rogue, hello, math, multitask, all[/red]")

    def load_code_task(
        self,
        name: str,
        code: list[int],
        priority: int = 1,
        size: int = 32,
        base_addr: int | None = None,
    ) -> PCB:
        """Load machine code bytes into a newly forged task PCB and RAM partition."""
        pcb = self.kernel.load_task_code(
            name=name,
            code=code,
            priority=priority,
            partition_size=size,
            base_address=base_addr,
        )
        console.print(
            f"[bold green]✓ Loaded task '{pcb.name}' (PID {pcb.task_id}) "
            f"@ [0x{pcb.base:02X}, 0x{pcb.limit:02X}), Entry: 0x{pcb.entry_point:02X}, "
            f"Size: {len(code)} bytes.[/bold green]"
        )
        return pcb

    def load_asm_task(
        self,
        name: str,
        asm_source: str,
        priority: int = 1,
        size: int = 32,
        base_addr: int | None = None,
    ) -> tuple[PCB, AssemblyResult]:
        """Assemble source code and register as an active task PCB."""
        if base_addr is not None:
            target_origin = base_addr
        elif not self.kernel.tasks:
            target_origin = 0x40
        else:
            target_origin = max(t["limit"] for t in self.kernel.tasks)

        result = assemble(asm_source, origin=target_origin)
        pcb = self.load_code_task(
            name=name,
            code=result.bytecode,
            priority=priority,
            size=max(size, len(result.bytecode) + 12),
            base_addr=target_origin,
        )
        return pcb, result

    def load_asm_file(
        self,
        file_path: str | Path,
        name: str | None = None,
        priority: int = 1,
        size: int = 32,
    ) -> tuple[PCB, AssemblyResult]:
        """Read an assembly file from disk, assemble it, and register as a task."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Assembly file not found: {path}")
        source = path.read_text(encoding="utf-8")
        task_name = name or path.stem
        return self.load_asm_task(name=task_name, asm_source=source, priority=priority, size=size)

    def disassemble_ram(self, start: int = 0x40, length: int = 16) -> None:
        """Disassemble bytes from RAM and display a structured listing table."""
        start = max(0, min(start, len(self.ram.memory) - 1))
        end = min(len(self.ram.memory), start + length)
        raw_bytes = [self.ram.read(addr) for addr in range(start, end)]

        instructions = disassemble(raw_bytes, origin=start)

        table = Table(title=f"RAM Disassembly (0x{start:02X} - 0x{end - 1:02X})", border_style="cyan")
        table.add_column("Address", style="bold yellow")
        table.add_column("Hex Bytes", style="bold white")
        table.add_column("Instruction", style="bold green")
        table.add_column("Operands", style="cyan")
        table.add_column("Description", style="dim")

        for ins in instructions:
            hex_str = " ".join(f"{b:02X}" for b in ins.raw_bytes)
            table.add_row(f"0x{ins.address:02X}", hex_str, ins.mnemonic, ins.operands, ins.description)

        console.print(table)

    def step(self, count: int = 1) -> None:
        """Execute 1 or more CPU steps."""
        if not self.kernel.tasks and not self.kernel.has_active_tasks():
            console.print("[yellow]No active tasks to execute. Load a demo, code, or assembly task first.[/yellow]")
            return

        self.bootloader.load_ivt()
        self.kernel.install_isr()

        if self.cpu.halted and self.kernel.has_active_tasks():
            self.cpu.halted = False

        if not any(t["state"] == TaskState.RUNNING for t in self.kernel.tasks):
            ready_idx = self.kernel.scheduler.pick_next_index(self.kernel.tasks, -1)
            if ready_idx is not None:
                self.kernel.current_task_index = ready_idx
                first_task = self.kernel.tasks[ready_idx]
                first_task["state"] = TaskState.RUNNING
                self.cpu.registers["SP"] = first_task["task_sp"]
                self.cpu.base_address = first_task["base"]
                self.cpu.limit_address = first_task["limit"]
                self.cpu.iret()
                self.is_started = True

        for i in range(count):
            if self.cpu.halted:
                console.print("[bold red]CPU is HALTED. No further steps possible.[/bold red]")
                break
            prev_pc = self.cpu.registers["PC"]
            prev_acc = self.cpu.registers["ACC"]
            self.cpu.step()
            self.kernel.total_cycles += 1
            curr_pc = self.cpu.registers["PC"]
            curr_acc = self.cpu.registers["ACC"]
            console.print(
                f"[dim]Step {i + 1}: PC 0x{prev_pc:02X}->0x{curr_pc:02X} | ACC: {prev_acc}->{curr_acc} | "
                f"R1: {self.cpu.registers['R1']} | R2: {self.cpu.registers['R2']} | SP: 0x{self.cpu.registers['SP']:02X}[/dim]"
            )

    def run_simulation(self, max_steps: int | None = 100) -> None:
        """Run the simulation loop until completion or max_steps."""
        if not self.kernel.tasks and not self.kernel.has_active_tasks():
            console.print("[yellow]No active tasks to run. Load a demo, code, or assembly task first.[/yellow]")
            return

        console.print(f"[bold cyan]>>> Executing simulation loop (max_steps={max_steps})...[/bold cyan]")
        start_cycles = self.kernel.total_cycles

        self.bootloader.load_ivt()
        self.kernel.install_isr()
        self.kernel.multitasking_loop(max_steps=max_steps)
        self.is_started = True

        ran_cycles = self.kernel.total_cycles - start_cycles
        console.print(f"[bold green]✓ Simulation run finished ({ran_cycles} cycles executed). CPU Halted: {self.cpu.halted}[/bold green]")
        if self.kernel.console_output:
            console.print(f"[bold yellow]Kernel Console Output:[/bold yellow] {''.join(self.kernel.console_output)}")

    def reboot(self, custom_text: str | None = None) -> None:
        """Reset the system and restart with startup animation."""
        console.clear()
        self.ram = RAM(256)
        self.cpu = CPU(self.ram)
        self.kernel = Kernel(self.ram, self.cpu)
        self.bootloader = Bootloader(self.ram, self.cpu, self.kernel)
        self.is_booted = False
        self.is_started = False
        self.play_startup_animation(custom_text=custom_text)


def show_assembly_help() -> None:
    """Display the CPU assembly instruction set and directive cheat sheet."""
    table = Table(title="OS-SIM Assembly Instruction Set & Directives", border_style="cyan")
    table.add_column("Category", style="bold yellow")
    table.add_column("Mnemonic & Syntax", style="bold green")
    table.add_column("Bytes", justify="right", style="cyan")
    table.add_column("Description", style="white")

    table.add_row("Memory I/O", "LOAD_IMM <val> / LDI", "2", "Load 8-bit immediate value into ACC")
    table.add_row("Memory I/O", "LOAD <addr> / LD", "2", "Load byte from RAM address into ACC")
    table.add_row("Memory I/O", "STORE <addr> / ST", "2", "Store ACC byte into RAM address")
    table.add_row("Transfer", "MOV <dest>, <src>", "1-2", "Copy between ACC, R1, R2, SP, [addr], or #imm")
    table.add_row("ALU Arithmetic", "ADD R1 | ADD R2", "1", "ACC = (ACC + Rn) & 0xFF (sets Z, C flags)")
    table.add_row("ALU Arithmetic", "SUB R1 | SUB R2", "1", "ACC = (ACC - Rn) & 0xFF (sets Z, C flags)")
    table.add_row("ALU Arithmetic", "MUL R1 | MUL R2", "1", "ACC = (ACC * Rn) & 0xFF (sets Z, C flags)")
    table.add_row("ALU Arithmetic", "DIV R1 | DIV R2", "1", "ACC = (ACC // Rn) & 0xFF (traps on divide by 0)")
    table.add_row("ALU Logic", "AND R1 | AND R2", "1", "Bitwise AND between Rn and ACC")
    table.add_row("ALU Logic", "OR R1  | OR R2", "1", "Bitwise OR between Rn and ACC")
    table.add_row("ALU Logic", "XOR R1 | XOR R2", "1", "Bitwise XOR between Rn and ACC")
    table.add_row("ALU Logic", "NOT / NOT ACC", "1", "Bitwise NOT on ACC")
    table.add_row("Branching", "JUMP <addr> / JMP", "2", "Unconditional jump to address or label")
    table.add_row("Branching", "JZ <addr> / JUMP_IF_ZERO", "2", "Jump to address or label if Zero flag (Z) is set")
    table.add_row("Kernel / Trap", "SYSCALL / INT 5", "1", "Invoke OS kernel syscall (ACC=ID, R1=arg1, R2=arg2)")
    table.add_row("Kernel / Trap", "HALT / HLT", "1", "Halt CPU execution (Kernel mode only)")
    table.add_row("Kernel / Trap", "IRET", "1", "Return from interrupt and restore CPU frame")
    table.add_row("Directives", ".ORG <addr>", "0", "Set assembly location counter / base address")
    table.add_row("Directives", "DB <b0>, <b1>... / .BYTE", "N", "Define raw data bytes")
    table.add_row("Directives", '.ASCII "string"', "N", "Define raw ASCII string bytes")
    table.add_row("Directives", '.ASCIIZ "string" / .STRING', "N+1", "Define null-terminated ASCII string")
    table.add_row("Directives", "<NAME> EQU <val> / .EQU", "0", "Define constant symbol alias")
    console.print(table)

    sys_table = Table(title="OS System Call IDs (ACC = ID, R1 = Arg 1, R2 = Arg 2)", border_style="magenta")
    sys_table.add_column("Syscall Constant", style="bold cyan")
    sys_table.add_column("ID", justify="right", style="yellow")
    sys_table.add_column("Arguments", style="white")
    sys_table.add_column("Description", style="dim")

    sys_table.add_row("SYS_YIELD", "1", "None", "Voluntarily yield CPU timeslice to next task")
    sys_table.add_row("SYS_EXIT", "2", "R1 = Exit code", "Terminate current task")
    sys_table.add_row("SYS_SLEEP", "3", "R1 = Ticks", "Put task to sleep for N timer ticks")
    sys_table.add_row("SYS_GETPID", "4", "None", "Returns current Task PID in ACC")
    sys_table.add_row("SYS_PRINT_NUM", "5", "R1 = Integer", "Print 8-bit integer to console buffer")
    sys_table.add_row("SYS_PRINT_CHAR", "6", "R1 = ASCII code", "Print single character to console buffer")
    sys_table.add_row("SYS_PRINT_STR", "7", "R1 = RAM addr, R2 = Length", "Print string from RAM to console buffer")
    sys_table.add_row("SYS_SPAWN", "8", "R1 = Entry point, R2 = Priority", "Spawn a new task dynamically")
    sys_table.add_row("SYS_WAIT", "9", "R1 = Target PID", "Block until target task terminates")
    sys_table.add_row("SYS_KILL", "10", "R1 = Target PID", "Terminate target task")
    sys_table.add_row("SYS_GET_TICKS", "11", "None", "Returns system tick count in ACC")
    sys_table.add_row("SYS_ALLOC", "12", "R1 = Bytes", "Allocate heap memory in task partition")
    console.print(sys_table)


def run_interactive_assembler(
    session: OSSimulatorSession,
    task_name: str = "Task_UserASM",
    prio: int = 1,
    size: int = 32,
) -> None:
    """Interactive multi-line assembly environment allowing users to write and execute code."""
    base_addr = 0x40 if not session.kernel.tasks else max(t["limit"] for t in session.kernel.tasks)

    panel_content = Text.assemble(
        ("Interactive Assembly Studio\n", "bold cyan"),
        ("Enter assembly instructions line-by-line. Supports labels, directives, and syscalls.\n", "white"),
        ("Target Memory Partition: ", "dim"),
        (f"[0x{base_addr:02X}, 0x{base_addr + size:02X})\n\n", "bold yellow"),
        ("Commands:\n", "bold white"),
        ("  RUN    ", "bold green"), ("- Assemble code, create task, and execute simulation loop\n", "dim"),
        ("  LOAD   ", "bold cyan"), ("- Assemble and register task into READY state (step manually)\n", "dim"),
        ("  LIST   ", "bold yellow"), ("- Show lines entered so far\n", "dim"),
        ("  CLEAR  ", "bold red"), ("- Empty current code buffer\n", "dim"),
        ("  HELP   ", "bold magenta"), ("- Display assembly instruction & syscall cheat sheet\n", "dim"),
        ("  EXIT   ", "bold red"), ("- Return to OS shell without assembling\n", "dim"),
    )
    console.print(Panel(panel_content, title="[bold green]OS-SIM Assembly Studio[/bold green]", border_style="cyan"))

    buffer: list[str] = []

    while True:
        line_no = len(buffer) + 1
        prompt_str = f"[bold cyan]asm[/bold cyan] [dim][0x{base_addr:02X}:{line_no:02d}][/dim][bold white]>[/bold white] "
        try:
            user_input = Prompt.ask(prompt_str)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Assembly studio aborted. Returning to shell.[/yellow]")
            break

        line = user_input.strip()
        if not line:
            continue

        upper_cmd = line.upper()

        if upper_cmd in ("EXIT", "QUIT", "CANCEL"):
            console.print("[dim]Exiting assembly studio.[/dim]")
            break

        if upper_cmd == "HELP":
            show_assembly_help()
            continue

        if upper_cmd == "CLEAR":
            buffer.clear()
            console.print("[yellow]Code buffer cleared.[/yellow]")
            continue

        if upper_cmd in ("LIST", "SHOW"):
            if not buffer:
                console.print("[dim]Buffer is empty.[/dim]")
            else:
                table = Table(title=f"Code Buffer ({len(buffer)} lines)", border_style="blue")
                table.add_column("Line", style="bold yellow", justify="right")
                table.add_column("Assembly Source", style="bold white")
                for idx, src_line in enumerate(buffer, start=1):
                    table.add_row(str(idx), src_line)
                console.print(table)
            continue

        if upper_cmd in ("RUN", "EXEC", "LOAD"):
            if not buffer:
                console.print("[yellow]Buffer is empty. Enter instructions before compiling.[/yellow]")
                continue

            asm_source = "\n".join(buffer)
            try:
                pcb, result = session.load_asm_task(
                    name=task_name,
                    asm_source=asm_source,
                    priority=prio,
                    size=size,
                    base_addr=base_addr,
                )
            except AssemblyError as err:
                console.print(f"[bold red]{err}[/bold red]")
                continue
            except Exception as err:
                console.print(f"[bold red]Failed to load task: {err}[/bold red]")
                continue

            listing_table = Table(title=f"Assembled Listing: '{pcb.name}'", border_style="green")
            listing_table.add_column("Line", justify="right", style="dim")
            listing_table.add_column("Address", style="bold yellow")
            listing_table.add_column("Bytes", style="bold cyan")
            listing_table.add_column("Source Code", style="bold white")

            for entry in result.listing:
                hex_b = " ".join(f"{b:02X}" for b in entry.bytes_emitted)
                listing_table.add_row(
                    str(entry.line_num),
                    f"0x{entry.address:02X}",
                    hex_b,
                    entry.source_text,
                )
            console.print(listing_table)

            if upper_cmd in ("RUN", "EXEC"):
                session.run_simulation(max_steps=100)
            else:
                console.print(f"[bold green]Task '{pcb.name}' is READY. Use 'run' or 'step' to execute.[/bold green]")

            break

        buffer.append(line)


def show_interactive_help() -> None:
    """Display the interactive shell command cheat sheet."""
    table = Table(title="OS-SIM Shell Commands", border_style="cyan")
    table.add_column("Command", style="bold green")
    table.add_column("Arguments", style="yellow")
    table.add_column("Description", style="white")

    table.add_row("help / ?", "", "Show this commands manual")
    table.add_row("status", "", "Display overall OS subsystem health and task counts")
    table.add_row("cpu", "", "Show detailed CPU registers, flags, and memory bounds")
    table.add_row("mem / ram", "[start=0] [len=256]", "Inspect colored RAM hex dump and memory regions")
    table.add_row("ps / tasks", "", "List all registered process control blocks (PCB)")
    table.add_row("demo", "<counter|rogue|hello|math|multitask|all>", "Load pre-built machine code tasks")
    table.add_row("asm", "[task_name=Task_UserASM]", "Open interactive assembly studio to write assembly code")
    table.add_row("code / task-code", "<name> <b0> <b1>...", "Write machine code bytes and register task directly")
    table.add_row("exec / run-asm", "<file.asm> [steps=100]", "Assemble file from disk and execute immediately")
    table.add_row("load-asm", "<file.asm> [prio=1] [size=32]", "Assemble file from disk and register in READY state")
    table.add_row("disasm", "[start=0x40] [len=16]", "Disassemble bytes in RAM into assembly mnemonics")
    table.add_row("run", "[steps=100]", "Run kernel multitasking loop")
    table.add_row("step", "[count=1]", "Execute 1 or more CPU instruction cycles")
    table.add_row("load", "<addr> <byte0> <byte1>...", "Write raw machine code bytes into RAM")
    table.add_row("read", "<addr>", "Read byte value at RAM address")
    table.add_row("write", "<addr> <value>", "Write byte value to RAM address")
    table.add_row("spawn", "<name> <entry> [base] [size=32] [prio=1]", "Forge and register a new task PCB")
    table.add_row("kill", "<pid>", "Terminate a task using sys_kill")
    table.add_row("dmesg / logs", "", "View output buffer from SYS_PRINT_* syscalls")
    table.add_row("say", "<text>", "Typewriter text broadcast animation")
    table.add_row("reboot", "[custom_text]", "Reboot OS and replay startup sequence")
    table.add_row("clear", "", "Clear terminal screen")
    table.add_row("exit / shutdown", "", "Power off the OS simulator")
    console.print(table)


def run_interactive_shell(session: OSSimulatorSession) -> None:
    """Run interactive REPL shell for the OS simulation."""
    console.print("[dim]Type [bold white]'help'[/bold white] to view available commands, or [bold white]'demo all'[/bold white] to load sample tasks.[/dim]\n")

    while True:
        try:
            raw_prompt = "[bold green]os-sim[/bold green][bold white]>[/bold white] "
            user_input = Prompt.ask(raw_prompt)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Received shutdown signal. Exiting OS-SIM.[/dim]")
            break

        line = user_input.strip()
        if not line:
            continue

        try:
            tokens = shlex.split(line)
        except ValueError as err:
            console.print(f"[red]Input syntax error: {err}[/red]")
            continue

        cmd = tokens[0].lower()
        args = tokens[1:]

        match cmd:
            case "help" | "?":
                show_interactive_help()

            case "status":
                session.show_status()

            case "cpu":
                session.show_cpu()

            case "mem" | "ram":
                start_addr = parse_int(args[0]) if len(args) > 0 else 0
                dump_len = parse_int(args[1]) if len(args) > 1 else 256
                session.show_memory(start=start_addr, length=dump_len)

            case "ps" | "tasks":
                session.show_tasks()

            case "demo":
                if not args:
                    console.print("[yellow]Usage: demo <counter|rogue|hello|math|multitask|all>[/yellow]")
                else:
                    session.load_demo(args[0])

            case "run":
                max_s = parse_int(args[0]) if args else 100
                session.run_simulation(max_steps=max_s)

            case "step":
                steps = parse_int(args[0]) if args else 1
                session.step(count=steps)

            case "load":
                if len(args) < 2:
                    console.print("[yellow]Usage: load <addr> <b0> <b1> <b2>... (e.g. load 0x40 0x03 0x01 0x10)[/yellow]")
                else:
                    target_addr = parse_int(args[0])
                    bytes_to_write = [parse_int(b) for b in args[1:]]
                    for offset, byte in enumerate(bytes_to_write):
                        session.ram.write(target_addr + offset, byte)
                    console.print(f"[bold green]Wrote {len(bytes_to_write)} bytes starting at 0x{target_addr:02X}.[/bold green]")

            case "read":
                if not args:
                    console.print("[yellow]Usage: read <addr>[/yellow]")
                else:
                    addr = parse_int(args[0])
                    val = session.ram.read(addr)
                    console.print(f"RAM[0x{addr:02X}]: [bold cyan]0x{val:02X}[/bold cyan] ({val})")

            case "write":
                if len(args) < 2:
                    console.print("[yellow]Usage: write <addr> <val>[/yellow]")
                else:
                    addr = parse_int(args[0])
                    val = parse_int(args[1])
                    session.ram.write(addr, val)
                    console.print(f"[bold green]RAM[0x{addr:02X}] <- 0x{val:02X} ({val})[/bold green]")

            case "code" | "task-code" | "load-code":
                if len(args) < 2:
                    console.print("[yellow]Usage: code <name> <b0> <b1> <b2>... [prio=1] [size=32][/yellow]")
                else:
                    task_name = args[0]
                    raw_bytes = [parse_int(b) for b in args[1:]]
                    try:
                        session.load_code_task(name=task_name, code=raw_bytes)
                    except Exception as err:
                        console.print(f"[red]Error loading task code: {err}[/red]")

            case "asm" | "assemble":
                t_name = args[0] if args else "Task_UserASM"
                run_interactive_assembler(session, task_name=t_name)

            case "exec" | "run-asm":
                if not args:
                    console.print("[yellow]Usage: exec <file.asm> [steps=100][/yellow]")
                else:
                    file_path = args[0]
                    max_s = parse_int(args[1]) if len(args) > 1 else 100
                    try:
                        session.load_asm_file(file_path)
                        session.run_simulation(max_steps=max_s)
                    except Exception as err:
                        console.print(f"[red]Execution error: {err}[/red]")

            case "load-asm":
                if not args:
                    console.print("[yellow]Usage: load-asm <file.asm> [priority=1] [size=32][/yellow]")
                else:
                    file_path = args[0]
                    prio = parse_int(args[1]) if len(args) > 1 else 1
                    sz = parse_int(args[2]) if len(args) > 2 else 32
                    try:
                        pcb, _ = session.load_asm_file(file_path, priority=prio, size=sz)
                        console.print(f"[bold green]Task '{pcb.name}' is READY. Use 'run' or 'step' to execute.[/bold green]")
                    except Exception as err:
                        console.print(f"[red]Assembly load error: {err}[/red]")

            case "disasm":
                start_a = parse_int(args[0]) if len(args) > 0 else 0x40
                dump_l = parse_int(args[1]) if len(args) > 1 else 16
                session.disassemble_ram(start=start_a, length=dump_l)

            case "spawn":
                if len(args) < 2:
                    console.print("[yellow]Usage: spawn <name> <entry_point> [base] [size=32] [priority=1][/yellow]")
                else:
                    task_name = args[0]
                    entry = parse_int(args[1])
                    if len(args) > 2:
                        base = parse_int(args[2])
                        size = parse_int(args[3]) if len(args) > 3 else 32
                        priority = parse_int(args[4]) if len(args) > 4 else 1
                    else:
                        if not session.kernel.tasks:
                            base = 0x40 if entry < 0x40 else entry
                        else:
                            highest = max(t["limit"] for t in session.kernel.tasks)
                            base = highest if entry < highest else entry
                        size = 32
                        priority = 1

                    limit = max(base + size, entry + 16)
                    stack_top = limit - 1

                    if limit > len(session.ram.memory) - 8:
                        console.print("[red]Error: Out of RAM space for new partition.[/red]")
                    else:
                        existing_pids = [t["task_id"] for t in session.kernel.tasks + session.kernel.terminated_tasks]
                        new_pid = max(existing_pids, default=-1) + 1
                        session.kernel.create_task(
                            task_id=new_pid,
                            name=task_name,
                            priority=priority,
                            entry_point=entry,
                            stack_top=stack_top,
                            base=base,
                            limit=limit,
                        )
                        console.print(f"[bold green]Spawned task '{task_name}' (PID {new_pid}) @ [0x{base:02X}, 0x{limit:02X}), entry: 0x{entry:02X}[/bold green]")

            case "kill":
                if not args:
                    console.print("[yellow]Usage: kill <pid>[/yellow]")
                else:
                    pid = parse_int(args[0])
                    ret = session.kernel.sys_kill(pid)
                    if ret == 0:
                        console.print(f"[bold green]Task {pid} terminated.[/bold green]")
                    else:
                        console.print(f"[red]Failed to kill task {pid} (PID not found).[/red]")

            case "dmesg" | "logs":
                logs = session.kernel.console_output
                if not logs:
                    console.print("[dim]Kernel console log buffer is empty.[/dim]")
                else:
                    console.print(Panel("".join(logs), title="Kernel Console Buffer (dmesg)", border_style="yellow"))

            case "say":
                text_to_say = " ".join(args)
                if not text_to_say:
                    console.print("[yellow]Usage: say <text>[/yellow]")
                else:
                    typewriter_text(text_to_say, delay=0.03, style="bold cyan")

            case "reboot":
                custom_txt = " ".join(args) if args else None
                session.reboot(custom_text=custom_txt)

            case "clear":
                console.clear()

            case "exit" | "shutdown" | "quit":
                console.print("[bold green]System shutting down... All subsystems halted. Goodbye![/bold green]")
                break

            case _:
                console.print(f"[red]Unknown command: '{cmd}'. Type 'help' for available commands.[/red]")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    text: Annotated[
        str | None,
        typer.Option("--text", "-t", help="Startup text to display or animate in boot sequence."),
    ] = None,
    say: Annotated[
        str | None,
        typer.Option("--say", "-s", help="Alias for --text: custom loading text you say."),
    ] = None,
    speed: Annotated[
        float,
        typer.Option("--speed", help="Animation speed multiplier (default: 1.0, 0 for instant)."),
    ] = 1.0,
    animation: Annotated[
        bool,
        typer.Option("--animation/--no-animation", help="Toggle startup loading animation."),
    ] = True,
    quick: Annotated[
        bool,
        typer.Option("--quick", "-q", help="Quick mode (disable animation delays)."),
    ] = False,
    demo: Annotated[
        str | None,
        typer.Option("--demo", "-d", help="Load and execute a built-in demo directly."),
    ] = None,
    asm: Annotated[
        str | None,
        typer.Option("--asm", "-a", help="Assemble and run an assembly (.asm) file directly."),
    ] = None,
    steps: Annotated[
        int,
        typer.Option("--steps", help="Maximum simulation steps if running a demo."),
    ] = 100,
    batch: Annotated[
        bool,
        typer.Option("--batch", help="Exit after boot/demo instead of opening interactive shell."),
    ] = False,
) -> None:
    """Boot the OS Simulator with loading animation and interactive shell."""
    if ctx.invoked_subcommand is not None:
        return

    # Consolidate text inputs
    startup_text = say if say is not None else text
    anim_enabled = False if quick else animation

    session = OSSimulatorSession(speed=0.0 if quick else speed, animate=anim_enabled)
    session.play_startup_animation(custom_text=startup_text)

    if demo:
        session.load_demo(demo)
        session.run_simulation(max_steps=steps)

    if asm:
        session.load_asm_file(asm)
        session.run_simulation(max_steps=steps)

    if not batch:
        run_interactive_shell(session)


@app.command("boot")
def boot_cmd(
    text: Annotated[str | None, typer.Option("--text", "-t", help="Custom boot text")] = None,
    speed: Annotated[float, typer.Option("--speed", help="Speed multiplier")] = 1.0,
    quick: Annotated[bool, typer.Option("--quick", "-q", help="Skip animation delays")] = False,
) -> None:
    """Boot the OS simulation and enter the interactive shell."""
    session = OSSimulatorSession(speed=0.0 if quick else speed, animate=not quick)
    session.play_startup_animation(custom_text=text)
    run_interactive_shell(session)


@app.command("demo")
def demo_cmd(
    name: Annotated[str, typer.Argument(help="Demo name: counter, rogue, hello, math, multitask, all")] = "all",
    steps: Annotated[int, typer.Option("--steps", help="Number of CPU steps to run")] = 100,
    interactive: Annotated[bool, typer.Option("--interactive", "-i", help="Enter shell after demo")] = False,
) -> None:
    """Boot the OS, load a demonstration program, and run it."""
    session = OSSimulatorSession(speed=0.0, animate=False)
    session.play_startup_animation(custom_text=f"Running Demo: {name}")
    session.load_demo(name)
    session.run_simulation(max_steps=steps)
    if interactive:
        run_interactive_shell(session)


@app.command("asm")
def asm_cmd(
    file: Annotated[str | None, typer.Argument(help="Assembly file (.asm) to run")] = None,
    steps: Annotated[int, typer.Option("--steps", help="Number of CPU steps to run")] = 100,
    quick: Annotated[bool, typer.Option("--quick", "-q", help="Skip animation delays")] = False,
    batch: Annotated[bool, typer.Option("--batch", help="Exit after running code")] = False,
) -> None:
    """Write, assemble, and execute assembly code tasks."""
    session = OSSimulatorSession(speed=0.0 if quick else 1.0, animate=not quick)
    session.play_startup_animation(custom_text="OS-SIM Assembly Studio Loaded")
    if file:
        session.load_asm_file(file)
        session.run_simulation(max_steps=steps)
    else:
        run_interactive_assembler(session)

    if not batch:
        run_interactive_shell(session)


if __name__ == "__main__":
    app()
