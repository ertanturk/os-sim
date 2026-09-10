; ==============================================================================
; Hello World Demonstration Program
; Prints "Hello, OS Simulator!" using the SYS_PRINT_STR system call
; ==============================================================================

    LOAD_IMM msg            ; ACC = address of string
    MOV R1, ACC             ; R1 = arg1 (string address in RAM)
    LOAD_IMM 21             ; ACC = string length (21 chars)
    MOV R2, ACC             ; R2 = arg2 (string length)
    LOAD_IMM SYS_PRINT_STR  ; Syscall ID 7: SYS_PRINT_STR
    SYSCALL                 ; Invoke OS kernel syscall trap

    LOAD_IMM 0              ; Exit code 0
    MOV R1, ACC             ; R1 = exit code
    LOAD_IMM SYS_EXIT       ; Syscall ID 2: SYS_EXIT
    SYSCALL                 ; Terminate task

msg:
    .ascii "Hello, OS Simulator!\n"
