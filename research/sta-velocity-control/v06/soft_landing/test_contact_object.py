"""Independent unilateral 1-D object; not a Gazebo solver or flight proof."""
import math
import unittest
from contact_model import effective_contact


def trajectory(contacts, speed, thrust_fraction, dt):
    mass=1.535; c=effective_contact(); x=0.; v=speed; peak=0.; depth=0.
    def force(x,v):
        return contacts*max(0.,c['kp']*max(0.,x)+c['kd']*v) if x>=0 else 0.
    def derivative(x,v): return v,9.8066*(1-thrust_fraction)-force(x,v)/mass
    for _ in range(round(2/dt)):
        peak=max(peak,force(x,v)/mass); depth=max(depth,x)
        a,b=derivative(x,v); c1,d=derivative(x+dt*a/2,v+dt*b/2)
        e,f=derivative(x+dt*c1/2,v+dt*d/2); g,h=derivative(x+dt*e,v+dt*f)
        x+=dt*(a+2*c1+2*e+g)/6; v+=dt*(b+2*d+2*f+h)/6
        if not math.isfinite(x+v): raise ValueError('Nonfinite object')
    return peak,depth,abs(v)


class IndependentContactObject(unittest.TestCase):
    def test_one_two_four_contacts_speed_thrust_envelope(self):
        for contacts in (1,2,4):
            for speed in (.55,.7):
                for thrust in (0.,.5,.9):
                    with self.subTest(contacts=contacts,speed=speed,thrust=thrust):
                        coarse=trajectory(contacts,speed,thrust,.0002)
                        fine=trajectory(contacts,speed,thrust,.0001)
                        self.assertLess(fine[0],120); self.assertLess(fine[1],.02); self.assertLess(fine[2],.03)
                        for a,b in zip(coarse,fine): self.assertLess(abs(a-b),.002*max(1,abs(b)))


if __name__=='__main__': unittest.main()
