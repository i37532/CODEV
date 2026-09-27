############################################################################
#
#   Copyright (c) 2019 PX4 Development Team. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
# 3. Neither the name PX4 nor the names of its contributors may be
#    used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
# OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
# AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
############################################################################

px4_add_library(StaVelocityControl StaVelocityControl.cpp StaVelocityControl.hpp StaVelocityProtection.cpp StaVelocityProtection.hpp)
target_compile_features(StaVelocityControl PUBLIC cxx_std_14)
target_include_directories(StaVelocityControl PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

px4_add_library(PositionControl
	ControlMath.cpp
	ControlMath.hpp
	PositionControl.cpp
	PositionControl.hpp
)
target_include_directories(PositionControl PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(PositionControl PUBLIC StaVelocityControl)

px4_add_unit_gtest(SRC ControlMathTest.cpp LINKLIBS PositionControl)
px4_add_unit_gtest(SRC PositionControlTest.cpp LINKLIBS PositionControl)

if(BUILD_TESTING)
	px4_add_library(V00PositionReference
		test/v00/V00PositionControl.cpp
		test/v00/V00ControlMath.cpp
		test/v00/V00Takeoff.cpp
	)
	target_link_libraries(V00PositionReference PRIVATE hysteresis)
endif()
px4_add_unit_gtest(SRC VelocityControlTest.cpp LINKLIBS PositionControl V00PositionReference Takeoff)
px4_add_functional_gtest(SRC VelocitySelectionParamTest.cpp LINKLIBS PositionControl parameters)
px4_add_functional_gtest(SRC VelocityDiagnosticInputTest.cpp LINKLIBS PositionControl parameters)
px4_add_unit_gtest(SRC StaVelocityControlTest.cpp LINKLIBS StaVelocityControl)
px4_add_unit_gtest(SRC StaVelocityProtectionTest.cpp LINKLIBS StaVelocityControl PositionControl)
px4_add_unit_gtest(SRC VelocityEstaTest.cpp LINKLIBS PositionControl)
px4_add_unit_gtest(SRC VelocityEstaZTest.cpp LINKLIBS PositionControl)
px4_add_unit_gtest(SRC VelocityZIntegrationTest.cpp LINKLIBS PositionControl)
