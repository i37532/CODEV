// Synthetic source-path probe only: not a controller, firmware patch or flight replay.
// Out-of-range float->int16_t is intentionally exercised to expose the original
// unchecked conversion. Observed host behavior is NOT portable C++ semantics.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <climits>
int main(int argc, char **argv)
{
    if (argc != 2) { return 2; }
    volatile float input = std::strtof(argv[1], nullptr);
    constexpr float scale = 9.80665f / 2048.f;
    int16_t fifo = input / scale; // Original SimulatorMavlink assignment.
    bool clip = fifo <= INT16_MIN + 1 || fifo >= INT16_MAX - 1;
    std::printf("input=%.9g fifo=%d decoded=%.9g endpoint_clip=%d\n",
                static_cast<double>(input), fifo, static_cast<double>(fifo * scale), clip);
    return 0;
}
