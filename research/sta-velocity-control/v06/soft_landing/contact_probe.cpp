// Passive Gazebo physics fixture. No PX4, motor/control or measurement filtering.
#include <gazebo/gazebo.hh>
#include <gazebo/physics/physics.hh>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>

int main(int argc, char **argv)
{
    if (argc != 5) { return 2; }
    const double speed = std::stod(argv[2]);
    const double roll = std::stod(argv[3]);
    if (!std::isfinite(speed) || speed <= 0. || !std::isfinite(roll)) { return 2; }
    gazebo::setupServer();
    auto world = gazebo::loadWorld(argv[1]);
    if (!world) { gazebo::shutdown(); return 3; }
    world->Physics()->SetSeed(26928);
    auto model = world->ModelByName("iris");
    if (!model) { gazebo::shutdown(); return 4; }
    auto body = model->GetLink("base_link");
    // Lowest box corner starts 2 mm above the ground; original 0.47 x 0.47 x .11.
    const double height = .235 * std::abs(std::sin(roll)) + .055 * std::cos(roll) + .002;
    model->SetWorldPose(ignition::math::Pose3d(0., 0., height, roll, 0., 0.));
    model->SetLinearVel(ignition::math::Vector3d(0., 0., -speed));
    std::ofstream stream(argv[4]);
    if (!stream) { gazebo::shutdown(); return 5; }
    stream << std::setprecision(17) << "t,x,y,z,vx,vy,vz,roll,pitch,yaw,fx,fy,fz,fdx,fdy,fdz,depth\n";
    auto previous = body->WorldLinearVel();
    world->SetPaused(true);
    world->Run();
    for (int i = 0; i < 500; ++i) {
        world->Step(1);
        const auto pose = body->WorldPose();
        const auto velocity = body->WorldLinearVel();
        const auto specific = pose.Rot().RotateVectorReverse(body->WorldLinearAccel() - world->Gravity());
        const auto difference = pose.Rot().RotateVectorReverse((velocity - previous) / .004 - world->Gravity());
        double depth = 0.;
        for (double x : {-.235, .235}) for (double y : {-.235, .235}) for (double z : {-.055, .055}) {
            const auto point = pose.Pos() + pose.Rot().RotateVector(ignition::math::Vector3d(x, y, z));
            depth = std::max(depth, -point.Z());
        }
        stream << world->SimTime().Double() << ',' << pose.Pos().X() << ',' << pose.Pos().Y() << ',' << pose.Pos().Z()
               << ',' << velocity.X() << ',' << velocity.Y() << ',' << velocity.Z()
               << ',' << pose.Rot().Roll() << ',' << pose.Rot().Pitch() << ',' << pose.Rot().Yaw()
               << ',' << specific.X() << ',' << specific.Y() << ',' << specific.Z()
               << ',' << difference.X() << ',' << difference.Y() << ',' << difference.Z() << ',' << depth << '\n';
        previous = velocity;
    }
    stream.close();
    world->Stop();
    gazebo::shutdown();
    return 0;
}
