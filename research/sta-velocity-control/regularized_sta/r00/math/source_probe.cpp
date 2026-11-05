// SPDX-License-Identifier: BSD-3-Clause
// R00 read-only source-package probe. This is NOT a production controller.
#include "velocity_sta_ista.hpp"
#include <cmath>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <limits>

namespace {
std::size_t checks = 0, failures = 0, cases = 0;
void check(bool value) { ++checks; if (!value) { ++failures; } }
long double psi(long double s, long double epsilon)
{
    // Piecewise form, independent of the package's product/max evaluation.
    if (std::fabs(s) <= epsilon) { return s / std::sqrt(epsilon); }
    return std::copysign(std::sqrt(std::fabs(s)), s);
}
long double rho(long double s, long double epsilon)
{
    if (s >= epsilon) { return 1; }
    if (s <= -epsilon) { return -1; }
    return s / epsilon;
}
template<typename T> void mapped_grid()
{
    using namespace velocity_control;
    const long double configurations[][3] = {
        {.5L, .1L, .01L}, {2.L, 1.L, .02L},
        {3.L, 1.L, .1L}, {20.L, 12.L, .01L}
    };
    for (const auto &config : configurations) {
        const T eps = T(config[2]);
        const Parameters<T> p{T(config[0]), T(config[1]), eps, T(-1e9), T(1e9), T(1000)};
        const T errors[] = {T(0), -T(0), T(1e-12), T(-1e-12),
            eps / 2, -eps / 2, eps, -eps,
            std::nextafter(eps, T(0)), std::nextafter(-eps, T(0)),
            std::nextafter(eps, std::numeric_limits<T>::infinity()),
            std::nextafter(-eps, -std::numeric_limits<T>::infinity()),
            10 * eps, -10 * eps, T(1)};
        for (T s : errors) for (T nu : {T(-.2), T(0), T(.2)})
        for (T h : {T(.002), T(.005), T(.01), T(.04)})
        for (T ff : {T(-.1), T(0), T(.1)}) {
            State<T> state(nu);
            // Package e=-s. nu retains its physical acceleration sign.
            const auto got = propose(Algorithm::STA, p, state, Input<T>{-s, ff, h});
            const long double raw = (long double)ff - p.k1 * psi(s, eps) + nu;
            const long double candidate = (long double)nu - (long double)h * p.k2 * rho(s, eps);
            const long double tolerance = sizeof(T) == 4 ? 6e-6L : 1e-12L;
            ++cases;
            check(got.valid());
            check(std::fabs(got.acceleration_raw - raw) <= tolerance * (1 + std::fabs(raw)));
            check(std::fabs(got.nu_candidate - candidate) <= tolerance * (1 + std::fabs(candidate)));
            check(state.nu == nu); // propose never commits, including nonzero old nu.
        }
    }
}
}

int main()
{
    using namespace velocity_control;
    mapped_grid<float>(); mapped_grid<double>();
    const Parameters<double> p{3., 1., .1, -100., 100., 5.};
    State<double> reset_state;
    auto before_reset = propose(Algorithm::STA, p, reset_state, Input<double>{.5, 0., .005});
    reset_state.reset();
    const bool stale_reset_accepted = commit(reset_state, before_reset);
    State<double> axis_x, axis_y;
    auto cross_axis = propose(Algorithm::STA, p, axis_x, Input<double>{.5, 0., .005});
    const bool cross_axis_accepted = commit(axis_y, cross_axis);
    // These are deliberate audit observations, NOT safety acceptance checks.
    check(stale_reset_accepted && reset_state.nu == .005);
    check(cross_axis_accepted && axis_y.nu == .005 && axis_x.nu == 0.);
    // The package applies a total-acceleration clamp; PX4 retains correction
    // clamp before FF. A counterexample prevents claiming they are equivalent.
    State<double> limit_state;
    const Parameters<double> tight{3., 1., .1, -1., 1., 5.};
    auto limit = propose(Algorithm::STA, tight, limit_state, Input<double>{1., 3., .005});
    check(limit.acceleration_limited == 1.);
    const double correction_then_ff = 1. + 3.;
    check(limit.acceleration_limited != correction_then_ff);
    std::cout << std::setprecision(17)
        << "{\"input_cases_float_and_double\":" << cases
        << ",\"assertions\":" << checks << ",\"failures\":" << failures
        << ",\"source_reset_same_value_stale_accepted\":" << (stale_reset_accepted ? "true" : "false")
        << ",\"source_cross_axis_candidate_accepted\":" << (cross_axis_accepted ? "true" : "false")
        << ",\"package_total_clamp\":" << limit.acceleration_limited
        << ",\"px4_order_counterexample\":" << correction_then_ff << "}\n";
    return failures ? 1 : 0;
}
