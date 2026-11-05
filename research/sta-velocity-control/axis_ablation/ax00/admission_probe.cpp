// AX00 audit only: links unchanged production selector/protection/kernel.
// Does not instantiate a PX4 module, change parameters, or command a vehicle.
#include "VelocityControlSelector.hpp"
#include "StaVelocityProtection.hpp"
#include <cstdio>
#include <cstdlib>
#include <limits>

static int checks = 0;
static void check(bool ok, const char *name)
{
    ++checks;
    if (!ok) { std::fprintf(stderr, "FAIL %s\n", name); std::exit(1); }
}
static StaVelocityProtection::Config config(unsigned axes)
{
    StaVelocityProtection::Config c{};
    c.axes = axes;
    for (unsigned i = 0; i < 3; ++i) {
        c.gains[i] = {i == 2 ? 2.f : .5f, i == 2 ? 1.f : .1f};
        c.nu_limit[i] = i == 2 ? 4.f : .4f;
        c.acceleration_limit[i] = i == 2 ? 6.f : .8f;
    }
    return c;
}
int main()
{
    for (unsigned axes = 0; axes < 8; ++axes) {
        const bool allowed = axes == 0 || axes == 1 || axes == 3 || axes == 4 || axes == 7;
        VelocityControlSelector s;
        s.configure(axes ? 1 : 0, axes, false, true, axes);
        check((s.reject() == 0) == allowed, "selector admission");
        check(s.effectiveAxes() == static_cast<int32_t>(allowed ? axes : 0), "rejected request not effective");
        check(StaVelocityProtection::validConfig(config(axes)) == allowed, "guard admission");
        std::printf("mask=%u selector=%s protection=%s effective=%d\n", axes,
                    allowed ? "accept" : "reject", allowed ? "accept" : "reject", s.effectiveAxes());
    }
    for (int axes : {2, 5, 6}) {
        VelocityControlSelector s;
        s.configure(1, 7, false, true, 7);
        // Mirrors module's admitted X fallback while preserving original request.
        s.configure(1, axes, false, true, 1);
        check(s.reject() && s.effectiveAxes() == 7, "invalid mapped-X request retains previous XYZ");
        s.configure(1, axes, true, true, 1);
        check(s.pending() && s.effectiveAxes() == 7, "armed invalid request pending");
        s.configure(1, 7, true, true, 7);
        check(!s.pending() && !s.reject(), "cancel pending");
    }
    VelocityControlSelector s;
    s.configure(1, 1, true, true, 1);
    check(s.pending() && s.effectiveMode() == 0, "armed defers ESTA");
    s.configure(1, 1, false, true, 1);
    check(s.effectiveMode() == 1 && s.effectiveAxes() == 1, "disarm applies");
    s.configure(2, 0, false, true, 0);
    check(s.reject() && s.effectiveAxes() == 1, "ISTA reserved");
    s.configure(0, 0, false);
    check(s.effectiveMode() == 0 && s.effectiveAxes() == 0, "return PID");
    VelocityControlSelector fresh;
    check(fresh.effectiveMode() == 0 && fresh.effectiveAxes() == 0, "fresh selector default PID");

    for (unsigned axes : {1u, 3u, 4u, 7u}) {
        StaVelocityProtection p;
        check(p.configure(config(axes), false), "guard configure");
        StaVelocityProtection::Frame f{};
        f.sample = 1000000; f.armed = f.enabled = f.flying = true;
        f.landed = f.contact = false; f.velocity = {{.1f, -.1f, .1f}};
        check((p.begin(f).flags & StaVelocityProtection::Priming) != 0, "prime");
        f.sample += 10000;
        const auto proposal = p.begin(f);
        check(proposal.active_axes == axes && proposal.fault == 0, "independent active axes");
        const auto applied = p.finish(proposal.a_req, 0, true);
        check(applied.committed_axes == axes && applied.fault == 0, "one atomic selected commit");
        for (unsigned i = 0; i < 3; ++i) {
            check((axes & (1u << i)) ? p.state()[i] != 0.f : p.state()[i] == 0.f, "state isolation");
        }
        const auto before = p.state();
        check((p.begin(f).flags & StaVelocityProtection::Duplicate) != 0, "same sample duplicate");
        p.finish(proposal.a_req, 0, true);
        check(p.state() == before, "duplicate not reintegrated");
        f.sample += 10000;
        const auto next = p.begin(f);
        auto invalid = next.a_req;
        unsigned last = axes & 4 ? 2 : (axes & 2 ? 1 : 0);
        invalid[last] = std::numeric_limits<float>::quiet_NaN();
        const auto rejected = p.finish(invalid, axes, true);
        check(rejected.fault && rejected.committed_axes == 0 && p.state() == before,
              "last selected axis invalid: no partial commit");
        f.armed = false; f.sample += 10000;
        p.begin(f);
        check(p.state() == StaVelocityProtection::Vec{}, "disarm resets");
    }
    std::printf("PASS %d assertions; 8 admission masks; no module/flight\n", checks);
}
