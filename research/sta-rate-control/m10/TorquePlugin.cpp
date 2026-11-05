// Research-only Gazebo Classic plugin. Never linked into PX4 firmware.
#include <gazebo/gazebo.hh>
#include <gazebo/physics/physics.hh>
#include <gazebo/common/Events.hh>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <stdexcept>

namespace gazebo {
class M10Torque : public ModelPlugin {
    physics::LinkPtr link;
    event::ConnectionPtr connection;
    std::ofstream log;
    std::string trigger;
    double start{-1}, phase[3]{}, scale{0};
public:
    void Load(physics::ModelPtr model, sdf::ElementPtr sdf) override {
        link = model->GetLink("base_link");
        if (!link) throw std::runtime_error("M10 requires Iris base_link");
        trigger = sdf->Get<std::string>("trigger");
        scale = sdf->Get<double>("scale");
        for (int i=0;i<3;++i) phase[i] = sdf->Get<double>("phase"+std::to_string(i));
        log.open(sdf->Get<std::string>("log"));
        if (!log) throw std::runtime_error("Cannot record M10 torque");
        log << "sim_s,elapsed_s,tx_Nm,ty_Nm,tz_Nm\n" << std::setprecision(17);
        connection = event::Events::ConnectWorldUpdateBegin([this](const common::UpdateInfo &info) {
            const double now = info.simTime.Double();
            if (start < 0) {
                // Explicit controller sample-time origin, not host file-read
                // time. The disturbance has a 2 s zero prefix to absorb CLI
                // transport latency without changing its physical phase.
                std::ifstream input(trigger);
                double origin;
                if (input >> origin) {
                    if (!std::isfinite(origin) || origin < 0 || origin > now || now-origin >= 2)
                        throw std::runtime_error("M10 trigger origin invalid/too late");
                    start = origin;
                }
            }
            const double t = start < 0 ? -1 : now-start;
            ignition::math::Vector3d torque(0,0,0);
            // Compact C1 bump [2,12] s; both value and slope vanish at ends.
            if (t >= 2 && t <= 12) {
                const double envelope = std::pow(std::sin(M_PI*(t-2)/10),2);
                const double amplitudes[3]{.004,.004,.002};
                for (int i=0;i<3;++i)
                    torque[i] = scale*amplitudes[i]*envelope*std::sin(2*M_PI*.4*(t-2)+phase[i]);
            }
            link->AddRelativeTorque(torque); // Gazebo FLU body axes, physical N m.
            log << now << ',' << t << ',' << torque.X() << ',' << torque.Y() << ',' << torque.Z() << '\n';
            // Launcher terminates gzserver without destructors: flush each step.
            log.flush();
        });
    }
};
GZ_REGISTER_MODEL_PLUGIN(M10Torque)
}
