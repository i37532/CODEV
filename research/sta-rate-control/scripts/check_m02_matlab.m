function check_m02_matlab(jsonl_path, algorithms_path)
% Optional MATLAB check. Not evidence of execution until run successfully.
% Calls the independently reviewed esta_step.m; JSONL contains Python double
% reference inputs/outputs. C++ float conformance is separately tested by GTest.
    addpath(fullfile(algorithms_path, 'matlab'));
    rows = splitlines(strtrim(fileread(jsonl_path)));
    nu = [0.375, -0.625, 1.25];
    count = 0;
    for k = 1:numel(rows)
        r = jsondecode(rows{k});
        axis = r.axis + 1;
        assert(abs(nu(axis) - r.nu_old) < 1e-12);
        [a, next] = esta_step(r.rate - r.sp, nu(axis), r.lambda1, r.lambda2, r.dt);
        assert(abs(a - r.a) < 1e-12 * max(1, abs(r.a)));
        assert(abs(a / r.g - r.c) < 1e-12 * max(1, abs(r.c)));
        assert(abs(next - r.nu_next) < 1e-12);
        nu(axis) = next;
        count = count + 1;
    end
    assert(count == 96);
    fprintf('PASS: MATLAB esta_step checked %d samples\n', count);
end
