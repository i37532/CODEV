// SPDX-License-Identifier: BSD-3-Clause
// C ABI exposes actual kernels, not a copied control law. Offline only.
#include "RegularizedStaVelocityControl.hpp"
#include "StaVelocityControl.hpp"
#include <cstdint>

struct Probe {
    RegularizedStaVelocityControl regularized;
    StaVelocityControl legacy;
    RegularizedStaVelocityControl::Candidate new_candidate;
    StaVelocityControl::Candidate old_candidate;
};

extern "C" {
void *r01_create() { return new Probe; }
void r01_destroy(void *p) { delete static_cast<Probe *>(p); }
int r01_config(void *p, int algorithm, float l1, float l2, float epsilon)
{
    auto &q = *static_cast<Probe *>(p);
    return algorithm ? q.regularized.setParameters(0, {l1, l2, epsilon}) : q.legacy.setParameters(0, {l1, l2});
}
int r01_reset(void *p, int algorithm, float nu)
{
    auto &q = *static_cast<Probe *>(p);
    return algorithm ? q.regularized.reset(0, nu) : q.legacy.reset(0, nu);
}
int r01_evaluate(void *p, int algorithm, float v, float target, float h, float *out)
{
    auto &q = *static_cast<Probe *>(p);
    if (algorithm) {
        q.new_candidate = q.regularized.evaluate(0, v, target, h);
        const auto &c = q.new_candidate;
        out[0] = c.s; out[1] = c.a_sta; out[2] = c.nu_before; out[3] = c.nu_next;
        return static_cast<int>(c.status);
    }
    q.old_candidate = q.legacy.evaluate(0, v, target, h);
    const auto &c = q.old_candidate;
    out[0] = c.s; out[1] = c.a_sta; out[2] = c.nu_before; out[3] = c.nu_next;
    return static_cast<int>(c.status);
}
int r01_commit(void *p, int algorithm, float applied)
{
    auto &q = *static_cast<Probe *>(p);
    return algorithm ? static_cast<int>(q.regularized.commitProtected(q.new_candidate, applied))
        : static_cast<int>(q.legacy.commitProtected(q.old_candidate, applied));
}
float r01_state(void *p, int algorithm)
{
    auto &q = *static_cast<Probe *>(p);
    return algorithm ? q.regularized.state()[0] : q.legacy.state()[0];
}
}
