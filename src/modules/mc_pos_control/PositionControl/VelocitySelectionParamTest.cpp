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
