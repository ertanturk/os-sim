; ==============================================================================
; Counter Loop with Preemptive / Voluntary Yield
; Increments R1 on each iteration and voluntarily yields CPU via SYS_YIELD
; ==============================================================================

loop:
    LOAD_IMM 1              ; ACC = 1
    ADD R1                  ; ACC = R1 + 1
    MOV R1, ACC             ; R1 = ACC (increment counter)

    LOAD_IMM SYS_YIELD      ; Syscall ID 1: SYS_YIELD
    SYSCALL                 ; Voluntarily surrender CPU timeslice

    JMP loop                ; Repeat loop indefinitely
