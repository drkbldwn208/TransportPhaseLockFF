`timescale 1ns / 1ps
// Two independent cosine reads per clock from one replicated quarter-wave ROM.
// 14 phase bits/turn; 4096 positive 16-bit values; 2 RAMB36 per instance.
// Values lie at angle-bin centres, avoiding a special quarter-wave endpoint.
module pdh_cosine_pair (
    input wire clk,
    input wire [13:0] phase_a, phase_b,
    output reg signed [15:0] cosine_a, cosine_b
);
    (* rom_style="block" *) reg [15:0] rom [0:4095];
    initial $readmemh("pdh_quarter_cos.mem", rom);
    reg [11:0] address_a, address_b;
    reg negative_a, negative_b, sign_a, sign_b;
    reg [15:0] magnitude_a, magnitude_b;

    always @(posedge clk) begin
        address_a <= phase_a[12] ? ~phase_a[11:0] : phase_a[11:0];
        address_b <= phase_b[12] ? ~phase_b[11:0] : phase_b[11:0];
        negative_a <= phase_a[13] ^ phase_a[12];
        negative_b <= phase_b[13] ^ phase_b[12];
        magnitude_a <= rom[address_a];
        magnitude_b <= rom[address_b];
        sign_a <= negative_a;
        sign_b <= negative_b;
        cosine_a <= sign_a ? -$signed(magnitude_a) : $signed(magnitude_a);
        cosine_b <= sign_b ? -$signed(magnitude_b) : $signed(magnitude_b);
    end
endmodule
