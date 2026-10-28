// Research-only x86 floating-point environment wrapper. Not a controller.
#include <xmmintrin.h>
extern "C" int probe_evaluate(void *, int, float, float, float, double *);
extern "C" int probe_reset(void *, int, float);
extern int pv_reject_site;
extern "C" int pv_site() { return pv_reject_site; }
extern "C" int pv_evaluate(void *obj, int axis, float v, float sp, float h, double *out, int flush)
{
    const unsigned saved = _mm_getcsr();
    // FTZ bit15 and DAZ bit6; preserve exception masks/rounding.
    _mm_setcsr(flush ? (saved | 0x8040U) : (saved & ~0x8040U));
    const int result = probe_evaluate(obj, axis, v, sp, h, out);
    _mm_setcsr(saved);
    return result;
}
