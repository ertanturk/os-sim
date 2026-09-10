; ==============================================================================
; Fibonacci Sequence Generator
; Computes Fibonacci sequence: 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89...
; Uses RAM variables (STORE / LOAD) to preserve values across system calls.
; ==============================================================================

    ; Initialize state: prev = 1, curr = 1
    LOAD_IMM 1
    STORE prev
    LOAD_IMM 1
    STORE curr

fib_loop:
    ; Print current Fibonacci number
    LOAD curr
    MOV R1, ACC             ; R1 = arg1 for SYS_PRINT_NUM
    LOAD_IMM SYS_PRINT_NUM
    SYSCALL

    ; Calculate next = prev + curr
    LOAD prev
    MOV R1, ACC             ; R1 = prev
    LOAD curr               ; ACC = curr
    ADD R1                  ; ACC = curr + prev
    STORE next              ; next = curr + prev

    ; Advance sequence: prev = curr, curr = next
    LOAD curr
    STORE prev
    LOAD next
    STORE curr

    ; Voluntarily surrender CPU timeslice to OS scheduler
    LOAD_IMM SYS_YIELD
    SYSCALL

    JMP fib_loop

prev:
    DB 0
curr:
    DB 0
next:
    DB 0
