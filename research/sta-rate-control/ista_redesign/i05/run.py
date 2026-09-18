#!/usr/bin/env python3
import json, os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'scripts'))
from run_m00 import main
from run_m10 import Checks as M10Checks


def apply_remediation_divisor(remediation, job, config, setting):
    """Keep the configured and inherited M10 expected divisor identical."""
    if remediation == 'R-C':
        divisor = int(job['parameters']['MC_RTC_DIV'])
        config['MC_RTC_DIV'] = divisor
        setting['div'] = divisor


class Checks(M10Checks):
    allowed_modes=(1,3)
    def __init__(self):
        super().__init__()
        remediation=self.job.get('remediation_subgate')
        expected_axes=7 if remediation in ('R-B','R-C') else 3
        if self.job.get('subgate')!='A' or self.job['parameters']['MC_STA_AXES']!=expected_axes:
            raise ValueError('Unsupported I05 subgate/mask')
        self.protocol=self.job['flight_protocol']
        for name,value in self.protocol['scenario_parameters'].items(): self.config[name]=value
        # M10 maps a scenario name to its historical divisor. I05R-C freezes the
        # divisor per job instead, so restore both the command and preflight
        # expectation after the inherited setup.
        apply_remediation_divisor(remediation, self.job, self.config, self.setting)

if __name__=='__main__': main(checks=Checks(),scenario_path=Path(__file__))
