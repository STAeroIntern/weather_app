from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta
import http.client
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

MAIN_PAGE_HTML = 'main_page.html'
RESULTS_PAGE_HTML = 'results_page.html'
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

@app.route("/", methods=["GET", "POST"])
def index():
    current_date = datetime.now().strftime("%Y-%m-%d")
    selected_station = DEFAULT_STATION
    date_input = ""
    time_input = ""

    if request.method == "POST":
        selected_station = request.form.get("station", DEFAULT_STATION)
        date_input = request.form.get("date_input", "")
        time_input = request.form.get("time_input", "")

        return redirect(f"/results?station={selected_station}&date_input={date_input}&time_input={time_input}")

    return render_template(MAIN_PAGE_HTML,
                            stations=STATIONS,
                            selected_station=selected_station,
                            date_input=date_input,
                            time_input=time_input,
                            current_date=current_date)


@app.route("/results")
def results():
    station_id = request.args.get("station", DEFAULT_STATION)
    date_input = request.args.get("date_input", "")
    time_input = request.args.get("time_input", "")

    date_param = process_user_date(date_input, time_input)

    results_dict = {}
    actual_time = None

    # Use ThreadPoolExecutor for parallel API calls
    with ThreadPoolExecutor(max_workers=len(API_ENDPOINTS)) as executor:
        # Submit all API calls as futures
        future_to_param = {
            executor.submit(fetch_nea_data_with_retry, endpoint, date_param, station_id): param_name
            for param_name, endpoint in API_ENDPOINTS.items()
        }

        for future in as_completed(future_to_param):
            param_name = future_to_param[future]
            try:
                value, actual_param = future.result()
                results_dict[param_name] = value
                # Use the first successful actual_param for time
                if actual_time is None and actual_param:
                    actual_time = actual_param.replace("?date=", "").replace("T", " ")
            except Exception as e:
                print(f"Error fetching {param_name}: {e}")
                results_dict[param_name] = None

    return render_template(RESULTS_PAGE_HTML,
                            results=results_dict,
                            selected_station=station_id,
                            actual_time=actual_time)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
