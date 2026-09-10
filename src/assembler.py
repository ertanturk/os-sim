"""Assembler and Disassembler for the 8-bit CPU architecture.

Supports:
- Two-pass assembly with forward and backward label resolution
- Built-in OS system call constants (SYS_PRINT_NUM, SYS_PRINT_STR, SYS_YIELD, etc.)
- Directives: .org, DB / .byte, .ascii, .asciiz / .string, .equ / EQU
- Register moves, ALU operations, jump conditions, and memory I/O
- Interactive assembly parsing and human-readable disassembly
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class AssemblyError(Exception):
    """Raised when an assembly source line fails lexical, syntax, or semantic validation."""

    def __init__(self, message: str, line_num: int | None = None, line_text: str | None = None):
        self.message = message
        self.line_num = line_num
        self.line_text = line_text
        context = f" at line {line_num} ('{line_text}')" if line_num is not None else ""
        super().__init__(f"Assembly Error{context}: {message}")


@dataclass
class AssemblyListingEntry:
    """Represents a single assembled source line and its emitted machine code."""

    line_num: int
    address: int
    bytes_emitted: list[int]
    source_text: str


@dataclass
class AssemblyResult:
    """The result of assembling an assembly source program."""

    bytecode: list[int]
    origin: int
    symbol_table: dict[str, int]
    listing: list[AssemblyListingEntry]
    source_map: dict[int, int]  # address -> line_num


@dataclass
class DisassembledInstruction:
    """Represents a single disassembled machine code instruction."""

    address: int
    raw_bytes: list[int]
    mnemonic: str
    operands: str
    description: str

    def __str__(self) -> str:
        hex_bytes = " ".join(f"{b:02X}" for b in self.raw_bytes)
        asm_str = f"{self.mnemonic:<8} {self.operands}".strip()
        return f"0x{self.address:02X}:  {hex_bytes:<8}  {asm_str:<18} ; {self.description}"


# Standard OS Kernel System Call IDs and IVT Constants
BUILTIN_SYMBOLS: dict[str, int] = {
    # Syscalls
    "SYS_YIELD": 0x01,
    "SYS_EXIT": 0x02,
    "SYS_SLEEP": 0x03,
    "SYS_GETPID": 0x04,
    "SYS_GET_PID": 0x04,
    "SYS_PRINT_NUM": 0x05,
    "SYS_PRINT_INT": 0x05,
    "SYS_PRINT_CHAR": 0x06,
    "SYS_PUTC": 0x06,
    "SYS_PRINT_STR": 0x07,
    "SYS_WRITE": 0x07,
    "SYS_SPAWN": 0x08,
    "SYS_CREATE_TASK": 0x08,
    "SYS_WAIT": 0x09,
    "SYS_WAITPID": 0x09,
    "SYS_KILL": 0x0A,
    "SYS_GET_TICKS": 0x0B,
    "SYS_ALLOC": 0x0C,
    # IVT Vectors
    "IVT_TIMER": 0x00,
    "IVT_KEYBOARD": 0x01,
    "IVT_DIV_ZERO": 0x02,
    "IVT_INVALID_OP": 0x03,
    "IVT_PAGE_FAULT": 0x04,
    "IVT_SYSCALL": 0x05,
    # Kernel Mailbox Registers
    "MAILBOX_OLD_SP": 0xFA,
    "MAILBOX_NEW_SP": 0xFB,
}

# Single-byte opcodes with no operands
NO_OPERAND_OPCODES: dict[str, tuple[int, str]] = {
    "HALT": (0x00, "Halt CPU execution (Kernel mode only)"),
    "HLT": (0x00, "Halt CPU execution (Kernel mode only)"),
    "SYSCALL": (0x05, "Invoke OS kernel system call trap"),
    "IRET": (0x0F, "Return from interrupt and restore CPU frame"),
    "NOT": (0x1E, "Bitwise NOT on ACC"),
}

# ALU operations targeting registers
ALU_REGISTER_OPCODES: dict[tuple[str, str], tuple[int, str]] = {
    ("ADD", "R1"): (0x10, "ACC = (ACC + R1) & 0xFF"),
    ("ADD", "R2"): (0x11, "ACC = (ACC + R2) & 0xFF"),
    ("SUB", "R1"): (0x12, "ACC = (ACC - R1) & 0xFF"),
    ("SUB", "R2"): (0x13, "ACC = (ACC - R2) & 0xFF"),
    ("MUL", "R1"): (0x14, "ACC = (ACC * R1) & 0xFF"),
    ("MUL", "R2"): (0x15, "ACC = (ACC * R2) & 0xFF"),
    ("DIV", "R1"): (0x16, "ACC = (ACC // R1) & 0xFF"),
    ("DIV", "R2"): (0x17, "ACC = (ACC // R2) & 0xFF"),
    ("AND", "R1"): (0x18, "ACC = ACC & R1"),
    ("AND", "R2"): (0x19, "ACC = ACC & R2"),
    ("OR", "R1"): (0x1A, "ACC = ACC | R1"),
    ("OR", "R2"): (0x1B, "ACC = ACC | R2"),
    ("XOR", "R1"): (0x1C, "ACC = ACC ^ R1"),
    ("XOR", "R2"): (0x1D, "ACC = ACC ^ R2"),
}

# Register-to-Register MOV instructions
MOV_REGISTER_OPCODES: dict[tuple[str, str], tuple[int, str]] = {
    ("R1", "ACC"): (0x20, "Copy ACC into R1"),
    ("R2", "ACC"): (0x21, "Copy ACC into R2"),
    ("ACC", "R1"): (0x22, "Copy R1 into ACC"),
    ("ACC", "R2"): (0x23, "Copy R2 into ACC"),
    ("R1", "R2"): (0x24, "Copy R2 into R1"),
    ("R2", "R1"): (0x25, "Copy R1 into R2"),
    ("SP", "ACC"): (0x26, "Copy ACC into Stack Pointer (SP)"),
    ("ACC", "SP"): (0x27, "Copy Stack Pointer (SP) into ACC"),
}

# Branching and jump opcodes
JUMP_OPCODES: dict[str, tuple[int, str]] = {
    "JUMP": (0x30, "Unconditional jump to target address"),
    "JMP": (0x30, "Unconditional jump to target address"),
    "JUMP_IF_ZERO": (0x31, "Jump to target address if Zero flag (Z) is set"),
    "JZ": (0x31, "Jump to target address if Zero flag (Z) is set"),
}

# Memory and Immediate opcodes
MEMORY_OPCODES: dict[str, tuple[int, str]] = {
    "LOAD": (0x01, "Load byte from RAM address into ACC"),
    "LD": (0x01, "Load byte from RAM address into ACC"),
    "STORE": (0x02, "Store ACC into RAM address"),
    "ST": (0x02, "Store ACC into RAM address"),
    "LOAD_IMM": (0x03, "Load 8-bit immediate value into ACC"),
    "LDI": (0x03, "Load 8-bit immediate value into ACC"),
}


def _unescape_string(s: str) -> bytes:
    """Convert an escaped string literal (e.g. 'Hello\\n') to bytes."""
    escapes = {
        "\\n": b"\n",
        "\\t": b"\t",
        "\\r": b"\r",
        "\\0": b"\x00",
        "\\\\": b"\\",
        '\\"': b'"',
        "\\'": b"'",
    }
    result = bytearray()
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            seq = s[i : i + 2]
            if seq in escapes:
                result.extend(escapes[seq])
                i += 2
                continue
        result.append(ord(s[i]) & 0xFF)
        i += 1
    return bytes(result)


def _parse_int_expr(expr: str, symbols: dict[str, int], line_num: int, line_text: str) -> int:
    """Evaluate an integer, symbol name, or basic addition/subtraction expression."""
    token = expr.strip()
    if not token:
        raise AssemblyError("Missing operand expression", line_num, line_text)

    # Handle addition/subtraction expressions, e.g. "label + 2" or "0x40 - 1"
    match = re.match(r"^([a-zA-Z0-9_$]+)\s*([+-])\s*([a-zA-Z0-9_$]+)$", token)
    if match:
        left_str, op, right_str = match.groups()
        left_val = _parse_int_expr(left_str, symbols, line_num, line_text)
        right_val = _parse_int_expr(right_str, symbols, line_num, line_text)
        return (left_val + right_val) if op == "+" else (left_val - right_val)

    # Check symbols first
    if token in symbols:
        return symbols[token]

    # Hex: 0x.. or $.. or ..h
    if token.startswith("0x") or token.startswith("0X"):
        try:
            return int(token, 16)
        except ValueError as err:
            raise AssemblyError(f"Invalid hex literal '{token}'", line_num, line_text) from err
    if token.startswith("$"):
        try:
            return int(token[1:], 16)
        except ValueError as err:
            raise AssemblyError(f"Invalid hex literal '{token}'", line_num, line_text) from err
    if len(token) > 1 and token.endswith(("h", "H")) and re.match(r"^[0-9a-fA-F]+[hH]$", token):
        try:
            return int(token[:-1], 16)
        except ValueError as err:
            raise AssemblyError(f"Invalid hex literal '{token}'", line_num, line_text) from err

    # Binary: 0b.. or %..
    if token.startswith(("0b", "0B")):
        try:
            return int(token, 2)
        except ValueError as err:
            raise AssemblyError(f"Invalid binary literal '{token}'", line_num, line_text) from err
    if token.startswith("%"):
        try:
            return int(token[1:], 2)
        except ValueError as err:
            raise AssemblyError(f"Invalid binary literal '{token}'", line_num, line_text) from err

    # Character literal: 'A'
    if (token.startswith("'") and token.endswith("'") and len(token) >= 3) or (
        token.startswith('"') and token.endswith('"') and len(token) >= 3
    ):
        inner = token[1:-1]
        unescaped = _unescape_string(inner)
        if len(unescaped) == 1:
            return unescaped[0]

    # Decimal
    try:
        return int(token)
    except ValueError as err:
        raise AssemblyError(
            f"Undefined symbol or invalid integer literal '{token}'", line_num, line_text
        ) from err


class Assembler:
    """Two-pass assembler converting 8-bit assembly source to executable machine code."""

    def __init__(self, origin: int = 0x40, extra_symbols: dict[str, int] | None = None):
        self.default_origin = origin
        self.symbols: dict[str, int] = dict(BUILTIN_SYMBOLS)
        if extra_symbols:
            self.symbols.update(extra_symbols)

    def _strip_comments(self, line: str) -> str:
        """Remove comments (; // #) outside of quoted strings."""
        in_quote = False
        quote_char = ""
        result: list[str] = []
        i = 0
        while i < len(line):
            c = line[i]
            if c in ('"', "'"):
                if not in_quote:
                    in_quote = True
                    quote_char = c
                elif quote_char == c:
                    in_quote = False
                result.append(c)
                i += 1
                continue

            if not in_quote:
                # Comment check
                if c in (";", "#"):
                    break
                if c == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    break

            result.append(c)
            i += 1
        return "".join(result).strip()

    def assemble(self, source: str, origin: int | None = None) -> AssemblyResult:
        """Assemble multiline source code string into bytecode.

        Returns an AssemblyResult containing machine code bytes, symbols, and line listings.
        """
        current_origin = origin if origin is not None else self.default_origin
        lines = source.splitlines()

        # PASS 1: Symbol discovery, label address assignment, size calculation
        pass1_symbols = dict(self.symbols)
        current_addr = current_origin
        cleaned_lines: list[tuple[int, str, str | None, str]] = []

        for line_num, raw_line in enumerate(lines, start=1):
            stripped = self._strip_comments(raw_line)
            if not stripped:
                continue

            label: str | None = None
            statement: str = stripped

            colon_pos = -1
            in_q = False
            q_char = ""
            for idx, ch in enumerate(stripped):
                if ch in ('"', "'"):
                    if not in_q:
                        in_q = True
                        q_char = ch
                    elif q_char == ch:
                        in_q = False
                elif ch == ":" and not in_q:
                    colon_pos = idx
                    break

            if colon_pos != -1:
                potential_label = stripped[:colon_pos].strip()
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_$]*$", potential_label):
                    raise AssemblyError(f"Invalid label identifier '{potential_label}'", line_num, raw_line)
                label = potential_label
                statement = stripped[colon_pos + 1 :].strip()

            # Handle EQU / .EQU directives on Pass 1
            equ_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_$]*)\s+(?:EQU|\.EQU)\s+(.+)$", statement, re.IGNORECASE)
            if equ_match:
                eq_label, eq_expr = equ_match.groups()
                val = _parse_int_expr(eq_expr, pass1_symbols, line_num, raw_line)
                pass1_symbols[eq_label] = val
                cleaned_lines.append((line_num, raw_line, None, ""))
                continue

            dot_equ_match = re.match(r"^\.EQU\s+([a-zA-Z_][a-zA-Z0-9_$]*)\s*,\s*(.+)$", statement, re.IGNORECASE)
            if dot_equ_match:
                eq_label, eq_expr = dot_equ_match.groups()
                val = _parse_int_expr(eq_expr, pass1_symbols, line_num, raw_line)
                pass1_symbols[eq_label] = val
                cleaned_lines.append((line_num, raw_line, None, ""))
                continue

            if label:
                if label in pass1_symbols:
                    raise AssemblyError(f"Duplicate label definition '{label}'", line_num, raw_line)
                pass1_symbols[label] = current_addr

            if not statement:
                cleaned_lines.append((line_num, raw_line, label, ""))
                continue

            org_match = re.match(r"^\.ORG\s+(.+)$", statement, re.IGNORECASE)
            if org_match:
                new_addr = _parse_int_expr(org_match.group(1), pass1_symbols, line_num, raw_line)
                current_addr = new_addr
                cleaned_lines.append((line_num, raw_line, label, statement))
                continue

            stmt_size = self._calculate_statement_size(statement, line_num, raw_line, pass1_symbols)
            cleaned_lines.append((line_num, raw_line, label, statement))
            current_addr += stmt_size

        # PASS 2: Code emission, operand evaluation, and listing generation
        emitted_bytes: list[int] = []
        listing: list[AssemblyListingEntry] = []
        source_map: dict[int, int] = {}
        code_origin = current_origin
        current_addr = current_origin

        for line_num, raw_line, _, statement in cleaned_lines:
            if not statement:
                continue

            org_match = re.match(r"^\.ORG\s+(.+)$", statement, re.IGNORECASE)
            if org_match:
                current_addr = _parse_int_expr(org_match.group(1), pass1_symbols, line_num, raw_line)
                if not emitted_bytes:
                    code_origin = current_addr
                continue

            line_bytes = self._emit_statement_bytes(statement, current_addr, pass1_symbols, line_num, raw_line)
            source_map[current_addr] = line_num
            listing.append(
                AssemblyListingEntry(
                    line_num=line_num,
                    address=current_addr,
                    bytes_emitted=line_bytes,
                    source_text=raw_line.strip(),
                )
            )
            emitted_bytes.extend(line_bytes)
            current_addr += len(line_bytes)

        return AssemblyResult(
            bytecode=emitted_bytes,
            origin=code_origin,
            symbol_table=pass1_symbols,
            listing=listing,
            source_map=source_map,
        )

    def _calculate_statement_size(
        self,
        statement: str,
        line_num: int,
        raw_line: str,
        symbols: dict[str, int],
    ) -> int:
        """Compute the byte length of a single assembly statement in Pass 1."""
        tokens = statement.split(None, 1)
        mnemonic = tokens[0].upper()
        args = tokens[1].strip() if len(tokens) > 1 else ""

        if mnemonic in ("DB", ".BYTE"):
            parts = [p.strip() for p in args.split(",") if p.strip()]
            return len(parts)
        if mnemonic == ".ASCII":
            s_val = self._extract_string_literal(args, line_num, raw_line)
            return len(_unescape_string(s_val))
        if mnemonic in (".ASCIIZ", ".STRING"):
            s_val = self._extract_string_literal(args, line_num, raw_line)
            return len(_unescape_string(s_val)) + 1

        if mnemonic in NO_OPERAND_OPCODES:
            return 1

        if mnemonic in ("ADD", "SUB", "MUL", "DIV", "AND", "OR", "XOR"):
            return 1

        if mnemonic == "MOV":
            parts = [p.strip() for p in args.split(",", 1)]
            if len(parts) != 2:
                raise AssemblyError("MOV instruction requires 2 operands (dest, src)", line_num, raw_line)
            dest, src = parts[0].upper(), parts[1].upper()
            if dest.startswith("[") and dest.endswith("]"):
                return 2
            if src.startswith("[") and src.endswith("]"):
                return 2
            if dest == "ACC" and (src.startswith("#") or (dest, src) not in MOV_REGISTER_OPCODES):
                return 2
            return 1

        if mnemonic in MEMORY_OPCODES or mnemonic in JUMP_OPCODES:
            return 2

        if mnemonic == "INT":
            return 1

        raise AssemblyError(f"Unknown mnemonic or directive '{mnemonic}'", line_num, raw_line)

    def _extract_string_literal(self, text: str, line_num: int, raw_line: str) -> str:
        """Extract contents of a double or single quoted string literal."""
        clean = text.strip()
        if (clean.startswith('"') and clean.endswith('"')) or (clean.startswith("'") and clean.endswith("'")):
            return clean[1:-1]
        raise AssemblyError(
            f"Expected quoted string literal, got '{text}'",
            line_num,
            raw_line,
        )

    def _emit_statement_bytes(
        self,
        statement: str,
        current_addr: int,
        symbols: dict[str, int],
        line_num: int,
        raw_line: str,
    ) -> list[int]:
        """Convert a statement into machine code bytes in Pass 2."""
        tokens = statement.split(None, 1)
        mnemonic = tokens[0].upper()
        args = tokens[1].strip() if len(tokens) > 1 else ""

        if mnemonic in ("DB", ".BYTE"):
            items = [p.strip() for p in args.split(",") if p.strip()]
            res = []
            for item in items:
                val = _parse_int_expr(item, symbols, line_num, raw_line)
                res.append(val & 0xFF)
            return res

        if mnemonic == ".ASCII":
            s_val = self._extract_string_literal(args, line_num, raw_line)
            return list(_unescape_string(s_val))

        if mnemonic in (".ASCIIZ", ".STRING"):
            s_val = self._extract_string_literal(args, line_num, raw_line)
            b = list(_unescape_string(s_val))
            b.append(0x00)
            return b

        if mnemonic in NO_OPERAND_OPCODES:
            opcode, _ = NO_OPERAND_OPCODES[mnemonic]
            return [opcode]

        if mnemonic in ("ADD", "SUB", "MUL", "DIV", "AND", "OR", "XOR"):
            target_reg = args.upper().strip()
            key = (mnemonic, target_reg)
            if key not in ALU_REGISTER_OPCODES:
                raise AssemblyError(
                    f"{mnemonic} expects GP register R1 or R2, got '{args}'",
                    line_num,
                    raw_line,
                )
            opcode, _ = ALU_REGISTER_OPCODES[key]
            return [opcode]

        if mnemonic == "MOV":
            parts = [p.strip() for p in args.split(",", 1)]
            if len(parts) != 2:
                raise AssemblyError("MOV requires two arguments separated by comma: dest, src", line_num, raw_line)
            raw_dest, raw_src = parts[0], parts[1]
            u_dest, u_src = raw_dest.upper(), raw_src.upper()

            if u_dest.startswith("[") and u_dest.endswith("]"):
                if u_src != "ACC":
                    raise AssemblyError("Only ACC can be stored via MOV [addr], ACC", line_num, raw_line)
                addr_expr = raw_dest[1:-1].strip()
                addr = _parse_int_expr(addr_expr, symbols, line_num, raw_line)
                return [0x02, addr & 0xFF]

            if u_src.startswith("[") and u_src.endswith("]"):
                if u_dest != "ACC":
                    raise AssemblyError("Only ACC can be loaded via MOV ACC, [addr]", line_num, raw_line)
                addr_expr = raw_src[1:-1].strip()
                addr = _parse_int_expr(addr_expr, symbols, line_num, raw_line)
                return [0x01, addr & 0xFF]

            if (u_dest, u_src) in MOV_REGISTER_OPCODES:
                opcode, _ = MOV_REGISTER_OPCODES[(u_dest, u_src)]
                return [opcode]

            if u_dest == "ACC":
                imm_expr = raw_src[1:] if raw_src.startswith("#") else raw_src
                val = _parse_int_expr(imm_expr, symbols, line_num, raw_line)
                return [0x03, val & 0xFF]

            raise AssemblyError(f"Illegal MOV register pair or format: MOV {raw_dest}, {raw_src}", line_num, raw_line)

        if mnemonic in JUMP_OPCODES:
            if not args:
                raise AssemblyError(f"{mnemonic} requires a target address or label", line_num, raw_line)
            target = _parse_int_expr(args, symbols, line_num, raw_line)
            opcode, _ = JUMP_OPCODES[mnemonic]
            return [opcode, target & 0xFF]

        if mnemonic in MEMORY_OPCODES:
            if not args:
                raise AssemblyError(f"{mnemonic} requires an address or immediate argument", line_num, raw_line)
            val = _parse_int_expr(args, symbols, line_num, raw_line)
            opcode, _ = MEMORY_OPCODES[mnemonic]
            return [opcode, val & 0xFF]

        if mnemonic == "INT":
            val = _parse_int_expr(args, symbols, line_num, raw_line)
            if val == 5:
                return [0x05]
            raise AssemblyError(f"Only INT 5 (Syscall) is supported, got INT {val}", line_num, raw_line)

        raise AssemblyError(f"Unrecognized instruction '{mnemonic}'", line_num, raw_line)


def assemble(
    source: str,
    origin: int = 0x40,
    extra_symbols: dict[str, int] | None = None,
) -> AssemblyResult:
    """Convenience function to assemble source text into bytecode."""
    assembler = Assembler(origin=origin, extra_symbols=extra_symbols)
    return assembler.assemble(source, origin=origin)


def assemble_file(
    file_path: str | Path,
    origin: int = 0x40,
    extra_symbols: dict[str, int] | None = None,
) -> AssemblyResult:
    """Read assembly file from disk and compile into bytecode."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Assembly source file not found: {path}")
    source = path.read_text(encoding="utf-8")
    return assemble(source, origin=origin, extra_symbols=extra_symbols)


def disassemble(
    bytecode: list[int],
    origin: int = 0x40,
    symbol_table: dict[str, int] | None = None,
) -> list[DisassembledInstruction]:
    """Disassemble raw byte list into structured assembly instructions."""
    inv_symbols: dict[int, str] = {}
    if symbol_table:
        for name, addr in symbol_table.items():
            if name not in inv_symbols or len(name) < len(inv_symbols[addr]):
                inv_symbols[addr] = name

    one_byte_ops: dict[int, tuple[str, str, str]] = {}
    for mnem, (op, desc) in NO_OPERAND_OPCODES.items():
        one_byte_ops[op] = (mnem, "", desc)
    for (mnem, reg), (op, desc) in ALU_REGISTER_OPCODES.items():
        one_byte_ops[op] = (mnem, reg, desc)
    for (dest, src), (op, desc) in MOV_REGISTER_OPCODES.items():
        one_byte_ops[op] = ("MOV", f"{dest}, {src}", desc)

    two_byte_ops: dict[int, tuple[str, str]] = {}
    two_byte_ops[0x01] = ("LOAD", "Load byte at address into ACC")
    two_byte_ops[0x02] = ("STORE", "Store ACC byte into address")
    two_byte_ops[0x03] = ("LOAD_IMM", "Load immediate byte into ACC")
    two_byte_ops[0x30] = ("JMP", "Unconditional jump to address")
    two_byte_ops[0x31] = ("JZ", "Jump to address if Zero flag (Z) is set")

    instructions: list[DisassembledInstruction] = []
    pc = 0

    while pc < len(bytecode):
        curr_addr = origin + pc
        opcode = bytecode[pc]

        if opcode in one_byte_ops:
            mnem, op_str, desc = one_byte_ops[opcode]
            instructions.append(
                DisassembledInstruction(
                    address=curr_addr,
                    raw_bytes=[opcode],
                    mnemonic=mnem,
                    operands=op_str,
                    description=desc,
                )
            )
            pc += 1
        elif opcode in two_byte_ops:
            mnem, desc_tmpl = two_byte_ops[opcode]
            if pc + 1 < len(bytecode):
                arg = bytecode[pc + 1]
                sym_label = inv_symbols.get(arg)
                op_str = sym_label if sym_label else f"0x{arg:02X}"
                instructions.append(
                    DisassembledInstruction(
                        address=curr_addr,
                        raw_bytes=[opcode, arg],
                        mnemonic=mnem,
                        operands=op_str,
                        description=f"{desc_tmpl} ({op_str})",
                    )
                )
                pc += 2
            else:
                instructions.append(
                    DisassembledInstruction(
                        address=curr_addr,
                        raw_bytes=[opcode],
                        mnemonic=f"DB 0x{opcode:02X}",
                        operands="",
                        description="Truncated opcode byte",
                    )
                )
                pc += 1
        else:
            instructions.append(
                DisassembledInstruction(
                    address=curr_addr,
                    raw_bytes=[opcode],
                    mnemonic="DB",
                    operands=f"0x{opcode:02X}",
                    description="Raw data byte",
                )
            )
            pc += 1

    return instructions


def format_disassembly(
    bytecode: list[int],
    origin: int = 0x40,
    symbol_table: dict[str, int] | None = None,
) -> str:
    """Format disassembly output into a readable multiline assembly listing string."""
    lines = [str(ins) for ins in disassemble(bytecode, origin=origin, symbol_table=symbol_table)]
    return "\n".join(lines)
