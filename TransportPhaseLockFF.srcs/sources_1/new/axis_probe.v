module axis_probe #(
    parameter TDATA_DEPTH = 160 
    ) (
    input  wire clk, rst_n,
    input wire [TDATA_DEPTH-1:0] inputPT_tdata,
    input wire inputPT_tvalid,
    output wire inputPT_tready,
    output wire [TDATA_DEPTH-1:0] outputPT_tdata,
    output wire outputPT_tvalid,
    input wire outputPT_tready, 
    output reg [31:0] cnt_valid_only,    // TVALID=1, TREADY=0  (backpressure)
    output reg [31:0] cnt_ready_only,    // TVALID=0, TREADY=1  (starvation)
    output reg [31:0] cnt_xfer,          // TVALID=1, TREADY=1  (transactions)
    output reg [31:0] cnt_idle,           // TVALID=0, TREADY=0
    output reg [31:0] tdata_sample
);
    

    always @(posedge clk) begin
        if (!rst_n) begin
            cnt_valid_only <= 0; cnt_ready_only <= 0;
            cnt_xfer <= 0;       cnt_idle <= 0;
        end else begin
            if      ( inputPT_tvalid &&  inputPT_tready) begin 
                cnt_xfer       <= cnt_xfer + 1;
                tdata_sample <= inputPT_tdata[31:0];
            end else if ( inputPT_tvalid && !inputPT_tready) cnt_valid_only <= cnt_valid_only + 1;
            else if (!inputPT_tvalid &&  inputPT_tready) cnt_ready_only <= cnt_ready_only + 1;
            else                          cnt_idle       <= cnt_idle + 1;
        end
    end
    
    assign outputPT_tdata = inputPT_tdata;
    assign outputPT_tvalid = inputPT_tvalid;
    assign inputPT_tready = outputPT_tready;
endmodule