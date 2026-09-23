// Offline probe: real ECL projection and generated MAVLink wire codecs.
// No flight processes, estimator, Navigator instance, or controller changes.
#include <cstdio>
#include <cmath>
#include <cstdint>
#include <geo/geo.h>
#include <common/mavlink.h>

int main()
{
	double lat0, lon0, x, y;
	while (std::scanf("%lf %lf %lf %lf", &lat0, &lon0, &x, &y) == 4) {
		map_projection_reference_s ref{};
		map_projection_init_timestamped(&ref, lat0, lon0, 1);
		double lat, lon;
		map_projection_reproject(&ref, static_cast<float>(x), static_cast<float>(y), &lat, &lon);
		lon = std::fmod(lon + 540.0, 360.0) - 180.0;
		const int32_t ilat = static_cast<int32_t>(std::round(lat * 1e7));
		const int32_t ilon = static_cast<int32_t>(std::round(lon * 1e7));
		mavlink_message_t msg{};
		mavlink_msg_command_int_pack(255, 190, &msg, 1, 1, MAV_FRAME_GLOBAL_INT,
			MAV_CMD_DO_REPOSITION, 0, 0, -1.f, 1.f, 0.f, 1.5756663f, ilat, ilon, 490.5f);
		mavlink_command_int_t decoded{};
		mavlink_msg_command_int_decode(&msg, &decoded);
		if (decoded.x != ilat || decoded.y != ilon || decoded.frame != MAV_FRAME_GLOBAL_INT
		    || decoded.command != MAV_CMD_DO_REPOSITION || decoded.param4 != 1.5756663f) { return 2; }
		float nx, ny;
		map_projection_project(&ref, static_cast<double>(decoded.x) / 1e7,
			static_cast<double>(decoded.y) / 1e7, &nx, &ny);
		std::printf("%.17g %.17g %d %d %.17g %.17g\n", lat, lon, decoded.x, decoded.y,
			static_cast<double>(nx), static_cast<double>(ny));
	}
	return std::ferror(stdin) ? 3 : 0;
}
