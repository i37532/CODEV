// SPDX-License-Identifier: BSD-3-Clause
#include <gtest/gtest.h>
#include <parameters/param.h>
#include "VelocityControlSelector.hpp"
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
