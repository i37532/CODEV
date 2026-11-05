#!/usr/bin/env python3
"""Archive offline source/real-log/wire evidence; never launch or change params."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
from pyulog import ULog
from pymavlink.dialects.v20 import common as mavlink
from v04_handoff06 import capture, send_once, project, f32
from v04_protocol05 import CONFIG, REPO


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    out=p.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False)
    record=json.loads((CONFIG.parent/'results05/run01.json').read_text())
    source=Path(record['logs'][-1]['archive'])
    if digest(source)!=record['logs'][-1]['sha256']:raise ValueError('Old ULog changed')
    log=ULog(str(source));ref=json.loads((source.parent/'height_reference.json').read_text())
    frozen=json.loads((source.parent/'task_yaw.json').read_text())
    t=capture(log,ref,frozen,38096000)
    sink=io.BytesIO();encoder=mavlink.MAVLink(sink,srcSystem=255,srcComponent=190)
    send_once(encoder,t)
    packet=sink.getvalue();decoded=mavlink.MAVLink(None).parse_char(packet)
    if decoded.x!=t['wire']['x'] or decoded.y!=t['wire']['y'] or decoded.frame!=5:raise ValueError('Wire mismatch')
    # Describe why global float32 coordinates in COMMAND_LONG are inappropriate here.
    hypothetical=project(ref['position']['ref_lat'],ref['position']['ref_lon'],f32(t['lat']),f32(t['lon']))
    source_paths=['src/modules/navigator/navigator_main.cpp','src/modules/navigator/loiter.cpp',
        'src/modules/mavlink/mavlink_receiver.cpp','src/modules/commander/Commander.cpp',
        'src/modules/flight_mode_manager/tasks/Auto/FlightTaskAuto.cpp','src/lib/ecl/geo/geo.cpp',
        'src/lib/ecl/geo/geo.h','msg/position_setpoint.msg',
        'build/px4_sitl_test/src/lib/ecl/geo/libecl_geo.a',
        'research/sta-velocity-control/v04/handoff06/ProjectionWireProbe.cpp']
    evidence=dict(kind='offline_only',new_flights=0,new_seeds=0,
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        source_hashes={name:digest(REPO/name) for name in source_paths},
        old_ulog=dict(path=str(source),sha256=digest(source),original_accepted=False,acceptance_changed=False),
        target=t,packet_hex=packet.hex(),decoded=decoded.to_dict(),
        hypothetical_command_long_xy=list(hypothetical),
        hypothetical_command_long_error_m=((hypothetical[0]-t['source_xy'][0])**2+(hypothetical[1]-t['source_xy'][1])**2)**.5,
        original_parameter_sha256=digest(REPO/'build/px4_sitl_default/tmp/rootfs/eeprom/parameters_10016'),
        limitations=['Real precommand replay only; no historical successful handoff exists',
                    'Synthetic postcommand responses do not instantiate Navigator/Commander/FlightTask or test live scheduling',
                    'NaN XY can trigger FlightTaskAuto local lock; not proof of a failsafe, but does not preserve the old hold target',
                    'No current flight authority, batch runner, new seeds or execution snapshot'],success=True)
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':main()
