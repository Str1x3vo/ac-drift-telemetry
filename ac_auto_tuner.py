import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext
import csv
import os
import re
import statistics
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

SETUPS_BASE  = Path(os.path.expanduser("~")) / "Documents" / "Assetto Corsa" / "setups"
ACTIVE_SPEED = 20   # km/h — below this row is ignored
DRIFT_SLIP   = 5    # deg  — above this counts as drifting

# Pressures are always hard-set — no telemetry needed
SET_PRESSURE = {"front": 32, "rear": 20}

# Suspension travel targets for drift — generous ranges, only act on extremes
TARGET_TRAVEL = {
    "front": {"min": 85,  "max": 135},
    "rear":  {"min": 100, "max": 150},
}

# Tyre temp targets — drift tyres run hot
TARGET_TEMP = {
    "front": {"min": 65, "max": 110},
    "rear":  {"min": 70, "max": 115},
}

# Camber: INI unit = tenths of a degree (-59 = -5.9°)
# Only adjust on big spread, small step, small cap
CAMBER_UNIT_PER_DEG_SPREAD = 1 / 6
CAMBER_MAX_CHANGE = 5

# Suspension travel stdev — drift is bouncy, only flag if genuinely out of control
TRAVEL_STDEV_FRONT = 25
TRAVEL_STDEV_REAR  = 35

# Sideslip CV — drift is inconsistent by nature, only intervene at extreme snap
SLIP_CV_LOOSE = 0.72   # stdev/avg — above = snapping, uncontrollable
SLIP_AVG_LOW  = 5.0    # deg — below = barely drifting at all

# Brake temp ratio — drift braking is hard and imbalanced, wide tolerance
BRAKE_RATIO_HIGH = 1.45
BRAKE_RATIO_LOW  = 0.70

# Rear wheel speed diff during drift — big diff is expected in drift
WHEEL_DIFF_HIGH = 45   # → raise preload
WHEEL_DIFF_LOW  = 5    # → lower preload (too locked)

# ─── CSV helpers ──────────────────────────────────────────────────────────────

def parse_csv(path):
    car = None
    headers = None
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if not row:
                continue
            if row[0].startswith('# car'):
                car = row[1].strip()
            elif row[0].startswith('#'):
                continue
            elif headers is None:
                headers = row
            elif len(row) == len(headers):
                try:
                    d = {h: (float(v) if v not in ('', 'None') else None)
                         for h, v in zip(headers, row)}
                    rows.append(d)
                except (ValueError, IndexError):
                    pass
    return car, rows

def active(rows):
    return [r for r in rows if (r.get('speed_kmh') or 0) > ACTIVE_SPEED]

def drifting(rows):
    return [r for r in rows
            if abs(r.get('sideslip_deg') or 0) > DRIFT_SLIP
            and (r.get('speed_kmh') or 0) > ACTIVE_SPEED]

def braking(rows):
    return [r for r in rows
            if (r.get('brake') or 0) > 0.3
            and (r.get('speed_kmh') or 0) > ACTIVE_SPEED]

def lifting(rows):
    """Coasting — low throttle, no brake, moving."""
    return [r for r in rows
            if (r.get('throttle') or 0) < 0.1
            and (r.get('brake') or 0) < 0.1
            and (r.get('speed_kmh') or 0) > ACTIVE_SPEED]

def avg(vals):
    v = [x for x in vals if x is not None]
    return statistics.mean(v) if v else None

def stdev(vals):
    v = [x for x in vals if x is not None]
    return statistics.stdev(v) if len(v) > 1 else 0.0

# ─── INI helpers ──────────────────────────────────────────────────────────────

def read_ini_values(path):
    vals = {}
    cur = None
    with open(path, 'r') as f:
        for line in f:
            m = re.match(r'^\[(.+)\]', line.strip())
            if m:
                cur = m.group(1)
            elif cur and line.strip().startswith('VALUE='):
                try:
                    vals[cur] = float(line.strip().split('=', 1)[1])
                except ValueError:
                    vals[cur] = line.strip().split('=', 1)[1]
    return vals

def write_ini(source, dest, changes):
    cur = None
    out = []
    with open(source, 'r') as f:
        for line in f:
            m = re.match(r'^\[(.+)\]', line.strip())
            if m:
                cur = m.group(1)
                out.append(line)
            elif cur and line.strip().startswith('VALUE=') and cur in changes:
                out.append(f'VALUE={changes[cur]}\n')
            else:
                out.append(line)
    with open(dest, 'w') as f:
        f.writelines(out)

# ─── Analysis ─────────────────────────────────────────────────────────────────

def analyse(rows):
    act  = active(rows)
    dft  = drifting(rows)
    brk  = braking(rows)
    lft  = lifting(rows)
    if not act:
        return None

    travel_src = dft if len(dft) > 50 else act

    # Suspension travel stdev
    travel_stdev = {}
    for c in ('FL', 'FR', 'RL', 'RR'):
        vals = [r.get(f'susp_{c}') for r in act if r.get(f'susp_{c}') is not None]
        travel_stdev[c] = statistics.stdev(vals) if len(vals) > 1 else 0.0

    # Max travel peaks (99th percentile approximation — sorted)
    travel_max = {}
    for c in ('FL', 'FR', 'RL', 'RR'):
        vals = sorted([r.get(f'susp_{c}') for r in act if r.get(f'susp_{c}') is not None])
        travel_max[c] = vals[int(len(vals) * 0.99)] if vals else None

    # Sideslip stats
    slip_vals = [abs(r.get('sideslip_deg') or 0) for r in dft]
    slip_avg  = statistics.mean(slip_vals) if slip_vals else 0
    slip_max  = max(slip_vals, default=0)
    slip_cv   = (statistics.stdev(slip_vals) / slip_avg) if (slip_avg > 0 and len(slip_vals) > 1) else 0

    # Rear wheel speed difference during drift
    wheel_diff_vals = [abs((r.get('wheel_speed_RL') or 0) - (r.get('wheel_speed_RR') or 0))
                       for r in dft]
    wheel_diff_avg  = statistics.mean(wheel_diff_vals) if wheel_diff_vals else 0

    # Brake temps during braking
    brake_temp_front = avg([(r.get('brake_temp_FL') or 0) + (r.get('brake_temp_FR') or 0)
                             for r in brk]) if brk else None
    brake_temp_rear  = avg([(r.get('brake_temp_RL') or 0) + (r.get('brake_temp_RR') or 0)
                             for r in brk]) if brk else None

    # Oversteer during lift (for diff coast tuning)
    oversteer_lift   = avg([r.get('oversteer_idx') for r in lft]) if lft else 0

    # Roll during drifts
    roll_avg = avg([abs(r.get('roll') or 0) for r in (dft if dft else act)])

    return {
        'active':          len(act),
        'drift':           len(dft),
        'pressure':        {c: avg([r.get(f'tyre_press_{c}') for r in act])
                            for c in ('FL','FR','RL','RR')},
        'temp':            {c: avg([r.get(f'tyre_temp_{c}') for r in act])
                            for c in ('FL','FR','RL','RR')},
        'spread':          {c: ((avg([r.get(f'tyre_temp_i_{c}') for r in act]) or 0)
                               - (avg([r.get(f'tyre_temp_o_{c}') for r in act]) or 0))
                            for c in ('FL','FR','RL','RR')},
        'travel_avg':      {c: avg([r.get(f'susp_{c}') for r in travel_src])
                            for c in ('FL','FR','RL','RR')},
        'travel_stdev':    travel_stdev,
        'travel_max':      travel_max,
        'sideslip_avg':    slip_avg,
        'sideslip_max':    slip_max,
        'sideslip_cv':     slip_cv,
        'wheel_diff_avg':  wheel_diff_avg,
        'brake_temp_front':brake_temp_front,
        'brake_temp_rear': brake_temp_rear,
        'oversteer_lift':  oversteer_lift,
        'roll_avg':        roll_avg,
    }

# ─── Tuning logic ─────────────────────────────────────────────────────────────

def clamp(val, lo, hi):
    return max(lo, min(hi, val))

def pct_change(current, factor, lo, hi):
    return int(round(clamp(current * factor, lo, hi)))

def build_changes(data, base):
    changes = {}
    reasons = []

    # ── 1. Tyre pressures — always hard-set for drift ─────────────────────────
    for ini_key, axle in [
        ('PRESSURE_LF','front'), ('PRESSURE_RF','front'),
        ('PRESSURE_LR','rear'),  ('PRESSURE_RR','rear'),
    ]:
        cv = base.get(ini_key)
        target = SET_PRESSURE[axle]
        if cv is None:
            continue
        if int(cv) != target:
            changes[ini_key] = target
            reasons.append(f"{ini_key}: hard-set to drift target  {cv:.0f} → {target}")

    # ── 2. Spring rates (suspension travel avg) ────────────────────────────────
    for corners, spring_keys, axle in [
        (('FL','FR'), ('SPRING_RATE_LF','SPRING_RATE_RF'), 'front'),
        (('RL','RR'), ('SPRING_RATE_LR','SPRING_RATE_RR'), 'rear'),
    ]:
        travels = [data['travel_avg'].get(c) for c in corners if data['travel_avg'].get(c)]
        if not travels:
            continue
        t_avg = sum(travels) / len(travels)
        lo, hi = TARGET_TRAVEL[axle]['min'], TARGET_TRAVEL[axle]['max']
        for sk in spring_keys:
            cv = base.get(sk)
            if cv is None:
                continue
            if t_avg > hi:
                # Drift: only stiffen if well beyond limit, and only gently
                factor = clamp(1 + (t_avg - hi) / 300, 1.01, 1.10)
                nv = int(round(cv * factor))
                changes[sk] = nv
                reasons.append(f"Spring {sk}: avg travel {t_avg:.0f}mm > {hi}mm → stiffen  {cv:.0f} → {nv}")
            elif t_avg < lo:
                # Too stiff — soften for more rotation
                factor = clamp(1 - (lo - t_avg) / 250, 0.88, 0.99)
                nv = int(round(cv * factor))
                changes[sk] = nv
                reasons.append(f"Spring {sk}: avg travel {t_avg:.0f}mm < {lo}mm → soften  {cv:.0f} → {nv}")

    # ── 3. Camber (inner/outer temp spread) ───────────────────────────────────
    # INI unit ≈ tenths of a degree. Inner hotter = too negative → increase value.
    for corner, ini_key in [
        ('FL','CAMBER_LF'), ('FR','CAMBER_RF'),
        ('RL','CAMBER_LR'), ('RR','CAMBER_RR'),
    ]:
        spread = data['spread'].get(corner, 0)
        cv = base.get(ini_key)
        if cv is None or abs(spread) < 8:
            continue
        # +spread = inner hotter → too negative → move toward 0 (increase value)
        delta = int(round(clamp(spread * CAMBER_UNIT_PER_DEG_SPREAD,
                                -CAMBER_MAX_CHANGE, CAMBER_MAX_CHANGE)))
        if delta == 0:
            continue
        nv = int(round(cv + delta))
        changes[ini_key] = nv
        direction = "less negative" if delta > 0 else "more negative"
        reasons.append(f"Camber {corner}: i/o spread {spread:+.1f}°C → {direction}  "
                       f"{ini_key} {cv:.0f} → {nv}")

    # ── 4. ARB ─────────────────────────────────────────────────────────────────
    # Rear ARB: only stiffen if angle is genuinely snappy/uncontrollable
    # For drift, loose rear is intentional — only intervene at extreme CV
    if data['drift'] > 100:
        cv = base.get('ARB_REAR')
        if cv is not None:
            if data['sideslip_cv'] > SLIP_CV_LOOSE:
                # Very snappy — stiffen rear ARB slightly
                factor = clamp(1 + (data['sideslip_cv'] - SLIP_CV_LOOSE) * 0.25, 1.0, 1.12)
                nv = int(round(cv * factor))
                changes['ARB_REAR'] = nv
                reasons.append(f"ARB_REAR: sideslip CV {data['sideslip_cv']:.2f} (snappy) → stiffen slightly  "
                               f"{cv:.0f} → {nv}")
            elif data['sideslip_avg'] < SLIP_AVG_LOW and data['sideslip_cv'] < 0.25:
                # Barely drifting, very consistent → rear too stiff → soften
                factor = clamp(1 - (SLIP_AVG_LOW - data['sideslip_avg']) * 0.020, 0.82, 0.99)
                nv = int(round(cv * factor))
                changes['ARB_REAR'] = nv
                reasons.append(f"ARB_REAR: sideslip avg {data['sideslip_avg']:.1f}° (low angle) → soften  "
                               f"{cv:.0f} → {nv}")

        # Front ARB: only adjust if roll is extreme (>8°) — roll is normal in drift
        cv_f = base.get('ARB_FRONT')
        if cv_f is not None and (data['roll_avg'] or 0) > 8.0:
            factor = clamp(1 + ((data['roll_avg'] - 8.0) * 0.02), 1.0, 1.10)
            nv = int(round(cv_f * factor))
            changes['ARB_FRONT'] = nv
            reasons.append(f"ARB_FRONT: avg roll {data['roll_avg']:.1f}° (excessive) → stiffen front  "
                           f"{cv_f:.0f} → {nv}")

    # ── 5. Rebound dampers (suspension travel stdev) ──────────────────────────
    for corner, rebound_key, fast_key, threshold in [
        ('FL', 'DAMP_REBOUND_LF', 'DAMP_FAST_REBOUND_LF', TRAVEL_STDEV_FRONT),
        ('FR', 'DAMP_REBOUND_RF', 'DAMP_FAST_REBOUND_RF', TRAVEL_STDEV_FRONT),
        ('RL', 'DAMP_REBOUND_LR', 'DAMP_FAST_REBOUND_LR', TRAVEL_STDEV_REAR),
        ('RR', 'DAMP_REBOUND_RR', 'DAMP_FAST_REBOUND_RR', TRAVEL_STDEV_REAR),
    ]:
        sd = data['travel_stdev'].get(corner, 0)
        if sd <= threshold:
            continue
        excess = (sd - threshold) / threshold   # 0 → 1+

        # Slow rebound
        cv = base.get(rebound_key)
        if cv is not None:
            factor = clamp(1 + excess * 0.15, 1.0, 1.20)
            nv = int(round(cv * factor))
            changes[rebound_key] = nv
            reasons.append(f"Damper {rebound_key}: travel stdev {sd:.1f}mm → increase rebound  "
                           f"{cv:.0f} → {nv}")

        # Fast rebound — only if very bouncy (excess > 0.4)
        if excess > 0.4:
            cv_f = base.get(fast_key)
            if cv_f is not None:
                factor = clamp(1 + (excess - 0.4) * 0.12, 1.0, 1.15)
                nv = int(round(cv_f * factor))
                changes[fast_key] = nv
                reasons.append(f"Damper {fast_key}: travel stdev {sd:.1f}mm (high) → increase fast rebound  "
                               f"{cv_f:.0f} → {nv}")

    # ── 6. Bump dampers (peak travel) ─────────────────────────────────────────
    # If 99th-pct travel is very high → suspension hitting limit → add bump damping
    for corner, bump_key, fast_bump_key, spring_key in [
        ('FL', 'DAMP_BUMP_LF', 'DAMP_FAST_BUMP_LF', 'SPRING_RATE_LF'),
        ('FR', 'DAMP_BUMP_RF', 'DAMP_FAST_BUMP_RF', 'SPRING_RATE_RF'),
        ('RL', 'DAMP_BUMP_LR', 'DAMP_FAST_BUMP_LR', 'SPRING_RATE_LR'),
        ('RR', 'DAMP_BUMP_RR', 'DAMP_FAST_BUMP_RR', 'SPRING_RATE_RR'),
    ]:
        peak = data['travel_max'].get(corner)
        avg_t = data['travel_avg'].get(corner)
        if peak is None or avg_t is None:
            continue
        # If peak > avg*1.8 → occasional big hits → increase fast bump
        if peak > avg_t * 1.8:
            cv_fb = base.get(fast_bump_key)
            if cv_fb is not None:
                ratio = peak / avg_t
                factor = clamp(1 + (ratio - 1.8) * 0.10, 1.0, 1.15)
                nv = int(round(cv_fb * factor))
                if nv != int(cv_fb):
                    changes[fast_bump_key] = nv
                    reasons.append(f"Damper {fast_bump_key}: peak {peak:.0f}mm vs avg {avg_t:.0f}mm → "
                                   f"increase fast bump  {cv_fb:.0f} → {nv}")

    # ── 7. Diff preload (rear wheel speed difference) ─────────────────────────
    wd = data['wheel_diff_avg']
    cv = base.get('DIFF_PRELOAD')
    if cv is not None and data['drift'] > 100:
        if wd > WHEEL_DIFF_HIGH:
            factor = clamp(1 + (wd - WHEEL_DIFF_HIGH) * 0.008, 1.0, 1.25)
            nv = int(round(cv * factor))
            changes['DIFF_PRELOAD'] = nv
            reasons.append(f"DIFF_PRELOAD: rear wheel speed diff avg {wd:.1f} (large) → raise preload  "
                           f"{cv:.0f} → {nv}")
        elif wd < WHEEL_DIFF_LOW and cv > 50:
            factor = clamp(1 - (WHEEL_DIFF_LOW - wd) * 0.02, 0.85, 0.99)
            nv = int(round(cv * factor))
            changes['DIFF_PRELOAD'] = nv
            reasons.append(f"DIFF_PRELOAD: rear wheel speed diff avg {wd:.1f} (near locked) → lower preload  "
                           f"{cv:.0f} → {nv}")

    # ── 8. Diff coast (oversteer on lift) ─────────────────────────────────────
    ov_lift = data.get('oversteer_lift') or 0
    cv = base.get('DIFF_COAST')
    if cv is not None:
        if ov_lift > 0.3:
            # Car oversteers on lift → reduce coast lock for smoother entry
            factor = clamp(1 - (ov_lift - 0.3) * 0.15, 0.82, 0.99)
            nv = int(round(clamp(cv * factor, 0, 100)))
            if nv != int(cv):
                changes['DIFF_COAST'] = nv
                reasons.append(f"DIFF_COAST: oversteer on lift {ov_lift:.2f} → reduce coast lock  "
                               f"{cv:.0f} → {nv}")
        elif ov_lift < 0.05 and cv < 80:
            # Very stable on lift → can add more coast for better entry stability
            nv = int(round(clamp(cv * 1.08, 0, 100)))
            if nv != int(cv):
                changes['DIFF_COAST'] = nv
                reasons.append(f"DIFF_COAST: stable on lift → can increase coast  "
                               f"{cv:.0f} → {nv}")

    # ── 9. Brake bias ──────────────────────────────────────────────────────────
    bf = data.get('brake_temp_front')
    br = data.get('brake_temp_rear')
    cv = base.get('FRONT_BIAS')
    if bf and br and br > 10 and cv is not None:
        ratio = bf / br
        if ratio > BRAKE_RATIO_HIGH:
            # Fronts working much harder → lower front bias
            delta = -int(round((ratio - BRAKE_RATIO_HIGH) * 8))
            nv = int(round(clamp(cv + delta, 40, 85)))
            changes['FRONT_BIAS'] = nv
            reasons.append(f"FRONT_BIAS: front brakes {ratio:.2f}x hotter than rear → reduce  "
                           f"{cv:.0f} → {nv}")
        elif ratio < BRAKE_RATIO_LOW:
            delta = int(round((BRAKE_RATIO_LOW - ratio) * 8))
            nv = int(round(clamp(cv + delta, 40, 85)))
            changes['FRONT_BIAS'] = nv
            reasons.append(f"FRONT_BIAS: rear brakes {1/ratio:.2f}x hotter than front → increase  "
                           f"{cv:.0f} → {nv}")

    return changes, reasons

# ─── GUI ──────────────────────────────────────────────────────────────────────

BG     = "#1a1a1a"
BG2    = "#242424"
ORANGE = "#e05a00"
GREEN  = "#90ee90"
YELLOW = "#ffcc44"
BLUE   = "#7ec8e3"
RED    = "#ff6666"
FG     = "#dddddd"
FONT   = ("Consolas", 9)
FONT_B = ("Consolas", 9, "bold")


class App:
    def __init__(self, root):
        self.root = root
        root.title("AC Drift Tuner")
        root.geometry("800x720")
        root.configure(bg=BG)
        root.resizable(True, True)

        self.csv_path  = None
        self.ini_path  = None
        self.car_model = None
        self.data      = None
        self.changes   = None
        self.base      = None

        self._style()
        self._build()

    def _style(self):
        s = ttk.Style()
        s.theme_use('clam')
        for name, bg in [('TButton','#333'), ('Accent.TButton', ORANGE)]:
            s.configure(name, background=bg, foreground='white',
                        borderwidth=0, padding=8, font=FONT_B)
        s.map('TButton',        background=[('active','#555')])
        s.map('Accent.TButton', background=[('active','#ff6a10')])

    def _build(self):
        tk.Label(self.root, text="AC DRIFT TUNER", font=("Consolas", 15, "bold"),
                 bg=BG, fg=ORANGE).pack(pady=(16,2))
        tk.Label(self.root, text="drift tuner — reads telemetry, adjusts setup for angle and consistency",
                 font=FONT, bg=BG, fg="#666").pack(pady=(0,12))

        frm = tk.Frame(self.root, bg=BG2, padx=16, pady=14)
        frm.pack(fill='x', padx=20, pady=(0,10))
        frm.columnconfigure(0, weight=1)

        tk.Label(frm, text="TELEMETRY CSV", font=FONT_B, bg=BG2, fg="#888").grid(row=0, column=0, sticky='w')
        self.csv_lbl = tk.Label(frm, text="No file selected", font=FONT, bg=BG2, fg="#ccc",
                                wraplength=530, anchor='w', justify='left')
        self.csv_lbl.grid(row=1, column=0, sticky='w', pady=(2,8))
        ttk.Button(frm, text="Browse", command=self._pick_csv).grid(row=1, column=1, padx=(8,0))

        tk.Label(frm, text="BASE SETUP", font=FONT_B, bg=BG2, fg="#888").grid(row=2, column=0, sticky='w')
        self.ini_lbl = tk.Label(frm, text="Will auto-detect once CSV is loaded", font=FONT, bg=BG2, fg="#ccc",
                                wraplength=530, anchor='w', justify='left')
        self.ini_lbl.grid(row=3, column=0, sticky='w', pady=(2,0))
        ttk.Button(frm, text="Browse", command=self._pick_ini).grid(row=3, column=1, padx=(8,0))

        ttk.Button(self.root, text="ANALYSE & TUNE", style='Accent.TButton',
                   command=self._run).pack(pady=(4,10))

        self.out = scrolledtext.ScrolledText(self.root, font=FONT, bg="#111", fg=FG,
                                             insertbackground='white', borderwidth=0,
                                             state='disabled', padx=12, pady=10)
        self.out.pack(fill='both', expand=True, padx=20, pady=(0,8))

        self.save_btn = ttk.Button(self.root, text="SAVE TUNED SETUP", command=self._save)
        self.save_btn.pack(pady=(0,16))
        self.save_btn.state(['disabled'])

    def _log(self, text, color=FG):
        self.out.configure(state='normal')
        tag = f'c{color}'
        self.out.tag_configure(tag, foreground=color)
        self.out.insert('end', text + '\n', tag)
        self.out.configure(state='disabled')
        self.out.see('end')

    def _clear(self):
        self.out.configure(state='normal')
        self.out.delete('1.0', 'end')
        self.out.configure(state='disabled')

    def _pick_csv(self):
        path = filedialog.askopenfilename(
            title="Select Telemetry CSV",
            filetypes=[("CSV files","*.csv"),("All files","*.*")],
            initialdir=str(Path.home() / "Downloads")
        )
        if not path:
            return
        self.csv_path = path
        self.csv_lbl.configure(text=os.path.basename(path), fg=BLUE)
        self._auto_ini(path)

    def _auto_ini(self, csv_path):
        try:
            car = None
            with open(csv_path, 'r') as f:
                for line in f:
                    if line.startswith('# car'):
                        car = line.split(',')[1].strip()
                        break
            if not car:
                return
            self.car_model = car
            ini = SETUPS_BASE / car / "generic" / "generic.ini"
            if ini.exists():
                self.ini_path = str(ini)
                self.ini_lbl.configure(text=str(ini), fg=GREEN)
            else:
                self.ini_path = None
                self.ini_lbl.configure(
                    text=f"Not found — {ini}\n"
                         f"→ In AC, save a setup called 'generic' for this car, then come back.",
                    fg=YELLOW
                )
        except Exception as e:
            self.ini_lbl.configure(text=f"Error: {e}", fg=RED)

    def _pick_ini(self):
        path = filedialog.askopenfilename(
            title="Select Base Setup INI",
            filetypes=[("INI files","*.ini"),("All files","*.*")],
            initialdir=str(SETUPS_BASE)
        )
        if path:
            self.ini_path = path
            self.ini_lbl.configure(text=path, fg=GREEN)

    def _run(self):
        if not self.csv_path:
            messagebox.showwarning("No CSV", "Load a telemetry CSV first.")
            return
        if not self.ini_path or not os.path.exists(self.ini_path):
            messagebox.showwarning(
                "No base setup",
                "Base setup not found.\n\n"
                "In Assetto Corsa:\n"
                "1. Load the car\n"
                "2. Set it up as a starting point\n"
                "3. Save it as 'generic' in the Generic folder\n\n"
                "Then come back and run again."
            )
            return

        self._clear()
        self.save_btn.state(['disabled'])
        self._log("═" * 60)
        self._log("  AC AUTO TUNER — ANALYSIS", ORANGE)
        self._log("═" * 60)

        try:
            car, rows = parse_csv(self.csv_path)
            self._log(f"\n  Car:        {car or 'unknown'}")
            self._log(f"  Base setup: {os.path.basename(self.ini_path)}")
            self._log(f"  Rows:       {len(rows)}")

            self.data = analyse(rows)
            if not self.data:
                self._log("\n  No active driving data found.", RED)
                return

            d = self.data
            self._log(f"  Active:     {d['active']} rows")
            self._log(f"  Drifting:   {d['drift']} rows")

            wp = d['pressure']
            self._log("\n─── WORKING PRESSURES (session avg) ───────────────────────────")
            self._log(f"  FL {wp['FL']:.1f} psi   FR {wp['FR']:.1f} psi")
            self._log(f"  RL {wp['RL']:.1f} psi   RR {wp['RR']:.1f} psi")
            self._log(f"  Set values will be forced to: front {SET_PRESSURE['front']} psi  rear {SET_PRESSURE['rear']} psi", YELLOW)

            tt = d['temp']
            self._log("\n─── TYRE TEMPS (avg active) ────────────────────────────────────")
            self._log(f"  FL {tt['FL']:.0f}°C   FR {tt['FR']:.0f}°C")
            self._log(f"  RL {tt['RL']:.0f}°C   RR {tt['RR']:.0f}°C")

            sp = d['spread']
            self._log("\n─── CAMBER SPREAD (inner − outer °C) ───────────────────────────")
            self._log(f"  FL {sp['FL']:+.1f}°C   FR {sp['FR']:+.1f}°C")
            self._log(f"  RL {sp['RL']:+.1f}°C   RR {sp['RR']:+.1f}°C   (+ve = inner hotter)")

            ta = d['travel_avg']
            ts = d['travel_stdev']
            self._log("\n─── SUSPENSION TRAVEL ──────────────────────────────────────────")
            self._log(f"  FL avg {ta['FL']:.0f}mm  stdev {ts['FL']:.1f}mm   "
                      f"FR avg {ta['FR']:.0f}mm  stdev {ts['FR']:.1f}mm")
            self._log(f"  RL avg {ta['RL']:.0f}mm  stdev {ts['RL']:.1f}mm   "
                      f"RR avg {ta['RR']:.0f}mm  stdev {ts['RR']:.1f}mm")

            self._log("\n─── DRIFT STATS ────────────────────────────────────────────────")
            self._log(f"  Sideslip avg {d['sideslip_avg']:.1f}°   max {d['sideslip_max']:.1f}°   "
                      f"CV {d['sideslip_cv']:.2f}")
            self._log(f"  Rear wheel diff avg {d['wheel_diff_avg']:.1f}")
            self._log(f"  Roll avg {d['roll_avg']:.2f}°   Oversteer on lift {d['oversteer_lift']:.3f}")

            if d['brake_temp_front'] and d['brake_temp_rear']:
                self._log(f"  Brake temps  F {d['brake_temp_front']:.0f}   R {d['brake_temp_rear']:.0f}")

            self.base = read_ini_values(self.ini_path)
            self.changes, reasons = build_changes(self.data, self.base)

            self._log("\n─── CHANGES ────────────────────────────────────────────────────")
            if self.changes:
                for r in reasons:
                    self._log(f"  ✓ {r}", GREEN)
            else:
                self._log("  No changes needed — setup looks well matched.", GREEN)

            self._log("\n" + "═" * 60)

            if self.changes:
                self.save_btn.state(['!disabled'])
                self._log(f"\n  {len(self.changes)} values updated. Click SAVE TUNED SETUP.", BLUE)

        except Exception as e:
            import traceback
            self._log(f"\n  Error: {e}", RED)
            self._log(traceback.format_exc(), RED)

    def _save(self):
        if not self.changes:
            return
        base_name = os.path.splitext(os.path.basename(self.ini_path))[0]
        dest = filedialog.asksaveasfilename(
            title="Save Tuned Setup",
            initialdir=os.path.dirname(self.ini_path),
            initialfile=f"{base_name}_autotuned.ini",
            defaultextension=".ini",
            filetypes=[("INI files","*.ini")]
        )
        if not dest:
            return
        try:
            write_ini(self.ini_path, dest, {k: str(v) for k, v in self.changes.items()})
            self._log(f"\n  Saved → {dest}", GREEN)
            messagebox.showinfo("Saved", f"Tuned setup saved:\n{dest}")
        except Exception as e:
            self._log(f"\n  Save error: {e}", RED)
            messagebox.showerror("Save Error", str(e))


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
