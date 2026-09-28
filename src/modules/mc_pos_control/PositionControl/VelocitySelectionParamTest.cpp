// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include <parameters/param.h>
#include "VelocityControlSelector.hpp"
#include "PositionControl.hpp"
#include <cstdio>
#include <unistd.h>

TEST(VelocitySelectionParam, BsonSaveReloadAndFreshSelector)
{
	param_control_autosave(false);
	const param_t mode=param_find("MPC_VC_MODE"), axes=param_find("MPC_VC_AXES");
	ASSERT_NE(mode,PARAM_INVALID); ASSERT_NE(axes,PARAM_INVALID);
	EXPECT_EQ(param_type(mode),PARAM_TYPE_INT32); EXPECT_EQ(param_type(axes),PARAM_TYPE_INT32);
	param_reset(mode); param_reset(axes);
	int32_t m=-1, a=-1;
	ASSERT_EQ(param_get(mode,&m),0); ASSERT_EQ(param_get(axes,&a),0);
	EXPECT_EQ(m,0); EXPECT_EQ(a,0);
	m=2; a=7;
	ASSERT_EQ(param_set(mode,&m),0); ASSERT_EQ(param_set(axes,&a),0);
	FILE *file=tmpfile(); ASSERT_NE(file,nullptr);
	ASSERT_EQ(param_export(fileno(file),false,nullptr),0);
	param_reset(mode); param_reset(axes);
	ASSERT_EQ(lseek(fileno(file),0,SEEK_SET),0);
	ASSERT_EQ(param_import(fileno(file),true),0);
	fclose(file);
	ASSERT_EQ(param_get(mode,&m),0); ASSERT_EQ(param_get(axes,&a),0);
	EXPECT_EQ(m,2); EXPECT_EQ(a,7);
	VelocityControlSelector restarted;
	restarted.configure(m,a,false);
	EXPECT_EQ(restarted.reject(),6); EXPECT_EQ(restarted.effectiveMode(),0); EXPECT_EQ(restarted.effectiveAxes(),0);
	param_reset(mode); param_reset(axes);
}

TEST(VelocitySelectionParam, VelocityDivisorDefaultAndBsonRestart)
{
	param_control_autosave(false);
	const param_t key=param_find("MPC_VC_DIV"); ASSERT_NE(key,PARAM_INVALID); param_reset(key);
	int32_t value=0; ASSERT_EQ(param_get(key,&value),0); EXPECT_EQ(value,1);
	value=4; ASSERT_EQ(param_set(key,&value),0);
	FILE *file=tmpfile(); ASSERT_NE(file,nullptr); ASSERT_EQ(param_export(fileno(file),false,nullptr),0);
	param_reset(key); ASSERT_EQ(lseek(fileno(file),0,SEEK_SET),0); ASSERT_EQ(param_import(fileno(file),true),0); fclose(file);
	ASSERT_EQ(param_get(key,&value),0); EXPECT_EQ(value,4);
	PositionControl restarted; restarted.configureVelocityDivisor(value,false); EXPECT_EQ(restarted.velocityDecimation().divisor,4);
	param_reset(key);
}

TEST(VelocitySelectionParam, EstaGainsSavedReloadedAndDisarmedAdmission)
{
	param_control_autosave(false);
	const char *names[]={"MPC_VC_L1_X","MPC_VC_L2_X","MPC_VC_NU_X","MPC_VC_A_X"};
	float values[]={1.f,.2f,.4f,.8f}; param_t keys[4];
	for (int i=0;i<4;++i) {
		keys[i]=param_find(names[i]); ASSERT_NE(keys[i],PARAM_INVALID);
		param_reset(keys[i]); float zero=-1.f; ASSERT_EQ(param_get(keys[i],&zero),0);
		EXPECT_FLOAT_EQ(zero,0.f); ASSERT_EQ(param_set(keys[i],&values[i]),0);
	}
	const param_t mode=param_find("MPC_VC_MODE"),axes=param_find("MPC_VC_AXES");
	int32_t one=1; ASSERT_EQ(param_set(mode,&one),0); ASSERT_EQ(param_set(axes,&one),0);
	FILE *f=tmpfile(); ASSERT_NE(f,nullptr); ASSERT_EQ(param_export(fileno(f),false,nullptr),0);
	for (auto key:keys) { param_reset(key); } param_reset(mode); param_reset(axes);
	ASSERT_EQ(lseek(fileno(f),0,SEEK_SET),0); ASSERT_EQ(param_import(fileno(f),true),0); fclose(f);
	for (int i=0;i<4;++i) { float v=0.f; ASSERT_EQ(param_get(keys[i],&v),0); EXPECT_FLOAT_EQ(v,values[i]); }
	int32_t m=0,a=0; ASSERT_EQ(param_get(mode,&m),0); ASSERT_EQ(param_get(axes,&a),0);
	PositionControl restarted; StaVelocityProtection::Config c{};
	c.axes=1; c.gains[0]={values[0],values[1]}; c.nu_limit[0]=values[2]; c.acceleration_limit[0]=values[3];
	restarted.configureVelocityEsta(c,false); restarted.configureVelocityControl(m,a,false);
	EXPECT_EQ(restarted.velocitySelection().effectiveMode(),1); EXPECT_EQ(restarted.velocitySelection().effectiveAxes(),1);
	for (auto key:keys) { param_reset(key); } param_reset(mode); param_reset(axes);
}

TEST(VelocitySelectionParam, XYIndependentGainsAndMaskSurviveBsonReload)
{
	param_control_autosave(false);
	const char *names[]={"MPC_VC_L1_X","MPC_VC_L2_X","MPC_VC_NU_X","MPC_VC_A_X",
		"MPC_VC_L1_Y","MPC_VC_L2_Y","MPC_VC_NU_Y","MPC_VC_A_Y"};
	float values[]={1.f,.2f,.4f,.8f,1.5f,.3f,.5f,.9f}; param_t keys[8];
	for(int i=0;i<8;++i) { keys[i]=param_find(names[i]); ASSERT_NE(keys[i],PARAM_INVALID); ASSERT_EQ(param_set(keys[i],&values[i]),0); }
	const param_t mode=param_find("MPC_VC_MODE"),axes=param_find("MPC_VC_AXES");
	int32_t one=1,three=3; ASSERT_EQ(param_set(mode,&one),0); ASSERT_EQ(param_set(axes,&three),0);
	FILE *f=tmpfile(); ASSERT_NE(f,nullptr); ASSERT_EQ(param_export(fileno(f),false,nullptr),0);
	for(auto key:keys) { param_reset(key); } param_reset(mode); param_reset(axes);
	ASSERT_EQ(lseek(fileno(f),0,SEEK_SET),0); ASSERT_EQ(param_import(fileno(f),true),0); fclose(f);
	float loaded[8]{};
	for(int i=0;i<8;++i) { ASSERT_EQ(param_get(keys[i],&loaded[i]),0); EXPECT_FLOAT_EQ(loaded[i],values[i]); }
	int32_t m=0,a=0; ASSERT_EQ(param_get(mode,&m),0); ASSERT_EQ(param_get(axes,&a),0);
	StaVelocityProtection::Config c{}; c.axes=a;
	for(int i=0;i<2;++i) { c.gains[i]={loaded[4*i],loaded[4*i+1]}; c.nu_limit[i]=loaded[4*i+2]; c.acceleration_limit[i]=loaded[4*i+3]; }
	PositionControl restarted; restarted.configureVelocityEsta(c,false); restarted.configureVelocityControl(m,a,false);
	EXPECT_EQ(restarted.velocitySelection().effectiveMode(),1); EXPECT_EQ(restarted.velocitySelection().effectiveAxes(),3);
	for(auto key:keys) { param_reset(key); } param_reset(mode); param_reset(axes);
}

TEST(VelocitySelectionParam, XYZIndependentGainsAndMaskSurviveBsonReload)
{
	param_control_autosave(false);
	const char *names[]={"MPC_VC_L1_X","MPC_VC_L2_X","MPC_VC_NU_X","MPC_VC_A_X",
		"MPC_VC_L1_Y","MPC_VC_L2_Y","MPC_VC_NU_Y","MPC_VC_A_Y",
		"MPC_VC_L1_Z","MPC_VC_L2_Z","MPC_VC_NU_Z","MPC_VC_A_Z"};
	float values[]={1.f,.2f,.4f,.8f,1.5f,.3f,.5f,.9f,2.f,1.f,4.f,6.f}; param_t keys[12];
	for(int i=0;i<12;++i) { keys[i]=param_find(names[i]); ASSERT_NE(keys[i],PARAM_INVALID); ASSERT_EQ(param_set(keys[i],&values[i]),0); }
	const param_t mode=param_find("MPC_VC_MODE"),axes=param_find("MPC_VC_AXES");
	int32_t one=1,three=7; ASSERT_EQ(param_set(mode,&one),0); ASSERT_EQ(param_set(axes,&three),0);
	FILE *f=tmpfile(); ASSERT_NE(f,nullptr); ASSERT_EQ(param_export(fileno(f),false,nullptr),0);
	for(auto key:keys) { param_reset(key); } param_reset(mode); param_reset(axes);
	ASSERT_EQ(lseek(fileno(f),0,SEEK_SET),0); ASSERT_EQ(param_import(fileno(f),true),0); fclose(f);
	float loaded[12]{};
	for(int i=0;i<12;++i) { ASSERT_EQ(param_get(keys[i],&loaded[i]),0); EXPECT_FLOAT_EQ(loaded[i],values[i]); }
	int32_t m=0,a=0; ASSERT_EQ(param_get(mode,&m),0); ASSERT_EQ(param_get(axes,&a),0);
	StaVelocityProtection::Config c{}; c.axes=a;
	for(int i=0;i<3;++i) { c.gains[i]={loaded[4*i],loaded[4*i+1]}; c.nu_limit[i]=loaded[4*i+2]; c.acceleration_limit[i]=loaded[4*i+3]; }
	PositionControl restarted; restarted.configureVelocityEsta(c,false); restarted.configureVelocityControl(m,a,false);
	EXPECT_EQ(restarted.velocitySelection().effectiveMode(),1); EXPECT_EQ(restarted.velocitySelection().effectiveAxes(),7);
	for(auto key:keys) { param_reset(key); } param_reset(mode); param_reset(axes);
}


TEST(VelocitySelectionParam, ZGainsBsonReloadDoNotDependOnXGains)
{
	param_control_autosave(false);
	const char *names[]={"MPC_VC_L1_Z","MPC_VC_L2_Z","MPC_VC_NU_Z","MPC_VC_A_Z"};
	float values[]={1.f,.2f,2.f,3.f}; param_t keys[4];
	for(int i=0;i<4;++i) {
		keys[i]=param_find(names[i]); ASSERT_NE(keys[i],PARAM_INVALID); param_reset(keys[i]);
		float value=-1.f; ASSERT_EQ(param_get(keys[i],&value),0); EXPECT_FLOAT_EQ(value,0.f);
		ASSERT_EQ(param_set(keys[i],&values[i]),0);
	}
	FILE *f=tmpfile(); ASSERT_NE(f,nullptr); ASSERT_EQ(param_export(fileno(f),false,nullptr),0);
	for(auto key:keys) { param_reset(key); }
	ASSERT_EQ(lseek(fileno(f),0,SEEK_SET),0); ASSERT_EQ(param_import(fileno(f),true),0); fclose(f);
	for(int i=0;i<4;++i) { float value=0.f; ASSERT_EQ(param_get(keys[i],&value),0); EXPECT_FLOAT_EQ(value,values[i]); }
	StaVelocityProtection::Config c{}; c.axes=4; c.gains[2]={values[0],values[1]}; c.nu_limit[2]=values[2]; c.acceleration_limit[2]=values[3];
	PositionControl restarted; restarted.configureVelocityEsta(c,false); restarted.configureVelocityControl(1,4,false);
	EXPECT_EQ(restarted.velocitySelection().effectiveAxes(),4);
	restarted.configureVelocityControl(1,1,false); EXPECT_NE(restarted.velocitySelection().reject(),0);
	for(auto key:keys) { param_reset(key); }
}
