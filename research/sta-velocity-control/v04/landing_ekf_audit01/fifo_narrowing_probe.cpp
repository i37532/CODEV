// Offline numeric-risk probe only. Not linked into PX4. No flight data replay.
// The out-of-range conversion intentionally reproduces the unchecked expression;
// sanitized execution MUST fail. Its unsanitized value is not portable behavior.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
int main(int argc, char **argv)
{
    if (argc != 2) { return 2; }
    volatile float input = std::strtof(argv[1], nullptr);
    const float scale = 9.80665f / 2048.f;
    int16_t narrowed = input / scale;
    std::printf("input=%.9g counts=%.9g int16=%d reconstructed=%.9g\n",
                double(input), double(input / scale), int(narrowed), double(narrowed * scale));
    return 0;
}
