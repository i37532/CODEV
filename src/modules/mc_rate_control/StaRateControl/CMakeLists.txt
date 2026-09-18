px4_add_library(StaRateControl StaRateControl.cpp StaRateControl.hpp StaProtection.cpp StaProtection.hpp)
target_compile_features(StaRateControl PUBLIC cxx_std_14)
target_compile_options(StaRateControl PRIVATE ${MAX_CUSTOM_OPT_LEVEL})
target_include_directories(StaRateControl PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
px4_add_unit_gtest(SRC StaRateControlTest.cpp LINKLIBS StaRateControl)
px4_add_unit_gtest(SRC StaProtectionTest.cpp LINKLIBS StaRateControl)
px4_add_unit_gtest(SRC StaAxesApplicationTest.cpp LINKLIBS StaRateControl)

# M08: selected by the shared protection adapter; never evaluated as idle output.
px4_add_library(IstaRateControl IstaRateControl.cpp IstaRateControl.hpp)
target_compile_features(IstaRateControl PUBLIC cxx_std_14)
target_compile_options(IstaRateControl PRIVATE ${MAX_CUSTOM_OPT_LEVEL})
target_include_directories(IstaRateControl PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(StaRateControl PUBLIC IstaRateControl)
px4_add_unit_gtest(SRC IstaRateControlTest.cpp LINKLIBS IstaRateControl)
px4_add_unit_gtest(SRC IstaIntegrationTest.cpp LINKLIBS StaRateControl RateControl)
px4_add_unit_gtest(SRC ControlDecimationTest.cpp LINKLIBS StaRateControl RateControl)

# I01: standalone offline kernel. NO dependency from module, dispatcher or protection.
px4_add_library(ProperIstaRateControl ProperIstaRateControl.cpp ProperIstaRateControl.hpp)
target_compile_features(ProperIstaRateControl PUBLIC cxx_std_14)
target_compile_options(ProperIstaRateControl PRIVATE ${MAX_CUSTOM_OPT_LEVEL})
target_include_directories(ProperIstaRateControl PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
px4_add_unit_gtest(SRC ProperIstaRateControlTest.cpp LINKLIBS ProperIstaRateControl)
