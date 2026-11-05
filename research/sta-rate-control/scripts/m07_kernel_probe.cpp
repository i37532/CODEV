// SPDX-License-Identifier: BSD-3-Clause
// Offline only: persistent production kernel, no simulator/vehicle transport.
#include "IstaRateControl.hpp"
#include <iomanip>
#include <iostream>

int main()
{
	IstaRateControl controller;
	size_t axis;
	float rate, sp, h, l1, l2, g, nu;
	int reset;
	std::cout << std::setprecision(17);

	while (std::cin >> axis >> rate >> sp >> h >> l1 >> l2 >> g >> reset >> nu) {
		if (!controller.setParameters(axis, {l1, l2, g}) || (reset && !controller.reset(axis, nu))) { return 2; }

		const float old = controller.state()[axis];
		const auto r = controller.update(axis, rate, sp, h);
		std::cout << static_cast<int>(r.status) << ' ' << static_cast<int>(r.branch) << ' '
			  << old << ' ' << r.s << ' ' << r.a << ' ' << r.c_raw << ' ' << r.nu_next << ' '
			  << r.virtual_s << ' ' << r.xi << ' ' << controller.state()[axis] << std::endl;
	}

	return std::cin.eof() ? 0 : 3;
}
