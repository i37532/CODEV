#!/usr/bin/env python3
import json, os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'scripts'))
from run_m00 import main
from run_m10 import Checks as M10Checks

class Checks(M10Checks):
    allowed_modes=(1,3)
    def __init__(self):
        super().__init__()
        remediation=self.job.get('remediation_subgate')
        expected_axes=7 if remediation=='R-B' else 3
        if self.job.get('subgate')!='A' or self.job['parameters']['MC_STA_AXES']!=expected_axes:
            raise ValueError('Unsupported I05 subgate/mask')
        self.protocol=self.job['flight_protocol']
        for name,value in self.protocol['scenario_parameters'].items(): self.config[name]=value

if __name__=='__main__': main(checks=Checks(),scenario_path=Path(__file__))
