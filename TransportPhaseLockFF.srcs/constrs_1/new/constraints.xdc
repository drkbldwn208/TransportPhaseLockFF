set_clock_groups -asynchronous -group [get_clocks clk_pl_0] -group [get_clocks RFADC1_CLK]

set_property PACKAGE_PIN G15 [get_ports dac_cs_0] 
set_property IOSTANDARD LVCMOS18 [get_ports dac_cs_0]

set_property PACKAGE_PIN G16 [get_ports dac_mosi_0]
set_property IOSTANDARD LVCMOS18 [get_ports dac_mosi_0]

set_property PACKAGE_PIN H15 [get_ports dac_sclk_0]
set_property IOSTANDARD LVCMOS18 [get_ports dac_sclk_0]