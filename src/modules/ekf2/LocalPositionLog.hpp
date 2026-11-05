// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <uORB/Publication.hpp>
#include <uORB/topics/vehicle_local_position.h>
#include <uORB/topics/vehicle_local_position_log.h>

// Dedicated SITL evidence channel. Original latest-value topic and its consumers
// are unchanged. No blocking, backpressure, clock rewriting or control feedback.
class LocalPositionLog
{
public:
	void publish(const vehicle_local_position_s &in)
	{
		vehicle_local_position_log_s out{};
		out.timestamp = in.timestamp;
		out.timestamp_sample = in.timestamp_sample;
		out.xy_valid = in.xy_valid;
		out.z_valid = in.z_valid;
		out.v_xy_valid = in.v_xy_valid;
		out.v_z_valid = in.v_z_valid;
		out.x = in.x;
		out.y = in.y;
		out.z = in.z;
		for (unsigned i = 0; i < 2; ++i) { out.delta_xy[i] = in.delta_xy[i]; }
		out.xy_reset_counter = in.xy_reset_counter;
		out.delta_z = in.delta_z;
		out.z_reset_counter = in.z_reset_counter;
		out.vx = in.vx;
		out.vy = in.vy;
		out.vz = in.vz;
		out.z_deriv = in.z_deriv;
		for (unsigned i = 0; i < 2; ++i) { out.delta_vxy[i] = in.delta_vxy[i]; }
		out.vxy_reset_counter = in.vxy_reset_counter;
		out.delta_vz = in.delta_vz;
		out.vz_reset_counter = in.vz_reset_counter;
		out.ax = in.ax;
		out.ay = in.ay;
		out.az = in.az;
		out.heading = in.heading;
		out.delta_heading = in.delta_heading;
		out.heading_reset_counter = in.heading_reset_counter;
		out.xy_global = in.xy_global;
		out.z_global = in.z_global;
		out.ref_timestamp = in.ref_timestamp;
		out.ref_lat = in.ref_lat;
		out.ref_lon = in.ref_lon;
		out.ref_alt = in.ref_alt;
		out.dist_bottom = in.dist_bottom;
		out.dist_bottom_valid = in.dist_bottom_valid;
		out.dist_bottom_sensor_bitfield = in.dist_bottom_sensor_bitfield;
		out.eph = in.eph;
		out.epv = in.epv;
		out.evh = in.evh;
		out.evv = in.evv;
		out.vxy_max = in.vxy_max;
		out.vz_max = in.vz_max;
		out.hagl_min = in.hagl_min;
		out.hagl_max = in.hagl_max;
		out.log_seq = ++_sequence;
		_pub.publish(out);
	}
private:
	uint32_t _sequence{0};
	uORB::Publication<vehicle_local_position_log_s> _pub{ORB_ID(vehicle_local_position_log)};
};
