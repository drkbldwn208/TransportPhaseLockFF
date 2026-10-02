VITIS_HLS ?= vitis_hls

.PHONY: all check-tool csim export clean help

all: export

check-tool:
	@command -v $(VITIS_HLS) >/dev/null 2>&1 || { \
		echo "ERROR: $(VITIS_HLS) not found. Source the Xilinx/Vitis settings script or run make VITIS_HLS=/path/to/vitis_hls ..."; \
		exit 127; \
	}

csim: check-tool
	HLS_STEP=csim $(VITIS_HLS) -f run_hls.tcl

export: check-tool
	HLS_STEP=export $(VITIS_HLS) -f run_hls.tcl

clean:
	$(RM) -r rfdc_iq_derotator_4lane_prj vitis_hls.log

help:
	@echo "Targets:"
	@echo "  make csim    Run C simulation"
	@echo "  make export  Run csim, synthesis, and IP export (default)"
	@echo "  make clean   Remove the generated HLS project and log"
