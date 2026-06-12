#!/usr/bin/env python3
"""
SYNOP FM-12 Surface Code Decoder & Encoder
WMO Manual on Codes, Volume I.1
"""

import sys
import re
import argparse
import datetime
import os
import json

# Output wrapper to avoid Unicode encode errors
SAFE_PRINT_TRANSLATION = str.maketrans({
    '╔':'+','╗':'+','╚':'+','╝':'+','║':'|','│':'|',
    '═':'-','─':'-','┌':'+','┐':'+','└':'+','┘':'+',
    '–':'-','—':'-','✔':'[OK]','✓':'[OK]','⚠':'[!]',
    '📍':'Station:','📅':'Date / Time:','💨':'Wind measured:',
    '✅':'[OK]','⏭':'[SKIPPED]','°':'deg','·':'*','•':'*'
})

def safe_print(*args, sep=' ', end='\n', file=sys.stdout, flush=False):
    text = sep.join(str(a) for a in args) + end
    text = text.translate(SAFE_PRINT_TRANSLATION)
    try:
        file.write(text)
    except Exception:
        file.write(text.encode(getattr(file,'encoding','utf-8') or 'utf-8',
                               errors='replace').decode('utf-8', errors='replace'))
    if flush:
        try: file.flush()
        except: pass

print = safe_print

# ══════════════════════════════════════════════════════════════════
#  TOML CONFIG
# ══════════════════════════════════════════════════════════════════

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synop_config.toml")

DEFAULT_CONFIG = {
    "settings": {
        "unit":           "knots",
        "output_format":  "terminal",
        "station_filter": "",
        "default_input":  "",
        "show_section3":  "true",
    }
}

def load_config():
    config = {k: dict(v) for k, v in DEFAULT_CONFIG.items()}
    if not os.path.exists(CONFIG_FILE):
        save_config(config)
        return config
    try:
        with open(CONFIG_FILE, "r") as f:
            lines = f.readlines()
        section = None
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"): continue
            m = re.match(r'^\[(\w+)\]$', line)
            if m:
                section = m.group(1)
                if section not in config: config[section] = {}
                continue
            m = re.match(r'^(\w+)\s*=\s*"?(.*?)"?\s*$', line)
            if m and section:
                config[section][m.group(1)] = m.group(2)
    except Exception:
        pass
    return config

def save_config(config):
    try:
        lines = ["# SYNOP Decoder Configuration File\n",
                 "# Edit this file to change default settings\n\n"]
        for section, values in config.items():
            lines.append(f"[{section}]\n")
            desc = {
                "unit":           "# Wind speed unit: knots or ms",
                "output_format":  "# Output format: terminal",
                "station_filter": "# Filter by station number (blank = show all)",
                "default_input":  "# Default input file path (blank = none)",
                "show_section3":  "# Show Section 3 data: true or false",
            }
            for k, v in values.items():
                if k in desc: lines.append(f"{desc[k]}\n")
                lines.append(f'{k} = "{v}"\n')
            lines.append("\n")
        with open(CONFIG_FILE, "w") as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"  WARNING: Could not save config: {e}")
        return False

def show_config(config):
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              SYNOP DECODER  –  CURRENT CONFIG               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  Config file : {CONFIG_FILE}")
    print()
    for section, values in config.items():
        print(f"  [{section}]")
        for k, v in values.items():
            print(f"    {k:20s} = {v if v else '(not set)'}")
    print()

def cmd_config(args, config):
    if args.set:
        for pair in args.set:
            if '=' not in pair:
                print(f"  ERROR: Use key=value format."); continue
            k, v = pair.split('=', 1)
            k = k.strip(); v = v.strip()
            if k in config['settings']:
                config['settings'][k] = v
                print(f"  [OK] Set {k} = {v}")
            else:
                print(f"  [!] Unknown key '{k}'. Valid: {list(config['settings'].keys())}")
        save_config(config)
    show_config(config)

# ══════════════════════════════════════════════════════════════════
#  LOOKUP TABLES & HELPERS
# ══════════════════════════════════════════════════════════════════

COMPASS_16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
              "S","SSW","SW","WSW","W","WNW","NW","NNW"]

def dd_to_compass(dd):
    if dd == 0:  return "Calm (0 deg)"
    if dd == 99: return "Variable"
    degrees = dd * 10
    idx = round(degrees / 22.5) % 16
    return f"{COMPASS_16[idx]} ({degrees} deg)"

def knots_to_kmph(kn): return round(kn * 1.852, 1)
def ms_to_kmph(ms):    return round(ms * 3.6, 1)

def decode_temp(sn, TTT):
    t = int(TTT) / 10.0
    return -t if int(sn) == 1 else t

# ── Visibility (Code 25: VV) ──────────────────────────────────────
def decode_vv(vv):
    vv = int(vv)
    if vv == 0:         return "< 0.1 km"
    if 1  <= vv <= 50:  return f"{vv/10:.1f} km"
    if 51 <= vv <= 55:  return "Not used (51-55)"
    if 56 <= vv <= 80:  return f"{vv-50} km"
    if 81 <= vv <= 88:  return f"{(vv-80)*5+30} km"
    if vv == 89:        return "> 70 km"
    # ── Estimated visibility (Code 25 table, your notes) ─────────
    if vv == 90:        return "< 0.05 km (Very thick fog)"
    if vv == 91:        return "0.05 km (Thick fog)"
    if vv == 92:        return "0.2 km (Moderate fog)"
    if vv == 93:        return "0.5 km (Slight fog / thick mist)"
    if vv == 94:        return "1.0 km (Thick mist)"
    if vv == 95:        return "2.0 km (Slight mist)"
    if vv == 96:        return "4.0 km"
    if vv == 97:        return "10 km"
    if vv == 98:        return "20 km"
    if vv == 99:        return ">= 50 km"
    return str(vv)

# ── Cloud Cover (N oktas) ─────────────────────────────────────────
def decode_N(N):
    table = {
        '0':"SKC – Sky clear (0 oktas)",
        '1':"FEW – 1 okta  (1/8)",
        '2':"FEW – 2 oktas (2/8)",
        '3':"SCT – 3 oktas (3/8)",
        '4':"SCT – 4 oktas (4/8)",
        '5':"BKN – 5 oktas (5/8)",
        '6':"BKN – 6 oktas (6/8)",
        '7':"OVC – 7 oktas (7/8)",
        '8':"OVC – Overcast (8 oktas)",
        '9':"Sky obscured or amount indeterminate",
        '/':"Not observed",
    }
    return table.get(str(N), f"Code {N}")

# ── Past Weather W1/W2 (Code 26) ─────────────────────────────────
def decode_W(W):
    """
    Code 26 – W1 and W2 Past Weather
    Per WMO Manual: W2 is always <= W1 (no time sequence implied)
    """
    table = {
        '0': "Cloud covering 1/2 or less of sky throughout the period",
        '1': "Cloud covering more than 1/2 sky during part of period, 1/2 or less during part",
        '2': "Cloud covering more than 1/2 of sky throughout the period",
        '3': "Sandstorm, duststorm or blowing snow",
        '4': "Fog or ice fog or thick haze",
        '5': "Drizzle",
        '6': "Rain",
        '7': "Snow, or rain and snow mixed",
        '8': "Shower(s)",
        '9': "Thunderstorm(s) with or without precipitation",
        '/':"Not observed / missing",
    }
    return table.get(str(W), f"Code {W}")

# ── Present Weather (ww) FULL TABLE ──────────────────────────────
def decode_ww(ww):
    ww = int(ww)
    # 0–9
    if ww == 0:  return "No significant weather"
    if ww == 1:  return "Clouds dissolving / becoming less developed"
    if ww == 2:  return "State of sky unchanged"
    if ww == 3:  return "Clouds forming / developing"
    if ww == 4:  return "Visibility reduced by smoke / ash / haze"
    if ww == 5:  return "Haze"
    if ww == 6:  return "Widespread dust in suspension"
    if ww == 7:  return "Dust or sand raised by wind"
    if ww == 8:  return "Well-developed dust or sand whirls"
    if ww == 9:  return "Dust or sandstorm within sight"
    # 10–19
    if ww == 10: return "Mist"
    if ww == 11: return "Shallow fog in patches"
    if ww == 12: return "Continuous shallow fog"
    if ww == 13: return "Lightning visible, no thunder heard"
    if ww == 14: return "Precipitation within sight, not reaching ground (virga)"
    if ww == 15: return "Precipitation within sight, reaching ground (distant)"
    if ww == 16: return "Precipitation within sight, reaching ground (near)"
    if ww == 17: return "TS – Thunderstorm (no precipitation at station)"
    if ww == 18: return "Squalls"
    if ww == 19: return "Funnel cloud(s) – tornado or waterspout"
    # 20–29 Recent
    if ww == 20: return "Drizzle (not freezing) – recent, not at obs time"
    if ww == 21: return "Rain (not freezing) – recent"
    if ww == 22: return "Snow – recent"
    if ww == 23: return "Rain and snow mixed – recent"
    if ww == 24: return "Freezing drizzle or freezing rain – recent"
    if ww == 25: return "Rain shower(s) – recent"
    if ww == 26: return "Snow shower(s) or rain-and-snow shower(s) – recent"
    if ww == 27: return "Hail shower(s) – recent"
    if ww == 28: return "Fog or ice fog – recent"
    if ww == 29: return "TS – Thunderstorm – recent (past hour)"
    # 30–39
    if ww == 30: return "Slight or moderate duststorm – decreasing"
    if ww == 31: return "Slight or moderate duststorm – no change"
    if ww == 32: return "Slight or moderate duststorm – beginning or increasing"
    if ww == 33: return "Severe duststorm – decreasing"
    if ww == 34: return "Severe duststorm – no change"
    if ww == 35: return "Severe duststorm – beginning or increasing"
    if ww == 36: return "Slight or moderate drifting snow (low)"
    if ww == 37: return "Heavy drifting snow (low)"
    if ww == 38: return "Slight or moderate blowing snow (high)"
    if ww == 39: return "Heavy blowing snow (high)"
    # 40–49 FOG
    if ww == 40: return "FOG – Fog at distance at obs time, not at station during preceding hour; extending above observer level"
    if ww == 41: return "FOG – Fog or ice fog in patches (has become thinner during preceding hour)"
    if ww == 42: return "FOG – Fog or ice fog, sky visible (has become thinner during preceding hour)"
    if ww == 43: return "FOG – Fog or ice fog, sky invisible (has become thinner during preceding hour)"
    if ww == 44: return "FOG – Fog or ice fog, sky visible (no appreciable change during preceding hour)"
    if ww == 45: return "FOG – Fog or ice fog, sky invisible (no appreciable change during preceding hour)"
    if ww == 46: return "FOG – Fog or ice fog, sky visible (has begun or become thicker during preceding hour)"
    if ww == 47: return "FOG – Fog or ice fog, sky invisible (has begun or become thicker during preceding hour)"
    if ww == 48: return "FOG – Fog, depositing rime, sky visible"
    if ww == 49: return "FOG – Fog, depositing rime, sky invisible"
    # 50–59 Drizzle
    if ww == 50: return "Drizzle – intermittent, slight"
    if ww == 51: return "Drizzle – continuous, slight"
    if ww == 52: return "Drizzle – intermittent, moderate"
    if ww == 53: return "Drizzle – continuous, moderate"
    if ww == 54: return "Drizzle – intermittent, heavy"
    if ww == 55: return "Drizzle – continuous, heavy"
    if ww == 56: return "Freezing drizzle – slight"
    if ww == 57: return "Freezing drizzle – moderate or heavy"
    if ww == 58: return "Drizzle and rain – slight"
    if ww == 59: return "Drizzle and rain – moderate or heavy"
    # 60–69 Rain
    if ww == 60: return "Rain – intermittent, slight"
    if ww == 61: return "Rain – continuous, slight"
    if ww == 62: return "Rain – intermittent, moderate"
    if ww == 63: return "Rain – continuous, moderate"
    if ww == 64: return "Rain – intermittent, heavy"
    if ww == 65: return "Rain – continuous, heavy"
    if ww == 66: return "Freezing rain – slight"
    if ww == 67: return "Freezing rain – moderate or heavy"
    if ww == 68: return "Rain or drizzle and snow – slight"
    if ww == 69: return "Rain or drizzle and snow – moderate or heavy"
    # 70–79 Snow
    if ww == 70: return "Snow – intermittent, slight"
    if ww == 71: return "Snow – continuous, slight"
    if ww == 72: return "Snow – intermittent, moderate"
    if ww == 73: return "Snow – continuous, moderate"
    if ww == 74: return "Snow – intermittent, heavy"
    if ww == 75: return "Snow – continuous, heavy"
    if ww == 76: return "Diamond dust (with or without fog)"
    if ww == 77: return "Snow grains (with or without fog)"
    if ww == 78: return "Isolated star-like snow crystals"
    if ww == 79: return "Ice pellets (sleet)"
    # 80–90 Showers
    if ww == 80: return "Rain shower(s) – slight"
    if ww == 81: return "Rain shower(s) – moderate or heavy"
    if ww == 82: return "Rain shower(s) – violent"
    if ww == 83: return "Shower(s) of rain and snow – slight"
    if ww == 84: return "Shower(s) of rain and snow – moderate or heavy"
    if ww == 85: return "Snow shower(s) – slight"
    if ww == 86: return "Snow shower(s) – moderate or heavy"
    if ww == 87: return "Shower(s) of snow pellets or small hail – slight (with or without rain)"
    if ww == 88: return "Shower(s) of snow pellets or small hail – moderate or heavy"
    if ww == 89: return "Hail shower(s) – slight, not associated with thunder"
    if ww == 90: return "Hail shower(s) – moderate or heavy, not associated with thunder"
    # 91–99 THUNDERSTORMS
    if ww == 91: return "TS/TSRA – Slight rain at obs time; thunderstorm during preceding hour but NOT at obs time"
    if ww == 92: return "TS/TSRA – Moderate or heavy rain at obs time; thunderstorm during preceding hour but NOT at obs time"
    if ww == 93: return "TS – Slight snow, or rain and snow, or hail at obs time; thunderstorm during preceding hour but NOT at obs time"
    if ww == 94: return "TS – Moderate or heavy snow, or rain and snow mixed, or hail at obs time; thunderstorm during preceding hour but NOT at obs time"
    if ww == 95: return "TS – Thunderstorm at obs time: slight or moderate, WITHOUT hail, but with rain and/or snow"
    if ww == 96: return "TS – Thunderstorm at obs time: slight or moderate, WITH hail"
    if ww == 97: return "TS – Thunderstorm at obs time: heavy, WITHOUT hail, but with rain and/or snow"
    if ww == 98: return "TS – Thunderstorm combined with duststorm or sandstorm at obs time"
    if ww == 99: return "TSRA – Thunderstorm at obs time: heavy, WITH hail (small hail / snow pellets)"
    return f"Present weather code {ww}"

# ── Cloud Types ───────────────────────────────────────────────────
def decode_cloud_type(CL, CM, CH):
    CL_table = {
        '0':"No CL clouds",
        '1':"Cu humilis or Cu fractus (fair weather)",
        '2':"Cu mediocris or Cu congestus (towering cumulus)",
        '3':"Cb calvus (no cirriform top)",
        '4':"Sc cumulogenitus (spreading from cumulus)",
        '5':"Sc (not cumulogenitus)",
        '6':"St or Fs (not of bad weather)",
        '7':"Fs and/or Fc of bad weather (low ragged clouds)",
        '8':"Cu and Sc at different levels",
        '9':"Cb capillatus (with cirriform top / anvil)",
        '/':"Not observed"
    }
    CM_table = {
        '0':"No CM clouds",
        '1':"As translucidus (thin altostratus)",
        '2':"As opacus or Ns (thick altostratus or nimbostratus)",
        '3':"Ac translucidus (single layer)",
        '4':"Ac translucidus (patchy, changing)",
        '5':"Ac translucidus (bands, spreading/thickening)",
        '6':"Ac cumulogenitus (from spreading cumulus)",
        '7':"Ac (double or multi-layer) or Ac with As or Ns",
        '8':"Ac castellanus or Ac floccus",
        '9':"Ac of chaotic sky",
        '/':"Not observed"
    }
    CH_table = {
        '0':"No CH clouds",
        '1':"Ci fibratus or Ci uncinus (not spreading)",
        '2':"Ci spissatus (dense, not from Cb)",
        '3':"Ci spissatus cumulonimbogenitus (from Cb anvil)",
        '4':"Ci uncinus or Ci fibratus (spreading/thickening)",
        '5':"Ci and/or Cs (below 45 deg above horizon)",
        '6':"Ci and/or Cs (above 45 deg above horizon)",
        '7':"Cs covering the entire sky",
        '8':"Cs not covering the entire sky",
        '9':"Cc alone or dominant",
        '/':"Not observed"
    }
    return (
        f"  Low cloud  (CL={CL}): {CL_table.get(str(CL), str(CL))}\n"
        f"  Mid cloud  (CM={CM}): {CM_table.get(str(CM), str(CM))}\n"
        f"  High cloud (CH={CH}): {CH_table.get(str(CH), str(CH))}"
    )

def decode_h(h):
    table = {
        '0':"< 50 m",      '1':"50-100 m",    '2':"100-200 m",
        '3':"200-300 m",   '4':"300-600 m",    '5':"600-1000 m",
        '6':"1000-1500 m", '7':"1500-2000 m",  '8':"2000-2500 m",
        '9':">= 2500 m or no clouds", '/':"Unknown"
    }
    return table.get(str(h), str(h))

def decode_iR(iR):
    table = {
        '0':"Precipitation included in Section 1 and Section 3",
        '1':"Precipitation included in Section 1 only",
        '2':"Precipitation included in Section 3 only",
        '3':"Precipitation omitted – no precipitation",
        '4':"Precipitation omitted – station not staffed"
    }
    return table.get(str(iR), str(iR))

def decode_iX(iX):
    table = {
        '1':"Manned station – present and past weather included",
        '2':"Manned station – present weather omitted",
        '3':"Manned station – present and past weather omitted",
        '4':"Automatic station – present and past weather included",
        '5':"Automatic station – present weather omitted",
        '6':"Automatic station – present and past weather omitted",
        '7':"Automatic station (type 2) – wx included"
    }
    return table.get(str(iX), str(iX))

def decode_P(PPPP):
    p = int(PPPP)
    return f"{(p+10000)/10.0:.1f} hPa" if p < 5000 else f"{p/10.0:.1f} hPa"

def validate_station(stn):
    if not re.match(r'^\d{5}$', stn):
        return False, "Station number must be exactly 5 digits"
    return True, "OK"

# ══════════════════════════════════════════════════════════════════
#  SECTION DECODERS
# ══════════════════════════════════════════════════════════════════

def decode_section0(header):
    m = re.match(r'AAXX\s+(\d{2})(\d{2})(\d)', header.upper())
    if not m: return {}, '1'
    YY, GG, iw = m.group(1), m.group(2), m.group(3)
    iw_table = {
        '0':'Calm / estimated (knots)', '1':'Anemometer (knots)',
        '3':'Calm / estimated (m/s)',   '4':'Anemometer (m/s)'
    }
    return {'day':YY,'hour':GG,'iw':iw,'iw_desc':iw_table.get(iw,f"iw={iw}")}, iw

def decode_section1(groups, iw='1'):
    out = {}
    i = 0
    # Position 0: iRiXhVV
    if i < len(groups) and re.match(r'^\d{5}$', groups[i]):
        g = groups[i]
        out['iR'] = decode_iR(g[0])
        out['iX'] = decode_iX(g[1])
        out['h']  = decode_h(g[2])
        out['VV'] = decode_vv(g[3:5])
        i += 1
    # Position 1: Nddff
    if i < len(groups) and re.match(r'^\d{5}$', groups[i]):
        g = groups[i]
        N = g[0]; dd = int(g[1:3]); ff = int(g[3:5])
        out['N'] = decode_N(N); out['N_raw'] = N
        out['dd'] = dd; out['dd_compass'] = dd_to_compass(dd)
        if ff == 99:
            i += 1
            if i < len(groups) and groups[i].startswith('00'):
                ff = int(groups[i][2:])
        out['ff_raw']  = ff
        out['ff_unit'] = 'knots' if iw in ('0','1') else 'm/s'
        out['ff_kmph'] = knots_to_kmph(ff) if iw in ('0','1') else ms_to_kmph(ff)
        i += 1
    # Remaining groups
    while i < len(groups):
        g = groups[i]; i += 1
        if not re.match(r'^[\d/]{5}$', g): continue
        c = g[0]
        if   c=='1':
            try: out['T']  = decode_temp(g[1], g[2:5])
            except: pass
        elif c=='2':
            try: out['Td'] = decode_temp(g[1], g[2:5])
            except: pass
        elif c=='3':
            try: out['P_stn'] = decode_P(g[1:])
            except: pass
        elif c=='4':
            try: out['P_slp'] = decode_P(g[1:])
            except: pass
        elif c=='5':
            tend_desc = {
                '0':'Rising then falling','1':'Rising then steady',
                '2':'Rising steadily',    '3':'Rising unsteadily',
                '4':'Steady',             '5':'Falling then rising',
                '6':'Falling then steady','7':'Falling steadily',
                '8':'Falling unsteadily'
            }
            ppp = int(g[2:]) if g[2:].isdigit() else 0
            out['P_tend'] = f"{tend_desc.get(g[1], f'code {g[1]}')}, {ppp/10:.1f} hPa change"
        elif c=='6':
            try:
                RRR = int(g[1:4]); t = g[4]
                t_t = {'1':'6h','2':'12h','3':'18h','4':'24h','5':'1h','6':'2h','7':'3h','9':'unknown'}
                out['RRR'] = f"{'Trace' if RRR>=990 else str(RRR)+' mm'} over {t_t.get(t,'?')}"
            except: pass
        elif c=='7':
            try:
                ww_s = g[1:3]
                if ww_s.isdigit():
                    out['ww_raw'] = int(ww_s)
                    out['ww']     = decode_ww(int(ww_s))
                # W1 and W2 – decode using Code 26
                out['W1']     = g[3]
                out['W2']     = g[4]
                out['W1_desc']= decode_W(g[3])
                out['W2_desc']= decode_W(g[4])
            except: pass
        elif c=='8':
            out['Nh_raw']=g[1]; out['Nh']=decode_N(g[1])
            out['CL']=g[2]; out['CM']=g[3]; out['CH']=g[4]
        elif c=='9':
            if g[1:3].isdigit() and g[3:5].isdigit():
                out['exact_time'] = f"{g[1:3]}h {g[3:5]}min UTC"
    return out

def decode_section3(groups):
    out = {}
    for g in groups:
        if not re.match(r'^[\d/]{5}$', g): continue
        c = g[0]
        if   c=='1':
            try: out['Tx'] = decode_temp(g[1], g[2:5])
            except: pass
        elif c=='2':
            try: out['Tn'] = decode_temp(g[1], g[2:5])
            except: pass
        elif c=='3': out['snow']     = f"Snow/ground state code: {g[1:]}"
        elif c=='4': out['ground']   = f"Ground surface state/temp code: {g[1:]}"
        elif c=='5': out['sunshine'] = f"Sunshine duration code: {g[1:]}"
        elif c=='6':
            try:
                RRR = int(g[1:4]); t = g[4]
                t_t = {'1':'6h','2':'12h','3':'18h','4':'24h','5':'1h','6':'2h','7':'3h','9':'unknown'}
                out['RRR_s3'] = f"{'Trace' if RRR>=990 else str(RRR)+' mm'} over {t_t.get(t,'?')}"
            except: pass
        elif c=='7': out['R24'] = f"Daily precipitation group: {g}"
    return out

# ══════════════════════════════════════════════════════════════════
#  MAIN DECODE  –  HARD STOP ON NON-AAXX
# ══════════════════════════════════════════════════════════════════

def decode_synop(raw):
    raw = raw.strip().replace('`n', '\n')
    if not raw: return None, ["ERROR: Empty input."]

    tokens = raw.replace('\n', ' ').split()
    if not tokens: return None, ["ERROR: Empty input."]

    # HARD STOP if not AAXX
    if tokens[0].upper() != 'AAXX':
        return None, [
            f"ERROR: Message must start with 'AAXX' (or 'aaxx').",
            f"         Got      : '{tokens[0]}'",
            f"         Expected : AAXX YYGGiw  (e.g. AAXX 06091)"
        ]

    header_line = f"{tokens[0]} {tokens[1]}" if len(tokens) > 1 and re.match(r'^\d{5}$', tokens[1]) else tokens[0]
    errors = []; result = {}

    if not re.match(r'^(?i:AAXX)\s+\d{5}$', header_line):
        errors.append(f"ERROR: AAXX header format invalid. Got: '{header_line}'")

    hdr, iw = decode_section0(header_line)
    result['header'] = hdr

    rest_tokens = tokens[2:] if len(tokens) > 2 else []
    main_groups = []; sec3_groups = []
    if '333' in rest_tokens:
        idx = rest_tokens.index('333')
        main_groups = rest_tokens[:idx]
        sec3_groups = rest_tokens[idx+1:]
    else:
        main_groups = rest_tokens

    if not main_groups:
        errors.append("ERROR: No observation data found after header.")
        return result, errors

    stn = main_groups[0]
    ok, msg = validate_station(stn)
    if not ok: errors.append(f"ERROR: {msg} (got '{stn}')")
    result['station'] = stn
    result['section1'] = decode_section1(main_groups[1:], iw)
    if sec3_groups:
        result['section3'] = decode_section3(sec3_groups)
    return result, errors

# ══════════════════════════════════════════════════════════════════
#  BATCH PROCESSOR
# ══════════════════════════════════════════════════════════════════

def extract_synop_blocks(text):
    lines = text.splitlines()
    blocks = []; i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r'^(?i:AAXX)\s+\d{5}$', line):
            block_lines = [line]; start_line = i + 1; i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if re.match(r'^(BBXX|OOXX|METAR|SPECI|TAF|TEMP|PILOT|TTXX|SHIP)\b', nxt, re.I): break
                if re.match(r'^(?i:AAXX)\s+\d{5}$', nxt): break
                block_lines.append(nxt); i += 1
            blocks.append(('\n'.join(block_lines), start_line))
        else:
            i += 1
    return blocks

def cmd_batch(args, config):
    filepath = args.file
    if not os.path.exists(filepath):
        print(f"\n  ERROR: File not found: '{filepath}'\n"); return
    try:
        with open(filepath, 'r', errors='ignore') as f:
            text = f.read()
    except Exception as e:
        print(f"\n  ERROR reading file: {e}\n"); return

    blocks = extract_synop_blocks(text)
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              SYNOP BATCH DECODER – FILE SCAN                ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  File    : {filepath}")
    print(f"  Total lines in file : {len(text.splitlines())}")
    print(f"  AAXX SYNOP blocks found : {len(blocks)}")

    if not blocks:
        print("\n  [!] No AAXX SYNOP blocks found in this file.\n"); return

    station_filter = config['settings'].get('station_filter','').strip()
    show_s3        = config['settings'].get('show_section3','true').lower() == 'true'
    decoded_count  = 0; skipped_count = 0

    for idx, (block, line_no) in enumerate(blocks, 1):
        result, errors = decode_synop(block)
        if station_filter and result and result.get('station') != station_filter:
            skipped_count += 1; continue
        print()
        print(f"  {'─'*60}")
        print(f"  Block {idx} / {len(blocks)}  (starts at line {line_no})")
        print(f"  {'─'*60}")
        print("  Raw:")
        for raw_line in block.splitlines(): print(f"    {raw_line}")
        print()
        print_result(result, errors, show_s3=show_s3)
        decoded_count += 1

    print()
    print(f"  [OK] Decoded : {decoded_count} block(s)")
    if skipped_count:
        print(f"  [SKIPPED] {skipped_count} block(s) (station filter = {station_filter})")
    print()

# ══════════════════════════════════════════════════════════════════
#  PRETTY PRINTER
# ══════════════════════════════════════════════════════════════════

def print_result(result, errors, show_s3=True):
    W = 64
    print()
    print("  ╔" + "═"*(W-2) + "╗")
    print("  ║" + "SYNOP FM-12 SURFACE CODE DECODER".center(W-2) + "║")
    print("  ╚" + "═"*(W-2) + "╝")
    print()

    if errors:
        for e in errors:
            for line in e.splitlines(): print(f"  [!]  {line}")
        print()
        if not result or 'station' not in result: return

    stn = result.get('station','?')
    print(f"  Station        : {stn}")
    hdr = result.get('header',{})
    if hdr:
        print(f"  Date / Time    : Day {hdr.get('day','?')} of month, {hdr.get('hour','?')}:00 UTC")
        print(f"  Wind measured  : {hdr.get('iw_desc','?')}")

    s1 = result.get('section1',{})
    if s1:
        print()
        print("  ┌─ SECTION 1 : SURFACE OBSERVATIONS " + "─"*(W-38) + "┐")
        if 'VV'     in s1: print(f"  │  Visibility          : {s1['VV']}")
        if 'N'      in s1: print(f"  │  Total cloud cover   : {s1['N']}")
        if 'dd'     in s1: print(f"  │  Wind direction      : {s1['dd_compass']}")
        if 'ff_raw' in s1: print(f"  │  Wind speed          : {s1['ff_raw']} {s1['ff_unit']} = {s1['ff_kmph']} km/h")
        if 'T'      in s1: print(f"  │  Dry bulb temp  (T)  : {s1['T']:.1f} degC")
        if 'Td'     in s1:
            print(f"  │  Dew point temp (Td) : {s1['Td']:.1f} degC")
            if 'T' in s1:
                rh = 100*(112 - 0.1*s1['T'] + s1['Td'])/(112 + 0.9*s1['T'])
                print(f"  │  Rel. humidity   (~) : {max(0,min(100,rh)):.0f}%")
        if 'P_stn'  in s1: print(f"  │  Station pressure    : {s1['P_stn']}")
        if 'P_slp'  in s1: print(f"  │  Sea-level pressure  : {s1['P_slp']}")
        if 'P_tend' in s1: print(f"  │  Pressure tendency   : {s1['P_tend']}")
        if 'RRR'    in s1: print(f"  │  Precipitation       : {s1['RRR']}")
        if 'ww'     in s1: print(f"  │  Present weather     : {s1['ww']}  [ww={s1.get('ww_raw','')}]")
        # W1/W2 now with full Code 26 descriptions
        if 'W1' in s1:
            print(f"  │  Past weather (W1)   : {s1['W1_desc']}  [W1={s1['W1']}]")
            print(f"  │  Past weather (W2)   : {s1['W2_desc']}  [W2={s1['W2']}]")
        print(f"  │  Precip data flag    : {s1.get('iR','?')}")
        print(f"  │  Station type        : {s1.get('iX','?')}")
        if 'h'  in s1: print(f"  │  Lowest cloud base   : {s1['h']}")
        if 'Nh' in s1: print(f"  │  Lowest layer (Nh)   : {s1['Nh']}")
        if 'CL' in s1:
            print(f"  │  Cloud types         :")
            for cl in decode_cloud_type(s1['CL'],s1['CM'],s1['CH']).splitlines():
                print(f"  │  {cl}")
        if 'exact_time' in s1:
            print(f"  │  Exact obs time      : {s1['exact_time']}")
        print("  └" + "─"*(W-4) + "┘")

    if show_s3:
        s3 = result.get('section3',{})
        if s3:
            print()
            print("  ┌─ SECTION 3 : ADDITIONAL DATA " + "─"*(W-32) + "┐")
            if 'Tx'     in s3: print(f"  │  Max temp (past 12h) : {s3['Tx']:.1f} degC")
            if 'Tn'     in s3: print(f"  │  Min temp (past 12h) : {s3['Tn']:.1f} degC")
            if 'RRR_s3' in s3: print(f"  │  Precipitation       : {s3['RRR_s3']}")
            if 'sunshine'in s3: print(f"  │  Sunshine            : {s3['sunshine']}")
            if 'snow'   in s3: print(f"  │  {s3['snow']}")
            if 'ground' in s3: print(f"  │  {s3['ground']}")
            if 'R24'    in s3: print(f"  │  {s3['R24']}")
            print("  └" + "─"*(W-4) + "┘")
    print()

# ══════════════════════════════════════════════════════════════════
#  INTERACTIVE ENCODER
# ══════════════════════════════════════════════════════════════════

def interactive_encode_and_decode():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          SYNOP INTERACTIVE ENCODER + DECODER                ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print("  Enter observation details. Press Enter to skip optional fields.")
    print()

    enc_errors = []

    stn = input("  1. Station number (5 digits, e.g. 43279): ").strip()
    if not re.match(r'^\d{5}$', stn):
        enc_errors.append(f"[!] Station '{stn}' is not valid.")

    print()
    print("  2. Wind  –  direction in degrees (0=N 90=E 180=S 270=W) and speed in km/h")
    wind_raw = input("     e.g. '140 37': ").strip()
    dd_code = 0; ff_knots = 0
    if wind_raw:
        parts = wind_raw.split()
        if len(parts) == 2:
            try:
                deg = float(parts[0]); kmph = float(parts[1])
                dd_code  = round(deg/10) if deg > 0 else 0
                if dd_code >= 36: dd_code = 0
                ff_knots = round(kmph/1.852)
                print(f"     → {dd_to_compass(dd_code)}, {ff_knots} knots ({kmph:.1f} km/h)")
            except: enc_errors.append("[!] Wind error. Use: <degrees> <km/h>")
        else: enc_errors.append("[!] Wind: two values needed.")

    print()
    temp_raw = input("  3. Dry bulb temperature degC (e.g. 39.0): ").strip()
    T_enc = None
    if temp_raw:
        try:
            T_val = float(temp_raw)
            T_enc = f"1{1 if T_val<0 else 0}{round(abs(T_val)*10):03d}"
        except: enc_errors.append("[!] Temperature must be a number.")

    td_raw = input("  3b. Dew point degC (optional): ").strip()
    Td_enc = None
    if td_raw:
        try:
            Td = float(td_raw)
            Td_enc = f"2{1 if Td<0 else 0}{round(abs(Td)*10):03d}"
        except: enc_errors.append("[!] Dew point must be a number.")

    print()
    print("  4. Present weather (keyword or ww code 0-99):")
    print("     clear  haze  mist  fog  fog_patch  fog_sky  fog_rime  fog_rime_inv")
    print("     drizzle  rain  snow  shower  hail")
    print("     ts  ts_hail  ts_heavy  tsra  tsra_heavy")
    wx_raw = input("     Weather: ").strip().lower()
    wx_map = {
        'clear':0,'haze':5,'mist':10,
        'fog':45,'fog_patch':41,'fog_sky':44,'fog_rime':48,'fog_rime_inv':49,
        'drizzle':53,'rain':63,'snow':73,'shower':80,'hail':89,
        'ts':95,'ts_hail':96,'ts_heavy':97,'tsra':95,'tsra_heavy':99
    }
    ww_code = None
    if wx_raw:
        if wx_raw in wx_map:
            ww_code = wx_map[wx_raw]
            print(f"     → ww={ww_code}: {decode_ww(ww_code)}")
        else:
            try:
                ww_code = int(wx_raw)
                if 0<=ww_code<=99: print(f"     → ww={ww_code}: {decode_ww(ww_code)}")
                else: enc_errors.append("[!] ww must be 0-99."); ww_code=None
            except: enc_errors.append(f"[!] Unknown weather '{wx_raw}'.")

    print()
    print("  5. Cloud cover oktas (0=Clear 1-2=FEW 3-4=SCT 5-6=BKN 7-8=OVC 9=Obscured):")
    N_raw = input("     Oktas (0-9): ").strip()
    N_code = 0
    if N_raw:
        try:
            N_code = int(N_raw)
            if not 0<=N_code<=9: enc_errors.append("[!] Oktas 0-9."); N_code=0
            else: print(f"     → {decode_N(N_code)}")
        except: enc_errors.append("[!] Oktas must be 0-9.")

    print()
    print("  5b. Cloud types (optional):")
    print("     CL: 0=None 1=Cu 2=Cu tower 3=Cb 4=Sc(Cu) 5=Sc 6=St 7=Fs 8=Cu+Sc 9=Cb(anvil)")
    print("     CM: 0=None 1=As 2=As/Ns 3=Ac 4=Ac patch 5=Ac band 6=Ac(Cu) 7=Ac multi 8=Ac cas 9=Ac chaos")
    print("     CH: 0=None 1=Ci 2=Ci dense 3=Ci anvil 4=Ci incr 5=Ci/Cs<45 6=Ci/Cs>45 7=Cs all 8=Cs part 9=Cc")
    CL = input("     CL (0-9 or /): ").strip() or '/'
    CM = input("     CM (0-9 or /): ").strip() or '/'
    CH = input("     CH (0-9 or /): ").strip() or '/'

    print()
    print("  5c. Lowest cloud base height:")
    print("     0=<50m 1=50-100m 2=100-200m 3=200-300m 4=300-600m 5=600-1000m 6=1-1.5km 7=1.5-2km 8=2-2.5km 9>=2.5km")
    h_raw  = input("     Code (0-9 or /): ").strip() or '/'
    h_code = h_raw if h_raw in '0123456789/' else '/'

    print()
    tx_raw = input("  6. Max temperature past 12h degC (optional): ").strip()
    Tx_enc = None
    if tx_raw:
        try:
            Tx = float(tx_raw)
            Tx_enc = f"1{1 if Tx<0 else 0}{round(abs(Tx)*10):03d}"
        except: enc_errors.append("[!] Max temp must be a number.")

    tn_raw = input("  6b. Min temperature past 12h degC (optional): ").strip()
    Tn_enc = None
    if tn_raw:
        try:
            Tn = float(tn_raw)
            Tn_enc = f"2{1 if Tn<0 else 0}{round(abs(Tn)*10):03d}"
        except: enc_errors.append("[!] Min temp must be a number.")

    now   = datetime.datetime.utcnow()
    synop = f"AAXX {now.strftime('%d%H')}1\n"
    groups = [stn, f"31{h_code}97", f"{N_code}{dd_code:02d}{ff_knots:02d}"]
    if T_enc:               groups.append(T_enc)
    if Td_enc:              groups.append(Td_enc)
    if ww_code is not None: groups.append(f"7{ww_code:02d}//")
    groups.append(f"8{N_code}{CL}{CM}{CH}")
    synop += " ".join(groups)
    sec3 = []
    if Tx_enc: sec3.append(Tx_enc)
    if Tn_enc: sec3.append(Tn_enc)
    if sec3: synop += "\n333\n" + " ".join(sec3)

    print()
    print("  ┌─ GENERATED SYNOP CODE ──────────────────────────────────┐")
    for line in synop.splitlines(): print(f"  │  {line}")
    print("  └─────────────────────────────────────────────────────────┘")
    if enc_errors:
        print()
        for e in enc_errors: print(f"  {e}")
    print()
    print("  ── DECODING GENERATED SYNOP ─────────────────────────────")
    decoded, dec_errors = decode_synop(synop)
    print_result(decoded, dec_errors)

# ══════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════

def result_to_json(result, errors):
    """Convert decoded result dict to clean JSON-serializable dict."""
    if not result:
        return {"status": "error", "errors": errors}

    s1 = result.get('section1', {})
    s3 = result.get('section3', {})
    hdr = result.get('header', {})

    output = {
        "status":   "ok" if not errors else "warning",
        "errors":   errors if errors else [],
        "station":  result.get('station', None),
        "header": {
            "day":          hdr.get('day', None),
            "hour_utc":     hdr.get('hour', None),
            "wind_unit":    hdr.get('iw_desc', None),
        },
        "section1": {
            "visibility":           s1.get('VV', None),
            "cloud_cover":          s1.get('N', None),
            "wind_direction_deg":   s1.get('dd', None) * 10 if s1.get('dd') is not None else None,
            "wind_direction_compass": s1.get('dd_compass', None),
            "wind_speed_knots":     s1.get('ff_raw', None),
            "wind_speed_kmph":      s1.get('ff_kmph', None),
            "wind_unit":            s1.get('ff_unit', None),
            "temp_dry_bulb_c":      s1.get('T', None),
            "temp_dew_point_c":     s1.get('Td', None),
            "humidity_pct":         round(max(0, min(100, 100*(112 - 0.1*s1['T'] + s1['Td'])/(112 + 0.9*s1['T'])))) if 'T' in s1 and 'Td' in s1 else None,
            "pressure_station_hpa": s1.get('P_stn', None),
            "pressure_slp_hpa":     s1.get('P_slp', None),
            "pressure_tendency":    s1.get('P_tend', None),
            "precipitation":        s1.get('RRR', None),
            "present_weather_code": s1.get('ww_raw', None),
            "present_weather_desc": s1.get('ww', None),
            "past_weather_W1_code": s1.get('W1', None),
            "past_weather_W1_desc": s1.get('W1_desc', None),
            "past_weather_W2_code": s1.get('W2', None),
            "past_weather_W2_desc": s1.get('W2_desc', None),
            "cloud_base_height":    s1.get('h', None),
            "cloud_cover_lowest":   s1.get('Nh', None),
            "cloud_low_CL":         s1.get('CL', None),
            "cloud_mid_CM":         s1.get('CM', None),
            "cloud_high_CH":        s1.get('CH', None),
            "precip_flag":          s1.get('iR', None),
            "station_type":         s1.get('iX', None),
            "exact_obs_time":       s1.get('exact_time', None),
        },
        "section3": {
            "max_temp_c":       s3.get('Tx', None),
            "min_temp_c":       s3.get('Tn', None),
            "precipitation":    s3.get('RRR_s3', None),
            "sunshine":         s3.get('sunshine', None),
            "snow_ground":      s3.get('snow', None),
        } if s3 else {}
    }
    return output

# ══════════════════════════════════════════════════════════════════
#  FLASK REST API
# ══════════════════════════════════════════════════════════════════

def run_api(host='0.0.0.0', port=5000):
    """Start Flask REST API server."""
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        print("\n  ERROR: Flask not installed.")
        print("  Run: pip install flask\n")
        return

    app = Flask(__name__)

    @app.route('/', methods=['GET'])
    def index():
        return jsonify({
            "service": "SYNOP FM-12 Decoder API",
            "version": "1.0",
            "endpoints": {
                "GET  /decode?synop=AAXX+...": "Decode a SYNOP message",
                "POST /decode  body:{synop:...}": "Decode via POST",
                "POST /batch   body:{synops:[...]}": "Decode multiple messages",
                "GET  /health": "Health check"
            }
        })

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "ok", "service": "SYNOP Decoder"})

    @app.route('/decode', methods=['GET', 'POST'])
    def decode_endpoint():
        # GET: /decode?synop=AAXX 06091 43279 ...
        # POST: {"synop": "AAXX 06091 43279 ..."}
        if request.method == 'GET':
            raw = request.args.get('synop', '').replace('+', ' ')
        else:
            data = request.get_json(silent=True) or {}
            raw  = data.get('synop', '')

        if not raw or not raw.strip():
            return jsonify({"status": "error", "message": "No SYNOP provided. Use ?synop=AAXX ..."}), 400

        raw = raw.replace('\\n', '\n')
        result, errors = decode_synop(raw)
        output = result_to_json(result, errors)

        if result is None:
            return jsonify(output), 400
        return jsonify(output), 200

    @app.route('/batch', methods=['POST'])
    def batch_endpoint():
        # POST: {"synops": ["AAXX ...", "AAXX ..."]}
        # OR:   {"text": "full text file contents with mixed codes"}
        data = request.get_json(silent=True) or {}

        results = []

        # Option 1: list of SYNOP strings
        if 'synops' in data:
            for raw in data['synops']:
                raw = raw.replace('\\n', '\n')
                result, errors = decode_synop(raw)
                results.append(result_to_json(result, errors))

        # Option 2: raw text (like a full file with mixed codes)
        elif 'text' in data:
            blocks = extract_synop_blocks(data['text'])
            for block, line_no in blocks:
                result, errors = decode_synop(block)
                j = result_to_json(result, errors)
                j['source_line'] = line_no
                results.append(j)
        else:
            return jsonify({"status":"error","message":"Provide 'synops' list or 'text' field"}), 400

        return jsonify({
            "status":  "ok",
            "count":   len(results),
            "results": results
        }), 200

    import builtins
    builtins.print(f"\n  SYNOP Decoder API starting...")
    builtins.print(f"  URL  : http://localhost:{port}")
    builtins.print(f"  Test : http://localhost:{port}/decode?synop=AAXX+06091+43279+32597+31410+10390+20264+30018+40035+83400+333+10264")
    builtins.print(f"  Stop : Press Ctrl+C\n")
    app.run(host=host, port=port, debug=False)


def save_output(data, path, fmt):
    """Save output to txt or json file."""
    try:
        if fmt == 'json':
            with open(path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        else:
            with open(path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(str(data))
        import builtins
        builtins.print(f"  [OK] Saved to: {path}")
    except Exception as e:
        import builtins
        builtins.print(f"  [!] Could not save: {e}")

def main():
    config = load_config()

    parser = argparse.ArgumentParser(
        prog='synop',
        description='SYNOP FM-12 Surface Code Decoder / Encoder',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
COMMANDS:
  synop decode AAXX 06091 43279 32597 31410 10390 20264 30018 40035 83400 333 10264
  synop decode AAXX 06091 43279 ... --json
  synop decode AAXX 06091 43279 ... --save output.json
  synop decode AAXX 06091 43279 ... --save output.txt
  synop decode -f obs.txt
  synop batch  -f messages.txt
  synop batch  -f messages.txt --json
  synop batch  -f messages.txt --save results.json
  synop encode
  synop config
  synop config --set station_filter=43279
  synop api
  synop api --port 8080
  synop help
        """
    )
    sub = parser.add_subparsers(dest='cmd')

    dec_p = sub.add_parser('decode', help='Decode a SYNOP message')
    dec_p.add_argument('message', nargs='*', help='SYNOP tokens')
    dec_p.add_argument('-f','--file',  help='Read from file')
    dec_p.add_argument('--json',       action='store_true', help='Output as JSON')
    dec_p.add_argument('--save',       help='Save output to file (.json or .txt)')

    bat_p = sub.add_parser('batch', help='Scan file for all AAXX blocks')
    bat_p.add_argument('-f','--file',  required=True, help='Input text file')
    bat_p.add_argument('--set',        nargs='*', help='Override config key=value')
    bat_p.add_argument('--json',       action='store_true', help='Output as JSON')
    bat_p.add_argument('--save',       help='Save output to file (.json or .txt)')

    sub.add_parser('encode', help='Interactive encoder + decoder')

    cfg_p = sub.add_parser('config', help='Show or set configuration')
    cfg_p.add_argument('--set', nargs='*', help='Set key=value')

    api_p = sub.add_parser('api', help='Start Flask REST API server')
    api_p.add_argument('--port', type=int, default=5000, help='Port number (default 5000)')
    api_p.add_argument('--host', default='0.0.0.0', help='Host (default 0.0.0.0)')

    sub.add_parser('help', help='Show help')

    args = parser.parse_args()

    # ── decode ──────────────────────────────────────────────────
    if args.cmd == 'decode':
        if getattr(args,'file',None):
            try:
                with open(args.file,'r',errors='ignore') as f: text = f.read()
            except Exception as e:
                print(f"\n  ERROR reading file: {e}\n"); sys.exit(1)
            blocks = extract_synop_blocks(text)
            if not blocks:
                print(f"\n  [!] No AAXX SYNOP blocks found in: {args.file}\n"); sys.exit(1)
            all_json = []
            for idx, (block, line_no) in enumerate(blocks, 1):
                result, errors = decode_synop(block)
                if args.json or (args.save and args.save.endswith('.json')):
                    all_json.append(result_to_json(result, errors))
                else:
                    if len(blocks) > 1:
                        print(f"\n  -- AAXX block {idx} (line {line_no}) --")
                    print_result(result, errors)
            if all_json:
                import builtins
                builtins.print(json.dumps(all_json if len(all_json)>1 else all_json[0], indent=2, default=str))
                if args.save:
                    save_output(all_json if len(all_json)>1 else all_json[0], args.save, 'json')
            return

        raw = None
        if getattr(args,'message',None):
            raw = " ".join(args.message)
            raw = raw.replace('\\n','\n').replace('`n','\n')
        else:
            print("  Paste SYNOP (Ctrl+D / Ctrl+Z when done):")
            raw = sys.stdin.read()
        if not raw or not raw.strip():
            print("\n  ERROR: No SYNOP message provided.\n"); sys.exit(1)

        result, errors = decode_synop(raw)

        # JSON output
        if args.json or (args.save and args.save.endswith('.json')):
            j = result_to_json(result, errors)
            import builtins
            builtins.print(json.dumps(j, indent=2, default=str))
            if args.save:
                save_output(j, args.save, 'json')
        else:
            # Text output
            if args.save and args.save.endswith('.txt'):
                import io, builtins
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                print_result(result, errors)
                text_out = sys.stdout.getvalue()
                sys.stdout = old_stdout
                save_output(text_out, args.save, 'txt')
                builtins.print(text_out, end='')
            else:
                print_result(result, errors)

    # ── batch ───────────────────────────────────────────────────
    elif args.cmd == 'batch':
        if getattr(args,'set',None):
            for pair in args.set:
                if '=' in pair:
                    k,v = pair.split('=',1)
                    if k.strip() in config['settings']:
                        config['settings'][k.strip()] = v.strip()

        if args.json or (getattr(args,'save',None) and args.save.endswith('.json')):
            # JSON batch output
            filepath = args.file
            if not os.path.exists(filepath):
                print(f"\n  ERROR: File not found: '{filepath}'\n"); return
            with open(filepath,'r',errors='ignore') as f: text = f.read()
            blocks = extract_synop_blocks(text)
            station_filter = config['settings'].get('station_filter','').strip()
            all_results = []
            for block, line_no in blocks:
                result, errors = decode_synop(block)
                if station_filter and result and result.get('station') != station_filter:
                    continue
                j = result_to_json(result, errors)
                j['source_line'] = line_no
                all_results.append(j)
            output = {"count": len(all_results), "results": all_results}
            import builtins
            builtins.print(json.dumps(output, indent=2, default=str))
            if getattr(args,'save',None):
                save_output(output, args.save, 'json')
        else:
            # Normal terminal batch + optional txt save
            if getattr(args,'save',None) and args.save.endswith('.txt'):
                import io, builtins
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                cmd_batch(args, config)
                text_out = sys.stdout.getvalue()
                sys.stdout = old_stdout
                save_output(text_out, args.save, 'txt')
                builtins.print(text_out, end='')
            else:
                cmd_batch(args, config)

    # ── encode ──────────────────────────────────────────────────
    elif args.cmd == 'encode':
        interactive_encode_and_decode()

    # ── config ──────────────────────────────────────────────────
    elif args.cmd == 'config':
        cmd_config(args, config)

    # ── api ─────────────────────────────────────────────────────
    elif args.cmd == 'api':
        run_api(host=args.host, port=args.port)

    # ── help ────────────────────────────────────────────────────
    else:
        parser.print_help()

if __name__ == '__main__':
    main()

# ══════════════════════════════════════════════════════════════════
#  RESULT TO JSON CONVERTER
# ══════════════════════════════════════════════════════════════════

#!/usr/bin/env python3
"""
SYNOP FM-12 Surface Code Decoder & Encoder
WMO Manual on Codes, Volume I.1
"""

import sys
import re
import argparse
import datetime
import os
import json

# Output wrapper to avoid Unicode encode errors
SAFE_PRINT_TRANSLATION = str.maketrans({
    '╔':'+','╗':'+','╚':'+','╝':'+','║':'|','│':'|',
    '═':'-','─':'-','┌':'+','┐':'+','└':'+','┘':'+',
    '–':'-','—':'-','✔':'[OK]','✓':'[OK]','⚠':'[!]',
    '📍':'Station:','📅':'Date / Time:','💨':'Wind measured:',
    '✅':'[OK]','⏭':'[SKIPPED]','°':'deg','·':'*','•':'*'
})

def safe_print(*args, sep=' ', end='\n', file=sys.stdout, flush=False):
    text = sep.join(str(a) for a in args) + end
    text = text.translate(SAFE_PRINT_TRANSLATION)
    try:
        file.write(text)
    except Exception:
        file.write(text.encode(getattr(file,'encoding','utf-8') or 'utf-8',
                               errors='replace').decode('utf-8', errors='replace'))
    if flush:
        try: file.flush()
        except: pass

print = safe_print

# ══════════════════════════════════════════════════════════════════
#  TOML CONFIG
# ══════════════════════════════════════════════════════════════════

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synop_config.toml")

DEFAULT_CONFIG = {
    "settings": {
        "unit":           "knots",
        "output_format":  "terminal",
        "station_filter": "",
        "default_input":  "",
        "show_section3":  "true",
    }
}

def load_config():
    config = {k: dict(v) for k, v in DEFAULT_CONFIG.items()}
    if not os.path.exists(CONFIG_FILE):
        save_config(config)
        return config
    try:
        with open(CONFIG_FILE, "r") as f:
            lines = f.readlines()
        section = None
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"): continue
            m = re.match(r'^\[(\w+)\]$', line)
            if m:
                section = m.group(1)
                if section not in config: config[section] = {}
                continue
            m = re.match(r'^(\w+)\s*=\s*"?(.*?)"?\s*$', line)
            if m and section:
                config[section][m.group(1)] = m.group(2)
    except Exception:
        pass
    return config

def save_config(config):
    try:
        lines = ["# SYNOP Decoder Configuration File\n",
                 "# Edit this file to change default settings\n\n"]
        for section, values in config.items():
            lines.append(f"[{section}]\n")
            desc = {
                "unit":           "# Wind speed unit: knots or ms",
                "output_format":  "# Output format: terminal",
                "station_filter": "# Filter by station number (blank = show all)",
                "default_input":  "# Default input file path (blank = none)",
                "show_section3":  "# Show Section 3 data: true or false",
            }
            for k, v in values.items():
                if k in desc: lines.append(f"{desc[k]}\n")
                lines.append(f'{k} = "{v}"\n')
            lines.append("\n")
        with open(CONFIG_FILE, "w") as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"  WARNING: Could not save config: {e}")
        return False

def show_config(config):
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              SYNOP DECODER  –  CURRENT CONFIG               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  Config file : {CONFIG_FILE}")
    print()
    for section, values in config.items():
        print(f"  [{section}]")
        for k, v in values.items():
            print(f"    {k:20s} = {v if v else '(not set)'}")
    print()

def cmd_config(args, config):
    if args.set:
        for pair in args.set:
            if '=' not in pair:
                print(f"  ERROR: Use key=value format."); continue
            k, v = pair.split('=', 1)
            k = k.strip(); v = v.strip()
            if k in config['settings']:
                config['settings'][k] = v
                print(f"  [OK] Set {k} = {v}")
            else:
                print(f"  [!] Unknown key '{k}'. Valid: {list(config['settings'].keys())}")
        save_config(config)
    show_config(config)

# ══════════════════════════════════════════════════════════════════
#  LOOKUP TABLES & HELPERS
# ══════════════════════════════════════════════════════════════════

COMPASS_16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
              "S","SSW","SW","WSW","W","WNW","NW","NNW"]

def dd_to_compass(dd):
    if dd == 0:  return "Calm (0 deg)"
    if dd == 99: return "Variable"
    degrees = dd * 10
    idx = round(degrees / 22.5) % 16
    return f"{COMPASS_16[idx]} ({degrees} deg)"

def knots_to_kmph(kn): return round(kn * 1.852, 1)
def ms_to_kmph(ms):    return round(ms * 3.6, 1)

def decode_temp(sn, TTT):
    t = int(TTT) / 10.0
    return -t if int(sn) == 1 else t

# ── Visibility (Code 25: VV) ──────────────────────────────────────
def decode_vv(vv):
    vv = int(vv)
    if vv == 0:         return "< 0.1 km"
    if 1  <= vv <= 50:  return f"{vv/10:.1f} km"
    if 51 <= vv <= 55:  return "Not used (51-55)"
    if 56 <= vv <= 80:  return f"{vv-50} km"
    if 81 <= vv <= 88:  return f"{(vv-80)*5+30} km"
    if vv == 89:        return "> 70 km"
    # ── Estimated visibility (Code 25 table, your notes) ─────────
    if vv == 90:        return "< 0.05 km (Very thick fog)"
    if vv == 91:        return "0.05 km (Thick fog)"
    if vv == 92:        return "0.2 km (Moderate fog)"
    if vv == 93:        return "0.5 km (Slight fog / thick mist)"
    if vv == 94:        return "1.0 km (Thick mist)"
    if vv == 95:        return "2.0 km (Slight mist)"
    if vv == 96:        return "4.0 km"
    if vv == 97:        return "10 km"
    if vv == 98:        return "20 km"
    if vv == 99:        return ">= 50 km"
    return str(vv)

# ── Cloud Cover (N oktas) ─────────────────────────────────────────
def decode_N(N):
    table = {
        '0':"SKC – Sky clear (0 oktas)",
        '1':"FEW – 1 okta  (1/8)",
        '2':"FEW – 2 oktas (2/8)",
        '3':"SCT – 3 oktas (3/8)",
        '4':"SCT – 4 oktas (4/8)",
        '5':"BKN – 5 oktas (5/8)",
        '6':"BKN – 6 oktas (6/8)",
        '7':"OVC – 7 oktas (7/8)",
        '8':"OVC – Overcast (8 oktas)",
        '9':"Sky obscured or amount indeterminate",
        '/':"Not observed",
    }
    return table.get(str(N), f"Code {N}")

# ── Past Weather W1/W2 (Code 26) ─────────────────────────────────
def decode_W(W):
    """
    Code 26 – W1 and W2 Past Weather
    Per WMO Manual: W2 is always <= W1 (no time sequence implied)
    """
    table = {
        '0': "Cloud covering 1/2 or less of sky throughout the period",
        '1': "Cloud covering more than 1/2 sky during part of period, 1/2 or less during part",
        '2': "Cloud covering more than 1/2 of sky throughout the period",
        '3': "Sandstorm, duststorm or blowing snow",
        '4': "Fog or ice fog or thick haze",
        '5': "Drizzle",
        '6': "Rain",
        '7': "Snow, or rain and snow mixed",
        '8': "Shower(s)",
        '9': "Thunderstorm(s) with or without precipitation",
        '/':"Not observed / missing",
    }
    return table.get(str(W), f"Code {W}")

# ── Present Weather (ww) FULL TABLE ──────────────────────────────
def decode_ww(ww):
    ww = int(ww)
    # 0–9
    if ww == 0:  return "No significant weather"
    if ww == 1:  return "Clouds dissolving / becoming less developed"
    if ww == 2:  return "State of sky unchanged"
    if ww == 3:  return "Clouds forming / developing"
    if ww == 4:  return "Visibility reduced by smoke / ash / haze"
    if ww == 5:  return "Haze"
    if ww == 6:  return "Widespread dust in suspension"
    if ww == 7:  return "Dust or sand raised by wind"
    if ww == 8:  return "Well-developed dust or sand whirls"
    if ww == 9:  return "Dust or sandstorm within sight"
    # 10–19
    if ww == 10: return "Mist"
    if ww == 11: return "Shallow fog in patches"
    if ww == 12: return "Continuous shallow fog"
    if ww == 13: return "Lightning visible, no thunder heard"
    if ww == 14: return "Precipitation within sight, not reaching ground (virga)"
    if ww == 15: return "Precipitation within sight, reaching ground (distant)"
    if ww == 16: return "Precipitation within sight, reaching ground (near)"
    if ww == 17: return "TS – Thunderstorm (no precipitation at station)"
    if ww == 18: return "Squalls"
    if ww == 19: return "Funnel cloud(s) – tornado or waterspout"
    # 20–29 Recent
    if ww == 20: return "Drizzle (not freezing) – recent, not at obs time"
    if ww == 21: return "Rain (not freezing) – recent"
    if ww == 22: return "Snow – recent"
    if ww == 23: return "Rain and snow mixed – recent"
    if ww == 24: return "Freezing drizzle or freezing rain – recent"
    if ww == 25: return "Rain shower(s) – recent"
    if ww == 26: return "Snow shower(s) or rain-and-snow shower(s) – recent"
    if ww == 27: return "Hail shower(s) – recent"
    if ww == 28: return "Fog or ice fog – recent"
    if ww == 29: return "TS – Thunderstorm – recent (past hour)"
    # 30–39
    if ww == 30: return "Slight or moderate duststorm – decreasing"
    if ww == 31: return "Slight or moderate duststorm – no change"
    if ww == 32: return "Slight or moderate duststorm – beginning or increasing"
    if ww == 33: return "Severe duststorm – decreasing"
    if ww == 34: return "Severe duststorm – no change"
    if ww == 35: return "Severe duststorm – beginning or increasing"
    if ww == 36: return "Slight or moderate drifting snow (low)"
    if ww == 37: return "Heavy drifting snow (low)"
    if ww == 38: return "Slight or moderate blowing snow (high)"
    if ww == 39: return "Heavy blowing snow (high)"
    # 40–49 FOG
    if ww == 40: return "FOG – Fog at distance at obs time, not at station during preceding hour; extending above observer level"
    if ww == 41: return "FOG – Fog or ice fog in patches (has become thinner during preceding hour)"
    if ww == 42: return "FOG – Fog or ice fog, sky visible (has become thinner during preceding hour)"
    if ww == 43: return "FOG – Fog or ice fog, sky invisible (has become thinner during preceding hour)"
    if ww == 44: return "FOG – Fog or ice fog, sky visible (no appreciable change during preceding hour)"
    if ww == 45: return "FOG – Fog or ice fog, sky invisible (no appreciable change during preceding hour)"
    if ww == 46: return "FOG – Fog or ice fog, sky visible (has begun or become thicker during preceding hour)"
    if ww == 47: return "FOG – Fog or ice fog, sky invisible (has begun or become thicker during preceding hour)"
    if ww == 48: return "FOG – Fog, depositing rime, sky visible"
    if ww == 49: return "FOG – Fog, depositing rime, sky invisible"
    # 50–59 Drizzle
    if ww == 50: return "Drizzle – intermittent, slight"
    if ww == 51: return "Drizzle – continuous, slight"
    if ww == 52: return "Drizzle – intermittent, moderate"
    if ww == 53: return "Drizzle – continuous, moderate"
    if ww == 54: return "Drizzle – intermittent, heavy"
    if ww == 55: return "Drizzle – continuous, heavy"
    if ww == 56: return "Freezing drizzle – slight"
    if ww == 57: return "Freezing drizzle – moderate or heavy"
    if ww == 58: return "Drizzle and rain – slight"
    if ww == 59: return "Drizzle and rain – moderate or heavy"
    # 60–69 Rain
    if ww == 60: return "Rain – intermittent, slight"
    if ww == 61: return "Rain – continuous, slight"
    if ww == 62: return "Rain – intermittent, moderate"
    if ww == 63: return "Rain – continuous, moderate"
    if ww == 64: return "Rain – intermittent, heavy"
    if ww == 65: return "Rain – continuous, heavy"
    if ww == 66: return "Freezing rain – slight"
    if ww == 67: return "Freezing rain – moderate or heavy"
    if ww == 68: return "Rain or drizzle and snow – slight"
    if ww == 69: return "Rain or drizzle and snow – moderate or heavy"
    # 70–79 Snow
    if ww == 70: return "Snow – intermittent, slight"
    if ww == 71: return "Snow – continuous, slight"
    if ww == 72: return "Snow – intermittent, moderate"
    if ww == 73: return "Snow – continuous, moderate"
    if ww == 74: return "Snow – intermittent, heavy"
    if ww == 75: return "Snow – continuous, heavy"
    if ww == 76: return "Diamond dust (with or without fog)"
    if ww == 77: return "Snow grains (with or without fog)"
    if ww == 78: return "Isolated star-like snow crystals"
    if ww == 79: return "Ice pellets (sleet)"
    # 80–90 Showers
    if ww == 80: return "Rain shower(s) – slight"
    if ww == 81: return "Rain shower(s) – moderate or heavy"
    if ww == 82: return "Rain shower(s) – violent"
    if ww == 83: return "Shower(s) of rain and snow – slight"
    if ww == 84: return "Shower(s) of rain and snow – moderate or heavy"
    if ww == 85: return "Snow shower(s) – slight"
    if ww == 86: return "Snow shower(s) – moderate or heavy"
    if ww == 87: return "Shower(s) of snow pellets or small hail – slight (with or without rain)"
    if ww == 88: return "Shower(s) of snow pellets or small hail – moderate or heavy"
    if ww == 89: return "Hail shower(s) – slight, not associated with thunder"
    if ww == 90: return "Hail shower(s) – moderate or heavy, not associated with thunder"
    # 91–99 THUNDERSTORMS
    if ww == 91: return "TS/TSRA – Slight rain at obs time; thunderstorm during preceding hour but NOT at obs time"
    if ww == 92: return "TS/TSRA – Moderate or heavy rain at obs time; thunderstorm during preceding hour but NOT at obs time"
    if ww == 93: return "TS – Slight snow, or rain and snow, or hail at obs time; thunderstorm during preceding hour but NOT at obs time"
    if ww == 94: return "TS – Moderate or heavy snow, or rain and snow mixed, or hail at obs time; thunderstorm during preceding hour but NOT at obs time"
    if ww == 95: return "TS – Thunderstorm at obs time: slight or moderate, WITHOUT hail, but with rain and/or snow"
    if ww == 96: return "TS – Thunderstorm at obs time: slight or moderate, WITH hail"
    if ww == 97: return "TS – Thunderstorm at obs time: heavy, WITHOUT hail, but with rain and/or snow"
    if ww == 98: return "TS – Thunderstorm combined with duststorm or sandstorm at obs time"
    if ww == 99: return "TSRA – Thunderstorm at obs time: heavy, WITH hail (small hail / snow pellets)"
    return f"Present weather code {ww}"

# ── Cloud Types ───────────────────────────────────────────────────
def decode_cloud_type(CL, CM, CH):
    CL_table = {
        '0':"No CL clouds",
        '1':"Cu humilis or Cu fractus (fair weather)",
        '2':"Cu mediocris or Cu congestus (towering cumulus)",
        '3':"Cb calvus (no cirriform top)",
        '4':"Sc cumulogenitus (spreading from cumulus)",
        '5':"Sc (not cumulogenitus)",
        '6':"St or Fs (not of bad weather)",
        '7':"Fs and/or Fc of bad weather (low ragged clouds)",
        '8':"Cu and Sc at different levels",
        '9':"Cb capillatus (with cirriform top / anvil)",
        '/':"Not observed"
    }
    CM_table = {
        '0':"No CM clouds",
        '1':"As translucidus (thin altostratus)",
        '2':"As opacus or Ns (thick altostratus or nimbostratus)",
        '3':"Ac translucidus (single layer)",
        '4':"Ac translucidus (patchy, changing)",
        '5':"Ac translucidus (bands, spreading/thickening)",
        '6':"Ac cumulogenitus (from spreading cumulus)",
        '7':"Ac (double or multi-layer) or Ac with As or Ns",
        '8':"Ac castellanus or Ac floccus",
        '9':"Ac of chaotic sky",
        '/':"Not observed"
    }
    CH_table = {
        '0':"No CH clouds",
        '1':"Ci fibratus or Ci uncinus (not spreading)",
        '2':"Ci spissatus (dense, not from Cb)",
        '3':"Ci spissatus cumulonimbogenitus (from Cb anvil)",
        '4':"Ci uncinus or Ci fibratus (spreading/thickening)",
        '5':"Ci and/or Cs (below 45 deg above horizon)",
        '6':"Ci and/or Cs (above 45 deg above horizon)",
        '7':"Cs covering the entire sky",
        '8':"Cs not covering the entire sky",
        '9':"Cc alone or dominant",
        '/':"Not observed"
    }
    return (
        f"  Low cloud  (CL={CL}): {CL_table.get(str(CL), str(CL))}\n"
        f"  Mid cloud  (CM={CM}): {CM_table.get(str(CM), str(CM))}\n"
        f"  High cloud (CH={CH}): {CH_table.get(str(CH), str(CH))}"
    )

def decode_h(h):
    table = {
        '0':"< 50 m",      '1':"50-100 m",    '2':"100-200 m",
        '3':"200-300 m",   '4':"300-600 m",    '5':"600-1000 m",
        '6':"1000-1500 m", '7':"1500-2000 m",  '8':"2000-2500 m",
        '9':">= 2500 m or no clouds", '/':"Unknown"
    }
    return table.get(str(h), str(h))

def decode_iR(iR):
    table = {
        '0':"Precipitation included in Section 1 and Section 3",
        '1':"Precipitation included in Section 1 only",
        '2':"Precipitation included in Section 3 only",
        '3':"Precipitation omitted – no precipitation",
        '4':"Precipitation omitted – station not staffed"
    }
    return table.get(str(iR), str(iR))

def decode_iX(iX):
    table = {
        '1':"Manned station – present and past weather included",
        '2':"Manned station – present weather omitted",
        '3':"Manned station – present and past weather omitted",
        '4':"Automatic station – present and past weather included",
        '5':"Automatic station – present weather omitted",
        '6':"Automatic station – present and past weather omitted",
        '7':"Automatic station (type 2) – wx included"
    }
    return table.get(str(iX), str(iX))

def decode_P(PPPP):
    p = int(PPPP)
    return f"{(p+10000)/10.0:.1f} hPa" if p < 5000 else f"{p/10.0:.1f} hPa"

def validate_station(stn):
    if not re.match(r'^\d{5}$', stn):
        return False, "Station number must be exactly 5 digits"
    return True, "OK"

# ══════════════════════════════════════════════════════════════════
#  SECTION DECODERS
# ══════════════════════════════════════════════════════════════════

def decode_section0(header):
    m = re.match(r'AAXX\s+(\d{2})(\d{2})(\d)', header.upper())
    if not m: return {}, '1'
    YY, GG, iw = m.group(1), m.group(2), m.group(3)
    iw_table = {
        '0':'Calm / estimated (knots)', '1':'Anemometer (knots)',
        '3':'Calm / estimated (m/s)',   '4':'Anemometer (m/s)'
    }
    return {'day':YY,'hour':GG,'iw':iw,'iw_desc':iw_table.get(iw,f"iw={iw}")}, iw

def decode_section1(groups, iw='1'):
    out = {}
    i = 0
    # Position 0: iRiXhVV
    if i < len(groups) and re.match(r'^\d{5}$', groups[i]):
        g = groups[i]
        out['iR'] = decode_iR(g[0])
        out['iX'] = decode_iX(g[1])
        out['h']  = decode_h(g[2])
        out['VV'] = decode_vv(g[3:5])
        i += 1
    # Position 1: Nddff
    if i < len(groups) and re.match(r'^\d{5}$', groups[i]):
        g = groups[i]
        N = g[0]; dd = int(g[1:3]); ff = int(g[3:5])
        out['N'] = decode_N(N); out['N_raw'] = N
        out['dd'] = dd; out['dd_compass'] = dd_to_compass(dd)
        if ff == 99:
            i += 1
            if i < len(groups) and groups[i].startswith('00'):
                ff = int(groups[i][2:])
        out['ff_raw']  = ff
        out['ff_unit'] = 'knots' if iw in ('0','1') else 'm/s'
        out['ff_kmph'] = knots_to_kmph(ff) if iw in ('0','1') else ms_to_kmph(ff)
        i += 1
    # Remaining groups
    while i < len(groups):
        g = groups[i]; i += 1
        if not re.match(r'^[\d/]{5}$', g): continue
        c = g[0]
        if   c=='1':
            try: out['T']  = decode_temp(g[1], g[2:5])
            except: pass
        elif c=='2':
            try: out['Td'] = decode_temp(g[1], g[2:5])
            except: pass
        elif c=='3':
            try: out['P_stn'] = decode_P(g[1:])
            except: pass
        elif c=='4':
            try: out['P_slp'] = decode_P(g[1:])
            except: pass
        elif c=='5':
            tend_desc = {
                '0':'Rising then falling','1':'Rising then steady',
                '2':'Rising steadily',    '3':'Rising unsteadily',
                '4':'Steady',             '5':'Falling then rising',
                '6':'Falling then steady','7':'Falling steadily',
                '8':'Falling unsteadily'
            }
            ppp = int(g[2:]) if g[2:].isdigit() else 0
            out['P_tend'] = f"{tend_desc.get(g[1], f'code {g[1]}')}, {ppp/10:.1f} hPa change"
        elif c=='6':
            try:
                RRR = int(g[1:4]); t = g[4]
                t_t = {'1':'6h','2':'12h','3':'18h','4':'24h','5':'1h','6':'2h','7':'3h','9':'unknown'}
                out['RRR'] = f"{'Trace' if RRR>=990 else str(RRR)+' mm'} over {t_t.get(t,'?')}"
            except: pass
        elif c=='7':
            try:
                ww_s = g[1:3]
                if ww_s.isdigit():
                    out['ww_raw'] = int(ww_s)
                    out['ww']     = decode_ww(int(ww_s))
                # W1 and W2 – decode using Code 26
                out['W1']     = g[3]
                out['W2']     = g[4]
                out['W1_desc']= decode_W(g[3])
                out['W2_desc']= decode_W(g[4])
            except: pass
        elif c=='8':
            out['Nh_raw']=g[1]; out['Nh']=decode_N(g[1])
            out['CL']=g[2]; out['CM']=g[3]; out['CH']=g[4]
        elif c=='9':
            if g[1:3].isdigit() and g[3:5].isdigit():
                out['exact_time'] = f"{g[1:3]}h {g[3:5]}min UTC"
    return out

def decode_section3(groups):
    out = {}
    for g in groups:
        if not re.match(r'^[\d/]{5}$', g): continue
        c = g[0]
        if   c=='1':
            try: out['Tx'] = decode_temp(g[1], g[2:5])
            except: pass
        elif c=='2':
            try: out['Tn'] = decode_temp(g[1], g[2:5])
            except: pass
        elif c=='3': out['snow']     = f"Snow/ground state code: {g[1:]}"
        elif c=='4': out['ground']   = f"Ground surface state/temp code: {g[1:]}"
        elif c=='5': out['sunshine'] = f"Sunshine duration code: {g[1:]}"
        elif c=='6':
            try:
                RRR = int(g[1:4]); t = g[4]
                t_t = {'1':'6h','2':'12h','3':'18h','4':'24h','5':'1h','6':'2h','7':'3h','9':'unknown'}
                out['RRR_s3'] = f"{'Trace' if RRR>=990 else str(RRR)+' mm'} over {t_t.get(t,'?')}"
            except: pass
        elif c=='7': out['R24'] = f"Daily precipitation group: {g}"
    return out

# ══════════════════════════════════════════════════════════════════
#  MAIN DECODE  –  HARD STOP ON NON-AAXX
# ══════════════════════════════════════════════════════════════════

def decode_synop(raw):
    raw = raw.strip().replace('`n', '\n')
    if not raw: return None, ["ERROR: Empty input."]

    tokens = raw.replace('\n', ' ').split()
    if not tokens: return None, ["ERROR: Empty input."]

    # HARD STOP if not AAXX
    if tokens[0].upper() != 'AAXX':
        return None, [
            f"ERROR: Message must start with 'AAXX' (or 'aaxx').",
            f"         Got      : '{tokens[0]}'",
            f"         Expected : AAXX YYGGiw  (e.g. AAXX 06091)"
        ]

    header_line = f"{tokens[0]} {tokens[1]}" if len(tokens) > 1 and re.match(r'^\d{5}$', tokens[1]) else tokens[0]
    errors = []; result = {}

    if not re.match(r'^(?i:AAXX)\s+\d{5}$', header_line):
        errors.append(f"ERROR: AAXX header format invalid. Got: '{header_line}'")

    hdr, iw = decode_section0(header_line)
    result['header'] = hdr

    rest_tokens = tokens[2:] if len(tokens) > 2 else []
    main_groups = []; sec3_groups = []
    if '333' in rest_tokens:
        idx = rest_tokens.index('333')
        main_groups = rest_tokens[:idx]
        sec3_groups = rest_tokens[idx+1:]
    else:
        main_groups = rest_tokens

    if not main_groups:
        errors.append("ERROR: No observation data found after header.")
        return result, errors

    stn = main_groups[0]
    ok, msg = validate_station(stn)
    if not ok: errors.append(f"ERROR: {msg} (got '{stn}')")
    result['station'] = stn
    result['section1'] = decode_section1(main_groups[1:], iw)
    if sec3_groups:
        result['section3'] = decode_section3(sec3_groups)
    return result, errors

# ══════════════════════════════════════════════════════════════════
#  BATCH PROCESSOR
# ══════════════════════════════════════════════════════════════════

def extract_synop_blocks(text):
    lines = text.splitlines()
    blocks = []; i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r'^(?i:AAXX)\s+\d{5}$', line):
            block_lines = [line]; start_line = i + 1; i += 1
            while i < len(lines):
                nxt = lines[i].strip()
                if re.match(r'^(BBXX|OOXX|METAR|SPECI|TAF|TEMP|PILOT|TTXX|SHIP)\b', nxt, re.I): break
                if re.match(r'^(?i:AAXX)\s+\d{5}$', nxt): break
                block_lines.append(nxt); i += 1
            blocks.append(('\n'.join(block_lines), start_line))
        else:
            i += 1
    return blocks

def cmd_batch(args, config):
    filepath = args.file
    if not os.path.exists(filepath):
        print(f"\n  ERROR: File not found: '{filepath}'\n"); return
    try:
        with open(filepath, 'r', errors='ignore') as f:
            text = f.read()
    except Exception as e:
        print(f"\n  ERROR reading file: {e}\n"); return

    blocks = extract_synop_blocks(text)
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║              SYNOP BATCH DECODER – FILE SCAN                ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  File    : {filepath}")
    print(f"  Total lines in file : {len(text.splitlines())}")
    print(f"  AAXX SYNOP blocks found : {len(blocks)}")

    if not blocks:
        print("\n  [!] No AAXX SYNOP blocks found in this file.\n"); return

    station_filter = config['settings'].get('station_filter','').strip()
    show_s3        = config['settings'].get('show_section3','true').lower() == 'true'
    decoded_count  = 0; skipped_count = 0

    for idx, (block, line_no) in enumerate(blocks, 1):
        result, errors = decode_synop(block)
        if station_filter and result and result.get('station') != station_filter:
            skipped_count += 1; continue
        print()
        print(f"  {'─'*60}")
        print(f"  Block {idx} / {len(blocks)}  (starts at line {line_no})")
        print(f"  {'─'*60}")
        print("  Raw:")
        for raw_line in block.splitlines(): print(f"    {raw_line}")
        print()
        print_result(result, errors, show_s3=show_s3)
        decoded_count += 1

    print()
    print(f"  [OK] Decoded : {decoded_count} block(s)")
    if skipped_count:
        print(f"  [SKIPPED] {skipped_count} block(s) (station filter = {station_filter})")
    print()

# ══════════════════════════════════════════════════════════════════
#  PRETTY PRINTER
# ══════════════════════════════════════════════════════════════════

def print_result(result, errors, show_s3=True):
    W = 64
    print()
    print("  ╔" + "═"*(W-2) + "╗")
    print("  ║" + "SYNOP FM-12 SURFACE CODE DECODER".center(W-2) + "║")
    print("  ╚" + "═"*(W-2) + "╝")
    print()

    if errors:
        for e in errors:
            for line in e.splitlines(): print(f"  [!]  {line}")
        print()
        if not result or 'station' not in result: return

    stn = result.get('station','?')
    print(f"  Station        : {stn}")
    hdr = result.get('header',{})
    if hdr:
        print(f"  Date / Time    : Day {hdr.get('day','?')} of month, {hdr.get('hour','?')}:00 UTC")
        print(f"  Wind measured  : {hdr.get('iw_desc','?')}")

    s1 = result.get('section1',{})
    if s1:
        print()
        print("  ┌─ SECTION 1 : SURFACE OBSERVATIONS " + "─"*(W-38) + "┐")
        if 'VV'     in s1: print(f"  │  Visibility          : {s1['VV']}")
        if 'N'      in s1: print(f"  │  Total cloud cover   : {s1['N']}")
        if 'dd'     in s1: print(f"  │  Wind direction      : {s1['dd_compass']}")
        if 'ff_raw' in s1: print(f"  │  Wind speed          : {s1['ff_raw']} {s1['ff_unit']} = {s1['ff_kmph']} km/h")
        if 'T'      in s1: print(f"  │  Dry bulb temp  (T)  : {s1['T']:.1f} degC")
        if 'Td'     in s1:
            print(f"  │  Dew point temp (Td) : {s1['Td']:.1f} degC")
            if 'T' in s1:
                rh = 100*(112 - 0.1*s1['T'] + s1['Td'])/(112 + 0.9*s1['T'])
                print(f"  │  Rel. humidity   (~) : {max(0,min(100,rh)):.0f}%")
        if 'P_stn'  in s1: print(f"  │  Station pressure    : {s1['P_stn']}")
        if 'P_slp'  in s1: print(f"  │  Sea-level pressure  : {s1['P_slp']}")
        if 'P_tend' in s1: print(f"  │  Pressure tendency   : {s1['P_tend']}")
        if 'RRR'    in s1: print(f"  │  Precipitation       : {s1['RRR']}")
        if 'ww'     in s1: print(f"  │  Present weather     : {s1['ww']}  [ww={s1.get('ww_raw','')}]")
        # W1/W2 now with full Code 26 descriptions
        if 'W1' in s1:
            print(f"  │  Past weather (W1)   : {s1['W1_desc']}  [W1={s1['W1']}]")
            print(f"  │  Past weather (W2)   : {s1['W2_desc']}  [W2={s1['W2']}]")
        print(f"  │  Precip data flag    : {s1.get('iR','?')}")
        print(f"  │  Station type        : {s1.get('iX','?')}")
        if 'h'  in s1: print(f"  │  Lowest cloud base   : {s1['h']}")
        if 'Nh' in s1: print(f"  │  Lowest layer (Nh)   : {s1['Nh']}")
        if 'CL' in s1:
            print(f"  │  Cloud types         :")
            for cl in decode_cloud_type(s1['CL'],s1['CM'],s1['CH']).splitlines():
                print(f"  │  {cl}")
        if 'exact_time' in s1:
            print(f"  │  Exact obs time      : {s1['exact_time']}")
        print("  └" + "─"*(W-4) + "┘")

    if show_s3:
        s3 = result.get('section3',{})
        if s3:
            print()
            print("  ┌─ SECTION 3 : ADDITIONAL DATA " + "─"*(W-32) + "┐")
            if 'Tx'     in s3: print(f"  │  Max temp (past 12h) : {s3['Tx']:.1f} degC")
            if 'Tn'     in s3: print(f"  │  Min temp (past 12h) : {s3['Tn']:.1f} degC")
            if 'RRR_s3' in s3: print(f"  │  Precipitation       : {s3['RRR_s3']}")
            if 'sunshine'in s3: print(f"  │  Sunshine            : {s3['sunshine']}")
            if 'snow'   in s3: print(f"  │  {s3['snow']}")
            if 'ground' in s3: print(f"  │  {s3['ground']}")
            if 'R24'    in s3: print(f"  │  {s3['R24']}")
            print("  └" + "─"*(W-4) + "┘")
    print()

# ══════════════════════════════════════════════════════════════════
#  INTERACTIVE ENCODER
# ══════════════════════════════════════════════════════════════════

def interactive_encode_and_decode():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║          SYNOP INTERACTIVE ENCODER + DECODER                ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print("  Enter observation details. Press Enter to skip optional fields.")
    print()

    enc_errors = []

    stn = input("  1. Station number (5 digits, e.g. 43279): ").strip()
    if not re.match(r'^\d{5}$', stn):
        enc_errors.append(f"[!] Station '{stn}' is not valid.")

    print()
    print("  2. Wind  –  direction in degrees (0=N 90=E 180=S 270=W) and speed in km/h")
    wind_raw = input("     e.g. '140 37': ").strip()
    dd_code = 0; ff_knots = 0
    if wind_raw:
        parts = wind_raw.split()
        if len(parts) == 2:
            try:
                deg = float(parts[0]); kmph = float(parts[1])
                dd_code  = round(deg/10) if deg > 0 else 0
                if dd_code >= 36: dd_code = 0
                ff_knots = round(kmph/1.852)
                print(f"     → {dd_to_compass(dd_code)}, {ff_knots} knots ({kmph:.1f} km/h)")
            except: enc_errors.append("[!] Wind error. Use: <degrees> <km/h>")
        else: enc_errors.append("[!] Wind: two values needed.")

    print()
    temp_raw = input("  3. Dry bulb temperature degC (e.g. 39.0): ").strip()
    T_enc = None
    if temp_raw:
        try:
            T_val = float(temp_raw)
            T_enc = f"1{1 if T_val<0 else 0}{round(abs(T_val)*10):03d}"
        except: enc_errors.append("[!] Temperature must be a number.")

    td_raw = input("  3b. Dew point degC (optional): ").strip()
    Td_enc = None
    if td_raw:
        try:
            Td = float(td_raw)
            Td_enc = f"2{1 if Td<0 else 0}{round(abs(Td)*10):03d}"
        except: enc_errors.append("[!] Dew point must be a number.")

    print()
    print("  4. Present weather (keyword or ww code 0-99):")
    print("     clear  haze  mist  fog  fog_patch  fog_sky  fog_rime  fog_rime_inv")
    print("     drizzle  rain  snow  shower  hail")
    print("     ts  ts_hail  ts_heavy  tsra  tsra_heavy")
    wx_raw = input("     Weather: ").strip().lower()
    wx_map = {
        'clear':0,'haze':5,'mist':10,
        'fog':45,'fog_patch':41,'fog_sky':44,'fog_rime':48,'fog_rime_inv':49,
        'drizzle':53,'rain':63,'snow':73,'shower':80,'hail':89,
        'ts':95,'ts_hail':96,'ts_heavy':97,'tsra':95,'tsra_heavy':99
    }
    ww_code = None
    if wx_raw:
        if wx_raw in wx_map:
            ww_code = wx_map[wx_raw]
            print(f"     → ww={ww_code}: {decode_ww(ww_code)}")
        else:
            try:
                ww_code = int(wx_raw)
                if 0<=ww_code<=99: print(f"     → ww={ww_code}: {decode_ww(ww_code)}")
                else: enc_errors.append("[!] ww must be 0-99."); ww_code=None
            except: enc_errors.append(f"[!] Unknown weather '{wx_raw}'.")

    print()
    print("  5. Cloud cover oktas (0=Clear 1-2=FEW 3-4=SCT 5-6=BKN 7-8=OVC 9=Obscured):")
    N_raw = input("     Oktas (0-9): ").strip()
    N_code = 0
    if N_raw:
        try:
            N_code = int(N_raw)
            if not 0<=N_code<=9: enc_errors.append("[!] Oktas 0-9."); N_code=0
            else: print(f"     → {decode_N(N_code)}")
        except: enc_errors.append("[!] Oktas must be 0-9.")

    print()
    print("  5b. Cloud types (optional):")
    print("     CL: 0=None 1=Cu 2=Cu tower 3=Cb 4=Sc(Cu) 5=Sc 6=St 7=Fs 8=Cu+Sc 9=Cb(anvil)")
    print("     CM: 0=None 1=As 2=As/Ns 3=Ac 4=Ac patch 5=Ac band 6=Ac(Cu) 7=Ac multi 8=Ac cas 9=Ac chaos")
    print("     CH: 0=None 1=Ci 2=Ci dense 3=Ci anvil 4=Ci incr 5=Ci/Cs<45 6=Ci/Cs>45 7=Cs all 8=Cs part 9=Cc")
    CL = input("     CL (0-9 or /): ").strip() or '/'
    CM = input("     CM (0-9 or /): ").strip() or '/'
    CH = input("     CH (0-9 or /): ").strip() or '/'

    print()
    print("  5c. Lowest cloud base height:")
    print("     0=<50m 1=50-100m 2=100-200m 3=200-300m 4=300-600m 5=600-1000m 6=1-1.5km 7=1.5-2km 8=2-2.5km 9>=2.5km")
    h_raw  = input("     Code (0-9 or /): ").strip() or '/'
    h_code = h_raw if h_raw in '0123456789/' else '/'

    print()
    tx_raw = input("  6. Max temperature past 12h degC (optional): ").strip()
    Tx_enc = None
    if tx_raw:
        try:
            Tx = float(tx_raw)
            Tx_enc = f"1{1 if Tx<0 else 0}{round(abs(Tx)*10):03d}"
        except: enc_errors.append("[!] Max temp must be a number.")

    tn_raw = input("  6b. Min temperature past 12h degC (optional): ").strip()
    Tn_enc = None
    if tn_raw:
        try:
            Tn = float(tn_raw)
            Tn_enc = f"2{1 if Tn<0 else 0}{round(abs(Tn)*10):03d}"
        except: enc_errors.append("[!] Min temp must be a number.")

    now   = datetime.datetime.utcnow()
    synop = f"AAXX {now.strftime('%d%H')}1\n"
    groups = [stn, f"31{h_code}97", f"{N_code}{dd_code:02d}{ff_knots:02d}"]
    if T_enc:               groups.append(T_enc)
    if Td_enc:              groups.append(Td_enc)
    if ww_code is not None: groups.append(f"7{ww_code:02d}//")
    groups.append(f"8{N_code}{CL}{CM}{CH}")
    synop += " ".join(groups)
    sec3 = []
    if Tx_enc: sec3.append(Tx_enc)
    if Tn_enc: sec3.append(Tn_enc)
    if sec3: synop += "\n333\n" + " ".join(sec3)

    print()
    print("  ┌─ GENERATED SYNOP CODE ──────────────────────────────────┐")
    for line in synop.splitlines(): print(f"  │  {line}")
    print("  └─────────────────────────────────────────────────────────┘")
    if enc_errors:
        print()
        for e in enc_errors: print(f"  {e}")
    print()
    print("  ── DECODING GENERATED SYNOP ─────────────────────────────")
    decoded, dec_errors = decode_synop(synop)
    print_result(decoded, dec_errors)

# ══════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════

def save_output(data, path, fmt):
    """Save output to txt or json file."""
    try:
        if fmt == 'json':
            with open(path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        else:
            with open(path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(str(data))
        import builtins
        builtins.print(f"  [OK] Saved to: {path}")
    except Exception as e:
        import builtins
        builtins.print(f"  [!] Could not save: {e}")

def main():
    config = load_config()

    parser = argparse.ArgumentParser(
        prog='synop',
        description='SYNOP FM-12 Surface Code Decoder / Encoder',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
COMMANDS:
  synop decode AAXX 06091 43279 32597 31410 10390 20264 30018 40035 83400 333 10264
  synop decode AAXX 06091 43279 ... --json
  synop decode AAXX 06091 43279 ... --save output.json
  synop decode AAXX 06091 43279 ... --save output.txt
  synop decode -f obs.txt
  synop batch  -f messages.txt
  synop batch  -f messages.txt --json
  synop batch  -f messages.txt --save results.json
  synop encode
  synop config
  synop config --set station_filter=43279
  synop api
  synop api --port 8080
  synop help
        """
    )
    sub = parser.add_subparsers(dest='cmd')

    dec_p = sub.add_parser('decode', help='Decode a SYNOP message')
    dec_p.add_argument('message', nargs='*', help='SYNOP tokens')
    dec_p.add_argument('-f','--file',  help='Read from file')
    dec_p.add_argument('--json',       action='store_true', help='Output as JSON')
    dec_p.add_argument('--save',       help='Save output to file (.json or .txt)')

    bat_p = sub.add_parser('batch', help='Scan file for all AAXX blocks')
    bat_p.add_argument('-f','--file',  required=True, help='Input text file')
    bat_p.add_argument('--set',        nargs='*', help='Override config key=value')
    bat_p.add_argument('--json',       action='store_true', help='Output as JSON')
    bat_p.add_argument('--save',       help='Save output to file (.json or .txt)')

    sub.add_parser('encode', help='Interactive encoder + decoder')

    cfg_p = sub.add_parser('config', help='Show or set configuration')
    cfg_p.add_argument('--set', nargs='*', help='Set key=value')

    api_p = sub.add_parser('api', help='Start Flask REST API server')
    api_p.add_argument('--port', type=int, default=5000, help='Port number (default 5000)')
    api_p.add_argument('--host', default='0.0.0.0', help='Host (default 0.0.0.0)')

    sub.add_parser('help', help='Show help')

    args = parser.parse_args()

    # ── decode ──────────────────────────────────────────────────
    if args.cmd == 'decode':
        if getattr(args,'file',None):
            try:
                with open(args.file,'r',errors='ignore') as f: text = f.read()
            except Exception as e:
                print(f"\n  ERROR reading file: {e}\n"); sys.exit(1)
            blocks = extract_synop_blocks(text)
            if not blocks:
                print(f"\n  [!] No AAXX SYNOP blocks found in: {args.file}\n"); sys.exit(1)
            all_json = []
            for idx, (block, line_no) in enumerate(blocks, 1):
                result, errors = decode_synop(block)
                if args.json or (args.save and args.save.endswith('.json')):
                    all_json.append(result_to_json(result, errors))
                else:
                    if len(blocks) > 1:
                        print(f"\n  -- AAXX block {idx} (line {line_no}) --")
                    print_result(result, errors)
            if all_json:
                import builtins
                builtins.print(json.dumps(all_json if len(all_json)>1 else all_json[0], indent=2, default=str))
                if args.save:
                    save_output(all_json if len(all_json)>1 else all_json[0], args.save, 'json')
            return

        raw = None
        if getattr(args,'message',None):
            raw = " ".join(args.message)
            raw = raw.replace('\\n','\n').replace('`n','\n')
        else:
            print("  Paste SYNOP (Ctrl+D / Ctrl+Z when done):")
            raw = sys.stdin.read()
        if not raw or not raw.strip():
            print("\n  ERROR: No SYNOP message provided.\n"); sys.exit(1)

        result, errors = decode_synop(raw)

        # JSON output
        if args.json or (args.save and args.save.endswith('.json')):
            j = result_to_json(result, errors)
            import builtins
            builtins.print(json.dumps(j, indent=2, default=str))
            if args.save:
                save_output(j, args.save, 'json')
        else:
            # Text output
            if args.save and args.save.endswith('.txt'):
                import io, builtins
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                print_result(result, errors)
                text_out = sys.stdout.getvalue()
                sys.stdout = old_stdout
                save_output(text_out, args.save, 'txt')
                builtins.print(text_out, end='')
            else:
                print_result(result, errors)

    # ── batch ───────────────────────────────────────────────────
    elif args.cmd == 'batch':
        if getattr(args,'set',None):
            for pair in args.set:
                if '=' in pair:
                    k,v = pair.split('=',1)
                    if k.strip() in config['settings']:
                        config['settings'][k.strip()] = v.strip()

        if args.json or (getattr(args,'save',None) and args.save.endswith('.json')):
            # JSON batch output
            filepath = args.file
            if not os.path.exists(filepath):
                print(f"\n  ERROR: File not found: '{filepath}'\n"); return
            with open(filepath,'r',errors='ignore') as f: text = f.read()
            blocks = extract_synop_blocks(text)
            station_filter = config['settings'].get('station_filter','').strip()
            all_results = []
            for block, line_no in blocks:
                result, errors = decode_synop(block)
                if station_filter and result and result.get('station') != station_filter:
                    continue
                j = result_to_json(result, errors)
                j['source_line'] = line_no
                all_results.append(j)
            output = {"count": len(all_results), "results": all_results}
            import builtins
            builtins.print(json.dumps(output, indent=2, default=str))
            if getattr(args,'save',None):
                save_output(output, args.save, 'json')
        else:
            # Normal terminal batch + optional txt save
            if getattr(args,'save',None) and args.save.endswith('.txt'):
                import io, builtins
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                cmd_batch(args, config)
                text_out = sys.stdout.getvalue()
                sys.stdout = old_stdout
                save_output(text_out, args.save, 'txt')
                builtins.print(text_out, end='')
            else:
                cmd_batch(args, config)

    # ── encode ──────────────────────────────────────────────────
    elif args.cmd == 'encode':
        interactive_encode_and_decode()

    # ── config ──────────────────────────────────────────────────
    elif args.cmd == 'config':
        cmd_config(args, config)

    # ── api ─────────────────────────────────────────────────────
    elif args.cmd == 'api':
        run_api(host=args.host, port=args.port)

    # ── help ────────────────────────────────────────────────────
    else:
        parser.print_help()

if __name__ == '__main__':
    main()

# ══════════════════════════════════════════════════════════════════
#  RESULT TO JSON CONVERTER
# ══════════════════════════════════════════════════════════════════

def result_to_json(result, errors):
    """Convert decoded result dict to clean JSON-serializable dict."""
    if not result:
        return {"status": "error", "errors": errors}

    s1 = result.get('section1', {})
    s3 = result.get('section3', {})
    hdr = result.get('header', {})

    output = {
        "status":   "ok" if not errors else "warning",
        "errors":   errors if errors else [],
        "station":  result.get('station', None),
        "header": {
            "day":          hdr.get('day', None),
            "hour_utc":     hdr.get('hour', None),
            "wind_unit":    hdr.get('iw_desc', None),
        },
        "section1": {
            "visibility":           s1.get('VV', None),
            "cloud_cover":          s1.get('N', None),
            "wind_direction_deg":   s1.get('dd', None) * 10 if s1.get('dd') is not None else None,
            "wind_direction_compass": s1.get('dd_compass', None),
            "wind_speed_knots":     s1.get('ff_raw', None),
            "wind_speed_kmph":      s1.get('ff_kmph', None),
            "wind_unit":            s1.get('ff_unit', None),
            "temp_dry_bulb_c":      s1.get('T', None),
            "temp_dew_point_c":     s1.get('Td', None),
            "humidity_pct":         round(max(0, min(100, 100*(112 - 0.1*s1['T'] + s1['Td'])/(112 + 0.9*s1['T'])))) if 'T' in s1 and 'Td' in s1 else None,
            "pressure_station_hpa": s1.get('P_stn', None),
            "pressure_slp_hpa":     s1.get('P_slp', None),
            "pressure_tendency":    s1.get('P_tend', None),
            "precipitation":        s1.get('RRR', None),
            "present_weather_code": s1.get('ww_raw', None),
            "present_weather_desc": s1.get('ww', None),
            "past_weather_W1_code": s1.get('W1', None),
            "past_weather_W1_desc": s1.get('W1_desc', None),
            "past_weather_W2_code": s1.get('W2', None),
            "past_weather_W2_desc": s1.get('W2_desc', None),
            "cloud_base_height":    s1.get('h', None),
            "cloud_cover_lowest":   s1.get('Nh', None),
            "cloud_low_CL":         s1.get('CL', None),
            "cloud_mid_CM":         s1.get('CM', None),
            "cloud_high_CH":        s1.get('CH', None),
            "precip_flag":          s1.get('iR', None),
            "station_type":         s1.get('iX', None),
            "exact_obs_time":       s1.get('exact_time', None),
        },
        "section3": {
            "max_temp_c":       s3.get('Tx', None),
            "min_temp_c":       s3.get('Tn', None),
            "precipitation":    s3.get('RRR_s3', None),
            "sunshine":         s3.get('sunshine', None),
            "snow_ground":      s3.get('snow', None),
        } if s3 else {}
    }
    return output

# ══════════════════════════════════════════════════════════════════
#  FLASK REST API
# ══════════════════════════════════════════════════════════════════

def run_api(host='0.0.0.0', port=5000):
    """Start Flask REST API server."""
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        print("\n  ERROR: Flask not installed.")
        print("  Run: pip install flask\n")
        return

    app = Flask(__name__)

    @app.route('/', methods=['GET'])
    def index():
        return jsonify({
            "service": "SYNOP FM-12 Decoder API",
            "version": "1.0",
            "endpoints": {
                "GET  /decode?synop=AAXX+...": "Decode a SYNOP message",
                "POST /decode  body:{synop:...}": "Decode via POST",
                "POST /batch   body:{synops:[...]}": "Decode multiple messages",
                "GET  /health": "Health check"
            }
        })

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "ok", "service": "SYNOP Decoder"})

    @app.route('/decode', methods=['GET', 'POST'])
    def decode_endpoint():
        # GET: /decode?synop=AAXX 06091 43279 ...
        # POST: {"synop": "AAXX 06091 43279 ..."}
        if request.method == 'GET':
            raw = request.args.get('synop', '').replace('+', ' ')
        else:
            data = request.get_json(silent=True) or {}
            raw  = data.get('synop', '')

        if not raw or not raw.strip():
            return jsonify({"status": "error", "message": "No SYNOP provided. Use ?synop=AAXX ..."}), 400

        raw = raw.replace('\\n', '\n')
        result, errors = decode_synop(raw)
        output = result_to_json(result, errors)

        if result is None:
            return jsonify(output), 400
        return jsonify(output), 200

    @app.route('/batch', methods=['POST'])
    def batch_endpoint():
        # POST: {"synops": ["AAXX ...", "AAXX ..."]}
        # OR:   {"text": "full text file contents with mixed codes"}
        data = request.get_json(silent=True) or {}

        results = []

        # Option 1: list of SYNOP strings
        if 'synops' in data:
            for raw in data['synops']:
                raw = raw.replace('\\n', '\n')
                result, errors = decode_synop(raw)
                results.append(result_to_json(result, errors))

        # Option 2: raw text (like a full file with mixed codes)
        elif 'text' in data:
            blocks = extract_synop_blocks(data['text'])
            for block, line_no in blocks:
                result, errors = decode_synop(block)
                j = result_to_json(result, errors)
                j['source_line'] = line_no
                results.append(j)
        else:
            return jsonify({"status":"error","message":"Provide 'synops' list or 'text' field"}), 400

        return jsonify({
            "status":  "ok",
            "count":   len(results),
            "results": results
        }), 200

    import builtins
    builtins.print(f"\n  SYNOP Decoder API starting...")
    builtins.print(f"  URL  : http://localhost:{port}")
    builtins.print(f"  Test : http://localhost:{port}/decode?synop=AAXX+06091+43279+32597+31410+10390+20264+30018+40035+83400+333+10264")
    builtins.print(f"  Stop : Press Ctrl+C\n")
    app.run(host=host, port=port, debug=False)