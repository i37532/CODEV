// V08 standalone Gazebo Classic experiment plugin, not an onboard controller.
#include "ForceWave.hpp"
#include <gazebo/gazebo.hh>
#include <gazebo/physics/physics.hh>
#include <gazebo/common/Events.hh>
#include <fstream>
#include <iomanip>
#include <set>

namespace gazebo {
class V08Force : public ModelPlugin {
    physics::ModelPtr model;
    physics::LinkPtr base;
    event::ConnectionPtr connection;
    std::ofstream log;
    std::string trigger, model_audit;
    double start{-1}, north_phase{}, east_phase{};
    bool enabled{}, audited{};
    void audit(physics::ModelPtr current, std::ofstream &out, std::set<std::string> &seen) {
        for (const auto &link: current->GetLinks()) {
            if (!seen.insert(link->GetScopedName()).second) continue;
            const auto inertial=link->GetInertial();
            const auto pose=model->WorldPose().Inverse()*link->WorldCoGPose();
            out << link->GetScopedName() << ',' << inertial->Mass() << ','
                << inertial->IXX() << ',' << inertial->IYY() << ',' << inertial->IZZ() << ','
                << inertial->IXY() << ',' << inertial->IXZ() << ',' << inertial->IYZ() << ','
                << pose.Pos().X() << ',' << pose.Pos().Y() << ',' << pose.Pos().Z() << '\n';
        }
        for (const auto &nested:current->NestedModels()) audit(nested,out,seen);
    }
public:
    ~V08Force() override {
        connection.reset();
        log.flush();
        log.close();
    }
    void Load(physics::ModelPtr m, sdf::ElementPtr sdf) override {
        model=m; base=model->GetLink("base_link");
        if (!base) throw std::runtime_error("V08 requires Iris base_link");
        trigger=sdf->Get<std::string>("trigger");model_audit=sdf->Get<std::string>("model_audit");
        enabled=sdf->Get<bool>("force_enabled");
        north_phase=sdf->Get<double>("north_phase");east_phase=sdf->Get<double>("east_phase");
        v08::force_enu(0.,north_phase,east_phase); // reject invalid phases even when disabled
        log.open(sdf->Get<std::string>("log"));
        if (!log) throw std::runtime_error("Cannot open V08 force log");
        log << "sim_s,elapsed_s,fx_enu_N,fy_enu_N,fz_enu_N\n" << std::setprecision(17);
        connection=event::Events::ConnectWorldUpdateBegin([this](const common::UpdateInfo &info) {
            const double now=info.simTime.Double();
            if (!audited) {
                std::ofstream out(model_audit);
                if (!out) throw std::runtime_error("Cannot audit loaded V08 model");
                out << "link,mass_kg,ixx,iyy,izz,ixy,ixz,iyz,cog_model_x,cog_model_y,cog_model_z\n" << std::setprecision(17);
                std::set<std::string> seen; audit(model,out,seen);out.flush();
                if (seen.size()!=7) throw std::runtime_error("V08 actual Iris link count differs (GPS required)");
                audited=true;
            }
            if (start<0) {
                std::ifstream input(trigger); double origin;
                if (input>>origin) {
                    if (!std::isfinite(origin) || origin<0 || origin>now || now-origin>=2.)
                        throw std::runtime_error("Invalid/late V08 sample-clock trigger");
                    start=origin;
                }
            }
            const double elapsed=start<0 ? -1. : now-start;
            const auto force=enabled ? v08::force_enu(elapsed,north_phase,east_phase) : std::array<double,3>{{0.,0.,0.}};
            base->AddForce(ignition::math::Vector3d(force[0],force[1],force[2]));
            log << now << ',' << elapsed << ',' << force[0] << ',' << force[1] << ',' << force[2] << '\n';
            log.flush();
        });
    }
};
GZ_REGISTER_MODEL_PLUGIN(V08Force)
}
