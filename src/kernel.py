"""OS Kernel managing task scheduling, PCBs, multitasking loop, and expanded system call interface."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from src.cpu import CPU
from src.ram import RAM


class TaskState(Enum):
    """Lifecycle states of a task in the operating system."""

    READY = "READY"
    RUNNING = "RUNNING"
    SLEEPING = "SLEEPING"
    BLOCKED = "BLOCKED"
    TERMINATED = "TERMINATED"


class SchedulingPolicy(Enum):
    """Supported CPU scheduling policies."""

    PRIORITY_ROUND_ROBIN = "priority_round_robin"
    ROUND_ROBIN = "round_robin"
    FIFO = "fifo"


def create_default_page_table() -> dict[int, dict]:
    """Create an isolated page table with 16 entries (pages 0-15) for an 8-bit architecture.

    Each entry:
    {
        "frame": 0,       # Physical frame number (0-15)
        "valid": False,   # Whether this page is currently allocated
    }
    """
    return {page: {"frame": 0, "valid": False} for page in range(16)}


class PCB(dict):
    """Process Control Block holding execution context, memory bounds, and scheduling metadata.

    Inherits from dict for seamless backward compatibility with existing dictionary access
    while providing property accessors for modern object-oriented usage.
    """

    def __init__(
        self,
        task_id: int,
        name: str,
        priority: int,
        entry_point: int,
        stack_top: int,
        base: int = 0,
        limit: int = 256,
        task_sp: int | None = None,
        state: TaskState = TaskState.READY,
        parent_id: int | None = None,
        locks: list[int] | None = None,
        page_table: dict[int, dict] | None = None,
    ):
        sp = stack_top - 5 if task_sp is None else task_sp
        if page_table is None:
            page_table = create_default_page_table()

        super().__init__(
            task_id=task_id,
            task_name=name,
            name=name,
            task_priority=priority,
            priority=priority,
            task_sp=sp,
            sp=sp,
            entry_point=entry_point,
            stack_top=stack_top,
            base=base,
            limit=limit,
            state=state,
            sleep_ticks=0,
            wait_pid=None,
            exit_code=None,
            parent_id=parent_id,
            heap_ptr=base,
            cpu_cycles=0,
            locks=[] if locks is None else list(locks),
            page_table=page_table,
            page_faults=0,
        )

        # Replaces base and limit in PCB
        self["page_table"] = page_table

    @property
    def task_id(self) -> int:
        return self["task_id"]

    @task_id.setter
    def task_id(self, val: int) -> None:
        self["task_id"] = val

    @property
    def name(self) -> str:
        return self["name"]

    @name.setter
    def name(self, val: str) -> None:
        self["name"] = val
        self["task_name"] = val

    @property
    def task_name(self) -> str:
        return self["task_name"]

    @task_name.setter
    def task_name(self, val: str) -> None:
        self["task_name"] = val
        self["name"] = val

    @property
    def priority(self) -> int:
        return self["task_priority"]

    @priority.setter
    def priority(self, val: int) -> None:
        self["task_priority"] = val
        self["priority"] = val

    @property
    def task_priority(self) -> int:
        return self["task_priority"]

    @task_priority.setter
    def task_priority(self, val: int) -> None:
        self["task_priority"] = val
        self["priority"] = val

    @property
    def task_sp(self) -> int:
        return self["task_sp"]

    @task_sp.setter
    def task_sp(self, val: int) -> None:
        self["task_sp"] = val
        self["sp"] = val

    @property
    def state(self) -> TaskState:
        return self["state"]

    @state.setter
    def state(self, val: TaskState) -> None:
        self["state"] = val

    @property
    def base(self) -> int:
        return self["base"]

    @base.setter
    def base(self, val: int) -> None:
        self["base"] = val

    @property
    def limit(self) -> int:
        return self["limit"]

    @limit.setter
    def limit(self, val: int) -> None:
        self["limit"] = val

    @property
    def entry_point(self) -> int:
        return self["entry_point"]

    @property
    def stack_top(self) -> int:
        return self["stack_top"]

    @property
    def sleep_ticks(self) -> int:
        return self["sleep_ticks"]

    @sleep_ticks.setter
    def sleep_ticks(self, val: int) -> None:
        self["sleep_ticks"] = val

    @property
    def wait_pid(self) -> int | None:
        return self["wait_pid"]

    @wait_pid.setter
    def wait_pid(self, val: int | None) -> None:
        self["wait_pid"] = val

    @property
    def exit_code(self) -> int | None:
        return self["exit_code"]

    @exit_code.setter
    def exit_code(self, val: int | None) -> None:
        self["exit_code"] = val

    @property
    def heap_ptr(self) -> int:
        return self["heap_ptr"]

    @heap_ptr.setter
    def heap_ptr(self, val: int) -> None:
        self["heap_ptr"] = val

    @property
    def parent_id(self) -> int | None:
        return self["parent_id"]

    @parent_id.setter
    def parent_id(self, val: int | None) -> None:
        self["parent_id"] = val

    @property
    def locks(self) -> list[int]:
        return self["locks"]

    @locks.setter
    def locks(self, val: list[int]) -> None:
        self["locks"] = val

    @property
    def page_table(self) -> dict[int, dict]:
        return self["page_table"]

    @page_table.setter
    def page_table(self, val: dict[int, dict]) -> None:
        self["page_table"] = val

    @property
    def page_faults(self) -> int:
        return self["page_faults"]

    @page_faults.setter
    def page_faults(self, val: int) -> None:
        self["page_faults"] = val


class Scheduler:
    """Manages scheduling algorithms and ready queue selection."""

    def __init__(self, policy: SchedulingPolicy = SchedulingPolicy.PRIORITY_ROUND_ROBIN):
        self.policy = policy

    def pick_next_index(self, tasks: list[PCB], current_index: int) -> int | None:
        """Select next task index based on scheduling policy and task readiness."""
        if not tasks:
            return None

        # Filter to tasks ready or currently running
        ready_indices = [
            i for i, t in enumerate(tasks) if t["state"] in (TaskState.READY, TaskState.RUNNING)
        ]
        if not ready_indices:
            return None

        match self.policy:
            case SchedulingPolicy.PRIORITY_ROUND_ROBIN:
                highest_priority = max(tasks[i]["task_priority"] for i in ready_indices)
                eligible = [
                    i for i in ready_indices if tasks[i]["task_priority"] == highest_priority
                ]
                for idx in eligible:
                    if idx > current_index:
                        return idx
                return eligible[0]

            case SchedulingPolicy.ROUND_ROBIN:
                for idx in ready_indices:
                    if idx > current_index:
                        return idx
                return ready_indices[0]

            case SchedulingPolicy.FIFO:
                return ready_indices[0]

            case _:
                return ready_indices[0]

    def tick(self, tasks: list[PCB]) -> list[PCB]:
        """Decrement sleep counters and wake up ready tasks. Returns newly woken tasks."""
        woken: list[PCB] = []
        for task in tasks:
            if task["state"] == TaskState.SLEEPING:
                task["sleep_ticks"] = max(0, task["sleep_ticks"] - 1)
                if task["sleep_ticks"] == 0:
                    task["state"] = TaskState.READY
                    woken.append(task)
        return woken


class Kernel:
    """Operating System Kernel managing task scheduling, PCBs, and system calls."""

    # Interrupt Vector Table (IVT) addresses
    IVT_TIMER_VECTOR: int = 0x00
    ISR_TRAMPOLINE_ADDR: int = 0x20
    MAILBOX_OLD_SP: int = 0xFA
    MAILBOX_NEW_SP: int = 0xFB
    IVT_SYSCALL_VECTOR: int = 0x05

    # Idle task configuration
    IDLE_TASK_ADDR: int = 0x30
    IDLE_TASK_ID: int = 255

    # System Call IDs
    SYS_YIELD: int = 0x01
    SYS_EXIT: int = 0x02
    SYS_SLEEP: int = 0x03
    SYS_GETPID: int = 0x04
    SYS_GET_PID: int = 0x04  # Alias
    SYS_PRINT_NUM: int = 0x05
    SYS_PRINT_INT: int = 0x05  # Alias
    SYS_PRINT_CHAR: int = 0x06
    SYS_PUTC: int = 0x06  # Alias
    SYS_PRINT_STR: int = 0x07
    SYS_WRITE: int = 0x07  # Alias
    SYS_SPAWN: int = 0x08
    SYS_CREATE_TASK: int = 0x08  # Alias
    SYS_WAIT: int = 0x09
    SYS_WAITPID: int = 0x09  # Alias
    SYS_KILL: int = 0x0A
    SYS_GET_TICKS: int = 0x0B
    SYS_ALLOC: int = 0x0C
    SYS_MUTEX_LOCK: int = 0x0D
    SYS_MUTEX_UNLOCK: int = 0x0E
    SYS_LOCK: int = 0x0D  # Alias
    SYS_UNLOCK: int = 0x0E  # Alias

    # Assembly ISR Machine Code:
    # MOV ACC, SP (0x27) -> STORE 0xFA (0x02, 0xFA) ->
    # LOAD 0xFB (0x01, 0xFB) -> MOV SP, ACC (0x26) -> IRET (0x0F)
    ISR_MACHINE_CODE: list[int] = [
        0x27,  # MOV ACC, SP
        0x02,
        0xFA,  # STORE 0xFA (Save outgoing SP)
        0x01,
        0xFB,  # LOAD 0xFB  (Read incoming SP)
        0x26,  # MOV SP, ACC
        0x0F,  # IRET
    ]

    def __init__(self, ram: RAM, cpu: CPU):
        self.ram = ram
        self.cpu = cpu
        self.tasks: list[PCB] = []
        self.terminated_tasks: list[PCB] = []
        self.current_task_index: int = 0
        self.system_ticks: int = 0
        self.total_cycles: int = 0
        self.console_output: list[str] = []
        self.custom_syscalls: dict[int, Callable[[Kernel, int, int], int | None]] = {}
        self.locks: dict[int, dict] = {}
        self.last_fault: str | None = None
        self.scheduler = Scheduler(policy=SchedulingPolicy.PRIORITY_ROUND_ROBIN)
        self.free_frames: list[int] = list(range(4, 15))

        self.cpu.syscall_handler = self.handle_syscall
        self.cpu.fault_handler = self.handle_fault
        self.cpu.page_fault_handler = self.handle_page_fault
        self.page_fault_count: int = 0

        self.idle_task: PCB | None = None
        self._is_idle_running: bool = False
        self._init_idle_task()

        if hasattr(self.ram, "add_write_hook"):
            self.ram.add_write_hook(self.MAILBOX_OLD_SP, self.schedule)

    def alloc_frame(self) -> int:
        """Allocate a free physical frame (4-14)."""
        if not self.free_frames:
            raise RuntimeError("Out of physical memory: No free frames available.")
        return self.free_frames.pop(0)

    def alloc_frame_for_page(self, preferred_frame: int | None = None) -> int:
        """Allocate preferred physical frame if available, otherwise any free frame."""
        if preferred_frame is not None and preferred_frame in self.free_frames:
            self.free_frames.remove(preferred_frame)
            return preferred_frame
        return self.alloc_frame()

    def free_frame(self, frame: int) -> None:
        """Return a physical frame to the free frame pool."""
        if 4 <= frame < 15 and frame not in self.free_frames:
            self.free_frames.append(frame)
            self.free_frames.sort()

    def free_task_frames(self, task: PCB) -> None:
        """Free physical frames allocated to a task's page table."""
        pt = task.get("page_table")
        if not pt:
            return
        for entry in pt.values():
            if entry.get("valid"):
                frame = entry.get("frame")
                if frame is not None and 4 <= frame < 15:
                    self.free_frame(frame)
                entry["valid"] = False

    def get_free_frame_count(self) -> int:
        """Return the number of currently free physical frames."""
        return len(self.free_frames)

    def _read_task_byte(self, task: PCB, vaddr: int) -> int:
        pt = task.get("page_table")
        if pt is not None:
            page = (vaddr & 0xFF) >> 4
            entry = pt.get(page)
            if (not entry or not entry.get("valid")) and (task["base"] <= (vaddr & 0xFF) < task["limit"]):
                self.handle_page_fault(vaddr, task=task)
                entry = pt.get(page)
            if entry and entry.get("valid"):
                return self.ram.read((entry["frame"] << 4) | (vaddr & 0x0F))
            return 0
        return self.ram.read(vaddr)

    def _write_task_byte(self, task: PCB, vaddr: int, val: int) -> None:
        pt = task.get("page_table")
        if pt is not None:
            page = (vaddr & 0xFF) >> 4
            entry = pt.get(page)
            if (not entry or not entry.get("valid")) and (task["base"] <= (vaddr & 0xFF) < task["limit"]):
                self.handle_page_fault(vaddr, task=task)
                entry = pt.get(page)
            if entry and entry.get("valid"):
                self.ram.write((entry["frame"] << 4) | (vaddr & 0x0F), val & 0xFF)
            return
        self.ram.write(vaddr, val & 0xFF)

    def _init_idle_task(self) -> None:
        """Set up a benign in-memory idle task to run when all user tasks are sleeping."""
        # 0x30: JUMP 0x30 (infinite loop at IDLE_TASK_ADDR)
        self.ram.write(self.IDLE_TASK_ADDR, 0x30)
        self.ram.write(self.IDLE_TASK_ADDR + 1, self.IDLE_TASK_ADDR)

        # Forge stack frame at 0x3E
        idle_stack_top = 0x3E
        self.ram.write(idle_stack_top, self.IDLE_TASK_ADDR)  # PC
        self.ram.write(idle_stack_top - 1, 0x00)  # ACC
        self.ram.write(idle_stack_top - 2, 0x00)  # R1
        self.ram.write(idle_stack_top - 3, 0x00)  # R2
        self.ram.write(idle_stack_top - 4, 0x00)  # Flags

        idle_page_table = create_default_page_table()
        for p in range(4):
            idle_page_table[p] = {"frame": p, "valid": True}

        self.idle_task = PCB(
            task_id=self.IDLE_TASK_ID,
            name="[idle]",
            priority=0,
            entry_point=self.IDLE_TASK_ADDR,
            stack_top=idle_stack_top,
            base=0x00,
            limit=0x40,
            task_sp=idle_stack_top - 5,
            state=TaskState.READY,
            page_table=idle_page_table,
        )

    def install_isr(self) -> None:
        """Write the assembly context-switch trampoline into kernel RAM."""
        for offset, byte in enumerate(self.ISR_MACHINE_CODE):
            self.ram.write(self.ISR_TRAMPOLINE_ADDR + offset, byte)

    def create_task(
        self,
        task_id: int,
        name: str,
        priority: int,
        entry_point: int,
        stack_top: int,
        base: int,
        limit: int,
        parent_id: int | None = None,
        page_table: dict[int, dict] | None = None,
    ) -> PCB:
        """Forge a 5-byte interrupt frame in RAM and register the task PCB."""
        task_pcb = PCB(
            task_id=task_id,
            name=name,
            priority=priority,
            entry_point=entry_point,
            stack_top=stack_top,
            base=base,
            limit=limit,
            task_sp=stack_top - 5,
            state=TaskState.READY,
            parent_id=parent_id,
            page_table=page_table,
        )

        # Push fake hardware context in reverse order of IRET pops:
        # flags (pop 1st), R2 (pop 2nd), R1 (pop 3rd), ACC (pop 4th), PC (pop 5th)
        self._write_task_byte(task_pcb, stack_top, entry_point & 0xFF)  # PC (popped last)
        self._write_task_byte(task_pcb, stack_top - 1, 0x00)  # ACC
        self._write_task_byte(task_pcb, stack_top - 2, 0x00)  # R1
        self._write_task_byte(task_pcb, stack_top - 3, 0x00)  # R2
        self._write_task_byte(task_pcb, stack_top - 4, 0x00)  # Flags (popped first)

        self.tasks.append(task_pcb)
        return task_pcb

    def load_task_code(
        self,
        name: str,
        code: list[int],
        priority: int = 1,
        partition_size: int = 32,
        base_address: int | None = None,
    ) -> PCB:
        """Allocate a memory partition, assign physical frames, write machine code, and register task PCB."""
        if not code:
            raise ValueError("Cannot load empty code into task.")

        # Determine partition base
        if base_address is not None:
            base = base_address
        else:
            base = 0x40 if not self.tasks else max(t["limit"] for t in self.tasks)

        actual_size = max(partition_size, len(code) + 10)
        limit = base + actual_size

        if limit > 256:
            raise RuntimeError(
                f"Out of memory: Task '{name}' requires partition up to 0x{limit:02X}, "
                f"exceeding RAM boundary 0x100."
            )

        if len(code) > (limit - base - 6):
            raise RuntimeError(
                f"Code size ({len(code)} bytes) too large for partition size ({actual_size} bytes). "
                f"Need room for 5-byte stack frame."
            )

        start_page = base >> 4
        code_end_page = (base + len(code) - 1) >> 4
        stack_page = (limit - 1) >> 4

        # Lazy allocation: pre-allocate code pages and stack page; other pages fault in on demand
        prealloc_pages = sorted(set(range(start_page, code_end_page + 1)) | {stack_page})

        if len(self.free_frames) < len(prealloc_pages):
            raise RuntimeError(
                f"Out of physical memory: Task '{name}' requires {len(prealloc_pages)} frames at startup, "
                f"but only {len(self.free_frames)} free frames available."
            )

        page_table = create_default_page_table()
        allocated_frames: list[int] = []
        try:
            for p in prealloc_pages:
                frame = self.alloc_frame_for_page(preferred_frame=p)
                allocated_frames.append(frame)
                page_table[p] = {"frame": frame, "valid": True}
        except Exception:
            for f in allocated_frames:
                self.free_frame(f)
            raise

        new_id = (
            max(
                [t["task_id"] for t in self.tasks + self.terminated_tasks],
                default=-1,
            )
            + 1
        )
        entry_point = base
        stack_top = limit - 1

        task_pcb = self.create_task(
            task_id=new_id,
            name=name,
            priority=priority if priority > 0 else 1,
            entry_point=entry_point,
            stack_top=stack_top,
            base=base,
            limit=limit,
            page_table=page_table,
        )

        # Write machine code into RAM at the allocated physical frames
        for offset, byte_val in enumerate(code):
            self._write_task_byte(task_pcb, base + offset, byte_val & 0xFF)

        return task_pcb

    def pick_next_task_index(self) -> int:
        """Select next task index using the configured scheduler policy."""
        idx = self.scheduler.pick_next_index(self.tasks, self.current_task_index)
        if idx is not None:
            return idx
        return 0 if self.tasks else 0

    def tick(self) -> None:
        """Advance kernel timer by 1 tick, waking up sleeping tasks if elapsed."""
        self.system_ticks += 1
        self.scheduler.tick(self.tasks)

    def _any_task_ready(self) -> bool:
        """Check if any user task is currently ready or running."""
        return any(t["state"] in (TaskState.READY, TaskState.RUNNING) for t in self.tasks)

    def _any_task_sleeping(self) -> bool:
        """Check if any user task is currently sleeping or blocked."""
        return any(t["state"] in (TaskState.SLEEPING, TaskState.BLOCKED) for t in self.tasks)

    def has_active_tasks(self) -> bool:
        """Return True if any user task is active (ready, running, sleeping, or blocked)."""
        return any(
            t["state"]
            in (TaskState.READY, TaskState.RUNNING, TaskState.SLEEPING, TaskState.BLOCKED)
            for t in self.tasks
        )

    def schedule(self) -> None:
        """Preemptive context switcher triggered by the assembly ISR mailbox write."""
        if not self.tasks and not self.has_active_tasks():
            self.cpu.halt()
            return

        old_sp = self.ram.read(self.MAILBOX_OLD_SP)

        # Update outgoing task context
        if self._is_idle_running and self.idle_task is not None:
            self.idle_task["task_sp"] = old_sp
        elif self.tasks and 0 <= self.current_task_index < len(self.tasks):
            outgoing = self.tasks[self.current_task_index]
            outgoing["task_sp"] = old_sp
            if outgoing["state"] == TaskState.RUNNING:
                outgoing["state"] = TaskState.READY

        # Advance timer ticks and wake up any expired sleeping tasks
        self.tick()

        # Run scheduler selection
        next_idx = self.scheduler.pick_next_index(self.tasks, self.current_task_index)

        if next_idx is not None:
            self._is_idle_running = False
            self.current_task_index = next_idx
            incoming = self.tasks[next_idx]
            incoming["state"] = TaskState.RUNNING

            # Update CPU hardware memory protection registers
            self.cpu.base_address = incoming["base"]
            self.cpu.limit_address = incoming["limit"]
            self.cpu.page_table = incoming["page_table"]

            # Write incoming task SP into mailbox for assembly ISR trampoline to restore
            self.ram.write(self.MAILBOX_NEW_SP, incoming["task_sp"])
        elif self._any_task_sleeping() and self.idle_task is not None:
            # No ready user tasks, but some are sleeping; run idle task
            self._is_idle_running = True
            self.cpu.base_address = self.idle_task["base"]
            self.cpu.limit_address = self.idle_task["limit"]
            self.cpu.page_table = self.idle_task["page_table"]
            self.ram.write(self.MAILBOX_NEW_SP, self.idle_task["task_sp"])
        else:
            # All tasks terminated; halt CPU
            self.cpu.halt()
            self.ram.write(self.MAILBOX_NEW_SP, old_sp)

    def _switch_to_idle(self) -> None:
        """Switch CPU execution to the kernel idle task."""
        if self.idle_task is None:
            return
        self._is_idle_running = True
        self.cpu.registers["SP"] = self.idle_task["task_sp"]
        self.cpu.base_address = self.idle_task["base"]
        self.cpu.limit_address = self.idle_task["limit"]
        self.cpu.page_table = self.idle_task["page_table"]
        self.cpu.iret()

    def multitasking_loop(self, max_steps: int | None = None) -> None:
        """Multitasking loop: executes CPU steps, manages task scheduling, ticks, and state."""
        if self.has_active_tasks():
            if self.cpu.halted:
                self.cpu.halted = False

            # If no task is currently running, dispatch the first ready task
            if not any(t["state"] == TaskState.RUNNING for t in self.tasks):
                ready_idx = self.scheduler.pick_next_index(self.tasks, -1)
                if ready_idx is not None:
                    self.current_task_index = ready_idx
                    incoming = self.tasks[ready_idx]
                    incoming["state"] = TaskState.RUNNING
                    self.cpu.registers["SP"] = incoming["task_sp"]
                    self.cpu.base_address = incoming["base"]
                    self.cpu.limit_address = incoming["limit"]
                    self.cpu.page_table = incoming["page_table"]
                    self.cpu.iret()

        steps = 0
        while not self.cpu.halted and self.has_active_tasks():
            if max_steps is not None and steps >= max_steps:
                break

            # Handle state where all active user tasks are sleeping
            if not self._any_task_ready():
                if self._any_task_sleeping():
                    if not self._is_idle_running:
                        self._switch_to_idle()
                else:
                    self.cpu.halt()
                    break

            self.cpu.step()
            steps += 1
            self.total_cycles += 1

    def run(self, max_steps: int | None = None) -> None:
        """Convenience method to execute the kernel multitasking loop."""
        self.multitasking_loop(max_steps=max_steps)

    def handle_page_fault(self, virtual_addr: int, task: PCB | None = None) -> bool:
        """Handle a page fault via demand paging within task memory partition."""
        if task is None:
            if not self.tasks or not (0 <= self.current_task_index < len(self.tasks)):
                return False
            task = self.tasks[self.current_task_index]

        vaddr = virtual_addr & 0xFF
        base = task["base"]
        limit = task["limit"]

        # Check bounds: address must be within task partition
        if not (base <= vaddr < limit):
            return False

        page = vaddr >> 4
        pt = task.get("page_table")
        if pt is None:
            return False

        entry = pt.get(page)
        if entry is None:
            return False

        if entry.get("valid", False):
            return True

        # Check if physical frame available
        if not self.free_frames:
            return False

        frame = self.alloc_frame()
        # Zero out newly allocated frame memory
        frame_base = frame << 4
        for i in range(16):
            self.ram.write(frame_base + i, 0)

        entry["frame"] = frame
        entry["valid"] = True

        self.page_fault_count += 1
        task["page_faults"] = task.get("page_faults", 0) + 1
        print(
            f"[Kernel] Page fault handled: Task '{task['task_name']}' (PID {task['task_id']}) "
            f"mapped virtual page {page} (0x{page << 4:02X}) to physical frame {frame} (0x{frame << 4:02X})"
        )
        return True

    def handle_fault(self, fault_type: str) -> None:
        """Terminate the offending task and switch to the next available task."""
        self.last_fault = fault_type
        if self.tasks and 0 <= self.current_task_index < len(self.tasks):
            current_task = self.tasks[self.current_task_index]["task_name"]
            print(f"Fault triggered by {current_task}: {fault_type}")
            self.sys_exit(exit_code=255)
        else:
            print(f"Fault occurred: {fault_type}")
            self.cpu.halt()

    def register_syscall(
        self,
        syscall_id: int,
        handler: Callable[[Kernel, int, int], int | None],
    ) -> None:
        """Register a custom system call handler."""
        self.custom_syscalls[syscall_id] = handler

    def handle_syscall(self) -> None:
        """Inspect the stack frame and dispatch the appropriate system call."""
        sp = self.cpu.registers["SP"]
        current_task = (
            self.tasks[self.current_task_index]
            if self.tasks and 0 <= self.current_task_index < len(self.tasks)
            else None
        )
        if current_task is not None:
            syscall_id = self._read_task_byte(current_task, sp + 4)
            arg1 = self._read_task_byte(current_task, sp + 3)
            arg2 = self._read_task_byte(current_task, sp + 2)
        else:
            syscall_id = self.ram.read(sp + 4)  # ACC holds the syscall ID
            arg1 = self.ram.read(sp + 3)  # R1 holds argument 1
            arg2 = self.ram.read(sp + 2)  # R2 holds argument 2

        def _write_ret(val: int) -> None:
            if current_task is not None:
                self._write_task_byte(current_task, sp + 4, val & 0xFF)
            else:
                self.ram.write(sp + 4, val & 0xFF)

        # Check custom registered syscalls first
        if syscall_id in self.custom_syscalls:
            result = self.custom_syscalls[syscall_id](self, arg1, arg2)
            if result is not None:
                _write_ret(result)
            self.cpu.iret()
            return

        match syscall_id:
            case self.SYS_YIELD:
                self.sys_yield()

            case self.SYS_EXIT:
                self.sys_exit(exit_code=arg1)

            case self.SYS_SLEEP:
                self.sys_sleep(ticks=arg1)

            case self.SYS_GETPID:
                pid = self.sys_getpid()
                _write_ret(pid)
                self.cpu.iret()

            case self.SYS_PRINT_NUM:
                ret = self.sys_print_num(num=arg1)
                _write_ret(ret)
                self.cpu.iret()

            case self.SYS_PRINT_CHAR:
                ret = self.sys_print_char(char_code=arg1)
                _write_ret(ret)
                self.cpu.iret()

            case self.SYS_PRINT_STR:
                ret = self.sys_print_str(addr=arg1, length=arg2)
                _write_ret(ret)
                self.cpu.iret()

            case self.SYS_SPAWN:
                new_pid = self.sys_spawn(entry_point=arg1, priority=arg2)
                _write_ret(new_pid)
                self.cpu.iret()

            case self.SYS_WAIT:
                self.sys_wait(target_pid=arg1)

            case self.SYS_KILL:
                ret = self.sys_kill(target_pid=arg1)
                _write_ret(ret)
                self.cpu.iret()

            case self.SYS_GET_TICKS:
                ticks = self.sys_get_ticks()
                _write_ret(ticks)
                self.cpu.iret()

            case self.SYS_ALLOC:
                addr = self.sys_alloc(size=arg1)
                _write_ret(addr)
                self.cpu.iret()

            case self.SYS_MUTEX_LOCK:
                self.sys_mutex_lock(lock_id=arg1)

            case self.SYS_MUTEX_UNLOCK:
                self.sys_mutex_unlock(lock_id=arg1)
                self.cpu.iret()

            case _:
                raise RuntimeError(f"Unknown Syscall ID: {hex(syscall_id)}")

    def sys_yield(self) -> None:
        """Voluntary yield: save current SP, pick next task, and switch."""
        if not self.tasks:
            self.cpu.halt()
            return

        current_task = self.tasks[self.current_task_index]
        current_task["task_sp"] = self.cpu.registers["SP"]
        if current_task["state"] == TaskState.RUNNING:
            current_task["state"] = TaskState.READY

        # Pick the next ready task
        next_idx = self.scheduler.pick_next_index(self.tasks, self.current_task_index)
        if next_idx is None:
            # Only this task is ready; resume it
            next_idx = self.current_task_index

        self.current_task_index = next_idx
        next_task = self.tasks[self.current_task_index]
        next_task["state"] = TaskState.RUNNING

        # Restore incoming task context and bounds
        self.cpu.registers["SP"] = next_task["task_sp"]
        self.cpu.base_address = next_task["base"]
        self.cpu.limit_address = next_task["limit"]
        self.cpu.page_table = next_task["page_table"]

        self.cpu.iret()

    def sys_exit(self, exit_code: int = 0) -> None:
        """Terminate the current task and switch to the next ready task."""
        if not self.tasks or self.current_task_index >= len(self.tasks):
            self.cpu.halt()
            return

        terminated_task = self.tasks.pop(self.current_task_index)
        terminated_task["state"] = TaskState.TERMINATED
        terminated_task["exit_code"] = exit_code
        self.terminated_tasks.append(terminated_task)
        self.free_task_frames(terminated_task)

        print(f"Task {terminated_task['task_name']} exited with code {exit_code}")

        # Wake up any task waiting on this terminated task
        for task in self.tasks:
            if (
                task["state"] == TaskState.BLOCKED
                and task["wait_pid"] == terminated_task["task_id"]
            ):
                task["state"] = TaskState.READY
                task["wait_pid"] = None
                # Write exit code into waiting task's saved ACC on its stack
                self._write_task_byte(task, task["task_sp"] + 4, exit_code & 0xFF)

        # Release any mutexes owned by the exiting task and remove from wait queues
        for lock_id, lock in self.locks.items():
            if terminated_task["task_id"] in lock.get("wait_queue", []):
                lock["wait_queue"].remove(terminated_task["task_id"])
            if lock.get("owner_pid") == terminated_task["task_id"]:
                found_waiter = False
                while lock["wait_queue"]:
                    next_task_id = lock["wait_queue"].pop(0)
                    target = next((t for t in self.tasks if t["task_id"] == next_task_id), None)
                    if target is not None:
                        target["state"] = TaskState.READY
                        lock["owner_pid"] = next_task_id
                        if "locks" in target and lock_id not in target["locks"]:
                            target["locks"].append(lock_id)
                        found_waiter = True
                        break
                if not found_waiter:
                    lock["locked"] = False
                    lock["owner_pid"] = None

        if not self.has_active_tasks():
            print("All tasks completed. Halting CPU.")
            self.cpu.halt()
            return

        # Pick next ready task
        next_idx = self.scheduler.pick_next_index(self.tasks, self.current_task_index - 1)

        if next_idx is not None:
            self.current_task_index = next_idx
            next_task = self.tasks[self.current_task_index]
            next_task["state"] = TaskState.RUNNING

            self.cpu.registers["SP"] = next_task["task_sp"]
            self.cpu.base_address = next_task["base"]
            self.cpu.limit_address = next_task["limit"]
            self.cpu.page_table = next_task["page_table"]
            self.cpu.iret()
        elif self._any_task_sleeping() and self.idle_task is not None:
            self._switch_to_idle()
        else:
            print("All tasks completed. Halting CPU.")
            self.cpu.halt()

    def sys_sleep(self, ticks: int) -> None:
        """Put current task to sleep for specified timer ticks."""
        current_task = self.tasks[self.current_task_index]
        current_task["task_sp"] = self.cpu.registers["SP"]
        current_task["state"] = TaskState.SLEEPING
        current_task["sleep_ticks"] = max(1, ticks)

        # Write 0 as return value into saved ACC so waking task receives 0
        self._write_task_byte(current_task, current_task["task_sp"] + 4, 0x00)

        # Select next task to run
        next_idx = self.scheduler.pick_next_index(self.tasks, self.current_task_index)
        if next_idx is not None:
            self.current_task_index = next_idx
            next_task = self.tasks[self.current_task_index]
            next_task["state"] = TaskState.RUNNING

            self.cpu.registers["SP"] = next_task["task_sp"]
            self.cpu.base_address = next_task["base"]
            self.cpu.limit_address = next_task["limit"]
            self.cpu.page_table = next_task["page_table"]
            self.cpu.iret()
        elif self.idle_task is not None:
            self._switch_to_idle()
        else:
            self.cpu.halt()

    def sys_getpid(self) -> int:
        """Return the current task's ID."""
        if self.tasks and 0 <= self.current_task_index < len(self.tasks):
            return self.tasks[self.current_task_index]["task_id"]
        return 0

    def sys_print_num(self, num: int) -> int:
        """Print integer to console and record in kernel console buffer."""
        msg = str(num & 0xFF)
        self.console_output.append(msg)
        print(f"[Kernel Console] {msg}")
        return 0

    def sys_print_char(self, char_code: int) -> int:
        """Print ASCII character to console and record in kernel console buffer."""
        ch = chr(char_code & 0xFF)
        self.console_output.append(ch)
        print(f"[Kernel Console] {ch}")
        return 0

    def sys_print_str(self, addr: int, length: int) -> int:
        """Print string from memory, verifying memory protection bounds."""
        current_task = self.tasks[self.current_task_index]
        pt = current_task.get("page_table")

        if pt is not None and any(entry.get("valid") for entry in pt.values()):
            page = (addr & 0xFF) >> 4
            if not pt.get(page, {}).get("valid", False) and not self.handle_page_fault(
                addr, task=current_task
            ):
                self.handle_fault("Segmentation Fault: Illegal String Read")
                return 0xFF
        else:
            base = current_task["base"]
            limit = current_task["limit"]
            if not (base <= addr < limit):
                self.handle_fault("Segmentation Fault: Illegal String Read")
                return 0xFF

        chars: list[str] = []
        read_len = length if length > 0 else 256
        for offset in range(read_len):
            cur_addr = addr + offset
            if pt is not None and any(entry.get("valid") for entry in pt.values()):
                cur_page = (cur_addr & 0xFF) >> 4
                entry = pt.get(cur_page)
                if not entry or not entry.get("valid", False):
                    if not self.handle_page_fault(cur_addr, task=current_task):
                        break
                    entry = pt.get(cur_page)
                paddr = (entry["frame"] << 4) | (cur_addr & 0x0F)
            else:
                if cur_addr >= current_task["limit"]:
                    break
                paddr = cur_addr

            b = self.ram.read(paddr)
            if length == 0 and b == 0:  # Null-terminated
                break
            chars.append(chr(b))

        s = "".join(chars)
        self.console_output.append(s)
        print(f"[Kernel Console] {s}")
        return len(chars)

    def sys_spawn(self, entry_point: int, priority: int) -> int:
        """Dynamically create a new task with given entry point and priority."""
        new_id = (
            max(
                [t["task_id"] for t in self.tasks + self.terminated_tasks],
                default=-1,
            )
            + 1
        )

        # Allocate memory partition after highest existing boundary
        highest_limit = max(
            [t["limit"] for t in self.tasks + self.terminated_tasks],
            default=0x40,
        )
        partition_size = 32
        new_base = highest_limit
        new_limit = new_base + partition_size

        if new_limit > 256:
            return 0xFF  # Out of virtual address space

        start_page = new_base >> 4
        entry_page = entry_point >> 4
        stack_page = (new_limit - 1) >> 4
        prealloc_pages = sorted(set(range(start_page, entry_page + 1)) | {stack_page})

        if len(self.free_frames) < len(prealloc_pages):
            return 0xFF  # Out of memory

        page_table = create_default_page_table()
        allocated_frames: list[int] = []
        try:
            for p in prealloc_pages:
                frame = self.alloc_frame_for_page(preferred_frame=p)
                allocated_frames.append(frame)
                page_table[p] = {"frame": frame, "valid": True}
        except Exception:
            for f in allocated_frames:
                self.free_frame(f)
            return 0xFF

        new_stack_top = new_limit - 1
        curr_pid = self.sys_getpid()
        self.create_task(
            task_id=new_id,
            name=f"Task_{new_id}",
            priority=priority if priority > 0 else 1,
            entry_point=entry_point,
            stack_top=new_stack_top,
            base=new_base,
            limit=new_limit,
            parent_id=curr_pid,
            page_table=page_table,
        )
        return new_id

    def sys_wait(self, target_pid: int) -> None:
        """Wait for a target task to terminate and return its exit code."""
        current_task = self.tasks[self.current_task_index]
        sp = self.cpu.registers["SP"]

        # Check if already terminated
        for term in self.terminated_tasks:
            if term["task_id"] == target_pid:
                exit_code = term["exit_code"] if term["exit_code"] is not None else 0
                self._write_task_byte(current_task, sp + 4, exit_code & 0xFF)
                self.cpu.iret()
                return

        # Check if active
        target = next((t for t in self.tasks if t["task_id"] == target_pid), None)
        if target is None:
            # Target PID does not exist
            self._write_task_byte(current_task, sp + 4, 0xFF)
            self.cpu.iret()
            return

        # Block current task until target terminates
        current_task["task_sp"] = self.cpu.registers["SP"]
        current_task["state"] = TaskState.BLOCKED
        current_task["wait_pid"] = target_pid

        # Switch to next ready task
        next_idx = self.scheduler.pick_next_index(self.tasks, self.current_task_index)
        if next_idx is not None:
            self.current_task_index = next_idx
            next_task = self.tasks[self.current_task_index]
            next_task["state"] = TaskState.RUNNING

            self.cpu.registers["SP"] = next_task["task_sp"]
            self.cpu.base_address = next_task["base"]
            self.cpu.limit_address = next_task["limit"]
            self.cpu.page_table = next_task["page_table"]
            self.cpu.iret()
        elif self.idle_task is not None:
            self._switch_to_idle()
        else:
            self.cpu.halt()

    def sys_kill(self, target_pid: int) -> int:
        """Terminate a specific task by PID."""
        if self.tasks and self.tasks[self.current_task_index]["task_id"] == target_pid:
            self.sys_exit(exit_code=9)
            return 0

        target_idx = next(
            (i for i, t in enumerate(self.tasks) if t["task_id"] == target_pid),
            None,
        )
        if target_idx is None:
            return 0xFF  # Not found

        killed_task = self.tasks.pop(target_idx)
        killed_task["state"] = TaskState.TERMINATED
        killed_task["exit_code"] = 9
        self.terminated_tasks.append(killed_task)
        self.free_task_frames(killed_task)

        # Wake up any task waiting on this PID
        for task in self.tasks:
            if task["state"] == TaskState.BLOCKED and task["wait_pid"] == target_pid:
                task["state"] = TaskState.READY
                task["wait_pid"] = None
                self._write_task_byte(task, task["task_sp"] + 4, 9)

        # Release any mutexes owned by the killed task and remove from wait queues
        for lock_id, lock in self.locks.items():
            if killed_task["task_id"] in lock.get("wait_queue", []):
                lock["wait_queue"].remove(killed_task["task_id"])
            if lock.get("owner_pid") == killed_task["task_id"]:
                found_waiter = False
                while lock["wait_queue"]:
                    next_task_id = lock["wait_queue"].pop(0)
                    target = next((t for t in self.tasks if t["task_id"] == next_task_id), None)
                    if target is not None:
                        target["state"] = TaskState.READY
                        lock["owner_pid"] = next_task_id
                        if "locks" in target and lock_id not in target["locks"]:
                            target["locks"].append(lock_id)
                        found_waiter = True
                        break
                if not found_waiter:
                    lock["locked"] = False
                    lock["owner_pid"] = None

        if target_idx < self.current_task_index:
            self.current_task_index -= 1

        return 0

    def sys_get_ticks(self) -> int:
        """Return the current system tick count."""
        return self.system_ticks & 0xFF

    def sys_alloc(self, size: int) -> int:
        """Allocate heap memory, mapping new virtual pages to physical frames."""
        if size <= 0:
            return 0

        current_task = self.tasks[self.current_task_index]
        heap_start = current_task["heap_ptr"]
        new_heap_end = heap_start + size

        if new_heap_end > current_task["limit"] - 10 or new_heap_end > 256:
            return 0

        pt = current_task.get("page_table")
        if pt is not None:
            start_page = heap_start >> 4
            end_page = (new_heap_end - 1) >> 4
            needed = [
                p for p in range(start_page, end_page + 1) if not pt.get(p, {}).get("valid", False)
            ]

            if len(needed) > len(self.free_frames):
                return 0

            allocated: list[tuple[int, int]] = []
            try:
                for p in needed:
                    frame = self.alloc_frame()
                    allocated.append((p, frame))
                    pt[p] = {"frame": frame, "valid": True}
            except Exception:
                for p, f in allocated:
                    self.free_frame(f)
                    pt[p] = {"frame": 0, "valid": False}
                return 0

        current_task["heap_ptr"] = new_heap_end
        return heap_start

    def get_held_locks(self, pid: int | None = None) -> list[int]:
        """Return a sorted list of lock IDs currently held by the specified task PID."""
        target_pid = self.sys_getpid() if pid is None else pid
        return sorted(
            lid
            for lid, ldata in self.locks.items()
            if ldata.get("owner_pid") == target_pid and ldata.get("locked")
        )

    def can_acquire_lock(self, lock_id: int, pid: int | None = None) -> bool:
        """Check if lock_id is strictly greater than all locks currently owned by the task."""
        held = self.get_held_locks(pid)
        return not held or lock_id > max(held)

    def sys_mutex_lock(self, lock_id: int) -> None:
        """Acquire a mutex lock. Block task and reschedule if lock is already taken."""
        if not self.tasks or not (0 <= self.current_task_index < len(self.tasks)):
            return

        current_task = self.tasks[self.current_task_index]
        current_pid = self.sys_getpid()

        # 🔍 Check: The kernel looks at all the locks this task currently holds.
        held_locks = self.get_held_locks(current_pid)

        # 📏 Condition: The new_lock_id must be strictly greater (>) than any lock the task already owns.
        # 🛑 Violation: If the task tries to acquire a lock with a smaller or equal number, it breaks the rule!
        if any(lock_id <= lid for lid in held_locks):
            self.handle_fault(
                f"Lock Ordering Violation: Task {current_pid} attempted to acquire lock {lock_id} "
                f"while holding lock(s) {held_locks} (must be strictly greater)"
            )
            return

        if lock_id not in self.locks:
            self.locks[lock_id] = {
                "locked": False,
                "owner_pid": None,
                "wait_queue": [],
            }

        lock = self.locks[lock_id]

        # If the lock is free:
        if not lock["locked"]:
            lock["locked"] = True
            lock["owner_pid"] = current_pid
            if "locks" in current_task and lock_id not in current_task["locks"]:
                current_task["locks"].append(lock_id)
            self.cpu.iret()
            return

        # If the lock is already taken:
        lock["wait_queue"].append(current_pid)
        current_task["task_sp"] = self.cpu.registers["SP"]
        current_task["state"] = TaskState.BLOCKED

        # Call the scheduler to run another task
        next_idx = self.scheduler.pick_next_index(self.tasks, self.current_task_index)
        if next_idx is not None:
            self._is_idle_running = False
            self.current_task_index = next_idx
            next_task = self.tasks[self.current_task_index]
            next_task["state"] = TaskState.RUNNING

            self.cpu.registers["SP"] = next_task["task_sp"]
            self.cpu.base_address = next_task["base"]
            self.cpu.limit_address = next_task["limit"]
            self.cpu.page_table = next_task["page_table"]
            self.cpu.iret()
        elif self.idle_task is not None:
            self._switch_to_idle()
        else:
            self.cpu.halt()

    def sys_mutex_unlock(self, lock_id: int) -> None:
        """Release a mutex lock. Wake up the next waiting task if any."""
        if not self.tasks or not (0 <= self.current_task_index < len(self.tasks)):
            return

        if lock_id not in self.locks:
            return

        lock = self.locks[lock_id]
        current_pid = self.sys_getpid()
        current_task = self.tasks[self.current_task_index]

        # Check that the caller is the owner_pid
        if lock["owner_pid"] != current_pid:
            return

        if "locks" in current_task and lock_id in current_task["locks"]:
            current_task["locks"].remove(lock_id)

        # If wait_queue has waiting tasks:
        found_waiter = False
        while lock["wait_queue"]:
            next_task_id = lock["wait_queue"].pop(0)
            target = next((t for t in self.tasks if t["task_id"] == next_task_id), None)
            if target is not None:
                target["state"] = TaskState.READY
                lock["owner_pid"] = next_task_id
                if "locks" in target and lock_id not in target["locks"]:
                    target["locks"].append(lock_id)
                found_waiter = True
                break

        if not found_waiter:
            # If the queue is empty:
            lock["locked"] = False
            lock["owner_pid"] = None

    def get_console_output(self) -> str:
        """Return concatenated console output produced by system calls."""
        return "".join(self.console_output)

    def start(self, max_steps: int | None = None) -> None:
        """Bootstrap the first task and start the multitasking loop."""
        if not self.tasks:
            raise RuntimeError("Cannot start kernel: Task ready queue is empty.")

        # Ensure the ISR routine is in place
        self.install_isr()

        # Load Task 0's initial SP and launch via IRET
        self.current_task_index = 0
        first_task = self.tasks[0]
        first_task["state"] = TaskState.RUNNING

        self.cpu.registers["SP"] = first_task["task_sp"]
        self.cpu.base_address = first_task["base"]
        self.cpu.limit_address = first_task["limit"]
        self.cpu.page_table = first_task["page_table"]
        self.cpu.halted = False

        self.cpu.iret()  # Unpacks forged context into registers
        self.multitasking_loop(max_steps=max_steps)
