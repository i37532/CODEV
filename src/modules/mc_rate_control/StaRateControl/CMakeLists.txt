px4_add_library(StaRateControl StaRateControl.cpp StaRateControl.hpp StaProtection.cpp StaProtection.hpp)
target_compile_features(StaRateControl PUBLIC cxx_std_14)
target_compile_options(StaRateControl PRIVATE ${MAX_CUSTOM_OPT_LEVEL})
target_include_directories(StaRateControl PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
px4_add_unit_gtest(SRC StaRateControlTest.cpp LINKLIBS StaRateControl)
px4_add_unit_gtest(SRC StaProtectionTest.cpp LINKLIBS StaRateControl)
px4_add_unit_gtest(SRC StaAxesApplicationTest.cpp LINKLIBS StaRateControl)

# M07 pure kernel: deliberately NOT a dependency of mc_rate_control / StaRateControl.
px4_add_library(IstaRateControl IstaRateControl.cpp IstaRateControl.hpp)
target_compile_features(IstaRateControl PUBLIC cxx_std_14)
target_compile_options(IstaRateControl PRIVATE ${MAX_CUSTOM_OPT_LEVEL})
target_include_directories(IstaRateControl PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
px4_add_unit_gtest(SRC IstaRateControlTest.cpp LINKLIBS IstaRateControl)
