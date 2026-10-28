// Read-only admission audit. Uses the existing production selector unchanged.
#include "VelocityControlSelector.hpp"
#include <cassert>
#include <iostream>

int main()
{
    VelocityControlSelector gate;
    assert(gate.effectiveMode()==0 && gate.effectiveAxes()==0);
    std::cout << "PASS default_pid\n";
    for (int axis=0; axis<=7; ++axis) {
        gate.configure(5,axis,false,true,axis,true,true);
        assert(gate.requestedMode()==5 && (gate.reject() & VelocityControlSelector::ModeRange));
        assert(gate.effectiveMode()==0 && gate.effectiveAxes()==0);
    }
    std::cout << "PASS mode5_all_masks_rejected\n";
    gate.configure(2,0,false,true,0,true,true);
    assert(gate.reject() & VelocityControlSelector::ModeUnimplemented);
    std::cout << "PASS mode2_still_reserved\n";
    for (int mode : {1,3,4}) {
        gate.configure(mode,1,false,true,1,true,true);
        assert(gate.reject()==0 && gate.effectiveMode()==mode && gate.effectiveAxes()==1);
        gate.configure(5,1,false,true,1,true,true);
        assert(gate.reject()!=0 && gate.effectiveMode()==mode);
    }
    std::cout << "PASS_existing_modes_not_overwritten\n";
    gate.configure(5,1,true,true,1,true,true);
    assert(gate.pending() && gate.reject()!=0 && gate.effectiveMode()==4);
    gate.configure(4,1,true,true,1,true,true);
    assert(!gate.pending() && gate.reject()==0);
    std::cout << "PASS armed_pending_cancellation\n";
    gate.configure(0,0,false);
    assert(gate.effectiveMode()==0 && gate.effectiveAxes()==0 && gate.reject()==0);
    std::cout << "PASS disarmed_pid\nTests run: 6, passed: 6, failed: 0\n";
}
