# M00 PID reference fixture

`M00RateControl.cpp/.hpp` freeze `RateControl.cpp/.hpp` at commit
`9a0ed8e9f9be5040cea1893bc8129959cdc65478` (same controller as the original
`9a3c4e3625474ce7fd2cd5c9687933ccf6a70bc7` source baseline).

Only the standalone `RateControl` class/include identifier is renamed to
`M00RateControl`, with two provenance comment lines added. Method names and
floating-point operation order are unchanged. These files are linked only
into `unit-RateControlDispatcher`, never the flight firmware.

Keep this reference frozen when extending the production dispatcher. The
tests compare raw float bit patterns for all three outputs and integrator
states; `EXPECT_FLOAT_EQ` tolerances are deliberately not used. Deterministic
sequences cover both the unchanged default and rejected/pending requests,
nonzero feedforward, live gain/limit changes, saturation feedback (including
retained feedback), disarm and non-rotary-wing resets, landed/maybe_landed,
and intervals with rate control disabled. The original module's reset and
update ordering is replayed in the test; real uORB integration is separately
checked by the M01 SITL scenario. This is finite regression coverage, not a
proof for every possible input or target toolchain.
