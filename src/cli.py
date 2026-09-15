"""Interactive CLI and OS simulator emulator with startup animation, shell, and live dashboard."""

from __future__ import annotations

import select
import shlex
import sys
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
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

try:
    import termios
    import tty
except ImportError:
    termios = None  # ty: ignore[invalid-assignment]
    tty = None  # type: ignore[assignment]

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


class RawTerminalContext:
    """Context manager to put standard input in cbreak mode and restore on exit."""

    def __enter__(self):
        if sys.stdin.isatty() and termios is not None and tty is not None:
            self.fd = sys.stdin.fileno()
            self.old_settings = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        else:
            self.fd = None
            self.old_settings = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None and self.old_settings is not None and termios is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)


def get_key(timeout: float = 0.1) -> str | None:
    """Non-blocking read of a single key from standard input."""
    if not sys.stdin.isatty() or sys.platform == "win32":
        return None
    rlist, _, _ = select.select([sys.stdin], [], [], timeout)
    if rlist:
        try:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                r2, _, _ = select.select([sys.stdin], [], [], 0.02)
                if r2:
                    sys.stdin.read(2)
            return ch
        except Exception:
            return None
    return None


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
        self.execution_log: list[str] = []

    def reboot_clean(self) -> None:
        """Reset hardware state cleanly without animations."""
        self.ram = RAM(256)
        self.cpu = CPU(self.ram)
        self.kernel = Kernel(self.ram, self.cpu)
        self.bootloader = Bootloader(self.ram, self.cpu, self.kernel)
        self.is_booted = True
        self.is_started = False
        self.execution_log.clear()
        self.bootloader.load_ivt()
        self.kernel.install_isr()

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

        console.print(
            "[bold yellow]>>> Initiating Hardware Power-On Self-Test (POST)...[/bold yellow]"
        )
        for stage, status in post_checks:
            self._sleep(0.08)
            console.print(
                f"  [bold blue]•[/bold blue] {stage:<42} [bold green]{status}[/bold green]"
            )

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
        console.print(
            "\n[bold green]✓ Operating System successfully booted into interactive mode![/bold green]\n"
        )

    def show_status(self) -> None:
        """Display summary table of the OS state."""
        table = Table(title="OS-SIM System Status", border_style="cyan")
        table.add_column("Subsystem", style="bold yellow")
        table.add_column("Configuration / Current State", style="bold white")

        table.add_row("CPU Architecture", "8-bit Accumulator with GP Registers (R1, R2)")
        table.add_row("Execution Privilege", "KERNEL MODE" if self.cpu.kernel_mode else "USER MODE")
        table.add_row(
            "CPU Status",
            "[bold red]HALTED[/bold red]" if self.cpu.halted else "[bold green]ACTIVE[/bold green]",
        )
        table.add_row("CPU Cycles", str(self.cpu.cycle_count))
        table.add_row("System Ticks", str(self.kernel.system_ticks))
        table.add_row("Total RAM", f"{len(self.ram.memory)} Bytes")
        table.add_row(
            "Active Tasks",
            str(len([t for t in self.kernel.tasks if t["state"] != TaskState.TERMINATED])),
        )
        table.add_row("Terminated Tasks", str(len(self.kernel.terminated_tasks)))
        table.add_row("Scheduler Policy", self.kernel.scheduler.policy.value)
        console.print(table)

    def get_cpu_context_table(self, compact: bool = False) -> Table:
        """Construct rich Table representing CPU execution state, mode, task, and PC."""
        title = "CPU Execution Context" if not compact else "CPU Context"
        status_table = Table(title=title, border_style="cyan", show_header=not compact)
        status_table.add_column("Property", style="bold cyan")
        status_table.add_column("Value", style="bold white")
        if not compact:
            status_table.add_column("Details", style="dim")

        state_str = (
            "[bold red]HALTED[/bold red]" if self.cpu.halted else "[bold green]ACTIVE[/bold green]"
        )
        if compact:
            status_table.add_row(
                "State / Mode",
                f"{state_str} | {'[bold yellow]Kernel[/bold yellow]' if self.cpu.kernel_mode else '[bold green]User[/bold green]'}",
            )
        else:
            status_table.add_row("CPU State", state_str, f"Halted Flag: {self.cpu.halted}")
            status_table.add_row(
                "Privilege Mode",
                "[bold yellow]Kernel Mode[/bold yellow]"
                if self.cpu.kernel_mode
                else "[bold green]User Mode[/bold green]",
                "Direct physical RAM access"
                if self.cpu.kernel_mode
                else "Virtual Memory MMU enforcement",
            )

        curr_task = (
            self.kernel.tasks[self.kernel.current_task_index]
            if self.kernel.tasks and 0 <= self.kernel.current_task_index < len(self.kernel.tasks)
            else None
        )
        if curr_task is not None:
            task_info = f"{curr_task['task_name']} (PID {curr_task['task_id']})"
            task_detail = f"Priority {curr_task['priority']} | State: {curr_task['state'].value} | Partition: [0x{curr_task['base']:02X}, 0x{curr_task['limit']:02X})"
        elif self.kernel._is_idle_running and self.kernel.idle_task:
            task_info = "[dim]Idle Task (PID 255)[/dim]"
            task_detail = "Executing kernel idle loop"
        else:
            task_info = "[dim]None (Bootstrap / Stopped)[/dim]"
            task_detail = "No active user task scheduled"

        if compact:
            status_table.add_row("Task", task_info)
            status_table.add_row(
                "Cycle",
                f"{self.cpu.cycle_count}/{CPU.TIMER_INTERRUPT_CYCLE_COUNT} (Tot: {self.kernel.total_cycles})",
            )
        else:
            status_table.add_row("Current Task", task_info, task_detail)
            status_table.add_row(
                "Cycle Counter",
                f"{self.cpu.cycle_count} / {CPU.TIMER_INTERRUPT_CYCLE_COUNT}",
                f"Preemption interrupt in {CPU.TIMER_INTERRUPT_CYCLE_COUNT - self.cpu.cycle_count} cycles (Total: {self.kernel.total_cycles})",
            )
            status_table.add_row(
                "Interrupts",
                "ENABLED" if self.cpu.interrupts_enabled else "DISABLED",
                f"Pending Queue: {len(self.cpu.interrupt_queue)} vectors {self.cpu.interrupt_queue}",
            )

        pc_val = self.cpu.registers["PC"]
        phys_pc = self.cpu.translate_address(pc_val, access_type="fetch", force=True)
        if phys_pc is not None and 0 <= phys_pc < len(self.ram.memory):
            next_bytes = [
                self.ram.read(min(phys_pc + i, len(self.ram.memory) - 1)) for i in range(2)
            ]
            dis = disassemble(next_bytes, origin=pc_val)
            ins_str = f"{dis[0].mnemonic} {dis[0].operands}".strip() if dis else "Unknown"
        else:
            ins_str = "[red]Unmapped / Invalid[/red]"

        pc_page = (pc_val & 0xFF) >> 4
        pt = self.cpu.page_table or {}
        entry = pt.get(pc_page, {})
        if self.cpu.kernel_mode:
            exec_frame_str = f"Kernel Frame {phys_pc >> 4}" if phys_pc is not None else "Invalid"
        else:
            exec_frame_str = (
                f"Frame {entry.get('frame', '-')}"
                if entry.get("valid") and phys_pc is not None
                else f"Phys 0x{phys_pc:02X}"
                if phys_pc is not None
                else "[red]Unmapped[/red]"
            )

        if compact:
            status_table.add_row("PC -> Frame", f"0x{pc_val:02X} -> {exec_frame_str}")
            status_table.add_row("Next Ins", ins_str)
            status_table.add_row(
                "ALU Flags",
                f"Z: [bold cyan]{int(self.cpu.flags['Z'])}[/bold cyan] | C: [bold cyan]{int(self.cpu.flags['C'])}[/bold cyan]",
            )
        else:
            status_table.add_row(
                "Executing Frame / PC",
                f"Virtual 0x{pc_val:02X} -> {exec_frame_str}",
                f"Next Instruction: {ins_str}",
            )

        return status_table

    def get_registers_table(self, compact: bool = False) -> Table:
        """Construct rich Table representing CPU register state."""
        reg_table = Table(title="CPU Register State", border_style="green")
        reg_table.add_column("Reg", style="bold cyan")
        reg_table.add_column("Hex", style="bold yellow")
        reg_table.add_column("Dec", style="bold white")
        reg_table.add_column("Binary", style="dim")
        reg_table.add_column("Physical Mapping", style="magenta")
        if not compact:
            reg_table.add_column("Function / Role", style="dim")

        roles = {
            "ACC": "Accumulator (ALU target, Syscall ID & Return Value)",
            "R1": "General Purpose 1 (Syscall Arg 1)",
            "R2": "General Purpose 2 (Syscall Arg 2)",
            "PC": "Program Counter (Next Instruction Address)",
            "SP": "Stack Pointer (Decrements on push, increments on pop)",
        }

        reg_order = ["ACC", "R1", "R2", "PC", "SP"]
        sorted_regs = sorted(
            self.cpu.registers.keys(), key=lambda r: reg_order.index(r) if r in reg_order else 99
        )
        for reg in sorted_regs:
            val = self.cpu.registers[reg]
            phys_mapping = "-"
            if reg == "PC":
                p = self.cpu.translate_address(val, access_type="fetch", force=True)
                phys_mapping = (
                    f"Phys 0x{p:02X} (Frame {p >> 4})" if p is not None else "[red]Fault[/red]"
                )
            elif reg == "SP":
                p = self.cpu.translate_address(val, access_type="write", force=True)
                phys_mapping = (
                    f"Phys 0x{p:02X} (Frame {p >> 4})" if p is not None else "[red]Fault[/red]"
                )

            row = [
                reg,
                f"0x{val:02X}",
                str(val),
                f"{val:08b}",
                phys_mapping,
            ]
            if not compact:
                row.append(roles.get(reg, "-"))
            reg_table.add_row(*row)

        return reg_table

    def get_flags_table(self) -> Table:
        """Construct rich Table representing ALU Zero and Carry status flags."""
        flag_table = Table(title="ALU Status Flags", border_style="magenta")
        flag_table.add_column("Flag", style="bold cyan")
        flag_table.add_column("Status", style="bold white")
        flag_table.add_column("Meaning", style="dim")
        flag_table.add_row(
            "Z (Zero)",
            "1 (TRUE)" if self.cpu.flags["Z"] else "0 (FALSE)",
            "Set when ALU result is 0 (Used for JZ branching)",
        )
        flag_table.add_row(
            "C (Carry)",
            "1 (TRUE)" if self.cpu.flags["C"] else "0 (FALSE)",
            "Set on arithmetic overflow (>255) or underflow (<0)",
        )
        return flag_table

    def get_mmu_table(self, compact: bool = False) -> Table:
        """Construct rich Table representing MMU page table and physical frame mappings."""
        active_pt = self.cpu.page_table or {}
        pc_page = (self.cpu.registers["PC"] & 0xFF) >> 4
        sp_page = (self.cpu.registers["SP"] & 0xFF) >> 4
        curr_task = (
            self.kernel.tasks[self.kernel.current_task_index]
            if self.kernel.tasks and 0 <= self.kernel.current_task_index < len(self.kernel.tasks)
            else None
        )

        if not compact:
            mmu_table = Table(
                title="Virtual Memory & Page Table Mapping (MMU)", border_style="yellow"
            )
            mmu_table.add_column("Page", justify="right", style="bold cyan")
            mmu_table.add_column("Virtual Range", style="bold yellow")
            mmu_table.add_column("Physical Frame", justify="right", style="bold green")
            mmu_table.add_column("Physical Range", style="white")
            mmu_table.add_column("Status", style="bold")
            mmu_table.add_column("Active Usage / Segment", style="dim")

            for p in range(16):
                v_start = p << 4
                v_end = v_start + 15
                v_range = f"0x{v_start:02X}-0x{v_end:02X}"

                entry = active_pt.get(p)
                if entry and entry.get("valid"):
                    frame = entry["frame"]
                    p_start = frame << 4
                    p_end = p_start + 15
                    p_range = f"0x{p_start:02X}-0x{p_end:02X}"
                    status = "[bold green]MAPPED[/bold green]"

                    tags = []
                    if p < 4:
                        tags.append("Kernel Reserved")
                    if p == pc_page:
                        tags.append("[bold yellow]EXECUTING (PC)[/bold yellow]")
                    if p == sp_page:
                        tags.append("[cyan]STACK (SP)[/cyan]")
                    if (
                        curr_task
                        and (curr_task["base"] >> 4) <= p <= ((curr_task["limit"] - 1) >> 4)
                        and not tags
                    ):
                        tags.append("Task Partition")
                    usage = " | ".join(tags) if tags else "User Memory"
                    frame_str = str(frame)
                else:
                    p_range = "-"
                    frame_str = "-"
                    if curr_task and (curr_task["base"] >> 4) <= p <= (
                        (curr_task["limit"] - 1) >> 4
                    ):
                        status = "[yellow]UNMAPPED (Demand)[/yellow]"
                        usage = "Task Virtual Space (Fault on Access)"
                    elif p < 4:
                        status = "[dim]Kernel Region[/dim]"
                        usage = "Kernel Low Memory"
                    elif p == 15:
                        status = "[dim]Mailbox / High RAM[/dim]"
                        usage = "Mailbox & System Buffer"
                    else:
                        status = "[dim]UNMAPPED[/dim]"
                        usage = "-"

                mmu_table.add_row(f"{p}", v_range, frame_str, p_range, status, usage)
            return mmu_table

        # Dual-column compact 8-row MMU table for live inspector panel
        mmu_table = Table(
            title="MMU Page Table (16 Pages -> Physical Frames)",
            border_style="yellow",
            padding=(0, 1),
        )
        mmu_table.add_column("P", justify="right", style="bold cyan")
        mmu_table.add_column("Virt", style="bold yellow")
        mmu_table.add_column("Frm", justify="right", style="bold green")
        mmu_table.add_column("Status", style="bold")
        mmu_table.add_column("Tag", style="dim")
        mmu_table.add_column("│", justify="center", style="dim")
        mmu_table.add_column("P", justify="right", style="bold cyan")
        mmu_table.add_column("Virt", style="bold yellow")
        mmu_table.add_column("Frm", justify="right", style="bold green")
        mmu_table.add_column("Status", style="bold")
        mmu_table.add_column("Tag", style="dim")

        def cell_info(pg: int) -> tuple[str, str, str, str, str]:
            v_str = f"0x{pg << 4:02X}"
            entry = active_pt.get(pg)
            if entry and entry.get("valid"):
                frm = str(entry["frame"])
                st = "[green]MAP[/green]"
                if pg == pc_page:
                    tg = "[bold yellow]EXEC[/bold yellow]"
                elif pg == sp_page:
                    tg = "[cyan]STK[/cyan]"
                elif pg < 4:
                    tg = "KRN"
                else:
                    tg = "TASK"
            else:
                frm = "-"
                if curr_task and (curr_task["base"] >> 4) <= pg <= ((curr_task["limit"] - 1) >> 4):
                    st = "[yellow]DEM[/yellow]"
                    tg = "DEM"
                elif pg < 4:
                    st = "[dim]KRN[/dim]"
                    tg = "LOW"
                elif pg == 15:
                    st = "[dim]BOX[/dim]"
                    tg = "MBOX"
                else:
                    st = "[dim]UNM[/dim]"
                    tg = "-"
            return (str(pg), v_str, frm, st, tg)

        for row in range(8):
            p_left = row
            p_right = row + 8
            l_p, l_v, l_f, l_s, l_t = cell_info(p_left)
            r_p, r_v, r_f, r_s, r_t = cell_info(p_right)
            mmu_table.add_row(l_p, l_v, l_f, l_s, l_t, "│", r_p, r_v, r_f, r_s, r_t)

        return mmu_table

    def get_frame_pool_summary(self) -> Text:
        """Construct Text summary of free physical frames and page fault counts."""
        curr_task = (
            self.kernel.tasks[self.kernel.current_task_index]
            if self.kernel.tasks and 0 <= self.kernel.current_task_index < len(self.kernel.tasks)
            else None
        )
        free_frames = self.kernel.free_frames
        task_faults = curr_task.get("page_faults", 0) if curr_task else 0
        return Text.from_markup(
            f"[dim]Frame Pool: [bold green]{len(free_frames)}[/bold green] free {free_frames} | "
            f"Faults: Kernel [bold yellow]{self.kernel.page_fault_count}[/bold yellow], Task [bold cyan]{task_faults}[/bold cyan][/dim]"
        )

    def get_right_inspector_panel(self, compact: bool = True) -> Panel:
        """Combine execution context, registers, ALU flags, and MMU table into right inspector."""
        items = [
            self.get_cpu_context_table(compact=compact),
            self.get_registers_table(compact=compact),
        ]
        if not compact:
            items.append(self.get_flags_table())
        items.append(self.get_mmu_table(compact=compact))
        items.append(self.get_frame_pool_summary())
        return Panel(
            Group(*items),
            title="[bold cyan]CPU & MMU Live Inspector[/bold cyan]",
            border_style="cyan",
        )

    def show_cpu(self) -> None:
        """Display detailed CPU registers, flags, execution status, and MMU/frame mapping."""
        console.print(self.get_cpu_context_table(compact=False))
        console.print(self.get_registers_table(compact=False))
        console.print(self.get_flags_table())
        console.print(self.get_mmu_table(compact=False))
        console.print(self.get_frame_pool_summary())
        console.print()

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
                        row_vals.append(
                            f"[green]{b:02X}[/green]" if b != 0 else f"[dim]{b:02X}[/dim]"
                        )

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
        console.print(
            "[dim]Regions: [cyan]IVT (0x00-1F)[/cyan] | [magenta]ISR (0x20-2F)[/magenta] | [blue]Idle (0x30-3F)[/blue] | [green]User (0x40-F9)[/green] | [yellow]Mailbox (0xFA-FB)[/yellow][/dim]"
        )

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
            console.print(
                f"[bold green]Loaded 'counter' demo (Task {pid}) at 0x40. Continuously increments R1 and yields.[/bold green]"
            )
        elif name in ("rogue", "fault"):
            pid = load_rogue_demo(self.ram, self.kernel)
            console.print(
                f"[bold green]Loaded 'rogue' demo (Task {pid}) at 0x60. Attempts illegal memory write to trigger fault.[/bold green]"
            )
        elif name in ("hello", "print"):
            pid = load_hello_demo(self.ram, self.kernel, "Hello OS!")
            console.print(
                f"[bold green]Loaded 'hello' demo (Task {pid}) at 0x40. Invokes SYS_PRINT_STR syscall.[/bold green]"
            )
        elif name in ("math", "alu"):
            pid = load_math_demo(self.ram, self.kernel)
            console.print(
                f"[bold green]Loaded 'math' demo (Task {pid}) at 0x40. Computes (15 + 25) * 2 = 80 and prints it.[/bold green]"
            )
        elif name in ("multitask", "coop"):
            p1, p2 = load_multitask_demo(self.ram, self.kernel)
            console.print(
                f"[bold green]Loaded 'multitask' demo (Tasks {p1} & {p2}). Alternates execution via SYS_YIELD.[/bold green]"
            )
        elif name in ("all", "suite"):
            p1, p2 = load_all_demo(self.ram, self.kernel)
            console.print(
                f"[bold green]Loaded 'all' demo suite (Task {p1}: Counter, Task {p2}: Rogue Writer).[/bold green]"
            )
        else:
            console.print(
                f"[red]Unknown demo '{demo_name}'. Available: counter, rogue, hello, math, multitask, all[/red]"
            )

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

        table = Table(
            title=f"RAM Disassembly (0x{start:02X} - 0x{end - 1:02X})", border_style="cyan"
        )
        table.add_column("Address", style="bold yellow")
        table.add_column("Hex Bytes", style="bold white")
        table.add_column("Instruction", style="bold green")
        table.add_column("Operands", style="cyan")
        table.add_column("Description", style="dim")

        for ins in instructions:
            hex_str = " ".join(f"{b:02X}" for b in ins.raw_bytes)
            table.add_row(
                f"0x{ins.address:02X}", hex_str, ins.mnemonic, ins.operands, ins.description
            )

        console.print(table)

    def step_single(self) -> str | None:
        """Execute one CPU instruction step and append formatted trace to execution_log."""
        if not self.kernel.tasks and not self.kernel.has_active_tasks():
            self.execution_log.append(
                "[yellow]No tasks available to execute. Press 1-5 to load a demo.[/yellow]"
            )
            return None

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
                self.cpu.page_table = first_task["page_table"]
                self.cpu.iret()
                self.is_started = True

        if self.cpu.halted:
            return None

        prev_pc = self.cpu.registers["PC"]
        prev_acc = self.cpu.registers["ACC"]
        phys_pc = self.cpu.translate_address(prev_pc, access_type="fetch", force=True)
        if phys_pc is not None and 0 <= phys_pc < len(self.ram.memory):
            raw = [self.ram.read(min(phys_pc + i, len(self.ram.memory) - 1)) for i in range(2)]
            dis = disassemble(raw, origin=prev_pc)
            ins_str = f"{dis[0].mnemonic} {dis[0].operands}".strip() if dis else "Unknown"
        else:
            ins_str = "FAULT"

        self.cpu.step()
        self.kernel.total_cycles += 1
        curr_pc = self.cpu.registers["PC"]
        curr_acc = self.cpu.registers["ACC"]

        log_entry = (
            f"[dim]#{self.kernel.total_cycles:03d}[/dim] "
            f"[bold cyan]0x{prev_pc:02X}[/bold cyan] [bold white]{ins_str:<12}[/bold white] -> "
            f"PC:[yellow]0x{curr_pc:02X}[/yellow] ACC:[yellow]0x{curr_acc:02X}[/yellow] "
            f"R1:[dim]0x{self.cpu.registers['R1']:02X}[/dim] SP:[dim]0x{self.cpu.registers['SP']:02X}[/dim]"
        )
        self.execution_log.append(log_entry)
        if len(self.execution_log) > 50:
            self.execution_log.pop(0)

        return (
            f"PC 0x{prev_pc:02X}->0x{curr_pc:02X} | ACC: {prev_acc}->{curr_acc} | "
            f"R1: {self.cpu.registers['R1']} | R2: {self.cpu.registers['R2']} | SP: 0x{self.cpu.registers['SP']:02X}"
        )

    def step(self, count: int = 1) -> None:
        """Execute 1 or more CPU steps."""
        if not self.kernel.tasks and not self.kernel.has_active_tasks():
            console.print(
                "[yellow]No active tasks to execute. Load a demo, code, or assembly task first.[/yellow]"
            )
            return

        for i in range(count):
            if self.cpu.halted:
                console.print("[bold red]CPU is HALTED. No further steps possible.[/bold red]")
                break
            msg = self.step_single()
            if msg:
                console.print(f"[dim]Step {i + 1}: {msg}[/dim]")

    def get_dashboard_header(self, is_running: bool, status_msg: str) -> Panel:
        """Render top dashboard status header banner."""
        if self.cpu.halted:
            badge = "[bold white on red] HALTED [/bold white on red]"
        elif is_running:
            badge = "[bold white on green] RUNNING [/bold white on green]"
        else:
            badge = "[bold white on yellow] PAUSED [/bold white on yellow]"

        title_text = Text.from_markup(
            f"[bold cyan]OS-SIM LIVE SPLIT-SCREEN DASHBOARD[/bold cyan]  {badge}  "
            f"Ticks: [bold white]{self.kernel.system_ticks}[/bold white]  "
            f"Cycles: [bold white]{self.kernel.total_cycles}[/bold white]  "
            f"Status: {status_msg}",
            justify="center",
        )
        return Panel(Align.center(title_text), border_style="cyan")

    def get_trace_panel(self) -> Panel:
        """Render recent execution history log and next instruction pipeline preview."""
        items: list[Text] = []
        if not self.execution_log:
            items.append(
                Text.from_markup(
                    "[dim]No steps executed yet. Press [Space] or [S] to step, [R] to run.[/dim]"
                )
            )
        else:
            recent = self.execution_log[-10:]
            for line in recent:
                items.append(Text.from_markup(line))

        pc_val = self.cpu.registers["PC"]
        phys_pc = self.cpu.translate_address(pc_val, access_type="fetch", force=True)
        preview_lines: list[str] = ["[bold yellow]Pipeline (Next Instructions):[/bold yellow]"]
        if phys_pc is not None and 0 <= phys_pc < len(self.ram.memory):
            scan_vaddr = pc_val
            for _ in range(3):
                scan_p = self.cpu.translate_address(scan_vaddr, access_type="fetch", force=True)
                if scan_p is None or scan_p >= len(self.ram.memory):
                    break
                raw = [self.ram.read(min(scan_p + j, len(self.ram.memory) - 1)) for j in range(2)]
                dis = disassemble(raw, origin=scan_vaddr)
                if not dis:
                    break
                ins = dis[0]
                marker = "[bold yellow]>>>[/bold yellow]" if scan_vaddr == pc_val else "   "
                preview_lines.append(
                    f"{marker} [cyan]0x{scan_vaddr:02X}[/cyan]: [bold white]{ins.mnemonic} {ins.operands}[/bold white]"
                )
                scan_vaddr += len(ins.raw_bytes)
        else:
            preview_lines.append(
                "    [dim red]Next instruction unmapped or out of bounds[/dim red]"
            )

        preview_text = Text.from_markup("\n".join(preview_lines))
        return Panel(
            Group(*items, Text(""), preview_text),
            title="[bold green]Execution Trace & Pipeline[/bold green]",
            border_style="green",
        )

    def get_subview_panel(self, view_mode: str = "tasks") -> Panel:
        """Render bottom-left subview: either Process PCB Table or RAM hex dump."""
        if view_mode == "tasks":
            table = Table(title="Process Control Blocks (PCB)", border_style="magenta", expand=True)
            table.add_column("PID", style="bold cyan", justify="right", width=4)
            table.add_column("Name", style="bold white", width=14)
            table.add_column("Prio", justify="right", width=4)
            table.add_column("State", style="bold", width=10)
            table.add_column("Entry", justify="right", width=6)
            table.add_column("SP", justify="right", width=6)
            table.add_column("Bounds [Base, Lim)", style="yellow", width=18)
            table.add_column("Faults", justify="right", width=6)

            all_tasks = self.kernel.tasks + self.kernel.terminated_tasks
            if not all_tasks:
                return Panel(
                    Text.from_markup("[dim]No tasks registered in kernel.[/dim]"),
                    title="[bold magenta]Processes[/bold magenta]",
                    border_style="magenta",
                )

            for t in all_tasks:
                st = t["state"]
                if st == TaskState.RUNNING:
                    st_str = "[green]RUNNING[/green]"
                elif st == TaskState.READY:
                    st_str = "[cyan]READY[/cyan]"
                elif st == TaskState.SLEEPING:
                    st_str = "[yellow]SLEEP[/yellow]"
                elif st == TaskState.BLOCKED:
                    st_str = "[magenta]BLOCK[/magenta]"
                else:
                    st_str = "[dim red]EXIT[/dim red]"

                table.add_row(
                    str(t["task_id"]),
                    t["task_name"][:14],
                    str(t["task_priority"]),
                    st_str,
                    f"0x{t['entry_point']:02X}",
                    f"0x{t['task_sp']:02X}",
                    f"[0x{t['base']:02X}, 0x{t['limit']:02X})",
                    str(t.get("page_faults", 0)),
                )
            return Panel(
                table, title="[bold magenta]Processes (PCB)[/bold magenta]", border_style="magenta"
            )

        # RAM Hex Dump subview
        curr_task = (
            self.kernel.tasks[self.kernel.current_task_index]
            if self.kernel.tasks and 0 <= self.kernel.current_task_index < len(self.kernel.tasks)
            else None
        )
        base = curr_task["base"] if curr_task else 0x40
        base = max(0, min(base, len(self.ram.memory) - 64))
        ram_table = Table(
            title=f"RAM Partition (0x{base:02X} - 0x{base + 63:02X})",
            border_style="blue",
            expand=True,
        )
        ram_table.add_column("Offset", style="bold yellow", width=7)
        for col in range(16):
            ram_table.add_column(f"{col:02X}", justify="center", width=3)
        ram_table.add_column("ASCII", style="green", width=16)

        for r_base in range(base, base + 64, 16):
            vals: list[str] = []
            chars: list[str] = []
            for c in range(16):
                a = r_base + c
                if a < len(self.ram.memory):
                    b = self.ram.read(a)
                    vals.append(f"{b:02X}" if b != 0 else f"[dim]{b:02X}[/dim]")
                    chars.append(chr(b) if 32 <= b <= 126 else ".")
                else:
                    vals.append("  ")
                    chars.append(" ")
            ram_table.add_row(f"0x{r_base:02X}:", *vals, "".join(chars))
        return Panel(ram_table, title="[bold blue]RAM Memory Dump[/bold blue]", border_style="blue")

    def get_controls_footer(self) -> Panel:
        """Render bottom keybindings cheat sheet panel."""
        controls_text = Text.from_markup(
            "[bold green][S][/bold green] Step  "
            "[bold green][Space][/bold green] Step 5  "
            "[bold green][R][/bold green] Run/Pause  "
            "[bold green][1..5][/bold green] Demos (1:Count 2:Rogue 3:Hello 4:Math 5:Multi)  "
            "[bold green][T][/bold green] Tasks/RAM  "
            "[bold red][Q][/bold red] Quit",
            justify="center",
        )
        return Panel(Align.center(controls_text), border_style="dim")

    def run_dashboard(self, initial_demo: str | None = None) -> None:
        """Run fullscreen live split-screen TUI dashboard with persistent right-side status inspector."""
        if initial_demo:
            self.load_demo(initial_demo)
        elif not self.kernel.tasks:
            self.load_demo("counter")

        layout = Layout(name="root")
        layout.split_row(
            Layout(name="left", ratio=3),
            Layout(name="right", ratio=2),
        )
        layout["left"].split_column(
            Layout(name="header", size=3),
            Layout(name="trace", ratio=3),
            Layout(name="subview", ratio=2),
            Layout(name="footer", size=3),
        )

        is_running = False
        subview_mode = "tasks"
        status_msg = "[bold green]Ready (Press S or Space to step)[/bold green]"

        if not sys.stdin.isatty():
            self.step_single()
            layout["header"].update(self.get_dashboard_header(is_running, status_msg))
            layout["trace"].update(self.get_trace_panel())
            layout["subview"].update(self.get_subview_panel(subview_mode))
            layout["footer"].update(self.get_controls_footer())
            layout["right"].update(self.get_right_inspector_panel(compact=True))
            console.print(layout)
            return

        with (
            RawTerminalContext(),
            Live(layout, screen=True, console=console, refresh_per_second=15) as live,
        ):
            while True:
                layout["header"].update(self.get_dashboard_header(is_running, status_msg))
                layout["trace"].update(self.get_trace_panel())
                layout["subview"].update(self.get_subview_panel(subview_mode))
                layout["footer"].update(self.get_controls_footer())
                layout["right"].update(self.get_right_inspector_panel(compact=True))
                live.refresh()

                timeout = 0.08 if is_running else 0.2
                key = get_key(timeout=timeout)

                if is_running:
                    if self.cpu.halted:
                        is_running = False
                        status_msg = "[bold red]CPU Halted[/bold red]"
                    else:
                        self.step_single()

                if key is None:
                    continue

                if key in ("q", "Q", "\x03"):
                    break
                elif key in ("s", "S"):
                    is_running = False
                    self.step_single()
                    status_msg = "[cyan]Stepped 1 instruction[/cyan]"
                elif key == " ":
                    is_running = False
                    for _ in range(5):
                        if self.cpu.halted:
                            break
                        self.step_single()
                    status_msg = "[cyan]Stepped 5 instructions[/cyan]"
                elif key in ("r", "R"):
                    is_running = not is_running
                    status_msg = (
                        "[bold green]Continuous execution[/bold green]"
                        if is_running
                        else "[yellow]Execution paused[/yellow]"
                    )
                elif key in ("t", "T"):
                    subview_mode = "ram" if subview_mode == "tasks" else "tasks"
                    status_msg = f"[cyan]Switched subview to {subview_mode.upper()}[/cyan]"
                elif key == "1":
                    is_running = False
                    self.reboot_clean()
                    self.load_demo("counter")
                    status_msg = "[bold green]Loaded: Counter[/bold green]"
                elif key == "2":
                    is_running = False
                    self.reboot_clean()
                    self.load_demo("rogue")
                    status_msg = "[bold green]Loaded: Rogue (Page Fault Trigger)[/bold green]"
                elif key == "3":
                    is_running = False
                    self.reboot_clean()
                    self.load_demo("hello")
                    status_msg = "[bold green]Loaded: Hello Syscall[/bold green]"
                elif key == "4":
                    is_running = False
                    self.reboot_clean()
                    self.load_demo("math")
                    status_msg = "[bold green]Loaded: Math ALU[/bold green]"
                elif key == "5":
                    is_running = False
                    self.reboot_clean()
                    self.load_demo("multitask")
                    status_msg = "[bold green]Loaded: Multitask Cooperative[/bold green]"

    def run_simulation(self, max_steps: int | None = 100) -> None:
        """Run the simulation loop until completion or max_steps."""
        if not self.kernel.tasks and not self.kernel.has_active_tasks():
            console.print(
                "[yellow]No active tasks to run. Load a demo, code, or assembly task first.[/yellow]"
            )
            return

        console.print(
            f"[bold cyan]>>> Executing simulation loop (max_steps={max_steps})...[/bold cyan]"
        )
        start_cycles = self.kernel.total_cycles

        self.bootloader.load_ivt()
        self.kernel.install_isr()
        self.kernel.multitasking_loop(max_steps=max_steps)
        self.is_started = True

        ran_cycles = self.kernel.total_cycles - start_cycles
        console.print(
            f"[bold green]✓ Simulation run finished ({ran_cycles} cycles executed). CPU Halted: {self.cpu.halted}[/bold green]"
        )
        if self.kernel.console_output:
            console.print(
                f"[bold yellow]Kernel Console Output:[/bold yellow] {''.join(self.kernel.console_output)}"
            )

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
    table.add_row(
        "Transfer", "MOV <dest>, <src>", "1-2", "Copy between ACC, R1, R2, SP, [addr], or #imm"
    )
    table.add_row(
        "ALU Arithmetic", "ADD R1 | ADD R2", "1", "ACC = (ACC + Rn) & 0xFF (sets Z, C flags)"
    )
    table.add_row(
        "ALU Arithmetic", "SUB R1 | SUB R2", "1", "ACC = (ACC - Rn) & 0xFF (sets Z, C flags)"
    )
    table.add_row(
        "ALU Arithmetic", "MUL R1 | MUL R2", "1", "ACC = (ACC * Rn) & 0xFF (sets Z, C flags)"
    )
    table.add_row(
        "ALU Arithmetic", "DIV R1 | DIV R2", "1", "ACC = (ACC // Rn) & 0xFF (traps on divide by 0)"
    )
    table.add_row("ALU Logic", "AND R1 | AND R2", "1", "Bitwise AND between Rn and ACC")
    table.add_row("ALU Logic", "OR R1  | OR R2", "1", "Bitwise OR between Rn and ACC")
    table.add_row("ALU Logic", "XOR R1 | XOR R2", "1", "Bitwise XOR between Rn and ACC")
    table.add_row("ALU Logic", "NOT / NOT ACC", "1", "Bitwise NOT on ACC")
    table.add_row("Branching", "JUMP <addr> / JMP", "2", "Unconditional jump to address or label")
    table.add_row(
        "Branching",
        "JZ <addr> / JUMP_IF_ZERO",
        "2",
        "Jump to address or label if Zero flag (Z) is set",
    )
    table.add_row(
        "Kernel / Trap",
        "SYSCALL / INT 5",
        "1",
        "Invoke OS kernel syscall (ACC=ID, R1=arg1, R2=arg2)",
    )
    table.add_row("Kernel / Trap", "HALT / HLT", "1", "Halt CPU execution (Kernel mode only)")
    table.add_row("Kernel / Trap", "IRET", "1", "Return from interrupt and restore CPU frame")
    table.add_row("Directives", ".ORG <addr>", "0", "Set assembly location counter / base address")
    table.add_row("Directives", "DB <b0>, <b1>... / .BYTE", "N", "Define raw data bytes")
    table.add_row("Directives", '.ASCII "string"', "N", "Define raw ASCII string bytes")
    table.add_row(
        "Directives", '.ASCIIZ "string" / .STRING', "N+1", "Define null-terminated ASCII string"
    )
    table.add_row("Directives", "<NAME> EQU <val> / .EQU", "0", "Define constant symbol alias")
    console.print(table)

    sys_table = Table(
        title="OS System Call IDs (ACC = ID, R1 = Arg 1, R2 = Arg 2)", border_style="magenta"
    )
    sys_table.add_column("Syscall Constant", style="bold cyan")
    sys_table.add_column("ID", justify="right", style="yellow")
    sys_table.add_column("Arguments", style="white")
    sys_table.add_column("Description", style="dim")

    sys_table.add_row("SYS_YIELD", "1", "None", "Voluntarily yield CPU timeslice to next task")
    sys_table.add_row("SYS_EXIT", "2", "R1 = Exit code", "Terminate current task")
    sys_table.add_row("SYS_SLEEP", "3", "R1 = Ticks", "Put task to sleep for N timer ticks")
    sys_table.add_row("SYS_GETPID", "4", "None", "Returns current Task PID in ACC")
    sys_table.add_row("SYS_PRINT_NUM", "5", "R1 = Integer", "Print 8-bit integer to console buffer")
    sys_table.add_row(
        "SYS_PRINT_CHAR", "6", "R1 = ASCII code", "Print single character to console buffer"
    )
    sys_table.add_row(
        "SYS_PRINT_STR",
        "7",
        "R1 = RAM addr, R2 = Length",
        "Print string from RAM to console buffer",
    )
    sys_table.add_row(
        "SYS_SPAWN", "8", "R1 = Entry point, R2 = Priority", "Spawn a new task dynamically"
    )
    sys_table.add_row("SYS_WAIT", "9", "R1 = Target PID", "Block until target task terminates")
    sys_table.add_row("SYS_KILL", "10", "R1 = Target PID", "Terminate target task")
    sys_table.add_row("SYS_GET_TICKS", "11", "None", "Returns system tick count in ACC")
    sys_table.add_row("SYS_ALLOC", "12", "R1 = Bytes", "Allocate heap memory in task partition")
    sys_table.add_row("SYS_MUTEX_LOCK", "13", "R1 = Lock ID", "Acquire mutex lock; block if taken")
    sys_table.add_row(
        "SYS_MUTEX_UNLOCK", "14", "R1 = Lock ID", "Release mutex lock and wake next waiter"
    )
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
        (
            "Enter assembly instructions line-by-line. Supports labels, directives, and syscalls.\n",
            "white",
        ),
        ("Target Memory Partition: ", "dim"),
        (f"[0x{base_addr:02X}, 0x{base_addr + size:02X})\n\n", "bold yellow"),
        ("Commands:\n", "bold white"),
        ("  RUN    ", "bold green"),
        ("- Assemble code, create task, and execute simulation loop\n", "dim"),
        ("  LOAD   ", "bold cyan"),
        ("- Assemble and register task into READY state (step manually)\n", "dim"),
        ("  LIST   ", "bold yellow"),
        ("- Show lines entered so far\n", "dim"),
        ("  CLEAR  ", "bold red"),
        ("- Empty current code buffer\n", "dim"),
        ("  HELP   ", "bold magenta"),
        ("- Display assembly instruction & syscall cheat sheet\n", "dim"),
        ("  EXIT   ", "bold red"),
        ("- Return to OS shell without assembling\n", "dim"),
    )
    console.print(
        Panel(
            panel_content,
            title="[bold green]OS-SIM Assembly Studio[/bold green]",
            border_style="cyan",
        )
    )

    buffer: list[str] = []

    while True:
        line_no = len(buffer) + 1
        prompt_str = f"[bold cyan]asm[/bold cyan] [dim][0x{base_addr:02X}:{line_no:02d}][/dim][bold white]>[/bold white] "
        try:
            user_input = Prompt.ask(prompt_str)
        except KeyboardInterrupt, EOFError:
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
                console.print(
                    "[yellow]Buffer is empty. Enter instructions before compiling.[/yellow]"
                )
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
                console.print(
                    f"[bold green]Task '{pcb.name}' is READY. Use 'run' or 'step' to execute.[/bold green]"
                )

            break

        buffer.append(line)


def show_interactive_help() -> None:
    """Display the interactive shell command cheat sheet."""
    table = Table(title="OS-SIM Shell Commands", border_style="cyan")
    table.add_column("Command", style="bold green")
    table.add_column("Arguments", style="yellow")
    table.add_column("Description", style="white")

    table.add_row("help / ?", "", "Show this commands manual")
    table.add_row(
        "dashboard / tui",
        "[demo]",
        "Launch fullscreen live split dashboard with right-side inspector",
    )
    table.add_row("status", "", "Display overall OS subsystem health and task counts")
    table.add_row(
        "cpu / mmu / regs", "", "Show detailed CPU registers, flags, executing frame, and MMU table"
    )
    table.add_row(
        "mem / ram", "[start=0] [len=256]", "Inspect colored RAM hex dump and memory regions"
    )
    table.add_row("ps / tasks", "", "List all registered process control blocks (PCB)")
    table.add_row(
        "demo", "<counter|rogue|hello|math|multitask|all>", "Load pre-built machine code tasks"
    )
    table.add_row(
        "asm", "[task_name=Task_UserASM]", "Open interactive assembly studio to write assembly code"
    )
    table.add_row(
        "code / task-code",
        "<name> <b0> <b1>...",
        "Write machine code bytes and register task directly",
    )
    table.add_row(
        "exec / run-asm",
        "<file.asm> [steps=100]",
        "Assemble file from disk and execute immediately",
    )
    table.add_row(
        "load-asm",
        "<file.asm> [prio=1] [size=32]",
        "Assemble file from disk and register in READY state",
    )
    table.add_row(
        "disasm", "[start=0x40] [len=16]", "Disassemble bytes in RAM into assembly mnemonics"
    )
    table.add_row("run", "[steps=100]", "Run kernel multitasking loop")
    table.add_row("step", "[count=1]", "Execute 1 or more CPU instruction cycles")
    table.add_row("load", "<addr> <byte0> <byte1>...", "Write raw machine code bytes into RAM")
    table.add_row("read", "<addr>", "Read byte value at RAM address")
    table.add_row("write", "<addr> <value>", "Write byte value to RAM address")
    table.add_row(
        "spawn", "<name> <entry> [base] [size=32] [prio=1]", "Forge and register a new task PCB"
    )
    table.add_row("kill", "<pid>", "Terminate a task using sys_kill")
    table.add_row("dmesg / logs", "", "View output buffer from SYS_PRINT_* syscalls")
    table.add_row("say", "<text>", "Typewriter text broadcast animation")
    table.add_row("reboot", "[custom_text]", "Reboot OS and replay startup sequence")
    table.add_row("clear", "", "Clear terminal screen")
    table.add_row("exit / shutdown", "", "Power off the OS simulator")
    console.print(table)


def run_interactive_shell(session: OSSimulatorSession) -> None:
    """Run interactive REPL shell for the OS simulation."""
    console.print(
        "[dim]Type [bold white]'help'[/bold white] to view available commands, or [bold white]'demo all'[/bold white] to load sample tasks.[/dim]\n"
    )

    while True:
        try:
            raw_prompt = "[bold green]os-sim[/bold green][bold white]>[/bold white] "
            user_input = Prompt.ask(raw_prompt)
        except KeyboardInterrupt, EOFError:
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

            case "dashboard" | "tui" | "live":
                demo_arg = args[0] if args else None
                session.run_dashboard(initial_demo=demo_arg)

            case "status":
                session.show_status()

            case "cpu" | "mmu" | "regs" | "registers" | "frames" | "pages":
                session.show_cpu()

            case "mem" | "ram":
                start_addr = parse_int(args[0]) if len(args) > 0 else 0
                dump_len = parse_int(args[1]) if len(args) > 1 else 256
                session.show_memory(start=start_addr, length=dump_len)

            case "ps" | "tasks":
                session.show_tasks()

            case "demo":
                if not args:
                    console.print(
                        "[yellow]Usage: demo <counter|rogue|hello|math|multitask|all>[/yellow]"
                    )
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
                    console.print(
                        "[yellow]Usage: load <addr> <b0> <b1> <b2>... (e.g. load 0x40 0x03 0x01 0x10)[/yellow]"
                    )
                else:
                    target_addr = parse_int(args[0])
                    bytes_to_write = [parse_int(b) for b in args[1:]]
                    for offset, byte in enumerate(bytes_to_write):
                        session.ram.write(target_addr + offset, byte)
                    console.print(
                        f"[bold green]Wrote {len(bytes_to_write)} bytes starting at 0x{target_addr:02X}.[/bold green]"
                    )

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
                    console.print(
                        f"[bold green]RAM[0x{addr:02X}] <- 0x{val:02X} ({val})[/bold green]"
                    )

            case "code" | "task-code" | "load-code":
                if len(args) < 2:
                    console.print(
                        "[yellow]Usage: code <name> <b0> <b1> <b2>... [prio=1] [size=32][/yellow]"
                    )
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
                    console.print(
                        "[yellow]Usage: load-asm <file.asm> [priority=1] [size=32][/yellow]"
                    )
                else:
                    file_path = args[0]
                    prio = parse_int(args[1]) if len(args) > 1 else 1
                    sz = parse_int(args[2]) if len(args) > 2 else 32
                    try:
                        pcb, _ = session.load_asm_file(file_path, priority=prio, size=sz)
                        console.print(
                            f"[bold green]Task '{pcb.name}' is READY. Use 'run' or 'step' to execute.[/bold green]"
                        )
                    except Exception as err:
                        console.print(f"[red]Assembly load error: {err}[/red]")

            case "disasm":
                start_a = parse_int(args[0]) if len(args) > 0 else 0x40
                dump_l = parse_int(args[1]) if len(args) > 1 else 16
                session.disassemble_ram(start=start_a, length=dump_l)

            case "spawn":
                if len(args) < 2:
                    console.print(
                        "[yellow]Usage: spawn <name> <entry_point> [base] [size=32] [priority=1][/yellow]"
                    )
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
                        existing_pids = [
                            t["task_id"]
                            for t in session.kernel.tasks + session.kernel.terminated_tasks
                        ]
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
                        console.print(
                            f"[bold green]Spawned task '{task_name}' (PID {new_pid}) @ [0x{base:02X}, 0x{limit:02X}), entry: 0x{entry:02X}[/bold green]"
                        )

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
                    console.print(
                        Panel(
                            "".join(logs),
                            title="Kernel Console Buffer (dmesg)",
                            border_style="yellow",
                        )
                    )

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
                console.print(
                    "[bold green]System shutting down... All subsystems halted. Goodbye![/bold green]"
                )
                break

            case _:
                console.print(
                    f"[red]Unknown command: '{cmd}'. Type 'help' for available commands.[/red]"
                )


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
    dashboard: Annotated[
        bool,
        typer.Option(
            "--dashboard", "-D", help="Launch fullscreen live split-screen dashboard directly."
        ),
    ] = False,
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

    if dashboard:
        session.run_dashboard(initial_demo=demo)
        return

    if demo:
        session.load_demo(demo)
        session.run_simulation(max_steps=steps)

    if asm:
        session.load_asm_file(asm)
        session.run_simulation(max_steps=steps)

    if not batch:
        run_interactive_shell(session)


@app.command("dashboard")
@app.command("tui")
def dashboard_cmd(
    demo: Annotated[
        str | None, typer.Option("--demo", "-d", help="Load built-in demo into dashboard")
    ] = None,
) -> None:
    """Launch fullscreen live split dashboard with persistent right-side inspector."""
    session = OSSimulatorSession(speed=0.0, animate=False)
    session.run_dashboard(initial_demo=demo)


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
    name: Annotated[
        str, typer.Argument(help="Demo name: counter, rogue, hello, math, multitask, all")
    ] = "all",
    steps: Annotated[int, typer.Option("--steps", help="Number of CPU steps to run")] = 100,
    interactive: Annotated[
        bool, typer.Option("--interactive", "-i", help="Enter shell after demo")
    ] = False,
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


@app.command("cpu")
def cpu_cmd(
    demo: Annotated[
        str | None, typer.Option("--demo", "-d", help="Load demo before showing CPU status")
    ] = None,
    steps: Annotated[
        int, typer.Option("--steps", help="CPU steps to run before showing status")
    ] = 0,
    interactive: Annotated[
        bool, typer.Option("--interactive", "-i", help="Enter interactive shell after display")
    ] = False,
) -> None:
    """Display detailed CPU registers, ALU flags, executing frame, and MMU page table."""
    session = OSSimulatorSession(speed=0.0, animate=False)
    if demo:
        session.load_demo(demo)
        if steps > 0:
            session.step(count=steps)
    session.show_cpu()
    if interactive:
        run_interactive_shell(session)


@app.command("status")
def status_cmd() -> None:
    """Display OS subsystem status and task counts."""
    session = OSSimulatorSession(speed=0.0, animate=False)
    session.show_status()


if __name__ == "__main__":
    app()
