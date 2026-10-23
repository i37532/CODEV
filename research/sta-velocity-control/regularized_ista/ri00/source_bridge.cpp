// RI00 audit-only bridge to the ORIGINAL uploaded header; no PX4 registration.
#include "velocity_sta_ista.hpp"
#include "VelocityControlSelector.hpp"
#include <limits>
using namespace velocity_control;

template<class T> void call(const double *x, double *y)
{
    Parameters<T> p{T(x[0]),T(x[1]),T(x[2]),T(x[3]),T(x[4]),T(x[5])};
    State<T> state{T(x[7])};
    auto q=propose(Algorithm::ISTA,p,state,Input<T>{T(-x[6]),T(x[8]),T(x[9])});
    y[0]=int(q.status); y[1]=-double(q.predicted_error);
    y[2]=q.acceleration_raw; y[3]=q.nu_candidate; y[4]=q.acceleration_limited;
    commit(state,q,x[10]!=0);
    y[5]=state.nu; y[6]=q.integration_frozen_local; y[7]=q.state_limited;
}
extern "C" void source_float(const double *x,double *y) { call<float>(x,y); }
extern "C" void source_double(const double *x,double *y) { call<double>(x,y); }
extern "C" int source_weak_commit(int which)
{
    Parameters<float> p{.5f,.1f,.01f,-10.f,10.f,10.f};
    State<float> a,b;
    auto q=propose(Algorithm::ISTA,p,a,Input<float>{.1f,0.f,.008f});
    if (which==0) { return commit(b,q); } // foreign owner, same nu
    if (which==1) { a.reset(); return commit(a,q); } // reset to same value
    q.nu_next=.25f; return commit(a,q); // mutable payload
}
extern "C" int selector_rejects_mode4()
{
    VelocityControlSelector s;
    s.configure(4,1,false,true,1,true);
    return s.effectiveMode()==0 && (s.reject() & VelocityControlSelector::ModeRange);
}
