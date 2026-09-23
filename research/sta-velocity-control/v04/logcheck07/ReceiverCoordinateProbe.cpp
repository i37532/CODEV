// Offline codec + receiver expression reference, compiled with pinned SITL flags.
#include <cstdint>
#include <common/mavlink.h>
extern "C" double receive_coordinate(int32_t coordinate)
{
    mavlink_message_t message{};
    mavlink_command_int_t command{};
    command.x = coordinate;
    command.y = coordinate;
    command.command = MAV_CMD_DO_REPOSITION;
    command.frame = MAV_FRAME_GLOBAL_INT;
    mavlink_msg_command_int_encode(255, 190, &message, &command);
    mavlink_command_int_t cmd_mavlink{};
    mavlink_msg_command_int_decode(&message, &cmd_mavlink);
    // Same expression as the SHA-pinned production receiver; do not rationalize here.
    return ((double)cmd_mavlink.x) / 1e7;
}
