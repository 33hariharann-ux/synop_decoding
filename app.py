from flask import Flask, render_template, request, Response
from synop_decode import decode_synop, extract_synop_blocks

import csv
import json
import base64
import io
from io import StringIO
from openpyxl import Workbook
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

app = Flask(__name__)

latest_results = []


# ==================================================
# HOME PAGE
# ==================================================

@app.route("/")
def home():
    return render_template("index.html")


# ==================================================
# SINGLE DECODE PAGE
# ==================================================

@app.route("/single")
def single():
    return render_template("single_decode.html")


# ==================================================
# SINGLE SYNOP DECODER
# ==================================================

@app.route("/decode", methods=["POST"])
def decode():
    synop_text = request.form["synop"]
    result, errors = decode_synop(synop_text)
    return render_template("single_decode.html", result=result, errors=errors)


# ==================================================
# MULTI DECODE PAGE
# ==================================================

@app.route("/multi")
def multi():
    return render_template("multi_decode.html")


# ==================================================
# MULTI SYNOP DECODER
# ==================================================

@app.route("/multi_decode", methods=["POST"])
def multi_decode():
    global latest_results

    synop_text = request.form["synops"]
    results = []
    blocks = []

    for line in synop_text.splitlines():
        line = line.strip()
        if line.upper().startswith("AAXX"):
            blocks.append(line)

    for block in blocks:
        try:
            result, errors = decode_synop(block)
            if result is None:
                continue
            section1 = result.get("section1", {})
            results.append({
                "station":     result.get("station", "N/A"),
                "temperature": section1.get("T", "N/A"),
                "weather":     section1.get("ww", "N/A"),
                "visibility":  section1.get("VV", "N/A"),
                "wind":        section1.get("ff_kmph", "N/A"),
                "dew_point":   section1.get("Td", "N/A"),
                "humidity":    section1.get("humidity", "N/A"),
            })
        except Exception as e:
            results.append({
                "station": "ERROR", "temperature": "-",
                "weather": str(e), "visibility": "-",
                "wind": "-", "dew_point": "-", "humidity": "-"
            })

    latest_results = results
    summary = build_summary(results)
    charts   = build_charts(results)

    return render_template(
        "multi_decode.html",
        results=results,
        summary=summary,
        charts=charts
    )


# ==================================================
# BATCH PAGE
# ==================================================

@app.route("/batch")
def batch():
    return render_template("batch_upload.html")


# ==================================================
# BATCH DECODER
# ==================================================

@app.route("/batch_decode", methods=["POST"])
def batch_decode():
    global latest_results

    uploaded_file = request.files["file"]
    print("=" * 60)
    print("FILE RECEIVED:", uploaded_file.filename)

    content = uploaded_file.read().decode("utf-8", errors="ignore")
    print("CONTENT LENGTH:", len(content))

    results = []
    blocks = extract_synop_blocks(content)

    if len(blocks) == 0:
        print("Trying single-line mode...")
        for line in content.splitlines():
            line = line.strip()
            if line.upper().startswith("AAXX"):
                blocks.append((line, 0))

    print("BLOCKS FOUND:", len(blocks))

    for block, line_no in blocks:
        try:
            result, errors = decode_synop(block)
            if result is None:
                continue
            section1 = result.get("section1", {})
            results.append({
                "station":     result.get("station", "N/A"),
                "temperature": section1.get("T", "N/A"),
                "weather":     section1.get("ww", "N/A"),
                "visibility":  section1.get("VV", "N/A"),
                "wind":        section1.get("ff_kmph", "N/A"),
                "dew_point":   section1.get("Td", "N/A"),
                "humidity":    section1.get("humidity", "N/A"),
            })
        except Exception as e:
            print("ERROR:", e)
            results.append({
                "station": "ERROR", "temperature": "-",
                "weather": str(e), "visibility": "-",
                "wind": "-", "dew_point": "-", "humidity": "-"
            })

    latest_results = results
    summary = build_summary(results)
    charts   = build_charts(results)

    print("TOTAL RESULTS:", len(results))
    print("=" * 60)

    return render_template(
        "batch_upload.html",
        results=results,
        summary=summary,
        charts=charts
    )


# ==================================================
# HELPER: BUILD SUMMARY STATS
# ==================================================

def build_summary(results):
    valid_temps = []
    haze_count  = 0
    ts_count    = 0
    fog_count   = 0
    rain_count  = 0

    for row in results:
        try:
            valid_temps.append(float(row["temperature"]))
        except:
            pass

        wx = str(row.get("weather", "")).lower()
        if "haze" in wx:
            haze_count += 1
        if "thunderstorm" in wx or wx.startswith("ts"):
            ts_count += 1
        if "fog" in wx:
            fog_count += 1
        if "rain" in wx:
            rain_count += 1

    return {
        "total_stations": len(results),
        "max_temp":   round(max(valid_temps), 1) if valid_temps else "N/A",
        "min_temp":   round(min(valid_temps), 1) if valid_temps else "N/A",
        "avg_temp":   round(sum(valid_temps) / len(valid_temps), 1) if valid_temps else "N/A",
        "haze":       haze_count,
        "thunderstorm": ts_count,
        "fog":        fog_count,
        "rain":       rain_count,
    }


# ==================================================
# HELPER: BUILD CHARTS (base64 PNG)
# ==================================================

def build_charts(results):
    charts = {}

    # ── Temp Distribution ──────────────────────────────────────
    valid_temps = []
    for row in results:
        try:
            valid_temps.append(float(row["temperature"]))
        except:
            pass

    if valid_temps:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(valid_temps, bins=15, color="#0056b3", edgecolor="white", alpha=0.85)
        ax.set_title("Temperature Distribution", fontsize=14, fontweight="bold", color="#003366")
        ax.set_xlabel("Temperature (°C)", color="#444")
        ax.set_ylabel("Number of Stations", color="#444")
        ax.tick_params(colors="#555")
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_facecolor("#f9fbff")
        fig.patch.set_facecolor("#ffffff")
        plt.tight_layout()
        charts["temp_dist"] = _fig_to_b64(fig)
        plt.close(fig)

    # ── Top 10 Hottest Stations ────────────────────────────────
    station_temps = []
    for row in results:
        try:
            station_temps.append((row["station"], float(row["temperature"])))
        except:
            pass

    if station_temps:
        top10 = sorted(station_temps, key=lambda x: x[1], reverse=True)[:10]
        labels = [s for s, _ in top10]
        values = [t for _, t in top10]

        cmap = matplotlib.colormaps["YlOrRd"]
        norm_vals = [(v - min(values)) / (max(values) - min(values) + 0.001) for v in values]
        colors = [cmap(n) for n in norm_vals]

        fig, ax = plt.subplots(figsize=(8, 4))
        bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1], edgecolor="white")
        ax.set_title("Top 10 Hottest Stations", fontsize=14, fontweight="bold", color="#003366")
        ax.set_xlabel("Temperature (°C)", color="#444")
        ax.tick_params(colors="#555")
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_facecolor("#f9fbff")
        fig.patch.set_facecolor("#ffffff")

        for bar, val in zip(bars, values[::-1]):
            ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2,
                    f"{val}°C", va="center", fontsize=9, color="#333")

        plt.tight_layout()
        charts["top10"] = _fig_to_b64(fig)
        plt.close(fig)

    # ── Weather Condition Pie ──────────────────────────────────
    summary = build_summary(results)
    wx_data = {
        "Haze":         summary["haze"],
        "Thunderstorm": summary["thunderstorm"],
        "Fog":          summary["fog"],
        "Rain":         summary["rain"],
    }
    wx_data = {k: v for k, v in wx_data.items() if v > 0}
    other = summary["total_stations"] - sum(wx_data.values())
    if other > 0:
        wx_data["Other / Clear"] = other

    if wx_data and sum(wx_data.values()) > 0:
        pie_colors = ["#f39c12", "#e74c3c", "#95a5a6", "#3498db", "#2ecc71"]
        fig, ax = plt.subplots(figsize=(6, 4))
        wedges, texts, autotexts = ax.pie(
            list(wx_data.values()),
            labels=list(wx_data.keys()),
            autopct="%1.0f%%",
            colors=pie_colors[:len(wx_data)],
            startangle=140,
            pctdistance=0.8,
            wedgeprops=dict(edgecolor="white", linewidth=1.5)
        )
        for t in autotexts:
            t.set_fontsize(9)
        ax.set_title("Weather Conditions Breakdown", fontsize=13, fontweight="bold", color="#003366")
        fig.patch.set_facecolor("#ffffff")
        plt.tight_layout()
        charts["wx_pie"] = _fig_to_b64(fig)
        plt.close(fig)

    return charts


def _fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ==================================================
# MAP VIEW  (station coords lookup)
# ==================================================

STATION_COORDS = {
    "42182": (28.58, 77.20, "New Delhi"),
    "42299": (26.75, 83.37, "Gorakhpur"),
    "42339": (25.45, 81.73, "Allahabad"),
    "42401": (23.07, 72.63, "Ahmedabad"),
    "42492": (22.32, 87.32, "Kharagpur"),
    "42571": (21.10, 79.05, "Nagpur"),
    "42867": (17.45, 78.47, "Hyderabad"),
    "43003": (26.91, 75.80, "Jaipur"),
    "43057": (23.28, 77.35, "Bhopal"),
    "43128": (21.25, 81.63, "Raipur"),
    "43150": (20.27, 85.83, "Bhubaneswar"),
    "43192": (19.12, 72.85, "Mumbai"),
    "43279": (19.12, 72.85, "Mumbai (Santacruz)"),
    "43285": (18.53, 73.85, "Pune"),
    "43314": (17.72, 83.30, "Visakhapatnam"),
    "43325": (12.97, 77.59, "Bangalore"),
    "43346": (16.53, 80.52, "Vijayawada"),
    "43369": (13.00, 80.18, "Chennai (Meenambakkam)"),
    "43377": (13.07, 80.27, "Chennai (Nungambakkam)"),
    "43378": (12.82, 80.22, "Chennai"),
    "43418": (11.67, 78.13, "Salem"),
    "43466": (10.92, 76.97, "Coimbatore"),
    "43552": (11.03, 77.05, "Trichy"),
    "43599": (8.73,  77.70, "Tirunelveli"),
    "42071": (31.63, 74.87, "Amritsar"),
    "42101": (30.35, 76.78, "Chandigarh"),
    "42150": (28.58, 77.20, "Delhi (Palam)"),
    "42647": (22.65, 88.45, "Kolkata (Dum Dum)"),
    "42809": (21.10, 81.63, "Raipur"),
    "43149": (20.25, 85.82, "Bhubaneswar"),
}

WX_COLOR = {
    "haze":         "#f39c12",
    "fog":          "#95a5a6",
    "thunderstorm": "#e74c3c",
    "ts":           "#e74c3c",
    "rain":         "#3498db",
    "drizzle":      "#5dade2",
    "snow":         "#85c1e9",
    "clear":        "#2ecc71",
}

def wx_color(weather_str):
    s = str(weather_str).lower()
    for key, color in WX_COLOR.items():
        if key in s:
            return color
    return "#888888"


@app.route("/map")
def map_view():
    global latest_results
    stations_json = []
    for row in latest_results:
        stn = str(row.get("station", "")).strip()
        coords = STATION_COORDS.get(stn)
        if coords:
            lat, lon, name = coords
            stations_json.append({
                "station": stn,
                "name":    name,
                "lat":     lat,
                "lon":     lon,
                "temp":    row.get("temperature", "N/A"),
                "weather": row.get("weather", "N/A"),
                "wind":    row.get("wind", "N/A"),
                "visibility": row.get("visibility", "N/A"),
                "color":   wx_color(row.get("weather", "")),
            })
    return render_template("map_view.html", stations_json=json.dumps(stations_json))


# ==================================================
# API ROUTES (Docs and Programmatic Endpoint)
# ==================================================

@app.route("/docs")
def docs():
    return render_template("api_docs.html")


@app.route("/api/decode", methods=["POST"])
def api_decode():
    """
    Accepts raw JSON payload: {"synop": "AAXX 06091 43279 ..."}
    Returns decoded JSON structure.
    """
    data = request.get_json(silent=True)
    if not data or "synop" not in data:
        return {"error": "Invalid request. Provide a JSON body with a 'synop' key."}, 400
        
    synop_text = data["synop"]
    result, errors = decode_synop(synop_text)
    
    return {
        "success": True if result else False,
        "decoded": result,
        "errors": errors
    }, 200


# ==================================================
# FULL REPORT DOWNLOAD (TXT)
# ==================================================

@app.route("/download_report")
def download_report():
    global latest_results
    output = StringIO()
    output.write("=" * 60 + "\n")
    output.write("   SYNOP FM-12 DECODED WEATHER REPORT\n")
    output.write("   IMD Weather Intelligence Dashboard\n")
    output.write("=" * 60 + "\n\n")

    for i, row in enumerate(latest_results, 1):
        output.write("-" * 50 + "\n")
        output.write(f"  RECORD       : {i}\n")
        output.write(f"  STATION      : {row['station']}\n")
        t = row['temperature']
        output.write(f"  TEMPERATURE  : {t} °C\n" if t != "N/A" else f"  TEMPERATURE  : N/A\n")
        output.write(f"  DEW POINT    : {row.get('dew_point','N/A')} °C\n")
        output.write(f"  HUMIDITY     : {row.get('humidity','N/A')}\n")
        output.write(f"  WEATHER      : {row['weather']}\n")
        output.write(f"  VISIBILITY   : {row['visibility']}\n")
        output.write(f"  WIND SPEED   : {row['wind']} km/h\n")
        output.write("-" * 50 + "\n\n")

    output.write("=" * 60 + "\n")
    output.write(f"  TOTAL RECORDS: {len(latest_results)}\n")
    output.write("=" * 60 + "\n")

    return Response(
        output.getvalue(),
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=full_decoded_report.txt"}
    )


# ==================================================
# EXISTING DOWNLOADS
# ==================================================

@app.route("/download_csv")
def download_csv():
    global latest_results
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Station", "Temperature", "Dew Point", "Humidity", "Weather", "Visibility", "Wind"])
    for row in latest_results:
        writer.writerow([
            row["station"], row["temperature"], row.get("dew_point","N/A"),
            row.get("humidity","N/A"), row["weather"], row["visibility"], row["wind"]
        ])
    return Response(
        output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=decoded_synop.csv"}
    )


@app.route("/download_txt")
def download_txt():
    global latest_results
    output = StringIO()
    for row in latest_results:
        output.write(
            f"Station: {row['station']} | Temp: {row['temperature']} °C | "
            f"Weather: {row['weather']} | Visibility: {row['visibility']} | "
            f"Wind: {row['wind']} km/h\n"
        )
    return Response(
        output.getvalue(), mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=decoded_synop.txt"}
    )


@app.route("/download_json")
def download_json():
    global latest_results
    return Response(
        json.dumps(latest_results, indent=4), mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=decoded_synop.json"}
    )


@app.route("/download_excel")
def download_excel():
    global latest_results
    wb = Workbook()
    ws = wb.active
    ws.title = "Decoded SYNOP"
    ws.append(["Station", "Temperature", "Dew Point", "Humidity", "Weather", "Visibility", "Wind"])
    for row in latest_results:
        ws.append([
            row["station"], row["temperature"], row.get("dew_point","N/A"),
            row.get("humidity","N/A"), row["weather"], row["visibility"], row["wind"]
        ])
    file_path = "decoded_synop.xlsx"
    wb.save(file_path)
    with open(file_path, "rb") as f:
        excel_data = f.read()
    return Response(
        excel_data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=decoded_synop.xlsx"}
    )


if __name__ == "__main__":
    app.run(debug=True)