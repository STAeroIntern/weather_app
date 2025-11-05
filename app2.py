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


def fetch_nea_data_with_retry(endpoint, date_param, station_id, max_retries=3):
    retries = 0
    current_param = date_param

    # Determine if we have time in the param
    has_time = "T" in current_param

    while True:
        try:
            conn = http.client.HTTPSConnection("api-open.data.gov.sg")
            conn.request("GET", endpoint + current_param)
            res = conn.getresponse()
            data = res.read()
            conn.close()

            data_json = json.loads(data)
            readings = data_json.get("data", {}).get("readings", [])
            value = None
            if readings:
                for r in readings[0]["data"]:
                    if r["stationId"] == station_id:
                        value = r["value"]
                        break

            if value is not None:
                return value, current_param

            # If no value found
            if has_time and retries < max_retries:
                dt = datetime.strptime(current_param.replace("?date=", ""), "%Y-%m-%dT%H:%M:%S")
                dt -= timedelta(seconds=60)
                current_param = f"?date={dt.strftime('%Y-%m-%dT%H:%M:%S')}"
                retries += 1
            else:
                # No time or retries exhausted
                return None, current_param

        except Exception as e:
            print(f"Error fetching data: {e}")
            return None, current_param


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

def generate_time_intervals(date_input, start_time, end_time, interval_minutes=5):
    """
    Returns a list of datetime strings in ISO format every `interval_minutes`
    between start_time and end_time on the given date.
    """
    # If start_time/end_time empty, assume full day
    if not start_time:
        start_time = "00:00:00"
    if not end_time:
        end_time = "23:59:59"

    # Build full datetime strings
    start_dt = datetime.strptime(f"{date_input}T{start_time}", "%Y-%m-%dT%H:%M:%S")
    end_dt = datetime.strptime(f"{date_input}T{end_time}", "%Y-%m-%dT%H:%M:%S")

    timestamps = []
    current = start_dt
    while current <= end_dt:
        timestamps.append(current.strftime("%Y-%m-%dT%H:%M:%S"))
        current += timedelta(minutes=interval_minutes)
    return timestamps

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


def fetch_all_for_timestamp(station_id, timestamp):
    """Fetch all API readings for a single timestamp."""
    date_param = f"?date={timestamp}"
    results_dict = {}
    actual_time = timestamp

    with ThreadPoolExecutor(max_workers=len(API_ENDPOINTS)) as executor:
        future_to_param = {
            executor.submit(fetch_nea_data_with_retry, endpoint, date_param, station_id): param_name
            for param_name, endpoint in API_ENDPOINTS.items()
        }

        for future in as_completed(future_to_param):
            param_name = future_to_param[future]
            try:
                value, actual_param = future.result()
                results_dict[param_name] = value
                if actual_param:
                    actual_time = actual_param.replace("?date=", "").replace("T", " ")
            except Exception as e:
                print(f"Error fetching {param_name} for {timestamp}: {e}")
                results_dict[param_name] = None

    return {"timestamp": actual_time, "data": results_dict}


@app.route("/results", methods=["GET", "POST"])
def results():
    # Determine whether it's GET or POST
    data_source = request.form if request.method == "POST" else request.args

    station_id = data_source.get("station", DEFAULT_STATION)
    date_input = data_source.get("date_input", "")
    start_time_input = data_source.get("start_time", "00:00")
    end_time_input = data_source.get("end_time", "23:55")

    # Ensure seconds exist
    if len(start_time_input.split(":")) == 2:
        start_time_input += ":00"
    if len(end_time_input.split(":")) == 2:
        end_time_input += ":00"

    # Combine date + time into datetime objects
    start_dt = datetime.strptime(f"{date_input}T{start_time_input}", "%Y-%m-%dT%H:%M:%S")
    end_dt = datetime.strptime(f"{date_input}T{end_time_input}", "%Y-%m-%dT%H:%M:%S")

    # Generate timestamps every 5 minutes
    timestamps = []
    current_dt = start_dt
    while current_dt <= end_dt:
        timestamps.append(current_dt.strftime("%Y-%m-%dT%H:%M:%S"))
        current_dt += timedelta(minutes=5)

    # Parallel API fetching
    def fetch_all_for_timestamp(station_id, timestamp):
        date_param = f"?date={timestamp}"
        results_dict = {}
        actual_time = timestamp

        with ThreadPoolExecutor(max_workers=len(API_ENDPOINTS)) as executor:
            future_to_param = {
                executor.submit(fetch_nea_data_with_retry, endpoint, date_param, station_id): param_name
                for param_name, endpoint in API_ENDPOINTS.items()
            }

            for future in as_completed(future_to_param):
                param_name = future_to_param[future]
                try:
                    value, actual_param = future.result()
                    results_dict[param_name] = value
                    if actual_param:
                        actual_time = actual_param.replace("?date=", "").replace("T", " ")
                except Exception as e:
                    print(f"Error fetching {param_name} for {timestamp}: {e}")
                    results_dict[param_name] = None

        return {"timestamp": actual_time, "data": results_dict}

    all_results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ts = {executor.submit(fetch_all_for_timestamp, station_id, ts): ts for ts in timestamps}
        for future in as_completed(future_to_ts):
            all_results.append(future.result())

    # Sort results by timestamp
    all_results.sort(key=lambda x: x["timestamp"])

    station_name = next((s["name"] for s in STATIONS if s["id"] == station_id), "Unknown Station")

    return render_template(RESULTS_PAGE_HTML,
                           station_name=station_name,
                           selected_station=station_id,
                           all_results=all_results)


@app.route("/export", methods=["POST"])
def export():
    station = request.form.get("station")
    station_name = request.form.get("station_name")
    export_format = request.form.get("format")

    # Reconstruct the table from hidden inputs
    timestamps = request.form.getlist("timestamps[]")
    data_rows = []

    # Collect all columns from first timestamp
    all_params = []
    if timestamps:
        sample_ts = timestamps[0]
        for key in request.form.keys():
            if key.startswith(sample_ts + "_"):
                all_params.append(key[len(sample_ts)+1:])

    for ts in timestamps:
        row = {"Time": ts}
        for param in all_params:
            val = request.form.get(f"{ts}_{param}")
            row[param] = val
        data_rows.append(row)

    df = pd.DataFrame(data_rows)

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
        table_data = [list(df.columns)] + df.values.tolist()

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
