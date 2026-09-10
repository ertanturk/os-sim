"""CPU class for the OS simulator."""

from __future__ import annotations

from collections.abc import Callable

from src.ram import RAM


class CPUFault(Exception):
    """Base class for CPU hardware traps and exceptions."""

    pass


class DivisionByZeroFault(CPUFault):
    """Raised when an instruction attempts division by zero."""

    pass


class InvalidRegisterError(CPUFault):
    """Raised when referencing a register that does not exist."""

    pass


class InvalidInstructionFault(CPUFault):
    """Raised when attempting to execute an illegal or malformed instruction."""

    pass


class PrivilegeViolationFault(CPUFault):
    """Raised when attempting to execute an illegal or malformed instruction."""

    pass


class _FetchFault(CPUFault):
    """Internal signal to cleanly abort the current instruction cycle."""

    pass


class CPU:
    """8-bit Accumulator-based CPU with status flags, trap handling, and unified execution."""

    TIMER_INTERRUPT_CYCLE_COUNT = 50
    VALID_GP_REGISTERS = frozenset({"R1", "R2"})
    VALID_REGISTERS = frozenset({"R1", "R2", "ACC", "PC", "SP"})
    INTERRUPT_VECTOR_TABLE = {
        "timer": 0x00,  # Preemptive multitasking & scheduler
        "keyboard": 0x01,  # User input I/O
        "divide_by_zero": 0x02,  # Math error fault
        "invalid_opcode": 0x03,  # Corrupted or illegal instruction
        "page_fault": 0x04,  # Virtual memory protection / missing page
        "syscall": 0x05,  # User program requesting kernel services
    }

    def __init__(self, ram: RAM):
        self.ram = ram
        self.registers: dict[str, int] = {
            "R1": 0,
            "R2": 0,
            "ACC": 0,
            "PC": 0,
            "SP": len(self.ram.memory) - 1,
        }
        self.flags: dict[str, bool] = {
            "Z": False,  # Zero flag
            "C": False,  # Carry / Borrow flag
        }
        self.halted: bool = False
        self.cycle_count: int = 0
        self.interrupt_queue: list[int] = []
        self.interrupts_enabled: bool = True
        self.syscall_handler: Callable | None = None
        self.kernel_mode: bool = True
        self.fault_handler: Callable | None = None
        self.base_address: int = 0
        self.limit_address: int = len(self.ram.memory)

    def _validate_register(self, reg: str, allow_acc_pc: bool = False) -> None:
        allowed = self.VALID_REGISTERS if allow_acc_pc else self.VALID_GP_REGISTERS
        if reg not in allowed:
            raise InvalidRegisterError(f"Register '{reg}' is invalid. Allowed: {sorted(allowed)}")

    def _update_alu(self, raw_result: int, update_carry: bool = True) -> None:
        """Truncate raw result to 8 bits and update Zero and Carry flags."""
        if update_carry:
            self.flags["C"] = raw_result > 0xFF or raw_result < 0

        self.registers["ACC"] = raw_result & 0xFF
        self.flags["Z"] = self.registers["ACC"] == 0

    def load(self, address: int) -> None:
        """Load byte from RAM address into Accumulator and update Zero flag."""
        if not self._validate_memory_read(address):
            return

        val = self.ram.read(address) & 0xFF
        self.registers["ACC"] = val
        self.flags["Z"] = val == 0

    def load_imm(self, value: int) -> None:
        """Load immediate value into Accumulator."""
        self.registers["ACC"] = value & 0xFF
        self.flags["Z"] = value == 0

    def store(self, address: int) -> None:
        """Store Accumulator value into RAM address."""
        if not self._validate_memory_write(address):
            return
        self.ram.write(address, self.registers["ACC"] & 0xFF)

    def mov(self, dest: str, src: str) -> None:
        """Copy value between valid registers."""
        self._validate_register(dest, allow_acc_pc=True)
        self._validate_register(src, allow_acc_pc=True)
        self.registers[dest] = self.registers[src] & 0xFF

    def add(self, target: str) -> None:
        """Add target register to Accumulator."""
        self._validate_register(target)
        self._update_alu(self.registers["ACC"] + self.registers[target], update_carry=True)

    def sub(self, target: str) -> None:
        """Subtract target register from Accumulator."""
        self._validate_register(target)
        self._update_alu(self.registers["ACC"] - self.registers[target], update_carry=True)

    def mul(self, target: str) -> None:
        """Multiply Accumulator by target register."""
        self._validate_register(target)
        self._update_alu(self.registers["ACC"] * self.registers[target], update_carry=True)

    def div(self, target: str) -> None:
        """Divide Accumulator by target register. Triggers DivisionByZeroFault on zero."""
        self._validate_register(target)
        divisor = self.registers[target]
        if divisor == 0:
            raise DivisionByZeroFault("CPU Trap: Division by zero attempted.")

        self._update_alu(self.registers["ACC"] // divisor, update_carry=False)

    def and_(self, target: str) -> None:
        """Bitwise AND between target register and Accumulator."""
        self._validate_register(target)
        self._update_alu(self.registers["ACC"] & self.registers[target], update_carry=False)

    def or_(self, target: str) -> None:
        """Bitwise OR between target register and Accumulator."""
        self._validate_register(target)
        self._update_alu(self.registers["ACC"] | self.registers[target], update_carry=False)

    def xor(self, target: str) -> None:
        """Bitwise XOR between target register and Accumulator."""
        self._validate_register(target)
        self._update_alu(self.registers["ACC"] ^ self.registers[target], update_carry=False)

    def not_(self, target: str | None = None) -> None:
        """Bitwise NOT on target register (or ACC if unspecified), storing result in ACC."""
        if target is not None:
            self._validate_register(target)
            val = self.registers[target]
        else:
            val = self.registers["ACC"]

        self._update_alu((~val) & 0xFF, update_carry=False)

    def jump(self, address: int) -> None:
        """Unconditional jump to address."""
        self.registers["PC"] = address & 0xFFFF

    def jump_if_zero(self, address: int, target: str | None = None) -> None:
        """Jump if Zero flag (Z) is set, or if an explicitly provided register is zero."""
        if target is not None:
            self._validate_register(target, allow_acc_pc=True)
            condition = self.registers[target] == 0
        else:
            condition = self.flags["Z"]

        if condition:
            self.registers["PC"] = address & 0xFFFF

    def halt(self) -> None:
        """Halt the CPU execution loop without corrupting PC state."""
        self.halted = True

    def push(self, value: int) -> None:
        """Push value onto the stack."""
        if not self._validate_memory_write(self.registers["SP"]):
            return
        self.ram.write(self.registers["SP"], value & 0xFF)
        self.registers["SP"] -= 1

    def pop(self) -> int:
        """Pop value from the stack with bounds checking."""
        target_address = self.registers["SP"] + 1
        if not self._validate_memory_read(target_address):
            return 0

        self.registers["SP"] = target_address
        return self.ram.read(self.registers["SP"]) & 0xFF

    def interrupt(self, vector_address: int) -> None:
        """Save CPU state, flags, and jump to the interrupt service routine."""
        # Check for stack overflow/violation when in User Mode
        if not self.kernel_mode:
            stack_in_bounds = (
                self.base_address <= (self.registers["SP"] - 4)
                and self.registers["SP"] < self.limit_address
            )
            if not stack_in_bounds:
                self.kernel_mode = True  # Elevate so fault handling runs safely
                if self.fault_handler:
                    self.fault_handler("Segmentation Fault: Stack Overflow / Invalid SP")
                return

        # Elevate privilege and save hardware frame
        self.kernel_mode = True

        self.push(self.registers["PC"])
        self.push(self.registers["ACC"])
        self.push(self.registers["R1"])
        self.push(self.registers["R2"])
        flags_byte = (int(self.flags["Z"]) << 1) | int(self.flags["C"])
        self.push(flags_byte)

        # Dispatch handler
        if vector_address == self.INTERRUPT_VECTOR_TABLE["syscall"] and self.syscall_handler:
            self.syscall_handler()
            return

        handler_address = self.ram.read(vector_address)
        self.registers["PC"] = handler_address
        self.interrupts_enabled = False

    def iret(self) -> None:
        """Return from interrupt, restoring saved CPU state and flags."""
        flags_byte = self.pop()
        self.flags["C"] = bool(flags_byte & 0x01)
        self.flags["Z"] = bool(flags_byte & 0x02)

        self.registers["R2"] = self.pop()
        self.registers["R1"] = self.pop()
        self.registers["ACC"] = self.pop()
        self.registers["PC"] = self.pop()
        self.interrupts_enabled = True
        self.kernel_mode = False

    def load_program(self, code: list[int], entry_point: int = 6) -> None:
        """Load machine code into RAM and set the program counter."""
        for offset, byte in enumerate(code):
            self.ram.write(entry_point + offset, byte)
        self.registers["PC"] = entry_point

    def _fetch_byte(self) -> int:
        """Fetch byte at PC from RAM if within bounds; advance PC."""
        if not self._validate_pc():
            raise _FetchFault()

        byte = self.ram.read(self.registers["PC"])
        self.registers["PC"] += 1
        return byte

    def _validate_memory_write(self, address: int) -> bool:
        """Ensure User Mode programs cannot overwrite protected kernel memory."""
        # Fast path: kernel mode has full access, user mode is restricted to [0x40, 0xFA)
        if self.kernel_mode or (self.base_address <= address < self.limit_address):
            return True

        # Violation path: handle fault
        if self.fault_handler:
            self.fault_handler("Segmentation Fault: Illegal Memory Write")
        else:
            raise PrivilegeViolationFault(f"Access violation at address {hex(address)}")

        return False

    def _validate_memory_read(self, address: int) -> bool:
        """Ensure User Mode programs cannot read outside their memory bounds."""
        # Fast path: kernel mode has full access; user mode must stay within bounds
        if self.kernel_mode or (self.base_address <= address < self.limit_address):
            return True

        # Violation path: report fault
        if self.fault_handler:
            self.fault_handler("Segmentation Fault: Illegal Memory Read")
        else:
            raise PrivilegeViolationFault(f"Illegal memory read at address {hex(address)}")

        return False

    def _require_kernel_mode(self) -> bool:
        """Ensure CPU is in Kernel Mode; trigger fault and abort if in User Mode."""
        if not self.kernel_mode:
            if self.fault_handler:
                self.fault_handler("Privilege Violation")
            else:
                raise PrivilegeViolationFault("Operation not permitted in User Mode.")
            return False
        return True

    def _validate_pc(self) -> bool:
        """Ensure User Mode execution remains strictly within memory bounds."""
        if self.kernel_mode or (self.base_address <= self.registers["PC"] < self.limit_address):
            return True

        if self.fault_handler:
            self.fault_handler("Segmentation Fault: Illegal Instruction Fetch")
        else:
            raise PrivilegeViolationFault(f"Fetch out of bounds at {hex(self.registers['PC'])}")

        return False

    def step(self) -> None:
        """Fetch, decode, and execute a single instruction."""
        if self.halted:
            return

        self.cycle_count += 1
        if self.cycle_count >= self.TIMER_INTERRUPT_CYCLE_COUNT:
            self.cycle_count = 0
            self.interrupt_queue.append(self.INTERRUPT_VECTOR_TABLE["timer"])

        if self.interrupts_enabled and self.interrupt_queue:
            vector_address = self.interrupt_queue.pop(0)
            self.interrupt(vector_address)

        if self.halted:
            return

        try:
            opcode = self._fetch_byte()

            match opcode:
                # System
                case 0x00:
                    if not self._require_kernel_mode():
                        return
                    self.halt()
                case 0x05:  # SYSCALL: Software interrupt to kernel vector 0x05
                    self.interrupt(self.INTERRUPT_VECTOR_TABLE["syscall"])
                case 0x0F:
                    if not self._require_kernel_mode():
                        return
                    self.iret()

                # Memory I/O
                case 0x01:
                    self.load(self._fetch_byte())
                case 0x02:
                    self.store(self._fetch_byte())
                case 0x03:
                    self.load_imm(self._fetch_byte())

                # Arithmetic (ALU)
                case 0x10:
                    self.add("R1")
                case 0x11:
                    self.add("R2")
                case 0x12:
                    self.sub("R1")
                case 0x13:
                    self.sub("R2")
                case 0x14:
                    self.mul("R1")
                case 0x15:
                    self.mul("R2")
                case 0x16:
                    self.div("R1")
                case 0x17:
                    self.div("R2")

                # Logic (ALU)
                case 0x18:
                    self.and_("R1")
                case 0x19:
                    self.and_("R2")
                case 0x1A:
                    self.or_("R1")
                case 0x1B:
                    self.or_("R2")
                case 0x1C:
                    self.xor("R1")
                case 0x1D:
                    self.xor("R2")
                case 0x1E:
                    self.not_()

                # Data Transfer (Register-to-Register)
                case 0x20:
                    self.mov("R1", "ACC")
                case 0x21:
                    self.mov("R2", "ACC")
                case 0x22:
                    self.mov("ACC", "R1")
                case 0x23:
                    self.mov("ACC", "R2")
                case 0x24:
                    self.mov("R1", "R2")
                case 0x25:
                    self.mov("R2", "R1")
                case 0x26:
                    self.mov("SP", "ACC")
                case 0x27:
                    self.mov("ACC", "SP")

                # Control Flow
                case 0x30:
                    self.jump(self._fetch_byte())
                case 0x31:
                    self.jump_if_zero(self._fetch_byte())

                case _:
                    if self.fault_handler:
                        self.fault_handler(f"Invalid Opcode: {hex(opcode)}")
                    else:
                        raise InvalidInstructionFault(f"Unknown opcode: {hex(opcode)}")

        except _FetchFault:
            return
        except DivisionByZeroFault as err:
            if self.fault_handler:
                self.fault_handler(str(err))
            else:
                raise

    def run(self, max_steps: int | None = None) -> None:
        """Run instructions continuously until HALT or max_steps reached."""
        steps = 0
        while not self.halted:
            if max_steps is not None and steps >= max_steps:
                break
            self.step()
            steps += 1
