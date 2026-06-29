VITIS_HLS ?= vitis_hls

STREAMER_32_DIR := dwell_fcw_streamer_32_bit
STREAMER_64_DIR := dwell_streamer_64_bit

.PHONY: all check-tool csim csim32 csim64 export export32 export64 clean clean32 clean64 help

all: export

check-tool:
	@command -v $(VITIS_HLS) >/dev/null 2>&1 || { \
		echo "ERROR: $(VITIS_HLS) not found. Source the Xilinx/Vitis settings script or run make VITIS_HLS=/path/to/vitis_hls ..."; \
		exit 127; \
	}

csim: csim32 csim64

csim32: check-tool
	cd $(STREAMER_32_DIR) && HLS_STEP=csim $(VITIS_HLS) -f run_hls.tcl

csim64: check-tool
	cd $(STREAMER_64_DIR) && HLS_STEP=csim $(VITIS_HLS) -f run_hls.tcl

export: export32 export64

export32: check-tool
	cd $(STREAMER_32_DIR) && HLS_STEP=export $(VITIS_HLS) -f run_hls.tcl

export64: check-tool
	cd $(STREAMER_64_DIR) && HLS_STEP=export $(VITIS_HLS) -f run_hls.tcl

clean: clean32 clean64

clean32:
	$(RM) -r $(STREAMER_32_DIR)/dwell_fcw_streamer_32_prj $(STREAMER_32_DIR)/vitis_hls.log

clean64:
	$(RM) -r $(STREAMER_64_DIR)/dwell_fcw_streamer_64_prj $(STREAMER_64_DIR)/vitis_hls.log

help:
	@echo "Targets:"
	@echo "  make csim      Run C simulation for 32-bit and 64-bit streamers"
	@echo "  make csim32    Run C simulation for the 32-bit streamer"
	@echo "  make csim64    Run C simulation for the 64-bit streamer"
	@echo "  make export    Run csim, synthesis, and IP export for both streamers"
	@echo "  make export32  Run csim, synthesis, and IP export for the 32-bit streamer"
	@echo "  make export64  Run csim, synthesis, and IP export for the 64-bit streamer"
	@echo "  make clean     Remove generated HLS projects and logs"
