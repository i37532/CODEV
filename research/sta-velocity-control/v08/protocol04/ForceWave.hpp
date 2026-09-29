// Research-only world-force waveform; never linked into PX4 control firmware.
#pragma once
#include <array>
#include <cmath>
#include <stdexcept>

namespace v08 {
inline std::array<double,3> force_enu(double elapsed, double north_phase, double east_phase)
{
    if (!std::isfinite(elapsed) || !std::isfinite(north_phase) || !std::isfinite(east_phase))
        throw std::invalid_argument("nonfinite force waveform input");
    if (elapsed <= 8. || elapsed >= 56.) return {{0.,0.,0.}};
    constexpr double pi=3.141592653589793238462643383279502884;
    const double t=elapsed-8.;
    const double envelope=std::pow(std::sin(pi*t/48.),2);
    const double north=.15*envelope*std::sin(2.*pi*t/16.+north_phase);
    const double east=.15*envelope*std::sin(2.*pi*t/24.+east_phase);
    return {{east,north,0.}}; // world ENU: x east, y north, z up; units N
}
}
