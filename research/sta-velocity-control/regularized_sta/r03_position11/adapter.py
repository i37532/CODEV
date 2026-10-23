"""Private, hash-bound position-clock bindings; old sources remain unchanged.

This module supplies offline/prospective components, never flight authority.
Every AST substitution must match exactly once. Numerical safety predicates,
non-position clocks and state/update semantics are retained.
"""
import ast
import copy
import hashlib
import importlib.util
import inspect
from pathlib import Path
import types

import numpy as np

HERE=Path(__file__).resolve().parent
RESEARCH=HERE.parents[1]
SCRIPTS=RESEARCH/'scripts'
LEGACY=RESEARCH/'v08/protocol02'
PINS={
    SCRIPTS/'v04_heading_stream.py':'0d23ea43e95968aeb86529ce073aa85d9a99f8a07c006349654d6744adeb0db3',
    SCRIPTS/'v04_live_clock09.py':'74d7e97d04faeab285691eede9424c02cb26dedb637111dae93d701f707e8a09',
    SCRIPTS/'v04_prearm17.py':'74b851f57752e09a1f493d6ba591013fd6ea4d9b8f247717d095a5e7c3fb58fa',
    LEGACY/'position_log.py':'5e1fe7caa0d6f377196f3e684fa3ef77ca0f692df494448f32f983c369af40ae',
    LEGACY/'baseline.py':'9c66099b1bd11e422c21b505db526469ed47a58e327d6d53b5a872687d6d729b',
    LEGACY/'monitor.py':'da51a4aadb04f77f482bf4da9e262ae76b092e236c611d721db2fbc35cdfc8f2',
    LEGACY/'handoff_capture.py':'7994a2fbcbfdee497cb9a14a8c7d25887ff7eabdcd267fd8c4f91db2398c78bf',
    RESEARCH/'axis_ablation/ax04/run.py':'b73f9ccc6d0057cf0ce622d4c3c4d26a7765b38ab1174ede5801bb2d49199d79',
}


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name,path):
    if path in PINS and digest(path)!=PINS[path]: raise ValueError('Position11 frozen dependency changed: '+str(path))
    spec=importlib.util.spec_from_file_location('_position11_'+name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


policy=load('policy',HERE/'policy.py')
callbacks=load('callbacks',HERE/'callbacks.py')


def clone(function,**overrides):
    result=types.FunctionType(function.__code__,dict(function.__globals__,**overrides),function.__name__,
        function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__
    return result


def rewrite(function,replacements,**overrides):
    """Pinned source, named exact replacements; not a broad comparison rewrite."""
    path=Path(inspect.getsourcefile(function)).resolve()
    if path in PINS and digest(path)!=PINS[path]: raise ValueError('Changed position dependency')
    tree=ast.parse(path.read_text())
    nodes=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==function.__name__]
    if len(nodes)!=1: raise ValueError('Missing unique function '+function.__name__)
    tree=copy.deepcopy(nodes[0])
    proof=[]
    for before,after,expression in replacements:
        def parse(s): return ast.parse(s,mode='eval').body if expression else ast.parse(s).body[0]
        old,new=parse(before),parse(after)
        class Replace(ast.NodeTransformer):
            count=0
            def generic_visit(self,node):
                if ast.dump(node,include_attributes=False)==ast.dump(old,include_attributes=False):
                    self.count+=1; return ast.copy_location(copy.deepcopy(new),node)
                return super().generic_visit(node)
        replace=Replace(); tree=replace.visit(tree)
        if replace.count!=1: raise ValueError('Position11 replacement count '+str(replace.count)+': '+before)
        proof.append(dict(before=before,after=after,expression=expression))
    namespace=dict(function.__globals__,**overrides)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[tree],type_ignores=[])),str(path),'exec'),namespace)
    result=namespace[function.__name__]
    result.position11_changes=proof
    return result


def build_heading():
    module=load('heading',SCRIPTS/'v04_heading_stream.py')
    replay=rewrite(module.replay,[
        ("span(pos,start,end)","position_policy.reference_window(pos,ref['position'],end)",True),
        ("np.any(gaps<=0)","np.any(gaps < 0) if k == 'timestamp' else np.any(gaps <= 0)",True),
        ("np.searchsorted(pos['timestamp'],diag['input_timestamp'][consumed])",
         "position_policy.exact_indices(pos,diag['input_timestamp'][consumed],diag['timestamp_sample'][consumed])",True),
        ("np.flatnonzero(times==frozen['timestamp'])",
         "np.flatnonzero((times==frozen['timestamp']) & (pos['timestamp_sample'][ix]==frozen['timestamp_sample']))",True),
        ("(t-int(pos['timestamp'][before]))*1e-6",
         "(int(pos['timestamp_sample'][i])-int(pos['timestamp_sample'][before]))*1e-6",True),
    ],data=policy.data,position_policy=policy)
    live=load('live',SCRIPTS/'v04_live_clock09.py')
    sealed=rewrite(live.sealed_time,[("int(a['timestamp'][-1])",
        "min(int(a['timestamp'][-1]),int(pos['timestamp'][-1]))",True)],data=policy.data)
    live_replay=clone(live.replay,sealed_time=sealed,heading_replay=replay)
    prearm=load('prearm',SCRIPTS/'v04_prearm17.py')
    original_reference=clone(prearm.reference_row,data=policy.data,sealed_time=sealed)
    def reference(log):
        value=original_reference(log)
        policy.unique_at(policy.data(log,'vehicle_local_position'),value['timestamp'])
        return value
    # Prearm timing hook explicitly reads this global to record the watermark.
    reference=clone(reference,sealed_time=sealed)
    return types.SimpleNamespace(replay=replay,live_replay=live_replay,sealed_time=sealed,reference=reference)


def build_capture(heading):
    capture=load('capture',LEGACY/'handoff_capture.py')
    new_capture=clone(capture.capture,replay=heading.live_replay,data=policy.data)
    class Handoff(capture.Handoff):
        start=clone(capture.Handoff.start,capture=new_capture)
    return types.SimpleNamespace(capture=new_capture,Handoff=Handoff)


def bind_height(height,heading):
    handoff=height.__globals__['check_handoff']
    capture=build_capture(heading)
    new_handoff=clone(handoff,capture=capture.capture,data=policy.data)
    # height is the already privately bound handoff06 function. Keep its Nx3
    # reference and private globals; replace only the position publication test.
    new_height=rewrite(height,[("np.any(np.diff(pos['timestamp'][ix].astype(np.int64))<=0)",
        "np.any(np.diff(pos['timestamp'][ix].astype(np.int64))<0)",True),
        ("from task import offsets","pass",False)],
        replay=heading.replay,check_handoff=new_handoff)
    return new_height


def position_rates(d,mask):
    p,s=policy.validate(d); p,s=p[mask],s[mask]
    if len(p)<2: raise ValueError('Missing position rate window')
    def rates(t):
        gaps=np.diff(t)*1e-6
        return dict(n=len(t),hz=(len(t)-1)*1e6/(t[-1]-t[0]),dt_min_s=float(gaps.min()),
            dt_median_s=float(np.median(gaps)),dt_max_s=float(gaps.max()),dt_p95_s=float(np.percentile(gaps,95)))
    # Preserve the old publication summary shape; add separately named sample
    # diagnostics without changing any metric weights or coverage thresholds.
    return rates(p), bool(len(p)>=600 and np.max(np.diff(p))<=250000 and np.max(np.diff(s))<=250000)


def proxy_indices(log,pos,times):
    """Old latest-preceding proxy, with exact consumption for equality ties.

Later targets retain the old descriptive preceding-published convention. At
the tied publication itself, use the queued output diagnostic's two clocks;
missing/ambiguous output identity rejects rather than picking the last row.
"""
    p,s=policy.validate(pos)
    q=policy.clock(times)
    i=np.searchsorted(p,q,side='right')-1
    if np.any(i<0) or np.any(q-p[i]>20000): raise ValueError('Asynchronous pairing too old/missing')
    left=np.searchsorted(p,q,side='left'); right=np.searchsorted(p,q,side='right')
    ambiguous=np.flatnonzero(right-left>1)
    if len(ambiguous):
        d=log.get_dataset('sta_velocity_ctrl_status').data
        outputs=np.asarray(d['output_timestamp'])
        callbacks.validate(d)
        # Both output rows of a tied group must be requested; use the recorded
        # single-publisher order only after matching whole-group multiplicity.
        a,b=callbacks.grouped_indices(q,outputs)
        mapping=dict(zip(a.tolist(),b.tolist()))
        for k in ambiguous:
            if int(k) not in mapping: raise ValueError('Missing tied output callback')
            j=mapping[int(k)]
            i[k]=policy.exact_indices(pos,[d['input_timestamp'][j]],[d['timestamp_sample'][j]])[0]
            if p[i[k]]!=q[k]: raise ValueError('Output did not consume tied position group')
    return i,q-p[i]


def bind_baseline(module):
    original=module.analyze
    def analyze(run,protocol,*,attitude_policy=None):
        return rewrite(original,[
            ("if len(t) < 2 or np.any(np.diff(t) <= 0):\n    raise ValueError('Missing/nonmonotonic topic: ' + name)",
             "if len(t) < 2 or np.any(np.diff(t) < 0 if name in ('vehicle_local_position','vehicle_local_position_setpoint','vehicle_attitude_setpoint') else np.diff(t) <= 0):\n    raise ValueError('Missing/nonmonotonic topic: ' + name)",False),
            ("previous_indices(pos['timestamp'], times, 20000)","position_proxy_indices(log,pos,times)",True),
            ("previous_indices(ay['timestamp'], qd['timestamp'][mask(qd)], 20000)",
             "yaw_previous(ay,qd['timestamp'][mask(qd)],20000)",True),
            ("log.get_dataset('vehicle_local_position')","check_output_groups(log)",False),
        ],ULog=policy.ULog,CONFIG=module.CONFIG,position_proxy_indices=proxy_indices,
            yaw_previous=callbacks.yaw_previous,check_output_groups=check_output_groups)(run,protocol,attitude_policy=attitude_policy)
    module.analyze=analyze
    return module


def bind_analysis(function,**overrides):
    # The freshly loaded baseline module is private to this analyze invocation.
    return rewrite(function,[("bs.loader.exec_module(base_module)",
        "base_module = load_position_baseline(bs,base_module)",False)],
        ULog=policy.ULog,load_position_baseline=load_baseline,**overrides)


def load_baseline(spec,module):
    if Path(spec.origin).resolve()!=LEGACY/'baseline.py' or digest(Path(spec.origin))!=PINS[LEGACY/'baseline.py']:
        raise ValueError('Unexpected private baseline source')
    spec.loader.exec_module(module)
    return bind_baseline(module)


def check_output_groups(log):
    log.get_dataset('vehicle_local_position')
    d=log.get_dataset('sta_velocity_ctrl_status').data
    callbacks.validate(d)
    mask=(d['output_timestamp']>0)&(d['attitude_timestamp']>0)
    x={k:v[mask] for k,v in d.items()}
    if not len(x['timestamp']): raise ValueError('Missing callback outputs')
    for name,key,pairs in (
        ('vehicle_local_position_setpoint','output_timestamp',
         [(f'v_sp[{i}]',('vx','vy','vz')[i]) for i in range(3)]+
         [(f'a_req[{i}]',f'acceleration[{i}]') for i in range(3)]+[(f'thrust[{i}]',f'thrust[{i}]') for i in range(3)]),
        ('vehicle_attitude_setpoint','attitude_timestamp',[(f'q_sp[{i}]',f'q_d[{i}]') for i in range(4)])):
        target=log.get_dataset(name).data
        callbacks.exact_output_match(x,target,key,pairs,int(x['timestamp'][0]),int(x['timestamp'][-1])+1)


def build_attitude_policy():
    original=load('attitude',SCRIPTS/'v04_attitude_clock09.py').AttitudeClockPolicy
    safety=rewrite(original.safety,[("unique_previous(target['timestamp'], d['timestamp'][ix])",
        "yaw_previous(target,d['timestamp'][ix])",True)],yaw_previous=callbacks.yaw_previous)
    metrics=rewrite(original.yaw_metrics,[("unique_previous(target['timestamp'], p[m])",
        "yaw_previous(target,p[m])",True)],yaw_previous=callbacks.yaw_previous)
    return type('CallbackAttitudePolicy',(original,),{'safety':safety,'yaw_metrics':metrics})


def bind_components(r02,components):
    aligned=rewrite(r02.aligned,[("cp.strict_clock(data[name])","callback_clock(name,data[name])",False)],
        callback_clock=callbacks.callback_clock)
    private=types.SimpleNamespace(**vars(r02)); private.aligned=aligned
    return private,clone(components,r02=private)


def bind_targets(targets):
    position=rewrite(targets.check_position_sum,[
        ("strict_clock(pos['timestamp'])","publication(pos['timestamp'])",True),
        ("np.searchsorted(source, wanted)","position_policy.exact_indices(pos,wanted,x['timestamp_sample'])",True),
    ],position_policy=policy,publication=callbacks.publication)
    attitude=rewrite(targets.attitude_match,[
        ("from v04_attitude_clock09 import strict_clock, exact_output_match","pass",False),
        ("_, di, ai = np.intersect1d(wanted, source, return_indices=True)",
         "di, ai = grouped_indices(wanted,source)",False),
        ("'unique exact publication intersection'","'complete equal-time groups in single-publisher order; exact payload and callback identity'",True),
    ],strict_clock=callbacks.publication,exact_output_match=callbacks.exact_output_match,
        grouped_indices=callbacks.grouped_indices)
    return clone(targets.check_targets,check_position_sum=position,attitude_match=attitude)


def make_checks(prepared,heading):
    """New subclass, no mutation of the old MRO, imported globals or readers."""
    # Prearm04 has already bound the original AX04 constructor/read skeleton.
    # Its methods dispatch these explicit self hooks during the same lifecycle.
    source_phase=next(cls.__dict__['_phase_monitor'] for cls in prepared.__mro__ if '_phase_monitor' in cls.__dict__)
    source_monitor=next(cls.__dict__['monitor'] for cls in prepared.__mro__
        if 'monitor' in cls.__dict__ and Path(inspect.getsourcefile(cls.__dict__['monitor'])).resolve()==LEGACY/'monitor.py')
    source_ax04=next(cls.__dict__['monitor'] for cls in prepared.__mro__
        if 'monitor' in cls.__dict__ and Path(inspect.getsourcefile(cls.__dict__['monitor'])).resolve()==RESEARCH/'axis_ablation/ax04/run.py')
    parent=clone(source_monitor,replay=heading.live_replay)
    ax04=rewrite(source_ax04,[("parent=super().monitor","parent=self._position11_parent_monitor",False)])
    class Checks(prepared):
        _phase_monitor=clone(source_phase,replay=heading.live_replay)
        _position11_parent_monitor=parent
        _position11_ax04_monitor=ax04
        def _prearm_owned_reader(self,*,preparation):
            reader=super()._prearm_owned_reader(preparation=preparation)
            if reader is not None: reader.view=policy.PositionLogView
            return reader
        def _prearm_reference(self,log,function):
            return super()._prearm_reference(log,heading.reference)
        def _prearm_replay(self,log,ref,function):
            return super()._prearm_replay(log,ref,heading.live_replay)
        def monitor(self,phase,cli,topic,output,state):
            # Retain prearm04's measured monitor wrapper and reader accounting;
            # only its parent dispatch is rebound to the private AX04 copy.
            return private_monitor(self,phase,cli,topic,output,state)
    original_monitor=prepared.monitor
    # The prepared class may have a post-logger subclass with inherited monitor.
    # Rewrite its exact super call without copying any flight thresholds.
    private_monitor=rewrite(original_monitor,[(
        "super(PrearmPreparedChecks, self).monitor(phase, cli, self._prearm_topic(topic, receipt), output, state)",
        "self._position11_ax04_monitor(phase, cli, self._prearm_topic(topic, receipt), output, state)",True)])
    return Checks
