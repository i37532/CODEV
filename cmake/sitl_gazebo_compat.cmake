# PX4-SITL_gazebo builds gazebo_user_camera_plugin even when the optional
# GStreamer plugins are disabled. Load the Qt5 build helpers unconditionally
# so QT5_WRAP_CPP is available on Ubuntu 22.04 with Gazebo Classic 11.
find_package(Qt5 COMPONENTS Core Widgets Test REQUIRED)
