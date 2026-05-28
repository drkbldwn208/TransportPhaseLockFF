; ModuleID = '/home/levlabcukomen/Desktop/VivadoProjects/TransportPhaseLockFF/hls_sources/rfdc_iq_derotator/rfdc_iq_derotator_prj/solution1/.autopilot/db/a.g.ld.5.gdce.bc'
source_filename = "llvm-link"
target datalayout = "e-m:e-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
target triple = "fpga64-xilinx-none"

%"class.hls::stream<ap_uint<128>, 0>" = type { %"struct.ap_uint<128>" }
%"struct.ap_uint<128>" = type { %"struct.ap_int_base<128, false>" }
%"struct.ap_int_base<128, false>" = type { %"struct.ssdm_int<128, false>" }
%"struct.ssdm_int<128, false>" = type { i128 }
%"struct.ap_uint<32>" = type { %"struct.ap_int_base<32, false>" }
%"struct.ap_int_base<32, false>" = type { %"struct.ssdm_int<32, false>" }
%"struct.ssdm_int<32, false>" = type { i32 }

; Function Attrs: inaccessiblememonly nounwind willreturn
declare void @llvm.sideeffect() #0

; Function Attrs: noinline willreturn
define void @apatb_rfdc_iq_derotator_ir(%"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture nonnull dereferenceable(16) %s_axis_i, %"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture nonnull dereferenceable(16) %s_axis_q, %"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture nonnull dereferenceable(16) %m_axis_i, %"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture nonnull dereferenceable(16) %m_axis_q, i1 zeroext %enable, i1 zeroext %reset_phase, %"struct.ap_uint<32>"* nocapture readonly %phase_offset) local_unnamed_addr #1 {
entry:
  %s_axis_i_copy = alloca i128, align 512
  call void @llvm.sideeffect() #7 [ "stream_interface"(i128* %s_axis_i_copy, i32 0) ]
  %s_axis_q_copy = alloca i128, align 512
  call void @llvm.sideeffect() #7 [ "stream_interface"(i128* %s_axis_q_copy, i32 0) ]
  %m_axis_i_copy = alloca i128, align 512
  call void @llvm.sideeffect() #7 [ "stream_interface"(i128* %m_axis_i_copy, i32 0) ]
  %m_axis_q_copy = alloca i128, align 512
  call void @llvm.sideeffect() #7 [ "stream_interface"(i128* %m_axis_q_copy, i32 0) ]
  call fastcc void @copy_in(%"class.hls::stream<ap_uint<128>, 0>"* nonnull %s_axis_i, i128* nonnull align 512 %s_axis_i_copy, %"class.hls::stream<ap_uint<128>, 0>"* nonnull %s_axis_q, i128* nonnull align 512 %s_axis_q_copy, %"class.hls::stream<ap_uint<128>, 0>"* nonnull %m_axis_i, i128* nonnull align 512 %m_axis_i_copy, %"class.hls::stream<ap_uint<128>, 0>"* nonnull %m_axis_q, i128* nonnull align 512 %m_axis_q_copy)
  call void @apatb_rfdc_iq_derotator_hw(i128* %s_axis_i_copy, i128* %s_axis_q_copy, i128* %m_axis_i_copy, i128* %m_axis_q_copy, i1 %enable, i1 %reset_phase, %"struct.ap_uint<32>"* %phase_offset)
  call void @copy_back(%"class.hls::stream<ap_uint<128>, 0>"* %s_axis_i, i128* %s_axis_i_copy, %"class.hls::stream<ap_uint<128>, 0>"* %s_axis_q, i128* %s_axis_q_copy, %"class.hls::stream<ap_uint<128>, 0>"* %m_axis_i, i128* %m_axis_i_copy, %"class.hls::stream<ap_uint<128>, 0>"* %m_axis_q, i128* %m_axis_q_copy)
  ret void
}

; Function Attrs: argmemonly noinline willreturn
define internal fastcc void @copy_in(%"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="0", i128* noalias nocapture align 512 "unpacked"="1.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="2", i128* noalias nocapture align 512 "unpacked"="3.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="4", i128* noalias nocapture align 512 "unpacked"="5.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="6", i128* noalias nocapture align 512 "unpacked"="7.0") unnamed_addr #2 {
entry:
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>.13"(i128* align 512 %1, %"class.hls::stream<ap_uint<128>, 0>"* %0)
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>.13"(i128* align 512 %3, %"class.hls::stream<ap_uint<128>, 0>"* %2)
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>.13"(i128* align 512 %5, %"class.hls::stream<ap_uint<128>, 0>"* %4)
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>.13"(i128* align 512 %7, %"class.hls::stream<ap_uint<128>, 0>"* %6)
  ret void
}

; Function Attrs: argmemonly noinline willreturn
define internal fastcc void @copy_out(%"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="0", i128* noalias nocapture align 512 "unpacked"="1.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="2", i128* noalias nocapture align 512 "unpacked"="3.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="4", i128* noalias nocapture align 512 "unpacked"="5.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="6", i128* noalias nocapture align 512 "unpacked"="7.0") unnamed_addr #3 {
entry:
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>"(%"class.hls::stream<ap_uint<128>, 0>"* %0, i128* align 512 %1)
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>"(%"class.hls::stream<ap_uint<128>, 0>"* %2, i128* align 512 %3)
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>"(%"class.hls::stream<ap_uint<128>, 0>"* %4, i128* align 512 %5)
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>"(%"class.hls::stream<ap_uint<128>, 0>"* %6, i128* align 512 %7)
  ret void
}

; Function Attrs: argmemonly noinline willreturn
define internal fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>"(%"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="0" %dst, i128* noalias nocapture align 512 "unpacked"="1.0" %src) unnamed_addr #4 {
entry:
  %0 = icmp eq %"class.hls::stream<ap_uint<128>, 0>"* %dst, null
  br i1 %0, label %ret, label %copy

copy:                                             ; preds = %entry
  call fastcc void @"streamcpy_hls.p0class.hls::stream<ap_uint<128>, 0>.8"(%"class.hls::stream<ap_uint<128>, 0>"* nonnull %dst, i128* align 512 %src)
  br label %ret

ret:                                              ; preds = %copy, %entry
  ret void
}

; Function Attrs: argmemonly noinline willreturn
define internal fastcc void @"streamcpy_hls.p0class.hls::stream<ap_uint<128>, 0>.8"(%"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture "unpacked"="0", i128* noalias nocapture align 512 "unpacked"="1.0") unnamed_addr #5 {
entry:
  %2 = alloca i128
  %3 = alloca %"class.hls::stream<ap_uint<128>, 0>"
  br label %empty

empty:                                            ; preds = %push, %entry
  %4 = bitcast i128* %1 to i8*
  %5 = call i1 @fpga_fifo_not_empty_16(i8* %4)
  br i1 %5, label %push, label %ret

push:                                             ; preds = %empty
  %6 = bitcast i128* %2 to i8*
  %7 = bitcast i128* %1 to i8*
  call void @fpga_fifo_pop_16(i8* %6, i8* %7)
  %8 = load volatile i128, i128* %2
  %.ivi = insertvalue %"class.hls::stream<ap_uint<128>, 0>" undef, i128 %8, 0, 0, 0, 0
  store %"class.hls::stream<ap_uint<128>, 0>" %.ivi, %"class.hls::stream<ap_uint<128>, 0>"* %3
  %9 = bitcast %"class.hls::stream<ap_uint<128>, 0>"* %3 to i8*
  %10 = bitcast %"class.hls::stream<ap_uint<128>, 0>"* %0 to i8*
  call void @fpga_fifo_push_16(i8* %9, i8* %10)
  br label %empty, !llvm.loop !5

ret:                                              ; preds = %empty
  ret void
}

; Function Attrs: argmemonly noinline willreturn
define internal fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>.13"(i128* noalias nocapture align 512 "unpacked"="0.0" %dst, %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="1" %src) unnamed_addr #4 {
entry:
  %0 = icmp eq %"class.hls::stream<ap_uint<128>, 0>"* %src, null
  br i1 %0, label %ret, label %copy

copy:                                             ; preds = %entry
  call fastcc void @"streamcpy_hls.p0class.hls::stream<ap_uint<128>, 0>.16"(i128* align 512 %dst, %"class.hls::stream<ap_uint<128>, 0>"* nonnull %src)
  br label %ret

ret:                                              ; preds = %copy, %entry
  ret void
}

; Function Attrs: argmemonly noinline willreturn
define internal fastcc void @"streamcpy_hls.p0class.hls::stream<ap_uint<128>, 0>.16"(i128* noalias nocapture align 512 "unpacked"="0.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture "unpacked"="1") unnamed_addr #5 {
entry:
  %2 = alloca %"class.hls::stream<ap_uint<128>, 0>"
  %3 = alloca i128
  br label %empty

empty:                                            ; preds = %push, %entry
  %4 = bitcast %"class.hls::stream<ap_uint<128>, 0>"* %1 to i8*
  %5 = call i1 @fpga_fifo_not_empty_16(i8* %4)
  br i1 %5, label %push, label %ret

push:                                             ; preds = %empty
  %6 = bitcast %"class.hls::stream<ap_uint<128>, 0>"* %2 to i8*
  %7 = bitcast %"class.hls::stream<ap_uint<128>, 0>"* %1 to i8*
  call void @fpga_fifo_pop_16(i8* %6, i8* %7)
  %8 = load volatile %"class.hls::stream<ap_uint<128>, 0>", %"class.hls::stream<ap_uint<128>, 0>"* %2
  %.evi = extractvalue %"class.hls::stream<ap_uint<128>, 0>" %8, 0, 0, 0, 0
  store i128 %.evi, i128* %3
  %9 = bitcast i128* %3 to i8*
  %10 = bitcast i128* %0 to i8*
  call void @fpga_fifo_push_16(i8* %9, i8* %10)
  br label %empty, !llvm.loop !7

ret:                                              ; preds = %empty
  ret void
}

declare void @apatb_rfdc_iq_derotator_hw(i128*, i128*, i128*, i128*, i1, i1, %"struct.ap_uint<32>"*)

; Function Attrs: argmemonly noinline willreturn
define internal fastcc void @copy_back(%"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="0", i128* noalias nocapture align 512 "unpacked"="1.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="2", i128* noalias nocapture align 512 "unpacked"="3.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="4", i128* noalias nocapture align 512 "unpacked"="5.0", %"class.hls::stream<ap_uint<128>, 0>"* noalias "unpacked"="6", i128* noalias nocapture align 512 "unpacked"="7.0") unnamed_addr #3 {
entry:
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>"(%"class.hls::stream<ap_uint<128>, 0>"* %0, i128* align 512 %1)
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>"(%"class.hls::stream<ap_uint<128>, 0>"* %2, i128* align 512 %3)
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>"(%"class.hls::stream<ap_uint<128>, 0>"* %4, i128* align 512 %5)
  call fastcc void @"onebyonecpy_hls.p0class.hls::stream<ap_uint<128>, 0>"(%"class.hls::stream<ap_uint<128>, 0>"* %6, i128* align 512 %7)
  ret void
}

define void @rfdc_iq_derotator_hw_stub_wrapper(i128*, i128*, i128*, i128*, i1, i1, %"struct.ap_uint<32>"*) #6 {
entry:
  %7 = alloca %"class.hls::stream<ap_uint<128>, 0>"
  %8 = alloca %"class.hls::stream<ap_uint<128>, 0>"
  %9 = alloca %"class.hls::stream<ap_uint<128>, 0>"
  %10 = alloca %"class.hls::stream<ap_uint<128>, 0>"
  call void @copy_out(%"class.hls::stream<ap_uint<128>, 0>"* %7, i128* %0, %"class.hls::stream<ap_uint<128>, 0>"* %8, i128* %1, %"class.hls::stream<ap_uint<128>, 0>"* %9, i128* %2, %"class.hls::stream<ap_uint<128>, 0>"* %10, i128* %3)
  call void @rfdc_iq_derotator_hw_stub(%"class.hls::stream<ap_uint<128>, 0>"* %7, %"class.hls::stream<ap_uint<128>, 0>"* %8, %"class.hls::stream<ap_uint<128>, 0>"* %9, %"class.hls::stream<ap_uint<128>, 0>"* %10, i1 %4, i1 %5, %"struct.ap_uint<32>"* %6)
  call void @copy_in(%"class.hls::stream<ap_uint<128>, 0>"* %7, i128* %0, %"class.hls::stream<ap_uint<128>, 0>"* %8, i128* %1, %"class.hls::stream<ap_uint<128>, 0>"* %9, i128* %2, %"class.hls::stream<ap_uint<128>, 0>"* %10, i128* %3)
  ret void
}

declare void @rfdc_iq_derotator_hw_stub(%"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture nonnull, %"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture nonnull, %"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture nonnull, %"class.hls::stream<ap_uint<128>, 0>"* noalias nocapture nonnull, i1 zeroext, i1 zeroext, %"struct.ap_uint<32>"* nocapture readonly)

declare i1 @fpga_fifo_not_empty_16(i8*)

declare void @fpga_fifo_pop_16(i8*, i8*)

declare void @fpga_fifo_push_16(i8*, i8*)

attributes #0 = { inaccessiblememonly nounwind willreturn }
attributes #1 = { noinline willreturn "fpga.wrapper.func"="wrapper" }
attributes #2 = { argmemonly noinline willreturn "fpga.wrapper.func"="copyin" }
attributes #3 = { argmemonly noinline willreturn "fpga.wrapper.func"="copyout" }
attributes #4 = { argmemonly noinline willreturn "fpga.wrapper.func"="onebyonecpy_hls" }
attributes #5 = { argmemonly noinline willreturn "fpga.wrapper.func"="streamcpy_hls" }
attributes #6 = { "fpga.wrapper.func"="stub" }
attributes #7 = { inaccessiblememonly nounwind willreturn "xlx.port.bitwidth"="128" "xlx.source"="user" }

!llvm.dbg.cu = !{}
!llvm.ident = !{!0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0, !0}
!llvm.module.flags = !{!1, !2, !3}
!blackbox_cfg = !{!4}

!0 = !{!"clang version 7.0.0 "}
!1 = !{i32 2, !"Dwarf Version", i32 4}
!2 = !{i32 2, !"Debug Info Version", i32 3}
!3 = !{i32 1, !"wchar_size", i32 4}
!4 = !{}
!5 = distinct !{!5, !6}
!6 = !{!"llvm.loop.rotate.disable"}
!7 = distinct !{!7, !6}
