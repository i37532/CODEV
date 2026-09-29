// Offline actual-plugin-waveform evaluation, no Gazebo or flight processes.
#include "ForceWave.hpp"
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
int main(int argc,char **argv) {
    if (argc!=4) return 2;
    try {
        const auto f=v08::force_enu(std::stod(argv[1]),std::stod(argv[2]),std::stod(argv[3]));
        std::cout << std::setprecision(17) << f[0] << ' ' << f[1] << ' ' << f[2] << '\n';
    } catch(const std::exception &) {return 1;}
    return 0;
}
