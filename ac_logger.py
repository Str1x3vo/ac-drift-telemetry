"""
Assetto Corsa Telemetry Logger
Reads AC shared memory and logs to CSV for drift setup analysis.
Run this before/during an AC session. Press Ctrl+C to stop and save.
"""

import mmap
import ctypes
import struct
import csv
import math
import os
import json
import time
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")
os.makedirs(LOG_DIR, exist_ok=True)

# ── AC Shared Memory Layout ────────────────────────────────────────────────────

class ACPhysics(ctypes.Structure):
    _fields_ = [
        ("packetId",             ctypes.c_int),
        ("gas",                  ctypes.c_float),
        ("brake",                ctypes.c_float),
        ("fuel",                 ctypes.c_float),
        ("gear",                 ctypes.c_int),
        ("rpms",                 ctypes.c_int),
        ("steerAngle",           ctypes.c_float),
        ("speedKmh",             ctypes.c_float),
        ("velocity",             ctypes.c_float * 3),
        ("accG",                 ctypes.c_float * 3),
        ("wheelSlip",            ctypes.c_float * 4),
        ("wheelLoad",            ctypes.c_float * 4),
        ("wheelsPressure",       ctypes.c_float * 4),
        ("wheelAngularSpeed",    ctypes.c_float * 4),
        ("tyreWear",             ctypes.c_float * 4),
        ("tyreDirtyLevel",       ctypes.c_float * 4),
        ("tyreCoreTemperature",  ctypes.c_float * 4),
        ("camberRAD",            ctypes.c_float * 4),
        ("suspensionTravel",     ctypes.c_float * 4),
        ("drs",                  ctypes.c_float),
        ("tc",                   ctypes.c_float),
        ("heading",              ctypes.c_float),
        ("pitch",                ctypes.c_float),
        ("roll",                 ctypes.c_float),
        ("cgHeight",             ctypes.c_float),
        ("carDamage",            ctypes.c_float * 5),
        ("numberOfTyresOut",     ctypes.c_int),
        ("pitLimiterOn",         ctypes.c_int),
        ("abs",                  ctypes.c_float),
        ("kersCharge",           ctypes.c_float),
        ("kersInput",            ctypes.c_float),
        ("autoShifterOn",        ctypes.c_int),
        ("rideHeight",           ctypes.c_float * 2),
        ("turboBoost",           ctypes.c_float),
        ("ballast",              ctypes.c_float),
        ("airDensity",           ctypes.c_float),
        ("airTemp",              ctypes.c_float),
        ("roadTemp",             ctypes.c_float),
        ("localAngularVel",      ctypes.c_float * 3),
        ("finalFF",              ctypes.c_float),
        ("performanceMeter",     ctypes.c_float),
        ("engineBrake",          ctypes.c_int),
        ("ersRecoveryLevel",     ctypes.c_int),
        ("ersPowerLevel",        ctypes.c_int),
        ("ersHeatCharging",      ctypes.c_int),
        ("ersIsCharging",        ctypes.c_int),
        ("kersCurrentKJ",        ctypes.c_float),
        ("drsAvailable",         ctypes.c_int),
        ("drsEnabled",           ctypes.c_int),
        ("brakeTemp",            ctypes.c_float * 4),
        ("clutch",               ctypes.c_float),
        ("tyreTempI",            ctypes.c_float * 4),
        ("tyreTempM",            ctypes.c_float * 4),
        ("tyreTempO",            ctypes.c_float * 4),
        ("isAIControlled",       ctypes.c_int),
        ("tyreContactPoint",     ctypes.c_float * 12),
        ("tyreContactNormal",    ctypes.c_float * 12),
        ("tyreContactHeading",   ctypes.c_float * 12),
        ("brakeBias",            ctypes.c_float),
        ("localVelocity",        ctypes.c_float * 3),
    ]

class ACGraphics(ctypes.Structure):
    _fields_ = [
        ("packetId",             ctypes.c_int),
        ("status",               ctypes.c_int),   # 0=off 1=replay 2=live 3=pause
        ("session",              ctypes.c_int),
        ("currentTime",          ctypes.c_wchar * 15),
        ("lastTime",             ctypes.c_wchar * 15),
        ("bestTime",             ctypes.c_wchar * 15),
        ("split",                ctypes.c_wchar * 15),
        ("completedLaps",        ctypes.c_int),
        ("position",             ctypes.c_int),
        ("iCurrentTime",         ctypes.c_int),
        ("iLastTime",            ctypes.c_int),
        ("iBestTime",            ctypes.c_int),
        ("sessionTimeLeft",      ctypes.c_float),
        ("distanceTraveled",     ctypes.c_float),
        ("isInPit",              ctypes.c_int),
        ("currentSectorIndex",   ctypes.c_int),
        ("lastSectorTime",       ctypes.c_int),
        ("numberOfLaps",         ctypes.c_int),
        ("tyreCompound",         ctypes.c_wchar * 33),
        ("replayTimeMultiplier", ctypes.c_float),
        ("normalizedCarPosition",ctypes.c_float),
        ("activeCars",           ctypes.c_int),
        ("carCoordinates",       ctypes.c_float * 180),
        ("carID",                ctypes.c_int * 60),
        ("playerCarID",          ctypes.c_int),
        ("penaltyTime",          ctypes.c_float),
        ("flag",                 ctypes.c_int),
        ("penalty",              ctypes.c_int),
        ("idealLineOn",          ctypes.c_int),
        ("isInPitLane",          ctypes.c_int),
        ("surfaceGrip",          ctypes.c_float),
        ("mandatoryPitDone",     ctypes.c_int),
        ("windSpeed",            ctypes.c_float),
        ("windDirection",        ctypes.c_float),
    ]

class ACStatic(ctypes.Structure):
    _fields_ = [
        ("smVersion",            ctypes.c_wchar * 15),
        ("acVersion",            ctypes.c_wchar * 15),
        ("numberOfSessions",     ctypes.c_int),
        ("numCars",              ctypes.c_int),
        ("carModel",             ctypes.c_wchar * 33),
        ("track",                ctypes.c_wchar * 33),
        ("playerName",           ctypes.c_wchar * 33),
        ("playerSurname",        ctypes.c_wchar * 33),
        ("playerNick",           ctypes.c_wchar * 33),
        ("sectorCount",          ctypes.c_int),
        ("maxTorque",            ctypes.c_float),
        ("maxPower",             ctypes.c_float),
        ("maxRpm",               ctypes.c_int),
        ("maxFuel",              ctypes.c_float),
        ("suspensionMaxTravel",  ctypes.c_float * 4),
        ("tyreRadius",           ctypes.c_float * 4),
        ("maxTurboBoost",        ctypes.c_float),
    ]

# ── Shared Memory Reader ───────────────────────────────────────────────────────

def open_shm(name, size):
    try:
        return mmap.mmap(-1, size, tagname=name)
    except Exception:
        return None

def read_struct(shm, cls):
    if shm is None:
        return None
    shm.seek(0)
    buf = shm.read(ctypes.sizeof(cls))
    return cls.from_buffer_copy(buf)

# ── Calculations ───────────────────────────────────────────────────────────────

def sideslip_angle(phys):
    """Body sideslip angle in degrees — the drift angle."""
    vx = phys.localVelocity[0]  # lateral
    vz = phys.localVelocity[2]  # longitudinal
    if abs(vz) < 0.5:
        return 0.0
    return math.degrees(math.atan2(vx, vz))

def oversteer_index(phys):
    """
    Difference between front and rear slip.
    Positive = oversteer (rear slipping more than front).
    """
    front_slip = (phys.wheelSlip[0] + phys.wheelSlip[1]) / 2
    rear_slip  = (phys.wheelSlip[2] + phys.wheelSlip[3]) / 2
    return rear_slip - front_slip

def avg_tyre_temp(phys, axle):
    """Average of inner/mid/outer for FL=0 FR=1 RL=2 RR=3"""
    i = phys.tyreTempI[axle]
    m = phys.tyreTempM[axle]
    o = phys.tyreTempO[axle]
    return (i + m + o) / 3.0

# ── Console Display ────────────────────────────────────────────────────────────

WHEEL = ["FL", "FR", "RL", "RR"]

def clear_line():
    print("\r" + " " * 100 + "\r", end="")

def print_live(phys, gfx, elapsed):
    if phys is None or gfx is None:
        return
    slip_angle = sideslip_angle(phys)
    os_idx     = oversteer_index(phys)
    yaw        = math.degrees(phys.localAngularVel[1])
    temps_r    = [avg_tyre_temp(phys, i) for i in [2, 3]]

    status_map = {0: "OFF", 1: "REPLAY", 2: "LIVE", 3: "PAUSED"}
    status     = status_map.get(gfx.status, "?")

    line = (
        f"[{elapsed:6.1f}s] {status:6s} | "
        f"SPD {phys.speedKmh:5.1f}km/h  G{phys.gear}  "
        f"THR {phys.gas*100:4.0f}%  BRK {phys.brake*100:4.0f}%  "
        f"STEER {math.degrees(phys.steerAngle):+6.1f}°  "
        f"SLIP {slip_angle:+6.1f}°  "
        f"YAW {yaw:+6.1f}°/s  "
        f"OS {os_idx:+5.2f}  "
        f"RL {temps_r[0]:4.0f}°  RR {temps_r[1]:4.0f}°"
    )
    print(f"\r{line}", end="", flush=True)

# ── CSV Writer ─────────────────────────────────────────────────────────────────

CSV_HEADERS = [
    "time_s",
    "speed_kmh", "gear", "rpm",
    "throttle", "brake", "clutch", "steer_deg",
    "sideslip_deg", "yaw_rate_deg_s", "oversteer_idx",
    "pitch", "roll", "heading",
    "local_vel_x", "local_vel_y", "local_vel_z",
    "slip_FL", "slip_FR", "slip_RL", "slip_RR",
    "susp_FL", "susp_FR", "susp_RL", "susp_RR",
    "ride_height_front", "ride_height_rear",
    "cg_height",
    "tyre_temp_FL", "tyre_temp_FR", "tyre_temp_RL", "tyre_temp_RR",
    "tyre_temp_i_FL", "tyre_temp_i_FR", "tyre_temp_i_RL", "tyre_temp_i_RR",
    "tyre_temp_m_FL", "tyre_temp_m_FR", "tyre_temp_m_RL", "tyre_temp_m_RR",
    "tyre_temp_o_FL", "tyre_temp_o_FR", "tyre_temp_o_RL", "tyre_temp_o_RR",
    "brake_temp_FL", "brake_temp_FR", "brake_temp_RL", "brake_temp_RR",
    "tyre_press_FL", "tyre_press_FR", "tyre_press_RL", "tyre_press_RR",
    "tyre_load_FL", "tyre_load_FR", "tyre_load_RL", "tyre_load_RR",
    "tyre_wear_FL", "tyre_wear_FR", "tyre_wear_RL", "tyre_wear_RR",
    "wheel_speed_FL", "wheel_speed_FR", "wheel_speed_RL", "wheel_speed_RR",
    "camber_deg_FL", "camber_deg_FR", "camber_deg_RL", "camber_deg_RR",
    "accel_x", "accel_y", "accel_z",
    "air_temp", "road_temp",
    "turbo_boost", "tc_active", "abs_active",
    "lap", "lap_time_ms", "dist_traveled",
    "wind_speed", "wind_dir",
    "pp_active", "pp_plan_type", "pp_weather", "pp_weather_idx",
    "pp_rain_amount", "pp_rain_wetness", "pp_rain_water", "pp_rain_prob",
    "pp_temp_air", "pp_temp_road", "pp_humidity", "pp_mist",
    "pp_wind_strength", "pp_wind_dir",
]

def _pp_row(pp):
    if pp is None:
        return [0, "", "", -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    return [
        1,
        pp["plan_type"],
        pp["weather_name"],
        pp["weather_idx"],
        pp["rain_amount"],
        pp["rain_wetness"],
        pp["rain_water"],
        pp["rain_prob"],
        pp["temp_air"],
        pp["temp_road"],
        pp["humidity"],
        pp["mist"],
        pp["wind_strength"],
        pp["wind_dir"],
    ]

def build_row(phys, gfx, elapsed):
    slip = sideslip_angle(phys)
    yaw  = math.degrees(phys.localAngularVel[1])
    os   = oversteer_index(phys)
    return [
        round(elapsed, 3),
        round(phys.speedKmh, 2),
        phys.gear,
        phys.rpms,
        round(phys.gas, 4),
        round(phys.brake, 4),
        round(phys.clutch, 4),
        round(math.degrees(phys.steerAngle), 2),
        round(slip, 3),
        round(yaw, 3),
        round(os, 4),
        round(phys.pitch, 4),
        round(phys.roll, 4),
        round(math.degrees(phys.heading), 2),
        # Local velocity components (m/s)
        round(phys.localVelocity[0], 3),
        round(phys.localVelocity[1], 3),
        round(phys.localVelocity[2], 3),
        # Wheel slip
        *[round(phys.wheelSlip[i], 4) for i in range(4)],
        # Suspension travel (mm)
        *[round(phys.suspensionTravel[i] * 1000, 2) for i in range(4)],
        # Ride height (mm)
        round(phys.rideHeight[0] * 1000, 2),
        round(phys.rideHeight[1] * 1000, 2),
        # CG height (m)
        round(phys.cgHeight, 4),
        # Tyre temps — avg, then inner, mid, outer per corner
        *[round(avg_tyre_temp(phys, i), 1) for i in range(4)],
        *[round(phys.tyreTempI[i], 1) for i in range(4)],
        *[round(phys.tyreTempM[i], 1) for i in range(4)],
        *[round(phys.tyreTempO[i], 1) for i in range(4)],
        # Brake temps
        *[round(phys.brakeTemp[i], 1) for i in range(4)],
        # Tyre pressures (psi)
        *[round(phys.wheelsPressure[i], 2) for i in range(4)],
        # Tyre load (N)
        *[round(phys.wheelLoad[i], 1) for i in range(4)],
        # Tyre wear (0-1)
        *[round(phys.tyreWear[i], 4) for i in range(4)],
        # Wheel angular speed (rad/s)
        *[round(phys.wheelAngularSpeed[i], 3) for i in range(4)],
        # Dynamic camber (degrees)
        *[round(math.degrees(phys.camberRAD[i]), 3) for i in range(4)],
        # G forces
        round(phys.accG[0], 4),
        round(phys.accG[1], 4),
        round(phys.accG[2], 4),
        # Ambient
        round(phys.airTemp, 1),
        round(phys.roadTemp, 1),
        # Systems
        round(phys.turboBoost, 3),
        round(phys.tc, 3),
        round(phys.abs, 3),
        gfx.completedLaps,
        gfx.iCurrentTime,
        round(gfx.distanceTraveled, 1),
        # Wind (from graphics)
        round(gfx.windSpeed, 2),
        round(gfx.windDirection, 2),
        # Pure Planner
        *(_pp_row(read_planner_weather())),
    ]

# ── Pure Planner ───────────────────────────────────────────────────────────────

PUREPLANNER_LAST_USED = (
    r"D:\SteamLibrary\steamapps\common\assettocorsa"
    r"\extension\config-ext\PurePlanner\Plans\last_used.json"
)

PLAN_TYPE_MAP = {0: "Timed", 1: "Daycycle", 2: "Stamp"}

_pp_cache      = None   # last parsed weather dict
_pp_cache_time = 0.0    # when we last read the file
_pp_file_mtime = 0.0    # last known file modification time
PP_READ_INTERVAL = 10.0 # seconds between file reads

def read_planner_weather():
    """
    Read Pure Planner's last_used.json (updated every ~10s by CSP).
    Returns a dict of weather values, or None if PP is not active.
    """
    global _pp_cache, _pp_cache_time, _pp_file_mtime

    now = time.perf_counter()
    if now - _pp_cache_time < PP_READ_INTERVAL:
        return _pp_cache

    _pp_cache_time = now

    if not os.path.exists(PUREPLANNER_LAST_USED):
        return None

    try:
        mtime = os.path.getmtime(PUREPLANNER_LAST_USED)
        # If file hasn't changed since last read and we have a cache, return it
        if mtime == _pp_file_mtime and _pp_cache is not None:
            return _pp_cache

        # If file is older than 60s, Pure Planner probably isn't running
        if time.time() - mtime > 60:
            _pp_cache = None
            return None

        _pp_file_mtime = mtime
        with open(PUREPLANNER_LAST_USED, "r", encoding="utf-8") as f:
            data = json.load(f)

        container = data.get("container", [])
        if not container:
            return None

        w = container[0].get("data", {}).get("weather", {})
        ctrl = data.get("control", {})

        _pp_cache = {
            "plan_type":    PLAN_TYPE_MAP.get(ctrl.get("type", -1), "unknown"),
            "weather_idx":  w.get("index", -1),
            "weather_name": PURE_WEATHER_MAP.get(w.get("index", -1), "unknown"),
            "rain_amount":  round(w.get("rain_amount",    0.0), 4),
            "rain_wetness": round(w.get("rain_wetness",   0.0), 4),
            "rain_water":   round(w.get("rain_water",     0.0), 4),
            "rain_prob":    round(w.get("rain_probability",0.0),4),
            "temp_air":     round(w.get("temp_air",       0.0), 1),
            "temp_road":    round(w.get("temp_road",      0.0), 1),
            "humidity":     round(w.get("humidity",       0.0), 4),
            "mist":         round(w.get("mist",           0.0), 4),
            "wind_strength":round(w.get("wind_strength",  0.0), 1),
            "wind_dir":     round(w.get("wind_direction", 0.0), 1),
        }
        return _pp_cache
    except Exception:
        return None

# ── Session Metadata Detection ─────────────────────────────────────────────────

AC_DOCS       = os.path.join(os.path.expanduser("~"), "Documents", "Assetto Corsa")
CM_PRESET_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AcTools Content Manager", "Presets", "Quick Drive")

PURE_WEATHER_MAP = {
    0:"light_thunderstorm", 1:"thunderstorm", 2:"heavy_thunderstorm",
    3:"light_drizzle", 4:"drizzle", 5:"heavy_drizzle",
    6:"light_rain", 7:"rain", 8:"heavy_rain",
    9:"light_snow", 10:"snow", 11:"heavy_snow",
    12:"light_sleet", 13:"sleet", 14:"heavy_sleet",
    15:"clear", 16:"few_clouds", 17:"scattered_clouds",
    18:"broken_clouds", 19:"overcast_clouds", 20:"fog",
    21:"mist", 22:"smoke", 23:"haze", 24:"sand", 25:"dust",
    26:"squalls", 27:"tornado", 28:"hurricane", 31:"windy",
    32:"hail", 40:"random_dry", 41:"random_rainy", 42:"random_bad",
    100:"no_clouds", 50:"cm", 666:"empty",
}

def detect_setup(car_model):
    """Compare last.ini against named setups to identify active tune."""
    setup_dir = os.path.join(AC_DOCS, "setups", car_model, "generic")
    last_ini  = os.path.join(setup_dir, "last.ini")
    if not os.path.exists(last_ini):
        return "unknown"
    try:
        def normalise(text):
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            return "\n".join(lines)

        with open(last_ini, "r", encoding="utf-8", errors="ignore") as f:
            last_content = normalise(f.read())
        for fname in os.listdir(setup_dir):
            if fname == "last.ini" or not fname.endswith(".ini"):
                continue
            fpath = os.path.join(setup_dir, fname)
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = normalise(f.read())
            if content == last_content:
                return fname.replace(".ini", "")
        return "custom"
    except Exception:
        return "unknown"

def detect_cm_preset():
    """Return the name of the most recently written CM Quick Drive preset."""
    if not os.path.exists(CM_PRESET_DIR):
        return "unknown"
    try:
        candidates = []
        for fname in os.listdir(CM_PRESET_DIR):
            if not fname.endswith(".cmpreset"):
                continue
            fpath = os.path.join(CM_PRESET_DIR, fname)
            candidates.append((os.path.getmtime(fpath), fname.replace(".cmpreset", "")))
        if not candidates:
            return "unknown"
        candidates.sort(reverse=True)
        return candidates[0][1]
    except Exception:
        return "unknown"

def parse_game_preset():
    """Parse Game.cmpreset for weather name and track state."""
    game_preset = os.path.join(CM_PRESET_DIR, "Game.cmpreset")
    weather     = "unknown"
    track_state = "unknown"
    if not os.path.exists(game_preset):
        return weather, track_state
    try:
        with open(game_preset, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Weather
        weather_id = data.get("WeatherId", "")
        for line in weather_id.replace("\\n", "\n").split("\n"):
            if line.startswith("CM_WEATHER="):
                cw = int(line.split("=")[1])
                weather = PURE_WEATHER_MAP.get(cw, f"weather_{cw}")
                break

        # Track state — pull from preset filename or description
        tp_preset = data.get("TrackPropertiesPresetFilename", "")
        if tp_preset:
            track_state = os.path.basename(tp_preset).replace(".cmpreset", "")
        else:
            tp_data = data.get("TrackPropertiesData", "{}")
            try:
                tp = json.loads(tp_data)
                track_state = tp.get("d", "unknown").split(".")[0]
            except Exception:
                pass
    except Exception:
        pass
    return weather, track_state

# ── Main Loop ──────────────────────────────────────────────────────────────────

SAMPLE_RATE_HZ = 30  # samples per second

def main():
    print("Assetto Corsa Telemetry Logger")
    print("Waiting for AC to start... (Ctrl+C to quit)\n")

    phys_shm  = None
    graph_shm = None
    stat_shm  = None

    csv_file   = None
    csv_writer = None
    log_path   = None
    session_active = False
    start_time = None
    last_packet = -1
    sample_interval = 1.0 / SAMPLE_RATE_HZ

    try:
        while True:
            # (Re)open shared memory if needed
            if phys_shm is None:
                phys_shm  = open_shm("Local\\acpmf_physics",  ctypes.sizeof(ACPhysics))
                graph_shm = open_shm("Local\\acpmf_graphics", ctypes.sizeof(ACGraphics))
                stat_shm  = open_shm("Local\\acpmf_static",   ctypes.sizeof(ACStatic))

            if phys_shm is None:
                time.sleep(1)
                continue

            phys = read_struct(phys_shm,  ACPhysics)
            gfx  = read_struct(graph_shm, ACGraphics)
            stat = read_struct(stat_shm,  ACStatic)

            is_live = gfx is not None and gfx.status == 2  # AC_LIVE

            if is_live and not session_active:
                # New session started
                session_active = True
                start_time     = time.perf_counter()
                last_packet    = -1

                car   = stat.carModel.strip() if stat else "unknown"
                track = stat.track.strip()    if stat else "unknown"

                # Detect metadata
                setup       = detect_setup(car)
                cm_preset   = detect_cm_preset()
                weather, track_state = parse_game_preset()

                ts    = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                fname = f"{ts}_{car}_{track}_{setup}_{weather}.csv".replace(" ", "_")
                log_path = os.path.join(LOG_DIR, fname)

                csv_file   = open(log_path, "w", newline="", encoding="utf-8")
                csv_writer = csv.writer(csv_file)
                # Write metadata as comment rows
                csv_writer.writerow(["# car",        car])
                csv_writer.writerow(["# track",      track])
                csv_writer.writerow(["# setup",      setup])
                csv_writer.writerow(["# cm_preset",  cm_preset])
                csv_writer.writerow(["# weather",    weather])
                csv_writer.writerow(["# track_state",track_state])
                csv_writer.writerow(CSV_HEADERS)

                print(f"\nLogging: {fname}")
                pp = read_planner_weather()
                print(f"  Car:         {car}")
                print(f"  Track:       {track}")
                print(f"  Setup:       {setup}")
                print(f"  CM Preset:   {cm_preset}")
                if pp:
                    print(f"  Pure Planner: ACTIVE ({pp['plan_type']})")
                    print(f"  PP Weather:  {pp['weather_name']}  rain={pp['rain_amount']}  wetness={pp['rain_wetness']}  temp={pp['temp_air']}C")
                else:
                    print(f"  Weather:     {weather} (static)")
                print(f"  Track State: {track_state}")
                print("-" * 100)

            elif not is_live and session_active:
                # Session ended
                session_active = False
                if csv_file:
                    csv_file.close()
                    csv_file = None
                    print(f"\n\nSession ended. Saved: {log_path}")
                phys_shm = graph_shm = stat_shm = None  # force reconnect next session

            if session_active and phys is not None and gfx is not None:
                if phys.packetId != last_packet:
                    last_packet = phys.packetId
                    elapsed = time.perf_counter() - start_time
                    row = build_row(phys, gfx, elapsed)
                    csv_writer.writerow(row)
                    print_live(phys, gfx, elapsed)

            time.sleep(sample_interval)

    except KeyboardInterrupt:
        print("\n\nStopped by user.")
    finally:
        if csv_file:
            csv_file.close()
            print(f"Saved: {log_path}")
        for shm in [phys_shm, graph_shm, stat_shm]:
            if shm:
                try:
                    shm.close()
                except Exception:
                    pass

if __name__ == "__main__":
    main()
