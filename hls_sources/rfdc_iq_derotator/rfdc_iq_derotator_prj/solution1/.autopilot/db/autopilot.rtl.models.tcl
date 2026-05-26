set SynModuleInfo {
  {SRCNAME rfdc_iq_derotator MODELNAME rfdc_iq_derotator RTLNAME rfdc_iq_derotator IS_TOP 1
    SUBMODULES {
      {MODELNAME rfdc_iq_derotator_mul_16s_16s_32_1_1 RTLNAME rfdc_iq_derotator_mul_16s_16s_32_1_1 BINDTYPE op TYPE mul IMPL auto LATENCY 0 ALLOW_PRAGMA 1}
      {MODELNAME rfdc_iq_derotator_sparsemux_7_2_16_1_1 RTLNAME rfdc_iq_derotator_sparsemux_7_2_16_1_1 BINDTYPE op TYPE sparsemux IMPL auto}
      {MODELNAME rfdc_iq_derotator_mac_muladd_16s_16s_32s_33_4_1 RTLNAME rfdc_iq_derotator_mac_muladd_16s_16s_32s_33_4_1 BINDTYPE op TYPE all IMPL dsp_slice LATENCY 3}
      {MODELNAME rfdc_iq_derotator_mac_mulsub_16s_16s_32s_32_4_1 RTLNAME rfdc_iq_derotator_mac_mulsub_16s_16s_32s_32_4_1 BINDTYPE op TYPE all IMPL dsp_slice LATENCY 3}
      {MODELNAME rfdc_iq_derotator_frp_fifoout RTLNAME rfdc_iq_derotator_frp_fifoout BINDTYPE interface TYPE internal_frp_fifoout}
      {MODELNAME rfdc_iq_derotator_frp_pipeline_valid RTLNAME rfdc_iq_derotator_frp_pipeline_valid BINDTYPE interface TYPE internal_frp_validbits INSTNAME rfdc_iq_derotator_frp_pipeline_valid_U}
      {MODELNAME rfdc_iq_derotator_regslice_both RTLNAME rfdc_iq_derotator_regslice_both BINDTYPE interface TYPE adapter IMPL reg_slice}
    }
  }
}
