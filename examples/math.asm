; ==============================================================================
; Arithmetic ALU Program
; Calculates: (15 + 25) * 2 = 80, prints result, and exits cleanly
; ==============================================================================

    LOAD_IMM 15             ; ACC = 15
    MOV R1, ACC             ; R1 = 15
    LOAD_IMM 25             ; ACC = 25
    ADD R1                  ; ACC = 25 + 15 = 40
    MOV R1, ACC             ; R1 = 40

    LOAD_IMM 2              ; ACC = 2
    MUL R1                  ; ACC = 2 * 40 = 80
    MOV R1, ACC             ; R1 = 80 (arg1 for SYS_PRINT_NUM)

    LOAD_IMM SYS_PRINT_NUM  ; Syscall ID 5: SYS_PRINT_NUM
    SYSCALL                 ; Print 80 to kernel console

    LOAD_IMM 0              ; Exit code 0
    MOV R1, ACC             ; R1 = 0
    LOAD_IMM SYS_EXIT       ; Syscall ID 2: SYS_EXIT
    SYSCALL                 ; Terminate task
