// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <cstring>
#include <cstdlib>
#include <limits.h>
#include <sys/stat.h>
#include <unistd.h>
#if defined(__linux__)
#include <sys/vfs.h>
#include <linux/magic.h>
#endif

// Opt-in Linux SITL evidence storage; never redirects normal or hardware logs.
// The runner owns a fresh private tmpfs directory, then archives after shutdown.
class SitlResearchLogRoot
{
public:
	bool configure(const char *path)
	{
		_path[0] = '\0';
#if defined(__linux__)
		constexpr const char prefix[] = "/dev/shm/px4-v07-";
		if (!path || strlen(path) >= sizeof(_path) || strlen(path) <= sizeof(prefix) - 1
		    || strncmp(path, prefix, sizeof(prefix) - 1) != 0) { return false; }
		for (const char *p = path + sizeof(prefix) - 1; *p; ++p) {
			if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z')
			      || (*p >= '0' && *p <= '9') || *p == '_' || *p == '-')) { return false; }
		}
		struct stat info{};
		struct statfs fs{};
		char canonical[PATH_MAX]{};
		if (lstat(path, &info) != 0 || !S_ISDIR(info.st_mode) || info.st_uid != geteuid()
		    || (info.st_mode & 0077) != 0 || !realpath(path, canonical) || strcmp(path, canonical) != 0
		    || statfs(path, &fs) != 0 || fs.f_type != TMPFS_MAGIC) { return false; }
		memcpy(_path, path, strlen(path) + 1);
		return true;
#else
		(void)path;
		return false;
#endif
	}
	const char *get() const { return _path[0] ? _path : nullptr; }
private:
	char _path[96]{};
};
