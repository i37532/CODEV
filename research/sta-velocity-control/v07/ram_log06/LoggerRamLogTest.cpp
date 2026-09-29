// SPDX-License-Identifier: BSD-3-Clause
#define MODULE_NAME "ram_log_probe"
#define PX4_BOARD_NAME "ram_log_probe"
#include <gtest/gtest.h>
#include "logger.h"
#include <fstream>
#include <memory>
#include <string>
#include <unistd.h>
#include <sys/stat.h>
using namespace px4::logger;

class LoggerRamLog : public ::testing::Test
{
protected:
	void SetUp() override {
		char path[]="/dev/shm/px4-v07-XXXXXX";
		ASSERT_NE(mkdtemp(path),nullptr);_root=path;
		printf("Private tmpfs fixture retained: %s\n",_root.c_str());
		const char *old=getenv("PX4_SITL_LOG_DIR");_had=old!=nullptr;_old=old?old:"";
		ASSERT_EQ(unsetenv("PX4_SITL_LOG_DIR"),0);
	}
	void TearDown() override {
		if (_had) { EXPECT_EQ(setenv("PX4_SITL_LOG_DIR",_old.c_str(),1),0); }
		else { EXPECT_EQ(unsetenv("PX4_SITL_LOG_DIR"),0); }
	}
	std::unique_ptr<Logger> instantiate() {
		char name[]="logger",f[]="-f";char *argv[]={name,f,nullptr};
		return std::unique_ptr<Logger>(Logger::instantiate(2,argv));
	}
	std::string _root,_old;bool _had{false};
};

TEST_F(LoggerRamLog, DefaultRootUnchanged)
{
	auto logger=instantiate();ASSERT_NE(logger,nullptr);
	EXPECT_STREQ(logger->log_root(LogType::Full),"./log");
	EXPECT_STREQ(logger->log_root(LogType::Mission),"./mission_log");
}

TEST_F(LoggerRamLog, EnvironmentRedirectsOnlyFullLogAndSessionNaming)
{
	ASSERT_EQ(setenv("PX4_SITL_LOG_DIR",_root.c_str(),1),0);
	auto logger=instantiate();ASSERT_NE(logger,nullptr);
	EXPECT_STREQ(logger->log_root(LogType::Full),_root.c_str());
	EXPECT_STREQ(logger->log_root(LogType::Mission),"./mission_log");
	char filename[256]{};
	ASSERT_EQ(logger->get_log_file_name(LogType::Full,filename,sizeof(filename)),0);
	EXPECT_EQ(std::string(filename),_root+"/sess001/log001.ulg");
}

TEST_F(LoggerRamLog, InvalidEnvironmentDoesNotSilentlyFallback)
{
	for(const char *path : {"", ".", "/", "/tmp", "/dev/shm/px4-v07-missing-test", "/dev/shm/px4-v07-../bad"}) {
		ASSERT_EQ(setenv("PX4_SITL_LOG_DIR",path,1),0);
		EXPECT_EQ(instantiate(),nullptr);
	}
}

TEST_F(LoggerRamLog, PublicPermissionsAndSymlinkRejected)
{
	SitlResearchLogRoot root;
	ASSERT_TRUE(root.configure(_root.c_str()));
	ASSERT_EQ(chmod(_root.c_str(),0755),0);
	EXPECT_FALSE(root.configure(_root.c_str()));EXPECT_EQ(root.get(),nullptr);
	ASSERT_EQ(chmod(_root.c_str(),0700),0);
	const std::string link=_root+"-link";ASSERT_EQ(symlink(_root.c_str(),link.c_str()),0);
	EXPECT_FALSE(root.configure(link.c_str()));EXPECT_EQ(root.get(),nullptr);
}

TEST_F(LoggerRamLog, ActualWriterDrainsToPrivateTmpfsWithoutChangingFsyncCode)
{
	const std::string path=_root+"/probe.ulg";
	LogWriterFile writer(65536);ASSERT_TRUE(writer.init());ASSERT_EQ(writer.thread_start(),0);
	writer.start_log(LogType::Full,path.c_str());
	std::string payload(8192,'Q');
	writer.lock();const int result=writer.write_message(LogType::Full,&payload[0],payload.size(),0);writer.unlock();
	EXPECT_EQ(result,0);
	// Production logger notifies regularly. Do not stop before the new writer
	// has entered its _should_run loop (a one-shot condition signal can be lost).
	bool drained=false;
	for(int i=0;i<1000;++i) {
		writer.notify();
		writer.lock();drained=writer._buffers[0]._total_written==payload.size();writer.unlock();
		if(drained) { break; } usleep(1000);
	}
	EXPECT_TRUE(drained);writer.stop_log(LogType::Full);
	bool closed=false;
	for(int i=0;i<1000;++i) {
		writer.lock();closed=writer._buffers[0].fd()<0;writer.unlock();
		if(closed) { break; } writer.notify();usleep(1000);
	}
	writer.thread_stop();ASSERT_TRUE(closed);
	std::ifstream f(path);const std::string recorded(std::istreambuf_iterator<char>(f),{});
	EXPECT_EQ(recorded,payload);
}
