#!/usr/bin/env python3
from cereal import car, arne182
from selfdrive.car.chrysler.values import Ecu, ECU_FINGERPRINT, CAR, FINGERPRINTS
from selfdrive.car import STD_CARGO_KG, scale_rot_inertia, scale_tire_stiffness, is_ecu_disconnected, gen_empty_fingerprint
from selfdrive.car.interfaces import CarInterfaceBase

class CarInterface(CarInterfaceBase):
  @staticmethod
  def compute_gb(accel, speed):
    return float(accel) / 3.0

  @staticmethod
  def get_params(candidate, fingerprint=None, has_relay=False, car_fw=None):
    if fingerprint is None:
      fingerprint = gen_empty_fingerprint()
    if car_fw is None:
      car_fw = []

    ret = CarInterfaceBase.get_std_params(candidate, fingerprint, has_relay)
    ret.carName = "chrysler"
    ret.safetyModel = car.CarParams.SafetyModel.chrysler

    # Chrysler port is a community feature, since we don't own one to test
    ret.communityFeature = True

    # Speed conversion:              20, 45 mph
    ret.wheelbase = 3.089  # in meters for Pacifica Hybrid 2017
    ret.steerRatio = 16.2  # Pacifica Hybrid 2017
    ret.mass = 1964. + STD_CARGO_KG  # kg curb weight Pacifica 2017
    #pidscale = 0.12
    #ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kfBP = [[9. * pidscale, 20. * pidscale], [9. * pidscale, 20. * pidscale], [0.]]
    #ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV, ret.lateralTuning.pid.kfV = [[0.15 * pidscale,0.30 * pidscale], [0.03 * pidscale,0.05 * pidscale], [0.00006 * pidscale]] # full torque for 10 deg at 80mph means 0.00007818594
    #ret.lateralTuning.pid.kdBP, ret.lateralTuning.pid.kdV = [[0.], [0.1]]
    
    ret.steerActuatorDelay =  0.02 #steer packet is sent every 20 ms
    ret.steerRateCost = 0.002
    ret.steerLimitTimer = 0.8
    ret.lateralTuning.init('indi')
    ret.lateralTuning.indi.innerLoopGain = 1.0
    ret.lateralTuning.indi.outerLoopGainV = [1.5] #V is the gain value to use when at that speed
    ret.lateralTuning.indi.outerLoopGainBP = [0] #BP is the vehicle speed in m/sec
    ret.lateralTuning.indi.timeConstant = 1.0
    ret.lateralTuning.indi.actuatorEffectiveness = 30.0

    if candidate in (CAR.JEEP_CHEROKEE_2017, CAR.JEEP_CHEROKEE_2018, CAR.JEEP_CHEROKEE_2019):
      ret.wheelbase = 2.91  # in meters
      ret.steerRatio = 12.7
      ret.steerActuatorDelay = 0.2  # in seconds

    ret.centerToFront = ret.wheelbase * 0.44
    
    if candidate in (CAR.CHRYSLER_300_2018):
      ret.wheelbase = 3.05308 # in meters
      ret.steerRatio = 15.5 # 2013 V-6 (RWD) — 15.5:1 V-6 (AWD) — 16.5:1 V-8 (RWD) — 15.5:1 V-8 (AWD) — 16.5:1
      ret.mass = 1828.0 + STD_CARGO_KG # 2013 V-6 RWD
      # ret.lateralTuning.pid.kf = 0.00006   # full torque for 10 deg at 80mph means 0.00007818594
      #ret.steerActuatorDelay =  0.1
      ret.steerRateCost = 0.02
      ret.steerLimitTimer = 0.8
      ret.lateralTuning.init('indi')
      ret.lateralTuning.indi.innerLoopGain = 1.92
      ret.lateralTuning.indi.outerLoopGain = 0.78
      ret.lateralTuning.indi.timeConstant = 10.0
      ret.lateralTuning.indi.actuatorEffectiveness = 1.35

    ret.minSteerSpeed = 3.8  # m/s
    if candidate in (CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2020, CAR.JEEP_CHEROKEE_2019):
      # TODO allow 2019 cars to steer down to 13 m/s if already engaged.
      ret.minSteerSpeed = 17.5  # m/s 17 on the way up, 13 on the way down once engaged.

    # starting with reasonable value for civic and scaling by mass and wheelbase
    ret.rotationalInertia = scale_rot_inertia(ret.mass, ret.wheelbase)

    # TODO: start from empirically derived lateral slip stiffness for the civic and scale by
    # mass and CG position, so all cars will have approximately similar dyn behaviors
    ret.tireStiffnessFront, ret.tireStiffnessRear = scale_tire_stiffness(ret.mass, ret.wheelbase, ret.centerToFront)

    ret.enableCamera = is_ecu_disconnected(fingerprint[0], FINGERPRINTS, ECU_FINGERPRINT, candidate, Ecu.fwdCamera) or has_relay
    print("ECU Camera Simulated: {0}".format(ret.enableCamera))

    return ret

  # returns a car.CarState
  def update(self, c, can_strings):
    # ******************* do can recv *******************
    self.cp.update_strings(can_strings)
    self.cp_cam.update_strings(can_strings)

    ret = self.CS.update(self.cp, self.cp_cam)
    ret_arne182 = arne182.CarStateArne182.new_message()

    ret.canValid = self.cp.can_valid and self.cp_cam.can_valid

    # speeds
    ret.steeringRateLimited = self.CC.steer_rate_limited if self.CC is not None else False

    ret.buttonEvents = []

    # events

    events, events_arne182 = self.create_common_events(ret, extra_gears=[car.CarState.GearShifter.low], gas_resume_speed = 2.)

    if ret.vEgo < self.CP.minSteerSpeed:
      events.add(car.CarEvent.EventName.belowSteerSpeed)


    ret.events = events.to_msg()

    ret_arne182.events = events_arne182.to_msg()

    # copy back carState packet to CS
    self.CS.out = ret.as_reader()

    return self.CS.out, ret_arne182.as_reader()


  # pass in a car.CarControl
  # to be called @ 100hz
  def apply(self, c):

    if (self.CS.frame == -1):
      return []  # if we haven't seen a frame 220, then do not update.

    can_sends = self.CC.update(c.enabled, self.CS, c.actuators, c.cruiseControl.cancel, c.hudControl.visualAlert)

    return can_sends
