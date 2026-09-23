// Read-only diagnostic of the receiver's integer-coordinate expression.
// Not a controller or revised flight/acceptance path.
#include <cstdio>
#include <cstdlib>
#include <cstdint>
int main(int argc, char **argv)
{
    if (argc != 2) { return 2; }
    volatile int32_t wire = static_cast<int32_t>(std::strtol(argv[1], nullptr, 10));
    const double value = static_cast<double>(wire) / 1e7;
    std::printf("%.17g %a\n", value, value);
    return 0;
}
