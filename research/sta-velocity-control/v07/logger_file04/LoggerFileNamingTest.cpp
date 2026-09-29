// SPDX-License-Identifier: BSD-3-Clause
// Offline production-code probe; compile with -fno-access-control, no flight.
#define MODULE_NAME "logger_file_probe"
#define PX4_BOARD_NAME "logger_file_probe"
#include <gtest/gtest.h>
#include "logger.h"
#include <uORB/Publication.hpp>
#include <uORB/topics/vehicle_gps_position.h>
#include <fstream>
#include <memory>
#include <string>
#include <unistd.h>
#include <sys/stat.h>
using namespace px4::logger;

class LoggerFileNaming : public ::testing::Test
{
protected:
	void SetUp() override {
		ASSERT_STREQ(PX4_STORAGEDIR, ".");
		ASSERT_NE(getcwd(_before, sizeof(_before)), nullptr);
		char temporary[] = "/tmp/v07-logger-file-XXXXXX";
		char *path = mkdtemp(temporary);
		ASSERT_NE(path, nullptr);
		printf("Owned offline fixture: %s\n", path);
		ASSERT_EQ(chdir(path), 0);
		ASSERT_EQ(mkdir("log", 0700), 0);
	}
	void TearDown() override { EXPECT_EQ(chdir(_before), 0); }
	void write(const char *path, const char *value) { std::ofstream f(path); f << value; ASSERT_TRUE(f.good()); }
	std::string read(const char *path) { std::ifstream f(path); return std::string(std::istreambuf_iterator<char>(f), {}); }
	char _before[4096]{};
};

TEST_F(LoggerFileNaming, ActualCliWithoutTimestampFlagSelectsSessionNaming)
{
	char name[]="logger", b[]="-b", size[]="256", r[]="-r", hz[]="1000", f[]="-f";
	char *argv[]={name,b,size,r,hz,f,nullptr};
	std::unique_ptr<Logger> logger(Logger::instantiate(6,argv));
	ASSERT_NE(logger,nullptr);
	EXPECT_FALSE(logger->_log_name_timestamp);
	EXPECT_EQ(logger->_log_interval,1000u);
	EXPECT_EQ(logger->_log_mode,Logger::LogMode::boot_until_shutdown);
}

TEST_F(LoggerFileNaming, RestartCreatesDistinctSessionAndPreservesOldBytes)
{
	char first[128]{}, second[128]{};
	{
		Logger logger(LogWriter::BackendFile,4096,1000,nullptr,Logger::LogMode::boot_until_shutdown,false);
		ASSERT_EQ(logger.get_log_file_name(LogType::Full,first,sizeof(first)),0);
		write(first,"old ULog bytes");
	}
	{
		Logger logger(LogWriter::BackendFile,4096,1000,nullptr,Logger::LogMode::boot_until_shutdown,false);
		ASSERT_EQ(logger.get_log_file_name(LogType::Full,second,sizeof(second)),0);
		write(second,"new ULog bytes");
	}
	EXPECT_STREQ(first,"./log/sess001/log001.ulg");
	EXPECT_STREQ(second,"./log/sess002/log001.ulg");
	EXPECT_EQ(read(first),"old ULog bytes");
	EXPECT_EQ(read(second),"new ULog bytes");
}

TEST_F(LoggerFileNaming, RepeatedFileInOneSessionSkipsExistingName)
{
	Logger logger(LogWriter::BackendFile,4096,1000,nullptr,Logger::LogMode::boot_until_shutdown,false);
	char first[128]{}, second[128]{};
	ASSERT_EQ(logger.get_log_file_name(LogType::Full,first,sizeof(first)),0);
	write(first,"retained");
	ASSERT_EQ(logger.get_log_file_name(LogType::Full,second,sizeof(second)),0);
	EXPECT_STREQ(second,"./log/sess001/log002.ulg");
	EXPECT_EQ(read(first),"retained");
}

TEST_F(LoggerFileNaming, SameGpsSecondReproducesTimestampNameCollision)
{
	uORB::Publication<vehicle_gps_position_s> pub{ORB_ID(vehicle_gps_position)};
	vehicle_gps_position_s gps{}; gps.timestamp=1; gps.fix_type=3; gps.time_utc_usec=1790653930000000ULL;
	pub.publish(gps);
	char first[128]{}, second[128]{};
	{
		Logger logger(LogWriter::BackendFile,4096,1000,nullptr,Logger::LogMode::boot_until_shutdown,true);
		ASSERT_EQ(logger.get_log_file_name(LogType::Full,first,sizeof(first)),0);
		write(first,"retained demonstration");
	}
	{
		Logger logger(LogWriter::BackendFile,4096,1000,nullptr,Logger::LogMode::boot_until_shutdown,true);
		ASSERT_EQ(logger.get_log_file_name(LogType::Full,second,sizeof(second)),0);
	}
	EXPECT_STREQ(first,second); // Existing -t behavior, not a desired safety property.
	EXPECT_EQ(read(first),"retained demonstration"); // Probe itself never overwrites.
}
