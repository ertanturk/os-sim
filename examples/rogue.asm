; ==============================================================================
; Rogue Memory Access Program
; Attempts illegal write to Kernel RAM space (address 0x10) to demonstrate
; Hardware Memory Protection Unit (MPU) violation and kernel fault handling.
; ==============================================================================

    LOAD_IMM 0xEE           ; ACC = 0xEE
    STORE 0x10              ; Attempt illegal write to IVT vector table!
                            ; Hardware MPU will trap this with Segmentation Fault!

    LOAD_IMM SYS_EXIT
    SYSCALL
