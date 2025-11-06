from flask import Flask, render_template, request, redirect,send_file
from datetime import datetime, timedelta
import http.client
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import time

app = Flask(__name__)

#MAIN_PAGE_HTML = 'main_page.html'
#RESULTS_PAGE_HTML = 'results_page.html'

MAIN_PAGE_HTML = 'main2.html'
RESULTS_PAGE_HTML = 'results2.html'
DEFAULT_STATION = "S115"

STATIONS = [
    {"id": "S06", "name": "Paya Lebar", "lat": 1.3524, "lon": 103.9007},
    {"id": "S24", "name": "Upper Changi Road North", "lat": 1.3678, "lon": 103.9826},
    {"id": "S43", "name": "Kim Chuan Road", "lat": 1.3399, "lon": 103.8878},
    {"id": "S44", "name": "Nanyang Avenue", "lat": 1.34583, "lon": 103.68166},
    {"id": "S50", "name": "Clementi Road", "lat": 1.3337, "lon": 103.7768},
    {"id": "S60", "name": "Sentosa", "lat": 1.25, "lon": 103.8279},
    {"id": "S102", "name": "Semakau Landfill", "lat": 1.189, "lon": 103.768},
    {"id": "S106", "name": "Pulau Ubin", "lat": 1.4168, "lon": 103.9673},
    {"id": "S107", "name": "East Coast Parkway", "lat": 1.3135, "lon": 103.9625},
    {"id": "S109", "name": "Ang Mo Kio Avenue 5", "lat": 1.3764, "lon": 103.8492},
    {"id": "S111", "name": "Scotts Road", "lat": 1.31055, "lon": 103.8365},
    {"id": "S115", "name": "Tuas South Avenue 3", "lat": 1.29377, "lon": 103.61843},
    {"id": "S117", "name": "Banyan Road", "lat": 1.256, "lon": 103.679}
]

API_ENDPOINTS = {
    "Wind Direction (°)": "/v2/real-time/api/wind-direction",
    "Wind Speed (Knots)": "/v2/real-time/api/wind-speed",
    "Temperature (°C)": "/v2/real-time/api/air-temperature",
    "Relative Humidity (%)": "/v2/real-time/api/relative-humidity",
    "Rainfall (mm)": "/v2/real-time/api/rainfall"
}


def fetch_nea_data_all_station(endpoint, date_param, station_id, start_time=None, end_time=None, max_retries=3, retry_delay=1):
    """
    Fetch all paginated readings for a given date, filter by station and optional time window.
    Retries on connection failures.
    """
    all_station_readings = []
    pagination_token = None
    start_dt = datetime.fromisoformat(start_time) if start_time else None
    end_dt = datetime.fromisoformat(end_time) if end_time else None

    while True:
        url = endpoint + date_param
        if pagination_token:
            url += f"&paginationToken={pagination_token}"

        for attempt in range(max_retries):
            try:
                conn = http.client.HTTPSConnection("api-open.data.gov.sg", timeout=5)
                conn.request("GET", url)
                res = conn.getresponse()
                if res.status != 200:
                    raise Exception(f"HTTP {res.status}")
                data = res.read()
                conn.close()

                data_json = json.loads(data)
                readings = data_json.get("data", {}).get("readings", [])

                for entry in readings:
                    ts_str = entry.get("timestamp")
                    ts_dt = datetime.fromisoformat(ts_str).replace(tzinfo=None)  # make naive
                    if start_dt and ts_dt < start_dt:
                        continue
                    if end_dt and ts_dt > end_dt:
                        continue
                    for r in entry.get("data", []):
                        if r.get("stationId") == station_id:
                            all_station_readings.append({"timestamp": ts_str, "value": r.get("value")})
                            break

                pagination_token = data_json.get("data", {}).get("paginationToken")
                break  # success, exit retry loop

            except Exception as e:
                print(f"Attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    print("Max retries reached. Stopping.")
                    return all_station_readings  # return what we have so far

        if not pagination_token:
            break

    return all_station_readings


def process_user_date(date_input, time_input):
    today_str = datetime.now().strftime('%Y-%m-%d')
    date_input = date_input.strip()
    if not date_input:
        date_input = today_str
    if not time_input or time_input == "":
        if date_input == today_str:
            return f"?date={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
        else:
            return f"?date={date_input}"
    time_parts = time_input.split(":")
    time_parts = [t if t else "00" for t in time_parts]
    while len(time_parts) < 3:
        time_parts.append("00")
    return f"?date={date_input}T{':'.join(time_parts[:3])}"


@app.route("/", methods=["GET", "POST"])
def index():
    current_date = datetime.now().strftime("%Y-%m-%d")
    selected_station = DEFAULT_STATION
    date_input = ""
    start_time = ""
    end_time = ""

    if request.method == "POST":
        selected_station = request.form.get("station", DEFAULT_STATION)
        date_input = request.form.get("date_input", "")
        start_time = request.form.get("start_time", "")
        end_time = request.form.get("end_time", "")

        return redirect(f"/results?station={selected_station}&date_input={date_input}&start_time={start_time}&end_time={end_time}")

    return render_template(MAIN_PAGE_HTML,
                           stations=STATIONS,
                           selected_station=selected_station,
                           date_input=date_input,
                           start_time=start_time,
                           end_time=end_time,
                           current_date=current_date)



from concurrent.futures import ThreadPoolExecutor

def fetch_all_for_station_window_parallel(station_id, date_input, start_time, end_time):
    date_param = f"?date={date_input}"
    all_results = {}

    def fetch(param_name, endpoint):
        return param_name, fetch_nea_data_all_station(endpoint, date_param, station_id, start_time, end_time)

    with ThreadPoolExecutor(max_workers=len(API_ENDPOINTS)) as executor:
        futures = [executor.submit(fetch, param, ep) for param, ep in API_ENDPOINTS.items()]
        for f in futures:
            param_name, readings = f.result()
            all_results[param_name] = readings

    # Flatten by timestamp
    timestamps = sorted({r["timestamp"] for lst in all_results.values() for r in lst})
    # final_results = []
    # for ts in timestamps:
    #     row = {"timestamp": ts, "data": {}}
    #     for param, lst in all_results.items():
    #         value = next((r["value"] for r in lst if r["timestamp"] == ts), None)
    #         row["data"][param] = value
    #     final_results.append(row)

    final_results = []
    for param, lst in all_results.items():
        # Convert timestamps to naive datetime objects
        for r in lst:
            r['dt'] = datetime.fromisoformat(r['timestamp']).replace(tzinfo=None)

    # Build a set of all timestamps across all readings
    all_timestamps = sorted({r['dt'] for lst in all_results.values() for r in lst})

    for ts in all_timestamps:
        row = {"timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"), "data": {}}
        for param, lst in all_results.items():
            value = next((r['value'] for r in lst if r['dt'] == ts), None)
            row['data'][param] = value
        final_results.append(row)


    return final_results

@app.route("/results", methods=["GET", "POST"])
def results():
    data_source = request.form if request.method == "POST" else request.args

    station_id = data_source.get("station", DEFAULT_STATION)
    date_input = data_source.get("date_input", "")
    start_time_input = data_source.get("start_time", "") or "00:00:00"
    end_time_input = data_source.get("end_time", "") or "23:55:00"

    # Ensure seconds
    if len(start_time_input.split(":")) == 2:
        start_time_input += ":00"
    if len(end_time_input.split(":")) == 2:
        end_time_input += ":00"

    start_dt_str = f"{date_input}T{start_time_input}"
    end_dt_str = f"{date_input}T{end_time_input}"

    # Fetch all readings for the station in the window
    all_results = fetch_all_for_station_window_parallel(station_id, date_input, start_dt_str, end_dt_str)
    
    # Convert timestamps in results to naive string format
    for row in all_results:
        ts_dt = datetime.fromisoformat(row["timestamp"]).replace(tzinfo=None)
        row["timestamp"] = ts_dt.strftime("%Y-%m-%d %H:%M:%S")

    station_name = next((s["name"] for s in STATIONS if s["id"] == station_id), "Unknown Station")
    param_names = list(API_ENDPOINTS.keys())

    return render_template(RESULTS_PAGE_HTML,
                           station_name=station_name,
                           selected_station=station_id,
                           all_results=all_results,
                           param_names=param_names)


@app.route("/export", methods=["POST"])
def export():
    station = request.form.get("station")
    station_name = request.form.get("station_name")
    export_format = request.form.get("format")
    
    # Pass param_names from template to ensure same order
    param_names = request.form.getlist("param_names[]")  # send this hidden input in template

    # Reconstruct the table from hidden inputs
    timestamps = request.form.getlist("timestamps[]")

    data_rows = []

    for ts in timestamps:
        row = {"Time": ts}
        for param in param_names:
            val = request.form.get(f"{ts}_{param}")
            row[param] = val
        data_rows.append(row)

    #df = pd.DataFrame(data_rows)
    df = pd.DataFrame(data_rows, columns=["Time"] + param_names)

    if export_format == "csv":
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(io.BytesIO(output.getvalue().encode('utf-8')),
                         mimetype="text/csv",
                         as_attachment=True,
                         download_name=f"{station}_weather.csv")

    elif export_format == "excel":
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        return send_file(output,
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True,
                         download_name=f"{station}_weather.xlsx")

    elif export_format == "pdf":
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []

        # Styles for PDF
        styles = getSampleStyleSheet()
        title = Paragraph(f"Weather Data for {station_name} ({station})", styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 12))

        # Prepare table data
        #table_data = [list(df.columns)] + df.values.tolist()
        table_data = [["Time"] + param_names] + df[["Time"] + param_names].values.tolist()

        table = Table(table_data)
        table_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
        ])
        table.setStyle(table_style)
        elements.append(table)

        doc.build(elements)
        buffer.seek(0)
        return send_file(buffer,
                         as_attachment=True,
                         download_name=f"{station}_weather.pdf",
                         mimetype='application/pdf')

    else:
        return "Invalid format", 400
        
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
